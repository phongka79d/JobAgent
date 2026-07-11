"""Application metadata inventory, constraints, and identity rules."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from app.db.base import SINGLETON_PK, Base
from app.db.enums import (
    GraphSyncStatus,
    JdQuality,
    ProcessingStatus,
    RecordStatus,
)
from app.db.models import APPLICATION_TABLE_NAMES
from app.db.models.attachments import Attachment
from app.db.models.conversation import (
    AgentRun,
    ChatMessage,
    Conversation,
    ToolExecution,
)
from app.db.models.jobs import JobPost
from app.db.models.memory import MemoryFact
from app.db.models.outbox import GraphSyncOutbox
from app.db.models.profile import CandidateProfile, JobPreferences, ProfileDraft
from app.db.session import DatabaseSessionManager, create_session_manager
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

EXPECTED_TABLES = frozenset(APPLICATION_TABLE_NAMES)
LANGGRAPH_CHECKPOINT_MARKERS = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "models.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def test_metadata_contains_exactly_eleven_application_tables() -> None:
    table_names = set(Base.metadata.tables.keys())
    assert table_names == EXPECTED_TABLES
    assert len(APPLICATION_TABLE_NAMES) == 11
    assert table_names.isdisjoint(LANGGRAPH_CHECKPOINT_MARKERS)


def test_no_langgraph_checkpoint_models_registered() -> None:
    for name in Base.metadata.tables:
        assert "checkpoint" not in name.lower()


def test_job_status_dimensions_are_independent_and_exact() -> None:
    assert {m.value for m in ProcessingStatus} == {
        "received",
        "processing",
        "processed",
        "failed",
    }
    assert {m.value for m in JdQuality} == {"full", "partial", "unscorable"}
    assert {m.value for m in GraphSyncStatus} == {
        "not_required",
        "pending",
        "synced",
        "failed",
    }
    assert {m.value for m in RecordStatus} == {"active", "ignored_duplicate"}

    sets = [
        {m.value for m in ProcessingStatus},
        {m.value for m in JdQuality},
        {m.value for m in GraphSyncStatus},
        {m.value for m in RecordStatus},
    ]
    for i, left in enumerate(sets):
        for j, right in enumerate(sets):
            if i != j:
                assert left != right

    job_table = Base.metadata.tables["job_posts"]
    for column in (
        "processing_status",
        "jd_quality",
        "graph_sync_status",
        "record_status",
    ):
        assert column in job_table.c


def test_uuid_and_singleton_identity_rules_are_explicit() -> None:
    uuid_tables = {
        "attachments": Attachment,
        "profile_drafts": ProfileDraft,
        "job_posts": JobPost,
        "chat_messages": ChatMessage,
        "agent_runs": AgentRun,
        "tool_executions": ToolExecution,
        "graph_sync_outbox": GraphSyncOutbox,
        "memory_facts": MemoryFact,
    }
    for _name, model in uuid_tables.items():
        pk = inspect(model).primary_key[0]
        assert pk.name == "id"
        assert pk.type.python_type is uuid.UUID

    singleton_models = (CandidateProfile, JobPreferences, Conversation)
    for model in singleton_models:
        pk = inspect(model).primary_key[0]
        assert pk.name == "id"
        assert pk.type.python_type is int
        ck_sql = " ".join(
            str(c.sqltext) for c in model.__table__.constraints if hasattr(c, "sqltext")
        )
        assert str(SINGLETON_PK) in ck_sql

    # Business key remains required, unique, and indexed (not the PK).
    memory_key = MemoryFact.__table__.c.key
    assert memory_key.nullable is False
    assert memory_key.unique is True
    key_indexes = [
        ix
        for ix in MemoryFact.__table__.indexes
        if list(ix.columns.keys()) == ["key"]
    ]
    assert key_indexes, "memory_facts.key must be indexed"


def test_no_blob_columns_for_uploaded_bytes() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            type_name = type(column.type).__name__.lower()
            assert "largebinary" not in type_name
            assert "blob" not in type_name


def test_structured_json_columns_exist_without_generic_repository_api() -> None:
    json_columns = {
        ("candidate_profile", "profile_json"),
        ("profile_drafts", "draft_json"),
        ("job_preferences", "preferences_json"),
        ("job_posts", "extracted_json"),
        ("job_posts", "score_cache"),
        ("chat_messages", "structured_payload"),
        ("memory_facts", "value_json"),
        ("graph_sync_outbox", "payload"),
    }
    for table_name, column_name in json_columns:
        assert column_name in Base.metadata.tables[table_name].c

    import app.db as db_pkg

    # JSON remains model-owned; no generic repository facade on app.db.
    # Plan 2 Batch03 introduces a narrow AttachmentRepository only.
    assert not hasattr(db_pkg, "GenericRepository")
    assert not hasattr(db_pkg, "JsonRepository")
    repos_root = Path(__file__).resolve().parents[2] / "app" / "repositories"
    assert repos_root.is_dir()
    assert (repos_root / "attachments.py").is_file()
    assert not (repos_root / "generic.py").exists()


@pytest.mark.asyncio
async def test_create_all_materializes_eleven_tables(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        async with db_manager.engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            )
            names = {row[0] for row in result.fetchall()}
        assert EXPECTED_TABLES.issubset(names)
        assert names.isdisjoint(LANGGRAPH_CHECKPOINT_MARKERS)


async def _expect_integrity_error(
    db_manager: DatabaseSessionManager,
    build: object,
) -> None:
    """Flush a row that must violate a constraint; roll back without leaking."""
    session = db_manager.session_factory()
    try:
        session.add(build)  # type: ignore[arg-type]
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_foreign_keys_enforced(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        assert await db_manager.foreign_keys_enabled() is True
        await _expect_integrity_error(
            db_manager,
            ChatMessage(
                conversation_id=999,
                role="user",
                content="orphan",
            ),
        )


@pytest.mark.asyncio
async def test_singleton_and_uniqueness_rules(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        async with db_manager.session_scope() as session:
            session.add(
                Attachment(
                    file_hash="a" * 64,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=100,
                    page_count=1,
                    storage_path="staged/a.pdf",
                    state="staged",
                )
            )
            session.add(Conversation(id=SINGLETON_PK))
            session.add(
                CandidateProfile(
                    id=SINGLETON_PK,
                    profile_json={"summary": "ok"},
                )
            )
            session.add(
                JobPreferences(
                    id=SINGLETON_PK,
                    preferences_json={"roles": ["engineer"]},
                )
            )
            session.add(
                MemoryFact(
                    key="preferred_city",
                    value_json={"city": "Berlin"},
                    source="user",
                )
            )

        await _expect_integrity_error(
            db_manager,
            CandidateProfile(
                id=2,
                profile_json={"summary": "bad"},
            ),
        )
        await _expect_integrity_error(
            db_manager,
            Attachment(
                file_hash="a" * 64,
                original_name="other.pdf",
                mime_type="application/pdf",
                size_bytes=50,
                storage_path="staged/b.pdf",
                state="staged",
            ),
        )
        await _expect_integrity_error(
            db_manager,
            MemoryFact(
                key="preferred_city",
                value_json={"city": "Munich"},
                source="user",
            ),
        )

        async with db_manager.session_scope() as session:
            session.add(
                JobPost(
                    source_type="text",
                    raw_content="Job A",
                    raw_content_hash="b" * 64,
                    processing_status="received",
                    graph_sync_status="not_required",
                    record_status="active",
                )
            )
        await _expect_integrity_error(
            db_manager,
            JobPost(
                source_type="text",
                raw_content="Job B",
                raw_content_hash="b" * 64,
                processing_status="received",
                graph_sync_status="not_required",
                record_status="active",
            ),
        )


@pytest.mark.asyncio
async def test_independent_status_check_constraints(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        await _expect_integrity_error(
            db_manager,
            JobPost(
                source_type="text",
                raw_content="x",
                raw_content_hash="c" * 64,
                processing_status="full",
                graph_sync_status="not_required",
                record_status="active",
            ),
        )
        await _expect_integrity_error(
            db_manager,
            JobPost(
                source_type="text",
                raw_content="y",
                raw_content_hash="d" * 64,
                processing_status="received",
                jd_quality="processed",
                graph_sync_status="not_required",
                record_status="active",
            ),
        )

        async with db_manager.session_scope() as session:
            job = JobPost(
                source_type="url",
                source_url="https://example.com/job",
                raw_content="Engineer role",
                raw_content_hash="e" * 64,
                processing_status=ProcessingStatus.PROCESSED.value,
                jd_quality=JdQuality.PARTIAL.value,
                graph_sync_status=GraphSyncStatus.PENDING.value,
                record_status=RecordStatus.ACTIVE.value,
                extracted_json={"title": "Engineer"},
                score_cache={"semantic": 0.1},
            )
            session.add(job)
            await session.flush()
            loaded = (
                await session.execute(select(JobPost).where(JobPost.id == job.id))
            ).scalar_one()
            assert loaded.processing_status == "processed"
            assert loaded.jd_quality == "partial"
            assert loaded.graph_sync_status == "pending"
            assert loaded.record_status == "active"


@pytest.mark.asyncio
async def test_utc_timestamps_and_json_storage(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        async with db_manager.session_scope() as session:
            session.add(Conversation(id=SINGLETON_PK))
            fact = MemoryFact(
                key="preferred_city",
                value_json={"city": "Berlin"},
                source="user",
            )
            session.add(fact)
            session.add(
                GraphSyncOutbox(
                    operation="upsert_candidate",
                    entity_id=str(uuid.uuid4()),
                    payload={"id": "1", "skills": []},
                    status="pending",
                    attempts=0,
                )
            )
            await session.flush()
            assert fact.created_at.tzinfo is not None
            assert fact.created_at.utcoffset() is not None
            assert fact.created_at.utcoffset().total_seconds() == 0

        async with db_manager.session_scope() as session:
            loaded = (
                await session.execute(
                    select(MemoryFact).where(MemoryFact.key == "preferred_city")
                )
            ).scalar_one()
            assert loaded.value_json == {"city": "Berlin"}
            assert loaded.created_at.tzinfo is not None
            assert loaded.created_at.utcoffset() is not None
            assert loaded.created_at.utcoffset().total_seconds() == 0

            with pytest.raises(StatementError, match="timezone-aware"):
                loaded.updated_at = datetime.now()
                await session.flush()
            await session.rollback()


@pytest.mark.asyncio
async def test_relationships_and_duplicate_self_fk(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        async with db_manager.session_scope() as session:
            attachment = Attachment(
                file_hash="f" * 64,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                storage_path="staged/f.pdf",
                state="staged",
            )
            session.add(attachment)
            await session.flush()

            session.add(
                ProfileDraft(
                    source_attachment_id=attachment.id,
                    draft_json={"summary": "draft"},
                    state="pending",
                )
            )

            original = JobPost(
                source_type="text",
                raw_content="Original",
                raw_content_hash="1" * 64,
                processing_status="processed",
                jd_quality="full",
                graph_sync_status="synced",
                record_status="active",
            )
            session.add(original)
            await session.flush()

            session.add(
                JobPost(
                    source_type="text",
                    raw_content="Near duplicate",
                    raw_content_hash="2" * 64,
                    processing_status="processed",
                    jd_quality="full",
                    graph_sync_status="not_required",
                    record_status="ignored_duplicate",
                    duplicate_of_job_id=original.id,
                )
            )

            session.add(Conversation(id=SINGLETON_PK))
            await session.flush()
            message = ChatMessage(
                conversation_id=SINGLETON_PK,
                role="user",
                content="hello",
                structured_payload={"intent": "chat"},
            )
            session.add(message)
            await session.flush()
            run = AgentRun(
                message_id=message.id,
                state="running",
                pending_approval=False,
            )
            session.add(run)
            await session.flush()
            session.add(
                ToolExecution(
                    agent_run_id=run.id,
                    tool_name="save_job",
                    arguments_summary="url=https://example.com",
                    status="succeeded",
                    duration_ms=12,
                )
            )


@pytest.mark.asyncio
async def test_one_agent_run_per_user_turn_message(tmp_path: Path) -> None:
    """Database uniqueness enforces one run per message; resume reuses the row."""
    async with temporary_db(tmp_path) as db_manager:
        async with db_manager.session_scope() as session:
            session.add(Conversation(id=SINGLETON_PK))
            message = ChatMessage(
                conversation_id=SINGLETON_PK,
                role="user",
                content="resume me",
            )
            session.add(message)
            await session.flush()
            run = AgentRun(
                message_id=message.id,
                state="interrupted",
                pending_approval=True,
            )
            session.add(run)
            await session.flush()
            run_id = run.id
            message_id = message.id

        # Second run for the same user-turn message is rejected at the DB.
        await _expect_integrity_error(
            db_manager,
            AgentRun(
                message_id=message_id,
                state="pending",
                pending_approval=False,
            ),
        )

        # Interrupt/resume continues on the existing run row (same id).
        async with db_manager.session_scope() as session:
            existing = (
                await session.execute(
                    select(AgentRun).where(AgentRun.message_id == message_id)
                )
            ).scalar_one()
            assert existing.id == run_id
            existing.state = "running"
            existing.pending_approval = False
            await session.flush()
            resumed = (
                await session.execute(select(AgentRun).where(AgentRun.id == run_id))
            ).scalar_one()
            assert resumed.state == "running"
            assert resumed.message_id == message_id

        # ORM cardinality is one-to-one (uselist=False / singular relationship).
        message_rel = inspect(ChatMessage).relationships["agent_run"]
        assert message_rel.uselist is False
        run_message_col = AgentRun.__table__.c.message_id
        assert run_message_col.unique is True


@pytest.mark.asyncio
async def test_naive_datetime_rejected_on_bind(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db_manager:
        session = db_manager.session_factory()
        try:
            fact = MemoryFact(key="x", value_json=1, source="test")
            session.add(fact)
            await session.flush()
            with pytest.raises(StatementError, match="timezone-aware"):
                fact.created_at = datetime(2020, 1, 1, 12, 0, 0)
                await session.flush()
            await session.rollback()
        finally:
            await session.close()

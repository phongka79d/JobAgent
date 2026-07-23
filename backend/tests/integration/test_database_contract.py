"""Full SQLite schema contract: parity, constraints, FKs, cascades, PRAGMAs."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
from app.db import seed as seed_module
from app.db.session import (
    REQUIRED_BUSY_TIMEOUT_MS,
    REQUIRED_FOREIGN_KEYS,
    REQUIRED_JOURNAL_MODE,
    build_async_engine,
    read_connection_pragmas,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.support.db_migration import (
    BACKEND_ROOT,
    EXPECTED_FRESH_TABLES,
    assert_migrated_matches_accepted_models,
    expected_indexes,
    expected_named_constraints,
    observe_schema,
    run_async,
    session_factory,
)

TS = "2020-01-01"


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (shared harness fixture)."""
    return migrated_sqlite


async def _x(s: AsyncSession, sql: str) -> object:
    return await s.execute(text(sql))


async def _fail(f: async_sessionmaker[AsyncSession], sql: str) -> None:
    async with f() as s:
        with pytest.raises(IntegrityError):
            await _x(s, sql)
            await s.commit()
        await s.rollback()


async def _cnt(s: AsyncSession, t: str) -> int:
    return int((await _x(s, f"SELECT COUNT(*) FROM {t}")).scalar_one())


def _att(
    i: str,
    h: str,
    p: str,
    *,
    st: str = "staged",
    pages: int | None = None,
    mime: str = "application/pdf",
) -> str:
    pc = ", page_count" if pages is not None else ""
    pv = f", {pages}" if pages is not None else ""
    return (
        f"INSERT INTO attachments (id, file_hash, original_name, mime_type, "
        f"size_bytes{pc}, storage_path, state, created_at, updated_at) VALUES "
        f"('{i}', '{h}', 'x.pdf', '{mime}', 10{pv}, '{p}', '{st}', '{TS}', '{TS}')"
    )


def _profile(profile_id: str, attachment_id: str) -> str:
    return (
        "INSERT INTO profiles ("
        "id, attachment_id, display_name, profile_json, location, "
        "extraction_version, source_hash, state, created_at, updated_at, "
        "last_opened_at) VALUES ("
        f"'{profile_id}', '{attachment_id}', 'Profile', '{{}}', NULL, "
        f"'v1', 'hash-{profile_id}', 'ready', '{TS}', '{TS}', '{TS}')"
    )


def _pending_profile(
    profile_id: str,
    attachment_id: str,
    *,
    location_sql: str = "NULL",
) -> str:
    return (
        "INSERT INTO profiles ("
        "id, attachment_id, display_name, profile_json, location, "
        "extraction_version, source_hash, state, created_at, updated_at, "
        "last_opened_at) VALUES ("
        f"'{profile_id}', '{attachment_id}', 'Pending', NULL, {location_sql}, "
        f"NULL, NULL, 'pending', '{TS}', '{TS}', '{TS}')"
    )


def _conversation(conversation_id: str, profile_id: str) -> str:
    return (
        "INSERT INTO conversations ("
        "id, profile_id, title, created_at, updated_at, last_opened_at) VALUES ("
        f"'{conversation_id}', '{profile_id}', 'Chat', '{TS}', '{TS}', '{TS}')"
    )


def test_migrated_schema_exact_model_parity(db_path: Path) -> None:
    """Every table/column/type/null/constraint/index/FK matches accepted models."""

    async def _c() -> None:
        e = build_async_engine(db_path)
        try:
            async with e.connect() as c:

                def _check(sync_conn: object) -> None:
                    assert_migrated_matches_accepted_models(
                        sync_conn,  # type: ignore[arg-type]
                        exact_tables=EXPECTED_FRESH_TABLES,
                    )

                await c.run_sync(_check)
            # Programmatic completeness is asserted by the metadata oracle above;
            # avoid freezing counts that legitimately change with the contract.
            assert expected_named_constraints()
            assert expected_indexes()
        finally:
            await e.dispose()

    run_async(_c())


def test_schema_pragmas_and_partial_index_present(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        try:
            async with session_factory(e)() as s:
                pr = await read_connection_pragmas(s)
            assert pr["foreign_keys"] == REQUIRED_FOREIGN_KEYS
            assert pr["journal_mode"] == REQUIRED_JOURNAL_MODE
            assert pr["busy_timeout"] == REQUIRED_BUSY_TIMEOUT_MS
            partial = expected_indexes()["uq_attachments__single_active"]
            assert partial["unique"] is True
            assert partial["where"] == "state = 'active'"
            incomplete = expected_indexes()["uq_profiles__single_incomplete"]
            assert incomplete["unique"] is True
            assert incomplete["where"] == "profile_json is null"
        finally:
            await e.dispose()

    run_async(_c())


def test_invalid_rows_rejected_and_partial_unique(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            await _fail(
                f,
                f"INSERT INTO workspace_state (id, updated_at) "
                f"VALUES ('other', '{TS}')",
            )
            await _fail(f, _att("a1", "h1", "p1", mime="text/plain"))
            async with f() as s:
                await _x(s, _att("act1", "h1", "p1", st="active", pages=1))
                await s.commit()
            await _fail(f, _att("act2", "h2", "p2", st="active", pages=1))
        finally:
            await e.dispose()

    run_async(_c())


def test_database_rejects_partial_pending_profile(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _x(s, _att("pending-valid", "hpv", "ppv"))
                await _x(s, _pending_profile("profile-pending", "pending-valid"))
                await s.commit()

            async with f() as s:
                await _x(s, _att("pending-partial", "hpp", "ppp"))
                await s.commit()
            await _fail(
                f,
                _pending_profile(
                    "profile-partial",
                    "pending-partial",
                    location_sql="'Invented'",
                ),
            )
        finally:
            await e.dispose()

    run_async(_c())


def test_database_allows_only_one_incomplete_profile(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _x(s, _att("pending-one", "hpo", "ppo"))
                await _x(s, _pending_profile("profile-one", "pending-one"))
                await s.commit()

            async with f() as s:
                await _x(s, _att("pending-two", "hpt", "ppt"))
                await s.commit()
            await _fail(f, _pending_profile("profile-two", "pending-two"))
        finally:
            await e.dispose()

    run_async(_c())


def test_fk_restrict_and_cascade_chains(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _x(s, _att("att-r", "hr", "pr", st="active", pages=2))
                await _x(s, _profile("profile-r", "att-r"))
                await _x(s, _conversation("conv-r", "profile-r"))
                await _x(
                    s,
                    "INSERT INTO chat_messages "
                    "(id, conversation_id, role, content, created_at, updated_at) "
                    f"VALUES ('msg1', 'conv-r', 'user', 'hello', '{TS}', '{TS}')",
                )
                await _x(
                    s,
                    "INSERT INTO agent_runs "
                    "(id, user_message_id, state, created_at, updated_at) "
                    f"VALUES ('run1', 'msg1', 'running', '{TS}', '{TS}')",
                )
                await _x(
                    s,
                    "INSERT INTO tool_executions "
                    "(id, run_id, tool_call_id, tool_name, status, "
                    "created_at, updated_at) VALUES "
                    f"('tool1', 'run1', 'tc1', 'demo', 'pending', '{TS}', '{TS}')",
                )
                await s.commit()
            await _fail(f, "DELETE FROM attachments WHERE id = 'att-r'")
            async with f() as s:
                await _x(s, "DELETE FROM conversations WHERE id = 'conv-r'")
                await s.commit()
                assert await _cnt(s, "chat_messages") == 0
                assert await _cnt(s, "agent_runs") == 0
                assert await _cnt(s, "tool_executions") == 0
            async with f() as s:
                await _x(s, _att("att-d", "hd", "pd"))
                await _x(
                    s,
                    "INSERT INTO profile_drafts "
                    "(id, source_attachment_id, draft_json, created_at, updated_at) "
                    f"VALUES ('draft-1', 'att-d', '{{}}', '{TS}', '{TS}')",
                )
                await s.commit()
            async with f() as s:
                await _x(s, "DELETE FROM attachments WHERE id = 'att-d'")
                await s.commit()
                assert await _cnt(s, "profile_drafts") == 0
        finally:
            await e.dispose()

    run_async(_c())


def test_cv_ownership_cascade_and_set_null(db_path: Path) -> None:
    """Chunk/document CASCADE; message SET NULL; run/tool CASCADE on attach delete."""

    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with f() as s:
                await _x(s, _att("att-own", "hown", "pown"))
                await _x(s, _att("att-keep", "hkeep", "pkeep"))
                await _x(s, _profile("profile-keep", "att-keep"))
                await _x(s, _conversation("conv-keep", "profile-keep"))
                for sql in (
                    "INSERT INTO attachment_text_chunks ("
                    "id, attachment_id, ordinal, text, preview, "
                    "char_count, token_estimate, created_at) VALUES "
                    f"('chk1', 'att-own', 0, 'body', 'body', 4, 1, '{TS}')",
                    "INSERT INTO cv_documents ("
                    "attachment_id, document_json, profile_json, outline_json, "
                    "extraction_version, source_hash, created_at, updated_at) "
                    f"VALUES ('att-own', '{{}}', '{{}}', '{{}}', 'v1', 'h1', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO cv_document_drafts ("
                    "attachment_id, document_json, profile_json, outline_json, "
                    "extraction_version, source_hash, created_at, updated_at) "
                    f"VALUES ('att-own', '{{}}', '{{}}', '{{}}', 'v1', 'h1', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO chat_messages ("
                    "id, conversation_id, role, content, source_attachment_id, "
                    f"created_at, updated_at) VALUES "
                    f"('msg-own', 'conv-keep', 'user', 'cv note', 'att-own', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO chat_messages ("
                    "id, conversation_id, role, content, "
                    f"created_at, updated_at) VALUES "
                    f"('msg-plain', 'conv-keep', 'user', 'plain', '{TS}', '{TS}')",
                    "INSERT INTO agent_runs ("
                    "id, user_message_id, source_attachment_id, state, "
                    f"created_at, updated_at) VALUES "
                    f"('run-own', 'msg-own', 'att-own', 'running', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO agent_runs ("
                    "id, user_message_id, state, created_at, updated_at) "
                    f"VALUES ('run-plain', 'msg-plain', 'running', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO tool_executions ("
                    "id, run_id, source_attachment_id, tool_call_id, tool_name, "
                    "status, created_at, updated_at) VALUES "
                    f"('tool-own', 'run-plain', 'att-own', 'tc-own', 'read', "
                    f"'pending', '{TS}', '{TS}')",
                ):
                    await _x(s, sql)
                await s.commit()
            async with f() as s:
                await _x(s, "DELETE FROM attachments WHERE id = 'att-own'")
                await s.commit()
                assert await _cnt(s, "attachment_text_chunks") == 0
                assert await _cnt(s, "cv_documents") == 0
                assert await _cnt(s, "cv_document_drafts") == 0
                assert await _cnt(s, "agent_runs") == 1
                assert await _cnt(s, "tool_executions") == 0
                msg_src = (
                    await _x(
                        s,
                        "SELECT source_attachment_id, content "
                        "FROM chat_messages WHERE id = 'msg-own'",
                    )
                ).one()
                assert msg_src[0] is None
                assert msg_src[1] == "cv note"
                assert await _cnt(s, "attachments") == 1
            async with f() as s:
                await _x(
                    s,
                    "UPDATE attachments SET state = 'deleting' "
                    "WHERE id = 'att-keep'",
                )
                await s.commit()
                st = (
                    await _x(
                        s, "SELECT state FROM attachments WHERE id = 'att-keep'"
                    )
                ).scalar_one()
                assert st == "deleting"
        finally:
            await e.dispose()

    run_async(_c())


def test_no_create_all_in_app_or_migrations() -> None:
    """Runtime/migration sources must not invoke metadata schema creation."""
    pat = re.compile(r"create_all\(")
    hits = [
        str(p.relative_to(BACKEND_ROOT))
        for root in (BACKEND_ROOT / "app", BACKEND_ROOT / "migrations")
        for p in root.rglob("*.py")
        if pat.search(p.read_text(encoding="utf-8"))
    ]
    assert hits == [] and "create_all(" not in inspect.getsource(seed_module)


def test_workspace_seed_and_profile_tables_start_empty(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        try:
            async with e.connect() as c:
                row = (
                    await c.execute(
                        text("SELECT id, active_profile_id FROM workspace_state")
                    )
                ).one()
                counts = [
                    int(
                        (
                            await c.execute(text(f"SELECT COUNT(*) FROM {name}"))
                        ).scalar_one()
                    )
                    for name in ("profiles", "profile_preferences", "conversations")
                ]
            assert row == ("main", None)
            assert counts == [0, 0, 0]
        finally:
            await e.dispose()

    run_async(_c())


def _job_insert(job_id: str = "job-e1") -> str:
    return (
        "INSERT INTO job_posts ("
        "id, source_type, source_url, raw_content, raw_content_hash, "
        "extraction_json, processing_status, jd_quality, failure_code, "
        "embedding_json, embedding_model, embedding_dimensions, "
        "created_at, updated_at) VALUES ("
        f"'{job_id}', 'text', NULL, 'JD body', 'hash-{job_id}', "
        f"NULL, 'received', NULL, NULL, NULL, NULL, NULL, '{TS}', '{TS}')"
    )


def _eval_insert(
    *,
    eval_id: str,
    job_id: str,
    profile_id: str,
    ctx: str,
) -> str:
    result = json.dumps(
        {
            "job_id": job_id,
            "title": "T",
            "company": None,
            "location": None,
            "work_mode": "remote",
            "source_url": None,
            "final_score": 0.5,
            "quality_multiplier": 1.0,
            "components": {
                "semantic_similarity": 0.5,
                "skill_score": None,
                "seniority_score": None,
                "experience_score": None,
                "location_score": None,
                "work_mode_score": None,
            },
            "effective_weights": {"semantic_similarity": 1.0},
            "matched_required_skills": [],
            "matched_preferred_skills": [],
            "related_skills": [],
            "missing_required_skills": [],
            "summary": "ok",
        }
    ).replace("'", "''")
    return (
        "INSERT INTO job_evaluations ("
        "id, job_id, profile_id, evaluation_context_hash, "
        "job_revision, profile_revision, preferences_revision, "
        "cv_source_hash, matching_contract_version, result_json, "
        "created_at, updated_at) VALUES ("
        f"'{eval_id}', '{job_id}', '{profile_id}', '{ctx}', "
        f"'{TS}', '{TS}', '{TS}', 'cvhash', 'match_v1', '{result}', "
        f"'{TS}', '{TS}')"
    )


def test_job_evaluations_named_schema_and_cascades(db_path: Path) -> None:
    """Named unique/index and CASCADE from job_posts and profiles."""

    async def _c() -> None:
        e = build_async_engine(db_path)
        f = session_factory(e)
        try:
            async with e.connect() as c:

                def _check(sync_conn: object) -> None:
                    observed = observe_schema(sync_conn)  # type: ignore[arg-type]
                    assert "uq_job_evaluations__job_profile_context" in (
                        observed["named_constraints"]
                    )
                    assert "ix_job_evaluations__job_created_at" in (
                        observed["indexes"]
                    )
                    ix = observed["indexes"][
                        "ix_job_evaluations__job_created_at"
                    ]
                    assert ix["columns"] == ("job_id", "created_at")
                    assert ix["unique"] is False
                    fks = observed["foreign_keys"]
                    assert (
                        "job_evaluations",
                        "job_id",
                        "job_posts",
                        "id",
                        "CASCADE",
                    ) in fks
                    assert (
                        "job_evaluations",
                        "profile_id",
                        "profiles",
                        "id",
                        "CASCADE",
                    ) in fks

                await c.run_sync(_check)

            async with f() as s:
                await _x(s, _att("att-e1", "he1", "pe1"))
                await _x(s, _profile("profile-e1", "att-e1"))
                await _x(s, _job_insert("job-e1"))
                await _x(
                    s,
                    _eval_insert(
                        eval_id="eval-1",
                        job_id="job-e1",
                        profile_id="profile-e1",
                        ctx="ctx-a",
                    ),
                )
                await s.commit()

            # Unique (job_id, profile_id, evaluation_context_hash).
            await _fail(
                f,
                _eval_insert(
                    eval_id="eval-dup",
                    job_id="job-e1",
                    profile_id="profile-e1",
                    ctx="ctx-a",
                ),
            )

            async with f() as s:
                await _x(s, "DELETE FROM job_posts WHERE id = 'job-e1'")
                await s.commit()
                assert await _cnt(s, "job_evaluations") == 0

            async with f() as s:
                await _x(s, _att("att-e2", "he2", "pe2"))
                await _x(s, _profile("profile-e2", "att-e2"))
                await _x(s, _job_insert("job-e2"))
                await _x(
                    s,
                    _eval_insert(
                        eval_id="eval-2",
                        job_id="job-e2",
                        profile_id="profile-e2",
                        ctx="ctx-b",
                    ),
                )
                await s.commit()
            async with f() as s:
                await _x(s, "DELETE FROM profiles WHERE id = 'profile-e2'")
                await _x(s, "DELETE FROM attachments WHERE id = 'att-e2'")
                await s.commit()
                assert await _cnt(s, "job_evaluations") == 0
                assert await _cnt(s, "job_posts") == 1
        finally:
            await e.dispose()

    run_async(_c())

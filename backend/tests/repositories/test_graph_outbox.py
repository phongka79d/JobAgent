"""Graph outbox repository: transactional enqueue, replay, claims, payload safety."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.enums import OutboxStatus
from app.db.models.outbox import GraphSyncOutbox
from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.graph_outbox import (
    GraphOutboxDuplicateError,
    GraphOutboxNotFoundError,
    GraphOutboxPayloadError,
    GraphOutboxRepository,
    GraphOutboxRepositoryError,
    GraphOutboxStateError,
    validate_outbox_payload,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    manager = create_session_manager(tmp_path / "outbox.db")
    await manager.create_all()
    try:
        yield manager
    finally:
        await manager.dispose()


def _payload(entity_id: str | None = None) -> dict[str, object]:
    eid = entity_id or str(uuid4())
    return {"entity_id": eid, "skill_keys": ["python"], "version": 1}


@pytest.mark.asyncio
async def test_enqueue_and_claim_round_trip(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            row = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            assert row.status == OutboxStatus.PENDING.value
            assert row.attempts == 0
            assert row.last_error is None
            assert row.payload["entity_id"] == entity_id

            claimed = await repo.claim_pending(limit=10)
            assert len(claimed) == 1
            assert claimed[0].id == row.id


@pytest.mark.asyncio
async def test_same_transaction_rollback_discards_enqueue(tmp_path: Path) -> None:
    """Rolling back a unit of work also rolls back its outbox enqueue."""
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        session = db.session_factory()
        try:
            repo = GraphOutboxRepository(session)
            await repo.enqueue(
                operation="upsert_candidate",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            await session.rollback()
        finally:
            await session.close()

        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            assert await repo.get_by_identity("upsert_candidate", entity_id) is None
            claimed = await repo.claim_pending(limit=10)
            assert claimed == []
            count = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_enqueue_does_not_commit_implicitly(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        session_a: AsyncSession = db.session_factory()
        try:
            repo = GraphOutboxRepository(session_a)
            row = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            assert row.id is not None
            assert await repo.get_by_identity("upsert_job", entity_id) is not None

            session_b = db.session_factory()
            try:
                repo_b = GraphOutboxRepository(session_b)
                assert await repo_b.get_by_identity("upsert_job", entity_id) is None
            finally:
                await session_b.close()
        finally:
            await session_a.rollback()
            await session_a.close()


@pytest.mark.asyncio
async def test_replay_enqueue_returns_same_row_without_reset(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            first = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            failed = await repo.mark_failed(first.id, error="neo4j_unavailable")
            assert failed.status == OutboxStatus.FAILED.value
            assert failed.attempts == 1

            # Replay with a different payload must not create a second row or
            # reset attempts / terminal state.
            second = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload={
                    "entity_id": entity_id,
                    "skill_keys": ["rust"],
                    "version": 99,
                },
            )
            assert second.id == first.id
            assert second.attempts == 1
            assert second.status == OutboxStatus.FAILED.value
            assert second.payload["version"] == 1  # original payload retained

            count = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_cross_session_replay_is_idempotent(tmp_path: Path) -> None:
    """After commit, a later session replaying the same identity reuses the row."""
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            first = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            first_id = first.id
            await repo.mark_failed(first.id, error="neo4j_unavailable")

        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            second = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload={
                    "entity_id": entity_id,
                    "skill_keys": ["go"],
                    "version": 2,
                },
            )
            assert second.id == first_id
            assert second.attempts == 1
            assert second.status == OutboxStatus.FAILED.value
            count = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert count == 1


@pytest.mark.asyncio
async def test_unique_identity_rejects_raw_second_insert(tmp_path: Path) -> None:
    """Schema uniqueness remains enforceable outside the idempotent enqueue path."""
    from sqlalchemy.exc import IntegrityError

    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )

        session = db.session_factory()
        try:
            session.add(
                GraphSyncOutbox(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload=_payload(entity_id),
                    status=OutboxStatus.PENDING.value,
                    attempts=0,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_racey_enqueue_raises_duplicate_when_lookup_misses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If identity lookup misses an already-flushed peer, uniqueness fails closed."""
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )

        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)

            async def _miss(
                operation: str, entity_id: str
            ) -> GraphSyncOutbox | None:
                return None

            monkeypatch.setattr(repo, "get_by_identity", _miss)
            with pytest.raises(GraphOutboxDuplicateError, match="duplicate"):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload=_payload(entity_id),
                )


@pytest.mark.asyncio
async def test_claim_pending_is_bounded_and_deterministic(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        ids: list[str] = []
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            for _ in range(5):
                eid = str(uuid4())
                ids.append(eid)
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=eid,
                    payload=_payload(eid),
                )

        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            first_batch = await repo.claim_pending(limit=2)
            assert len(first_batch) == 2
            # Deterministic: earliest created_at, then id.
            assert first_batch[0].created_at <= first_batch[1].created_at
            if first_batch[0].created_at == first_batch[1].created_at:
                assert first_batch[0].id < first_batch[1].id

            again = await repo.claim_pending(limit=2)
            assert [r.id for r in again] == [r.id for r in first_batch]

            all_rows = await repo.claim_pending(limit=10)
            assert len(all_rows) == 5
            for earlier, later in zip(all_rows, all_rows[1:], strict=False):
                assert (earlier.created_at, earlier.id) <= (later.created_at, later.id)


@pytest.mark.asyncio
async def test_claim_limit_validation(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            with pytest.raises(GraphOutboxRepositoryError, match="claim limit"):
                await repo.claim_pending(limit=0)
            with pytest.raises(GraphOutboxRepositoryError, match="claim limit"):
                await repo.claim_pending(limit=501)
            with pytest.raises(GraphOutboxRepositoryError, match="claim limit"):
                await repo.claim_pending(limit=-1)


@pytest.mark.asyncio
async def test_mark_synced_and_mark_failed_transitions(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            row = await repo.enqueue(
                operation="upsert_skill",
                entity_id=entity_id,
                payload={"entity_id": entity_id, "canonical_key": "python"},
            )

            failed = await repo.mark_failed(row.id, error="neo4j_unavailable")
            assert failed.status == OutboxStatus.FAILED.value
            assert failed.attempts == 1
            assert failed.last_error == "neo4j_unavailable"

            failed_again = await repo.mark_failed(row.id, error="timeout")
            assert failed_again.attempts == 2
            assert failed_again.last_error == "timeout"

            # Terminal synced is durable; further failure is rejected.
            synced = await repo.mark_synced(row.id)
            assert synced.status == OutboxStatus.SYNCED.value
            assert synced.last_error is None
            assert synced.attempts == 2  # attempts not reset on success

            again = await repo.mark_synced(row.id)
            assert again.status == OutboxStatus.SYNCED.value

            with pytest.raises(GraphOutboxStateError):
                await repo.mark_failed(row.id, error="late")


@pytest.mark.asyncio
async def test_failure_recovery_requeue_preserves_attempts(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            row = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            await repo.mark_failed(row.id, error="neo4j_unavailable")
            await repo.mark_failed(row.id, error="neo4j_unavailable")

            # Failed rows are not claimable as pending until requeued.
            assert await repo.claim_pending(limit=10) == []

            requeued = await repo.requeue_failed(row.id)
            assert requeued.status == OutboxStatus.PENDING.value
            assert requeued.attempts == 2
            assert requeued.last_error == "neo4j_unavailable"

            claimed = await repo.claim_pending(limit=10)
            assert len(claimed) == 1
            assert claimed[0].id == row.id
            assert claimed[0].attempts == 2


@pytest.mark.asyncio
async def test_mark_missing_row_raises(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            missing = uuid4()
            with pytest.raises(GraphOutboxNotFoundError):
                await repo.mark_synced(missing)
            with pytest.raises(GraphOutboxNotFoundError):
                await repo.mark_failed(missing, error="x")
            with pytest.raises(GraphOutboxNotFoundError):
                await repo.requeue_failed(missing)


@pytest.mark.asyncio
async def test_payload_rejection_paths_secrets_raw_documents(tmp_path: Path) -> None:
    entity_id = str(uuid4())
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)

            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"entity_id": entity_id, "storage_path": "active/x"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={
                        "entity_id": entity_id,
                        "path": str(tmp_path / "secret.pdf"),
                    },
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"entity_id": entity_id, "api_key": "should-not-store"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={
                        "entity_id": entity_id,
                        "note": "BEGIN PRIVATE KEY\nabc\n",
                    },
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"entity_id": entity_id, "raw_content": "full jd text"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"entity_id": entity_id, "blob": b"\x00\x01"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"entity_id": entity_id, "doc": "x" * 3000},
                )

            # No durable row after rejections.
            count = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert count == 0


def test_validate_outbox_payload_errors_do_not_echo_values() -> None:
    secret = "super-secret-token-value-xyz"
    path = r"C:\Users\ACER\hidden\file.pdf"
    with pytest.raises(GraphOutboxPayloadError) as ei_key:
        validate_outbox_payload({"api_key": secret})
    assert secret not in str(ei_key.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_path:
        validate_outbox_payload({"entity_id": "1", "ref": path})
    assert path not in str(ei_path.value)
    assert "hidden" not in str(ei_path.value)


def test_payload_rejects_relative_service_paths_credentials_and_documents() -> None:
    """A2 probes: relative service path, Basic credential, raw document key."""
    entity_id = str(uuid4())
    service_path = f"active/{entity_id}"
    basic_cred = "Basic dXNlcjpwYXNz"
    raw_doc = (
        "This is the full raw job description text that must not be stored "
        "in the outbox payload as document content."
    )

    with pytest.raises(GraphOutboxPayloadError) as ei_path:
        validate_outbox_payload({"attachment": service_path})
    assert service_path not in str(ei_path.value)
    assert entity_id not in str(ei_path.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_cred:
        validate_outbox_payload({"configuration": basic_cred})
    assert basic_cred not in str(ei_cred.value)
    assert "dXNlcjpwYXNz" not in str(ei_cred.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_doc:
        validate_outbox_payload({"document": raw_doc})
    assert raw_doc not in str(ei_doc.value)
    assert "job description" not in str(ei_doc.value)

    # Staged service path and other relative multi-segment paths.
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"ref": f"staged/{entity_id}"})
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"ref": "files/sub/item.bin"})


def test_payload_rejects_posix_absolute_and_file_uri_paths() -> None:
    """All POSIX absolute forms and file: filesystem URIs fail closed."""
    cases = (
        "/",
        "/tmp",
        "/etc",
        "/var/log/app.log",
        "file:///tmp/secret.pdf",
        "file://localhost/tmp/x",
        "file:/tmp/alone",
        "FILE:///C:/Users/hidden/file.pdf",
        # Quoted and embedded filesystem URIs under ordinary keys.
        '"file:///tmp/secret.pdf"',
        "open file:///tmp/secret.pdf",
        "dsn=file:/var/lib/jobagent/secret.pdf",
    )
    for path_value in cases:
        with pytest.raises(GraphOutboxPayloadError) as ei:
            validate_outbox_payload({"ref": path_value})
        msg = str(ei.value)
        # Generic code-only errors; never echo the submitted path or fragments.
        assert msg == "filesystem path not permitted"
        assert path_value not in msg
        assert "secret" not in msg
        assert "hidden" not in msg
        assert "Users" not in msg


def test_payload_rejects_credential_uri_and_header_value_forms() -> None:
    """Credential-bearing URI userinfo and header/colon/equal assignment forms."""
    pg_uri = "postgresql://user:s3cretPass@localhost/db"
    postgres_uri = "postgres://admin:hunter2@host:5432/app"
    mysql_uri = "mysql://u:p@h/db"
    neo4j_uri = "neo4j://neo4j:graphSecret@localhost:7687"
    https_userinfo = "https://api:tokenValue@example.com/v1"
    # Mid-string / prefixed forms must fail closed, not only whole-value URIs.
    jdbc_pg = "jdbc:postgresql://sync:nestedJdbcSecret@db/app"
    dsn_pg = "dsn=postgresql://user:dsnSecret@localhost/db"
    quoted_pg = '"postgresql://user:quotedSecret@localhost/db"'
    password_header = "password: hunter2-value"
    api_key_header = "X-Api-Key: abcd1234secret"
    passwd_header = "Passwd: still-secret"
    labeled_header = "cfg=password: labeledHeaderSecret"
    # Equal-sign credential assignments with optional whitespace (source category).
    password_eq_ws = "password = equalWsSecret"
    password_eq_case = "Password = EqualCaseSecret"
    x_api_key_eq_ws = "X-Api-Key = xApiKeyEqualWsSecret"
    x_api_key_eq_tight = "x-api-key=xApiKeyEqualTightSecret"
    api_key_eq_ws = "api_key = apiKeyEqualWsSecret"
    password_eq_tight = "password=equalTightSecret"
    labeled_eq = "cfg=password = labeledEqualSecret"

    secret_fragments = (
        "s3cretPass",
        "hunter2",
        "graphSecret",
        "tokenValue",
        "nestedJdbcSecret",
        "dsnSecret",
        "quotedSecret",
        "abcd1234secret",
        "still-secret",
        "labeledHeaderSecret",
        "equalWsSecret",
        "EqualCaseSecret",
        "xApiKeyEqualWsSecret",
        "xApiKeyEqualTightSecret",
        "apiKeyEqualWsSecret",
        "equalTightSecret",
        "labeledEqualSecret",
    )

    for cred in (
        pg_uri,
        postgres_uri,
        mysql_uri,
        neo4j_uri,
        https_userinfo,
        jdbc_pg,
        dsn_pg,
        quoted_pg,
        password_header,
        api_key_header,
        passwd_header,
        labeled_header,
        password_eq_ws,
        password_eq_case,
        x_api_key_eq_ws,
        x_api_key_eq_tight,
        api_key_eq_ws,
        password_eq_tight,
        labeled_eq,
    ):
        with pytest.raises(GraphOutboxPayloadError) as ei:
            validate_outbox_payload({"configuration": cred})
        msg = str(ei.value)
        assert msg == "prohibited content category"
        assert cred not in msg
        for fragment in secret_fragments:
            assert fragment not in msg

    # Public HTTP URLs without userinfo remain permitted structured data.
    ok = validate_outbox_payload(
        {"entity_id": "e1", "source_url": "https://example.com/jobs/1"}
    )
    assert ok["source_url"] == "https://example.com/jobs/1"


def test_payload_rejects_transcript_and_alternate_document_categories() -> None:
    """Alternate raw-document categories (transcript) fail closed by category."""
    transcript_body = (
        "This is a full interview transcript that must never be stored "
        "in the graph outbox payload as raw document content."
    )
    with pytest.raises(GraphOutboxPayloadError) as ei:
        validate_outbox_payload({"transcript": transcript_body})
    msg = str(ei.value)
    assert transcript_body not in msg
    assert "interview transcript" not in msg

    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"interview_transcript": "dump"})
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"transcription_notes": "dump"})


def test_payload_rejects_nested_prohibited_categories() -> None:
    """Nested maps/lists must apply the same fail-closed policy."""
    entity_id = str(uuid4())
    service_path = f"active/{entity_id}"
    basic_cred = "Basic YWRtaW46c2VjcmV0"
    raw_doc = "Nested raw CV body that must never enter the outbox."
    posix_root = "/"
    posix_single = "/tmp"
    file_uri = "file:///var/lib/jobagent/secret.pdf"
    pg_uri = "postgresql://sync:nestedSecret@db/app"
    password_header = "password: nested-header-secret"
    transcript_body = "Nested full transcript body that must never enter outbox."

    with pytest.raises(GraphOutboxPayloadError) as ei_path:
        validate_outbox_payload(
            {"entity_id": entity_id, "meta": {"attachment": service_path}}
        )
    assert service_path not in str(ei_path.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_cred:
        validate_outbox_payload(
            {
                "entity_id": entity_id,
                "items": [{"configuration": basic_cred}],
            }
        )
    assert basic_cred not in str(ei_cred.value)
    assert "YWRtaW46c2VjcmV0" not in str(ei_cred.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_doc:
        validate_outbox_payload(
            {"entity_id": entity_id, "payload": {"document": raw_doc}}
        )
    assert raw_doc not in str(ei_doc.value)
    assert "Nested raw CV" not in str(ei_doc.value)

    # Nested POSIX absolute, file URI, credential URI/header, and transcript.
    with pytest.raises(GraphOutboxPayloadError) as ei_posix:
        validate_outbox_payload({"entity_id": entity_id, "meta": {"ref": posix_root}})
    assert str(ei_posix.value) == "filesystem path not permitted"

    with pytest.raises(GraphOutboxPayloadError) as ei_single:
        validate_outbox_payload(
            {"entity_id": entity_id, "items": [{"location": posix_single}]}
        )
    assert str(ei_single.value) == "filesystem path not permitted"
    assert posix_single not in str(ei_single.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_file:
        validate_outbox_payload(
            {"entity_id": entity_id, "nested": {"uri": file_uri}}
        )
    assert str(ei_file.value) == "filesystem path not permitted"
    assert file_uri not in str(ei_file.value)
    assert "secret.pdf" not in str(ei_file.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_pg:
        validate_outbox_payload(
            {"entity_id": entity_id, "items": [{"endpoint": pg_uri}]}
        )
    assert str(ei_pg.value) == "prohibited content category"
    assert pg_uri not in str(ei_pg.value)
    assert "nestedSecret" not in str(ei_pg.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_jdbc:
        validate_outbox_payload(
            {
                "entity_id": entity_id,
                "items": [{"endpoint": "jdbc:postgresql://u:jdbcNested@h/db"}],
            }
        )
    assert str(ei_jdbc.value) == "prohibited content category"
    assert "jdbcNested" not in str(ei_jdbc.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_embed_file:
        validate_outbox_payload(
            {
                "entity_id": entity_id,
                "nested": {"uri": "open file:///var/lib/jobagent/secret.pdf"},
            }
        )
    assert str(ei_embed_file.value) == "filesystem path not permitted"
    assert "secret.pdf" not in str(ei_embed_file.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_hdr:
        validate_outbox_payload(
            {"entity_id": entity_id, "meta": {"header": password_header}}
        )
    assert str(ei_hdr.value) == "prohibited content category"
    assert password_header not in str(ei_hdr.value)
    assert "nested-header-secret" not in str(ei_hdr.value)

    # Nested equal-sign credential assignments with optional whitespace.
    password_eq_ws = "password = nestedEqualWsSecret"
    x_api_key_eq_ws = "X-Api-Key = nestedXApiEqualWsSecret"
    with pytest.raises(GraphOutboxPayloadError) as ei_eq:
        validate_outbox_payload(
            {"entity_id": entity_id, "meta": {"configuration": password_eq_ws}}
        )
    assert str(ei_eq.value) == "prohibited content category"
    assert password_eq_ws not in str(ei_eq.value)
    assert "nestedEqualWsSecret" not in str(ei_eq.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_xeq:
        validate_outbox_payload(
            {
                "entity_id": entity_id,
                "items": [{"configuration": x_api_key_eq_ws}],
            }
        )
    assert str(ei_xeq.value) == "prohibited content category"
    assert x_api_key_eq_ws not in str(ei_xeq.value)
    assert "nestedXApiEqualWsSecret" not in str(ei_xeq.value)

    with pytest.raises(GraphOutboxPayloadError) as ei_tr:
        validate_outbox_payload(
            {"entity_id": entity_id, "payload": {"transcript": transcript_body}}
        )
    assert str(ei_tr.value) == "prohibited payload key"
    assert transcript_body not in str(ei_tr.value)
    assert "Nested full transcript" not in str(ei_tr.value)

    # Category keys with alternate spellings still fail closed.
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"entity_id": entity_id, "raw_text": "dump"})
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"entity_id": entity_id, "document_text": "dump"})
    with pytest.raises(GraphOutboxPayloadError):
        validate_outbox_payload({"entity_id": entity_id, "attachment_ref": "x"})


@pytest.mark.asyncio
async def test_enqueue_rejects_a2_payload_probes(tmp_path: Path) -> None:
    """Repository enqueue surface rejects A2 path/credential/document categories."""
    entity_id = str(uuid4())
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"attachment": f"active/{entity_id}"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"configuration": "Basic dXNlcjpwYXNz"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"document": "raw document content for rejection"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"ref": "/"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"ref": "/tmp"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"ref": "file:///tmp/secret.pdf"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={
                        "configuration": "postgresql://user:pass@localhost/db",
                    },
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"configuration": "password: hunter2"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"configuration": "password = equalWsEnqueueSecret"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"configuration": "X-Api-Key = xApiEnqueueSecret"},
                )
            with pytest.raises(GraphOutboxPayloadError):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id=entity_id,
                    payload={"transcript": "full interview transcript body"},
                )
            count = (
                await session.execute(select(func.count()).select_from(GraphSyncOutbox))
            ).scalar_one()
            assert count == 0


@pytest.mark.asyncio
async def test_failed_error_sanitizes_path_shaped_messages(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            row = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            bad = str(tmp_path / "leak.db")
            failed = await repo.mark_failed(row.id, error=bad)
            assert failed.last_error == "sync_failed"
            assert bad not in (failed.last_error or "")


@pytest.mark.asyncio
async def test_mark_failed_sanitizes_equal_sign_credential_errors(
    tmp_path: Path,
) -> None:
    """Credential assignment shapes must not persist in last_error."""
    async with temporary_db(tmp_path) as db:
        entity_id = str(uuid4())
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            row = await repo.enqueue(
                operation="upsert_job",
                entity_id=entity_id,
                payload=_payload(entity_id),
            )
            password_eq = "password = markFailedEqualWsSecret"
            failed = await repo.mark_failed(row.id, error=password_eq)
            assert failed.last_error == "sync_failed"
            assert password_eq not in (failed.last_error or "")
            assert "markFailedEqualWsSecret" not in (failed.last_error or "")

            x_api = "X-Api-Key = markFailedXApiEqualSecret"
            failed_again = await repo.mark_failed(row.id, error=x_api)
            assert failed_again.last_error == "sync_failed"
            assert x_api not in (failed_again.last_error or "")
            assert "markFailedXApiEqualSecret" not in (failed_again.last_error or "")
            assert failed_again.attempts == 2

            # Generic code-only errors with no credential shape remain intact.
            plain = await repo.mark_failed(row.id, error="neo4j_unavailable")
            assert plain.last_error == "neo4j_unavailable"


@pytest.mark.asyncio
async def test_invalid_operation_and_entity_rejected(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            with pytest.raises(GraphOutboxRepositoryError, match="operation"):
                await repo.enqueue(
                    operation="bad op",
                    entity_id=str(uuid4()),
                    payload=_payload(),
                )
            with pytest.raises(GraphOutboxRepositoryError, match="entity_id"):
                await repo.enqueue(
                    operation="upsert_job",
                    entity_id="../etc/passwd",
                    payload=_payload(),
                )


@pytest.mark.asyncio
async def test_claim_excludes_synced_and_failed(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as db:
        async with db.session_scope() as session:
            repo = GraphOutboxRepository(session)
            pending_id = str(uuid4())
            failed_id = str(uuid4())
            synced_id = str(uuid4())
            pending = await repo.enqueue(
                operation="upsert_job",
                entity_id=pending_id,
                payload=_payload(pending_id),
            )
            failed = await repo.enqueue(
                operation="upsert_job",
                entity_id=failed_id,
                payload=_payload(failed_id),
            )
            synced = await repo.enqueue(
                operation="upsert_job",
                entity_id=synced_id,
                payload=_payload(synced_id),
            )
            await repo.mark_failed(failed.id, error="neo4j_unavailable")
            await repo.mark_synced(synced.id)

            claimed = await repo.claim_pending(limit=10)
            assert [r.id for r in claimed] == [pending.id]


@pytest.mark.asyncio
async def test_no_worker_timer_or_poll_surface() -> None:
    """Repository module must not expose worker/timer/polling hooks."""
    import app.repositories.graph_outbox as mod

    banned = (
        "poll",
        "worker",
        "timer",
        "background",
        "loop",
        "schedule",
        "start_worker",
        "run_forever",
    )
    public = [name for name in dir(mod) if not name.startswith("_")]
    for name in public:
        lower = name.lower()
        assert not any(token in lower for token in banned)

    repo_methods = [
        name for name in dir(GraphOutboxRepository) if not name.startswith("_")
    ]
    for name in repo_methods:
        lower = name.lower()
        assert not any(token in lower for token in banned)

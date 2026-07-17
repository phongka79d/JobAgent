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
            # Programmatic completeness: none of the 63/8 expected missing.
            assert len(expected_named_constraints()) == 63
            assert len(expected_indexes()) == 8
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
                f"INSERT INTO conversation (id, created_at, updated_at) "
                f"VALUES ('other', '{TS}', '{TS}')",
            )
            await _fail(f, _att("a1", "h1", "p1", mime="text/plain"))
            async with f() as s:
                await _x(s, _att("act1", "h1", "p1", st="active", pages=1))
                await s.commit()
            await _fail(f, _att("act2", "h2", "p2", st="active", pages=1))
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
                await _x(
                    s,
                    "INSERT INTO candidate_profile "
                    "(id, active_attachment_id, profile_json, "
                    f"created_at, updated_at) VALUES "
                    f"('active', 'att-r', '{{}}', '{TS}', '{TS}')",
                )
                await s.commit()
            await _fail(f, "DELETE FROM attachments WHERE id = 'att-r'")
            async with f() as s:
                await _x(s, _att("att-d", "hd", "pd"))
                for sql in (
                    "INSERT INTO profile_drafts "
                    "(id, source_attachment_id, draft_json, created_at, updated_at) "
                    f"VALUES ('current', 'att-d', '{{}}', '{TS}', '{TS}')",
                    "INSERT INTO chat_messages "
                    "(id, conversation_id, role, content, created_at, updated_at) "
                    f"VALUES ('msg1', 'main', 'user', 'hello', '{TS}', '{TS}')",
                    "INSERT INTO agent_runs "
                    "(id, user_message_id, state, created_at, updated_at) "
                    f"VALUES ('run1', 'msg1', 'running', '{TS}', '{TS}')",
                    "INSERT INTO tool_executions "
                    "(id, run_id, tool_call_id, tool_name, status, "
                    "created_at, updated_at) VALUES "
                    f"('tool1', 'run1', 'tc1', 'demo', 'pending', '{TS}', '{TS}')",
                ):
                    await _x(s, sql)
                await s.commit()
            async with f() as s:
                await _x(s, "DELETE FROM attachments WHERE id = 'att-d'")
                await s.commit()
                assert await _cnt(s, "profile_drafts") == 0
            async with f() as s:
                await _x(s, "DELETE FROM conversation WHERE id = 'main'")
                await s.commit()
                assert await _cnt(s, "chat_messages") == 0
                assert await _cnt(s, "agent_runs") == 0
                assert await _cnt(s, "tool_executions") == 0
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
                    f"('msg-own', 'main', 'user', 'cv note', 'att-own', "
                    f"'{TS}', '{TS}')",
                    "INSERT INTO chat_messages ("
                    "id, conversation_id, role, content, "
                    f"created_at, updated_at) VALUES "
                    f"('msg-plain', 'main', 'user', 'plain', '{TS}', '{TS}')",
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


def test_seeded_preferences_json_shape(db_path: Path) -> None:
    async def _c() -> None:
        e = build_async_engine(db_path)
        try:
            async with e.connect() as c:
                raw = (
                    await c.execute(
                        text("SELECT preferences_json FROM job_preferences")
                    )
                ).scalar_one()
                n = (
                    await c.execute(
                        text("SELECT COUNT(*) FROM candidate_profile")
                    )
                ).scalar_one()
            prefs = json.loads(raw) if isinstance(raw, str) else raw
            assert set(prefs) == {
                "target_roles",
                "preferred_locations",
                "acceptable_work_modes",
                "target_seniority",
            }
            assert all(prefs[k] == [] for k in prefs)
            assert int(n) == 0
        finally:
            await e.dispose()

    run_async(_c())

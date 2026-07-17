"""Alembic upgrade/idempotency tests on isolated temporary SQLite files."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.db.models.chat import CONVERSATION_ID
from app.db.models.profiles import JOB_PREFERENCE_KEYS, JOB_PREFERENCES_ID
from app.db.seed import APPLICATION_TABLE_NAMES, ensure_singleton_seeds
from app.db.session import (
    build_async_engine,
    get_session_factory,
    session_scope,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.support.db_migration import (
    BACKEND_ROOT,
    EXPECTED_FRESH_TABLES,
    MIGRATION_HEAD,
    alembic_config,
    assert_migrated_matches_accepted_models,
    run_async,
    upgrade_to_head,
)


def _current(db: Path) -> str:
    cfg = alembic_config(db)
    assert ScriptDirectory.from_config(cfg).get_heads() == [MIGRATION_HEAD]

    async def _read() -> str:
        e = build_async_engine(db)
        try:
            async with e.connect() as c:

                def _rev(sc: object) -> str | None:
                    return MigrationContext.configure(sc).get_current_revision()  # type: ignore[arg-type]

                return (await c.run_sync(_rev)) or ""
        finally:
            await e.dispose()

    return run_async(_read())


async def _names(e: AsyncEngine) -> set[str]:
    async with e.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )
        ).fetchall()
    return {str(r[0]) for r in rows}


async def _counts(e: AsyncEngine) -> dict[str, int]:
    out: dict[str, int] = {}
    async with e.connect() as c:
        for name in (
            "conversation",
            "job_preferences",
            "candidate_profile",
            "profile_drafts",
        ):
            out[name] = int(
                (
                    await c.execute(text(f"SELECT COUNT(*) FROM {name}"))
                ).scalar_one()
            )
    return out


def test_fresh_upgrade_creates_twelve_tables_and_singleton_seeds(
    isolated_sqlite: Path,
) -> None:
    db = isolated_sqlite
    upgrade_to_head(db)
    assert _current(db) == MIGRATION_HEAD

    async def _c() -> None:
        e = build_async_engine(db)
        try:
            names = await _names(e)
            assert names == set(EXPECTED_FRESH_TABLES)
            assert APPLICATION_TABLE_NAMES <= names
            assert "attachment_text_chunks" in names
            assert "cv_documents" in names
            assert "cv_document_drafts" in names
            counts = await _counts(e)
            assert counts["conversation"] == 1
            assert counts["job_preferences"] == 1
            assert counts["candidate_profile"] == 0
            assert counts["profile_drafts"] == 0
            async with e.connect() as c:
                assert (
                    await c.execute(text("SELECT id FROM conversation"))
                ).scalar_one() == CONVERSATION_ID
                row = (
                    await c.execute(
                        text(
                            "SELECT id, preferences_json FROM job_preferences"
                        )
                    )
                ).one()
                def _parity(sc: object) -> None:
                    assert_migrated_matches_accepted_models(
                        sc,  # type: ignore[arg-type]
                        exact_tables=EXPECTED_FRESH_TABLES,
                    )

                await c.run_sync(_parity)
                # deleting accepted by CHECK; existing staged/archived untouched.
                await c.execute(
                    text(
                        "INSERT INTO attachments ("
                        "id, file_hash, original_name, mime_type, size_bytes, "
                        "page_count, storage_path, state, failure_code, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-arch', 'h-arch', 'a.pdf', 'application/pdf', 10, "
                        "1, 'p/a.pdf', 'archived', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO attachments ("
                        "id, file_hash, original_name, mime_type, size_bytes, "
                        "page_count, storage_path, state, failure_code, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-staged', 'h-staged', 's.pdf', 'application/pdf', "
                        "10, NULL, 'p/s.pdf', 'staged', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO attachments ("
                        "id, file_hash, original_name, mime_type, size_bytes, "
                        "page_count, storage_path, state, failure_code, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-del', 'h-del', 'd.pdf', 'application/pdf', 10, "
                        "1, 'p/d.pdf', 'deleting', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.commit()
                states = {
                    str(r[0]): str(r[1])
                    for r in (
                        await c.execute(
                            text("SELECT id, state FROM attachments")
                        )
                    ).fetchall()
                }
                assert states["a-arch"] == "archived"
                assert states["a-staged"] == "staged"
                assert states["a-del"] == "deleting"
                # chunk row with FK + ordinal unique
                await c.execute(
                    text(
                        "INSERT INTO attachment_text_chunks ("
                        "id, attachment_id, ordinal, text, preview, "
                        "char_count, token_estimate, created_at"
                        ") VALUES ("
                        "'c1', 'a-arch', 0, 'hello chunk', 'hello chunk', "
                        "11, 3, CURRENT_TIMESTAMP)"
                    )
                )
                await c.commit()
                n_chunks = (
                    await c.execute(
                        text("SELECT COUNT(*) FROM attachment_text_chunks")
                    )
                ).scalar_one()
                assert int(n_chunks) == 1
                n_docs = (
                    await c.execute(text("SELECT COUNT(*) FROM cv_documents"))
                ).scalar_one()
                n_drafts = (
                    await c.execute(
                        text("SELECT COUNT(*) FROM cv_document_drafts")
                    )
                ).scalar_one()
                assert int(n_docs) == 0 and int(n_drafts) == 0
            assert row[0] == JOB_PREFERENCES_ID
            prefs = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            assert set(prefs) == set(JOB_PREFERENCE_KEYS)
            assert all(prefs[k] == [] for k in JOB_PREFERENCE_KEYS)
        finally:
            await e.dispose()

    run_async(_c())


def test_upgrade_at_head_is_noop_and_does_not_duplicate_seeds(
    isolated_sqlite: Path,
) -> None:
    db = isolated_sqlite
    upgrade_to_head(db)
    upgrade_to_head(db)
    assert _current(db) == MIGRATION_HEAD

    async def _c() -> None:
        e = build_async_engine(db)
        try:
            counts = await _counts(e)
            assert counts["conversation"] == 1
            assert counts["job_preferences"] == 1
            assert counts["candidate_profile"] == 0
            names = await _names(e)
            assert names == set(EXPECTED_FRESH_TABLES)
        finally:
            await e.dispose()

    run_async(_c())


def test_upgrade_preserves_unrelated_checkpoint_like_tables(
    isolated_sqlite: Path,
) -> None:
    db = isolated_sqlite

    async def _plant() -> None:
        e = build_async_engine(db)
        try:
            async with e.begin() as c:
                await c.execute(
                    text(
                        "CREATE TABLE checkpoints ("
                        "id TEXT PRIMARY KEY NOT NULL, payload TEXT NOT NULL)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO checkpoints (id, payload) "
                        "VALUES ('cp1', 'keep-me')"
                    )
                )
                await c.execute(
                    text(
                        "CREATE TABLE langgraph_writes ("
                        "id TEXT PRIMARY KEY NOT NULL)"
                    )
                )
        finally:
            await e.dispose()

    run_async(_plant())
    upgrade_to_head(db)

    async def _c() -> None:
        e = build_async_engine(db)
        try:
            names = await _names(e)
            assert {"checkpoints", "langgraph_writes"}.issubset(names)
            assert APPLICATION_TABLE_NAMES.issubset(names)
            assert "alembic_version" in names
            async with e.connect() as c:
                payload = (
                    await c.execute(
                        text(
                            "SELECT payload FROM checkpoints WHERE id = 'cp1'"
                        )
                    )
                ).scalar_one()

                def _parity(sc: object) -> None:
                    # Checkpoint tables may coexist; still require model parity.
                    assert_migrated_matches_accepted_models(sc)  # type: ignore[arg-type]

                await c.run_sync(_parity)
            assert payload == "keep-me"
        finally:
            await e.dispose()

    run_async(_c())


def test_startup_singleton_safeguard_is_idempotent(
    isolated_sqlite: Path,
) -> None:
    db = isolated_sqlite
    upgrade_to_head(db)

    async def _c() -> None:
        async with session_scope() as s:
            await ensure_singleton_seeds(s)
        async with session_scope() as s:
            await ensure_singleton_seeds(s)
        factory = get_session_factory()
        async with factory() as s:
            conv = int(
                (
                    await s.execute(text("SELECT COUNT(*) FROM conversation"))
                ).scalar_one()
            )
            prefs = int(
                (
                    await s.execute(
                        text("SELECT COUNT(*) FROM job_preferences")
                    )
                ).scalar_one()
            )
            profile = int(
                (
                    await s.execute(
                        text("SELECT COUNT(*) FROM candidate_profile")
                    )
                ).scalar_one()
            )
        assert (conv, prefs, profile) == (1, 1, 0)

    run_async(_c())


def test_upgrade_from_0002_preserves_rows_without_document_synthesis(
    isolated_sqlite: Path,
) -> None:
    """Existing 0002 data survives 0003; no CVDocument rows invented."""
    db = isolated_sqlite
    command.upgrade(alembic_config(db), "0002_add_attachment_text_chunks")

    async def _plant() -> None:
        e = build_async_engine(db)
        try:
            async with e.begin() as c:
                await c.execute(
                    text(
                        "INSERT INTO attachments ("
                        "id, file_hash, original_name, mime_type, size_bytes, "
                        "page_count, storage_path, state, failure_code, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-active', 'h-active', 'cv.pdf', 'application/pdf', "
                        "20, 2, 'p/active.pdf', 'active', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO attachments ("
                        "id, file_hash, original_name, mime_type, size_bytes, "
                        "page_count, storage_path, state, failure_code, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-arch', 'h-arch', 'old.pdf', 'application/pdf', "
                        "10, 1, 'p/arch.pdf', 'archived', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO attachment_text_chunks ("
                        "id, attachment_id, ordinal, text, preview, "
                        "char_count, token_estimate, created_at"
                        ") VALUES ("
                        "'chunk-1', 'a-active', 0, 'legacy body', "
                        "'legacy body', 11, 3, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO candidate_profile ("
                        "id, active_attachment_id, profile_json, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'active', 'a-active', '{\"skills\":[]}', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO chat_messages ("
                        "id, conversation_id, role, content, "
                        "structured_payload, created_at, updated_at"
                        ") VALUES ("
                        "'msg-1', 'main', 'user', 'extract this', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO agent_runs ("
                        "id, user_message_id, state, pending_approval_json, "
                        "error_code, completed_at, created_at, updated_at"
                        ") VALUES ("
                        "'run-1', 'msg-1', 'completed', NULL, NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                        "CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO tool_executions ("
                        "id, run_id, tool_call_id, tool_name, "
                        "arguments_summary_json, status, duration_ms, "
                        "error_code, result_json, created_at, updated_at"
                        ") VALUES ("
                        "'tool-1', 'run-1', 'tc-1', 'extract_profile', NULL, "
                        "'completed', 5, NULL, "
                        ":result_json, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "result_json": json.dumps(
                            {
                                "ok": True,
                                "code": None,
                                "message": None,
                                "data": {},
                            }
                        )
                    },
                )
                await c.execute(
                    text(
                        "CREATE TABLE checkpoints ("
                        "id TEXT PRIMARY KEY NOT NULL, payload TEXT NOT NULL)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO checkpoints (id, payload) "
                        "VALUES ('cp-legacy', 'checkpoint-keep')"
                    )
                )
        finally:
            await e.dispose()

    run_async(_plant())
    upgrade_to_head(db)
    assert _current(db) == MIGRATION_HEAD

    async def _c() -> None:
        e = build_async_engine(db)
        try:
            async with e.connect() as c:
                att_states = {
                    str(r[0]): str(r[1])
                    for r in (
                        await c.execute(
                            text("SELECT id, state FROM attachments")
                        )
                    ).fetchall()
                }
                assert att_states == {
                    "a-active": "active",
                    "a-arch": "archived",
                }
                chunk = (
                    await c.execute(
                        text(
                            "SELECT attachment_id, text "
                            "FROM attachment_text_chunks"
                        )
                    )
                ).one()
                assert chunk == ("a-active", "legacy body")
                profile = (
                    await c.execute(
                        text(
                            "SELECT active_attachment_id FROM candidate_profile"
                        )
                    )
                ).scalar_one()
                assert profile == "a-active"
                msg = (
                    await c.execute(
                        text(
                            "SELECT content, source_attachment_id, redacted_at "
                            "FROM chat_messages WHERE id = 'msg-1'"
                        )
                    )
                ).one()
                assert msg[0] == "extract this"
                assert msg[1] is None
                assert msg[2] is None
                run_src = (
                    await c.execute(
                        text(
                            "SELECT source_attachment_id FROM agent_runs "
                            "WHERE id = 'run-1'"
                        )
                    )
                ).scalar_one()
                assert run_src is None
                tool_src = (
                    await c.execute(
                        text(
                            "SELECT source_attachment_id FROM tool_executions "
                            "WHERE id = 'tool-1'"
                        )
                    )
                ).scalar_one()
                assert tool_src is None
                assert (
                    int(
                        (
                            await c.execute(
                                text("SELECT COUNT(*) FROM cv_documents")
                            )
                        ).scalar_one()
                    )
                    == 0
                )
                assert (
                    int(
                        (
                            await c.execute(
                                text("SELECT COUNT(*) FROM cv_document_drafts")
                            )
                        ).scalar_one()
                    )
                    == 0
                )
                payload = (
                    await c.execute(
                        text(
                            "SELECT payload FROM checkpoints "
                            "WHERE id = 'cp-legacy'"
                        )
                    )
                ).scalar_one()
                assert payload == "checkpoint-keep"

                def _parity(sc: object) -> None:
                    assert_migrated_matches_accepted_models(sc)  # type: ignore[arg-type]

                await c.run_sync(_parity)

                # Chunk FK is CASCADE after upgrade.
                fk_rows = (
                    await c.execute(
                        text("PRAGMA foreign_key_list('attachment_text_chunks')")
                    )
                ).fetchall()
                assert any(
                    str(r[3]) == "attachment_id"
                    and str(r[6] or "").upper() == "CASCADE"
                    for r in fk_rows
                )
        finally:
            await e.dispose()

    run_async(_c())


def test_migration_0003_has_no_external_call_imports() -> None:
    """0003 must not import provider, filesystem, or Neo4j modules."""
    path = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "0003_add_cv_documents_and_ownership.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "app.services",
        "app.integrations",
        "app.graph",
        "neo4j",
        "httpx",
        "openai",
        "pathlib",
        "os",
        "shutil",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert alias.name not in forbidden_roots
                banned_roots = {
                    "neo4j", "httpx", "openai", "pathlib", "os", "shutil",
                }
                assert root not in banned_roots
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            assert not any(
                mod == f or mod.startswith(f + ".") for f in forbidden_roots
            )
    src = path.read_text(encoding="utf-8")
    assert "cv_documents" in src
    assert "INSERT INTO cv_documents" not in src
    assert "INSERT INTO cv_document_drafts" not in src

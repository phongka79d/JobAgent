"""Alembic upgrade/idempotency tests on isolated temporary SQLite files."""

from __future__ import annotations

import ast
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from app.db.models.profiles import WORKSPACE_STATE_ID
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


def _sqlite_snapshot(db: Path) -> dict[str, Any]:
    """Capture schema metadata, migration revision, and ownership rows exactly."""
    with sqlite3.connect(db) as connection:
        master = tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'index', 'trigger') "
                "ORDER BY type, name"
            )
        )
        tables = (
            "profile_drafts",
            "profile_reextract_operations",
            "profiles",
            "attachments",
            "workspace_state",
        )
        metadata: dict[str, object] = {}
        rows: dict[str, tuple[tuple[object, ...], ...]] = {}
        for table in tables:
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if exists is None:
                continue
            indexes = []
            for index in connection.execute(f"PRAGMA index_list('{table}')"):
                index_name = str(index[1])
                indexes.append(
                    (
                        tuple(index),
                        tuple(
                            tuple(row)
                            for row in connection.execute(
                                f"PRAGMA index_info('{index_name}')"
                            )
                        ),
                    )
                )
            metadata[table] = {
                "table_info": tuple(
                    tuple(row)
                    for row in connection.execute(f"PRAGMA table_info('{table}')")
                ),
                "foreign_key_list": tuple(
                    sorted(
                        (
                            str(row[2]),
                            str(row[3]),
                            str(row[4]),
                            str(row[5]),
                            str(row[6]),
                            str(row[7]),
                        )
                        for row in connection.execute(
                            f"PRAGMA foreign_key_list('{table}')"
                        )
                    )
                ),
                "index_list": tuple(indexes),
            }
            rows[table] = tuple(
                tuple(row)
                for row in connection.execute(f"SELECT * FROM '{table}' ORDER BY 1")
            )
        return {
            "master": master,
            "metadata": metadata,
            "rows": rows,
            "alembic_version": tuple(
                tuple(row)
                for row in connection.execute("SELECT * FROM alembic_version")
            ),
            "foreign_key_check": tuple(
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
            ),
        }


def _seed_valid_profile_draft(db: Path) -> dict[str, object]:
    """Plant a 0007 draft with values that migration 0008 must retain exactly."""
    command.upgrade(alembic_config(db), "0007_add_cv_tailoring")
    payload = {"summary": "Keep exact JSON", "skills": ["Python", "SQL"]}
    now = "2026-07-31 00:00:00+00:00"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO attachments "
            "(id, file_hash, original_name, mime_type, size_bytes, page_count, "
            "storage_path, state, failure_code, created_at, updated_at) VALUES "
            "('attachment-0008', 'hash-0008', 'cv.pdf', 'application/pdf', 10, "
            "1, 'cv.pdf', 'archived', NULL, ?, ?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO profiles "
            "(id, attachment_id, display_name, profile_json, location, "
            "extraction_version, source_hash, state, created_at, updated_at, "
            "last_opened_at) VALUES ('profile-0008', 'attachment-0008', "
            "'Profile', '{}', NULL, 'v1', 'source-0008', 'ready', ?, ?, ?)",
            (now, now, now),
        )
        connection.execute(
            "INSERT INTO profile_drafts "
            "(id, source_attachment_id, target_profile_id, draft_json, created_at, "
            "updated_at) VALUES ('draft-0008', 'attachment-0008', 'profile-0008', "
            "?, ?, ?)",
            (json.dumps(payload, separators=(",", ":")), now, now),
        )
    return payload


def _insert_draft(
    db: Path,
    *,
    draft_id: str,
    target_profile_id: str | None,
    source_attachment_id: str | None,
) -> None:
    now = "2026-07-31 00:00:00+00:00"
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO profile_drafts "
            "(id, source_attachment_id, target_profile_id, draft_json, created_at, "
            "updated_at) VALUES (?, ?, ?, '{}', ?, ?)",
            (draft_id, source_attachment_id, target_profile_id, now, now),
        )


def test_0008_rejects_null_draft_target_before_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    command.upgrade(alembic_config(isolated_sqlite), "0007_add_cv_tailoring")
    _insert_draft(
        isolated_sqlite,
        draft_id="draft-null-target",
        target_profile_id=None,
        source_attachment_id=None,
    )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_drafts.target_profile_id"):
        command.upgrade(
            alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
        )
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_rejects_orphan_draft_target_before_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    command.upgrade(alembic_config(isolated_sqlite), "0007_add_cv_tailoring")
    with sqlite3.connect(isolated_sqlite) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
    _insert_draft(
        isolated_sqlite,
        draft_id="draft-orphan-target",
        target_profile_id="missing-profile",
        source_attachment_id=None,
    )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_drafts.target_profile_id"):
        command.upgrade(
            alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
        )
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_rejects_duplicate_draft_targets_before_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    _seed_valid_profile_draft(isolated_sqlite)
    _insert_draft(
        isolated_sqlite,
        draft_id="draft-duplicate-target",
        target_profile_id="profile-0008",
        source_attachment_id=None,
    )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_drafts.target_profile_id"):
        command.upgrade(
            alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
        )
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_rejects_orphan_draft_source_before_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    _seed_valid_profile_draft(isolated_sqlite)
    with sqlite3.connect(isolated_sqlite) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "UPDATE profile_drafts SET source_attachment_id = 'missing-attachment' "
            "WHERE id = 'draft-0008'"
        )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_drafts.source_attachment_id"):
        command.upgrade(
            alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
        )
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_rejects_foreign_key_check_before_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    command.upgrade(alembic_config(isolated_sqlite), "0007_add_cv_tailoring")
    with sqlite3.connect(isolated_sqlite) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "UPDATE workspace_state SET active_profile_id = 'missing-profile' "
            "WHERE id = 'main'"
        )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="foreign_key_check"):
        command.upgrade(
            alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
        )
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_preserves_valid_draft_schema_rows_and_json(
    isolated_sqlite: Path,
) -> None:
    payload = _seed_valid_profile_draft(isolated_sqlite)
    before = _sqlite_snapshot(isolated_sqlite)
    command.upgrade(
        alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
    )
    after = _sqlite_snapshot(isolated_sqlite)
    with sqlite3.connect(isolated_sqlite) as connection:
        row = connection.execute(
            "SELECT id, source_attachment_id, target_profile_id, draft_json, "
            "created_at, updated_at, reextract_operation_id FROM profile_drafts"
        ).fetchone()
        assert row is not None
        assert row == (
            "draft-0008",
            "attachment-0008",
            "profile-0008",
            json.dumps(payload, separators=(",", ":")),
            "2026-07-31 00:00:00+00:00",
            "2026-07-31 00:00:00+00:00",
            None,
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before_draft = before["metadata"]["profile_drafts"]
    after_draft = after["metadata"]["profile_drafts"]
    assert [row[1] for row in before_draft["table_info"]] == [
        "id",
        "source_attachment_id",
        "target_profile_id",
        "draft_json",
        "created_at",
        "updated_at",
    ]
    assert [row[1] for row in after_draft["table_info"]] == [
        "id",
        "source_attachment_id",
        "target_profile_id",
        "draft_json",
        "created_at",
        "updated_at",
        "reextract_operation_id",
    ]
    assert before["rows"]["attachments"] == after["rows"]["attachments"]
    assert before["rows"]["profiles"] == after["rows"]["profiles"]
    assert not [
        row
        for row in after["master"]
        if row[0] == "trigger" and row[2] == "profile_drafts"
    ]


def test_0008_downgrade_refuses_populated_operation_without_mutation(
    isolated_sqlite: Path,
) -> None:
    _seed_valid_profile_draft(isolated_sqlite)
    command.upgrade(
        alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
    )
    now = "2026-07-31 00:00:00+00:00"
    with sqlite3.connect(isolated_sqlite) as connection:
        connection.execute(
            "INSERT INTO profile_reextract_operations "
            "(id, profile_id, source_attachment_id, base_profile_updated_at, "
            "base_workspace_updated_at, state, error_code, created_at, updated_at) "
            "VALUES ('operation-0008', 'profile-0008', 'attachment-0008', ?, ?, "
            "'running', NULL, ?, ?)",
            (now, now, now, now),
        )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_reextract_operations"):
        command.downgrade(alembic_config(isolated_sqlite), "0007_add_cv_tailoring")
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_downgrade_refuses_linked_draft_without_schema_or_data_mutation(
    isolated_sqlite: Path,
) -> None:
    _seed_valid_profile_draft(isolated_sqlite)
    command.upgrade(
        alembic_config(isolated_sqlite), "0008_profile_reextract_ownership"
    )
    with sqlite3.connect(isolated_sqlite) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "UPDATE profile_drafts SET reextract_operation_id = 'missing-operation' "
            "WHERE id = 'draft-0008'"
        )
    before = _sqlite_snapshot(isolated_sqlite)
    with pytest.raises(CommandError, match="profile_drafts references an operation"):
        command.downgrade(alembic_config(isolated_sqlite), "0007_add_cv_tailoring")
    assert _sqlite_snapshot(isolated_sqlite) == before


def test_0008_empty_operation_downgrade_and_reupgrade_preserves_ordinary_draft(
    isolated_sqlite: Path,
) -> None:
    payload = _seed_valid_profile_draft(isolated_sqlite)
    cfg = alembic_config(isolated_sqlite)
    before = _sqlite_snapshot(isolated_sqlite)
    command.upgrade(cfg, "0008_profile_reextract_ownership")
    upgraded = _sqlite_snapshot(isolated_sqlite)
    command.downgrade(cfg, "0007_add_cv_tailoring")
    downgraded = _sqlite_snapshot(isolated_sqlite)
    command.upgrade(cfg, "0008_profile_reextract_ownership")
    reupgraded = _sqlite_snapshot(isolated_sqlite)
    with sqlite3.connect(isolated_sqlite) as connection:
        draft_json_row = connection.execute(
            "SELECT draft_json FROM profile_drafts WHERE id = 'draft-0008'"
        ).fetchone()
        assert draft_json_row is not None
        draft_json = draft_json_row[0]
        assert draft_json == json.dumps(payload, separators=(",", ":"))
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert before["metadata"]["profile_drafts"] == downgraded["metadata"][
        "profile_drafts"
    ]
    assert upgraded["metadata"]["profile_drafts"] == reupgraded["metadata"][
        "profile_drafts"
    ]
    assert before["rows"]["attachments"] == reupgraded["rows"]["attachments"]
    assert before["rows"]["profiles"] == reupgraded["rows"]["profiles"]


def test_0008_is_the_migration_head() -> None:
    assert MIGRATION_HEAD == "0008_profile_reextract_ownership"
    assert ScriptDirectory.from_config(
        alembic_config(Path(":memory:"))
    ).get_heads() == ["0008_profile_reextract_ownership"]


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
            "workspace_state",
            "profiles",
            "profile_preferences",
            "conversations",
            "profile_drafts",
        ):
            out[name] = int(
                (
                    await c.execute(text(f"SELECT COUNT(*) FROM {name}"))
                ).scalar_one()
            )
    return out


def test_fresh_upgrade_creates_application_tables_and_workspace_seed(
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
            assert "job_evaluations" in names
            counts = await _counts(e)
            assert counts["workspace_state"] == 1
            assert counts["profiles"] == 0
            assert counts["profile_preferences"] == 0
            assert counts["conversations"] == 0
            assert counts["profile_drafts"] == 0
            async with e.connect() as c:
                row = (
                    await c.execute(
                        text(
                            "SELECT id, active_profile_id FROM workspace_state"
                        )
                    )
                ).one()
                n_evals = (
                    await c.execute(
                        text("SELECT COUNT(*) FROM job_evaluations")
                    )
                ).scalar_one()
                assert int(n_evals) == 0

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
            assert row == (WORKSPACE_STATE_ID, None)
        finally:
            await e.dispose()

    run_async(_c())


def test_migration_head_adds_tailoring_and_preserves_agent_activity_projection(
    isolated_sqlite: Path,
) -> None:
    command.upgrade(alembic_config(isolated_sqlite), "head")

    async def _body() -> None:
        engine = build_async_engine(isolated_sqlite)
        try:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text("PRAGMA foreign_key_list('agent_activities')")
                    )
                ).fetchall()
                assert any(
                    str(row[2]) == "agent_runs"
                    and str(row[3]) == "run_id"
                    and str(row[6] or "").upper() == "CASCADE"
                    for row in rows
                )
                version = (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar_one()
                assert version == "0008_profile_reextract_ownership"
                tables = await _names(engine)
                assert "cv_tailoring_sessions" in tables
                assert "cv_tailoring_versions" in tables
                run_columns = {
                    str(row[1])
                    for row in (
                        await connection.execute(
                            text("PRAGMA table_info('agent_runs')")
                        )
                    ).fetchall()
                }
                assert {
                    "run_kind",
                    "tailoring_session_id",
                    "parent_run_id",
                } <= run_columns
        finally:
            await engine.dispose()

    run_async(_body())


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
            assert counts["workspace_state"] == 1
            assert counts["profiles"] == 0
            assert counts["profile_preferences"] == 0
            assert counts["conversations"] == 0
            names = await _names(e)
            assert names == set(EXPECTED_FRESH_TABLES)
        finally:
            await e.dispose()

    run_async(_c())


def test_tailoring_migration_downgrades_and_reupgrades_on_disposable_db(
    isolated_sqlite: Path,
) -> None:
    cfg = alembic_config(isolated_sqlite)
    command.upgrade(cfg, "0006_add_agent_activities")

    async def _plant_chat_history() -> None:
        engine = build_async_engine(isolated_sqlite)
        try:
            async with engine.begin() as connection:
                statements = (
                    "INSERT INTO attachments "
                    "(id, file_hash, original_name, mime_type, size_bytes, "
                    "page_count, storage_path, state, failure_code, created_at, "
                    "updated_at) VALUES ('att-7', 'hash-7', 'cv.pdf', "
                    "'application/pdf', 10, 1, 'att-7.pdf', 'archived', NULL, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    "INSERT INTO profiles "
                    "(id, attachment_id, display_name, profile_json, location, "
                    "extraction_version, source_hash, state, created_at, updated_at, "
                    "last_opened_at) VALUES ('profile-7', 'att-7', 'Synthetic', '{}', "
                    "NULL, 'cv-document-v1', 'source-7', 'ready', CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    "INSERT INTO conversations "
                    "(id, profile_id, title, created_at, updated_at, last_opened_at) "
                    "VALUES ('conversation-7', 'profile-7', 'Synthetic', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    "INSERT INTO chat_messages "
                    "(id, conversation_id, role, content, structured_payload, "
                    "source_attachment_id, redacted_at, created_at, updated_at) "
                    "VALUES ('message-7', 'conversation-7', 'user', 'Synthetic', "
                    "NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    "INSERT INTO agent_runs "
                    "(id, user_message_id, source_attachment_id, state, "
                    "pending_approval_json, error_code, completed_at, created_at, "
                    "updated_at) VALUES ('run-7', 'message-7', NULL, 'completed', "
                    "NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP)",
                    "INSERT INTO agent_activities "
                    "(id, run_id, sequence, kind, label, technical_name, status, "
                    "duration_ms, error_code, started_at, updated_at, completed_at) "
                    "VALUES ('activity-7', 'run-7', 0, 'assistant', 'Synthetic', "
                    "NULL, 'completed', 1, NULL, CURRENT_TIMESTAMP, "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    "INSERT INTO tool_executions "
                    "(id, run_id, source_attachment_id, tool_call_id, tool_name, "
                    "arguments_summary_json, status, duration_ms, error_code, "
                    "result_json, created_at, updated_at) VALUES "
                    "('tool-7', 'run-7', NULL, 'call-7', 'synthetic_tool', NULL, "
                    "'completed', 1, NULL, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                )
                for statement in statements:
                    await connection.execute(text(statement))
        finally:
            await engine.dispose()

    run_async(_plant_chat_history())
    command.upgrade(cfg, "head")

    async def _assert_chat_history(*, at_head: bool) -> None:
        engine = build_async_engine(isolated_sqlite)
        try:
            async with engine.connect() as connection:
                run = (
                    await connection.execute(
                        text(
                            "SELECT user_message_id, state"
                            + (", run_kind" if at_head else "")
                            + " FROM agent_runs WHERE id = 'run-7'"
                        )
                    )
                ).one()
                assert tuple(run[:2]) == ("message-7", "completed")
                if at_head:
                    assert run[2] == "chat"
                assert int(
                    (
                        await connection.execute(
                            text(
                                "SELECT COUNT(*) FROM agent_activities "
                                "WHERE run_id = 'run-7'"
                            )
                        )
                    ).scalar_one()
                ) == 1
                assert int(
                    (
                        await connection.execute(
                            text(
                                "SELECT COUNT(*) FROM tool_executions "
                                "WHERE run_id = 'run-7'"
                            )
                        )
                    ).scalar_one()
                ) == 1
        finally:
            await engine.dispose()

    run_async(_assert_chat_history(at_head=True))
    command.downgrade(cfg, "0006_add_agent_activities")

    async def _assert_0006() -> None:
        engine = build_async_engine(isolated_sqlite)
        try:
            assert "cv_tailoring_sessions" not in await _names(engine)
            async with engine.connect() as connection:
                columns = {
                    str(row[1])
                    for row in (
                        await connection.execute(
                            text("PRAGMA table_info('agent_runs')")
                        )
                    ).fetchall()
                }
                assert "run_kind" not in columns
                assert "tailoring_session_id" not in columns
                assert "parent_run_id" not in columns
        finally:
            await engine.dispose()

    run_async(_assert_0006())
    run_async(_assert_chat_history(at_head=False))
    command.upgrade(cfg, "head")
    assert _current(isolated_sqlite) == MIGRATION_HEAD
    run_async(_assert_chat_history(at_head=True))


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


def test_startup_workspace_safeguard_is_idempotent(
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
            workspace = int(
                (
                    await s.execute(text("SELECT COUNT(*) FROM workspace_state"))
                ).scalar_one()
            )
            prefs = int(
                (
                    await s.execute(
                        text("SELECT COUNT(*) FROM profile_preferences")
                    )
                ).scalar_one()
            )
            profile = int(
                (
                    await s.execute(
                        text("SELECT COUNT(*) FROM profiles")
                    )
                ).scalar_one()
            )
        assert (workspace, prefs, profile) == (1, 0, 0)

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
    with pytest.raises(RuntimeError, match="Reset.*SQLite"):
        upgrade_to_head(db)
    assert _current(db) == "0004_add_job_evaluations"

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


def _assert_migration_has_no_external_call_imports(path: Path) -> None:
    """Structural migrations must not import provider/filesystem/Neo4j owners."""
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


def test_migration_0003_has_no_external_call_imports() -> None:
    """0003 must not import provider, filesystem, or Neo4j modules."""
    path = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "0003_add_cv_documents_and_ownership.py"
    )
    _assert_migration_has_no_external_call_imports(path)
    src = path.read_text(encoding="utf-8")
    assert "cv_documents" in src
    assert "INSERT INTO cv_documents" not in src
    assert "INSERT INTO cv_document_drafts" not in src


def test_migration_0004_has_no_external_call_imports_or_backfill() -> None:
    """0004 is structural only: no provider/graph work and no evaluation rows."""
    path = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "0004_add_job_evaluations.py"
    )
    _assert_migration_has_no_external_call_imports(path)
    src = path.read_text(encoding="utf-8")
    assert "job_evaluations" in src
    assert "INSERT INTO job_evaluations" not in src
    assert "op.create_table" in src
    assert path.read_text(encoding="utf-8").count("create_table") == 1


def test_migration_0005_is_guarded_explicit_and_provider_free() -> None:
    path = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "0005_cv_profiles_multi_conversation.py"
    )
    _assert_migration_has_no_external_call_imports(path)
    src = path.read_text(encoding="utf-8")
    assert "op.get_bind()" in src
    assert "Reset the local SQLite database" in src
    assert "op.create_table" in src
    assert "Base.metadata" not in src
    assert "create_all" not in src
    assert 'op.drop_table("checkpoint' not in src
    assert 'op.drop_table("langgraph_' not in src
    assert "'pending'" in src
    assert "profile_json IS NULL" in src
    assert "uq_profiles__single_incomplete" in src


def test_upgrade_from_0003_preserves_rows_without_evaluation_synthesis(
    isolated_sqlite: Path,
) -> None:
    """Existing 0003 data survives 0004; no job_evaluations rows invented."""
    db = isolated_sqlite
    command.upgrade(alembic_config(db), "0003_add_cv_documents_and_ownership")

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
                        "INSERT INTO job_posts ("
                        "id, source_type, source_url, raw_content, "
                        "raw_content_hash, extraction_json, processing_status, "
                        "jd_quality, failure_code, embedding_json, "
                        "embedding_model, embedding_dimensions, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'job-1', 'text', NULL, 'Engineer role', 'hash-job-1', "
                        "NULL, 'received', NULL, NULL, NULL, NULL, NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO cv_documents ("
                        "attachment_id, document_json, profile_json, "
                        "outline_json, extraction_version, source_hash, "
                        "created_at, updated_at"
                        ") VALUES ("
                        "'a-active', '{}', '{}', '{}', 'v1', 'cv-hash-1', "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
                )
                await c.execute(
                    text(
                        "INSERT INTO chat_messages ("
                        "id, conversation_id, role, content, "
                        "structured_payload, created_at, updated_at"
                        ") VALUES ("
                        "'msg-1', 'main', 'user', 'keep me', NULL, "
                        "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                    )
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
                        "VALUES ('cp-0003', 'checkpoint-keep-0003')"
                    )
                )
        finally:
            await e.dispose()

    run_async(_plant())
    with pytest.raises(RuntimeError, match="Reset.*SQLite"):
        upgrade_to_head(db)
    assert _current(db) == "0004_add_job_evaluations"

    async def _c() -> None:
        e = build_async_engine(db)
        try:
            async with e.connect() as c:
                job = (
                    await c.execute(
                        text(
                            "SELECT raw_content FROM job_posts WHERE id='job-1'"
                        )
                    )
                ).scalar_one()
                assert job == "Engineer role"
                docs = (
                    await c.execute(
                        text("SELECT source_hash FROM cv_documents")
                    )
                ).scalar_one()
                assert docs == "cv-hash-1"
                msg = (
                    await c.execute(
                        text(
                            "SELECT content FROM chat_messages WHERE id='msg-1'"
                        )
                    )
                ).scalar_one()
                assert msg == "keep me"
                assert (
                    int(
                        (
                            await c.execute(
                                text("SELECT COUNT(*) FROM job_evaluations")
                            )
                        ).scalar_one()
                    )
                    == 0
                )
                payload = (
                    await c.execute(
                        text(
                            "SELECT payload FROM checkpoints "
                            "WHERE id = 'cp-0003'"
                        )
                    )
                ).scalar_one()
                assert payload == "checkpoint-keep-0003"

                fk_rows = (
                    await c.execute(
                        text("PRAGMA foreign_key_list('job_evaluations')")
                    )
                ).fetchall()
                assert any(
                    str(r[3]) == "job_id"
                    and str(r[2]) == "job_posts"
                    and str(r[6] or "").upper() == "CASCADE"
                    for r in fk_rows
                )
                assert any(
                    str(r[3]) == "active_attachment_id"
                    and str(r[2]) == "attachments"
                    and str(r[6] or "").upper() == "CASCADE"
                    for r in fk_rows
                )
        finally:
            await e.dispose()

    run_async(_c())

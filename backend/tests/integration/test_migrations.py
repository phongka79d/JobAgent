"""Integration tests for the Alembic migration lifecycle.

Proves:
- Fresh ``upgrade head`` materializes the eleven application tables.
- A second ``upgrade head`` on the same file is a no-op (no duplicate objects).
- Initialized Plan 2 schema upgrades additively to Plan 3 run idempotency.
- Initialized row data survives re-upgrade and additive revisions.
- Migrated schema agrees with SQLAlchemy model metadata (columns, FKs, uniques,
  indexes, check constraints).
- No LangGraph checkpoint tables are created.
- Tests inject ``SQLITE_PATH`` only and never load the user-owned root ``.env``.

Schema creation is owned by Alembic only — these tests do not call
``Base.metadata.create_all`` / ``drop_all`` as a substitute for migrations.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.db.base import Base
from app.db.models import APPLICATION_TABLE_NAMES
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, inspect
from sqlalchemy.engine import create_engine
from sqlalchemy.schema import Index

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
EXPECTED_TABLES = frozenset(APPLICATION_TABLE_NAMES)
PLAN2_HEAD = "c885a5846d85"
PLAN3_IDEMPOTENCY_HEAD = "d4e5f6a7b8c9"
EXPECTED_HEAD = PLAN3_IDEMPOTENCY_HEAD
LANGGRAPH_CHECKPOINT_MARKERS = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    }
)


def _alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # Ensure script location resolves relative to backend/, not the process CWD.
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return cfg


@contextmanager
def _sqlite_path_env(db_path: Path) -> Iterator[None]:
    """Inject SQLITE_PATH for Alembic without loading root settings/.env."""
    previous = os.environ.get("SQLITE_PATH")
    os.environ["SQLITE_PATH"] = str(db_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SQLITE_PATH", None)
        else:
            os.environ["SQLITE_PATH"] = previous


def upgrade_head(db_path: Path) -> None:
    """Run ``alembic upgrade head`` against a temporary SQLite file path."""
    with _sqlite_path_env(db_path):
        command.upgrade(_alembic_config(), "head")


def upgrade_to(db_path: Path, revision: str) -> None:
    """Run ``alembic upgrade <revision>`` against a temporary SQLite file path."""
    with _sqlite_path_env(db_path):
        command.upgrade(_alembic_config(), revision)


def list_user_tables(db_path: Path) -> set[str]:
    """Return user table names from sqlite_master (excludes sqlite_* internals)."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    return {row[0] for row in rows}


def table_sql(db_path: Path, table: str) -> str:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    assert row is not None, f"missing table DDL for {table}"
    return row[0] or ""


def index_rows(db_path: Path, table: str) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(f"PRAGMA index_list('{table}')").fetchall()  # noqa: S608
        )


def foreign_key_rows(db_path: Path, table: str) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return list(
            conn.execute(f"PRAGMA foreign_key_list('{table}')").fetchall()  # noqa: S608
        )


def column_info(db_path: Path, table: str) -> dict[str, sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()  # noqa: S608
    return {row["name"]: row for row in rows}


def alembic_version(db_path: Path) -> str | None:
    with sqlite3.connect(db_path) as conn:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    return None if row is None else str(row[0])


def _normalize_sql_fragment(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _check_sql_texts_from_metadata(table_name: str) -> list[str]:
    table = Base.metadata.tables[table_name]
    texts: list[str] = []
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint):
            texts.append(_normalize_sql_fragment(str(constraint.sqltext)))
    return texts


def _fk_specs_from_metadata(table_name: str) -> set[tuple[str, str, str, str | None]]:
    """(local_col, remote_table, remote_col, ondelete) tuples from model metadata."""
    table = Base.metadata.tables[table_name]
    specs: set[tuple[str, str, str, str | None]] = set()
    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue
        ondelete = constraint.ondelete
        for element in constraint.elements:
            specs.add(
                (
                    element.parent.name,
                    element.column.table.name,
                    element.column.name,
                    ondelete,
                )
            )
    return specs


def _unique_column_sets_from_metadata(table_name: str) -> set[frozenset[str]]:
    table = Base.metadata.tables[table_name]
    unique_sets: set[frozenset[str]] = set()
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            unique_sets.add(frozenset(col.name for col in constraint.columns))
    for column in table.columns:
        if column.unique:
            unique_sets.add(frozenset({column.name}))
    for index in table.indexes:
        if index.unique:
            unique_sets.add(frozenset(col.name for col in index.columns))
    return unique_sets


def _index_specs_from_metadata(table_name: str) -> set[tuple[str, frozenset[str], bool]]:
    """(index_name, columns, unique) for non-primary indexes on the model."""
    table = Base.metadata.tables[table_name]
    specs: set[tuple[str, frozenset[str], bool]] = set()
    for index in table.indexes:
        assert isinstance(index, Index)
        name = index.name
        assert name is not None
        cols = frozenset(col.name for col in index.columns)
        specs.add((name, cols, bool(index.unique)))
    # Column-level unique/index flags may also create named indexes via convention.
    for column in table.columns:
        if column.index or column.unique:
            # Prefer matching any model index that covers the column.
            covered = any(column.name in cols for _n, cols, _u in specs)
            if not covered:
                # SQLAlchemy will still emit an index; name follows naming_convention.
                expected_name = f"ix_{table_name}_{column.name}"
                specs.add(
                    (
                        expected_name,
                        frozenset({column.name}),
                        bool(column.unique),
                    )
                )
    return specs


def assert_schema_matches_metadata(db_path: Path) -> None:
    """Compare migrated SQLite objects with Base.metadata inventory."""
    tables = list_user_tables(db_path)
    app_tables = tables - {"alembic_version"}
    assert app_tables == EXPECTED_TABLES
    assert app_tables.isdisjoint(LANGGRAPH_CHECKPOINT_MARKERS)
    for name in tables:
        assert "checkpoint" not in name.lower()

    for table_name in sorted(EXPECTED_TABLES):
        meta_table = Base.metadata.tables[table_name]
        migrated_cols = column_info(db_path, table_name)
        expected_col_names = {col.name for col in meta_table.columns}
        assert set(migrated_cols) == expected_col_names, table_name

        for col in meta_table.columns:
            row = migrated_cols[col.name]
            # SQLite notnull: 1 = NOT NULL.
            assert bool(row["notnull"]) == (not col.nullable), (
                f"{table_name}.{col.name} nullability"
            )
            if col.primary_key:
                assert int(row["pk"]) >= 1

        # Check constraints appear in CREATE TABLE SQL.
        ddl = _normalize_sql_fragment(table_sql(db_path, table_name))
        for check_sql in _check_sql_texts_from_metadata(table_name):
            # SQLite may reformat quotes/spaces; require key predicate fragments.
            # Full text is usually preserved from our explicit CHECK definitions.
            assert check_sql in ddl or _check_predicate_present(check_sql, ddl), (
                f"missing check on {table_name}: {check_sql}"
            )

        # Foreign keys.
        meta_fks = _fk_specs_from_metadata(table_name)
        db_fks = {
            (
                row["from"],
                row["table"],
                row["to"],
                (row["on_delete"] or None),
            )
            for row in foreign_key_rows(db_path, table_name)
        }
        # Normalize ondelete: SQLite may report NO ACTION for unspecified.
        normalized_db_fks: set[tuple[str, str, str, str | None]] = set()
        for local, remote_table, remote_col, ondelete in db_fks:
            od = ondelete
            if od is not None and od.upper() in {"NO ACTION", "RESTRICT"}:
                # RESTRICT is stored; metadata may use RESTRICT or SET NULL/CASCADE.
                pass
            if od is not None and od.upper() == "NO ACTION":
                od = None
            normalized_db_fks.add((local, remote_table, remote_col, od))

        for local, remote_table, remote_col, ondelete in meta_fks:
            match = next(
                (
                    item
                    for item in normalized_db_fks
                    if item[0] == local
                    and item[1] == remote_table
                    and item[2] == remote_col
                ),
                None,
            )
            assert match is not None, (
                f"missing FK {table_name}.{local} -> "
                f"{remote_table}.{remote_col}"
            )
            if ondelete is not None:
                assert (match[3] or "").upper() == ondelete.upper(), (
                    f"ondelete mismatch for {table_name}.{local}: "
                    f"{match[3]!r} != {ondelete!r}"
                )

        # Unique indexes / uniqueness.
        meta_uniques = _unique_column_sets_from_metadata(table_name)
        db_unique_sets: set[frozenset[str]] = set()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            for ix in conn.execute(
                f"PRAGMA index_list('{table_name}')"  # noqa: S608
            ).fetchall():
                if not ix["unique"]:
                    continue
                # Skip autoindex for primary keys when origin is 'pk'.
                if ix["origin"] == "pk":
                    continue
                cols = conn.execute(
                    f"PRAGMA index_info('{ix['name']}')"  # noqa: S608
                ).fetchall()
                db_unique_sets.add(frozenset(c["name"] for c in cols))
        for unique_cols in meta_uniques:
            assert unique_cols in db_unique_sets, (
                f"missing unique set on {table_name}: {sorted(unique_cols)}"
            )

        # Named indexes (unique and non-unique).
        meta_indexes = _index_specs_from_metadata(table_name)
        db_indexes: set[tuple[str, frozenset[str], bool]] = set()
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            for ix in conn.execute(
                f"PRAGMA index_list('{table_name}')"  # noqa: S608
            ).fetchall():
                if ix["origin"] == "pk":
                    continue
                cols = conn.execute(
                    f"PRAGMA index_info('{ix['name']}')"  # noqa: S608
                ).fetchall()
                db_indexes.add(
                    (
                        ix["name"],
                        frozenset(c["name"] for c in cols),
                        bool(ix["unique"]),
                    )
                )
        for name, cols, unique in meta_indexes:
            assert (name, cols, unique) in db_indexes, (
                f"missing index {name} on {table_name} "
                f"cols={sorted(cols)} unique={unique}; have={db_indexes}"
            )


def _check_predicate_present(check_sql: str, ddl: str) -> bool:
    """Fallback: strip check wrapper noise and compare core predicate tokens."""
    core = check_sql
    for prefix in ("check (", "check("):
        if core.startswith(prefix):
            core = core[len(prefix) :]
            if core.endswith(")"):
                core = core[:-1]
    core = core.strip()
    return core in ddl


def test_alembic_reports_exactly_one_head() -> None:
    """``alembic heads`` must report the single expected revision."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    heads = script.get_heads()
    assert heads == [EXPECTED_HEAD]


def test_fresh_upgrade_creates_eleven_application_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    assert not db_path.exists()

    upgrade_head(db_path)

    assert db_path.is_file()
    assert alembic_version(db_path) == EXPECTED_HEAD
    tables = list_user_tables(db_path)
    assert EXPECTED_TABLES.issubset(tables)
    assert "alembic_version" in tables
    assert tables.isdisjoint(LANGGRAPH_CHECKPOINT_MARKERS)
    app_only = tables - {"alembic_version"}
    assert app_only == EXPECTED_TABLES
    assert_schema_matches_metadata(db_path)


def test_second_upgrade_on_initialized_file_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "initialized.db"
    upgrade_head(db_path)
    tables_after_first = list_user_tables(db_path)
    version_after_first = alembic_version(db_path)

    # Seed a marker row after first upgrade.
    marker_id = str(uuid4()).replace("-", "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO conversation (id, created_at, updated_at) "
            "VALUES (1, '2020-01-01 00:00:00', '2020-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO memory_facts "
            "(id, key, value_json, source, created_at, updated_at) "
            "VALUES (?, 'preferred_city', ?, 'test', "
            "'2020-01-01 00:00:00', '2020-01-01 00:00:00')",
            (marker_id, '{"city":"Berlin"}'),
        )
        conn.commit()

    upgrade_head(db_path)

    assert alembic_version(db_path) == version_after_first == EXPECTED_HEAD
    assert list_user_tables(db_path) == tables_after_first
    assert_schema_matches_metadata(db_path)

    with sqlite3.connect(db_path) as conn:
        conv = conn.execute("SELECT id FROM conversation WHERE id = 1").fetchone()
        fact = conn.execute(
            "SELECT key, value_json FROM memory_facts WHERE id = ?",
            (marker_id,),
        ).fetchone()
    assert conv is not None
    assert fact is not None
    assert fact[0] == "preferred_city"
    assert "Berlin" in fact[1]


def test_upgrade_preserves_initialized_data_and_constraints(tmp_path: Path) -> None:
    """Re-upgrade must not drop/recreate tables or lose application rows."""
    db_path = tmp_path / "persist.db"
    upgrade_head(db_path)

    attachment_id = str(uuid4()).replace("-", "")
    job_id = str(uuid4()).replace("-", "")
    hash_value = "a" * 64
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO attachments "
            "(id, file_hash, original_name, mime_type, size_bytes, page_count, "
            "storage_path, state, created_at, updated_at) VALUES "
            "(?, ?, 'cv.pdf', 'application/pdf', 100, 1, 'staged/a.pdf', "
            "'staged', '2020-01-01 00:00:00', '2020-01-01 00:00:00')",
            (attachment_id, hash_value),
        )
        conn.execute(
            "INSERT INTO job_posts "
            "(id, source_type, raw_content, raw_content_hash, processing_status, "
            "graph_sync_status, record_status, created_at, updated_at) VALUES "
            "(?, 'text', 'Engineer', ?, 'received', 'not_required', 'active', "
            "'2020-01-01 00:00:00', '2020-01-01 00:00:00')",
            (job_id, "b" * 64),
        )
        conn.commit()

        # Constraint still enforced after first upgrade.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO attachments "
                "(id, file_hash, original_name, mime_type, size_bytes, "
                "storage_path, state, created_at, updated_at) VALUES "
                "(?, ?, 'other.pdf', 'application/pdf', 1, 'staged/b.pdf', "
                "'staged', '2020-01-01 00:00:00', '2020-01-01 00:00:00')",
                (str(uuid4()).replace("-", ""), hash_value),
            )
        conn.rollback()

    upgrade_head(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        att = conn.execute(
            "SELECT file_hash, state FROM attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
        job = conn.execute(
            "SELECT processing_status, record_status FROM job_posts WHERE id = ?",
            (job_id,),
        ).fetchone()
        assert att == (hash_value, "staged")
        assert job == ("received", "active")

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO job_posts "
                "(id, source_type, raw_content, raw_content_hash, "
                "processing_status, graph_sync_status, record_status, "
                "created_at, updated_at) VALUES "
                "(?, 'text', 'x', ?, 'full', 'not_required', 'active', "
                "'2020-01-01 00:00:00', '2020-01-01 00:00:00')",
                (str(uuid4()).replace("-", ""), "c" * 64),
            )
        conn.rollback()


def test_migration_file_has_no_checkpoint_or_destructive_reset() -> None:
    """Static guard: revisions must not create checkpoint objects or reset."""
    initial = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "c885a5846d85_initial_application_schema.py"
    )
    plan3 = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "d4e5f6a7b8c9_plan3_run_idempotency.py"
    )
    for revision in (initial, plan3):
        text = revision.read_text(encoding="utf-8")
        upgrade_section = text.split("def downgrade", 1)[0]
        # No LangGraph checkpoint table creation in upgrade.
        for marker in LANGGRAPH_CHECKPOINT_MARKERS:
            assert f'"{marker}"' not in upgrade_section
            assert f"'{marker}'" not in upgrade_section
        # No broad reset helpers in upgrade path.
        assert "drop_all" not in upgrade_section
        assert "metadata.drop" not in upgrade_section
        assert "DROP DATABASE" not in upgrade_section.upper()
        # Additive path must not drop tables.
        assert "op.drop_table" not in upgrade_section

    initial_upgrade = initial.read_text(encoding="utf-8").split("def downgrade", 1)[0]
    assert "op.create_table" in initial_upgrade
    plan3_upgrade = plan3.read_text(encoding="utf-8").split("def downgrade", 1)[0]
    assert "add_column" in plan3_upgrade
    assert "op.create_table" not in plan3_upgrade
    assert "op.drop_table" not in plan3_upgrade


def test_plan2_initialized_schema_upgrades_additively_with_data(
    tmp_path: Path,
) -> None:
    """Accepted Plan 2 head upgrades to Plan 3 without destructive recreation."""
    db_path = tmp_path / "plan2_then_plan3.db"
    upgrade_to(db_path, PLAN2_HEAD)
    assert alembic_version(db_path) == PLAN2_HEAD

    tables_at_plan2 = list_user_tables(db_path)
    assert "agent_runs" in tables_at_plan2
    plan2_agent_cols = set(column_info(db_path, "agent_runs"))
    assert "turn_idempotency_key" not in plan2_agent_cols
    assert "resume_idempotency_key" not in plan2_agent_cols

    message_id = str(uuid4()).replace("-", "")
    run_id = str(uuid4()).replace("-", "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO conversation (id, created_at, updated_at) "
            "VALUES (1, '2020-01-01 00:00:00', '2020-01-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO chat_messages "
            "(id, conversation_id, role, content, structured_payload, "
            "created_at, updated_at) VALUES "
            "(?, 1, 'user', 'hello from plan2', NULL, "
            "'2020-01-01 00:00:00', '2020-01-01 00:00:00')",
            (message_id,),
        )
        conn.execute(
            "INSERT INTO agent_runs "
            "(id, message_id, state, pending_approval, error, "
            "created_at, updated_at) VALUES "
            "(?, ?, 'interrupted', 1, NULL, "
            "'2020-01-01 00:00:00', '2020-01-01 00:00:00')",
            (run_id, message_id),
        )
        conn.commit()

    upgrade_head(db_path)

    assert alembic_version(db_path) == EXPECTED_HEAD
    assert list_user_tables(db_path) == tables_at_plan2
    assert_schema_matches_metadata(db_path)

    cols = column_info(db_path, "agent_runs")
    assert "turn_idempotency_key" in cols
    assert "resume_idempotency_key" in cols
    assert int(cols["turn_idempotency_key"]["notnull"]) == 0
    assert int(cols["resume_idempotency_key"]["notnull"]) == 0

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, message_id, state, pending_approval, "
            "turn_idempotency_key, resume_idempotency_key "
            "FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        msg = conn.execute(
            "SELECT content FROM chat_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == run_id
    assert row[1] == message_id
    assert row[2] == "interrupted"
    assert int(row[3]) == 1
    assert row[4] is None
    assert row[5] is None
    assert msg is not None
    assert msg[0] == "hello from plan2"

    # Unique turn key enforced after additive upgrade.
    message_id_2 = str(uuid4()).replace("-", "")
    run_id_2 = str(uuid4()).replace("-", "")
    run_id_3 = str(uuid4()).replace("-", "")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO chat_messages "
            "(id, conversation_id, role, content, structured_payload, "
            "created_at, updated_at) VALUES "
            "(?, 1, 'user', 'second', NULL, "
            "'2020-01-01 00:00:01', '2020-01-01 00:00:01')",
            (message_id_2,),
        )
        conn.execute(
            "INSERT INTO agent_runs "
            "(id, message_id, state, pending_approval, error, "
            "turn_idempotency_key, resume_idempotency_key, "
            "created_at, updated_at) VALUES "
            "(?, ?, 'pending', 0, NULL, 'dup-key', NULL, "
            "'2020-01-01 00:00:01', '2020-01-01 00:00:01')",
            (run_id_2, message_id_2),
        )
        conn.commit()
        message_id_3 = str(uuid4()).replace("-", "")
        conn.execute(
            "INSERT INTO chat_messages "
            "(id, conversation_id, role, content, structured_payload, "
            "created_at, updated_at) VALUES "
            "(?, 1, 'user', 'third', NULL, "
            "'2020-01-01 00:00:02', '2020-01-01 00:00:02')",
            (message_id_3,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO agent_runs "
                "(id, message_id, state, pending_approval, error, "
                "turn_idempotency_key, resume_idempotency_key, "
                "created_at, updated_at) VALUES "
                "(?, ?, 'pending', 0, NULL, 'dup-key', NULL, "
                "'2020-01-01 00:00:02', '2020-01-01 00:00:02')",
                (run_id_3, message_id_3),
            )
        conn.rollback()


def test_env_uses_sqlite_path_without_loading_root_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With SQLITE_PATH set, upgrade must not call load_settings (no real .env)."""
    db_path = tmp_path / "no_settings.db"

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("load_settings must not run when SQLITE_PATH is set")

    monkeypatch.setattr("app.config.load_settings", _boom)
    upgrade_head(db_path)
    assert alembic_version(db_path) == EXPECTED_HEAD
    assert EXPECTED_TABLES.issubset(list_user_tables(db_path))


def test_metadata_parity_via_sqlalchemy_inspect(tmp_path: Path) -> None:
    """Engine reflection agrees with model metadata for the migrated file."""
    db_path = tmp_path / "reflect.db"
    upgrade_head(db_path)

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        reflected = set(inspector.get_table_names())
        assert EXPECTED_TABLES.issubset(reflected)
        assert reflected.isdisjoint(LANGGRAPH_CHECKPOINT_MARKERS)

        for table_name in EXPECTED_TABLES:
            meta_cols = {
                c.name: c for c in Base.metadata.tables[table_name].columns
            }
            reflected_cols = {c["name"]: c for c in inspector.get_columns(table_name)}
            assert set(reflected_cols) == set(meta_cols)

            reflected_fks = inspector.get_foreign_keys(table_name)
            meta_fk_targets = {
                (tuple(fk["constrained_columns"]), fk["referred_table"])
                for fk in reflected_fks
            }
            for constraint in Base.metadata.tables[table_name].constraints:
                if isinstance(constraint, ForeignKeyConstraint):
                    local_cols = tuple(col.name for col in constraint.columns)
                    remote_table = constraint.elements[0].column.table.name
                    assert (local_cols, remote_table) in meta_fk_targets

            reflected_unique = {
                frozenset(u["column_names"])
                for u in inspector.get_unique_constraints(table_name)
            }
            # Unique indexes also enforce uniqueness on SQLite.
            for ix in inspector.get_indexes(table_name):
                if ix.get("unique"):
                    reflected_unique.add(frozenset(ix["column_names"]))
            for unique_cols in _unique_column_sets_from_metadata(table_name):
                assert unique_cols in reflected_unique
    finally:
        engine.dispose()

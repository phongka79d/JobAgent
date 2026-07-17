"""Migration-to-accepted-model SQLite schema parity helpers.

Compares a migrated SQLite database against the application-table SQLAlchemy
metadata: columns, named constraints, indexes (including partial WHERE),
and foreign-key targets/delete actions.
"""
from __future__ import annotations

import re
from typing import Any

import app.db.models  # noqa: F401  — register application tables
from app.db.base import Base
from app.db.seed import APPLICATION_TABLE_NAMES
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.types import JSON, DateTime, TypeEngine

_CONSTRAINT_NAME_RE = re.compile(
    r"\bCONSTRAINT\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
_WHERE_RE = re.compile(r"\bWHERE\s+(.+)$", re.IGNORECASE | re.DOTALL)


def _sqlite_type_name(col_type: TypeEngine[Any]) -> str:
    """Map accepted model column types to SQLite declared type names."""
    if isinstance(col_type, Text):
        return "TEXT"
    if isinstance(col_type, Integer):
        return "INTEGER"
    if isinstance(col_type, DateTime):
        return "DATETIME"
    if isinstance(col_type, JSON):
        return "JSON"
    return str(col_type).upper()


def accepted_metadata() -> MetaData:
    """Return the registered application metadata (twelve tables)."""
    assert set(Base.metadata.tables) == APPLICATION_TABLE_NAMES
    return Base.metadata


def expected_named_constraints() -> frozenset[str]:
    """All named PK/UQ/CK/FK constraints from accepted models (63)."""
    names: set[str] = set()
    for table in accepted_metadata().tables.values():
        for constraint in table.constraints:
            if constraint.name:
                names.add(str(constraint.name))
    return frozenset(names)


def expected_columns() -> dict[str, dict[str, tuple[str, bool]]]:
    """table -> column -> (sqlite_type, nullable)."""
    out: dict[str, dict[str, tuple[str, bool]]] = {}
    for tname, table in accepted_metadata().tables.items():
        out[tname] = {
            col.name: (_sqlite_type_name(col.type), bool(col.nullable))
            for col in table.columns
        }
    return out


def expected_foreign_keys() -> frozenset[tuple[str, str, str, str, str]]:
    """(table, local_col, ref_table, ref_col, ondelete_upper)."""
    fks: set[tuple[str, str, str, str, str]] = set()
    for tname, table in accepted_metadata().tables.items():
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            ondelete = (constraint.ondelete or "NO ACTION").upper()
            for element in constraint.elements:
                fks.add(
                    (
                        tname,
                        element.parent.name,
                        element.column.table.name,
                        element.column.name,
                        ondelete,
                    )
                )
    return frozenset(fks)


def expected_indexes() -> dict[str, dict[str, Any]]:
    """name -> {table, unique, columns, where_fragment|None}."""
    out: dict[str, dict[str, Any]] = {}
    for tname, table in accepted_metadata().tables.items():
        for index in table.indexes:
            where = index.dialect_options.get("sqlite", {}).get("where")
            where_fragment: str | None = None
            if where is not None:
                compiled = str(
                    where.compile(compile_kwargs={"literal_binds": True})
                )
                where_fragment = " ".join(compiled.split()).lower()
            out[str(index.name)] = {
                "table": tname,
                "unique": bool(index.unique),
                "columns": tuple(col.name for col in index.columns),
                "where": where_fragment,
            }
    return out


def _user_table_names(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ).fetchall()
    return {str(r[0]) for r in rows}


def _named_constraints_from_ddl(table_sql: str) -> set[str]:
    return {m.group(1) for m in _CONSTRAINT_NAME_RE.finditer(table_sql)}


def _normalize_where(sql: str | None) -> str | None:
    if not sql:
        return None
    match = _WHERE_RE.search(sql)
    if not match:
        return None
    return " ".join(match.group(1).split()).lower().rstrip(";")


def observe_schema(connection: Connection) -> dict[str, Any]:
    """Load migrated SQLite schema facts for parity comparison."""
    tables = _user_table_names(connection)
    table_sql_rows = connection.execute(
        text(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        )
    ).fetchall()
    table_sql = {str(r[0]): str(r[1]) for r in table_sql_rows}

    columns: dict[str, dict[str, tuple[str, bool]]] = {}
    named: set[str] = set()
    fks: set[tuple[str, str, str, str, str]] = set()
    indexes: dict[str, dict[str, Any]] = {}

    for tname in sorted(APPLICATION_TABLE_NAMES):
        if tname not in tables:
            continue
        col_rows = connection.execute(
            text(f"PRAGMA table_info('{tname}')")
        ).fetchall()
        columns[tname] = {
            str(row[1]): (str(row[2]).upper(), not bool(row[3]))
            for row in col_rows
        }
        if tname in table_sql:
            named |= _named_constraints_from_ddl(table_sql[tname])
        for row in connection.execute(
            text(f"PRAGMA foreign_key_list('{tname}')")
        ).fetchall():
            fks.add(
                (
                    tname,
                    str(row[3]),
                    str(row[2]),
                    str(row[4]),
                    str(row[6] or "NO ACTION").upper(),
                )
            )
        for row in connection.execute(
            text(f"PRAGMA index_list('{tname}')")
        ).fetchall():
            ix_name = str(row[1])
            if ix_name.startswith("sqlite_autoindex_"):
                continue
            cols = tuple(
                str(r[2])
                for r in connection.execute(
                    text(f"PRAGMA index_info('{ix_name}')")
                ).fetchall()
                if r[2] is not None
            )
            ix_sql_row = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND name = :n"
                ),
                {"n": ix_name},
            ).fetchone()
            ix_sql = str(ix_sql_row[0]) if ix_sql_row and ix_sql_row[0] else None
            indexes[ix_name] = {
                "table": tname,
                "unique": bool(row[2]),
                "columns": cols,
                "where": _normalize_where(ix_sql),
            }

    return {
        "tables": tables,
        "columns": columns,
        "named_constraints": frozenset(named),
        "foreign_keys": frozenset(fks),
        "indexes": indexes,
    }


def assert_migrated_matches_accepted_models(
    connection: Connection,
    *,
    exact_tables: frozenset[str] | None = None,
) -> None:
    """Prove exact migration ↔ accepted model parity for application tables.

    Checks: optional exact table set, every column name/nullability/type,
    all named constraints, all indexes (columns/uniqueness/partial WHERE),
    and every FK target/delete action.
    """
    expected_constraints = expected_named_constraints()
    # 0002 had 56; +2 pk + 2 cv FKs + 3 ownership FKs = 63 named constraints.
    assert len(expected_constraints) == 63
    expected_cols = expected_columns()
    expected_fks = expected_foreign_keys()
    expected_ix = expected_indexes()
    # Prior 5 + 3 source_attachment_id indexes.
    assert len(expected_ix) == 8

    observed = observe_schema(connection)
    if exact_tables is not None:
        assert observed["tables"] == set(exact_tables), (
            f"table set mismatch: "
            f"extra={observed['tables'] - set(exact_tables)} "
            f"missing={set(exact_tables) - observed['tables']}"
        )
    else:
        missing_tables = APPLICATION_TABLE_NAMES - observed["tables"]
        assert not missing_tables, f"missing application tables: {missing_tables}"

    assert observed["columns"] == expected_cols, (
        "column parity mismatch between models and migrated DB"
    )

    missing_c = expected_constraints - observed["named_constraints"]
    extra_app_c = {
        n
        for n in observed["named_constraints"] - expected_constraints
        if n.startswith(("pk_", "fk_", "uq_", "ck_"))
    }
    assert not missing_c, f"missing named constraints: {sorted(missing_c)}"
    assert not extra_app_c, f"unexpected named constraints: {sorted(extra_app_c)}"
    assert len(expected_constraints & observed["named_constraints"]) == 63

    missing_fk = expected_fks - observed["foreign_keys"]
    extra_fk = observed["foreign_keys"] - expected_fks
    assert not missing_fk, f"missing FKs: {sorted(missing_fk)}"
    assert not extra_fk, f"unexpected FKs: {sorted(extra_fk)}"

    obs_ix = observed["indexes"]
    missing_ix = set(expected_ix) - set(obs_ix)
    assert not missing_ix, f"missing indexes: {sorted(missing_ix)}"
    for name, spec in expected_ix.items():
        got = obs_ix[name]
        assert got["table"] == spec["table"], name
        assert got["unique"] == spec["unique"], name
        assert got["columns"] == spec["columns"], name
        assert got["where"] == spec["where"], (
            f"index {name} where mismatch: {got['where']!r} != {spec['where']!r}"
        )

    kinds = {
        PrimaryKeyConstraint,
        UniqueConstraint,
        CheckConstraint,
        ForeignKeyConstraint,
    }
    found_kinds = {
        type(c)
        for t in accepted_metadata().tables.values()
        for c in t.constraints
        if c.name
    }
    assert kinds <= found_kinds

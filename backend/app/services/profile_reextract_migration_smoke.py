"""Provider-free, read-only evidence projector for a migrated app_data SQLite file."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class MigrationSmokeResult:
    alembic_revision: str
    files: list[str]
    table_counts: dict[str, int]
    active_profile_id: str | None
    pending_action_count: int
    profile_draft_columns: list[str]
    operation_columns: list[str]
    foreign_key_check: list[tuple[object, ...]]


def run_smoke(*, sqlite_path: Path) -> MigrationSmokeResult:
    """Read migration parity facts without writes, network clients, or providers."""
    path = sqlite_path.resolve(strict=True)
    normalized_path = str(path).replace("\\", "/")
    uri = f"file:{quote(normalized_path)}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        table_counts = {}
        for table in tables:
            count_row = connection.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()
            table_counts[table] = int(count_row[0])
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        active = connection.execute(
            "SELECT active_profile_id FROM workspace_state WHERE id = 'main'"
        ).fetchone()
        profile_draft_columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info('profile_drafts')")
        ]
        operation_columns = [
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info('profile_reextract_operations')"
            )
        ]
        pending_action_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM profile_reextract_operations "
                "WHERE state IN ('running', 'review_ready')"
            ).fetchone()[0]
        )
        return MigrationSmokeResult(
            alembic_revision="" if revision is None else str(revision[0]),
            files=[path.name],
            table_counts=table_counts,
            active_profile_id=None if active is None else active[0],
            pending_action_count=pending_action_count,
            profile_draft_columns=profile_draft_columns,
            operation_columns=operation_columns,
            foreign_key_check=[
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
            ],
        )

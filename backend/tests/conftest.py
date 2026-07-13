"""Pytest plugins shared across unit and integration tests."""

from __future__ import annotations

# Register shared migration harness fixtures (isolated_sqlite, migrated_sqlite).
pytest_plugins = ("tests.support.db_migration",)

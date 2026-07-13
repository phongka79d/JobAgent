"""Pytest plugins shared across unit and integration tests."""

from __future__ import annotations

# Shared fixtures: migration harness + health integration helpers.
pytest_plugins = (
    "tests.support.db_migration",
    "tests.support.health",
)

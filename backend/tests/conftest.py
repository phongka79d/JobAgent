"""Pytest plugins shared across unit and integration tests."""

from __future__ import annotations

# Shared fixtures: migration harness + health + public chat API helpers.
pytest_plugins = (
    "tests.support.db_migration",
    "tests.support.health",
    "tests.support.public_api",
)

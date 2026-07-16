"""Idempotent singleton seeds for conversation and job_preferences.

Owns the startup safeguard that inserts missing ``conversation('main')`` and
``job_preferences('active')`` rows after migrations. Never seeds
``candidate_profile``, never runs migrations, and never invokes metadata
schema creation helpers reserved for Alembic only.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.chat import CONVERSATION_ID
from app.db.models.profiles import JOB_PREFERENCE_KEYS, JOB_PREFERENCES_ID

# Application tables owned by Alembic (Master §6.2) — ten exact names.
APPLICATION_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "attachments",
        "attachment_text_chunks",
        "candidate_profile",
        "profile_drafts",
        "job_preferences",
        "job_posts",
        "conversation",
        "chat_messages",
        "agent_runs",
        "tool_executions",
    }
)

# Single owned seed SQL (sync Alembic path and async startup path).
_CONVERSATION_SEED_SQL = (
    "INSERT OR IGNORE INTO conversation (id, created_at, updated_at) "
    "VALUES (:id, :created_at, :updated_at)"
)
_JOB_PREFERENCES_SEED_SQL = (
    "INSERT OR IGNORE INTO job_preferences "
    "(id, preferences_json, created_at, updated_at) "
    "VALUES (:id, :preferences_json, :created_at, :updated_at)"
)


def empty_job_preferences_document() -> dict[str, list[Any]]:
    """Return the approved empty preferences document (four empty lists)."""
    return {key: [] for key in JOB_PREFERENCE_KEYS}


def _preferences_json_text() -> str:
    return json.dumps(empty_job_preferences_document(), separators=(",", ":"))


def _singleton_seed_statements() -> Sequence[tuple[str, dict[str, Any]]]:
    """Return the two seed (SQL, params) pairs with one shared construction."""
    now = utc_now()
    return (
        (
            _CONVERSATION_SEED_SQL,
            {
                "id": CONVERSATION_ID,
                "created_at": now,
                "updated_at": now,
            },
        ),
        (
            _JOB_PREFERENCES_SEED_SQL,
            {
                "id": JOB_PREFERENCES_ID,
                "preferences_json": _preferences_json_text(),
                "created_at": now,
                "updated_at": now,
            },
        ),
    )


def ensure_singleton_seeds_on_connection(connection: Connection) -> None:
    """Insert missing singleton rows using a sync SQLAlchemy connection.

    Safe for Alembic upgrade transactions and test helpers. Idempotent via
    ``INSERT OR IGNORE`` on primary keys.
    """
    for sql, params in _singleton_seed_statements():
        connection.execute(text(sql), params)


async def ensure_singleton_seeds(session: AsyncSession) -> None:
    """Insert missing singleton rows on an async session (startup safeguard).

    Caller owns the surrounding transaction (e.g. ``session_scope``). Does not
    commit independently. Never touches ``candidate_profile``.
    """
    for sql, params in _singleton_seed_statements():
        await session.execute(text(sql), params)
    await session.flush()

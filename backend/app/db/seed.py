"""Application table registry and idempotent workspace-state seed."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.db.models.profiles import WORKSPACE_STATE_ID

APPLICATION_TABLE_NAMES: frozenset[str] = frozenset(
    {
        "attachments",
        "attachment_text_chunks",
        "cv_documents",
        "cv_document_drafts",
        "cv_tailoring_sessions",
        "cv_tailoring_versions",
        "profiles",
        "profile_drafts",
        "profile_reextract_operations",
        "profile_preferences",
        "workspace_state",
        "job_posts",
        "conversations",
        "chat_messages",
        "agent_runs",
        "agent_activities",
        "tool_executions",
        "job_evaluations",
    }
)


def empty_job_preferences_document() -> dict[str, list[Any]]:
    """Return the legacy empty document used only by historical revision 0001."""
    return {
        "target_roles": [],
        "preferred_locations": [],
        "acceptable_work_modes": [],
        "target_seniority": [],
    }


def ensure_singleton_seeds_on_connection(connection: Connection) -> None:
    """Seed tables owned by historical revision 0001 before revision 0005."""
    now = utc_now()
    connection.execute(
        text(
            "INSERT OR IGNORE INTO conversation (id, created_at, updated_at) "
            "VALUES ('main', :created_at, :updated_at)"
        ),
        {"created_at": now, "updated_at": now},
    )
    connection.execute(
        text(
            "INSERT OR IGNORE INTO job_preferences "
            "(id, preferences_json, created_at, updated_at) "
            "VALUES ('active', :preferences_json, :created_at, :updated_at)"
        ),
        {
            "preferences_json": json.dumps(
                empty_job_preferences_document(), separators=(",", ":")
            ),
            "created_at": now,
            "updated_at": now,
        },
    )


async def ensure_workspace_seed(session: AsyncSession) -> None:
    """Idempotently ensure only ``workspace_state('main')`` exists."""
    await session.execute(
        text(
            "INSERT OR IGNORE INTO workspace_state (id, active_profile_id, updated_at) "
            "VALUES (:id, NULL, :updated_at)"
        ),
        {"id": WORKSPACE_STATE_ID, "updated_at": utc_now()},
    )
    await session.flush()


# ponytail: migration tests import the former name until Task 13 updates the
# release harness. It delegates to the workspace-only seed and restores no
# singleton application rows.
ensure_singleton_seeds = ensure_workspace_seed

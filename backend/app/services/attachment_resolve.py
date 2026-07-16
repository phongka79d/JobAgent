"""Resolve processable attachment IDs for profile tools (Plan 4).

Owns recovery when the model invents placeholders such as ``current`` /
``latest`` instead of a staged attachment UUID. Prefer turn-scoped IDs,
then the current draft's source attachment, then the newest staged row.
Never invents IDs and never returns raw paths or file bytes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo

# Placeholders the model often invents when draft_id leaks into attachment_id.
_PLACEHOLDER_IDS: frozenset[str] = frozenset(
    {
        "current",
        "latest",
        "active",
        "staged",
        "cv",
        "pdf",
        "attachment",
        "none",
        "null",
        "undefined",
    }
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def looks_like_attachment_uuid(value: str) -> bool:
    """Return True when *value* is a UUID string form (v4 not strictly required)."""
    if not isinstance(value, str) or not _UUID_RE.match(value.strip()):
        return False
    try:
        UUID(value.strip())
    except (ValueError, TypeError, AttributeError):
        return False
    return True


async def list_processable_attachment_ids(session: AsyncSession) -> list[str]:
    """Return staged then active attachment IDs (newest staged first)."""
    staged = await session.execute(
        select(Attachment.id)
        .where(Attachment.state == ATTACHMENT_STATE_STAGED)
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
    )
    active = await session.execute(
        select(Attachment.id).where(Attachment.state == ATTACHMENT_STATE_ACTIVE)
    )
    out: list[str] = []
    seen: set[str] = set()
    for row in staged.fetchall():
        aid = str(row[0])
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    for row in active.fetchall():
        aid = str(row[0])
        if aid not in seen:
            seen.add(aid)
            out.append(aid)
    return out


async def _is_processable(session: AsyncSession, aid: str) -> bool:
    row = await att_repo.get_by_id(session, aid)
    if row is None:
        return False
    return row.state in {ATTACHMENT_STATE_STAGED, ATTACHMENT_STATE_ACTIVE}


async def resolve_attachment_id_for_propose(
    session: AsyncSession,
    requested: str | None,
    *,
    turn_attachment_ids: Sequence[str] | None = None,
) -> str | None:
    """Resolve a processable attachment id for ``propose_profile_from_cv``.

    Order:
    1. *requested* when it is a real UUID that exists and is staged/active
    2. First turn-scoped attachment id that exists and is processable
    3. Current draft ``source_attachment_id`` when processable
    4. Newest staged attachment
    5. Active attachment

    A concrete non-placeholder UUID that is missing or not processable fails
    closed (returns ``None``) without falling through to draft/newest staged.
    Placeholders such as ``current`` still recover via steps 2–5.

    Returns ``None`` when nothing processable is available.
    """
    raw = requested.strip() if isinstance(requested, str) else ""
    if raw and raw.lower() not in _PLACEHOLDER_IDS and looks_like_attachment_uuid(raw):
        if await _is_processable(session, raw):
            return raw
        # Explicit UUID miss: do not rewrite to another attachment.
        return None

    candidates: list[str] = []
    for item in turn_attachment_ids or ():
        if not isinstance(item, str):
            continue
        value = item.strip()
        if (
            value
            and value.lower() not in _PLACEHOLDER_IDS
            and looks_like_attachment_uuid(value)
            and value not in candidates
        ):
            candidates.append(value)

    draft = await profile_repo.get_current_draft(session)
    if draft is not None and isinstance(draft.source_attachment_id, str):
        source = draft.source_attachment_id.strip()
        if source and source not in candidates:
            candidates.append(source)

    for aid in await list_processable_attachment_ids(session):
        if aid not in candidates:
            candidates.append(aid)

    for aid in candidates:
        if await _is_processable(session, aid):
            return aid
    return None


__all__ = [
    "list_processable_attachment_ids",
    "looks_like_attachment_uuid",
    "resolve_attachment_id_for_propose",
]

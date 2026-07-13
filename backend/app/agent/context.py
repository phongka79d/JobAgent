"""Bounded recent-context and compact approved candidate memory (Master §12.4).

Prompt-budget owner: this module. The model receives only a compact recent
window that fits the documented ceilings below — never an unbounded conversation
load and never a fixed sixty-four-kilotoken history dump.

Budget ceilings (deterministic, content-character based on ``ChatMessage.content``):

* ``RECENT_CONTEXT_MAX_MESSAGES`` — hard cap on rows fetched and selected.
* ``RECENT_CONTEXT_CHAR_BUDGET`` — max sum of ``len(content)`` across selected
  messages (UTF-8-agnostic Python code-point length).

Selection walks newest-first using repository ordering
``(created_at DESC, id DESC)`` via a single bounded ``list_messages_before``
query (limit = max messages). It never calls full-conversation list APIs.
Selected messages are returned oldest→newest for chronological prompt order.

``candidate_context`` is a compact projection of the **approved** Candidate
Profile and Job Preferences only. Raw CV text, storage paths, secrets, full
history dumps, and unapproved draft documents never enter this list.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import ContextMessage
from app.db.models.chat import CONVERSATION_ID
from app.repositories import chat_messages as messages_repo
from app.repositories import profiles as profile_repo
from app.schemas.profile import (
    CandidateProfile,
    JobPreferences,
    parse_candidate_profile,
    parse_job_preferences,
)

# ---------------------------------------------------------------------------
# Documented prompt budget (owner: app.agent.context)
# ---------------------------------------------------------------------------
# Ceiling for how many prior durable messages may enter recent_context.
RECENT_CONTEXT_MAX_MESSAGES: int = 20
# Ceiling for total content characters across the selected recent window.
# Keeps the prompt bounded without relying on an unbounded history dump.
RECENT_CONTEXT_CHAR_BUDGET: int = 12_000

# Compact candidate cards use fixed kind tags (Agent state list[dict] slots).
CANDIDATE_CONTEXT_KIND_PROFILE: str = "approved_profile"
CANDIDATE_CONTEXT_KIND_PREFERENCES: str = "job_preferences"

# Evidence snippets are short already; still bound per-skill for prompt safety.
_MAX_EVIDENCE_ITEMS: int = 3
_MAX_EVIDENCE_CHARS: int = 120


class _MessageLike(Protocol):
    """Minimal durable message shape needed for budget selection."""

    id: str
    role: str
    content: str


def apply_recent_context_budget(
    messages_newest_first: Sequence[_MessageLike],
    *,
    max_messages: int = RECENT_CONTEXT_MAX_MESSAGES,
    char_budget: int = RECENT_CONTEXT_CHAR_BUDGET,
    exclude_ids: frozenset[str] | None = None,
) -> list[ContextMessage]:
    """Select a budget-bounded window from newest-first durable messages.

    Parameters
    ----------
    messages_newest_first:
        Prior messages ordered by ``(created_at DESC, id DESC)``. Callers must
        not pass an unbounded full-conversation dump; the loader below enforces
        a hard fetch limit.
    max_messages:
        Hard count ceiling (documented prompt budget).
    char_budget:
        Hard sum-of-content-length ceiling (documented prompt budget).
    exclude_ids:
        Message IDs to skip (e.g. the current turn's user message).

    Returns
    -------
    list[ContextMessage]
        Selected rows in chronological order ``(oldest → newest)``, compact
        projections only (id, role, content). Structured payloads and raw
        document bodies are never copied into context.
    """
    if max_messages < 0:
        raise ValueError("max_messages must be >= 0")
    if char_budget < 0:
        raise ValueError("char_budget must be >= 0")

    skip = exclude_ids or frozenset()
    selected_rev: list[ContextMessage] = []
    used_chars = 0

    for row in messages_newest_first:
        if len(selected_rev) >= max_messages:
            break
        if row.id in skip:
            continue
        # Text content only — never structured_payload / document bodies.
        content = row.content if isinstance(row.content, str) else ""
        size = len(content)
        if selected_rev and used_chars + size > char_budget:
            # Stop before exceeding budget; keep already-selected newer rows.
            break
        if not selected_rev and size > char_budget:
            # Single oversized newest message: include truncated to budget so the
            # window stays within the documented character ceiling.
            content = content[:char_budget]
            size = len(content)
        selected_rev.append(
            ContextMessage(id=row.id, role=row.role, content=content)
        )
        used_chars += size

    # Chronological order for prompt assembly.
    selected_rev.reverse()
    return selected_rev


async def load_recent_context(
    session: AsyncSession,
    *,
    exclude_ids: frozenset[str] | None = None,
    max_messages: int = RECENT_CONTEXT_MAX_MESSAGES,
    char_budget: int = RECENT_CONTEXT_CHAR_BUDGET,
) -> list[ContextMessage]:
    """Load recent main-conversation messages within the documented budget.

    Uses a single bounded repository fetch (``limit=max_messages``) against the
    singleton conversation. Does not paginate through the whole conversation and
    does not use history-cursor hydration (that path is for the public API).
    """
    if max_messages < 1:
        return []

    # Bounded newest-first fetch only — hard stop at max_messages rows.
    rows = await messages_repo.list_messages_before(
        session,
        limit=max_messages,
        before=None,
    )
    # Repository already confines to conversation_id == main; assert invariant.
    for row in rows:
        if row.conversation_id != CONVERSATION_ID:
            raise RuntimeError(
                "recent context loader received non-main conversation row"
            )

    return apply_recent_context_budget(
        rows,
        max_messages=max_messages,
        char_budget=char_budget,
        exclude_ids=exclude_ids,
    )


def empty_candidate_context() -> list[dict[str, object]]:
    """Return the empty approved-candidate projection (no active profile)."""
    return []


def _compact_skill(skill: Any) -> dict[str, Any]:
    """Project one skill without aliases or long evidence dumps."""
    ref = skill.skill
    evidence_src = list(skill.evidence or ())
    evidence: list[str] = []
    for item in evidence_src[:_MAX_EVIDENCE_ITEMS]:
        if not isinstance(item, str):
            continue
        snippet = item.strip()
        if not snippet:
            continue
        if len(snippet) > _MAX_EVIDENCE_CHARS:
            snippet = snippet[:_MAX_EVIDENCE_CHARS]
        evidence.append(snippet)
    return {
        "canonical_key": ref.canonical_key,
        "display_name": ref.display_name,
        "category": ref.category,
        "confidence": skill.confidence,
        "proficiency": skill.proficiency,
        "years": skill.years,
        "source": skill.source,
        "excluded": skill.excluded,
        "evidence": evidence,
    }


def compact_approved_profile_card(profile: CandidateProfile) -> dict[str, Any]:
    """Compact validated approved-profile card for ``candidate_context``.

    Structured facts only — no raw CV text, file paths, or secret fields.
    Omits skill aliases (taxonomy detail not needed for turn decisions).
    """
    return {
        "kind": CANDIDATE_CONTEXT_KIND_PROFILE,
        "summary": profile.summary,
        "current_title": profile.current_title,
        "total_experience_years": profile.total_experience_years,
        "skills": [_compact_skill(s) for s in profile.skills],
        "experiences": [
            {
                "title": e.title,
                "company": e.company,
                "start_date_text": e.start_date_text,
                "end_date_text": e.end_date_text,
                "summary": e.summary,
            }
            for e in profile.experiences
        ],
        "education": [
            {
                "institution": ed.institution,
                "degree": ed.degree,
                "field": ed.field,
                "graduation_year": ed.graduation_year,
            }
            for ed in profile.education
        ],
        "languages": [
            {"name": lang.name, "proficiency": lang.proficiency}
            for lang in profile.languages
        ],
        "extraction_confidence": profile.extraction_confidence,
    }


def compact_preferences_card(preferences: JobPreferences) -> dict[str, Any]:
    """Compact validated Job Preferences card for ``candidate_context``."""
    return {
        "kind": CANDIDATE_CONTEXT_KIND_PREFERENCES,
        "target_roles": list(preferences.target_roles),
        "preferred_locations": list(preferences.preferred_locations),
        "acceptable_work_modes": list(preferences.acceptable_work_modes),
        "target_seniority": list(preferences.target_seniority),
    }


def project_candidate_context(
    *,
    profile: CandidateProfile | None,
    preferences: JobPreferences | None,
) -> list[dict[str, Any]]:
    """Build the list projection from already-validated models (no I/O).

    Returns an empty list when no approved profile exists. Preferences alone
    never fill candidate context without an approved profile (draft-only and
    empty installs stay empty).
    """
    if profile is None:
        return list(empty_candidate_context())
    cards: list[dict[str, Any]] = [compact_approved_profile_card(profile)]
    if preferences is not None:
        cards.append(compact_preferences_card(preferences))
    return cards


async def load_candidate_context(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Load compact approved profile/preferences into Agent ``candidate_context``.

    Reads only ``candidate_profile('active')`` and ``job_preferences('active')``.
    Never reads draft rows, raw attachment bytes, or filesystem paths. Invalid
    stored JSON fails closed (empty context) rather than injecting unvalidated
    data into the model prompt.
    """
    row = await profile_repo.get_active_profile(session)
    if row is None:
        return list(empty_candidate_context())

    try:
        profile = parse_candidate_profile(row.profile_json)
    except Exception:
        return list(empty_candidate_context())

    prefs_model: JobPreferences | None = None
    prefs_row = await profile_repo.get_job_preferences(session)
    if prefs_row is not None:
        try:
            prefs_model = parse_job_preferences(prefs_row.preferences_json)
        except Exception:
            prefs_model = None

    return project_candidate_context(profile=profile, preferences=prefs_model)


__all__ = [
    "CANDIDATE_CONTEXT_KIND_PREFERENCES",
    "CANDIDATE_CONTEXT_KIND_PROFILE",
    "RECENT_CONTEXT_CHAR_BUDGET",
    "RECENT_CONTEXT_MAX_MESSAGES",
    "apply_recent_context_budget",
    "compact_approved_profile_card",
    "compact_preferences_card",
    "empty_candidate_context",
    "load_candidate_context",
    "load_recent_context",
    "project_candidate_context",
]

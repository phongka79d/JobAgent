"""Passive-JD recognition, durable source resolution, and cancel projection.

Owns pure fixed recognition/opt-out/sole-URL/obvious-JD predicates, one short
read of the initiating main-conversation user message via existing
repositories, bounded ``job_save_confirmation`` pending projection, and the
successful no-mutation cancellation ToolResult.

No provider, tool, interrupt, ingestion, evaluation, graph, or frontend work.
Does not import ``app.tools.jobs`` (graph/tool may import this module later).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import CHAT_MESSAGE_ROLE_USER, CONVERSATION_ID
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.schemas.jobs import (
    SAVE_JOB_CANCEL_OUTCOME,
    SAVE_JOB_SOURCE_CURRENT_MESSAGE,
    SaveJobCancellationData,
    SaveJobPreview,
)
from app.schemas.tools import ToolResult

SourceFailureCode = Literal["CURRENT_MESSAGE_NOT_FOUND", "INVALID_CURRENT_MESSAGE"]

# Stable safe codes for initiating-message lookup (Plan 12 source contract).
ERROR_CURRENT_MESSAGE_NOT_FOUND: Final[SourceFailureCode] = "CURRENT_MESSAGE_NOT_FOUND"
ERROR_INVALID_CURRENT_MESSAGE: Final[SourceFailureCode] = "INVALID_CURRENT_MESSAGE"

JOB_SAVE_CONFIRMATION_KIND: Final[str] = "job_save_confirmation"
JOB_SAVE_CONFIRMATION_ACTIONS: Final[tuple[str, str]] = (
    "save_job",
    "cancel_save_job",
)
SAVE_JOB_TOOL_NAME: Final[str] = "save_job"
CANCEL_SUMMARY: Final[str] = "JD chưa được lưu"
TEXT_LENGTH_CAP: Final[int] = 1_000_000

# Fixed obvious-JD thresholds (Plan 12 / design recognition boundary).
OBVIOUS_JD_MIN_NON_WS_CHARS: Final[int] = 300
OBVIOUS_JD_MIN_NON_EMPTY_LINES: Final[int] = 5
OBVIOUS_JD_MIN_DISTINCT_MARKERS: Final[int] = 2

# Fixed casefolded opt-out phrases (Unicode-aware via str.casefold).
_OPT_OUT_PHRASES: Final[tuple[str, ...]] = (
    "không lưu",
    "đừng lưu",
    "không cần lưu",
    "do not save",
    "don't save",
)

# Fixed marker allowlist; count distinct presence, never grow during Plan 12.
_JD_MARKERS: Final[tuple[str, ...]] = (
    "job description",
    "responsibilities",
    "requirements",
    "qualifications",
    "skills",
    "about the role",
    "mô tả công việc",
    "trách nhiệm",
    "yêu cầu",
    "kỹ năng",
    "quyền lợi",
    "mô tả vị trí",
)


@dataclass(frozen=True, slots=True)
class InitiatingMessage:
    """Exact durable initiating user content for the tool caller only."""

    content: str


@dataclass(frozen=True, slots=True)
class SourceLookupFailure:
    """Safe lookup/ownership failure before any side effect."""

    code: SourceFailureCode
    summary: str


def normalize_for_match(text: str) -> str:
    """Unicode-aware case fold for opt-out and marker matching."""
    return text.casefold()


def message_has_clear_opt_out(text: str) -> bool:
    """True when *text* contains an approved clear non-save phrase."""
    folded = normalize_for_match(text)
    return any(phrase.casefold() in folded for phrase in _OPT_OUT_PHRASES)


def message_is_sole_http_url(text: str) -> bool:
    """True when the entire message is one HTTP(S) URL (not a passive JD)."""
    stripped = text.strip()
    if not stripped or any(ch.isspace() for ch in stripped):
        return False
    folded = stripped.casefold()
    return folded.startswith("http://") or folded.startswith("https://")


def _non_whitespace_char_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _non_empty_line_count(text: str) -> int:
    # splitlines handles LF / CRLF / CR without inventing empty trailing lines.
    return sum(1 for line in text.splitlines() if line.strip() != "")


def _distinct_marker_count(text: str) -> int:
    folded = normalize_for_match(text)
    return sum(1 for marker in _JD_MARKERS if marker.casefold() in folded)


def message_is_large_text(text: str) -> bool:
    """True when *text* meets the coarse large-message reconsideration gate.

    Counts non-whitespace characters only. Not a JD classifier: does not use
    line count, exact phrases, or marker diversity as a semantic decision.
    """
    return _non_whitespace_char_count(text) >= OBVIOUS_JD_MIN_NON_WS_CHARS


def message_is_obvious_jd(text: str) -> bool:
    """True when *text* meets the fixed obvious structured-JD thresholds.

    ponytail: this heuristic is a narrow fallback for clearly structured
    local-demo JDs only (ceilings: 300 non-whitespace chars, 5 non-empty lines,
    2 distinct fixed markers). Acceptable while measured false positives/
    negatives stay immaterial for local demos; if they remain material, replace
    with a typed composer intent in a future approved increment instead of
    expanding the marker keyword list.
    """
    if not message_is_large_text(text):
        return False
    if _non_empty_line_count(text) < OBVIOUS_JD_MIN_NON_EMPTY_LINES:
        return False
    if _distinct_marker_count(text) < OBVIOUS_JD_MIN_DISTINCT_MARKERS:
        return False
    return True


async def resolve_initiating_user_message(
    session: AsyncSession,
    run_id: str,
) -> InitiatingMessage | SourceLookupFailure:
    """Resolve ``run_id → user_message_id → chat_messages`` in one short read.

    Uses existing repositories only (no wrappers). Returns exact content for
    the tool caller; never accepts a caller-supplied message ID.
    """
    if not isinstance(run_id, str) or run_id.strip() == "":
        return SourceLookupFailure(
            code=ERROR_CURRENT_MESSAGE_NOT_FOUND,
            summary="initiating message could not be resolved",
        )

    run = await runs_repo.get_run(session, run_id.strip())
    if run is None:
        return SourceLookupFailure(
            code=ERROR_CURRENT_MESSAGE_NOT_FOUND,
            summary="initiating message could not be resolved",
        )

    user_message_id = run.user_message_id
    if not isinstance(user_message_id, str) or user_message_id.strip() == "":
        return SourceLookupFailure(
            code=ERROR_CURRENT_MESSAGE_NOT_FOUND,
            summary="initiating message could not be resolved",
        )

    message = await messages_repo.get_by_id(session, user_message_id.strip())
    if message is None:
        return SourceLookupFailure(
            code=ERROR_CURRENT_MESSAGE_NOT_FOUND,
            summary="initiating message could not be resolved",
        )

    if message.role != CHAT_MESSAGE_ROLE_USER:
        return SourceLookupFailure(
            code=ERROR_INVALID_CURRENT_MESSAGE,
            summary="initiating message is not a valid user message",
        )
    if message.conversation_id != CONVERSATION_ID:
        return SourceLookupFailure(
            code=ERROR_INVALID_CURRENT_MESSAGE,
            summary="initiating message is not a valid user message",
        )
    content = message.content
    if not isinstance(content, str) or content.strip() == "":
        return SourceLookupFailure(
            code=ERROR_INVALID_CURRENT_MESSAGE,
            summary="initiating message is not a valid user message",
        )

    return InitiatingMessage(content=content)


def build_job_save_confirmation_projection(
    *,
    tool_call_id: str,
    content: str,
    preview: SaveJobPreview | None = None,
) -> dict[str, Any]:
    """Strict bounded pending/SSE projection (no raw JD, IDs, URLs, secrets)."""
    if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
        raise ValueError("tool_call_id must be a non-empty string")
    if not isinstance(content, str):
        raise ValueError("content must be a string")

    preview_payload: dict[str, Any]
    if preview is None:
        preview_payload = {"title": None, "company": None, "skills": []}
    else:
        preview_payload = {
            "title": preview.title,
            "company": preview.company,
            "skills": list(preview.skills),
        }

    return {
        "kind": JOB_SAVE_CONFIRMATION_KIND,
        "allowed_actions": list(JOB_SAVE_CONFIRMATION_ACTIONS),
        "card": {
            "tool_name": SAVE_JOB_TOOL_NAME,
            "tool_call_id": tool_call_id.strip(),
            "source": SAVE_JOB_SOURCE_CURRENT_MESSAGE,
            "text_length": min(len(content), TEXT_LENGTH_CAP),
            "preview": preview_payload,
        },
    }


def build_cancellation_tool_result() -> ToolResult:
    """Successful no-mutation cancel ToolResult (not a saved-Job outcome)."""
    data = SaveJobCancellationData(
        committed=False,
        outcome=SAVE_JOB_CANCEL_OUTCOME,
    )
    return ToolResult(
        ok=True,
        code=None,
        summary=CANCEL_SUMMARY,
        data=data.model_dump(mode="json"),
    )


__all__ = [
    "CANCEL_SUMMARY",
    "ERROR_CURRENT_MESSAGE_NOT_FOUND",
    "ERROR_INVALID_CURRENT_MESSAGE",
    "InitiatingMessage",
    "JOB_SAVE_CONFIRMATION_ACTIONS",
    "JOB_SAVE_CONFIRMATION_KIND",
    "OBVIOUS_JD_MIN_DISTINCT_MARKERS",
    "OBVIOUS_JD_MIN_NON_EMPTY_LINES",
    "OBVIOUS_JD_MIN_NON_WS_CHARS",
    "SAVE_JOB_TOOL_NAME",
    "SourceLookupFailure",
    "TEXT_LENGTH_CAP",
    "build_cancellation_tool_result",
    "build_job_save_confirmation_projection",
    "message_has_clear_opt_out",
    "message_is_large_text",
    "message_is_obvious_jd",
    "message_is_sole_http_url",
    "normalize_for_match",
    "resolve_initiating_user_message",
]

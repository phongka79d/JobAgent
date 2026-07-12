"""Application-owned profile approval authorization and resume parsing.

Commit authorization is never derived from LLM-controlled tool arguments alone.
The graph stages a pending draft id into the interrupt payload; only an approve
resume for the matching run/draft may inject ``approval_authorization`` so
``commit_profile_draft`` can run. Display summaries are separate from auth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal
from uuid import UUID

from langchain_core.messages import AIMessage

APPROVAL_KIND_PROFILE_DRAFT: Final[str] = "profile_draft"
APPROVAL_ACTION_COMMIT: Final[str] = "commit"

# Display-only keys allowed on the public approval summary path.
_PROFILE_DISPLAY_KEYS: Final[frozenset[str]] = frozenset(
    {
        "summary",
        "current_title",
        "skill_names",
        "experience_count",
        "education_count",
        "has_preference_changes",
        "target_roles_preview",
        "approval_kind",
        "kind",
    }
)

# Internal keys kept on the interrupt/checkpoint payload only (never SSE).
_PROFILE_INTERNAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "draft_id",
        "run_id",
        "action",
        "resume_idempotency_key",
        "authorized_action",
    }
)

_MAX_DISPLAY_LIST: Final[int] = 20
_MAX_DISPLAY_ITEM_LEN: Final[int] = 128
_MAX_SUMMARY_LEN: Final[int] = 512


@dataclass(frozen=True, slots=True)
class ResumeCommand:
    """Normalized application resume value for approve or correct."""

    action: Literal["approve", "correct"]
    correction_text: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileCommitAuthorization:
    """Application-owned one-shot commit grant (not LLM-manufactured)."""

    run_id: str
    draft_id: str
    resume_idempotency_key: str
    action: Literal["commit"] = "commit"

    def to_state_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "draft_id": self.draft_id,
            "resume_idempotency_key": self.resume_idempotency_key,
            "action": self.action,
        }


def parse_resume_command(value: Any) -> ResumeCommand:
    """Map LangGraph ``Command(resume=...)`` values to approve/correct."""
    if value is True or value is False:
        return ResumeCommand(action="approve")
    if isinstance(value, str):
        # Legacy/simple resumes (string tokens) mean approve.
        return ResumeCommand(action="approve")
    if isinstance(value, Mapping):
        raw_action = str(value.get("action") or "approve").strip().lower()
        key_raw = value.get("idempotency_key")
        key = (
            str(key_raw).strip()[:128]
            if isinstance(key_raw, str) and key_raw.strip()
            else None
        )
        if raw_action == "correct":
            text_raw = value.get("text")
            if text_raw is None:
                text_raw = value.get("correction_text")
            text = str(text_raw).strip() if text_raw is not None else ""
            if not text:
                # Invalid correction degrades to a no-op approve refusal path
                # handled by the graph (no draft commit, no silent success).
                return ResumeCommand(action="correct", correction_text=None, idempotency_key=key)
            return ResumeCommand(
                action="correct",
                correction_text=text[:32_768],
                idempotency_key=key,
            )
        return ResumeCommand(action="approve", idempotency_key=key)
    return ResumeCommand(action="approve")


def enrich_resume_value(resume_value: Any, *, resume_idempotency_key: str) -> Any:
    """Attach the application resume key so commit auth cannot be LLM-forged."""
    key = resume_idempotency_key.strip()
    if not key:
        return resume_value
    if resume_value is True or resume_value is False:
        return {"action": "approve", "idempotency_key": key}
    if isinstance(resume_value, str):
        return {"action": "approve", "idempotency_key": key}
    if isinstance(resume_value, Mapping):
        out = dict(resume_value)
        out["idempotency_key"] = key
        if "action" not in out:
            if out.get("text") or out.get("correction_text"):
                out["action"] = "correct"
            else:
                out["action"] = "approve"
        return out
    return {"action": "approve", "idempotency_key": key}


def extract_draft_id(payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("draft_id")
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    try:
        return str(UUID(cleaned))
    except (ValueError, AttributeError, TypeError):
        # Keep opaque non-UUID ids only when non-empty and bounded.
        return cleaned[:128] if len(cleaned) <= 128 else None


def build_commit_authorization(
    *,
    run_id: str,
    draft_id: str,
    resume_idempotency_key: str | None,
) -> dict[str, str]:
    key = (resume_idempotency_key or "").strip() or f"approve-{run_id}"
    return ProfileCommitAuthorization(
        run_id=str(run_id),
        draft_id=str(draft_id),
        resume_idempotency_key=key[:128],
    ).to_state_dict()


def build_commit_tool_message(
    *,
    draft_id: str,
    idempotency_key: str,
    run_id: str,
) -> AIMessage:
    """Application-owned tool call: one guarded commit after approve resume."""
    call_id = f"commit_{str(run_id).replace('-', '')[:16]}"
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "commit_profile_draft",
                "args": {
                    "draft_id": draft_id,
                    "idempotency_key": idempotency_key,
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def profile_display_summary(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Bounded display fields only — no draft/run auth tokens."""
    if not isinstance(payload, Mapping):
        return {
            "summary": "Approval required to continue",
            "approval_kind": APPROVAL_KIND_PROFILE_DRAFT,
        }
    out: dict[str, Any] = {}
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip():
        out["summary"] = " ".join(summary.strip().split())[:_MAX_SUMMARY_LEN]
    else:
        out["summary"] = "Approval required to continue"

    title = payload.get("current_title")
    if isinstance(title, str) and title.strip():
        out["current_title"] = title.strip()[:128]

    skills = _string_list(payload.get("skill_names"))
    if skills:
        out["skill_names"] = skills

    roles = _string_list(payload.get("target_roles_preview"))
    if roles:
        out["target_roles_preview"] = roles

    for count_key in ("experience_count", "education_count"):
        raw = payload.get(count_key)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            out[count_key] = raw

    prefs = payload.get("has_preference_changes")
    if isinstance(prefs, bool):
        out["has_preference_changes"] = prefs

    kind = payload.get("approval_kind") or payload.get("kind")
    has_profile_fields = any(
        key in out
        for key in (
            "current_title",
            "skill_names",
            "target_roles_preview",
            "experience_count",
            "education_count",
            "has_preference_changes",
        )
    ) or (
        isinstance(payload.get("approval_kind"), str)
        and payload.get("approval_kind", "").strip().lower().replace("-", "_")
        == APPROVAL_KIND_PROFILE_DRAFT
    )
    if has_profile_fields:
        out["approval_kind"] = APPROVAL_KIND_PROFILE_DRAFT
    elif isinstance(kind, str) and kind.strip():
        cleaned = kind.strip().lower().replace("-", "_").replace(" ", "_")[:64]
        out["approval_kind"] = cleaned
    else:
        out["approval_kind"] = "approval_required"

    return out


def sanitize_profile_approval_fields(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Sanitize interrupt payload: display fields + internal draft/run only."""
    out: dict[str, Any] = {"kind": "approval_required"}
    if not isinstance(payload, Mapping):
        return out

    for key, item in payload.items():
        if not isinstance(key, str) or not key:
            continue
        safe_key = key[:64]
        if safe_key not in _PROFILE_DISPLAY_KEYS and safe_key not in _PROFILE_INTERNAL_KEYS:
            # Preserve generic short scalars used by non-profile interrupts.
            if isinstance(item, bool) or item is None:
                out[safe_key] = item
            elif isinstance(item, int) and not isinstance(item, bool):
                out[safe_key] = item
            elif isinstance(item, float):
                out[safe_key] = item
            elif isinstance(item, str) and len(item) <= _MAX_SUMMARY_LEN:
                out[safe_key] = item
            continue

        if safe_key == "kind" and isinstance(item, str) and item.strip():
            out["kind"] = item.strip()[:64]
            continue
        if safe_key == "approval_kind" and isinstance(item, str) and item.strip():
            out["approval_kind"] = item.strip().lower().replace("-", "_")[:64]
            continue
        if safe_key in {"draft_id", "run_id", "resume_idempotency_key", "action", "authorized_action"}:
            if isinstance(item, str) and item.strip() and len(item) <= 128:
                out[safe_key] = item.strip()
            continue
        if safe_key == "summary" and isinstance(item, str) and item.strip():
            out["summary"] = item.strip()[:_MAX_SUMMARY_LEN]
            continue
        if safe_key == "current_title" and isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out["current_title"] = cleaned[:128]
            continue
        if safe_key in {"skill_names", "target_roles_preview"}:
            values = _string_list(item)
            if values:
                out[safe_key] = values
            continue
        if safe_key in {"experience_count", "education_count"}:
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                out[safe_key] = item
            continue
        if safe_key == "has_preference_changes" and isinstance(item, bool):
            out[safe_key] = item
            continue

    if "kind" not in out:
        out["kind"] = "approval_required"
    return out


def authorization_matches(
    auth: Mapping[str, Any] | None,
    *,
    draft_id: UUID | str,
    idempotency_key: str,
    run_id: str | None = None,
) -> bool:
    """True only when application grant matches the tool invocation."""
    if not isinstance(auth, Mapping):
        return False
    if str(auth.get("action") or "") != APPROVAL_ACTION_COMMIT:
        return False
    auth_draft = str(auth.get("draft_id") or "").strip()
    if not auth_draft or auth_draft != str(draft_id).strip():
        return False
    auth_key = str(auth.get("resume_idempotency_key") or "").strip()
    if not auth_key or auth_key != str(idempotency_key).strip():
        return False
    if run_id is not None:
        auth_run = str(auth.get("run_id") or "").strip()
        if auth_run and auth_run != str(run_id).strip():
            return False
    return True


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.strip().split())
        if not cleaned:
            continue
        out.append(cleaned[:_MAX_DISPLAY_ITEM_LEN])
        if len(out) >= _MAX_DISPLAY_LIST:
            break
    return out


__all__ = [
    "APPROVAL_ACTION_COMMIT",
    "APPROVAL_KIND_PROFILE_DRAFT",
    "ProfileCommitAuthorization",
    "ResumeCommand",
    "authorization_matches",
    "build_commit_authorization",
    "build_commit_tool_message",
    "enrich_resume_value",
    "extract_draft_id",
    "parse_resume_command",
    "profile_display_summary",
    "sanitize_profile_approval_fields",
]

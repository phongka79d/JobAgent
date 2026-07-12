"""Bounded ``save_job`` Agent tool with application-owned ``force_new`` auth.

Validates exactly one URL or raw-text input plus optional ``force_new``.
``force_new`` is authorized only from the current user turn in InjectedState
after excluding the exact URL/raw-JD payload. Document/tool argument text alone
never authorizes an override. Unauthorized overrides fail before service
mutation. Successful authorized overrides surface one allowlisted audit token
for durable tool observability (never the user turn or JD body).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Protocol

from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.job_tools import SaveJobResult
from app.services.jd_ingestion import JdIngestionError

# Exactly one allowlisted durable tool-summary token for authorized overrides.
FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN: Final[str] = "force_new_authorized"

# Explicit current-turn declarations only (not synonyms, not LLM Boolean alone).
_FORCE_NEW_DECLARATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:separate|distinct)\s+position\b",
    re.IGNORECASE,
)


class SaveJobInput(BaseModel):
    """Strict LLM-visible args (InjectedState is not part of this schema)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str | None = Field(default=None, max_length=2048)
    raw_text: str | None = Field(default=None, max_length=32_768)
    force_new: bool = False

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SaveJobInput:
        url = self.url.strip() if isinstance(self.url, str) else None
        raw = self.raw_text.strip() if isinstance(self.raw_text, str) else None
        has_url = bool(url)
        has_raw = bool(raw)
        if has_url == has_raw:
            # neither or both — fail closed before any service call
            raise ValueError("exactly one of url or raw_text required")
        # Normalize blanks to None after strip.
        object.__setattr__(self, "url", url if has_url else None)
        object.__setattr__(self, "raw_text", raw if has_raw else None)
        if not isinstance(self.force_new, bool):
            raise ValueError("force_new must be a boolean")
        return self


class JdIngestionPort(Protocol):
    async def save_job(
        self,
        *,
        url: str | None = None,
        raw_text: str | None = None,
        force_new_authorized: bool = False,
    ) -> SaveJobResult: ...


def _error(code: str) -> str:
    return f'ERROR:{{"code":"{code}","ok":false}}'


def _latest_user_turn_text(state: Mapping[str, Any] | None) -> str:
    """Read the current-turn user text from application Agent state only."""
    if not isinstance(state, Mapping):
        return ""
    messages = state.get("messages_for_this_turn") or ()
    if not isinstance(messages, Sequence):
        return ""
    for item in reversed(list(messages)):
        if isinstance(item, HumanMessage):
            content = item.content
            return content if isinstance(content, str) else str(content)
        if isinstance(item, Mapping):
            role = str(item.get("role", "")).lower()
            if role in {"user", "human"}:
                content = item.get("content", "")
                return content if isinstance(content, str) else str(content)
    return ""


def _exclude_payload(user_turn: str, payload: str | None) -> str:
    """Remove exact URL/raw-JD payload occurrences from the user turn."""
    if not payload or not user_turn:
        return user_turn
    remainder = user_turn
    # Exact match first, then stripped form if different.
    candidates = [payload]
    stripped = payload.strip()
    if stripped and stripped != payload:
        candidates.append(stripped)
    for piece in candidates:
        if piece and piece in remainder:
            remainder = remainder.replace(piece, " ")
    return remainder


def is_force_new_declared_in_user_turn(
    user_turn: str,
    *,
    url: str | None,
    raw_text: str | None,
) -> bool:
    """True only when declaration appears outside the URL/raw-JD payload.

    Scans the current user turn after excluding the exact tool input payload.
    Never trusts document text alone or tool arguments as authorization.
    """
    if not isinstance(user_turn, str) or not user_turn.strip():
        return False
    remainder = user_turn
    remainder = _exclude_payload(remainder, url)
    remainder = _exclude_payload(remainder, raw_text)
    if not remainder.strip():
        return False
    return _FORCE_NEW_DECLARATION_RE.search(remainder) is not None


class SaveJobToolService:
    """Thin authorization + validation wrapper over JD ingestion."""

    def __init__(self, ingestion: JdIngestionPort) -> None:
        self._ingestion = ingestion

    async def execute(
        self,
        *,
        url: str | None,
        raw_text: str | None,
        force_new: bool,
        state: Mapping[str, Any] | None,
    ) -> str:
        # Optional override: require application-owned current-turn evidence.
        force_new_authorized = False
        if force_new:
            user_turn = _latest_user_turn_text(state)
            if not is_force_new_declared_in_user_turn(
                user_turn,
                url=url,
                raw_text=raw_text,
            ):
                # Fail closed before any service mutation.
                return _error("FORCE_NEW_UNAUTHORIZED")
            force_new_authorized = True

        try:
            result = await self._ingestion.save_job(
                url=url,
                raw_text=raw_text,
                force_new_authorized=force_new_authorized,
            )
        except JdIngestionError as exc:
            return _error(exc.code)
        except Exception:
            return _error("SAVE_JOB_FAILED")

        if not isinstance(result, SaveJobResult):
            return _error("SAVE_JOB_FAILED")

        payload = result.model_dump(mode="json")
        payload["ok"] = True
        if force_new_authorized:
            # One allowlisted audit token only — never the user turn or JD.
            payload["authorization_audit"] = FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def create_save_job_tool(service: SaveJobToolService) -> StructuredTool:
    """Register ``save_job``; ``force_new`` auth comes from InjectedState only.

    ``args_schema`` is omitted so LangGraph can inject state without failing
    ``extra=forbid`` validation. Public args are re-validated with
    ``SaveJobInput`` inside the coroutine.
    """

    async def _save_job(
        url: str | None = None,
        raw_text: str | None = None,
        force_new: bool = False,
        state: Annotated[dict[str, Any], InjectedState] = None,  # type: ignore[assignment]
    ) -> str:
        try:
            parsed = SaveJobInput(url=url, raw_text=raw_text, force_new=force_new)
        except ValidationError:
            return _error("SAVE_JOB_INVALID_INPUT")
        app_state: Mapping[str, Any] | None = (
            state if isinstance(state, Mapping) else None
        )
        return await service.execute(
            url=parsed.url,
            raw_text=parsed.raw_text,
            force_new=parsed.force_new,
            state=app_state,
        )

    return StructuredTool.from_function(
        coroutine=_save_job,
        name="save_job",
        description=(
            "Save one public job URL or pasted JD text. "
            "Optional force_new requires the user to state this is a separate "
            "or distinct position in the current turn (outside the JD)."
        ),
    )


__all__ = [
    "FORCE_NEW_AUTHORIZATION_AUDIT_TOKEN",
    "JdIngestionPort",
    "SaveJobInput",
    "SaveJobToolService",
    "create_save_job_tool",
    "is_force_new_declared_in_user_turn",
]

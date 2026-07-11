"""Sanitized tool-execution observability repository.

Caller owns the ``AsyncSession`` transaction: methods flush only and never
commit or roll back. Persist only approved identifiers, status, timing, short
sanitized summaries, and error codes — never raw tool arguments, secrets, or
document bodies.
"""

from __future__ import annotations

import re
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import ToolExecutionStatus
from app.db.models.conversation import AgentRun, ToolExecution

_MAX_TOOL_NAME_LEN: Final[int] = 128
_MAX_SUMMARY_LEN: Final[int] = 512
_MAX_ERROR_CODE_LEN: Final[int] = 64
_TOOL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

_PATH_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_AUTH_SCHEME_RE = re.compile(
    r"^(?:Basic|Bearer|Digest|Token|Negotiate|NTLM)\s+\S+",
    re.IGNORECASE,
)
_URI_USERINFO_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#\"']*:[^/\s?#\"']*@",
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?:^|[\s\"'=])(?:password|passwd|secret|token|api[_-]?key|x[_-]?api[_-]?key|"
    r"authorization|access[_-]?key|private[_-]?key|credential|credentials|"
    r"auth[_-]?token|session[_-]?token|auth)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_SECRET_VALUE_MARKERS: tuple[str, ...] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)

# Summary must not smuggle raw argument dumps / secret material categories.
_PROHIBITED_SUMMARY_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "bearer",
        "private_key",
        "storage_path",
        "file_path",
        "raw_document",
        "raw_content",
        "document_bytes",
        "pdf_bytes",
        "cv_text",
        "jd_text",
    }
)


class ToolExecutionRepositoryError(Exception):
    """Tool execution operation failed without disclosing secret values."""


class ToolExecutionNotFoundError(ToolExecutionRepositoryError):
    """No tool execution row exists for the requested identity."""


class ToolExecutionStateError(ToolExecutionRepositoryError):
    """Requested status transition is not allowed for the current row state."""


class ToolExecutionValidationError(ToolExecutionRepositoryError):
    """Identifier, summary, timing, or error code failed closed validation."""


def _string_looks_like_path(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip().strip("\"'")
    lower = stripped.lower()
    if "file:" in lower:
        return True
    if _PATH_DRIVE_RE.match(stripped):
        return True
    if stripped.startswith("\\\\") or stripped.startswith("//"):
        return True
    if stripped.startswith("/"):
        return True
    if stripped.startswith("./") or stripped.startswith("../"):
        return True
    if "\\" in stripped:
        return True
    return False


def _string_looks_like_secret_or_document(value: str) -> bool:
    if len(value) > _MAX_SUMMARY_LEN:
        return True
    stripped = value.strip().strip("\"'")
    if _AUTH_SCHEME_RE.match(stripped):
        return True
    if _URI_USERINFO_RE.search(stripped):
        return True
    if _CREDENTIAL_ASSIGNMENT_RE.search(stripped):
        return True
    upper = value.upper()
    for marker in _SECRET_VALUE_MARKERS:
        if marker in upper:
            return True
    return False


def _summary_contains_prohibited_token(value: str) -> bool:
    lowered = value.lower().replace("-", "_")
    for token in _PROHIBITED_SUMMARY_TOKENS:
        if token in lowered:
            return True
    return False


def sanitize_arguments_summary(summary: str | None) -> str | None:
    """Validate a short human-safe tool arguments summary for storage.

    ``None`` is allowed. Mappings/raw dumps are rejected at the type boundary
    by callers (this accepts only strings). Path/secret/document categories
    fail closed without logging values.
    """
    if summary is None:
        return None
    if not isinstance(summary, str):
        raise ToolExecutionValidationError("invalid arguments_summary")
    cleaned = " ".join(summary.strip().split())
    if not cleaned:
        return None
    if len(cleaned) > _MAX_SUMMARY_LEN:
        raise ToolExecutionValidationError("arguments_summary too large")
    if _string_looks_like_path(cleaned):
        raise ToolExecutionValidationError("filesystem path not permitted")
    if _string_looks_like_secret_or_document(cleaned):
        raise ToolExecutionValidationError("prohibited content category")
    if _summary_contains_prohibited_token(cleaned):
        raise ToolExecutionValidationError("prohibited content category")
    return cleaned


def sanitize_error_code(error_code: str | None) -> str | None:
    """Normalize a short tool error code (UPPER_SNAKE) for durable storage."""
    if error_code is None:
        return None
    if not isinstance(error_code, str):
        raise ToolExecutionValidationError("invalid error_code")
    cleaned = error_code.strip().upper().replace("-", "_").replace(" ", "_")
    if not cleaned:
        return None
    if len(cleaned) > _MAX_ERROR_CODE_LEN:
        cleaned = cleaned[:_MAX_ERROR_CODE_LEN]
    if not _ERROR_CODE_RE.fullmatch(cleaned):
        raise ToolExecutionValidationError("invalid error_code")
    return cleaned


def _validate_tool_name(tool_name: str) -> str:
    if not isinstance(tool_name, str) or not _TOOL_NAME_RE.fullmatch(tool_name):
        raise ToolExecutionValidationError("invalid tool_name")
    if len(tool_name) > _MAX_TOOL_NAME_LEN:
        raise ToolExecutionValidationError("invalid tool_name")
    return tool_name


def _validate_uuid(value: UUID, *, name: str) -> UUID:
    if not isinstance(value, UUID):
        raise ToolExecutionValidationError(f"invalid {name}")
    return value


def _validate_duration_ms(duration_ms: int | None) -> int | None:
    if duration_ms is None:
        return None
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
        raise ToolExecutionValidationError("invalid duration_ms")
    if duration_ms < 0:
        raise ToolExecutionValidationError("invalid duration_ms")
    return duration_ms


class ToolExecutionRepository:
    """Narrow tool-execution observability on a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, execution_id: UUID) -> ToolExecution | None:
        """Load one tool execution by primary key, or None."""
        execution_id = _validate_uuid(execution_id, name="execution_id")
        return await self._session.get(ToolExecution, execution_id)

    async def list_for_run(self, agent_run_id: UUID) -> list[ToolExecution]:
        """Return tool rows for a run in stable chronological order."""
        agent_run_id = _validate_uuid(agent_run_id, name="agent_run_id")
        result = await self._session.execute(
            select(ToolExecution)
            .where(ToolExecution.agent_run_id == agent_run_id)
            .order_by(ToolExecution.created_at.asc(), ToolExecution.id.asc())
        )
        return list(result.scalars().all())

    async def start(
        self,
        *,
        agent_run_id: UUID,
        tool_name: str,
        arguments_summary: str | None = None,
    ) -> ToolExecution:
        """Record tool start with a sanitized summary only. Does not commit.

        Rejects raw argument mappings at the call boundary (summary is str or
        None). Never stores secrets or document bodies.
        """
        agent_run_id = _validate_uuid(agent_run_id, name="agent_run_id")
        safe_name = _validate_tool_name(tool_name)
        safe_summary = sanitize_arguments_summary(arguments_summary)

        run = await self._session.get(AgentRun, agent_run_id)
        if run is None:
            raise ToolExecutionValidationError("agent_run_id not found")

        row = ToolExecution(
            agent_run_id=agent_run_id,
            tool_name=safe_name,
            arguments_summary=safe_summary,
            status=ToolExecutionStatus.STARTED.value,
            duration_ms=None,
            error_code=None,
        )
        self._session.add(row)
        integrity_error: IntegrityError | None = None
        try:
            await self._session.flush()
        except IntegrityError as exc:
            integrity_error = exc
        if integrity_error is not None:
            raise ToolExecutionRepositoryError("tool execution write failed") from None
        return row

    async def finish(
        self,
        execution_id: UUID,
        *,
        duration_ms: int | None = None,
        arguments_summary: str | None = None,
    ) -> ToolExecution:
        """Mark a started execution succeeded with optional timing/summary.

        Does not commit. Rejects transitions from terminal statuses.
        """
        row = await self.get_by_id(execution_id)
        if row is None:
            raise ToolExecutionNotFoundError("tool execution not found")
        if row.status == ToolExecutionStatus.SUCCEEDED.value:
            # Replay of finish for the same started row: return without rewrite
            # when already succeeded (same outcome).
            return row
        if row.status != ToolExecutionStatus.STARTED.value:
            raise ToolExecutionStateError("invalid status transition")

        row.status = ToolExecutionStatus.SUCCEEDED.value
        row.duration_ms = _validate_duration_ms(duration_ms)
        row.error_code = None
        if arguments_summary is not None:
            row.arguments_summary = sanitize_arguments_summary(arguments_summary)
        await self._session.flush()
        return row

    async def fail(
        self,
        execution_id: UUID,
        *,
        error_code: str | None = None,
        duration_ms: int | None = None,
    ) -> ToolExecution:
        """Mark a started execution failed with a sanitized error code only.

        Does not commit. Stores codes, not stack traces or raw arguments.
        """
        row = await self.get_by_id(execution_id)
        if row is None:
            raise ToolExecutionNotFoundError("tool execution not found")
        if row.status == ToolExecutionStatus.FAILED.value:
            return row
        if row.status != ToolExecutionStatus.STARTED.value:
            raise ToolExecutionStateError("invalid status transition")

        row.status = ToolExecutionStatus.FAILED.value
        row.error_code = sanitize_error_code(error_code)
        row.duration_ms = _validate_duration_ms(duration_ms)
        await self._session.flush()
        return row

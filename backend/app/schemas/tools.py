"""Validated ``ToolResult`` contract and terminal tool-status coupling.

``ToolResult`` is exactly ``ok``, ``code``, ``summary``, and ``data``. Success
requires ``code=null`` with durable status ``completed`` and no ``error_code``.
Failure requires a stable non-null ``code``, durable status ``failed``, and
matching ``tool_executions.error_code``. Raw document bodies are ordinary JSON
objects only — no special escape type exists.
"""

from __future__ import annotations

from typing import Any

from app.schemas.common import (
    TOOL_STATUS_COMPLETED,
    TOOL_STATUS_FAILED,
    JSONObject,
    StrictModelConfig,
    ToolStatus,
)
from pydantic import BaseModel, Field, model_validator


class ToolResult(BaseModel):
    """Terminal tool execution result stored in ``tool_executions.result_json``."""

    model_config = StrictModelConfig

    ok: bool
    code: str | None = None
    summary: str = Field(min_length=1)
    data: JSONObject | None = None

    @model_validator(mode="after")
    def couple_ok_and_code(self) -> ToolResult:
        """Enforce success/failure coupling on the result object itself."""
        if self.ok:
            if self.code is not None:
                raise ValueError("ok=true requires code=null")
        else:
            if self.code is None or self.code.strip() == "":
                raise ValueError("ok=false requires a stable non-null code")
        return self


def validate_tool_result_terminal_coupling(
    result: ToolResult,
    *,
    status: ToolStatus | str,
    error_code: str | None,
) -> None:
    """Validate result against durable tool status and ``error_code``.

    Raises ``ValueError`` when success/failure coupling is violated. Only
    terminal statuses ``completed`` and ``failed`` are valid for a stored
    terminal result.
    """
    if status == TOOL_STATUS_COMPLETED:
        if not result.ok:
            raise ValueError(
                "status=completed requires ToolResult.ok=true and code=null"
            )
        if error_code is not None:
            raise ValueError(
                "status=completed requires tool_executions.error_code=null"
            )
        if result.code is not None:
            raise ValueError("status=completed requires ToolResult.code=null")
        return

    if status == TOOL_STATUS_FAILED:
        if result.ok:
            raise ValueError(
                "status=failed requires ToolResult.ok=false and a stable code"
            )
        if error_code is None or error_code.strip() == "":
            raise ValueError(
                "status=failed requires non-null tool_executions.error_code"
            )
        if result.code != error_code:
            raise ValueError(
                "ToolResult.code must equal tool_executions.error_code on failure"
            )
        return

    raise ValueError(
        "terminal ToolResult coupling requires status completed|failed; "
        f"got {status!r}"
    )


def parse_tool_result(payload: Any) -> ToolResult:
    """Parse and validate a ``ToolResult`` from arbitrary JSON-like input."""
    return ToolResult.model_validate(payload)

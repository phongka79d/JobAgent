"""Typed, sanitized health response schemas for GET /api/health.

Responses expose only overall/component status and stable failure codes.
They never include credentials, connection strings, filesystem paths,
provider headers, stack traces, or raw exception text.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SAFE_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class OverallStatus(StrEnum):
    """Aggregate process readiness for the Phase 1 foundation."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"


class ComponentState(StrEnum):
    """Per-component probe result."""

    UP = "up"
    DOWN = "down"


class ComponentHealth(BaseModel):
    """Single named dependency probe result."""

    model_config = ConfigDict(extra="forbid")

    status: ComponentState
    code: str | None = Field(
        default=None,
        description="Stable sanitized down-code; null when status is up.",
    )

    @field_validator("code")
    @classmethod
    def _require_safe_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SAFE_CODE_PATTERN.fullmatch(value):
            raise ValueError("invalid health code")
        return value


class HealthResponse(BaseModel):
    """Public health contract: overall plus three foundation components."""

    model_config = ConfigDict(extra="forbid")

    status: OverallStatus
    sqlite: ComponentHealth
    filesystem: ComponentHealth
    neo4j: ComponentHealth


def overall_status(
    sqlite: ComponentHealth,
    filesystem: ComponentHealth,
    neo4j: ComponentHealth,
) -> OverallStatus:
    """Deterministic aggregation: healthy only when every component is up."""
    if (
        sqlite.status is ComponentState.UP
        and filesystem.status is ComponentState.UP
        and neo4j.status is ComponentState.UP
    ):
        return OverallStatus.HEALTHY
    return OverallStatus.DEGRADED

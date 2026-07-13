"""Validated health payload for GET /api/health (Plan 2 §7.7).

Overall and each component use only ``available | unavailable``. Overall is
``available`` if and only if all three components are available.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

ComponentStatus = Literal["available", "unavailable"]


class HealthResponse(BaseModel):
    """Three-component health report with derived overall status."""

    model_config = ConfigDict(extra="forbid")

    overall: ComponentStatus
    sqlite: ComponentStatus
    filesystem: ComponentStatus
    neo4j: ComponentStatus

    @model_validator(mode="after")
    def overall_matches_components(self) -> HealthResponse:
        """Enforce overall available only when every component is available."""
        all_available = (
            self.sqlite == "available"
            and self.filesystem == "available"
            and self.neo4j == "available"
        )
        expected: ComponentStatus = "available" if all_available else "unavailable"
        if self.overall != expected:
            raise ValueError(
                "overall must be available iff sqlite, filesystem, and neo4j "
                "are all available"
            )
        return self


def build_health_response(
    *,
    sqlite: ComponentStatus,
    filesystem: ComponentStatus,
    neo4j: ComponentStatus,
) -> HealthResponse:
    """Build a validated health payload from the three component states."""
    overall: ComponentStatus = (
        "available"
        if sqlite == "available"
        and filesystem == "available"
        and neo4j == "available"
        else "unavailable"
    )
    return HealthResponse(
        overall=overall,
        sqlite=sqlite,
        filesystem=filesystem,
        neo4j=neo4j,
    )

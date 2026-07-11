"""Sanitized Neo4j error codes and health status types.

Public messages expose only stable codes — never credentials, URIs with
credentials, Cypher text, raw driver messages, or stack traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GraphErrorCode(StrEnum):
    """Stable, non-sensitive graph failure codes."""

    UNAVAILABLE = "neo4j_unavailable"
    TIMEOUT = "neo4j_timeout"
    CLOSED = "neo4j_closed"
    QUERY_FAILED = "neo4j_query_failed"
    SCHEMA_FAILED = "neo4j_schema_failed"
    INVALID_DIMENSION = "neo4j_invalid_dimension"


class GraphHealthStatus(StrEnum):
    """Component health status for probes (not overall process health)."""

    UP = "up"
    DOWN = "down"


class GraphError(Exception):
    """Sanitized graph failure (code-only str/repr; no chained secrets)."""

    def __init__(self, code: GraphErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"GraphError(code={self.code.value!r})"


@dataclass(frozen=True, slots=True)
class GraphHealth:
    """Bounded health probe result with optional sanitized down-code."""

    status: GraphHealthStatus
    code: str | None = None


def raise_unavailable() -> None:
    raise GraphError(GraphErrorCode.UNAVAILABLE) from None


def raise_timeout() -> None:
    raise GraphError(GraphErrorCode.TIMEOUT) from None


def raise_closed() -> None:
    raise GraphError(GraphErrorCode.CLOSED) from None


def raise_query_failed() -> None:
    raise GraphError(GraphErrorCode.QUERY_FAILED) from None

"""Focused Neo4j read fakes for matching integration tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ScriptedRead:
    """Rows returned when *query_contains* is present in a read query."""

    query_contains: str
    rows: Sequence[Mapping[str, Any]]


class _ScriptedResult:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        self._rows = [dict(row) for row in rows]

    async def consume(self) -> None:
        return None

    async def data(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]


class _ScriptedSession:
    def __init__(self, driver: ScriptedReadDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _ScriptedSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> _ScriptedResult:
        del kwargs
        params = dict(parameters) if parameters is not None else {}
        self._driver.queries.append(query)
        self._driver.parameters.append(params)
        upper = f" {' '.join(query.upper().split())} "
        if any(token in upper for token in self._driver.write_tokens):
            self._driver.write_queries.append(query)
            raise AssertionError(f"write Cypher is not allowed: {query}")
        if self._driver.failure is not None:
            raise self._driver.failure
        for script in self._driver.scripts:
            if script.query_contains in query:
                return _ScriptedResult(script.rows)
        raise AssertionError(f"unscripted read query: {query}")


class ScriptedReadDriver:
    """Async Neo4j driver fake that only serves scripted read queries."""

    write_tokens: tuple[str, ...] = (
        " MERGE ",
        " CREATE ",
        " DELETE ",
        " DETACH ",
        " SET ",
        " REMOVE ",
        " DROP ",
    )

    def __init__(
        self,
        scripts: Sequence[ScriptedRead],
        *,
        failure: Exception | None = None,
    ) -> None:
        self.scripts = tuple(scripts)
        self.failure = failure
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.write_queries: list[str] = []
        self.session_enter = 0
        self.session_exit = 0

    def session(self, **config: Any) -> _ScriptedSession:
        del config
        return _ScriptedSession(self)


def revision_read_driver(
    *,
    candidates: Sequence[Mapping[str, Any]],
    jobs: Sequence[Mapping[str, Any]],
    failure: Exception | None = None,
) -> ScriptedReadDriver:
    """Build a read fake for the Candidate/Job revision snapshot queries."""
    return ScriptedReadDriver(
        (
            ScriptedRead("MATCH (c:Candidate)", candidates),
            ScriptedRead("MATCH (j:Job)", jobs),
        ),
        failure=failure,
    )


__all__ = [
    "ScriptedRead",
    "ScriptedReadDriver",
    "revision_read_driver",
]

"""Injectable fake Neo4j driver/session for graph unit tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecordedQuery:
    query: str
    parameters: Mapping[str, Any]


class FakeResult:
    async def consume(self) -> None:
        return None


class FakeSession:
    def __init__(self, driver: FakeDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        return None

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> FakeResult:
        params = dict(parameters) if parameters is not None else {}
        self._driver.queries.append(RecordedQuery(query=query, parameters=params))
        if self._driver.run_error is not None:
            raise self._driver.run_error
        if self._driver.run_started is not None:
            self._driver.run_started.set()
        if self._driver.run_gate is not None:
            await self._driver.run_gate.wait()
        if self._driver.run_delay_seconds > 0:
            await asyncio.sleep(self._driver.run_delay_seconds)
        return FakeResult()


@dataclass
class FakeDriver:
    """In-memory driver that records queries and can simulate failures.

    Close semantics: ``closed`` is set only after a successful close. A
    ``close_error`` or cancelled wait on ``close_gate`` must not pre-mark the
    resource closed, so ownership tests can observe abandoned-vs-owned state.
    """

    queries: list[RecordedQuery] = field(default_factory=list)
    verify_calls: int = 0
    close_calls: int = 0
    run_error: BaseException | None = None
    verify_error: BaseException | None = None
    close_error: BaseException | None = None
    verify_delay_seconds: float = 0.0
    run_delay_seconds: float = 0.0
    closed: bool = False
    # Event gates for deterministic concurrency (set before client ops).
    verify_started: asyncio.Event | None = None
    verify_gate: asyncio.Event | None = None
    run_started: asyncio.Event | None = None
    run_gate: asyncio.Event | None = None
    close_started: asyncio.Event | None = None
    close_gate: asyncio.Event | None = None

    def session(self, **kwargs: Any) -> FakeSession:
        return FakeSession(self)

    async def verify_connectivity(self, **kwargs: Any) -> None:
        self.verify_calls += 1
        if self.verify_started is not None:
            self.verify_started.set()
        if self.verify_gate is not None:
            await self.verify_gate.wait()
        if self.verify_delay_seconds > 0:
            await asyncio.sleep(self.verify_delay_seconds)
        if self.verify_error is not None:
            raise self.verify_error

    async def close(self) -> None:
        self.close_calls += 1
        if self.close_started is not None:
            self.close_started.set()
        if self.close_gate is not None:
            await self.close_gate.wait()
        if self.close_error is not None:
            # Do not mark closed before a failed cleanup — ownership tests rely
            # on ``closed`` reflecting successful resource release only.
            raise self.close_error
        self.closed = True

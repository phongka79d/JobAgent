"""Async Neo4j driver lifecycle, bounded health probe, and safe query runner.

Owns connection lifecycle only. Schema DDL lives in ``schema.py``. Failures
surface as sanitized stable codes and never include credentials,
credential-bearing URIs, Cypher with data, or stack traces. Neo4j unavailability
does not touch SQLite or filesystem state.

Create/close ownership lives in ``lifecycle.py`` so concurrent first use,
health deadlines (including construction), and joinable close retry stay
correct without bloating this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, cast, runtime_checkable

from app.config import Settings
from app.graph.errors import (
    GraphError,
    GraphHealth,
    GraphHealthStatus,
    raise_query_failed,
    raise_timeout,
    raise_unavailable,
)
from app.graph.lifecycle import DriverLifecycle

DEFAULT_HEALTH_TIMEOUT_SECONDS: float = 2.0


@runtime_checkable
class GraphResult(Protocol):
    """Minimal async result surface used by the client."""

    async def consume(self) -> Any: ...


@runtime_checkable
class GraphSession(Protocol):
    """Minimal async session surface (real Neo4j session or test fake)."""

    async def run(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> GraphResult: ...

    async def __aenter__(self) -> GraphSession: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None: ...


@runtime_checkable
class GraphDriver(Protocol):
    """Minimal async driver surface (real Neo4j driver or test fake)."""

    def session(self, **kwargs: Any) -> GraphSession: ...

    def verify_connectivity(self, **kwargs: Any) -> Awaitable[None]: ...

    def close(self) -> Awaitable[None]: ...


DriverFactory = Callable[[], GraphDriver]


class Neo4jClient:
    """Lazy async Neo4j client with injectable driver boundary.

    Construction never connects. Drivers are created on first use via the
    injectable factory (tests) or the locked ``neo4j`` async driver (runtime).
    """

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        driver_factory: DriverFactory | None = None,
        health_timeout_seconds: float = DEFAULT_HEALTH_TIMEOUT_SECONDS,
    ) -> None:
        if health_timeout_seconds <= 0:
            raise ValueError("health_timeout_seconds must be positive")
        self._uri = uri
        self._user = user
        self._password = password
        self._driver_factory = driver_factory
        self._health_timeout_seconds = health_timeout_seconds
        self._lifecycle = DriverLifecycle(self._construct_driver_sync)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        driver_factory: DriverFactory | None = None,
        health_timeout_seconds: float = DEFAULT_HEALTH_TIMEOUT_SECONDS,
    ) -> Neo4jClient:
        """Build a client from typed settings without reading root ``.env``."""
        return cls(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password.get_secret_value(),
            driver_factory=driver_factory,
            health_timeout_seconds=health_timeout_seconds,
        )

    def __repr__(self) -> str:
        state = "closed" if self._lifecycle.is_closed else "open"
        connected = self._lifecycle.driver_created
        return (
            f"Neo4jClient(state={state!r}, driver_created={connected!r}, "
            f"health_timeout_seconds={self._health_timeout_seconds!r})"
        )

    __str__ = __repr__

    @property
    def is_closed(self) -> bool:
        return self._lifecycle.is_closed

    @property
    def driver_created(self) -> bool:
        """True while a driver is owned (published or held for close retry)."""
        return self._lifecycle.driver_created

    def _construct_driver_sync(self) -> GraphDriver:
        """Synchronous construction (run off the event loop via to_thread)."""
        if self._driver_factory is not None:
            return self._driver_factory()
        return self._create_default_driver()

    def _create_default_driver(self) -> GraphDriver:
        """Import and construct the locked async driver (lazy; not at import)."""
        import_failed = False
        try:
            from neo4j import AsyncGraphDatabase
        except Exception:
            import_failed = True
        if import_failed:
            raise_unavailable()
            raise AssertionError("unreachable")  # pragma: no cover

        created: GraphDriver | None = None
        create_failed = False
        try:
            # Auth/URI stay inside the driver; never logged by this module.
            created = cast(
                GraphDriver,
                AsyncGraphDatabase.driver(
                    self._uri,
                    auth=(self._user, self._password),
                ),
            )
        except Exception:
            create_failed = True
        if create_failed or created is None:
            raise_unavailable()
            raise AssertionError("unreachable")  # pragma: no cover
        return created

    async def get_driver(self) -> GraphDriver:
        """Return the live driver, creating it lazily on first use."""
        driver = await self._lifecycle.get_driver()
        return cast(GraphDriver, driver)

    async def run_query(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        """Run one parameter-bound query and consume the result.

        Callers must pass static Cypher and bind values through ``parameters``.
        Never interpolate untrusted identifiers or data into ``query``.
        """
        params: Mapping[str, Any] = parameters if parameters is not None else {}
        graph_error: GraphError | None = None
        timed_out = False
        other_failed = False
        try:
            driver = await self.get_driver()
            async with driver.session() as session:
                result = await session.run(query, params)
                await result.consume()
        except GraphError as exc:
            graph_error = exc
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            raise
        except Exception:
            other_failed = True
        if graph_error is not None:
            raise GraphError(graph_error.code) from None
        if timed_out:
            raise_timeout()
        if other_failed:
            raise_query_failed()

    async def fetch_records(
        self,
        query: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run one parameter-bound read query and return bounded row dicts.

        Intended for rebuild parity checks (IDs/counts). Callers must pass
        static Cypher and bind values through ``parameters``. Failures surface
        as sanitized ``GraphError`` codes only — never credentials, URIs, or
        raw driver messages.
        """
        params: Mapping[str, Any] = parameters if parameters is not None else {}
        graph_error: GraphError | None = None
        timed_out = False
        other_failed = False
        rows: list[dict[str, Any]] = []
        try:
            driver = await self.get_driver()
            async with driver.session() as session:
                result = await session.run(query, params)
                rows = await self._materialize_records(result)
        except GraphError as exc:
            graph_error = exc
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            raise
        except Exception:
            other_failed = True
        if graph_error is not None:
            raise GraphError(graph_error.code) from None
        if timed_out:
            raise_timeout()
        if other_failed:
            raise_query_failed()
        return rows

    @staticmethod
    async def _materialize_records(result: Any) -> list[dict[str, Any]]:
        """Extract plain dict rows from a driver result without leaking internals."""
        data_fn = getattr(result, "data", None)
        if callable(data_fn):
            raw = data_fn()
            if asyncio.iscoroutine(raw):
                raw = await raw
            if isinstance(raw, list):
                return [dict(item) for item in raw if isinstance(item, Mapping)]
            return []
        rows: list[dict[str, Any]] = []
        async for record in result:
            if isinstance(record, Mapping):
                rows.append(dict(record))
                continue
            record_data = getattr(record, "data", None)
            if callable(record_data):
                payload = record_data()
                if isinstance(payload, Mapping):
                    rows.append(dict(payload))
        return rows

    async def _connectivity_once(self) -> None:
        """Single connectivity attempt including lazy construction."""
        driver = await self.get_driver()
        await driver.verify_connectivity()

    async def verify_connectivity(self) -> None:
        """Bounded connectivity check; raises sanitized GraphError on failure.

        The deadline covers the complete operation, including first-use
        synchronous driver construction offloaded via ``asyncio.to_thread``.
        """
        graph_error: GraphError | None = None
        timed_out = False
        other_failed = False
        try:
            await asyncio.wait_for(
                self._connectivity_once(),
                timeout=self._health_timeout_seconds,
            )
        except GraphError as exc:
            graph_error = exc
        except TimeoutError:
            timed_out = True
        except asyncio.CancelledError:
            raise
        except Exception:
            other_failed = True
        if graph_error is not None:
            raise GraphError(graph_error.code) from None
        if timed_out:
            raise_timeout()
        if other_failed:
            raise_unavailable()

    async def health(self) -> GraphHealth:
        """Return component health without raising (sanitized codes only)."""
        graph_error: GraphError | None = None
        try:
            await self.verify_connectivity()
        except GraphError as exc:
            graph_error = exc
        if graph_error is not None:
            return GraphHealth(
                status=GraphHealthStatus.DOWN,
                code=graph_error.code.value,
            )
        return GraphHealth(status=GraphHealthStatus.UP, code=None)

    async def close(self) -> None:
        """Close the driver if created. Concurrent/repeated closes join cleanup.

        After close begins, new operations fail closed. Ownership is cleared only
        after successful driver close; failed close keeps the driver for retry.
        Cancelling a waiter does not cancel the shared cleanup task.
        """
        await self._lifecycle.close()

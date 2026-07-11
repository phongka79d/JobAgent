"""Shared async Neo4j driver create/close ownership.

Extracted so ``client.py`` stays focused. Guarantees:
- concurrent first use shares one create task and publishes one driver
- cancelling a waiter does not cancel shared create/close work (shielded)
- sync construction runs in a worker thread so the event loop stays responsive
- every create task has a lifecycle-owned terminal-outcome observer
- failed/cancelled close retains ownership for an explicit join/retry path
- ownership is cleared only after a successful driver close
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from app.graph.errors import GraphError, raise_closed, raise_unavailable


@runtime_checkable
class LifecycleDriver(Protocol):
    def close(self) -> Awaitable[None]: ...


ConstructSync = Callable[[], LifecycleDriver]


class DriverLifecycle:
    """Serialize lazy driver creation and joinable close ownership."""

    def __init__(self, construct_sync: ConstructSync) -> None:
        self._construct_sync = construct_sync
        self._driver: LifecycleDriver | None = None
        self._closed = False
        self._lock = asyncio.Lock()
        self._create_task: asyncio.Task[LifecycleDriver] | None = None
        self._close_task: asyncio.Task[None] | None = None

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def driver_created(self) -> bool:
        return self._driver is not None

    @property
    def driver(self) -> LifecycleDriver | None:
        return self._driver

    @staticmethod
    def _observe_create_task_done(task: asyncio.Task[LifecycleDriver]) -> None:
        """Retrieve create-task terminal outcome so the loop never logs it.

        Lifecycle-owned observer attached to every shared create task. When all
        health/query waiters time out or cancel before a late factory failure,
        this still retrieves the exception so asyncio cannot emit
        ``Task exception was never retrieved``.

        Does not log, re-raise, or surface exception details, URIs, passwords,
        or query data. Concurrent waiters may also retrieve the same outcome;
        double observation is safe. Never retains completed tasks beyond the
        callback invocation.
        """
        try:
            if task.cancelled():
                return
            # Success: returns None. Failure: retrieves exception for the loop.
            task.exception()
        except (asyncio.CancelledError, asyncio.InvalidStateError):
            return
        except Exception:
            # Done callbacks must never raise into the loop exception handler.
            return

    def _spawn_create_task(self) -> asyncio.Task[LifecycleDriver]:
        """Create one shared create task with a terminal-outcome observer."""
        create_task = asyncio.create_task(
            self._build_driver(),
            name="neo4j-create",
        )
        create_task.add_done_callback(self._observe_create_task_done)
        return create_task

    async def get_driver(self) -> LifecycleDriver:
        """Return the live driver, creating it lazily on first use."""
        async with self._lock:
            if self._closed:
                raise_closed()
                raise AssertionError("unreachable")  # pragma: no cover
            if self._driver is not None:
                return self._driver
            if self._create_task is None or self._create_task.done():
                # Drop completed create tasks so failures stay retryable and
                # finished tasks are not retained indefinitely.
                self._create_task = self._spawn_create_task()
            create_task = self._create_task

        graph_error: GraphError | None = None
        other_failed = False
        created: LifecycleDriver | None = None
        try:
            # Shield so waiter cancellation (e.g. health wait_for) cannot cancel
            # the shared create task via Task._fut_waiter and abandon a late
            # thread-built driver. Waiter still receives sanitized mapping.
            created = await asyncio.shield(create_task)
        except GraphError as exc:
            graph_error = exc
        except asyncio.CancelledError:
            raise
        except Exception:
            other_failed = True

        if graph_error is not None:
            raise GraphError(graph_error.code) from None
        if other_failed:
            raise_unavailable()
            raise AssertionError("unreachable")  # pragma: no cover

        async with self._lock:
            if self._closed:
                raise_closed()
                raise AssertionError("unreachable")  # pragma: no cover
            if self._driver is not None:
                return self._driver
            if created is not None:
                self._driver = created
                return created
        raise_unavailable()
        raise AssertionError("unreachable")  # pragma: no cover

    async def _build_driver(self) -> LifecycleDriver:
        """Create one driver, publish ownership, and close late orphans safely."""
        graph_error: GraphError | None = None
        other_failed = False
        created: LifecycleDriver | None = None
        try:
            created = await asyncio.to_thread(self._construct_sync)
        except GraphError as exc:
            graph_error = exc
        except Exception:
            other_failed = True

        if graph_error is not None:
            async with self._lock:
                if self._create_task is asyncio.current_task():
                    self._create_task = None
            raise GraphError(graph_error.code) from None
        if other_failed or created is None:
            async with self._lock:
                if self._create_task is asyncio.current_task():
                    self._create_task = None
            raise_unavailable()
            raise AssertionError("unreachable")  # pragma: no cover

        orphan_to_close: LifecycleDriver | None = None
        kick_close = False
        async with self._lock:
            if self._create_task is asyncio.current_task():
                self._create_task = None
            if self._driver is None:
                self._driver = created
            elif self._driver is not created:
                orphan_to_close = created
            if self._closed:
                close_task = self._close_task
                if close_task is None:
                    kick_close = True
                elif close_task.done():
                    orphan_to_close = self._driver
                    self._driver = None

        if kick_close:
            async with self._lock:
                if self._close_task is None and self._driver is not None:
                    self._close_task = asyncio.create_task(
                        self._run_close(),
                        name="neo4j-close",
                    )

        if orphan_to_close is not None:
            close_failed = False
            try:
                await orphan_to_close.close()
            except Exception:
                close_failed = True
            if close_failed:
                async with self._lock:
                    if self._driver is None:
                        self._driver = orphan_to_close
                    self._closed = True
                    self._close_task = None

        async with self._lock:
            owned = self._driver
        if owned is None:
            raise_closed()
            raise AssertionError("unreachable")  # pragma: no cover
        return owned

    async def _run_close(self) -> None:
        """Close owned driver; clear ownership only after successful close."""
        async with self._lock:
            create_task = self._create_task
        if create_task is not None and not create_task.done():
            try:
                # Join create without allowing this cleanup task's cancellation
                # to cancel create (shield); late drivers must be reaped.
                await asyncio.shield(create_task)
            except Exception:
                pass

        async with self._lock:
            driver = self._driver
            if self._create_task is not None and self._create_task.done():
                self._create_task = None

        if driver is None:
            return

        close_failed = False
        try:
            await driver.close()
        except Exception:
            close_failed = True

        async with self._lock:
            if close_failed:
                self._close_task = None
                return
            if self._driver is driver:
                self._driver = None
            if self._create_task is not None and self._create_task.done():
                self._create_task = None

    async def close(self) -> None:
        """Joinable close: concurrent waiters share one cleanup task."""
        async with self._lock:
            self._closed = True
            if (
                self._driver is None
                and (self._create_task is None or self._create_task.done())
                and (self._close_task is None or self._close_task.done())
            ):
                # Fully idle or already cleaned; ensure create slot is cleared.
                if self._create_task is not None and self._create_task.done():
                    self._create_task = None
                return
            if self._close_task is None or (
                self._close_task.done() and self._driver is not None
            ):
                self._close_task = asyncio.create_task(
                    self._run_close(),
                    name="neo4j-close",
                )
            close_task = self._close_task

        # Shield so cancelling a close waiter cannot cancel shared cleanup.
        await asyncio.shield(close_task)

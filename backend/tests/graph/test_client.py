"""Fake-driver tests for Neo4j client lifecycle, health, and redaction."""

from __future__ import annotations

import asyncio
import gc
import threading
import time
from typing import Any

import pytest
from app.config import Settings
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphErrorCode, GraphHealthStatus
from tests.graph.fakes import FakeDriver

SENTINEL_PASSWORD = "sentinel-neo4j-graph-secret-never-emit"
SENTINEL_URI = "bolt://neo4j:7687"
SENTINEL_USER = "neo4j"


def _settings(**overrides: Any) -> Settings:
    payload: dict[str, Any] = {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://localhost:5173",
        "VITE_API_BASE_URL": "http://localhost:8000",
        "SQLITE_PATH": "/data/jobagent.db",
        "FILES_DIR": "/data/files",
        "NEO4J_URI": SENTINEL_URI,
        "NEO4J_USER": SENTINEL_USER,
        "NEO4J_PASSWORD": SENTINEL_PASSWORD,
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
        "SHOPAIKEY_API_KEY": "sentinel-shopaikey-never-emit",
        "LLM_MODEL": "gpt-4o-mini",
        "LLM_TEMPERATURE": "0.0",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_DIMENSIONS": "1536",
        "MAX_PDF_SIZE_MB": "10",
        "MAX_PDF_PAGES": "10",
        "URL_FETCH_TIMEOUT_SECONDS": "10",
        "URL_MAX_RESPONSE_MB": "5",
        "TOOL_LOOP_LIMIT": "6",
    }
    payload.update(overrides)
    return Settings.model_validate(payload)


def _client_with_driver(
    driver: FakeDriver,
    *,
    health_timeout_seconds: float = 0.2,
) -> Neo4jClient:
    return Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: driver,
        health_timeout_seconds=health_timeout_seconds,
    )


def _assert_sanitized_graph_error(err: GraphError) -> None:
    assert SENTINEL_PASSWORD not in str(err)
    assert SENTINEL_PASSWORD not in repr(err)
    assert SENTINEL_URI not in str(err)
    assert SENTINEL_URI not in repr(err)
    assert err.__cause__ is None
    assert err.__context__ is None


@pytest.mark.asyncio
async def test_lazy_startup_does_not_create_driver_until_use() -> None:
    driver = FakeDriver()
    created: list[FakeDriver] = []

    def factory() -> FakeDriver:
        created.append(driver)
        return driver

    client = Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=factory,
    )
    assert client.driver_created is False
    assert created == []
    await client.verify_connectivity()
    assert client.driver_created is True
    assert created == [driver]
    assert driver.verify_calls == 1


@pytest.mark.asyncio
async def test_from_settings_uses_typed_settings_without_env_file() -> None:
    driver = FakeDriver()
    settings = _settings()
    client = Neo4jClient.from_settings(
        settings,
        driver_factory=lambda: driver,
    )
    await client.verify_connectivity()
    assert driver.verify_calls == 1


@pytest.mark.asyncio
async def test_run_query_passes_parameters_without_interpolation() -> None:
    driver = FakeDriver()
    client = _client_with_driver(driver)
    query = "MERGE (j:Job {id: $id}) SET j.title = $title"
    params = {"id": "job-1", "title": "Engineer"}
    await client.run_query(query, params)
    assert len(driver.queries) == 1
    recorded = driver.queries[0]
    assert recorded.query == query
    assert recorded.parameters == params
    # Cypher text itself must not contain bound values (parameter-safe path).
    assert "Engineer" not in recorded.query
    assert "job-1" not in recorded.query


@pytest.mark.asyncio
async def test_run_query_defaults_empty_parameters() -> None:
    driver = FakeDriver()
    client = _client_with_driver(driver)
    await client.run_query("RETURN 1")
    assert driver.queries[0].parameters == {}


@pytest.mark.asyncio
async def test_health_up_when_connectivity_succeeds() -> None:
    driver = FakeDriver()
    client = _client_with_driver(driver)
    health = await client.health()
    assert health.status is GraphHealthStatus.UP
    assert health.code is None


@pytest.mark.asyncio
async def test_health_down_on_unavailability_with_sanitized_code() -> None:
    driver = FakeDriver(
        verify_error=RuntimeError(
            f"Auth failed for {SENTINEL_USER}:{SENTINEL_PASSWORD} at {SENTINEL_URI}"
        )
    )
    client = _client_with_driver(driver)
    health = await client.health()
    assert health.status is GraphHealthStatus.DOWN
    assert health.code == GraphErrorCode.UNAVAILABLE.value
    rendered = f"{health!r} {health.code}"
    assert SENTINEL_PASSWORD not in rendered
    assert SENTINEL_URI not in rendered


@pytest.mark.asyncio
async def test_verify_connectivity_timeout_is_bounded() -> None:
    driver = FakeDriver(verify_delay_seconds=1.0)
    client = _client_with_driver(driver, health_timeout_seconds=0.05)
    with pytest.raises(GraphError) as exc_info:
        await client.verify_connectivity()
    assert exc_info.value.code is GraphErrorCode.TIMEOUT
    _assert_sanitized_graph_error(exc_info.value)


@pytest.mark.asyncio
async def test_run_query_maps_driver_errors_to_sanitized_code() -> None:
    secret_query = f"CREATE (n {{token: '{SENTINEL_PASSWORD}'}})"
    driver = FakeDriver(
        run_error=RuntimeError(f"failed query={secret_query} uri={SENTINEL_URI}")
    )
    client = _client_with_driver(driver)
    with pytest.raises(GraphError) as exc_info:
        await client.run_query(secret_query, {"token": SENTINEL_PASSWORD})
    err = exc_info.value
    assert err.code is GraphErrorCode.QUERY_FAILED
    _assert_sanitized_graph_error(err)
    assert secret_query not in str(err)


@pytest.mark.asyncio
async def test_driver_factory_failure_is_unavailable_and_redacted() -> None:
    def boom() -> FakeDriver:
        raise ConnectionError(
            f"cannot connect to bolt://{SENTINEL_USER}:{SENTINEL_PASSWORD}@host:7687"
        )

    client = Neo4jClient(
        uri=f"bolt://{SENTINEL_USER}:{SENTINEL_PASSWORD}@host:7687",
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=boom,
    )
    with pytest.raises(GraphError) as exc_info:
        await client.get_driver()
    err = exc_info.value
    assert err.code is GraphErrorCode.UNAVAILABLE
    _assert_sanitized_graph_error(err)


@pytest.mark.asyncio
async def test_close_is_idempotent_and_repeatable() -> None:
    driver = FakeDriver()
    client = _client_with_driver(driver)
    await client.get_driver()
    await client.close()
    await client.close()
    assert driver.close_calls == 1
    assert driver.closed is True
    assert client.is_closed is True
    assert client.driver_created is False
    with pytest.raises(GraphError) as exc_info:
        await client.get_driver()
    assert exc_info.value.code is GraphErrorCode.CLOSED
    _assert_sanitized_graph_error(exc_info.value)


@pytest.mark.asyncio
async def test_close_without_driver_is_safe() -> None:
    client = Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: FakeDriver(),
    )
    await client.close()
    await client.close()
    assert client.is_closed is True


@pytest.mark.asyncio
async def test_close_swallows_driver_close_errors() -> None:
    driver = FakeDriver(close_error=RuntimeError(f"close {SENTINEL_PASSWORD}"))
    client = _client_with_driver(driver)
    await client.get_driver()
    await client.close()
    assert driver.close_calls == 1
    # Failed cleanup must not pre-mark closed or drop ownership.
    assert driver.closed is False
    assert client.is_closed is True
    assert client.driver_created is True
    # Explicit retry path after the transient close error clears.
    driver.close_error = None
    await client.close()
    assert driver.close_calls == 2
    assert driver.closed is True
    assert client.driver_created is False


def test_repr_and_str_never_expose_credentials() -> None:
    client = Neo4jClient(
        uri=f"bolt://{SENTINEL_USER}:{SENTINEL_PASSWORD}@neo4j:7687",
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: FakeDriver(),
    )
    text = f"{client!s} {client!r}"
    assert SENTINEL_PASSWORD not in text
    assert "bolt://" not in text
    assert SENTINEL_USER not in text


def test_graph_error_repr_is_code_only() -> None:
    err = GraphError(GraphErrorCode.UNAVAILABLE)
    assert str(err) == "neo4j_unavailable"
    assert repr(err) == "GraphError(code='neo4j_unavailable')"


@pytest.mark.asyncio
async def test_health_timeout_code_is_stable() -> None:
    driver = FakeDriver(verify_delay_seconds=1.0)
    client = _client_with_driver(driver, health_timeout_seconds=0.05)
    health = await client.health()
    assert health.status is GraphHealthStatus.DOWN
    assert health.code == GraphErrorCode.TIMEOUT.value


def test_invalid_health_timeout_rejected() -> None:
    with pytest.raises(ValueError):
        Neo4jClient(
            uri=SENTINEL_URI,
            user=SENTINEL_USER,
            password=SENTINEL_PASSWORD,
            health_timeout_seconds=0,
        )


@pytest.mark.asyncio
async def test_client_does_not_touch_sqlite_on_failure(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Neo4j failure path must not create/mutate SQLite files."""
    root = tmp_path_factory.mktemp("sqlite_guard")
    db_path = root / "jobagent.db"
    db_path.write_text("canonical-sqlite-marker", encoding="utf-8")
    before = db_path.read_bytes()

    driver = FakeDriver(verify_error=OSError("neo4j down"))
    client = _client_with_driver(driver)
    health = await client.health()
    assert health.status is GraphHealthStatus.DOWN
    assert db_path.read_bytes() == before
    assert list(root.iterdir()) == [db_path]


@pytest.mark.asyncio
async def test_health_deadline_includes_blocking_first_use_factory() -> None:
    """Complete health op must obey deadline including sync factory work."""
    created: list[FakeDriver] = []

    def slow_factory() -> FakeDriver:
        time.sleep(0.12)
        driver = FakeDriver()
        created.append(driver)
        return driver

    client = Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=slow_factory,
        health_timeout_seconds=0.01,
    )
    started = time.perf_counter()
    health = await client.health()
    elapsed = time.perf_counter() - started
    assert health.status is GraphHealthStatus.DOWN
    assert health.code == GraphErrorCode.TIMEOUT.value
    # Must not wait for the full blocking factory sleep.
    assert elapsed < 0.08
    # Late-created driver must become owned; wait for the factory thread.
    deadline = time.perf_counter() + 2.0
    while not created and time.perf_counter() < deadline:
        await asyncio.sleep(0.01)
    assert len(created) == 1
    late = created[0]
    # Publish may land just after timeout; close must reap exactly once.
    deadline = time.perf_counter() + 2.0
    while not client.driver_created and time.perf_counter() < deadline:
        await asyncio.sleep(0.01)
    assert client.driver_created is True
    await client.close()
    assert late.close_calls == 1
    assert late.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_simultaneous_first_use_publishes_exactly_one_driver() -> None:
    created: list[FakeDriver] = []
    call_count = 0

    def counting_factory() -> FakeDriver:
        nonlocal call_count
        call_count += 1
        time.sleep(0.03)
        driver = FakeDriver()
        created.append(driver)
        return driver

    client = Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=counting_factory,
    )
    d1, d2 = await asyncio.gather(client.get_driver(), client.get_driver())
    assert d1 is d2
    assert call_count == 1
    assert len(created) == 1
    assert client.driver_created is True
    await client.close()
    assert created[0].close_calls == 1
    assert created[0].closed is True


@pytest.mark.asyncio
async def test_first_use_close_race_closes_created_driver_once() -> None:
    created: list[FakeDriver] = []
    factory_started = threading.Event()
    factory_release = threading.Event()

    def factory() -> FakeDriver:
        factory_started.set()
        assert factory_release.wait(timeout=5.0)
        driver = FakeDriver()
        created.append(driver)
        return driver

    client = Neo4jClient(
        uri=SENTINEL_URI,
        user=SENTINEL_USER,
        password=SENTINEL_PASSWORD,
        driver_factory=factory,
    )
    get_task = asyncio.create_task(client.get_driver())
    assert await asyncio.to_thread(factory_started.wait, 5.0)
    close_task = asyncio.create_task(client.close())
    # Give close time to mark closed and await the shared create task.
    await asyncio.sleep(0.02)
    factory_release.set()
    results = await asyncio.gather(get_task, close_task, return_exceptions=True)
    assert len(created) == 1
    assert any(
        isinstance(r, GraphError) and r.code is GraphErrorCode.CLOSED for r in results
    )
    # Close task should complete without error.
    assert not any(
        isinstance(r, BaseException)
        and not isinstance(r, GraphError)
        for r in results
        if r is not None
    ) or any(r is None for r in results)
    assert created[0].close_calls == 1
    assert created[0].closed is True
    assert client.driver_created is False
    assert client.is_closed is True


@pytest.mark.asyncio
async def test_query_close_race_does_not_abandon_driver() -> None:
    run_started = asyncio.Event()
    run_gate = asyncio.Event()
    driver = FakeDriver(run_started=run_started, run_gate=run_gate)
    client = _client_with_driver(driver)
    query_task = asyncio.create_task(client.run_query("RETURN 1"))
    await run_started.wait()
    close_task = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    run_gate.set()
    await asyncio.gather(query_task, close_task)
    assert driver.close_calls == 1
    assert driver.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_health_close_race_does_not_abandon_driver() -> None:
    verify_started = asyncio.Event()
    verify_gate = asyncio.Event()
    driver = FakeDriver(verify_started=verify_started, verify_gate=verify_gate)
    client = _client_with_driver(driver, health_timeout_seconds=2.0)
    health_task = asyncio.create_task(client.health())
    await verify_started.wait()
    close_task = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    verify_gate.set()
    health, _ = await asyncio.gather(health_task, close_task)
    assert health.status in {GraphHealthStatus.UP, GraphHealthStatus.DOWN}
    assert driver.close_calls == 1
    assert driver.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_two_concurrent_closes_join_same_cleanup() -> None:
    close_started = asyncio.Event()
    close_gate = asyncio.Event()
    driver = FakeDriver(close_started=close_started, close_gate=close_gate)
    client = _client_with_driver(driver)
    await client.get_driver()
    c1 = asyncio.create_task(client.close())
    await close_started.wait()
    c2 = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    close_gate.set()
    await asyncio.gather(c1, c2)
    assert driver.close_calls == 1
    assert driver.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_close_exception_retains_ownership_for_retry() -> None:
    driver = FakeDriver(
        close_error=RuntimeError(f"boom {SENTINEL_PASSWORD} {SENTINEL_URI}")
    )
    client = _client_with_driver(driver)
    await client.get_driver()
    await client.close()
    assert client.is_closed is True
    assert client.driver_created is True
    assert driver.closed is False
    assert driver.close_calls == 1
    driver.close_error = None
    await client.close()
    assert driver.close_calls == 2
    assert driver.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_close_cancellation_joins_or_retains_cleanup() -> None:
    close_started = asyncio.Event()
    close_gate = asyncio.Event()
    driver = FakeDriver(close_started=close_started, close_gate=close_gate)
    client = _client_with_driver(driver)
    await client.get_driver()
    close_task = asyncio.create_task(client.close())
    await close_started.wait()
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    # Cancelling the waiter must not abandon the resource.
    assert client.is_closed is True
    assert driver.closed is False
    assert client.driver_created is True
    assert driver.close_calls == 1
    close_gate.set()
    # Join path: second close awaits the same shared cleanup task.
    await client.close()
    assert driver.close_calls == 1
    assert driver.closed is True
    assert client.driver_created is False


@pytest.mark.asyncio
async def test_timeout_errors_are_fully_sanitized() -> None:
    driver = FakeDriver(verify_delay_seconds=1.0)
    client = _client_with_driver(driver, health_timeout_seconds=0.02)
    with pytest.raises(GraphError) as exc_info:
        await client.verify_connectivity()
    _assert_sanitized_graph_error(exc_info.value)
    assert exc_info.value.code is GraphErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_late_failing_factory_after_health_timeout_is_observed() -> None:
    """Lifecycle owns create-task outcomes after all waiters time out.

    Delayed factory failure must not emit ``Task exception was never retrieved``
    (or any loop exception context). Creation remains retryable; a later success
    closes exactly once. Health stays sanitized (code-only, no secrets).
    """
    contexts: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def capture(
        _loop: asyncio.AbstractEventLoop,
        context: dict[str, object],
    ) -> None:
        contexts.append(context)

    loop.set_exception_handler(capture)
    try:
        calls = 0
        created: list[FakeDriver] = []

        def factory() -> FakeDriver:
            nonlocal calls
            calls += 1
            if calls == 1:
                time.sleep(0.12)
                raise ConnectionError(
                    f"cannot connect {SENTINEL_PASSWORD} at {SENTINEL_URI}"
                )
            driver = FakeDriver()
            created.append(driver)
            return driver

        client = Neo4jClient(
            uri=SENTINEL_URI,
            user=SENTINEL_USER,
            password=SENTINEL_PASSWORD,
            driver_factory=factory,
            health_timeout_seconds=0.02,
        )
        health = await client.health()
        assert health.status is GraphHealthStatus.DOWN
        assert health.code == GraphErrorCode.TIMEOUT.value
        rendered = f"{health!r} {health.code}"
        assert SENTINEL_PASSWORD not in rendered
        assert SENTINEL_URI not in rendered

        # Wait for the delayed factory thread and create-task completion.
        deadline = time.perf_counter() + 2.0
        while calls < 1 and time.perf_counter() < deadline:
            await asyncio.sleep(0.01)
        assert calls == 1
        await asyncio.sleep(0.05)
        gc.collect()
        await asyncio.sleep(0.05)

        # Zero loop exception contexts after task completion and GC.
        assert contexts == []
        assert client.driver_created is False
        assert client.is_closed is False

        # Failed create left lifecycle retryable; later create succeeds once.
        got = await client.get_driver()
        assert calls == 2
        assert len(created) == 1
        assert got is created[0]
        assert client.driver_created is True
        await client.close()
        assert created[0].close_calls == 1
        assert created[0].closed is True
        assert client.driver_created is False
        assert client.is_closed is True
        # Still no loop contexts from the successful retry/close path.
        assert contexts == []
    finally:
        loop.set_exception_handler(previous_handler)

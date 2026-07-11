"""Sanitized GET /api/health route and bounded component probes.

Probe orchestration lives here and stays separate from database, filesystem,
and Neo4j client modules. Failures surface only as stable status/code values.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db.session import DatabaseSessionManager
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphHealthStatus
from app.graph.schema import ensure_graph_schema
from app.schemas.health import (
    ComponentHealth,
    ComponentState,
    HealthResponse,
    overall_status,
)

router = APIRouter(tags=["health"])

DEFAULT_PROBE_TIMEOUT_SECONDS: Final[float] = 2.0

# Stable sanitized component failure codes (never paths, URIs, or secrets).
SQLITE_UNAVAILABLE: Final[str] = "sqlite_unavailable"
SQLITE_TIMEOUT: Final[str] = "sqlite_timeout"
FILESYSTEM_UNAVAILABLE: Final[str] = "filesystem_unavailable"
FILESYSTEM_TIMEOUT: Final[str] = "filesystem_timeout"
NEO4J_UNAVAILABLE: Final[str] = "neo4j_unavailable"
NEO4J_TIMEOUT: Final[str] = "neo4j_timeout"


async def probe_sqlite(
    db: DatabaseSessionManager,
    *,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> ComponentHealth:
    """Bounded SQLite connectivity probe (SELECT 1)."""

    async def _check() -> None:
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    timed_out = False
    failed = False
    try:
        await asyncio.wait_for(_check(), timeout=timeout_seconds)
    except TimeoutError:
        timed_out = True
    except asyncio.CancelledError:
        raise
    except Exception:
        failed = True
    if timed_out:
        return ComponentHealth(status=ComponentState.DOWN, code=SQLITE_TIMEOUT)
    if failed:
        return ComponentHealth(status=ComponentState.DOWN, code=SQLITE_UNAVAILABLE)
    return ComponentHealth(status=ComponentState.UP, code=None)


async def probe_filesystem(
    files_dir: Path,
    *,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> ComponentHealth:
    """Bounded writable-storage probe under the configured FILES_DIR root."""

    async def _check() -> None:
        def _sync_probe() -> None:
            root = files_dir.expanduser()
            root.mkdir(parents=True, exist_ok=True)
            resolved_root = root.resolve(strict=False)
            if not resolved_root.is_dir():
                raise OSError("not a directory")
            name = f".health_probe_{uuid4().hex}"
            probe = resolved_root / name
            # Containment: resolved probe must remain under the storage root.
            if probe.resolve(strict=False).parent != resolved_root:
                raise OSError("escape")
            probe.write_bytes(b"ok")
            try:
                if probe.read_bytes() != b"ok":
                    raise OSError("readback differs")
            finally:
                if probe.exists():
                    probe.unlink()

        await asyncio.to_thread(_sync_probe)

    timed_out = False
    failed = False
    try:
        await asyncio.wait_for(_check(), timeout=timeout_seconds)
    except TimeoutError:
        timed_out = True
    except asyncio.CancelledError:
        raise
    except Exception:
        failed = True
    if timed_out:
        return ComponentHealth(status=ComponentState.DOWN, code=FILESYSTEM_TIMEOUT)
    if failed:
        return ComponentHealth(status=ComponentState.DOWN, code=FILESYSTEM_UNAVAILABLE)
    return ComponentHealth(status=ComponentState.UP, code=None)


async def probe_neo4j(
    client: Neo4jClient,
    *,
    embedding_dimensions: int,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    check_schema: bool = True,
) -> ComponentHealth:
    """Bounded Neo4j connectivity (and optional idempotent schema) probe."""

    async def _check() -> ComponentHealth:
        health = await client.health()
        if health.status is GraphHealthStatus.DOWN:
            code = health.code if health.code is not None else NEO4J_UNAVAILABLE
            return ComponentHealth(status=ComponentState.DOWN, code=code)
        if check_schema:
            await ensure_graph_schema(
                client,
                embedding_dimensions=embedding_dimensions,
            )
        return ComponentHealth(status=ComponentState.UP, code=None)

    timed_out = False
    graph_error: GraphError | None = None
    failed = False
    result: ComponentHealth | None = None
    try:
        result = await asyncio.wait_for(_check(), timeout=timeout_seconds)
    except TimeoutError:
        timed_out = True
    except GraphError as exc:
        graph_error = exc
    except asyncio.CancelledError:
        raise
    except Exception:
        failed = True
    if timed_out:
        return ComponentHealth(status=ComponentState.DOWN, code=NEO4J_TIMEOUT)
    if graph_error is not None:
        return ComponentHealth(
            status=ComponentState.DOWN,
            code=graph_error.code.value,
        )
    if failed or result is None:
        return ComponentHealth(status=ComponentState.DOWN, code=NEO4J_UNAVAILABLE)
    return result


async def collect_health(
    *,
    db: DatabaseSessionManager,
    files_dir: Path,
    neo4j: Neo4jClient,
    embedding_dimensions: int,
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
) -> HealthResponse:
    """Run all component probes concurrently and aggregate overall status."""
    sqlite_h, filesystem_h, neo4j_h = await asyncio.gather(
        probe_sqlite(db, timeout_seconds=timeout_seconds),
        probe_filesystem(files_dir, timeout_seconds=timeout_seconds),
        probe_neo4j(
            neo4j,
            embedding_dimensions=embedding_dimensions,
            timeout_seconds=timeout_seconds,
        ),
    )
    return HealthResponse(
        status=overall_status(sqlite_h, filesystem_h, neo4j_h),
        sqlite=sqlite_h,
        filesystem=filesystem_h,
        neo4j=neo4j_h,
    )


@router.get("/api/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Return overall and per-component health without secret-bearing fields."""
    db: DatabaseSessionManager = request.app.state.db
    files_dir: Path = request.app.state.files_dir
    neo4j: Neo4jClient = request.app.state.neo4j
    embedding_dimensions: int = request.app.state.embedding_dimensions
    timeout_seconds: float = request.app.state.probe_timeout_seconds
    return await collect_health(
        db=db,
        files_dir=files_dir,
        neo4j=neo4j,
        embedding_dimensions=embedding_dimensions,
        timeout_seconds=timeout_seconds,
    )

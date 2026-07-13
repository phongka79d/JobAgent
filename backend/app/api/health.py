"""GET /api/health — three-component availability boundary.

Probes reuse the configured async SQLite session, attachment storage root
access (no user-data probe file), and the Neo4j driver connectivity check.
Health never mutates schema and never writes application file content.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db.session import session_scope
from app.graph.driver import check_connectivity
from app.schemas.health import ComponentStatus, HealthResponse, build_health_response
from app.storage.attachments import AttachmentStorage

if TYPE_CHECKING:
    from neo4j import AsyncDriver

router = APIRouter(tags=["health"])


async def probe_sqlite() -> ComponentStatus:
    """Run a trivial query through the configured application session."""
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
        return "available"
    except Exception:
        return "unavailable"


async def probe_filesystem(storage: AttachmentStorage) -> ComponentStatus:
    """Verify FILES_DIR can be created/accessed without writing user data."""
    try:
        storage.ensure_root()
        root = storage.root
        if not root.is_dir():
            return "unavailable"
        # Access only: no probe file or user payload under the storage root.
        if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
            return "unavailable"
        return "available"
    except Exception:
        return "unavailable"


async def probe_neo4j(driver: AsyncDriver) -> ComponentStatus:
    """Delegate to the owned Neo4j connectivity check (no schema mutation)."""
    try:
        if await check_connectivity(driver):
            return "available"
        return "unavailable"
    except Exception:
        return "unavailable"


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Return validated overall + sqlite/filesystem/neo4j component status."""
    storage: AttachmentStorage = request.app.state.storage
    driver: AsyncDriver = request.app.state.neo4j_driver

    sqlite_status = await probe_sqlite()
    filesystem_status = await probe_filesystem(storage)
    neo4j_status = await probe_neo4j(driver)

    return build_health_response(
        sqlite=sqlite_status,
        filesystem=filesystem_status,
        neo4j=neo4j_status,
    )

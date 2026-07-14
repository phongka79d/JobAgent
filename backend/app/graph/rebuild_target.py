"""Exclusive choice-C target contract for Neo4j rebuild (Plan 5 §7.8).

Fail closed unless the runtime is the authorized Compose backend context:
local ``APP_ENV``, Bolt URI ``bolt://neo4j:7687``, and SQLite path
``/data/jobagent.db``. Loopback and host rebuild contexts are rejected.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from app.core.settings import Settings

# Canonical live Compose command (choice C; non-secret contract).
CANONICAL_COMPOSE_REBUILD_COMMAND: str = (
    "docker compose --env-file .env -f infrastructure/docker-compose.yml "
    "exec -T backend python -m app.graph.rebuild"
)

# Exact Compose backend runtime contract (not host loopback).
AUTHORIZED_NEO4J_URI: str = "bolt://neo4j:7687"
AUTHORIZED_SQLITE_PATH: str = "/data/jobagent.db"
AUTHORIZED_APP_ENV: str = "local"


class RebuildError(Exception):
    """Rebuild failed before or during graph reconstruction.

    ``code`` is a stable machine-oriented token; ``message`` is safe for
    developers (no secrets, credentials, or raw document bodies).
    """

    def __init__(self, message: str, *, code: str = "REBUILD_FAILED") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_bolt_uri(uri: str) -> str:
    """Return a comparable Bolt URI or empty string when invalid."""
    raw = (uri or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    if parts.scheme.lower() != "bolt":
        return ""
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    path = parts.path or ""
    if path not in {"", "/"}:
        return ""
    host = (parts.hostname or "").casefold()
    if not host:
        return ""
    port = parts.port
    if port is None:
        return ""
    return f"bolt://{host}:{port}"


def assert_local_compose_neo4j_target(settings: Settings) -> None:
    """Fail closed unless settings match the exclusive choice-C Compose contract.

    Does not print credentials. Rejects loopback, remote hosts, wrong ports,
    non-local APP_ENV, and any SQLite path other than the Compose volume path.
    """
    app_env = (settings.APP_ENV or "").strip().casefold()
    if app_env != AUTHORIZED_APP_ENV:
        raise RebuildError(
            "Rebuild refused: APP_ENV must be local for the authorized Compose "
            "backend rebuild context (choice C).",
            code="REBUILD_TARGET_REFUSED",
        )

    normalized = _normalize_bolt_uri(settings.NEO4J_URI or "")
    if normalized != AUTHORIZED_NEO4J_URI:
        raise RebuildError(
            "Rebuild refused: NEO4J_URI must be exactly "
            f"{AUTHORIZED_NEO4J_URI} (Compose service contract). "
            "Host loopback and remote graphs are out of scope.",
            code="REBUILD_TARGET_REFUSED",
        )

    sqlite_path = (settings.SQLITE_PATH or "").strip()
    if sqlite_path != AUTHORIZED_SQLITE_PATH:
        raise RebuildError(
            "Rebuild refused: SQLITE_PATH must be exactly "
            f"{AUTHORIZED_SQLITE_PATH} (Compose backend data volume). "
            "Host or alternate database paths are out of scope.",
            code="REBUILD_TARGET_REFUSED",
        )


__all__ = [
    "AUTHORIZED_APP_ENV",
    "AUTHORIZED_NEO4J_URI",
    "AUTHORIZED_SQLITE_PATH",
    "CANONICAL_COMPOSE_REBUILD_COMMAND",
    "RebuildError",
    "assert_local_compose_neo4j_target",
]

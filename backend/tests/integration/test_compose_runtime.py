"""Live Compose runtime health checks (04B).

Exercises host-published ``GET /api/health`` when the three-service stack is up.
Skips when the backend is unreachable so offline integration gates still pass.
Never loads root ``.env`` or prints secrets.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import pytest
from app.schemas.health import HealthResponse

_HEALTH_URL = "http://127.0.0.1:8000/api/health"
_EXPECTED_KEYS = frozenset({"overall", "sqlite", "filesystem", "neo4j"})
_AVAILABLE = "available"


def _fetch_health() -> dict[str, Any] | None:
    """Return health JSON when the endpoint answers; None if unreachable."""
    try:
        with urllib.request.urlopen(_HEALTH_URL, timeout=5) as response:
            body = response.read().decode("utf-8")
            status = response.status
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if status != 200:
        return None
    data = json.loads(body)
    if not isinstance(data, dict):
        return None
    return data


def _require_health() -> dict[str, Any]:
    payload = _fetch_health()
    if payload is None:
        pytest.skip(
            "Compose backend health unreachable at "
            f"{_HEALTH_URL} (start jobagent-plan2-test stack first)"
        )
    return payload


def test_live_health_all_components_available() -> None:
    """When Compose is healthy, all three components and overall are available."""
    payload = _require_health()
    validated = HealthResponse.model_validate(payload)
    assert set(payload.keys()) == _EXPECTED_KEYS
    assert validated.overall == _AVAILABLE
    assert validated.sqlite == _AVAILABLE
    assert validated.filesystem == _AVAILABLE
    assert validated.neo4j == _AVAILABLE


def test_live_health_payload_has_no_secret_or_connection_detail() -> None:
    """Health JSON must not leak credentials, URIs, or filesystem paths."""
    payload = _require_health()
    text = json.dumps(payload)
    HealthResponse.model_validate(payload)

    password = os.environ.get("NEO4J_PASSWORD")
    if password:
        assert password not in text
    shop = os.environ.get("SHOPAIKEY_API_KEY")
    if shop:
        assert shop not in text

    forbidden_substrings = (
        "bolt://",
        "neo4j://",
        "password",
        "api_key",
        "api-key",
        "/data/",
        "FILES_DIR",
        "SQLITE_PATH",
        "NEO4J_",
        "SHOPAIKEY",
    )
    lowered = text.lower()
    for token in forbidden_substrings:
        assert token.lower() not in lowered, (
            f"health payload must not contain {token!r}"
        )

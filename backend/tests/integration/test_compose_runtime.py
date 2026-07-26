"""Live Compose runtime health checks (04B).

Exercises host-published ``GET /api/health`` when the three-service stack is up.
Skips when the backend is unreachable so offline integration gates still pass.
Never loads root ``.env`` or prints secrets.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from app.schemas.health import HealthResponse

_HEALTH_URL = "http://127.0.0.1:8000/api/health"
_EXPECTED_KEYS = frozenset({"overall", "sqlite", "filesystem", "neo4j"})
_AVAILABLE = "available"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_FILE = _REPO_ROOT / "infrastructure" / "docker-compose.yml"
_BACKEND_DOCKERFILE = _REPO_ROOT / "infrastructure" / "docker" / "backend.Dockerfile"
_MIGRATION = (
    _REPO_ROOT
    / "backend"
    / "migrations"
    / "versions"
    / "0007_add_cv_tailoring.py"
)


def _compose_service_names(source: str) -> list[str]:
    in_services = False
    names: list[str] = []
    for line in source.splitlines():
        if line == "services:":
            in_services = True
            continue
        if not in_services:
            continue
        if line and not line.startswith(" "):
            break
        match = re.fullmatch(r"  ([a-z0-9_-]+):", line)
        if match is not None:
            names.append(match.group(1))
    return names


def test_compose_source_has_exact_services_and_migrates_before_uvicorn() -> None:
    compose = _COMPOSE_FILE.read_text(encoding="utf-8")
    dockerfile = _BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    migration = _MIGRATION.read_text(encoding="utf-8")
    command = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))

    assert _compose_service_names(compose) == ["neo4j", "backend", "frontend"]
    assert "alembic upgrade head && exec uvicorn" in dockerfile
    assert 'revision: str = "0007_add_cv_tailoring"' in migration
    assert "create_all" not in command
    for package in (
        "texlive-latex-base",
        "texlive-latex-recommended",
        "texlive-latex-extra",
        "texlive-fonts-recommended",
        "texlive-lang-other",
    ):
        assert package in dockerfile
    assert "RUN python -m app.services.cv_tailoring_smoke" in dockerfile
    assert dockerfile.count("exec uvicorn") == 1
    for name, default in {
        "CV_TAILOR_MAX_INSTRUCTION_CHARS": "4000",
        "CV_TAILOR_MAX_SECTIONS": "20",
        "CV_TAILOR_MAX_ITEMS_PER_SECTION": "30",
        "CV_TAILOR_MAX_TEX_CHARS": "100000",
        "CV_TAILOR_COMPILE_TIMEOUT_SECONDS": "15",
        "CV_TAILOR_MAX_PDF_MB": "5",
    }.items():
        assert f"{name}: ${{{name}:-{default}}}" in compose


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

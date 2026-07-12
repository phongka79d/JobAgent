"""Settings and secret-safety tests (synthetic env only; no network, no real .env)."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import (
    ALLOWED_EMBEDDING_DIMENSIONS,
    ALLOWED_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    SETTINGS_ENV_NAMES,
    Settings,
    SettingsError,
    load_settings,
)
from app.main import app, create_app
from fastapi import FastAPI

SENTINEL_API_KEY = "sentinel-shopaikey-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-never-emit"


def minimal_valid_environ() -> dict[str, str]:
    """Required secrets only; defaults cover the rest of section 23."""
    return {
        "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
        "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
    }


def full_valid_environ() -> dict[str, str]:
    return {
        "APP_ENV": "local",
        "FRONTEND_ORIGIN": "http://localhost:5173",
        "VITE_API_BASE_URL": "http://localhost:8000",
        "SQLITE_PATH": "/data/jobagent.db",
        "FILES_DIR": "/data/files",
        "NEO4J_URI": "bolt://neo4j:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
        "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
        "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
        "LLM_MODEL": "gpt-4o-mini",
        "LLM_TEMPERATURE": "0",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "EMBEDDING_DIMENSIONS": "1536",
        "MAX_PDF_SIZE_MB": "10",
        "MAX_PDF_PAGES": "10",
        "URL_FETCH_TIMEOUT_SECONDS": "10",
        "URL_MAX_RESPONSE_MB": "5",
        "TOOL_LOOP_LIMIT": "6",
    }


def test_section_23_names_are_complete() -> None:
    assert SETTINGS_ENV_NAMES == (
        "APP_ENV",
        "FRONTEND_ORIGIN",
        "VITE_API_BASE_URL",
        "SQLITE_PATH",
        "FILES_DIR",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "SHOPAIKEY_BASE_URL",
        "SHOPAIKEY_API_KEY",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "MAX_PDF_SIZE_MB",
        "MAX_PDF_PAGES",
        "URL_FETCH_TIMEOUT_SECONDS",
        "URL_MAX_RESPONSE_MB",
        "TOOL_LOOP_LIMIT",
    )


def test_defaults_match_master_section_23() -> None:
    settings = load_settings(environ=minimal_valid_environ())

    assert settings.app_env == "local"
    assert settings.frontend_origin == "http://localhost:5173"
    assert settings.vite_api_base_url == "http://localhost:8000"
    assert settings.sqlite_path == "/data/jobagent.db"
    assert settings.files_dir == "/data/files"
    assert settings.neo4j_uri == "bolt://neo4j:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.shopaikey_base_url == "https://api.shopaikey.com/v1"
    assert settings.llm_model == DEFAULT_LLM_MODEL
    assert settings.llm_temperature == 0.0
    assert settings.embedding_model == ALLOWED_EMBEDDING_MODEL
    assert settings.embedding_dimensions == ALLOWED_EMBEDDING_DIMENSIONS
    assert settings.max_pdf_size_mb == 10
    assert settings.max_pdf_pages == 10
    assert settings.url_fetch_timeout_seconds == 10
    assert settings.url_max_response_mb == 5
    assert settings.tool_loop_limit == 6


def test_full_environment_loads() -> None:
    settings = load_settings(environ=full_valid_environ())
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.embedding_dimensions == 1536
    assert settings.neo4j_password.get_secret_value() == SENTINEL_NEO4J_PASSWORD
    assert settings.shopaikey_api_key.get_secret_value() == SENTINEL_API_KEY


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NEO4J_PASSWORD", ""),
        ("SHOPAIKEY_API_KEY", ""),
        ("NEO4J_PASSWORD", "   "),
        ("SHOPAIKEY_API_KEY", "   "),
    ],
)
def test_required_secrets_reject_empty_without_disclosure(
    name: str, value: str
) -> None:
    environment = full_valid_environ()
    environment[name] = value

    with pytest.raises(SettingsError) as raised:
        load_settings(environ=environment)

    rendered = str(raised.value)
    assert SENTINEL_API_KEY not in rendered
    assert SENTINEL_NEO4J_PASSWORD not in rendered
    assert "Invalid application configuration." in rendered


def test_missing_required_secrets_fail() -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings(environ={})
    assert SENTINEL_API_KEY not in str(raised.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SHOPAIKEY_BASE_URL", ""),
        ("SHOPAIKEY_BASE_URL", "file:///private"),
        (
            "SHOPAIKEY_BASE_URL",
            f"https://user:{SENTINEL_API_KEY}@provider.example/v1",
        ),
        (
            "SHOPAIKEY_BASE_URL",
            f"https://provider.example/v1?api_key={SENTINEL_API_KEY}",
        ),
        (
            "SHOPAIKEY_BASE_URL",
            f"https://provider.example/v1#token={SENTINEL_API_KEY}",
        ),
        ("FRONTEND_ORIGIN", "not-a-url"),
        ("FRONTEND_ORIGIN", "http://localhost:5173/path"),
        ("FRONTEND_ORIGIN", f"https://user:{SENTINEL_API_KEY}@localhost:5173"),
        ("VITE_API_BASE_URL", "ftp://localhost:8000"),
        ("NEO4J_URI", "http://neo4j:7687"),
        ("NEO4J_URI", f"bolt://user:{SENTINEL_NEO4J_PASSWORD}@neo4j:7687"),
        ("LLM_MODEL", ""),
        ("EMBEDDING_MODEL", "other-embedding-model"),
        ("EMBEDDING_DIMENSIONS", "768"),
        ("EMBEDDING_DIMENSIONS", "0"),
        ("LLM_TEMPERATURE", "-1"),
        ("LLM_TEMPERATURE", "3"),
        ("LLM_TEMPERATURE", "nan"),
        ("LLM_TEMPERATURE", "NaN"),
        ("LLM_TEMPERATURE", "inf"),
        ("LLM_TEMPERATURE", "-inf"),
        ("LLM_TEMPERATURE", "Infinity"),
        ("FRONTEND_ORIGIN", "http://localhost:notaport"),
        ("VITE_API_BASE_URL", "http://localhost:99999"),
        ("SHOPAIKEY_BASE_URL", "https://provider.example:notaport/v1"),
        ("NEO4J_URI", "bolt://neo4j:notaport"),
        ("NEO4J_URI", "bolt://neo4j:99999"),
        ("MAX_PDF_SIZE_MB", "0"),
        ("MAX_PDF_PAGES", "-1"),
        ("URL_FETCH_TIMEOUT_SECONDS", "0"),
        ("URL_MAX_RESPONSE_MB", "0"),
        ("TOOL_LOOP_LIMIT", "0"),
        ("APP_ENV", ""),
        ("SQLITE_PATH", ""),
        ("FILES_DIR", ""),
    ],
)
def test_invalid_values_fail_without_secret_disclosure(
    name: str, value: str
) -> None:
    environment = full_valid_environ()
    environment[name] = value

    with pytest.raises(SettingsError) as raised:
        load_settings(environ=environment)

    rendered = str(raised.value)
    assert SENTINEL_API_KEY not in rendered
    assert SENTINEL_NEO4J_PASSWORD not in rendered
    assert "Invalid application configuration." == rendered
    # Generic error only; never echo submitted invalid tokens (ports, nan, etc.).
    if value:
        assert value not in rendered
    if "://" in value:
        port_token = value.rsplit(":", 1)[-1].split("/", 1)[0]
        if port_token and not port_token.isdigit():
            assert port_token not in rendered
        elif port_token.isdigit() and int(port_token) > 65535:
            assert port_token not in rendered


def test_repr_and_str_redact_secrets() -> None:
    settings = load_settings(environ=minimal_valid_environ())
    text = f"{settings!r} | {settings!s}"
    assert SENTINEL_API_KEY not in text
    assert SENTINEL_NEO4J_PASSWORD not in text
    assert "[REDACTED]" in text


def test_safe_public_config_omits_secrets_and_backend_paths() -> None:
    settings = load_settings(environ=full_valid_environ())
    public = settings.safe_public_config()

    assert "SHOPAIKEY_API_KEY" not in public
    assert "NEO4J_PASSWORD" not in public
    assert "NEO4J_URI" not in public
    assert "NEO4J_USER" not in public
    assert "SQLITE_PATH" not in public
    assert "FILES_DIR" not in public
    assert "SHOPAIKEY_BASE_URL" not in public
    assert SENTINEL_API_KEY not in str(public)
    assert SENTINEL_NEO4J_PASSWORD not in str(public)
    assert public["EMBEDDING_MODEL"] == ALLOWED_EMBEDDING_MODEL
    assert public["EMBEDDING_DIMENSIONS"] == ALLOWED_EMBEDDING_DIMENSIONS
    assert public["VITE_API_BASE_URL"] == "http://localhost:8000"


def test_root_env_file_loading_uses_synthetic_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "APP_ENV=test",
                f"NEO4J_PASSWORD={SENTINEL_NEO4J_PASSWORD}",
                f"SHOPAIKEY_API_KEY={SENTINEL_API_KEY}",
                "TOOL_LOOP_LIMIT=4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for name in SETTINGS_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    settings = load_settings(env_file=env_path)

    assert settings.app_env == "test"
    assert settings.tool_loop_limit == 4
    assert settings.llm_model == DEFAULT_LLM_MODEL


def test_process_environment_overrides_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "APP_ENV=from-file",
                f"NEO4J_PASSWORD={SENTINEL_NEO4J_PASSWORD}",
                f"SHOPAIKEY_API_KEY={SENTINEL_API_KEY}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for name in SETTINGS_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "from-process")

    settings = load_settings(env_file=env_path)
    assert settings.app_env == "from-process"


def test_load_settings_with_environ_does_not_require_real_root_env() -> None:
    # Synthetic injection path used by all unit tests; never touches user .env.
    settings = load_settings(environ=minimal_valid_environ())
    assert isinstance(settings, Settings)


def test_fastapi_app_is_importable_with_health_only() -> None:
    assert isinstance(app, FastAPI)
    built = create_app()
    assert isinstance(built, FastAPI)
    # Framework docs exist; OpenAPI application surface is health + Plan 3 chat.
    route_paths = {
        route.path
        for route in app.routes  # type: ignore[attr-defined]
        if hasattr(route, "path")
    }
    assert "/docs" in route_paths or "/openapi.json" in route_paths
    openapi_paths = set(app.openapi()["paths"])
    assert openapi_paths == {
        "/api/health",
        "/api/chat/history",
        "/api/chat/turns",
        "/api/chat/runs/{run_id}/resume",
    }
    assert not any(
        any(
            marker in path
            for marker in ("attachments", "profile", "jobs", "upload", "match")
        )
        for path in openapi_paths
    )

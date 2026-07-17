"""Unit tests for one-root Settings model (Plan 2 §7.1)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.core import settings as settings_module
from app.core.settings import (
    Settings,
    clear_settings_cache,
    get_settings,
    root_env_path,
)
from pydantic import AnyHttpUrl, SecretStr, ValidationError

# Exact external names and defaults from Plan 2 Section 7.1.
EXPECTED_FIELDS: dict[str, type[Any]] = {
    "APP_ENV": str,
    "FRONTEND_ORIGIN": str,
    "SQLITE_PATH": str,
    "FILES_DIR": str,
    "NEO4J_URI": str,
    "NEO4J_USER": str,
    "NEO4J_PASSWORD": SecretStr,
    "SHOPAIKEY_BASE_URL": AnyHttpUrl,
    "SHOPAIKEY_API_KEY": SecretStr,
    "LLM_MODEL": str,
    "LLM_TEMPERATURE": float,
    "EMBEDDING_MODEL": str,
    "EMBEDDING_DIMENSIONS": int,
    "MAX_PDF_SIZE_MB": int,
    "MAX_PDF_PAGES": int,
    "URL_FETCH_TIMEOUT_SECONDS": int,
    "URL_MAX_RESPONSE_MB": int,
    "TOOL_LOOP_LIMIT": int,
    # Plan 9 document-first batch ceiling.
    "CV_DOCUMENT_BATCH_MAX_CHARS": int,
}

EXPECTED_DEFAULTS: dict[str, Any] = {
    "APP_ENV": "local",
    "LLM_MODEL": "gpt-4o-mini",
    "LLM_TEMPERATURE": 0,
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "EMBEDDING_DIMENSIONS": 1536,
    "MAX_PDF_SIZE_MB": 10,
    "MAX_PDF_PAGES": 10,
    "URL_FETCH_TIMEOUT_SECONDS": 10,
    "URL_MAX_RESPONSE_MB": 5,
    "TOOL_LOOP_LIMIT": 6,
    "CV_DOCUMENT_BATCH_MAX_CHARS": 6000,
}

REQUIRED_WITHOUT_DEFAULT: frozenset[str] = frozenset(
    {
        "FRONTEND_ORIGIN",
        "SQLITE_PATH",
        "FILES_DIR",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "SHOPAIKEY_BASE_URL",
        "SHOPAIKEY_API_KEY",
    }
)

SANITIZED_ENV: dict[str, str] = {
    "FRONTEND_ORIGIN": "http://localhost:5173",
    "SQLITE_PATH": "/tmp/jobagent-test.db",
    "FILES_DIR": "/tmp/jobagent-files",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "test-neo4j-password-not-real",
    "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
    "SHOPAIKEY_API_KEY": "test-shopaikey-secret-not-real",
}


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure tests never depend on the developer's real root ``.env``."""
    clear_settings_cache()
    for key in EXPECTED_FIELDS:
        monkeypatch.delenv(key, raising=False)
    yield
    clear_settings_cache()


def _apply_sanitized(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    payload = {**SANITIZED_ENV, **overrides}
    for key, value in payload.items():
        monkeypatch.setenv(key, value)


def _settings_from_env_only() -> Settings:
    """Build Settings from process env only (no file load)."""
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_exposes_exactly_section_7_1_field_names() -> None:
    model_fields = set(Settings.model_fields)
    assert model_fields == set(EXPECTED_FIELDS)


def test_settings_field_types_match_section_7_1() -> None:
    for name, expected_type in EXPECTED_FIELDS.items():
        field = Settings.model_fields[name]
        annotation = field.annotation
        assert annotation is expected_type, (
            f"{name}: {annotation!r} != {expected_type!r}"
        )


def test_settings_defaults_match_section_7_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _apply_sanitized(monkeypatch)
    s = _settings_from_env_only()
    for name, default in EXPECTED_DEFAULTS.items():
        value = getattr(s, name)
        if name == "LLM_TEMPERATURE":
            assert float(value) == float(default)
        else:
            assert value == default


def test_required_fields_have_no_defaults() -> None:
    for name in REQUIRED_WITHOUT_DEFAULT:
        field = Settings.model_fields[name]
        assert field.is_required(), f"{name} should be required without default"


def test_get_settings_loads_root_env_and_is_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FRONTEND_ORIGIN=http://localhost:5173",
                "SQLITE_PATH=/tmp/jobagent-test.db",
                "FILES_DIR=/tmp/jobagent-files",
                "NEO4J_URI=bolt://localhost:7687",
                "NEO4J_USER=neo4j",
                "NEO4J_PASSWORD=test-neo4j-password-not-real",
                "SHOPAIKEY_BASE_URL=https://api.shopaikey.com/v1",
                "SHOPAIKEY_API_KEY=test-shopaikey-secret-not-real",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "root_env_path", lambda: env_path)
    clear_settings_cache()
    a = get_settings()
    b = get_settings()
    assert a is b
    assert a.FRONTEND_ORIGIN == "http://localhost:5173"
    assert a.NEO4J_PASSWORD.get_secret_value() == "test-neo4j-password-not-real"


def test_process_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _apply_sanitized(
        monkeypatch,
        APP_ENV="test",
        LLM_MODEL="override-model",
        LLM_TEMPERATURE="0.5",
        EMBEDDING_DIMENSIONS="768",
        MAX_PDF_SIZE_MB="3",
        TOOL_LOOP_LIMIT="2",
    )
    s = _settings_from_env_only()
    assert s.APP_ENV == "test"
    assert s.LLM_MODEL == "override-model"
    assert s.LLM_TEMPERATURE == 0.5
    assert s.EMBEDDING_DIMENSIONS == 768
    assert s.MAX_PDF_SIZE_MB == 3
    assert s.TOOL_LOOP_LIMIT == 2


def test_root_env_path_is_repository_root_dotenv_only() -> None:
    path = root_env_path()
    assert path.name == ".env"
    assert path.parent == settings_module.repo_root()
    assert (path.parent / "backend").is_dir() or (path.parent / "docs").is_dir()
    assert path.name != ".env.example"
    assert not str(path).endswith(".env.example")
    # Runtime must never load the documentation template.
    example = settings_module.repo_root() / ".env.example"
    assert path != example


def test_get_settings_never_uses_env_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    example_path = tmp_path / ".env.example"
    env_path.write_text(
        "\n".join(
            [
                "FRONTEND_ORIGIN=http://from-dotenv:5173",
                "SQLITE_PATH=/data/from-dotenv.db",
                "FILES_DIR=/data/from-dotenv-files",
                "NEO4J_URI=bolt://from-dotenv:7687",
                "NEO4J_USER=env-user",
                "NEO4J_PASSWORD=password-from-dotenv",
                "SHOPAIKEY_BASE_URL=https://api.shopaikey.com/v1",
                "SHOPAIKEY_API_KEY=key-from-dotenv",
                "APP_ENV=from-dotenv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    example_path.write_text(
        "\n".join(
            [
                "FRONTEND_ORIGIN=http://from-example:5173",
                "SQLITE_PATH=/data/from-example.db",
                "FILES_DIR=/data/from-example-files",
                "NEO4J_URI=bolt://from-example:7687",
                "NEO4J_USER=example-user",
                "NEO4J_PASSWORD=password-from-example",
                "SHOPAIKEY_BASE_URL=https://example.invalid/v1",
                "SHOPAIKEY_API_KEY=key-from-example",
                "APP_ENV=from-example",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "root_env_path", lambda: env_path)
    clear_settings_cache()
    s = get_settings()
    assert s.APP_ENV == "from-dotenv"
    assert s.FRONTEND_ORIGIN == "http://from-dotenv:5173"
    assert s.SQLITE_PATH == "/data/from-dotenv.db"
    assert s.NEO4J_USER == "env-user"
    assert s.NEO4J_PASSWORD.get_secret_value() == "password-from-dotenv"
    assert s.SHOPAIKEY_API_KEY.get_secret_value() == "key-from-dotenv"
    assert s.APP_ENV != "from-example"
    assert s.NEO4J_USER != "example-user"


def test_process_env_overrides_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FRONTEND_ORIGIN=http://from-dotenv:5173",
                "SQLITE_PATH=/data/from-dotenv.db",
                "FILES_DIR=/data/from-dotenv-files",
                "NEO4J_URI=bolt://from-dotenv:7687",
                "NEO4J_USER=env-user",
                "NEO4J_PASSWORD=password-from-dotenv",
                "SHOPAIKEY_BASE_URL=https://api.shopaikey.com/v1",
                "SHOPAIKEY_API_KEY=key-from-dotenv",
                "APP_ENV=from-dotenv",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "root_env_path", lambda: env_path)
    monkeypatch.setenv("APP_ENV", "from-process")
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://from-process:5173")
    clear_settings_cache()
    s = get_settings()
    assert s.APP_ENV == "from-process"
    assert s.FRONTEND_ORIGIN == "http://from-process:5173"
    assert s.SQLITE_PATH == "/data/from-dotenv.db"
    assert s.NEO4J_USER == "env-user"
    assert s.NEO4J_PASSWORD.get_secret_value() == "password-from-dotenv"


def test_secrets_are_masked_in_representations(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_neo = "super-secret-neo4j-password-xyz"
    secret_api = "super-secret-shopaikey-api-key-xyz"
    _apply_sanitized(
        monkeypatch,
        NEO4J_PASSWORD=secret_neo,
        SHOPAIKEY_API_KEY=secret_api,
    )
    s = _settings_from_env_only()
    for rendered in (repr(s), str(s)):
        assert secret_neo not in rendered
        assert secret_api not in rendered
    assert s.NEO4J_PASSWORD.get_secret_value() == secret_neo
    assert s.SHOPAIKEY_API_KEY.get_secret_value() == secret_api


def test_missing_required_field_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in SANITIZED_ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValidationError):
        _settings_from_env_only()

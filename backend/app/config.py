"""Typed root settings for the master-plan environment contract.

Loads configuration from process environment and, when requested, the single
repository-root ``.env`` file. Nested frontend/backend ``.env`` files are not
supported. Secret values are never logged or included in safe exports.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import SplitResult, urlsplit

from dotenv import dotenv_values
from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

REDACTED: Final[str] = "[REDACTED]"
ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[2]
ROOT_ENV_PATH: Final[Path] = ROOT_DIR / ".env"

ALLOWED_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
ALLOWED_EMBEDDING_DIMENSIONS: Final[int] = 1536
DEFAULT_LLM_MODEL: Final[str] = "gpt-4o-mini"

# Exact master-plan section 23 variable names (single source of field aliases).
SETTINGS_ENV_NAMES: Final[tuple[str, ...]] = (
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


class SettingsError(ValueError):
    """Invalid application configuration.

    Messages must never include secret values or credential-bearing URL parts.
    """


def _invalid_config() -> SettingsError:
    return SettingsError("Invalid application configuration.")


def _require_valid_optional_port(parsed: SplitResult) -> None:
    """Reject non-numeric or out-of-range ports without echoing submitted values.

    ``urlsplit`` stores the port text in ``netloc`` and only validates it when
    ``.port`` is accessed. Invalid ports raise ``ValueError`` with the raw token
    in the message, so callers must not surface that exception text.
    """
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("invalid port") from None


def _validate_http_url(value: str, *, allow_path: bool) -> str:
    cleaned = value.strip()
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise ValueError("invalid url") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid url")
    try:
        _require_valid_optional_port(parsed)
    except ValueError:
        raise ValueError("invalid url") from None
    if not allow_path and parsed.path not in {"", "/"}:
        raise ValueError("invalid origin")
    return cleaned


def _validate_neo4j_uri(value: str) -> str:
    cleaned = value.strip()
    try:
        parsed = urlsplit(cleaned)
    except ValueError as exc:
        raise ValueError("invalid neo4j uri") from exc
    if (
        parsed.scheme not in {"bolt", "bolt+s", "neo4j", "neo4j+s"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid neo4j uri")
    try:
        _require_valid_optional_port(parsed)
    except ValueError:
        raise ValueError("invalid neo4j uri") from None
    return cleaned


class Settings(BaseSettings):
    """All master section 23 variables, typed once with defaults or required rules."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        populate_by_name=True,
        validate_default=True,
    )

    app_env: str = Field(default="local", validation_alias="APP_ENV")
    frontend_origin: str = Field(
        default="http://localhost:5173",
        validation_alias="FRONTEND_ORIGIN",
    )
    vite_api_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="VITE_API_BASE_URL",
    )
    sqlite_path: str = Field(
        default="/data/jobagent.db",
        validation_alias="SQLITE_PATH",
    )
    files_dir: str = Field(default="/data/files", validation_alias="FILES_DIR")
    neo4j_uri: str = Field(
        default="bolt://neo4j:7687",
        validation_alias="NEO4J_URI",
    )
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(validation_alias="NEO4J_PASSWORD")
    shopaikey_base_url: str = Field(
        default="https://api.shopaikey.com/v1",
        validation_alias="SHOPAIKEY_BASE_URL",
    )
    shopaikey_api_key: SecretStr = Field(validation_alias="SHOPAIKEY_API_KEY")
    llm_model: str = Field(default=DEFAULT_LLM_MODEL, validation_alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    embedding_model: str = Field(
        default=ALLOWED_EMBEDDING_MODEL,
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_dimensions: int = Field(
        default=ALLOWED_EMBEDDING_DIMENSIONS,
        validation_alias="EMBEDDING_DIMENSIONS",
    )
    max_pdf_size_mb: int = Field(default=10, validation_alias="MAX_PDF_SIZE_MB")
    max_pdf_pages: int = Field(default=10, validation_alias="MAX_PDF_PAGES")
    url_fetch_timeout_seconds: int = Field(
        default=10,
        validation_alias="URL_FETCH_TIMEOUT_SECONDS",
    )
    url_max_response_mb: int = Field(
        default=5,
        validation_alias="URL_MAX_RESPONSE_MB",
    )
    tool_loop_limit: int = Field(default=6, validation_alias="TOOL_LOOP_LIMIT")

    @field_validator(
        "app_env",
        "sqlite_path",
        "files_dir",
        "neo4j_user",
        "llm_model",
        mode="before",
    )
    @classmethod
    def _strip_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("app_env", "sqlite_path", "files_dir", "neo4j_user", "llm_model")
    @classmethod
    def _require_non_empty_text(cls, value: str) -> str:
        if not value:
            raise ValueError("required")
        return value

    @field_validator("frontend_origin", mode="before")
    @classmethod
    def _normalize_frontend_origin(cls, value: object) -> object:
        if isinstance(value, str):
            return _validate_http_url(value, allow_path=False)
        return value

    @field_validator("vite_api_base_url", mode="before")
    @classmethod
    def _normalize_vite_api_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            return _validate_http_url(value, allow_path=True)
        return value

    @field_validator("shopaikey_base_url", mode="before")
    @classmethod
    def _normalize_shopaikey_base_url(cls, value: object) -> object:
        if isinstance(value, str):
            return _validate_http_url(value, allow_path=True)
        return value

    @field_validator("neo4j_uri", mode="before")
    @classmethod
    def _normalize_neo4j_uri(cls, value: object) -> object:
        if isinstance(value, str):
            return _validate_neo4j_uri(value)
        return value

    @field_validator("neo4j_password", "shopaikey_api_key", mode="before")
    @classmethod
    def _require_secret(cls, value: object) -> object:
        if value is None:
            raise ValueError("required")
        if isinstance(value, SecretStr):
            secret = value.get_secret_value().strip()
        else:
            secret = str(value).strip()
        if not secret:
            raise ValueError("required")
        return secret

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _parse_temperature(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("required")
            return cleaned
        return value

    @field_validator("llm_temperature")
    @classmethod
    def _bounds_temperature(cls, value: float) -> float:
        # Non-finite values (nan/inf) bypass ordinary range comparisons.
        if not math.isfinite(value) or value < 0.0 or value > 2.0:
            raise ValueError("out of range")
        return value

    @field_validator(
        "embedding_dimensions",
        "max_pdf_size_mb",
        "max_pdf_pages",
        "url_fetch_timeout_seconds",
        "url_max_response_mb",
        "tool_loop_limit",
        mode="before",
    )
    @classmethod
    def _parse_positive_int(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("required")
            return cleaned
        return value

    @field_validator(
        "max_pdf_size_mb",
        "max_pdf_pages",
        "url_fetch_timeout_seconds",
        "url_max_response_mb",
        "tool_loop_limit",
    )
    @classmethod
    def _require_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("out of range")
        return value

    @field_validator("embedding_model", mode="before")
    @classmethod
    def _strip_embedding_model(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _enforce_embedding_contract(self) -> Settings:
        if (
            self.embedding_model != ALLOWED_EMBEDDING_MODEL
            or self.embedding_dimensions != ALLOWED_EMBEDDING_DIMENSIONS
        ):
            raise ValueError("disallowed embedding contract")
        return self

    def __repr__(self) -> str:
        return (
            "Settings("
            f"app_env={self.app_env!r}, "
            f"frontend_origin={self.frontend_origin!r}, "
            f"vite_api_base_url={self.vite_api_base_url!r}, "
            f"sqlite_path={self.sqlite_path!r}, "
            f"files_dir={self.files_dir!r}, "
            f"neo4j_uri={self.neo4j_uri!r}, "
            f"neo4j_user={self.neo4j_user!r}, "
            f"neo4j_password={REDACTED!r}, "
            f"shopaikey_base_url={self.shopaikey_base_url!r}, "
            f"shopaikey_api_key={REDACTED!r}, "
            f"llm_model={self.llm_model!r}, "
            f"llm_temperature={self.llm_temperature!r}, "
            f"embedding_model={self.embedding_model!r}, "
            f"embedding_dimensions={self.embedding_dimensions!r}, "
            f"max_pdf_size_mb={self.max_pdf_size_mb!r}, "
            f"max_pdf_pages={self.max_pdf_pages!r}, "
            f"url_fetch_timeout_seconds={self.url_fetch_timeout_seconds!r}, "
            f"url_max_response_mb={self.url_max_response_mb!r}, "
            f"tool_loop_limit={self.tool_loop_limit!r}"
            ")"
        )

    __str__ = __repr__

    def safe_public_config(self) -> dict[str, Any]:
        """Return only explicitly non-secret configuration fields."""
        return {
            "APP_ENV": self.app_env,
            "FRONTEND_ORIGIN": self.frontend_origin,
            "VITE_API_BASE_URL": self.vite_api_base_url,
            "LLM_MODEL": self.llm_model,
            "LLM_TEMPERATURE": self.llm_temperature,
            "EMBEDDING_MODEL": self.embedding_model,
            "EMBEDDING_DIMENSIONS": self.embedding_dimensions,
            "MAX_PDF_SIZE_MB": self.max_pdf_size_mb,
            "MAX_PDF_PAGES": self.max_pdf_pages,
            "URL_FETCH_TIMEOUT_SECONDS": self.url_fetch_timeout_seconds,
            "URL_MAX_RESPONSE_MB": self.url_max_response_mb,
            "TOOL_LOOP_LIMIT": self.tool_loop_limit,
        }


def _settings_from_mapping(values: Mapping[str, str]) -> Settings:
    """Build settings from a synthetic or pre-merged environment mapping."""
    payload = {name: values[name] for name in SETTINGS_ENV_NAMES if name in values}
    try:
        return Settings.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        raise _invalid_config() from None


def load_settings(
    *,
    environ: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> Settings:
    """Load typed settings.

    Parameters
    ----------
    environ:
        When provided (tests), only this mapping is used. The real root ``.env``
        and process environment are not read.
    env_file:
        Optional dotenv path used when ``environ`` is omitted. Defaults to the
        repository-root ``.env``. Process environment variables take precedence
        over file values (Phase 0 diagnostic loading behavior).
    """
    if environ is not None:
        return _settings_from_mapping(environ)

    path = ROOT_ENV_PATH if env_file is None else env_file
    file_values: dict[str, str] = {}
    if path.is_file():
        file_values = {
            key: value
            for key, value in dotenv_values(path).items()
            if value is not None
        }
    merged: dict[str, str] = {}
    for name in SETTINGS_ENV_NAMES:
        if name in os.environ:
            merged[name] = os.environ[name]
        elif name in file_values:
            merged[name] = file_values[name]
    return _settings_from_mapping(merged)

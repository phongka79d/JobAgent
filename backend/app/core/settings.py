"""One-root Pydantic Settings model for JobAgent runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """Return the repository root (parent of ``backend/``)."""
    return Path(__file__).resolve().parents[3]


def root_env_path() -> Path:
    """Return the single runtime env file path: repository root ``.env``."""
    return repo_root() / ".env"


class Settings(BaseSettings):
    """Runtime settings with exact external field names from Plan 2 §7.1.

    Process environment values always override file values. Runtime loading goes
    through :func:`get_settings`, which reads only the repository root ``.env``
    (never ``.env.example``).
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "local"
    FRONTEND_ORIGIN: str
    SQLITE_PATH: str
    FILES_DIR: str
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: SecretStr
    SHOPAIKEY_BASE_URL: AnyHttpUrl
    SHOPAIKEY_API_KEY: SecretStr
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    MAX_PDF_SIZE_MB: int = 10
    MAX_PDF_PAGES: int = 10
    URL_FETCH_TIMEOUT_SECONDS: int = 10
    URL_MAX_RESPONSE_MB: int = 5
    TOOL_LOOP_LIMIT: int = 6


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton loaded from the root ``.env``."""
    return Settings(_env_file=root_env_path())  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    """Drop the cached settings instance (for tests)."""
    get_settings.cache_clear()

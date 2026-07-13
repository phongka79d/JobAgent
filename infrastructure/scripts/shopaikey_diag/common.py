"""Shared constants, settings load, HTTP helpers, and failure formatting."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover - environment setup
    print("SHOPAIKEY_COMPATIBILITY=FAIL", file=sys.stderr)
    print(f"ERROR=import_httpx:{exc}", file=sys.stderr)
    raise SystemExit(2) from exc

# Locked Phase 0 contract
LOCKED_CHAT_MODEL = "gpt-4o-mini"
LOCKED_EMBED_MODEL = "text-embedding-3-small"
LOCKED_DIMENSIONS = 1536
REQUEST_TIMEOUT_S = 60.0
DEFAULT_BASE_URL = "https://api.shopaikey.com/v1"

# Concise failure codes (non-zero exit path)
CODE_MISSING_KEY = "MISSING_KEY"
CODE_TIMEOUT = "TIMEOUT"
CODE_RATE_LIMIT = "RATE_LIMIT"
CODE_MALFORMED = "MALFORMED_RESPONSE"
CODE_MODEL_ABSENCE = "MODEL_ABSENCE"
CODE_DIMENSION = "DIMENSION_MISMATCH"
CODE_ORDERING = "ORDERING_MISMATCH"
CODE_HTTP = "HTTP_ERROR"
CODE_SCHEMA = "SCHEMA_FAIL"
CODE_STREAM = "STREAM_FAIL"
CODE_TOOL = "TOOL_FAIL"


class DiagnosticError(Exception):
    def __init__(self, code: str, capability: str, detail: str = "") -> None:
        self.code = code
        self.capability = capability
        self.detail = detail
        super().__init__(
            f"{code}:{capability}:{detail}" if detail else f"{code}:{capability}"
        )


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_root_env() -> None:
    """Minimal root .env loader: fill os.environ only for unset keys. No prints."""
    path = repo_root() / ".env"
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_quotes(value.strip())


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    llm_model: str
    embedding_model: str
    embedding_dimensions: int


def load_settings(*, load_env_file: bool = True) -> Settings:
    """Load settings from process env (and optionally root .env). Never prints secrets."""
    if load_env_file:
        load_root_env()
    key = (os.environ.get("SHOPAIKEY_API_KEY") or "").strip()
    if not key:
        raise DiagnosticError(CODE_MISSING_KEY, "config", "SHOPAIKEY_API_KEY")

    base = (os.environ.get("SHOPAIKEY_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    llm = (os.environ.get("LLM_MODEL") or LOCKED_CHAT_MODEL).strip()
    emb = (os.environ.get("EMBEDDING_MODEL") or LOCKED_EMBED_MODEL).strip()
    dim_raw = (os.environ.get("EMBEDDING_DIMENSIONS") or str(LOCKED_DIMENSIONS)).strip()
    try:
        dim = int(dim_raw)
    except ValueError as exc:
        raise DiagnosticError(CODE_MALFORMED, "config", "EMBEDDING_DIMENSIONS") from exc

    return Settings(
        base_url=base,
        api_key=key,
        llm_model=llm,
        embedding_model=emb,
        embedding_dimensions=dim,
    )


def redact(text: str, secret: str) -> str:
    if not text or not secret:
        return text
    out = text.replace(secret, "[REDACTED]")
    out = out.replace(f"Bearer {secret}", "Bearer [REDACTED]")
    out = out.replace(f"bearer {secret}", "bearer [REDACTED]")
    return out


def auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def emit_failure(
    *,
    code: str,
    capability: str,
    detail: str = "",
    secret: str = "",
    rows: list[tuple[str, str, str]] | None = None,
) -> int:
    """Common failure formatter: capability + concise code + FAIL marker; no secrets."""
    if rows is not None:
        print_table(rows)
    safe_detail = redact(detail, secret) if detail else ""
    if code == CODE_MISSING_KEY or (
        capability == "config" and "SHOPAIKEY_API_KEY" in (detail or "")
    ):
        print("MISSING_VARIABLE=SHOPAIKEY_API_KEY", file=sys.stderr)
    if safe_detail:
        print(f"ERROR={code}:{safe_detail}", file=sys.stderr)
    else:
        print(f"ERROR={code}:{capability}", file=sys.stderr)
    print(f"failed_capability={capability}")
    print("SHOPAIKEY_COMPATIBILITY=FAIL")
    return 1


def print_table(rows: list[tuple[str, str, str]]) -> None:
    print("capability | status | detail")
    print("--- | --- | ---")
    for name, status, detail in rows:
        print(f"{name} | {status} | {detail}")


def classify_http_error(exc: Exception, capability: str, secret: str) -> DiagnosticError:
    if isinstance(exc, httpx.TimeoutException):
        return DiagnosticError(CODE_TIMEOUT, capability, "request_timeout")
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return DiagnosticError(CODE_RATE_LIMIT, capability, f"status={status}")
        body = redact((exc.response.text or "")[:200], secret)
        return DiagnosticError(CODE_HTTP, capability, f"status={status}:{body}")
    if isinstance(exc, httpx.HTTPError):
        return DiagnosticError(CODE_HTTP, capability, redact(str(exc), secret)[:200])
    return DiagnosticError(CODE_MALFORMED, capability, redact(str(exc), secret)[:200])


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    secret: str,
    capability: str,
    json_body: dict[str, Any] | None = None,
) -> Any:
    try:
        resp = client.request(method, url, json=json_body)
        if resp.status_code == 429:
            raise DiagnosticError(CODE_RATE_LIMIT, capability, "status=429")
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise DiagnosticError(CODE_MALFORMED, capability, "non_json_body") from exc
    except DiagnosticError:
        raise
    except Exception as exc:
        raise classify_http_error(exc, capability, secret) from exc

"""Orchestrate seven ShopAIKey capability checks and CLI exit codes."""

from __future__ import annotations

import sys
from typing import Callable

import httpx

from shopaikey_diag.chat_checks import check_basic_chat, check_model_discovery
from shopaikey_diag.common import (
    CODE_MODEL_ABSENCE,
    LOCKED_CHAT_MODEL,
    REQUEST_TIMEOUT_S,
    DiagnosticError,
    Settings,
    auth_headers,
    emit_failure,
    load_settings,
    print_table,
    redact,
)
from shopaikey_diag.embeddings import check_scalar_batch_embeddings
from shopaikey_diag.streaming import check_ordered_text_streaming
from shopaikey_diag.schema_checks import check_structured_schema
from shopaikey_diag.tools_schema import (
    check_function_calling,
    check_tool_result_round_trip,
)


def run_checks(
    settings: Settings, results: list[tuple[str, str, str]]
) -> None:
    """Run all capability checks; append rows; raise DiagnosticError on first fail."""
    headers = auth_headers(settings.api_key)
    timeout = httpx.Timeout(REQUEST_TIMEOUT_S)
    checks: list[tuple[str, Callable[[httpx.Client, Settings], tuple[str, str]]]] = [
        ("model_discovery", check_model_discovery),
        ("basic_chat", check_basic_chat),
        ("function_calling", check_function_calling),
        ("tool_result_round_trip", check_tool_result_round_trip),
        ("structured_schema", check_structured_schema),
        ("ordered_text_streaming", check_ordered_text_streaming),
        ("scalar_batch_embeddings", check_scalar_batch_embeddings),
    ]
    with httpx.Client(headers=headers, timeout=timeout) as client:
        for name, fn in checks:
            try:
                status, detail = fn(client, settings)
                results.append((name, status, detail))
            except DiagnosticError as exc:
                results.append(
                    (
                        name,
                        "FAIL",
                        f"{exc.code}:{redact(exc.detail, settings.api_key)}",
                    )
                )
                raise


def main() -> int:
    try:
        settings = load_settings(load_env_file=True)
    except DiagnosticError as exc:
        return emit_failure(
            code=exc.code, capability=exc.capability, detail=exc.detail
        )

    if settings.llm_model != LOCKED_CHAT_MODEL:
        return emit_failure(
            code=CODE_MODEL_ABSENCE,
            capability="config",
            detail=f"llm={settings.llm_model} locked={LOCKED_CHAT_MODEL}",
        )

    print(f"httpx_version={httpx.__version__}")
    try:
        import pydantic as _pydantic

        print(f"pydantic_version={_pydantic.__version__}")
    except Exception:  # pragma: no cover
        print("pydantic_version=unknown")
    print(f"requested_llm_model={settings.llm_model}")
    print(f"requested_embedding_model={settings.embedding_model}")
    print(f"requested_embedding_dimensions={settings.embedding_dimensions}")
    print(f"base_url_host={settings.base_url.split('://', 1)[-1].split('/', 1)[0]}")

    rows: list[tuple[str, str, str]] = []
    try:
        run_checks(settings, rows)
        print_table(rows)
        print("SHOPAIKEY_COMPATIBILITY=PASS")
        return 0
    except DiagnosticError as exc:
        return emit_failure(
            code=exc.code,
            capability=exc.capability,
            detail=exc.detail,
            secret=settings.api_key,
            rows=rows,
        )
    except Exception as exc:  # pragma: no cover - unexpected
        safe = redact(str(exc), settings.api_key)[:200]
        return emit_failure(
            code="UNEXPECTED",
            capability="unknown",
            detail=safe,
            secret=settings.api_key,
            rows=rows,
        )


if __name__ == "__main__":
    raise SystemExit(main())

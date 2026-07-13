"""Model discovery and basic chat capability checks."""

from __future__ import annotations

import httpx

from shopaikey_diag.common import (
    CODE_MALFORMED,
    CODE_MODEL_ABSENCE,
    DiagnosticError,
    Settings,
    request_json,
)


def check_model_discovery(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    cap = "model_discovery"
    data = request_json(
        client,
        "GET",
        f"{settings.base_url}/models",
        secret=settings.api_key,
        capability=cap,
    )
    if not isinstance(data, dict) or "data" not in data:
        raise DiagnosticError(CODE_MALFORMED, cap, "models_missing_data")
    ids: set[str] = set()
    for item in data.get("data") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.add(item["id"])
    missing = []
    if settings.llm_model not in ids:
        missing.append(settings.llm_model)
    if settings.embedding_model not in ids:
        missing.append(settings.embedding_model)
    if missing:
        raise DiagnosticError(
            CODE_MODEL_ABSENCE,
            cap,
            "missing=" + ",".join(missing),
        )
    return (
        "PASS",
        f"chat={settings.llm_model} embed={settings.embedding_model} listed",
    )


def check_basic_chat(client: httpx.Client, settings: Settings) -> tuple[str, str]:
    cap = "basic_chat"
    body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 32,
        "messages": [
            {
                "role": "system",
                "content": "Reply with exactly the word PONG and nothing else.",
            },
            {"role": "user", "content": "PING"},
        ],
    }
    data = request_json(
        client,
        "POST",
        f"{settings.base_url}/chat/completions",
        secret=settings.api_key,
        capability=cap,
        json_body=body,
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "chat_shape") from exc
    if not isinstance(content, str) or not content.strip():
        raise DiagnosticError(CODE_MALFORMED, cap, "empty_content")
    model_obs = data.get("model") or settings.llm_model
    return "PASS", f"model={model_obs} content_len={len(content.strip())}"

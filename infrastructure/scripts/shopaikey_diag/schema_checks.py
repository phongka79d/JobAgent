"""Structured schema capability: strict, ordinary function, JSON mode + one repair."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from shopaikey_diag.common import (
    CODE_SCHEMA,
    DiagnosticError,
    Settings,
    redact,
    request_json,
)


class SyntheticCard(BaseModel):
    """Structured schema probe payload (side-effect-free)."""

    label: str = Field(..., min_length=1)
    value: int


CARD_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "value": {"type": "integer"},
    },
    "required": ["label", "value"],
    "additionalProperties": False,
}


def validate_card_payload(raw: Any) -> SyntheticCard:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return SyntheticCard.model_validate(raw)


def check_structured_schema(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    """Prefer strict schema; else ordinary function schema or JSON mode + one repair."""
    cap = "structured_schema"
    strategy = "unselected"
    url = f"{settings.base_url}/chat/completions"

    strict_body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 64,
        "messages": [
            {
                "role": "user",
                "content": (
                    'Return a SyntheticCard JSON object with label="alpha" and value=7.'
                ),
            }
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "synthetic_card",
                "strict": True,
                "schema": CARD_JSON_SCHEMA,
            },
        },
    }
    try:
        data = request_json(
            client,
            "POST",
            url,
            secret=settings.api_key,
            capability=cap,
            json_body=strict_body,
        )
        content = data["choices"][0]["message"]["content"]
        card = validate_card_payload(content)
        if card.label == "alpha" and card.value == 7:
            strategy = "strict_json_schema"
            return "PASS", f"strategy={strategy} label={card.label} value={card.value}"
    except (
        DiagnosticError,
        KeyError,
        IndexError,
        TypeError,
        ValidationError,
        json.JSONDecodeError,
    ):
        pass

    ordinary_body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 128,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Call synthetic_card with label=alpha and value=7. "
                    "Do not answer without the tool."
                ),
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "synthetic_card",
                    "description": "Emit a synthetic label/value card (side-effect-free).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "integer"},
                        },
                        "required": ["label", "value"],
                    },
                },
            }
        ],
        "tool_choice": {
            "type": "function",
            "function": {"name": "synthetic_card"},
        },
    }
    try:
        data = request_json(
            client,
            "POST",
            url,
            secret=settings.api_key,
            capability=cap,
            json_body=ordinary_body,
        )
        message = data["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        raw_args = tool_calls[0]["function"]["arguments"]
        card = validate_card_payload(raw_args)
        if card.label == "alpha" and card.value == 7:
            strategy = "ordinary_function_schema+pydantic"
            return "PASS", f"strategy={strategy} label={card.label} value={card.value}"
    except (
        DiagnosticError,
        KeyError,
        IndexError,
        TypeError,
        ValidationError,
        json.JSONDecodeError,
    ):
        pass

    def json_mode_call(messages: list[dict[str, str]]) -> SyntheticCard:
        body = {
            "model": settings.llm_model,
            "temperature": 0,
            "max_tokens": 64,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        data = request_json(
            client, "POST", url, secret=settings.api_key, capability=cap, json_body=body
        )
        content = data["choices"][0]["message"]["content"]
        return validate_card_payload(content)

    messages = [
        {
            "role": "system",
            "content": (
                'Respond with a JSON object only: {"label": string, "value": integer}.'
            ),
        },
        {
            "role": "user",
            "content": 'Produce label="alpha" and value=7.',
        },
    ]
    try:
        card = json_mode_call(messages)
        if card.label == "alpha" and card.value == 7:
            strategy = "json_mode+pydantic"
            return "PASS", f"strategy={strategy} label={card.label} value={card.value}"
    except (
        DiagnosticError,
        KeyError,
        IndexError,
        TypeError,
        ValidationError,
        json.JSONDecodeError,
    ):
        messages.append(
            {
                "role": "user",
                "content": (
                    'Repair: return only valid JSON with keys label="alpha" '
                    "and value=7 integers/strings as specified."
                ),
            }
        )
        try:
            card = json_mode_call(messages)
            if card.label == "alpha" and card.value == 7:
                strategy = "json_mode+pydantic+one_repair"
                return (
                    "PASS",
                    f"strategy={strategy} label={card.label} value={card.value}",
                )
        except (
            DiagnosticError,
            KeyError,
            IndexError,
            TypeError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            detail = redact(str(exc), settings.api_key)[:120]
            raise DiagnosticError(CODE_SCHEMA, cap, detail) from exc

    raise DiagnosticError(CODE_SCHEMA, cap, f"no_strategy_passed last={strategy}")

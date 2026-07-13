"""Synthetic tool, function-calling, and tool-result round-trip checks."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from shopaikey_diag.common import (
    CODE_MALFORMED,
    CODE_TOOL,
    DiagnosticError,
    Settings,
    request_json,
)


class SyntheticAddArgs(BaseModel):
    """Side-effect-free synthetic tool arguments."""

    a: int = Field(..., description="First integer operand")
    b: int = Field(..., description="Second integer operand")


def synthetic_add(a: int, b: int) -> dict[str, int]:
    """Side-effect-free pure function used for tool/schema probes."""
    return {"sum": a + b, "a": a, "b": b}


ADD_TOOL_ORDINARY: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "synthetic_add",
        "description": "Add two integers. Side-effect-free synthetic diagnostic tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First integer"},
                "b": {"type": "integer", "description": "Second integer"},
            },
            "required": ["a", "b"],
        },
    },
}


def parse_tool_call(
    message: dict[str, Any], capability: str
) -> tuple[str, str, SyntheticAddArgs]:
    tool_calls = message.get("tool_calls")
    if not tool_calls or not isinstance(tool_calls, list):
        raise DiagnosticError(CODE_TOOL, capability, "no_tool_calls")
    call = tool_calls[0]
    try:
        call_id = call["id"]
        fn = call["function"]
        name = fn["name"]
        raw_args = fn["arguments"]
    except (KeyError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, capability, "tool_call_shape") from exc
    if name != "synthetic_add":
        raise DiagnosticError(CODE_TOOL, capability, f"unexpected_tool={name}")
    try:
        parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        args = SyntheticAddArgs.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, capability, "tool_args_invalid") from exc
    return call_id, name, args


def check_function_calling(client: httpx.Client, settings: Settings) -> tuple[str, str]:
    cap = "function_calling"
    body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 128,
        "messages": [
            {
                "role": "user",
                "content": "Use synthetic_add with a=17 and b=25. Do not answer without the tool.",
            }
        ],
        "tools": [ADD_TOOL_ORDINARY],
        "tool_choice": {
            "type": "function",
            "function": {"name": "synthetic_add"},
        },
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
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "chat_shape") from exc
    call_id, name, args = parse_tool_call(message, cap)
    if args.a != 17 or args.b != 25:
        raise DiagnosticError(CODE_TOOL, cap, f"args_mismatch a={args.a} b={args.b}")
    return "PASS", f"tool={name} call_id_present={bool(call_id)} a={args.a} b={args.b}"


def check_tool_result_round_trip(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    cap = "tool_result_round_trip"
    user_msg = {
        "role": "user",
        "content": "Use synthetic_add with a=17 and b=25, then report the sum.",
    }
    first_body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 128,
        "messages": [user_msg],
        "tools": [ADD_TOOL_ORDINARY],
        "tool_choice": {
            "type": "function",
            "function": {"name": "synthetic_add"},
        },
    }
    first = request_json(
        client,
        "POST",
        f"{settings.base_url}/chat/completions",
        secret=settings.api_key,
        capability=cap,
        json_body=first_body,
    )
    try:
        assistant_msg = first["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "chat_shape") from exc
    call_id, _name, args = parse_tool_call(assistant_msg, cap)
    result = synthetic_add(args.a, args.b)
    second_body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 64,
        "messages": [
            user_msg,
            {
                "role": "assistant",
                "content": assistant_msg.get("content"),
                "tool_calls": assistant_msg.get("tool_calls"),
            },
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result),
            },
        ],
        "tools": [ADD_TOOL_ORDINARY],
    }
    second = request_json(
        client,
        "POST",
        f"{settings.base_url}/chat/completions",
        secret=settings.api_key,
        capability=cap,
        json_body=second_body,
    )
    try:
        final = second["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DiagnosticError(CODE_MALFORMED, cap, "final_shape") from exc
    if not isinstance(final, str) or not final.strip():
        raise DiagnosticError(CODE_TOOL, cap, "empty_final")
    if "42" not in final:
        raise DiagnosticError(CODE_TOOL, cap, "final_missing_sum")
    return "PASS", f"tool_result_sum={result['sum']} final_len={len(final.strip())}"

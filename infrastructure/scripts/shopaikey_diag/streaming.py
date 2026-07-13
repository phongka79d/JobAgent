"""Ordered text-streaming capability and pure SSE stream validation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import httpx

from shopaikey_diag.common import (
    CODE_MALFORMED,
    CODE_RATE_LIMIT,
    CODE_STREAM,
    CODE_TIMEOUT,
    DiagnosticError,
    Settings,
    auth_headers,
    classify_http_error,
)

EXPECTED_STREAM_TEXT = "1 2 3 4 5"
STREAM_PROMPT = "Count from 1 to 5 as digits separated by spaces only."


def _payload_from_line(line: str) -> str | None:
    """Extract SSE data payload; None means skip (blank, comment, or SSE meta)."""
    if not line:
        return None
    stripped = line.strip()
    if not stripped:
        return None
    # SSE comments and non-data fields are not content payloads.
    if stripped.startswith(":"):
        return None
    lower = stripped.lower()
    if lower.startswith(("event:", "id:", "retry:")):
        return None
    if stripped.startswith("data:") or lower.startswith("data:"):
        # Preserve exact payload after the first "data:" (case-insensitive).
        idx = stripped.lower().find("data:")
        return stripped[idx + 5 :].strip()
    # Bare terminal marker or JSON object (some proxies strip the data: prefix).
    if stripped == "[DONE]" or stripped.startswith("{"):
        return stripped
    raise DiagnosticError(CODE_MALFORMED, "ordered_text_streaming", "non_sse_line")


def consume_sse_payloads(
    payloads: Iterable[str],
    *,
    capability: str = "ordered_text_streaming",
) -> tuple[list[str], str | None, bool]:
    """Consume stream data payloads; never silently skip malformed JSON/shapes.

    Returns (nonempty_content_deltas, finish_reason, saw_done).
    """
    deltas: list[str] = []
    finish_reason: str | None = None
    saw_done = False

    for payload in payloads:
        if payload is None:
            continue
        if payload == "[DONE]":
            saw_done = True
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_json") from exc
        if not isinstance(chunk, dict):
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_chunk_type")
        # Usage/metadata-only SSE events may omit or empty `choices`; that is not a
        # content payload. Missing/non-list `choices` on other events is malformed.
        if "choices" not in chunk:
            if any(k in chunk for k in ("usage", "id", "object", "model")):
                continue
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_shape")
        choices = chunk["choices"]
        if not isinstance(choices, list):
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_choices_type")
        if not choices:
            continue
        choice = choices[0]
        if not isinstance(choice, dict):
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_choice_type")

        fr = choice.get("finish_reason")
        if isinstance(fr, str) and fr.strip():
            finish_reason = fr.strip()
        elif fr is not None and fr != "":
            # Non-string non-empty finish markers are malformed.
            raise DiagnosticError(CODE_MALFORMED, capability, "finish_reason_type")

        if "delta" not in choice and fr is None:
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_missing_delta")

        delta: Any = choice.get("delta")
        if delta is None:
            continue
        if not isinstance(delta, dict):
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_delta_type")
        piece = delta.get("content")
        if piece is None:
            continue
        if not isinstance(piece, str):
            raise DiagnosticError(CODE_MALFORMED, capability, "stream_content_type")
        if piece:
            deltas.append(piece)

    return deltas, finish_reason, saw_done


def assert_ordered_stream_result(
    deltas: list[str],
    finish_reason: str | None,
    saw_done: bool,
    *,
    capability: str = "ordered_text_streaming",
    expected: str = EXPECTED_STREAM_TEXT,
) -> tuple[str, str]:
    """Require exact normalized sequence, non-empty finish reason, and [DONE]."""
    if not deltas:
        raise DiagnosticError(CODE_STREAM, capability, "no_nonempty_deltas")
    joined = "".join(deltas)
    normalized = " ".join(joined.split())
    if normalized != expected:
        raise DiagnosticError(
            CODE_STREAM,
            capability,
            f"sequence_mismatch expected={expected!r} got={normalized!r}",
        )
    if not finish_reason or not str(finish_reason).strip():
        raise DiagnosticError(CODE_STREAM, capability, "missing_finish_reason")
    if not saw_done:
        raise DiagnosticError(CODE_STREAM, capability, "missing_done")
    return (
        "PASS",
        (
            f"delta_count={len(deltas)} joined={normalized!r} "
            f"finish_reason={finish_reason} done=yes ordered=yes"
        ),
    )


def evaluate_sse_lines(
    lines: Iterable[str],
    *,
    capability: str = "ordered_text_streaming",
    expected: str = EXPECTED_STREAM_TEXT,
) -> tuple[str, str]:
    """Pure helper for local fake-stream validation (no network)."""
    payloads: list[str] = []
    for line in lines:
        payload = _payload_from_line(line)
        if payload is not None:
            payloads.append(payload)
    deltas, finish_reason, saw_done = consume_sse_payloads(
        payloads, capability=capability
    )
    return assert_ordered_stream_result(
        deltas, finish_reason, saw_done, capability=capability, expected=expected
    )


def check_ordered_text_streaming(
    client: httpx.Client, settings: Settings
) -> tuple[str, str]:
    cap = "ordered_text_streaming"
    body = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 48,
        "stream": True,
        "messages": [{"role": "user", "content": STREAM_PROMPT}],
    }
    payloads: list[str] = []
    try:
        with client.stream(
            "POST",
            f"{settings.base_url}/chat/completions",
            json=body,
            headers=auth_headers(settings.api_key),
        ) as resp:
            if resp.status_code == 429:
                raise DiagnosticError(CODE_RATE_LIMIT, cap, "status=429")
            resp.raise_for_status()
            for line in resp.iter_lines():
                payload = _payload_from_line(line)
                if payload is None:
                    continue
                payloads.append(payload)
                if payload == "[DONE]":
                    break
    except DiagnosticError:
        raise
    except httpx.TimeoutException as exc:
        raise DiagnosticError(CODE_TIMEOUT, cap, "stream_timeout") from exc
    except httpx.HTTPStatusError as exc:
        raise classify_http_error(exc, cap, settings.api_key) from exc
    except httpx.HTTPError as exc:
        raise classify_http_error(exc, cap, settings.api_key) from exc

    deltas, finish_reason, saw_done = consume_sse_payloads(payloads, capability=cap)
    return assert_ordered_stream_result(
        deltas, finish_reason, saw_done, capability=cap, expected=EXPECTED_STREAM_TEXT
    )

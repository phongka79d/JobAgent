"""Shared ShopAIKey provider error classification and bounded one-retry loop.

Ownership
---------
* Timeout / rate-limit / generic provider failure codes and classification.
* At most one retry for timeout or rate-limit before a stable sanitized failure.
* Schema/parse failures are re-raised for domain repair owners; they are never
  retried as provider errors.

Domain modules (``profile_extraction``, ``jd_extraction``,
``cv_document_extraction``) keep their own prompts, structured schemas,
coercion, and domain exception types. They wrap :class:`ProviderRetryError`
into their stable failure surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Final, TypeVar

from pydantic import ValidationError

# Stable failure codes shared by profile and JD extraction surfaces.
FAILURE_PROVIDER_TIMEOUT: Final[str] = "PROVIDER_TIMEOUT"
FAILURE_PROVIDER_RATE_LIMIT: Final[str] = "PROVIDER_RATE_LIMIT"
FAILURE_PROVIDER_ERROR: Final[str] = "PROVIDER_ERROR"

MAX_PROVIDER_RETRIES: Final[int] = 1

# Parse/schema failures belong to domain repair paths, not provider retry.
SCHEMA_ERROR_TYPES: Final[tuple[type[BaseException], ...]] = (
    ValidationError,
    json.JSONDecodeError,
    TypeError,
    ValueError,
)

_RETRYABLE_CODES: Final[frozenset[str]] = frozenset(
    {FAILURE_PROVIDER_TIMEOUT, FAILURE_PROVIDER_RATE_LIMIT}
)

T = TypeVar("T")


class ProviderRetryError(Exception):
    """Provider call failed after classification (and optional one retry)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_rate_limit_error(exc: BaseException) -> bool:
    """True when the exception indicates an HTTP 429 / rate-limit failure."""
    name = type(exc).__name__
    if name in {"RateLimitError", "APIRateLimitError"}:
        return True
    module = type(exc).__module__ or ""
    if "openai" in module and "rate" in name.lower():
        return True
    status = getattr(exc, "status_code", None)
    return status == 429


def is_timeout_error(exc: BaseException) -> bool:
    """True when the exception indicates a connect/read/API timeout."""
    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__
    if name in {"APITimeoutError", "TimeoutException", "ReadTimeout", "ConnectTimeout"}:
        return True
    module = type(exc).__module__ or ""
    return "timeout" in name.lower() and (
        "openai" in module or "httpx" in module or "httpcore" in module
    )


def classify_provider_error(exc: BaseException) -> str:
    """Map a provider exception to a stable application failure code."""
    if is_rate_limit_error(exc):
        return FAILURE_PROVIDER_RATE_LIMIT
    if is_timeout_error(exc):
        return FAILURE_PROVIDER_TIMEOUT
    return FAILURE_PROVIDER_ERROR


def is_retryable_provider_code(code: str) -> bool:
    """True for timeout/rate-limit codes eligible for the single retry."""
    return code in _RETRYABLE_CODES


def invoke_with_provider_retry(
    call: Callable[[], T],
    *,
    schema_error_types: Sequence[type[BaseException]] = SCHEMA_ERROR_TYPES,
) -> tuple[T, int]:
    """Invoke ``call``; retry once on timeout/rate-limit only.

    Exactly one retry is hard-coded via ``MAX_PROVIDER_RETRIES`` (no public
    override). Retryable failures make at most two total attempts.

    Returns
    -------
    tuple[T, int]
        ``(result, retries_used)`` where ``retries_used`` is 0 or 1.

    Raises
    ------
    schema errors
        Re-raised unchanged so domain owners can run at most one repair.
    ProviderRetryError
        After exhausting the single retryable attempt, or on non-retryable
        provider failures. Message is sanitized (exception type name only).
    """
    retries_used = 0
    last_code = FAILURE_PROVIDER_ERROR
    last_message = "provider call failed"
    schema_types = tuple(schema_error_types)
    # Hard cap: initial attempt + exactly one retry (two attempts total).
    max_attempts = MAX_PROVIDER_RETRIES + 1

    for attempt in range(max_attempts):
        try:
            return call(), retries_used
        except schema_types:
            # Schema/parse failures are handled by domain repair, not provider retry.
            raise
        except ProviderRetryError:
            raise
        except Exception as exc:
            code = classify_provider_error(exc)
            last_code = code
            last_message = f"provider error: {type(exc).__name__}"
            if is_retryable_provider_code(code) and attempt < MAX_PROVIDER_RETRIES:
                retries_used += 1
                continue
            raise ProviderRetryError(code, last_message) from exc

    raise ProviderRetryError(last_code, last_message)


__all__ = [
    "FAILURE_PROVIDER_ERROR",
    "FAILURE_PROVIDER_RATE_LIMIT",
    "FAILURE_PROVIDER_TIMEOUT",
    "MAX_PROVIDER_RETRIES",
    "SCHEMA_ERROR_TYPES",
    "ProviderRetryError",
    "classify_provider_error",
    "invoke_with_provider_retry",
    "is_rate_limit_error",
    "is_retryable_provider_code",
    "is_timeout_error",
]

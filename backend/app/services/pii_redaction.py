"""Deterministic PII redaction for CV text before any external call.

Removes, at minimum (Master Plan §10.2 / Plan 4 §7.3):

- email addresses
- phone numbers
- lines labeled as address / contact address

Name, education, experience, and skill text remain available. Redaction is pure
and fail-closed: any unexpected failure raises a stable code and must prevent
ShopAIKey / provider invocation. Exception messages never embed source text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# ---------------------------------------------------------------------------
# Stable error surface
# ---------------------------------------------------------------------------


class PiiRedactionErrorCode(StrEnum):
    """Stable, non-sensitive redaction failure codes."""

    REDACTION_FAILED = "REDACTION_FAILED"
    INVALID_INPUT = "INVALID_INPUT"


class PiiRedactionError(Exception):
    """Sanitized redaction failure (code-only str/repr; no source text)."""

    def __init__(self, code: PiiRedactionErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"PiiRedactionError(code={self.code.value!r})"


# ---------------------------------------------------------------------------
# Patterns (deterministic; applied in a fixed order)
# ---------------------------------------------------------------------------

# Email: local@domain with common TLD; avoids matching pure domain tokens alone.
_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b[a-z0-9](?:[a-z0-9._%+\-]*[a-z0-9])?@"
    r"(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,}\b",
)

# Phone: international/local forms with separators, plus contiguous digit runs.
# Lower digit bound is intentionally high so years, room numbers, and short
# numeric codes are not redacted (conservative false-positive boundary).
# Examples: +1 555-123-4567, (555) 123-4567, 555.123.4567, +44 20 7946 0958,
# 5551234567, 0901234567, 02079460958, 447911123456
_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<!\w)"
    r"(?:"
    r"\+\d{1,3}[\s.\-()]{0,3}(?:\d[\s.\-()]{0,3}){6,14}\d"
    r"|"
    r"\(?\d{2,4}\)?[\s.\-](?:\d[\s.\-]?){5,12}\d"
    r"|"
    # Contiguous local / international-without-plus: E.164-ish 10–15 digits.
    r"\d{10,15}"
    r")"
    r"(?!\w)",
)

# Whole line labeled as address / contact address (and common variants).
# Colon-required after the label so compounds like "english-address-keep"
# are never treated as labeled contact lines. Case-insensitive.
_LABELED_ADDRESS_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?im)^[ \t]*(?:"
    r"contact[ \t]*address"
    r"|mailing[ \t]*address"
    r"|home[ \t]*address"
    r"|residential[ \t]*address"
    r"|street[ \t]*address"
    r"|address"
    r")[ \t]*:[ \t]*.+$",
)

# Inline labeled address fragments mid-line. Colon-required; stop at the next
# sentence terminator so following sections (Skills, Education) survive.
_LABELED_ADDRESS_INLINE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:"
    r"contact[ \t]*address"
    r"|mailing[ \t]*address"
    r"|home[ \t]*address"
    r"|residential[ \t]*address"
    r"|street[ \t]*address"
    r"|address"
    r")[ \t]*:[ \t]*[^\n\r.]+\.?",
)

# Collapse runs of spaces/tabs left by removals (preserve newlines).
_HORIZONTAL_WS_RE: Final[re.Pattern[str]] = re.compile(r"[^\S\n\r]{2,}")


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Internal redacted-text boundary for structured extraction.

    ``text`` is contact-scrubbed layout text safe for provider structured
    extraction. Counts are aggregate metrics only (never original substrings).
    """

    text: str
    emails_removed: int
    phones_removed: int
    address_lines_removed: int


def redact_pii(text: str) -> RedactionResult:
    """Deterministically remove email, phone, and labeled address contact data.

    Raises
    ------
    PiiRedactionError
        On invalid input type or unexpected redaction failure. Callers must
        treat any raised error as fail-closed and must not invoke an external
        provider with the original text.
    """
    if not isinstance(text, str):
        raise PiiRedactionError(PiiRedactionErrorCode.INVALID_INPUT)

    try:
        working = text
        emails_removed = 0
        phones_removed = 0
        address_lines_removed = 0

        # Address lines first so email/phone on those lines are dropped with them.
        working, n_addr_lines = _LABELED_ADDRESS_LINE_RE.subn("", working)
        address_lines_removed += n_addr_lines

        working, n_addr_inline = _LABELED_ADDRESS_INLINE_RE.subn("", working)
        address_lines_removed += n_addr_inline

        working, n_email = _EMAIL_RE.subn("", working)
        emails_removed += n_email

        working, n_phone = _PHONE_RE.subn("", working)
        phones_removed += n_phone

        working = _HORIZONTAL_WS_RE.sub(" ", working)
        # Trim trailing spaces on each line without dropping blank line structure.
        working = "\n".join(line.rstrip(" \t") for line in working.splitlines())
        if text.endswith("\n") and not working.endswith("\n"):
            working += "\n"

        return RedactionResult(
            text=working,
            emails_removed=emails_removed,
            phones_removed=phones_removed,
            address_lines_removed=address_lines_removed,
        )
    except PiiRedactionError:
        raise
    except Exception:
        raise PiiRedactionError(PiiRedactionErrorCode.REDACTION_FAILED) from None


def assert_no_contact_sentinels(text: str, sentinels: list[str] | tuple[str, ...]) -> None:
    """Raise REDACTION_FAILED if any contact sentinel remains in ``text``.

    Used by tests and optional pipeline self-checks. Does not embed sentinels
    into the exception message.
    """
    if not isinstance(text, str):
        raise PiiRedactionError(PiiRedactionErrorCode.INVALID_INPUT)
    try:
        for sentinel in sentinels:
            if sentinel and sentinel in text:
                raise PiiRedactionError(PiiRedactionErrorCode.REDACTION_FAILED)
    except PiiRedactionError:
        raise
    except Exception:
        raise PiiRedactionError(PiiRedactionErrorCode.REDACTION_FAILED) from None

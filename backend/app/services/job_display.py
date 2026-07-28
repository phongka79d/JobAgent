"""Pure stable display labels for persisted Jobs."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    return cleaned or None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _first_meaningful_sentence(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    first = _SENTENCE_END.split(cleaned, maxsplit=1)[0].rstrip(".!? ")
    return first or None


def derive_saved_job_display_label(
    *,
    title: str | None,
    company: str | None,
    summary: str | None,
    saved_at: datetime,
) -> str:
    clean_title = _clean(title)
    clean_company = _clean(company)
    if clean_title and clean_company:
        return f"{clean_title} \N{MIDDLE DOT} {clean_company}"[:140]
    if clean_title or clean_company:
        return (clean_title or clean_company or "")[:140]
    sentence = _first_meaningful_sentence(summary)
    if sentence:
        return sentence[:120]
    return f"Untitled saved job \N{MIDDLE DOT} {_aware_utc(saved_at).date().isoformat()}"


__all__ = ["derive_saved_job_display_label"]

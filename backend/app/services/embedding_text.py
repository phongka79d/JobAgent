"""Shared embedding whitespace normalization and versioned text builders.

Plan 5 §7.5 / Master §17.3: one whitespace owner and ``build_job_embedding_text_v1``.
Plan 6 extends this module with the Candidate builder; it must not create a
second whitespace normalizer. No provider calls or E5 query/passage prefixes.
"""

from __future__ import annotations

from typing import Final

from app.schemas.jobs import JobPostExtraction

# Explicit representation version (code/config migration, not silent change).
JOB_EMBEDDING_TEXT_VERSION: Final[str] = "v1"

# Deterministic separators (byte-stable across equivalent structured inputs).
_SECTION_SEP: Final[str] = "\n"
_LIST_ITEM_PREFIX: Final[str] = "- "
_SKILL_SEP: Final[str] = ", "


def normalize_embedding_whitespace(text: str) -> str:
    """Shared embedding whitespace normalizer: trim and collapse runs to spaces.

    This is the sole whitespace policy for versioned embedding representations
    (Job v1 and later Candidate). It does not NFKC, casefold, or strip punctuation.
    """
    return " ".join((text or "").split())


def _section(label: str, body: str) -> str:
    return f"{label}:{_SECTION_SEP}{body}" if body else f"{label}:"


def _bullet_list(items: list[str]) -> str:
    return _SECTION_SEP.join(f"{_LIST_ITEM_PREFIX}{item}" for item in items)


def build_job_embedding_text_v1(extraction: JobPostExtraction) -> str:
    """Build versioned Job embedding text from structured extraction only.

    Field order (exact)::

        title + summary + responsibilities + required skills + preferred skills

    Uses canonical skill ``display_name`` values and deterministic separators.
    Does not include company, quality, raw HTML, E5 prefixes, or aliases.
    """
    title = normalize_embedding_whitespace(extraction.title or "")
    summary = normalize_embedding_whitespace(extraction.summary)

    responsibilities: list[str] = []
    for raw in extraction.responsibilities:
        cleaned = normalize_embedding_whitespace(raw)
        if cleaned:
            responsibilities.append(cleaned)

    required: list[str] = []
    for job_skill in extraction.required_skills:
        name = normalize_embedding_whitespace(job_skill.skill.display_name)
        if name:
            required.append(name)

    preferred: list[str] = []
    for job_skill in extraction.preferred_skills:
        name = normalize_embedding_whitespace(job_skill.skill.display_name)
        if name:
            preferred.append(name)

    parts = [
        _section("title", title),
        _section("summary", summary),
        _section("responsibilities", _bullet_list(responsibilities)),
        _section("required_skills", _SKILL_SEP.join(required)),
        _section("preferred_skills", _SKILL_SEP.join(preferred)),
    ]
    return _SECTION_SEP.join(parts)

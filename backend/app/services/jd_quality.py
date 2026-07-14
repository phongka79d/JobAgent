"""Deterministic JD quality classification (Plan 5 §7.4 / Master §7.6).

Single implementation owner for ``job_posts.jd_quality``. Classification runs
only after a fully validated ``JobPostExtraction``. Quality is never part of the
extraction payload; contact-only or insufficient evidence yields
``unscorable`` as a successful processed outcome, not a processing failure.

Executable rules (task 01A / Plan 5):
- usable signal: at least one non-blank responsibility, or one skill (required
  or preferred) with at least one non-blank evidence snippet
- scoring groups (four): known seniority (not ``unknown``), any experience
  bound present, non-blank location, known work mode (not ``unknown``)
- ``full``: non-blank title and summary, usable signal, and at least three
  known scoring groups
- ``partial``: non-blank summary and usable signal, but not ``full``
- else: ``unscorable``

No provider, persistence, graph, or tool behavior lives here.
"""

from __future__ import annotations

from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
)
from app.schemas.jobs import JobPostExtraction, JobSkill


def _non_blank(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _skill_has_evidence(skill: JobSkill) -> bool:
    return any(_non_blank(snippet) for snippet in skill.evidence)


def _has_usable_signal(extraction: JobPostExtraction) -> bool:
    if any(_non_blank(item) for item in extraction.responsibilities):
        return True
    for skill in (*extraction.required_skills, *extraction.preferred_skills):
        if _skill_has_evidence(skill):
            return True
    return False


def _scoring_group_count(extraction: JobPostExtraction) -> int:
    count = 0
    if extraction.seniority != "unknown":
        count += 1
    if (
        extraction.min_experience_years is not None
        or extraction.max_experience_years is not None
    ):
        count += 1
    if _non_blank(extraction.location):
        count += 1
    if extraction.work_mode != "unknown":
        count += 1
    return count


def classify_jd_quality(extraction: JobPostExtraction) -> str:
    """Return exactly ``full``, ``partial``, or ``unscorable`` for validated facts."""
    has_summary = _non_blank(extraction.summary)
    has_signal = _has_usable_signal(extraction)

    if (
        _non_blank(extraction.title)
        and has_summary
        and has_signal
        and _scoring_group_count(extraction) >= 3
    ):
        return JOB_JD_QUALITY_FULL

    if has_summary and has_signal:
        return JOB_JD_QUALITY_PARTIAL

    return JOB_JD_QUALITY_UNSCORABLE

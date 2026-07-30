"""Non-blocking JD-fit warnings for selected tailored CV versions."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from app.schemas.cv_tailoring import SourceBoundText, TailoredCVContent, TailoredItem
from app.schemas.jobs import JobPostExtraction, JobSkill
from app.services.skill_assertion_guard import normalize_assertion_text


def _bound_texts(item: TailoredItem) -> Iterable[SourceBoundText]:
    for value in (item.title, item.subtitle, item.date_text, item.location):
        if value is not None:
            yield value
    yield item.body
    yield from item.bullets
    for attribute in item.attributes:
        yield from attribute.values


def _content_blob(content: TailoredCVContent) -> str:
    parts: list[str] = []
    for section in content.sections:
        parts.append(section.heading)
        for item in section.items:
            parts.extend(value.text for value in _bound_texts(item) if value.text)
    return "\n".join(parts)


def _label_occurs(label: str, text: str) -> bool:
    normalized_label = normalize_assertion_text(label)
    normalized_text = normalize_assertion_text(text)
    return bool(normalized_label) and bool(
        re.search(rf"(?<!\w){re.escape(normalized_label)}(?!\w)", normalized_text)
    )


def _skill_labels(skills: Sequence[JobSkill]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        label = skill.skill.display_name.strip()
        key = normalize_assertion_text(label)
        if not label or not key or key in seen:
            continue
        seen.add(key)
        labels.append(label[:120])
    return labels


def _covered_labels(content: TailoredCVContent, labels: Sequence[str]) -> set[str]:
    blob = _content_blob(content)
    return {
        normalize_assertion_text(label)
        for label in labels
        if _label_occurs(label, blob)
    }


def _lost_labels(
    *,
    content: TailoredCVContent,
    parent: TailoredCVContent,
    labels: Sequence[str],
) -> list[str]:
    parent_covered = _covered_labels(parent, labels)
    current_covered = _covered_labels(content, labels)
    lost_keys = parent_covered - current_covered
    return [
        label
        for label in labels
        if normalize_assertion_text(label) in lost_keys
    ]


def fit_warning_for_content_change(
    *,
    content: TailoredCVContent,
    parent: TailoredCVContent | None,
    job_context: JobPostExtraction | None,
) -> str | None:
    """Return a warning when selected content reduces parent JD skill coverage."""
    if parent is None or job_context is None:
        return None
    required = _skill_labels(job_context.required_skills)
    lost_required = _lost_labels(content=content, parent=parent, labels=required)
    if lost_required:
        return (
            "This version mentions fewer required JD skills than its parent: "
            f"{', '.join(lost_required[:3])}."
        )
    preferred = _skill_labels(job_context.preferred_skills)
    lost_preferred = _lost_labels(content=content, parent=parent, labels=preferred)
    if lost_preferred:
        return (
            "This version mentions fewer preferred JD skills than its parent: "
            f"{', '.join(lost_preferred[:3])}."
        )
    return None


__all__ = ["fit_warning_for_content_change"]

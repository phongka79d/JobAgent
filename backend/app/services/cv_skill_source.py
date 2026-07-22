"""Bounded source projections for Candidate skill provider calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Final

from app.schemas.cv_document import CVDocument, CVEntry, CVSection
from app.services.cv_skill_contracts import (
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    CandidateSkillBatch,
    CandidateSkillEntryContext,
    CandidateSkillExtractionError,
    CandidateSkillSourceRecord,
    serialize_source_records,
)

# ponytail: this minimum reserves the fixed JSON identity envelope; raise it only
# if the allowlisted record keys grow, while keeping the caller's bound explicit.
_MIN_SOURCE_BATCH_CHARS: Final[int] = 256


def _record_for_entry(
    section: CVSection,
    entry: CVEntry,
    *,
    source_order: int,
) -> CandidateSkillSourceRecord:
    attributes = tuple(
        (
            key,
            tuple(value) if isinstance(value, list) else value,
        )
        for key, value in entry.attributes.items()
    )
    return CandidateSkillSourceRecord(
        source_order=source_order,
        section_id=section.id,
        section_heading=section.heading,
        section_kind=section.kind,
        entry_id=entry.id,
        entry_ordinal=entry.ordinal,
        title=entry.title,
        subtitle=entry.subtitle,
        date_text=entry.date_text,
        location=entry.location,
        body=entry.body,
        bullets=tuple(entry.bullets),
        attributes=attributes,
    )


def _empty_content(record: CandidateSkillSourceRecord) -> CandidateSkillSourceRecord:
    return replace(
        record,
        title=None,
        subtitle=None,
        date_text=None,
        location=None,
        body="",
        bullets=(),
        attributes=(),
    )


def _bounded_value_records(
    value: str,
    *,
    build: Callable[[str], CandidateSkillSourceRecord],
    max_chars: int,
) -> tuple[CandidateSkillSourceRecord, ...]:
    remaining = value
    records: list[CandidateSkillSourceRecord] = []
    while remaining:
        candidate = build(remaining)
        if len(serialize_source_records((candidate,))) <= max_chars:
            records.append(candidate)
            break
        low, high, best = 1, len(remaining), 0
        while low <= high:
            middle = (low + high) // 2
            size = len(serialize_source_records((build(remaining[:middle]),)))
            if size <= max_chars:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        if best == 0:
            raise CandidateSkillExtractionError(
                FAILURE_INVALID_STRUCTURED_OUTPUT,
                "Candidate skill source metadata exceeds the batch bound",
            )
        split_at = best
        whitespace = remaining.rfind(" ", 0, best + 1)
        if whitespace >= max(1, best // 2):
            split_at = whitespace
        piece = remaining[:split_at].rstrip()
        if not piece:
            piece = remaining[:best]
            split_at = best
        records.append(build(piece))
        remaining = remaining[split_at:].lstrip()
    return tuple(records)


def _fragment_record(
    record: CandidateSkillSourceRecord,
    *,
    max_chars: int,
) -> tuple[CandidateSkillSourceRecord, ...]:
    if len(serialize_source_records((record,))) <= max_chars:
        return (record,)
    base = _empty_content(record)
    fragments: list[CandidateSkillSourceRecord] = []
    scalar_values = (
        (record.title, lambda value: replace(base, title=value)),
        (record.subtitle, lambda value: replace(base, subtitle=value)),
        (record.date_text, lambda value: replace(base, date_text=value)),
        (record.location, lambda value: replace(base, location=value)),
        (record.body, lambda value: replace(base, body=value)),
    )
    for value, build in scalar_values:
        if value:
            fragments.extend(
                _bounded_value_records(value, build=build, max_chars=max_chars)
            )
    for bullet in record.bullets:
        fragments.extend(
            _bounded_value_records(
                bullet,
                build=lambda value: replace(base, bullets=(value,)),
                max_chars=max_chars,
            )
        )
    for key, attribute in record.attributes:
        values = attribute if isinstance(attribute, tuple) else (attribute,)
        for value in values:
            as_list = isinstance(attribute, tuple)

            def build_attribute(part: str) -> CandidateSkillSourceRecord:
                projected: str | tuple[str, ...] = (part,) if as_list else part
                return replace(base, attributes=((key, projected),))

            fragments.extend(
                _bounded_value_records(
                    value,
                    build=build_attribute,
                    max_chars=max_chars,
                )
            )
    if fragments:
        return tuple(fragments)
    if len(serialize_source_records((base,))) <= max_chars:
        return (base,)
    raise CandidateSkillExtractionError(
        FAILURE_INVALID_STRUCTURED_OUTPUT,
        "Candidate skill source metadata exceeds the batch bound",
    )


def _substantive_entry_text(entry: CVEntry) -> str:
    values: list[str] = [entry.body, *entry.bullets]
    for value in entry.attributes.values():
        values.extend(value if isinstance(value, list) else (value,))
    return "\n".join(item for item in values if item)


def build_source_batches(
    document: CVDocument,
    *,
    max_chars: int,
) -> tuple[
    tuple[CandidateSkillBatch, ...],
    dict[str, CandidateSkillEntryContext],
]:
    """Project every entry, fragment oversized values, and partition by JSON size."""
    if max_chars < _MIN_SOURCE_BATCH_CHARS:
        raise CandidateSkillExtractionError(
            FAILURE_INVALID_STRUCTURED_OUTPUT,
            "Candidate skill batch character bound is too small",
        )
    records: list[CandidateSkillSourceRecord] = []
    contexts: dict[str, CandidateSkillEntryContext] = {}
    source_order = 0
    for section in document.sections:
        for entry in section.entries:
            if entry.id in contexts:
                raise CandidateSkillExtractionError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    "CV entry IDs must be unique for skill extraction",
                )
            metadata = tuple(
                item
                for item in (
                    entry.title,
                    entry.subtitle,
                    entry.date_text,
                    entry.location,
                )
                if item
            )
            contexts[entry.id] = CandidateSkillEntryContext(
                section=section,
                source_order=source_order,
                substantive_text=_substantive_entry_text(entry),
                metadata_values=metadata,
            )
            record = _record_for_entry(section, entry, source_order=source_order)
            records.extend(_fragment_record(record, max_chars=max_chars))
            source_order += 1

    batches: list[CandidateSkillBatch] = []
    current: list[CandidateSkillSourceRecord] = []
    for record in records:
        candidate = [*current, record]
        serialized = serialize_source_records(candidate)
        if current and len(serialized) > max_chars:
            current_serialized = serialize_source_records(current)
            batches.append(CandidateSkillBatch(tuple(current), current_serialized))
            current = [record]
            continue
        current = candidate
    if current:
        batches.append(
            CandidateSkillBatch(tuple(current), serialize_source_records(current))
        )
    return tuple(batches), contexts


__all__ = [
    "build_source_batches",
]

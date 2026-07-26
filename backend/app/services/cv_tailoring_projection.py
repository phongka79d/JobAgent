"""Deterministic source-fact bank and baseline tailored-CV projection."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote

from app.schemas.cv_document import CVDocument, CVEntry
from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredAttribute,
    TailoredCVContent,
    TailoredFactEvidence,
    TailoredHeaderSnapshot,
    TailoredItem,
    TailoredSection,
)
from app.schemas.profile import CandidateProfile


@dataclass(frozen=True, slots=True)
class TailoringBaseline:
    content: TailoredCVContent
    fact_bank: dict[str, TailoredFactEvidence]
    approved_skill_labels: tuple[str, ...]


def source_fact_id(
    *, source_hash: str, section_id: str, entry_id: str, field_path: str
) -> str:
    material = "\0".join((source_hash, section_id, entry_id, field_path))
    return "sf_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _bound_text(
    text: str,
    *,
    source_hash: str,
    section_id: str,
    entry_id: str,
    field_path: str,
    fact_bank: dict[str, TailoredFactEvidence],
) -> SourceBoundText:
    fact_ids: list[str] = []
    if text:
        fact_id = source_fact_id(
            source_hash=source_hash,
            section_id=section_id,
            entry_id=entry_id,
            field_path=field_path,
        )
        fact_bank[fact_id] = TailoredFactEvidence(
            fact_id=fact_id,
            section_id=section_id,
            source_entry_id=entry_id,
            field_path=field_path,
            source_text=text,
        )
        fact_ids.append(fact_id)
    return SourceBoundText(text=text, source_fact_ids=fact_ids)


def _optional_bound_text(
    text: str | None,
    *,
    source_hash: str,
    section_id: str,
    entry_id: str,
    field_path: str,
    fact_bank: dict[str, TailoredFactEvidence],
) -> SourceBoundText | None:
    if text is None:
        return None
    return _bound_text(
        text,
        source_hash=source_hash,
        section_id=section_id,
        entry_id=entry_id,
        field_path=field_path,
        fact_bank=fact_bank,
    )


def _project_entry(
    entry: CVEntry,
    *,
    source_hash: str,
    section_id: str,
    fact_bank: dict[str, TailoredFactEvidence],
) -> TailoredItem:
    def bound(text: str, field_path: str) -> SourceBoundText:
        return _bound_text(
            text,
            source_hash=source_hash,
            section_id=section_id,
            entry_id=entry.id,
            field_path=field_path,
            fact_bank=fact_bank,
        )

    def optional_bound(
        text: str | None, field_path: str
    ) -> SourceBoundText | None:
        return _optional_bound_text(
            text,
            source_hash=source_hash,
            section_id=section_id,
            entry_id=entry.id,
            field_path=field_path,
            fact_bank=fact_bank,
        )

    attributes: list[TailoredAttribute] = []
    for name, raw_value in entry.attributes.items():
        raw_values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not raw_values:
            continue
        escaped_name = quote(name, safe="")
        values = [
            bound(value, f"attributes.{escaped_name}[{index}]")
            for index, value in enumerate(raw_values)
        ]
        attributes.append(TailoredAttribute(name=name, values=values))

    return TailoredItem(
        id=entry.id,
        source_entry_id=entry.id,
        title=optional_bound(entry.title, "title"),
        subtitle=optional_bound(entry.subtitle, "subtitle"),
        date_text=optional_bound(entry.date_text, "date_text"),
        location=optional_bound(entry.location, "location"),
        body=bound(entry.body, "body"),
        bullets=[
            bound(bullet, f"bullets[{index}]")
            for index, bullet in enumerate(entry.bullets)
        ],
        attributes=attributes,
    )


def project_tailoring_baseline(
    document: CVDocument,
    *,
    profile: CandidateProfile,
    source_hash: str,
) -> TailoringBaseline:
    fact_bank: dict[str, TailoredFactEvidence] = {}
    sections = [
        TailoredSection(
            id=section.id,
            ordinal=section.ordinal,
            heading=section.heading,
            kind=section.kind,
            items=[
                _project_entry(
                    entry,
                    source_hash=source_hash,
                    section_id=section.id,
                    fact_bank=fact_bank,
                )
                for entry in section.entries
            ],
        )
        for section in document.sections
    ]
    content = TailoredCVContent(
        header=TailoredHeaderSnapshot(
            full_name=profile.full_name or "",
            location=profile.location,
            phone=profile.phone,
            email=profile.email,
            github_url=profile.github_url,
        ),
        sections=sections,
    )
    approved_skill_labels = tuple(
        skill.skill.display_name for skill in profile.skills if not skill.excluded
    )
    return TailoringBaseline(
        content=content,
        fact_bank=fact_bank,
        approved_skill_labels=approved_skill_labels,
    )


def select_section_context(
    baseline: TailoringBaseline,
    *,
    section_ids: Sequence[str],
) -> tuple[list[TailoredSection], dict[str, TailoredFactEvidence]]:
    requested = list(section_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("section_ids must be unique")
    sections_by_id = {section.id: section for section in baseline.content.sections}
    if any(section_id not in sections_by_id for section_id in requested):
        raise ValueError("unknown section id")
    requested_set = set(requested)
    sections = [
        sections_by_id[section_id].model_copy(deep=True)
        for section_id in requested
    ]
    facts = {
        fact_id: evidence.model_copy(deep=True)
        for fact_id, evidence in baseline.fact_bank.items()
        if evidence.section_id in requested_set
    }
    return sections, facts


__all__ = [
    "TailoringBaseline",
    "project_tailoring_baseline",
    "select_section_context",
    "source_fact_id",
]

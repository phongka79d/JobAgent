"""Deterministic CandidateProfile projection from a validated CVDocument.

Profile facts come only from the document. Certifications, projects, awards,
and other dynamic sections remain document-only and are never coerced into
skills. Skill labels pass through the sole SkillNormalizer.
"""

from __future__ import annotations

import re
from typing import Any, Final

from app.schemas.cv_document import CVDocument, CVEntry, CVSection
from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    LanguageItem,
    parse_candidate_profile,
)
from app.services.skill_normalization import (
    SkillNormalizer,
    comparison_fingerprint,
)

_MAX_EVIDENCE_SNIPPET_LEN: Final[int] = 240
_YEAR_RE: Final[re.Pattern[str]] = re.compile(r"\b(19|20)\d{2}\b")


def _clip_evidence(snippets: list[str]) -> list[str]:
    clipped: list[str] = []
    for item in snippets:
        text = " ".join(str(item).split())
        if not text:
            continue
        if len(text) > _MAX_EVIDENCE_SNIPPET_LEN:
            text = text[:_MAX_EVIDENCE_SNIPPET_LEN]
        clipped.append(text)
    return clipped


def _entry_text(entry: CVEntry) -> str:
    parts = [entry.title or "", entry.subtitle or "", entry.body, *entry.bullets]
    return " ".join(p for p in parts if p).strip()


def _sections_of_kind(document: CVDocument, kind: str) -> list[CVSection]:
    return [s for s in document.sections if s.kind == kind]


def _project_summary(document: CVDocument) -> str:
    parts: list[str] = []
    for section in _sections_of_kind(document, "summary"):
        for entry in section.entries:
            text = entry.body.strip() or _entry_text(entry)
            if text:
                parts.append(text)
    if parts:
        return "\n\n".join(parts)
    # Fallback: first non-empty body from any section (bounded).
    for section in document.sections:
        for entry in section.entries:
            if entry.body.strip():
                return entry.body.strip()[:2000]
    return ""


def _project_experiences(document: CVDocument) -> list[ExperienceItem]:
    items: list[ExperienceItem] = []
    for section in _sections_of_kind(document, "experience"):
        for entry in section.entries:
            title = (entry.title or "").strip() or "Role"
            company = (entry.subtitle or entry.location or None)
            if company is not None:
                company = company.strip() or None
            summary = entry.body.strip()
            if not summary and entry.bullets:
                summary = "; ".join(entry.bullets)
            end_raw = entry.attributes.get("end_date_text")
            end_date = end_raw if isinstance(end_raw, str) else None
            items.append(
                ExperienceItem(
                    title=title,
                    company=company,
                    start_date_text=entry.date_text,
                    end_date_text=end_date,
                    summary=summary or title,
                )
            )
    return items


def _project_education(document: CVDocument) -> list[EducationItem]:
    items: list[EducationItem] = []
    for section in _sections_of_kind(document, "education"):
        for entry in section.entries:
            institution = (entry.title or entry.body or "").strip() or "Institution"
            degree = entry.subtitle
            field = entry.attributes.get("field")
            if isinstance(field, list):
                field = field[0] if field else None
            if field is not None and not isinstance(field, str):
                field = None
            year: int | None = None
            raw_year = entry.attributes.get("graduation_year")
            if isinstance(raw_year, str) and raw_year.isdigit():
                year = int(raw_year)
            elif entry.date_text:
                match = _YEAR_RE.search(entry.date_text)
                if match:
                    year = int(match.group(0))
            items.append(
                EducationItem(
                    institution=institution,
                    degree=degree,
                    field=field if isinstance(field, str) else None,
                    graduation_year=year,
                )
            )
    return items


def _skill_names_from_entry(entry: CVEntry, *, section_heading: str) -> list[str]:
    names: list[str] = []
    if (
        entry.title
        and entry.title.strip()
        and comparison_fingerprint(entry.title)
        != comparison_fingerprint(section_heading)
    ):
        names.append(entry.title.strip())
    for bullet in entry.bullets:
        for part in re.split(r"[,;/|]", bullet):
            label = part.strip()
            if label:
                names.append(label)
    if entry.body.strip():
        for part in re.split(r"[,;/|]", entry.body):
            label = part.strip()
            if label and len(label) <= 64:
                names.append(label)
    # attributes may list skills
    for key, value in entry.attributes.items():
        if key.lower() in {"skill", "skills", "name"}:
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
            elif isinstance(value, list):
                names.extend(
                    v.strip()
                    for v in value
                    if isinstance(v, str) and v.strip()
                )
    return names


def _project_skills(
    document: CVDocument,
    normalizer: SkillNormalizer,
) -> list[CandidateSkill]:
    skills: list[CandidateSkill] = []
    seen: set[str] = set()
    for section in _sections_of_kind(document, "skills"):
        for entry in section.entries:
            evidence = _clip_evidence(
                [s for s in [entry.body, *entry.bullets, entry.title or ""] if s]
            )
            for name in _skill_names_from_entry(
                entry,
                section_heading=section.heading,
            ):
                for ref in normalizer.normalize_grouped_name(name):
                    if ref.canonical_key in seen:
                        continue
                    seen.add(ref.canonical_key)
                    skills.append(
                        CandidateSkill(
                            skill=ref,
                            confidence=0.7,
                            proficiency="unknown",
                            years=None,
                            source="cv",
                            excluded=False,
                            evidence=evidence or _clip_evidence([name]),
                        )
                    )
    return skills


def _project_languages(document: CVDocument) -> list[LanguageItem]:
    items: list[LanguageItem] = []
    for section in _sections_of_kind(document, "languages"):
        for entry in section.entries:
            name = (entry.title or entry.body or "").strip()
            if not name:
                continue
            proficiency = entry.subtitle
            if proficiency is None:
                raw = entry.attributes.get("proficiency")
                if isinstance(raw, str):
                    proficiency = raw
            items.append(LanguageItem(name=name, proficiency=proficiency))
    return items


def _project_current_title(
    document: CVDocument, experiences: list[ExperienceItem]
) -> str | None:
    for section in document.sections:
        if section.kind != "summary":
            continue
        for entry in section.entries:
            raw = entry.attributes.get("current_title")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    if experiences:
        return experiences[0].title
    return None


def project_candidate_profile(
    document: CVDocument,
    normalizer: SkillNormalizer,
) -> CandidateProfile:
    """Derive a validated CandidateProfile solely from *document*.

    Pure projection helper: no provider, network, or persistence side effects.
    """
    experiences = _project_experiences(document)
    education = _project_education(document)
    skills = _project_skills(document, normalizer)
    languages = _project_languages(document)
    summary = _project_summary(document)
    current_title = _project_current_title(document, experiences)
    conf = float(document.extraction_confidence)
    if conf < 0.0:
        conf = 0.0
    elif conf > 1.0:
        conf = 1.0
    raw: dict[str, Any] = {
        "summary": summary,
        "current_title": current_title,
        "total_experience_years": None,
        "skills": [s.model_dump(mode="json") for s in skills],
        "experiences": [e.model_dump(mode="json") for e in experiences],
        "education": [e.model_dump(mode="json") for e in education],
        "languages": [lang.model_dump(mode="json") for lang in languages],
        "extraction_confidence": conf,
    }
    return parse_candidate_profile(raw)


def project_outline(document: CVDocument) -> list[dict[str, Any]]:
    """Bounded outline projection: section ids/headings/kinds/counts/ranges."""
    outline: list[dict[str, Any]] = []
    for section in document.sections:
        ords = section.source_chunk_ordinals
        outline.append(
            {
                "id": section.id,
                "ordinal": section.ordinal,
                "heading": section.heading,
                "kind": section.kind,
                "entry_count": len(section.entries),
                "source_chunk_ordinals": list(ords),
                "source_chunk_range": (
                    [ords[0], ords[-1]] if ords else []
                ),
            }
        )
    return outline


__all__ = [
    "project_candidate_profile",
    "project_outline",
]

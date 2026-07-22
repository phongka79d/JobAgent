"""Guarded all-section Candidate skills projected from a validated CVDocument."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.cv_document import CVDocument
from app.schemas.profile import CandidateSkill
from app.schemas.skills import SkillRef
from app.services.cv_skill_contracts import (
    DEFAULT_SKILL_BATCH_MAX_CHARS,
    MAX_EVIDENCE_LENGTH,
    MAX_EVIDENCE_PER_ASSERTION,
    MAX_GUARD_ISSUES,
    CandidateSkillBatch,
    CandidateSkillEntryContext,
    CandidateSkillExtractionError,
    ExtractedCandidateSkillAssertion,
    ExtractedCandidateSkillBatch,
    StructuredCandidateSkillInvoker,
)
from app.services.cv_skill_provider import invoke_candidate_skill_batch
from app.services.cv_skill_source import build_source_batches
from app.services.skill_assertion_guard import (
    StructuralSkillIssue,
    is_group_label_in_source,
    is_label_grounded,
    is_source_grounded,
    matches_heading,
    normalize_assertion_text,
    structural_compound_part_count,
    structural_issue,
)
from app.services.skill_normalization import SkillNormalizer


@dataclass(frozen=True, slots=True)
class CandidateSkillExtractionOutcome:
    skills: tuple[CandidateSkill, ...]
    schema_repairs_used: int
    provider_retries_used: int
    batches: tuple[CandidateSkillBatch, ...]


def _guard_batch(
    extracted: ExtractedCandidateSkillBatch,
    *,
    source_batch: CandidateSkillBatch,
    contexts: dict[str, CandidateSkillEntryContext],
    normalizer: SkillNormalizer,
) -> tuple[StructuralSkillIssue, ...]:
    issues: list[StructuralSkillIssue] = []
    seen: dict[str, int] = {}
    headings = tuple(context.section.heading for context in contexts.values())
    for index, assertion in enumerate(extracted.assertions):
        name_path = f"assertions[{index}].name"
        if any(
            item not in source_batch.entry_ids for item in assertion.source_entry_ids
        ):
            issues.append(structural_issue("SOURCE_ENTRY_NOT_IN_BATCH", name_path))
            continue
        selected = [contexts.get(item) for item in assertion.source_entry_ids]
        if any(item is None for item in selected):
            issues.append(structural_issue("SOURCE_ENTRY_NOT_FOUND", name_path))
            continue
        entries = [item for item in selected if item is not None]
        orders = [item.source_order for item in entries]
        if orders != sorted(orders):
            issues.append(structural_issue("SOURCE_ENTRY_ORDER_INVALID", name_path))
        source = source_batch.source_text_for(assertion.source_entry_ids)
        for evidence_index, evidence in enumerate(assertion.evidence):
            if not is_source_grounded(evidence, source):
                issues.append(
                    structural_issue(
                        "EVIDENCE_NOT_IN_SOURCE",
                        f"assertions[{index}].evidence[{evidence_index}]",
                    )
                )
        try:
            ref = normalizer.normalize_name(assertion.name)
        except ValueError:
            issues.append(structural_issue("INVALID_SKILL_NAME", name_path))
            continue
        if not is_label_grounded(
            assertion.name,
            assertion.evidence,
            approved_aliases=(ref.display_name, *ref.aliases),
        ):
            issues.append(structural_issue("SKILL_NAME_NOT_IN_SOURCE", name_path))
        if matches_heading(assertion.name, headings):
            issues.append(structural_issue("HEADING_ONLY_SKILL", name_path))
        if is_group_label_in_source(assertion.name, source):
            issues.append(structural_issue("GROUP_LABEL_SKILL", name_path))
        normalized_name = normalize_assertion_text(assertion.name)
        if entries and all(item.section.kind != "skills" for item in entries):
            metadata_match = any(
                normalized_name == normalize_assertion_text(value)
                for item in entries
                for value in item.metadata_values
            )
            substantive_match = any(
                is_source_grounded(assertion.name, item.substantive_text)
                and bool(normalized_name)
                for item in entries
            )
            if metadata_match and not substantive_match:
                issues.append(structural_issue("METADATA_ONLY_SKILL", name_path))
        approved_atomic_labels: tuple[str, ...] = ()
        if normalizer.is_seed_skill(ref.canonical_key):
            approved_atomic_labels = (ref.display_name, *ref.aliases)
        compound_count = structural_compound_part_count(
            assertion.name,
            approved_atomic_labels=approved_atomic_labels,
        )
        if compound_count is not None:
            issues.append(
                structural_issue(
                    "COMPOUND_SKILL_LABEL",
                    name_path,
                    count=compound_count,
                )
            )
        seen[ref.canonical_key] = seen.get(ref.canonical_key, 0) + 1
        if seen[ref.canonical_key] > 1:
            issues.append(
                structural_issue(
                    "DUPLICATE_SKILL",
                    name_path,
                    count=seen[ref.canonical_key],
                )
            )
    return tuple(issues[:MAX_GUARD_ISSUES])


def _aggregate(
    accepted: Sequence[ExtractedCandidateSkillAssertion],
    *,
    contexts: dict[str, CandidateSkillEntryContext],
    normalizer: SkillNormalizer,
) -> tuple[CandidateSkill, ...]:
    ordered = sorted(
        enumerate(accepted),
        key=lambda pair: (
            min(contexts[item].source_order for item in pair[1].source_entry_ids),
            pair[0],
        ),
    )
    groups: OrderedDict[str, list[ExtractedCandidateSkillAssertion]] = OrderedDict()
    refs: dict[str, SkillRef] = {}
    for _, assertion in ordered:
        ref = normalizer.normalize_name(assertion.name)
        refs.setdefault(ref.canonical_key, ref)
        groups.setdefault(ref.canonical_key, []).append(assertion)
    skills: list[CandidateSkill] = []
    for key, assertions in groups.items():
        evidence: list[str] = []
        for assertion in assertions:
            for snippet in assertion.evidence:
                clipped = " ".join(snippet.split())[:MAX_EVIDENCE_LENGTH]
                if clipped and clipped not in evidence:
                    evidence.append(clipped)
        non_unknown = {
            item.proficiency for item in assertions if item.proficiency != "unknown"
        }
        years = {item.years for item in assertions if item.years is not None}
        skills.append(
            CandidateSkill(
                skill=refs[key],
                confidence=max(item.confidence for item in assertions),
                proficiency=(
                    next(iter(non_unknown)) if len(non_unknown) == 1 else "unknown"
                ),
                years=next(iter(years)) if len(years) == 1 else None,
                source="cv",
                excluded=False,
                evidence=evidence[:MAX_EVIDENCE_PER_ASSERTION],
            )
        )
    return tuple(skills)


def extract_candidate_skills_from_document(
    document: CVDocument,
    *,
    invoker: StructuredCandidateSkillInvoker,
    normalizer: SkillNormalizer,
    max_chars: int | None = None,
) -> CandidateSkillExtractionOutcome:
    """Extract, guard, and aggregate Candidate skills before publication."""
    ceiling = DEFAULT_SKILL_BATCH_MAX_CHARS if max_chars is None else max_chars
    batches, contexts = build_source_batches(document, max_chars=ceiling)
    accepted: list[ExtractedCandidateSkillAssertion] = []
    repairs_total = 0
    retries_total = 0
    for batch in batches:

        def guard_candidate(
            candidate: ExtractedCandidateSkillBatch,
        ) -> tuple[StructuralSkillIssue, ...]:
            return _guard_batch(
                candidate,
                source_batch=batch,
                contexts=contexts,
                normalizer=normalizer,
            )

        extracted, repairs, retries = invoke_candidate_skill_batch(
            batch,
            invoker=invoker,
            guard=guard_candidate,
        )
        accepted.extend(extracted.assertions)
        repairs_total += repairs
        retries_total += retries
    return CandidateSkillExtractionOutcome(
        skills=_aggregate(accepted, contexts=contexts, normalizer=normalizer),
        schema_repairs_used=repairs_total,
        provider_retries_used=retries_total,
        batches=batches,
    )


__all__ = [
    "CandidateSkillBatch",
    "CandidateSkillExtractionError",
    "CandidateSkillExtractionOutcome",
    "DEFAULT_SKILL_BATCH_MAX_CHARS",
    "ExtractedCandidateSkillAssertion",
    "ExtractedCandidateSkillBatch",
    "StructuredCandidateSkillInvoker",
    "extract_candidate_skills_from_document",
]

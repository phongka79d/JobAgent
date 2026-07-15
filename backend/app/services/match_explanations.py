"""Pure deterministic match explanation projector (Plan 6 02D / §7.7).

Assembles compact response models and stable summary prose only from accepted
02A skill facts, 02B/02C scored component facts, and authoritative Job
metadata. No scoring, LLM, provider, DB, or graph I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.jobs import JobWorkMode
from app.schemas.matching import (
    MatchComponentScores,
    MatchJobsResultData,
    MatchResult,
    MatchSkillEvidence,
    MissingRequiredSkill,
)
from app.services.match_components import ScoredMatchCandidate
from app.services.skill_matching import SkillCoverageResult, SkillMatchFact

_COMPONENT_ORDER: tuple[str, ...] = (
    "semantic_similarity",
    "skill_score",
    "seniority_score",
    "experience_score",
    "location_score",
    "work_mode_score",
)


@dataclass(frozen=True, slots=True)
class MatchExplanationInput:
    """Authoritative Job metadata plus accepted 02A-02C facts for one result."""

    scored: ScoredMatchCandidate
    skill_coverage: SkillCoverageResult
    title: str | None
    company: str | None
    location: str | None
    work_mode: JobWorkMode
    source_url: str | None


def project_match_result(item: MatchExplanationInput) -> MatchResult:
    """Project one scored candidate and skill facts into a strict MatchResult."""
    scored = item.scored
    components = scored.components
    if components.job_id.strip() == "":
        raise ValueError("job_id must be non-empty")

    matched_required = _matched_skills(item.skill_coverage.required_matches)
    matched_preferred = _matched_skills(item.skill_coverage.preferred_matches)
    related = _related_skills(
        item.skill_coverage.required_matches,
        item.skill_coverage.preferred_matches,
    )
    missing_required = _missing_required(item.skill_coverage.required_matches)

    component_scores = MatchComponentScores(
        semantic_similarity=components.semantic_similarity,
        skill_score=components.skill_score,
        seniority_score=components.seniority_score,
        experience_score=components.experience_score,
        location_score=components.location_score,
        work_mode_score=components.work_mode_score,
    )
    effective_weights = {
        name: scored.effective_weights[name]
        for name in _COMPONENT_ORDER
        if name in scored.effective_weights
    }

    summary = _build_summary(
        job_id=components.job_id,
        title=item.title,
        company=item.company,
        final_score=scored.final_score,
        matched_required=matched_required,
        related=related,
        missing_required=missing_required,
        component_scores=component_scores,
    )

    return MatchResult(
        job_id=components.job_id,
        title=item.title,
        company=item.company,
        location=item.location,
        work_mode=item.work_mode,
        source_url=item.source_url,
        final_score=scored.final_score,
        quality_multiplier=scored.quality_multiplier,
        components=component_scores,
        effective_weights=effective_weights,
        matched_required_skills=matched_required,
        matched_preferred_skills=matched_preferred,
        related_skills=related,
        missing_required_skills=missing_required,
        summary=summary,
    )


def project_match_jobs_result(
    items: Sequence[MatchExplanationInput],
    *,
    limit: int,
) -> MatchJobsResultData:
    """Project an already-ordered candidate list into compact result data."""
    results = [project_match_result(item) for item in items]
    return MatchJobsResultData(
        results=results,
        count=len(results),
        limit=limit,
    )


def _matched_skills(matches: Sequence[SkillMatchFact]) -> list[MatchSkillEvidence]:
    """Direct matches only; preserve source list order."""
    return [
        _skill_evidence(fact)
        for fact in matches
        if fact.match_type == "direct" and fact.candidate_skill is not None
    ]


def _related_skills(
    required_matches: Sequence[SkillMatchFact],
    preferred_matches: Sequence[SkillMatchFact],
) -> list[MatchSkillEvidence]:
    """Related matches from required then preferred; preserve source order."""
    ordered = (*required_matches, *preferred_matches)
    return [
        _skill_evidence(fact)
        for fact in ordered
        if fact.match_type == "related" and fact.candidate_skill is not None
    ]


def _missing_required(
    required_matches: Sequence[SkillMatchFact],
) -> list[MissingRequiredSkill]:
    """Gaps are only required skills whose best strength is zero."""
    missing: list[MissingRequiredSkill] = []
    for fact in required_matches:
        if fact.match_type != "none" and fact.strength != 0.0:
            continue
        job_skill = fact.job_skill
        missing.append(
            MissingRequiredSkill(
                job_skill_key=job_skill.skill.canonical_key,
                job_skill_display_name=job_skill.skill.display_name,
                job_evidence=list(job_skill.evidence),
            )
        )
    return missing


def _skill_evidence(fact: SkillMatchFact) -> MatchSkillEvidence:
    candidate = fact.candidate_skill
    if candidate is None:
        raise ValueError("matched skill fact requires a winning candidate skill")
    job_skill = fact.job_skill
    if fact.match_type == "direct":
        return MatchSkillEvidence(
            job_skill_key=job_skill.skill.canonical_key,
            job_skill_display_name=job_skill.skill.display_name,
            match_type="direct",
            strength=fact.strength,
            candidate_skill_key=candidate.skill.canonical_key,
            candidate_skill_display_name=candidate.skill.display_name,
            job_evidence=list(job_skill.evidence),
            candidate_evidence=list(candidate.evidence),
        )
    if fact.match_type != "related" or fact.relationship is None:
        raise ValueError("related skill fact requires seed relationship evidence")
    edge = fact.relationship
    return MatchSkillEvidence(
        job_skill_key=job_skill.skill.canonical_key,
        job_skill_display_name=job_skill.skill.display_name,
        match_type="related",
        strength=fact.strength,
        candidate_skill_key=candidate.skill.canonical_key,
        candidate_skill_display_name=candidate.skill.display_name,
        job_evidence=list(job_skill.evidence),
        candidate_evidence=list(candidate.evidence),
        relationship_from_key=edge.from_key,
        relationship_to_key=edge.to_key,
        relationship_weight=edge.weight,
        relationship_source=edge.source,
    )


def _build_summary(
    *,
    job_id: str,
    title: str | None,
    company: str | None,
    final_score: float,
    matched_required: Sequence[MatchSkillEvidence],
    related: Sequence[MatchSkillEvidence],
    missing_required: Sequence[MissingRequiredSkill],
    component_scores: MatchComponentScores,
) -> str:
    """Assemble one deterministic summary from projected facts only."""
    subject = title if title is not None and title != "" else job_id
    if company is not None and company != "":
        head = f"Match score {final_score} for {subject} at {company}."
    else:
        head = f"Match score {final_score} for {subject}."

    parts: list[str] = [head]

    if matched_required:
        details = "; ".join(
            f"{item.job_skill_display_name} (direct via "
            f"{item.candidate_skill_display_name})"
            for item in matched_required
        )
        parts.append(f"Matched required skills: {details}.")

    if related:
        details = "; ".join(
            f"{item.job_skill_display_name} (related via "
            f"{item.candidate_skill_display_name}, seed weight "
            f"{item.relationship_weight})"
            for item in related
        )
        parts.append(f"Related skills: {details}.")

    if missing_required:
        names = ", ".join(item.job_skill_display_name for item in missing_required)
        parts.append(f"Missing required skills: {names}.")

    unavailable = _unavailable_component_names(component_scores)
    if unavailable:
        parts.append(f"Unavailable components: {', '.join(unavailable)}.")

    return " ".join(parts)


def _unavailable_component_names(scores: MatchComponentScores) -> list[str]:
    values = {
        "skill_score": scores.skill_score,
        "seniority_score": scores.seniority_score,
        "experience_score": scores.experience_score,
        "location_score": scores.location_score,
        "work_mode_score": scores.work_mode_score,
    }
    return [
        name
        for name in _COMPONENT_ORDER
        if name in values and values[name] is None
    ]


__all__ = [
    "MatchExplanationInput",
    "project_match_jobs_result",
    "project_match_result",
]

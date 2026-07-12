"""Edge indexing and strongest-path skill evidence matching (Plan 6 §7.2).

Owns verified RELATED_TO indexing and direct/alias/related match paths.
Coverage lives in ``skill_match_coverage``; contracts in ``skill_match_contracts``.
Reuses ``normalize_skill_match_key``; never invents or persists RELATED_TO edges.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.schemas.candidate import CandidateSkill, SkillRef, SkillStatus
from app.schemas.job_post import JobSkill
from app.services.skill_match_contracts import (
    STRENGTH_DIRECT,
    STRENGTH_NONE,
    STRENGTH_VERIFIED_ALIAS,
    STRENGTH_VERIFIED_RELATED,
    MatchKind,
    SkillMatchEvidence,
    VerifiedRelatedEdge,
    bound_snippets,
    bound_source,
    is_verified_relationship_status,
)
from app.services.skill_normalization import normalize_skill_match_key


def _skill_surfaces(ref: SkillRef) -> list[str]:
    """Canonical key, display name, and aliases as non-blank surface strings."""
    surfaces: list[str] = []
    for value in (ref.canonical_key, ref.display_name, *ref.aliases):
        if isinstance(value, str) and value.strip():
            surfaces.append(value.strip())
    return surfaces


def _match_key_set(ref: SkillRef) -> frozenset[str]:
    keys: set[str] = set()
    for surface in _skill_surfaces(ref):
        match_key = normalize_skill_match_key(surface)
        if match_key:
            keys.add(match_key)
    return frozenset(keys)


def _dedupe_job_skills(skills: Sequence[JobSkill]) -> tuple[JobSkill, ...]:
    """Stable first-wins dedupe by nested ``canonical_key``; preserve order."""
    seen: set[str] = set()
    ordered: list[JobSkill] = []
    for item in skills:
        key = item.skill.canonical_key
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return tuple(ordered)


def _active_candidate_skills(
    skills: Sequence[CandidateSkill],
) -> tuple[CandidateSkill, ...]:
    """Non-excluded Candidate skills, stable first-wins by canonical_key."""
    seen: set[str] = set()
    ordered: list[CandidateSkill] = []
    for item in skills:
        if item.excluded:
            continue
        key = item.skill.canonical_key
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return tuple(ordered)


def _related_pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def index_verified_related_edges(
    edges: Sequence[VerifiedRelatedEdge],
) -> Mapping[tuple[str, str], VerifiedRelatedEdge]:
    """Index undirected verified edges; drop non-boolean-True and self-loops.

    First edge wins on duplicate pairs. Only ``verified is True`` is retained.
    """
    index: dict[tuple[str, str], VerifiedRelatedEdge] = {}
    for edge in edges:
        if not is_verified_relationship_status(edge.verified):
            continue
        from_key = edge.from_key.strip() if isinstance(edge.from_key, str) else ""
        to_key = edge.to_key.strip() if isinstance(edge.to_key, str) else ""
        if not from_key or not to_key or from_key == to_key:
            continue
        pair = _related_pair_key(from_key, to_key)
        if pair in index:
            continue
        index[pair] = VerifiedRelatedEdge(
            from_key=from_key,
            to_key=to_key,
            source=bound_source(edge.source),
            verified=True,
            weight=edge.weight,
        )
    return index


def _coerce_related_index(
    related_index: Mapping[tuple[str, str], VerifiedRelatedEdge] | None,
    related_edges: Sequence[VerifiedRelatedEdge],
) -> Mapping[tuple[str, str], VerifiedRelatedEdge]:
    """Build or re-filter so only ``verified is True`` remains (fail-closed)."""
    if related_index is None:
        return index_verified_related_edges(related_edges)
    return index_verified_related_edges(tuple(related_index.values()))


def _try_direct(
    job_ref: SkillRef,
    candidates: Sequence[CandidateSkill],
) -> SkillMatchEvidence | None:
    job_key = job_ref.canonical_key
    for cand in candidates:
        if cand.skill.canonical_key == job_key:
            return SkillMatchEvidence(
                job_canonical_key=job_key,
                job_display_name=job_ref.display_name,
                candidate_canonical_key=cand.skill.canonical_key,
                match_kind=MatchKind.DIRECT,
                strength=STRENGTH_DIRECT,
                evidence_snippets=bound_snippets(
                    list(job_ref.evidence) + list(cand.skill.evidence)
                ),
            )
    return None


def _try_verified_alias(
    job_ref: SkillRef,
    candidates: Sequence[CandidateSkill],
) -> SkillMatchEvidence | None:
    """Match when surfaces collide via a verified skill's alias properties.

    Requires at least one skill ``verified`` and overlapping match keys with
    unequal canonical keys (direct equality is handled first).
    """
    job_key = job_ref.canonical_key
    job_keys = _match_key_set(job_ref)
    if not job_keys:
        return None

    best: SkillMatchEvidence | None = None
    for cand in candidates:
        cand_ref = cand.skill
        if cand_ref.canonical_key == job_key:
            continue
        if (
            job_ref.status is not SkillStatus.VERIFIED
            and cand_ref.status is not SkillStatus.VERIFIED
        ):
            continue
        cand_keys = _match_key_set(cand_ref)
        if not job_keys.intersection(cand_keys):
            continue
        evidence = SkillMatchEvidence(
            job_canonical_key=job_key,
            job_display_name=job_ref.display_name,
            candidate_canonical_key=cand_ref.canonical_key,
            match_kind=MatchKind.VERIFIED_ALIAS,
            strength=STRENGTH_VERIFIED_ALIAS,
            evidence_snippets=bound_snippets(
                list(job_ref.evidence) + list(cand_ref.evidence)
            ),
        )
        if best is None or (
            cand_ref.canonical_key < (best.candidate_canonical_key or "")
        ):
            best = evidence
    return best


def _try_verified_related(
    job_ref: SkillRef,
    candidates: Sequence[CandidateSkill],
    related_index: Mapping[tuple[str, str], VerifiedRelatedEdge],
) -> SkillMatchEvidence | None:
    """Verified RELATED_TO between job key and a candidate key → strength 0.6."""
    job_key = job_ref.canonical_key
    best: SkillMatchEvidence | None = None
    for cand in candidates:
        cand_key = cand.skill.canonical_key
        if cand_key == job_key:
            continue
        pair = _related_pair_key(job_key, cand_key)
        edge = related_index.get(pair)
        if edge is None or not is_verified_relationship_status(edge.verified):
            continue
        path = (job_key, cand_key)
        source = edge.source or None
        evidence = SkillMatchEvidence(
            job_canonical_key=job_key,
            job_display_name=job_ref.display_name,
            candidate_canonical_key=cand_key,
            match_kind=MatchKind.VERIFIED_RELATED,
            strength=STRENGTH_VERIFIED_RELATED,
            related_path=path,
            source=source,
            evidence_snippets=bound_snippets([source] if source else []),
        )
        if best is None or (cand_key < (best.candidate_canonical_key or "")):
            best = evidence
    return best


def match_job_skill(
    job_skill: JobSkill,
    candidate_skills: Sequence[CandidateSkill],
    *,
    related_edges: Sequence[VerifiedRelatedEdge] = (),
    related_index: Mapping[tuple[str, str], VerifiedRelatedEdge] | None = None,
) -> SkillMatchEvidence:
    """Return strongest permitted match for one Job skill (precedence locked).

    direct (1.0) > verified alias (1.0) > verified RELATED_TO (0.6) >
    provisional/unverified/no match (0.0). Related boosts require
    ``verified is True`` on every path, including a caller-supplied index.
    """
    active = _active_candidate_skills(candidate_skills)
    index = _coerce_related_index(related_index, related_edges)
    job_ref = job_skill.skill

    direct = _try_direct(job_ref, active)
    if direct is not None:
        return direct

    alias = _try_verified_alias(job_ref, active)
    if alias is not None:
        return alias

    related = _try_verified_related(job_ref, active, index)
    if related is not None:
        return related

    kind = (
        MatchKind.PROVISIONAL
        if job_ref.status is SkillStatus.PROVISIONAL
        else MatchKind.NO_MATCH
    )
    return SkillMatchEvidence(
        job_canonical_key=job_ref.canonical_key,
        job_display_name=job_ref.display_name,
        candidate_canonical_key=None,
        match_kind=kind,
        strength=STRENGTH_NONE,
        evidence_snippets=bound_snippets(list(job_ref.evidence)),
    )


def match_skill_list(
    job_skills: Sequence[JobSkill],
    candidate_skills: Sequence[CandidateSkill],
    *,
    related_edges: Sequence[VerifiedRelatedEdge] = (),
    related_index: Mapping[tuple[str, str], VerifiedRelatedEdge] | None = None,
) -> tuple[SkillMatchEvidence, ...]:
    """Match each deduped Job skill; stable job-key order of the input list."""
    deduped = _dedupe_job_skills(job_skills)
    index = _coerce_related_index(related_index, related_edges)
    return tuple(
        match_job_skill(
            item,
            candidate_skills,
            related_index=index,
        )
        for item in deduped
    )


__all__ = [
    "index_verified_related_edges",
    "match_job_skill",
    "match_skill_list",
]

"""Load active/scorable SQLite Jobs and project them for full graph rebuild.

Keeps rebuild orchestration out of the infrastructure CLI. Reuses the online
Job projector (``project_eligible_job``) so Cypher/parameters stay single-sourced.
Does not mark SQLite/outbox sync state — that happens only after verification.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.db.session import DatabaseSessionManager
from app.graph.job_sync import (
    JobEmbeddingPort,
    JobGraphClient,
    is_graph_eligible,
    project_eligible_job,
)
from app.repositories.job_posts import (
    MAX_LIST_LIMIT,
    JobPostRecord,
    JobPostRepository,
)
from app.repositories.profiles import ProfileRepository
from app.schemas.job_post import JobPostExtraction
from app.services.skill_normalization import provisional_canonical_key

# Hard ceiling on rebuild pages to bound memory (keyset pagination).
_MAX_REBUILD_PAGES: int = 10_000


class RebuildLoadError(Exception):
    """Sanitized rebuild load/projection failure (code-only message)."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code

    def __repr__(self) -> str:
        return f"RebuildLoadError(code={self.code!r})"


@dataclass(frozen=True, slots=True)
class RebuildSnapshot:
    """Expected derived-graph parity inputs from canonical SQLite."""

    eligible_job_ids: tuple[str, ...]
    expected_skill_keys: frozenset[str]
    expected_family_keys: frozenset[str]
    expected_requires_count: int
    expected_prefers_count: int
    expected_in_family_count: int
    expected_candidate_count: int
    expected_has_skill_count: int
    jobs: tuple[JobPostRecord, ...]


def _family_key(extraction: JobPostExtraction) -> str | None:
    raw = extraction.job_family
    if raw is None:
        return None
    display = raw.strip()
    if not display:
        return None
    try:
        return provisional_canonical_key(display)
    except ValueError:
        return None


def _accumulate_job_expectations(
    extraction: JobPostExtraction,
    *,
    skill_keys: set[str],
    family_keys: set[str],
) -> tuple[int, int, int]:
    requires = 0
    prefers = 0
    in_family = 0
    for item in extraction.required_skills:
        skill_keys.add(item.skill.canonical_key)
        requires += 1
    for item in extraction.preferred_skills:
        skill_keys.add(item.skill.canonical_key)
        prefers += 1
    family = _family_key(extraction)
    if family is not None:
        family_keys.add(family)
        in_family = 1
    return requires, prefers, in_family


async def load_rebuild_snapshot(
    database: DatabaseSessionManager,
) -> RebuildSnapshot:
    """Load all graph-eligible Jobs via bounded keyset pages plus Candidate keys."""
    jobs: list[JobPostRecord] = []
    after_id: UUID | None = None
    pages = 0
    async with database.session_scope() as session:
        repo = JobPostRepository(session)
        while pages < _MAX_REBUILD_PAGES:
            pages += 1
            page = await repo.list_graph_eligible_page(
                after_id=after_id,
                limit=MAX_LIST_LIMIT,
            )
            if not page:
                break
            for record in page:
                if is_graph_eligible(record):
                    jobs.append(record)
            after_id = page[-1].id
            if len(page) < MAX_LIST_LIMIT:
                break
        else:
            raise RebuildLoadError("rebuild_job_page_limit")

        skill_keys: set[str] = set()
        family_keys: set[str] = set()
        requires_count = 0
        prefers_count = 0
        in_family_count = 0
        for record in jobs:
            extraction = record.extraction
            if extraction is None:
                continue
            req, pref, fam = _accumulate_job_expectations(
                extraction,
                skill_keys=skill_keys,
                family_keys=family_keys,
            )
            requires_count += req
            prefers_count += pref
            in_family_count += fam

        candidate_count = 0
        has_skill_count = 0
        approved = await ProfileRepository(session).get()
        if approved is not None:
            candidate_count = 1
            for candidate_skill in approved.profile.skills:
                if candidate_skill.excluded:
                    continue
                skill_keys.add(candidate_skill.skill.canonical_key)
                has_skill_count += 1

    job_ids = tuple(str(job.id) for job in jobs)
    return RebuildSnapshot(
        eligible_job_ids=job_ids,
        expected_skill_keys=frozenset(skill_keys),
        expected_family_keys=frozenset(family_keys),
        expected_requires_count=requires_count,
        expected_prefers_count=prefers_count,
        expected_in_family_count=in_family_count,
        expected_candidate_count=candidate_count,
        expected_has_skill_count=has_skill_count,
        jobs=tuple(jobs),
    )


async def project_jobs_for_rebuild(
    jobs: Sequence[JobPostRecord],
    client: JobGraphClient,
    embedding_service: JobEmbeddingPort,
) -> tuple[str, ...]:
    """Recompute embeddings and MERGE every eligible Job. No SQLite status writes."""
    projected: list[str] = []
    for record in jobs:
        if not is_graph_eligible(record):
            continue
        try:
            await project_eligible_job(record, client, embedding_service)
        except Exception as exc:
            code = getattr(exc, "code", None)
            if isinstance(code, str) and code:
                raise RebuildLoadError(code[:64]) from None
            raise RebuildLoadError("job_projection_failed") from None
        projected.append(str(record.id))
    return tuple(projected)


__all__ = [
    "RebuildLoadError",
    "RebuildSnapshot",
    "load_rebuild_snapshot",
    "project_jobs_for_rebuild",
]

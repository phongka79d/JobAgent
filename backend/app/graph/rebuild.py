"""Provider-free Neo4j rebuild public service and CLI (Plan 5 §7.8 / Plan 9).

One application owner for the local graph rebuild command, executable as
``python -m app.graph.rebuild`` inside the authoritative Compose backend
(container choice C only). Internal ownership:

* ``rebuild_target`` — exclusive Compose target contract
* ``rebuild_snapshot`` — read-only SQLite snapshot + embedding preflight
* ``rebuild_ops`` — label-scoped clear and endpoint-scoped counts

No ShopAIKey/embedding-provider call and no SQLite mutation.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings, get_settings
from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.db.session import get_session_factory
from app.graph.constraints import ensure_base_schema
from app.graph.driver import close_driver, open_driver
from app.graph.rebuild_ops import (
    CLEAR_CANDIDATE_CYPHER,
    CLEAR_CV_CYPHER,
    CLEAR_CV_ENTRY_CYPHER,
    CLEAR_CV_SECTION_CYPHER,
    CLEAR_JOB_CYPHER,
    CLEAR_SKILL_CYPHER,
    COUNT_ORDER,
    RebuildCounts,
    clear_jobagent_graph,
    count_graph,
)
from app.graph.rebuild_snapshot import (
    CONFIGURATION_RESTORATION_GUIDANCE,
    LegacyActiveCvRow,
    load_rebuild_inputs,
)
from app.graph.rebuild_target import (
    CANONICAL_COMPOSE_REBUILD_COMMAND,
    RebuildError,
    assert_local_compose_neo4j_target,
)
from app.graph.sync_candidate import CandidateSyncError, sync_candidate
from app.graph.sync_cv import CvSyncError, sync_cv
from app.graph.sync_job import JobSyncError, sync_job
from app.graph.sync_shared import (
    AsyncGraphDriver,
    consume_result,
    iso_utc,
    project_seed_skills_and_related,
    related_to_param_rows,
    seed_skill_param_rows,
)
from app.schemas.embeddings import (
    EmbeddingVectorError,
    require_locked_embedding_contract,
)
from app.services.skill_normalization import SkillNormalizer

# Re-export clear constants for ownership tests that inspect the public module.
_CLEAR_CANDIDATE_CYPHER = CLEAR_CANDIDATE_CYPHER
_CLEAR_JOB_CYPHER = CLEAR_JOB_CYPHER
_CLEAR_SKILL_CYPHER = CLEAR_SKILL_CYPHER
_CLEAR_CV_CYPHER = CLEAR_CV_CYPHER
_CLEAR_CV_SECTION_CYPHER = CLEAR_CV_SECTION_CYPHER
_CLEAR_CV_ENTRY_CYPHER = CLEAR_CV_ENTRY_CYPHER

# Legacy active CV (no approved document): metadata node only, reprocess-required.
_LEGACY_EXTRACTION_VERSION: str = "legacy-reprocess-required"

MERGE_LEGACY_CV_CYPHER: str = (
    "MERGE (cv:CV {id: $cv_id}) "
    "SET cv.original_name = $original_name, "
    "    cv.extraction_version = $extraction_version, "
    "    cv.source_updated_at = $source_updated_at "
    "RETURN cv.id AS id"
)

CLEAR_ALL_PROJECTS_TO_CYPHER: str = (
    "MATCH (:CV)-[r:PROJECTS_TO]->(c:Candidate {id: $candidate_id}) "
    "DELETE r"
)

MERGE_PROJECTS_TO_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id}) "
    "MATCH (c:Candidate {id: $candidate_id}) "
    "MERGE (cv)-[:PROJECTS_TO]->(c)"
)


async def _project_legacy_active_cv(
    driver: AsyncGraphDriver,
    legacy: LegacyActiveCvRow,
) -> None:
    """Emit metadata-only active CV (no sections/entries) for reprocess-required."""
    params = {
        "cv_id": legacy.attachment_id,
        "original_name": legacy.original_name,
        "extraction_version": _LEGACY_EXTRACTION_VERSION,
        "source_updated_at": iso_utc(legacy.source_updated_at),
        "candidate_id": CANDIDATE_PROFILE_ID,
    }
    async with driver.session() as session:
        result = await session.run(MERGE_LEGACY_CV_CYPHER, params)
        await consume_result(result)
        result = await session.run(CLEAR_ALL_PROJECTS_TO_CYPHER, params)
        await consume_result(result)
        result = await session.run(MERGE_PROJECTS_TO_CYPHER, params)
        await consume_result(result)


async def rebuild_graph(
    driver: AsyncGraphDriver,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    normalizer: SkillNormalizer,
    settings: Settings | None = None,
    enforce_local_target: bool = True,
) -> RebuildCounts:
    """Run the full provider-free rebuild; return printed counts.

    Order: choice-C target guard → SQLite preflight → label-scoped clear →
    schema → Candidate (optional) → scorable Jobs → approved CV branches
    (active PROJECTS_TO only) → legacy active metadata when needed →
    seed-only when empty → endpoint-scoped counts.

    Raises :class:`RebuildError` before the first destructive statement when
    embeddings or target checks fail. Never opens ShopAIKey or writes SQLite.
    """
    cfg = settings if settings is not None else get_settings()
    if enforce_local_target:
        assert_local_compose_neo4j_target(cfg)

    expected_model = str(cfg.EMBEDDING_MODEL)
    expected_dimensions = int(cfg.EMBEDDING_DIMENSIONS)
    try:
        require_locked_embedding_contract(
            model=expected_model,
            dimensions=expected_dimensions,
        )
    except EmbeddingVectorError as exc:
        raise RebuildError(
            f"Runtime embedding settings are not the locked contract. "
            f"{CONFIGURATION_RESTORATION_GUIDANCE}",
            code="EMBEDDING_CONFIG_MISMATCH",
        ) from exc

    # Preflight reads only — complete before any DETACH DELETE.
    async with session_factory() as session:
        (
            profile,
            profile_updated_at,
            scorable,
            approved_cvs,
            legacy_active,
        ) = await load_rebuild_inputs(
            session,
            expected_model=expected_model,
            expected_dimensions=expected_dimensions,
        )

    try:
        await clear_jobagent_graph(driver)
        await ensure_base_schema(driver)  # type: ignore[arg-type]

        if profile is not None and profile_updated_at is not None:
            await sync_candidate(
                driver,
                profile=profile,
                source_updated_at=profile_updated_at,
                normalizer=normalizer,
            )
        for job in scorable:
            await sync_job(
                driver,
                job_id=job.job_id,
                extraction=job.extraction,
                jd_quality=job.jd_quality,
                embedding=job.embedding,
                source_updated_at=job.source_updated_at,
                normalizer=normalizer,
            )

        for cv_row in approved_cvs:
            await sync_cv(
                driver,
                document=cv_row.document,
                original_name=cv_row.original_name,
                extraction_version=cv_row.extraction_version,
                source_updated_at=cv_row.source_updated_at,
                is_active=cv_row.is_active,
            )
        if legacy_active is not None:
            await _project_legacy_active_cv(driver, legacy_active)

        # Seed Skills/RELATED_TO when no Candidate and no Jobs still rebuild.
        if profile is None and not scorable:
            seed_skills = seed_skill_param_rows(normalizer)
            related = related_to_param_rows(normalizer)
            async with driver.session() as session:
                await project_seed_skills_and_related(
                    session,
                    seed_skills=seed_skills,
                    related=related,
                )
        return await count_graph(driver)
    except (CandidateSyncError, JobSyncError, CvSyncError) as exc:
        raise RebuildError(
            f"Graph projection failed during rebuild: {exc.message}",
            code=getattr(exc, "code", "REBUILD_FAILED"),
        ) from exc
    except RebuildError:
        raise
    except Exception as exc:
        raise RebuildError(
            "Graph projection failed during rebuild",
            code="REBUILD_FAILED",
        ) from exc


def format_counts(counts: RebuildCounts) -> str:
    """Format rebuild counts for stdout (stable key order, no secrets)."""
    lines = ["Neo4j rebuild complete (provider-free, SQLite read-only):"]
    for key in COUNT_ORDER:
        lines.append(f"  {key}: {counts.as_mapping()[key]}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    """Non-destructive help contract for the rebuild CLI (no store access)."""
    parser = argparse.ArgumentParser(
        prog="python -m app.graph.rebuild",
        description=(
            "Rebuild JobAgent Neo4j CV/Candidate/Job/Skill data from SQLite "
            "stored documents and embeddings without calling ShopAIKey or "
            "mutating SQLite. Destructive scope is limited to JobAgent labels "
            "CV, CVSection, CVEntry, Candidate, Job, and Skill (no unrestricted "
            "graph wipe). Only the active CV receives PROJECTS_TO. Authorized "
            "only inside the Compose backend container (choice C)."
        ),
        epilog=(
            "Canonical local Compose execution (choice C; run from repository "
            f"root with the stack up):\n  {CANONICAL_COMPOSE_REBUILD_COMMAND}\n\n"
            "Host wrapper is help/version only and never runs rebuild:\n"
            "  python infrastructure/scripts/rebuild_neo4j.py --help\n\n"
            "Runtime contract: APP_ENV=local, NEO4J_URI=bolt://neo4j:7687, "
            "SQLITE_PATH=/data/jobagent.db. Loopback host targets are refused. "
            "URL fetch, SSRF, and production multi-tenant safeguards remain "
            "out of MVP scope."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="JobAgent graph rebuild (provider-free)",
    )
    return parser


async def _async_main(
    *,
    settings: Settings | None = None,
    driver: AsyncGraphDriver | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    normalizer: SkillNormalizer | None = None,
    enforce_local_target: bool = True,
    stdout: TextIO | None = None,
) -> int:
    """Async entry used by CLI and injectable tests."""
    out = stdout if stdout is not None else sys.stdout
    cfg = settings if settings is not None else get_settings()
    owns_driver = driver is None
    graph: Any = driver
    try:
        if graph is None:
            graph = open_driver(cfg)
        factory = (
            session_factory
            if session_factory is not None
            else get_session_factory()
        )
        skill_norm = (
            normalizer if normalizer is not None else SkillNormalizer.production()
        )
        counts = await rebuild_graph(
            graph,
            session_factory=factory,
            normalizer=skill_norm,
            settings=cfg,
            enforce_local_target=enforce_local_target,
        )
        print(format_counts(counts), file=out)
        return 0
    except RebuildError as exc:
        print(f"REBUILD_FAILED ({exc.code}): {exc.message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"REBUILD_FAILED: {exc.__class__.__name__}", file=sys.stderr)
        return 1
    finally:
        if owns_driver and graph is not None:
            close = getattr(graph, "close", None)
            if callable(close):
                maybe = close()
                if asyncio.iscoroutine(maybe) or hasattr(maybe, "__await__"):
                    await maybe
            else:
                await close_driver(graph)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry: parse args (help is non-destructive) then run rebuild."""
    parser = build_arg_parser()
    parser.parse_args(list(argv) if argv is not None else None)
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANONICAL_COMPOSE_REBUILD_COMMAND",
    "CONFIGURATION_RESTORATION_GUIDANCE",
    "RebuildCounts",
    "RebuildError",
    "assert_local_compose_neo4j_target",
    "build_arg_parser",
    "format_counts",
    "main",
    "rebuild_graph",
]

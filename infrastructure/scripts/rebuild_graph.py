#!/usr/bin/env python3
"""Safe JobAgent Neo4j graph rebuild command.

Default execution is dry-run (non-destructive): prints the planned stages and
scoped Cypher without connecting or loading configuration values.

Destructive clearing requires ``--confirm-destructive``. Only JobAgent-derived
labels are cleared (``Candidate``, ``Job``, ``Skill``, ``JobFamily``). The
command never issues a database-wide unlabeled delete.

After clear + schema reapplication, the approved Candidate singleton and every
active full|partial Job are rebuilt from SQLite (embeddings recomputed), parity
of IDs/counts is verified, and Job/outbox sync state is updated only after
success.

Secrets, credential-bearing URIs, raw payloads, and document content are never
printed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, TextIO

# Allow ``python infrastructure/scripts/rebuild_graph.py`` from the repo root
# while reusing backend graph primitives (no duplicated driver/schema lifecycle).
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_BACKEND_ROOT: Final[Path] = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.session import (  # noqa: E402
    DatabaseSessionManager,
    create_session_manager,
)
from app.graph.candidate_sync import rebuild_candidate_projection  # noqa: E402
from app.graph.client import Neo4jClient  # noqa: E402
from app.graph.errors import GraphError  # noqa: E402
from app.graph.job_sync import JobEmbeddingPort  # noqa: E402
from app.graph.rebuild_jobs import (  # noqa: E402
    RebuildLoadError,
    RebuildSnapshot,
    load_rebuild_snapshot,
    project_jobs_for_rebuild,
)
from app.graph.rebuild_verify import (  # noqa: E402
    RebuildVerifyError,
    mark_rebuild_sync_states,
    verify_rebuild_parity,
)
from app.graph.schema import ensure_graph_schema  # noqa: E402

# Exit codes (stable for operators and tests).
EXIT_OK: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
# Retained for compatibility; full rebuild no longer returns incomplete.
EXIT_INCOMPLETE: Final[int] = 2

# Approved JobAgent-derived node labels only (master §8.3 / §21.4).
JOBAGENT_DERIVED_LABELS: Final[tuple[str, ...]] = (
    "Candidate",
    "Job",
    "Skill",
    "JobFamily",
)

# Static scoped clear statements. Each MATCH is label-bound; no unlabeled delete.
CLEAR_STATEMENTS: Final[tuple[str, ...]] = tuple(
    f"MATCH (n:{label}) DETACH DELETE n" for label in JOBAGENT_DERIVED_LABELS
)

# Forbidden substrings that would indicate indiscriminate database wipe.
_FORBIDDEN_CLEAR_MARKERS: Final[tuple[str, ...]] = (
    "DROP DATABASE",
    "DROP GRAPH",
    "DELETE ALL",
    "MATCH (n) DETACH DELETE",
    "MATCH () DETACH DELETE",
    "MATCH (n) DELETE",
)


class StageName(StrEnum):
    """Named rebuild pipeline stages (master §21.4)."""

    CLEAR_DERIVED = "clear_jobagent_derived"
    RECREATE_SCHEMA = "recreate_schema"
    REBUILD_CANDIDATE = "rebuild_candidate"
    LOAD_SQLITE_RECORDS = "load_sqlite_records"
    REBUILD_ENTITIES = "rebuild_entities"
    RECOMPUTE_EMBEDDINGS = "recompute_embeddings"
    VERIFY_ENTITY_COUNTS = "verify_entity_counts"
    UPDATE_SYNC_STATES = "update_sync_states"


class StageStatus(StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    NOT_IMPLEMENTED = "not_implemented"
    FAILED = "failed"
    SKIPPED = "skipped"


ALL_STAGES: Final[tuple[StageName, ...]] = (
    StageName.CLEAR_DERIVED,
    StageName.RECREATE_SCHEMA,
    StageName.REBUILD_CANDIDATE,
    StageName.LOAD_SQLITE_RECORDS,
    StageName.REBUILD_ENTITIES,
    StageName.RECOMPUTE_EMBEDDINGS,
    StageName.VERIFY_ENTITY_COUNTS,
    StageName.UPDATE_SYNC_STATES,
)
# All stages are implemented; kept for test compatibility.
IMPLEMENTED_STAGES: Final[tuple[StageName, ...]] = ALL_STAGES
DEFERRED_STAGES: Final[tuple[StageName, ...]] = ()

EnsureSchemaFn = Callable[[Neo4jClient], Awaitable[None]]


class RebuildClient(Protocol):
    """Graph surface required by the rebuild pipeline."""

    async def run_query(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
    ) -> None: ...

    async def fetch_records(
        self,
        query: str,
        parameters: dict[str, object] | None = None,
    ) -> list[dict[str, object]]: ...


@dataclass(frozen=True, slots=True)
class StageResult:
    name: StageName
    status: StageStatus
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RebuildReport:
    """Structured rebuild outcome (no secrets)."""

    dry_run: bool
    stages: tuple[StageResult, ...]
    exit_code: int
    messages: tuple[str, ...]


def assert_clear_statements_are_scoped(
    statements: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Return clear Cypher after verifying JobAgent-only label scope.

    Rejects unlabeled or database-wide wipe patterns. Safe to call from tests
    and from the command before any destructive execution.
    """
    chosen = tuple(statements) if statements is not None else CLEAR_STATEMENTS
    if not chosen:
        raise ValueError("clear statements must not be empty")
    if len(chosen) != len(JOBAGENT_DERIVED_LABELS):
        raise ValueError("clear statements must cover exactly the approved labels")

    joined_upper = "\n".join(chosen).upper()
    for marker in _FORBIDDEN_CLEAR_MARKERS:
        if marker.upper() in joined_upper:
            raise ValueError("indiscriminate clear statement rejected")

    for label, statement in zip(JOBAGENT_DERIVED_LABELS, chosen, strict=True):
        expected = f"MATCH (n:{label}) DETACH DELETE n"
        if statement != expected:
            raise ValueError("clear statement must be exact label-scoped DETACH DELETE")
        if f"(n:{label})" not in statement:
            raise ValueError("clear statement missing approved label")
        if "MATCH (n) " in statement or "MATCH () " in statement:
            raise ValueError("unlabeled clear statement rejected")
    return chosen


def build_parser() -> argparse.ArgumentParser:
    """CLI parser. Help text documents safety controls without loading config."""
    parser = argparse.ArgumentParser(
        prog="rebuild_graph.py",
        description=(
            "Safe JobAgent Neo4j graph rebuild. "
            "Default is dry-run (non-destructive): no connection and no config "
            "values are loaded or printed. Destructive clear of only "
            "Candidate/Job/Skill/JobFamily requires --confirm-destructive. "
            "Rebuilds Candidate and active full|partial Jobs from SQLite, "
            "recomputes embeddings, verifies ID/count parity, and updates "
            "sync state only after verified success."
        ),
        epilog=(
            "Safety: never clears an entire Neo4j database. "
            "Schema recreation reuses backend ensure_graph_schema. "
            "Passwords, credential-bearing URIs, raw payloads, and document "
            "content are never printed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print planned stages and scoped clear Cypher without connecting "
            "(default when --confirm-destructive is absent)."
        ),
    )
    parser.add_argument(
        "--confirm-destructive",
        action="store_true",
        help=(
            "Explicit confirmation required to clear JobAgent-derived labels "
            "and reapply constraints/vector index. Without this flag the "
            "command remains non-destructive."
        ),
    )
    return parser


def format_report_lines(report: RebuildReport) -> list[str]:
    """Human-readable status lines with no configuration or secret values."""
    lines: list[str] = []
    mode = "dry_run" if report.dry_run else "destructive"
    lines.append(f"rebuild_mode={mode}")
    lines.append(f"exit_code={report.exit_code}")
    for stage in report.stages:
        detail = f" detail={stage.detail}" if stage.detail else ""
        lines.append(f"stage={stage.name.value} status={stage.status.value}{detail}")
    for message in report.messages:
        lines.append(message)
    return lines


def _dry_run_report() -> RebuildReport:
    """Build a non-destructive plan report (no client, no settings)."""
    assert_clear_statements_are_scoped()
    stages = tuple(
        StageResult(name=name, status=StageStatus.PLANNED) for name in ALL_STAGES
    )
    messages = (
        "dry_run=true; no connection opened; no configuration values loaded",
        "clear_scope=Candidate,Job,Skill,JobFamily",
        *(f"clear_cypher={statement}" for statement in CLEAR_STATEMENTS),
        "schema_stage=delegates_to_ensure_graph_schema",
        "job_stages=load_project_verify_then_mark_sync",
    )
    return RebuildReport(
        dry_run=True,
        stages=stages,
        exit_code=EXIT_OK,
        messages=messages,
    )


def _fail_report(
    stage_results: list[StageResult],
    *,
    failed: StageName,
    detail: str,
    messages: list[str],
) -> RebuildReport:
    """Append FAILED for current stage and SKIPPED for remaining stages."""
    stage_results.append(
        StageResult(name=failed, status=StageStatus.FAILED, detail=detail)
    )
    started = {s.name for s in stage_results}
    for name in ALL_STAGES:
        if name not in started:
            stage_results.append(
                StageResult(name=name, status=StageStatus.SKIPPED, detail="prior_failure")
            )
    messages.append(f"error={detail}")
    return RebuildReport(
        dry_run=False,
        stages=tuple(stage_results),
        exit_code=EXIT_FAILURE,
        messages=tuple(messages),
    )


async def run_rebuild(
    *,
    dry_run: bool,
    confirm_destructive: bool,
    client: Neo4jClient | None = None,
    database: DatabaseSessionManager | None = None,
    embedding_service: JobEmbeddingPort | None = None,
    ensure_schema: EnsureSchemaFn | None = None,
) -> RebuildReport:
    """Execute or plan the rebuild pipeline.

    Parameters
    ----------
    dry_run:
        When True, plan only — no graph operations.
    confirm_destructive:
        Must be True for any destructive clear. Ignored when dry_run is True.
    client:
        Required when not dry_run. Injected in tests (fake driver).
    database:
        Required for Candidate/Job rebuild from SQLite.
    embedding_service:
        Required to recompute Job vectors during rebuild.
    ensure_schema:
        Optional override for schema recreation (defaults to ensure_graph_schema).
    """
    if dry_run or not confirm_destructive:
        return _dry_run_report()

    if client is None:
        return RebuildReport(
            dry_run=False,
            stages=(
                StageResult(
                    name=StageName.CLEAR_DERIVED,
                    status=StageStatus.FAILED,
                    detail="client_required",
                ),
            ),
            exit_code=EXIT_FAILURE,
            messages=("error=client_required",),
        )

    schema_fn: EnsureSchemaFn = (
        ensure_schema if ensure_schema is not None else ensure_graph_schema
    )
    stage_results: list[StageResult] = []
    messages: list[str] = [
        "destructive_confirmed=true",
        "clear_scope=Candidate,Job,Skill,JobFamily",
    ]

    # --- Stage: clear JobAgent-derived subgraph only ---
    try:
        statements = assert_clear_statements_are_scoped()
        for statement in statements:
            await client.run_query(statement, {})
        stage_results.append(
            StageResult(
                name=StageName.CLEAR_DERIVED,
                status=StageStatus.COMPLETED,
                detail="scoped_detach_delete",
            )
        )
    except GraphError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.CLEAR_DERIVED,
            detail=exc.code.value,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.CLEAR_DERIVED,
            detail="clear_failed",
            messages=messages,
        )

    # --- Stage: recreate constraints / vector index ---
    try:
        await schema_fn(client)
        stage_results.append(
            StageResult(
                name=StageName.RECREATE_SCHEMA,
                status=StageStatus.COMPLETED,
                detail="ensure_graph_schema",
            )
        )
    except GraphError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.RECREATE_SCHEMA,
            detail=exc.code.value,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.RECREATE_SCHEMA,
            detail="schema_failed",
            messages=messages,
        )

    # --- Remaining stages require SQLite + embedding seam ---
    if database is None:
        return _fail_report(
            stage_results,
            failed=StageName.REBUILD_CANDIDATE,
            detail="database_required",
            messages=messages,
        )
    if embedding_service is None:
        return _fail_report(
            stage_results,
            failed=StageName.REBUILD_CANDIDATE,
            detail="embedding_service_required",
            messages=messages,
        )

    # --- Stage: rebuild Candidate slice ---
    try:
        projected = await rebuild_candidate_projection(database, client)
        stage_results.append(
            StageResult(
                name=StageName.REBUILD_CANDIDATE,
                status=StageStatus.COMPLETED,
                detail=f"projected={projected}",
            )
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.REBUILD_CANDIDATE,
            detail="candidate_rebuild_failed",
            messages=messages,
        )

    # --- Stage: load active/scorable Jobs from SQLite ---
    snapshot: RebuildSnapshot
    try:
        snapshot = await load_rebuild_snapshot(database)
        stage_results.append(
            StageResult(
                name=StageName.LOAD_SQLITE_RECORDS,
                status=StageStatus.COMPLETED,
                detail=f"eligible_jobs={len(snapshot.eligible_job_ids)}",
            )
        )
    except RebuildLoadError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.LOAD_SQLITE_RECORDS,
            detail=exc.code,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.LOAD_SQLITE_RECORDS,
            detail="load_sqlite_failed",
            messages=messages,
        )

    # --- Stage: rebuild Job/Skill/JobFamily entities (with embeddings) ---
    try:
        projected_ids = await project_jobs_for_rebuild(
            snapshot.jobs,
            client,
            embedding_service,
        )
        stage_results.append(
            StageResult(
                name=StageName.REBUILD_ENTITIES,
                status=StageStatus.COMPLETED,
                detail=f"projected_jobs={len(projected_ids)}",
            )
        )
        # Embeddings are recomputed inside project_eligible_job (no second pass).
        stage_results.append(
            StageResult(
                name=StageName.RECOMPUTE_EMBEDDINGS,
                status=StageStatus.COMPLETED,
                detail=f"recomputed={len(projected_ids)}",
            )
        )
    except RebuildLoadError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.REBUILD_ENTITIES,
            detail=exc.code,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.REBUILD_ENTITIES,
            detail="entity_rebuild_failed",
            messages=messages,
        )

    # --- Stage: verify ID/count parity ---
    try:
        observed = await verify_rebuild_parity(client, snapshot)
        stage_results.append(
            StageResult(
                name=StageName.VERIFY_ENTITY_COUNTS,
                status=StageStatus.COMPLETED,
                detail=(
                    f"jobs={len(observed.job_ids)};"
                    f"skills={observed.skill_count};"
                    f"families={observed.family_count}"
                ),
            )
        )
    except RebuildVerifyError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.VERIFY_ENTITY_COUNTS,
            detail=exc.code,
            messages=messages,
        )
    except GraphError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.VERIFY_ENTITY_COUNTS,
            detail=exc.code.value,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.VERIFY_ENTITY_COUNTS,
            detail="verify_failed",
            messages=messages,
        )

    # --- Stage: mark sync states only after verified success ---
    try:
        marked = await mark_rebuild_sync_states(
            database,
            snapshot.eligible_job_ids,
        )
        stage_results.append(
            StageResult(
                name=StageName.UPDATE_SYNC_STATES,
                status=StageStatus.COMPLETED,
                detail=f"marked_synced={marked}",
            )
        )
    except RebuildVerifyError as exc:
        return _fail_report(
            stage_results,
            failed=StageName.UPDATE_SYNC_STATES,
            detail=exc.code,
            messages=messages,
        )
    except Exception:
        return _fail_report(
            stage_results,
            failed=StageName.UPDATE_SYNC_STATES,
            detail="sync_state_update_failed",
            messages=messages,
        )

    messages.append(
        "rebuild_complete=true; "
        f"eligible_jobs={len(snapshot.eligible_job_ids)}; "
        f"candidate_projected={snapshot.expected_candidate_count}"
    )
    return RebuildReport(
        dry_run=False,
        stages=tuple(stage_results),
        exit_code=EXIT_OK,
        messages=tuple(messages),
    )


def _load_runtime_from_root_settings() -> (
    tuple[Neo4jClient, DatabaseSessionManager, JobEmbeddingPort]
):
    """Construct runtime dependencies without printing configuration."""
    from app.config import load_settings
    from app.services.embeddings import JobEmbeddingService

    settings = load_settings()
    return (
        Neo4jClient.from_settings(settings),
        create_session_manager(settings.sqlite_path),
        JobEmbeddingService.from_settings(settings),
    )


async def _run_destructive_with_lifecycle() -> RebuildReport:
    """Open client, run destructive pipeline, always close the client."""
    client: Neo4jClient | None = None
    database: DatabaseSessionManager | None = None
    try:
        client, database, embedding_service = _load_runtime_from_root_settings()
    except Exception:
        return RebuildReport(
            dry_run=False,
            stages=(
                StageResult(
                    name=StageName.CLEAR_DERIVED,
                    status=StageStatus.FAILED,
                    detail="configuration_or_client_failed",
                ),
            ),
            exit_code=EXIT_FAILURE,
            messages=("error=configuration_or_client_failed",),
        )

    try:
        return await run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=client,
            database=database,
            embedding_service=embedding_service,
        )
    finally:
        try:
            await client.close()
        except Exception:
            pass
        if database is not None:
            try:
                await database.dispose()
            except Exception:
                pass


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    client: Neo4jClient | None = None,
    database: DatabaseSessionManager | None = None,
    embedding_service: JobEmbeddingPort | None = None,
    ensure_schema: EnsureSchemaFn | None = None,
) -> int:
    """CLI entrypoint. Injectable client/streams for tests; no live defaults."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Explicit --dry-run wins over confirm when both are passed (prefer safety).
    dry_run = bool(args.dry_run) or not bool(args.confirm_destructive)
    confirm = bool(args.confirm_destructive) and not bool(args.dry_run)

    if dry_run:
        report = _dry_run_report()
        for line in format_report_lines(report):
            print(line, file=out)
        return report.exit_code

    if client is not None:
        report = asyncio.run(
            run_rebuild(
                dry_run=False,
                confirm_destructive=confirm,
                client=client,
                database=database,
                embedding_service=embedding_service,
                ensure_schema=ensure_schema,
            )
        )
    else:
        report = asyncio.run(_run_destructive_with_lifecycle())

    stream = err if report.exit_code != EXIT_OK else out
    for line in format_report_lines(report):
        print(line, file=stream)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

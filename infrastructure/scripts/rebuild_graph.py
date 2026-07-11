#!/usr/bin/env python3
"""Safe JobAgent Neo4j graph rebuild command skeleton.

Default execution is dry-run (non-destructive): prints the planned stages and
scoped Cypher without connecting or loading configuration values.

Destructive clearing requires ``--confirm-destructive``. Only JobAgent-derived
labels are cleared (``Candidate``, ``Job``, ``Skill``, ``JobFamily``). The
command never issues a database-wide unlabeled delete.

After clear + schema reapplication (delegated to ``ensure_graph_schema``), later
rebuild stages remain explicitly unimplemented and return a non-success exit
code so a partial skeleton cannot be mistaken for a full rebuild.

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
from typing import Final, TextIO

# Allow ``python infrastructure/scripts/rebuild_graph.py`` from the repo root
# while reusing backend graph primitives (no duplicated driver/schema lifecycle).
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_BACKEND_ROOT: Final[Path] = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.graph.client import Neo4jClient  # noqa: E402
from app.graph.errors import GraphError  # noqa: E402
from app.graph.schema import ensure_graph_schema  # noqa: E402

# Exit codes (stable for operators and tests).
EXIT_OK: Final[int] = 0
EXIT_FAILURE: Final[int] = 1
EXIT_INCOMPLETE: Final[int] = 2  # clear+schema ok, deferred stages not implemented

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


# Stages that clear + schema may complete; the rest stay deferred.
IMPLEMENTED_STAGES: Final[tuple[StageName, ...]] = (
    StageName.CLEAR_DERIVED,
    StageName.RECREATE_SCHEMA,
)
DEFERRED_STAGES: Final[tuple[StageName, ...]] = (
    StageName.LOAD_SQLITE_RECORDS,
    StageName.REBUILD_ENTITIES,
    StageName.RECOMPUTE_EMBEDDINGS,
    StageName.VERIFY_ENTITY_COUNTS,
    StageName.UPDATE_SYNC_STATES,
)
ALL_STAGES: Final[tuple[StageName, ...]] = IMPLEMENTED_STAGES + DEFERRED_STAGES

EnsureSchemaFn = Callable[[Neo4jClient], Awaitable[None]]


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
        # Extra guard: label token must appear; bare MATCH (n) must not.
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
            "Safe JobAgent Neo4j graph rebuild skeleton. "
            "Default is dry-run (non-destructive): no connection and no config "
            "values are loaded or printed. Destructive clear of only "
            "Candidate/Job/Skill/JobFamily requires --confirm-destructive. "
            "Later SQLite load, entity rebuild, embedding recompute, count "
            "verification, and sync-state update stages are not implemented "
            "and return non-success after clear+schema."
        ),
        epilog=(
            "Safety: never clears an entire Neo4j database. "
            "Schema recreation reuses backend ensure_graph_schema (04A). "
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
        "deferred_stages=explicit_not_implemented_on_execute",
    )
    return RebuildReport(
        dry_run=True,
        stages=stages,
        exit_code=EXIT_OK,
        messages=messages,
    )


async def run_rebuild(
    *,
    dry_run: bool,
    confirm_destructive: bool,
    client: Neo4jClient | None = None,
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
    ensure_schema:
        Optional override for schema recreation (defaults to ensure_graph_schema).
    """
    if dry_run or not confirm_destructive:
        # Non-destructive path: never connect.
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
        stage_results.append(
            StageResult(
                name=StageName.CLEAR_DERIVED,
                status=StageStatus.FAILED,
                detail=exc.code.value,
            )
        )
        for name in ALL_STAGES[1:]:
            stage_results.append(
                StageResult(name=name, status=StageStatus.SKIPPED, detail="prior_failure")
            )
        messages.append(f"error={exc.code.value}")
        return RebuildReport(
            dry_run=False,
            stages=tuple(stage_results),
            exit_code=EXIT_FAILURE,
            messages=tuple(messages),
        )
    except Exception:
        stage_results.append(
            StageResult(
                name=StageName.CLEAR_DERIVED,
                status=StageStatus.FAILED,
                detail="clear_failed",
            )
        )
        for name in ALL_STAGES[1:]:
            stage_results.append(
                StageResult(name=name, status=StageStatus.SKIPPED, detail="prior_failure")
            )
        messages.append("error=clear_failed")
        return RebuildReport(
            dry_run=False,
            stages=tuple(stage_results),
            exit_code=EXIT_FAILURE,
            messages=tuple(messages),
        )

    # --- Stage: recreate constraints / vector index (04A primitive) ---
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
        stage_results.append(
            StageResult(
                name=StageName.RECREATE_SCHEMA,
                status=StageStatus.FAILED,
                detail=exc.code.value,
            )
        )
        for name in DEFERRED_STAGES:
            stage_results.append(
                StageResult(name=name, status=StageStatus.SKIPPED, detail="prior_failure")
            )
        messages.append(f"error={exc.code.value}")
        return RebuildReport(
            dry_run=False,
            stages=tuple(stage_results),
            exit_code=EXIT_FAILURE,
            messages=tuple(messages),
        )
    except Exception:
        stage_results.append(
            StageResult(
                name=StageName.RECREATE_SCHEMA,
                status=StageStatus.FAILED,
                detail="schema_failed",
            )
        )
        for name in DEFERRED_STAGES:
            stage_results.append(
                StageResult(name=name, status=StageStatus.SKIPPED, detail="prior_failure")
            )
        messages.append("error=schema_failed")
        return RebuildReport(
            dry_run=False,
            stages=tuple(stage_results),
            exit_code=EXIT_FAILURE,
            messages=tuple(messages),
        )

    # --- Deferred stages: honest not-implemented (no fake success) ---
    for name in DEFERRED_STAGES:
        stage_results.append(
            StageResult(
                name=name,
                status=StageStatus.NOT_IMPLEMENTED,
                detail="deferred_to_later_plan",
            )
        )
    messages.append(
        "rebuild_incomplete=true; deferred stages not implemented; "
        "full rebuild requires later SQLite loaders and sync"
    )
    return RebuildReport(
        dry_run=False,
        stages=tuple(stage_results),
        exit_code=EXIT_INCOMPLETE,
        messages=tuple(messages),
    )


def _load_client_from_root_settings() -> Neo4jClient:
    """Construct a client from root settings without printing configuration."""
    from app.config import load_settings

    settings = load_settings()
    return Neo4jClient.from_settings(settings)


async def _run_destructive_with_lifecycle() -> RebuildReport:
    """Open client, run destructive pipeline, always close the client."""
    client: Neo4jClient | None = None
    try:
        client = _load_client_from_root_settings()
    except Exception:
        # Settings / construction failures must not leak secrets.
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
        )
    finally:
        close_failed = False
        try:
            await client.close()
        except Exception:
            close_failed = True
        if close_failed:
            # Close failures are non-fatal for reporting; never attach details.
            pass


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    client: Neo4jClient | None = None,
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

    # Destructive path.
    if client is not None:
        # Test injection: never load real settings.
        report = asyncio.run(
            run_rebuild(
                dry_run=False,
                confirm_destructive=confirm,
                client=client,
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

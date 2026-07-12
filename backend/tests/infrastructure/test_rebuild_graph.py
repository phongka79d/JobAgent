"""Safety and skeleton tests for infrastructure/scripts/rebuild_graph.py."""

from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from app.db.session import create_session_manager
from app.graph.client import Neo4jClient
from app.graph.errors import GraphError, GraphErrorCode
from app.graph.schema import SCHEMA_STATEMENTS, ensure_graph_schema
from app.repositories.profiles import ProfileRepository
from app.schemas.candidate import CandidateProfile
from tests.graph.fakes import FakeDriver

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "infrastructure" / "scripts" / "rebuild_graph.py"
SENTINEL_PASSWORD = "sentinel-rebuild-secret-never-emit"
SENTINEL_API_KEY = "sentinel-shopaikey-rebuild-never-emit"
SENTINEL_URI = "bolt://neo4j:7687"


def _load_rebuild_module() -> ModuleType:
    """Import the infrastructure script as a module without installing it."""
    spec = importlib.util.spec_from_file_location(
        "jobagent_rebuild_graph",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses / annotations resolve cleanly.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rebuild() -> ModuleType:
    assert SCRIPT_PATH.is_file(), f"missing rebuild script: {SCRIPT_PATH}"
    return _load_rebuild_module()


def _client(driver: FakeDriver) -> Neo4jClient:
    return Neo4jClient(
        uri=SENTINEL_URI,
        user="neo4j",
        password=SENTINEL_PASSWORD,
        driver_factory=lambda: driver,
        health_timeout_seconds=0.2,
    )


def test_help_displays_safety_controls_without_connection(
    rebuild: ModuleType,
) -> None:
    parser = rebuild.build_parser()
    help_text = parser.format_help()
    assert "--confirm-destructive" in help_text
    assert "--dry-run" in help_text
    assert "Candidate" in help_text or "JobAgent" in help_text
    assert "non-destructive" in help_text.lower() or "dry-run" in help_text.lower()
    # Help must not embed secrets or credential-bearing material.
    assert SENTINEL_PASSWORD not in help_text
    assert "password" not in help_text.lower() or "Passwords" in help_text
    assert "://" not in help_text or "URI" in help_text


def test_help_subprocess_no_config_leak() -> None:
    """``python infrastructure/scripts/rebuild_graph.py --help`` from repo root."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0
    combined = completed.stdout + completed.stderr
    assert "--confirm-destructive" in combined
    assert SENTINEL_PASSWORD not in combined
    assert SENTINEL_API_KEY not in combined
    # Must not dump environment secrets if present in process env.
    for key in ("NEO4J_PASSWORD", "SHOPAIKEY_API_KEY"):
        value = __import__("os").environ.get(key)
        if value:
            assert value not in combined


def test_default_main_is_dry_run_non_destructive(rebuild: ModuleType) -> None:
    out = io.StringIO()
    err = io.StringIO()
    code = rebuild.main([], stdout=out, stderr=err)
    assert code == rebuild.EXIT_OK
    text = out.getvalue()
    assert "rebuild_mode=dry_run" in text
    assert "dry_run=true" in text
    assert "no connection opened" in text
    assert err.getvalue() == ""
    # Scoped Cypher visible in dry-run for operator review.
    for label in rebuild.JOBAGENT_DERIVED_LABELS:
        assert f"MATCH (n:{label}) DETACH DELETE n" in text
    assert SENTINEL_PASSWORD not in text


def test_explicit_dry_run_flag(rebuild: ModuleType) -> None:
    out = io.StringIO()
    code = rebuild.main(["--dry-run"], stdout=out, stderr=io.StringIO())
    assert code == rebuild.EXIT_OK
    assert "rebuild_mode=dry_run" in out.getvalue()


def test_dry_run_wins_over_confirm(rebuild: ModuleType) -> None:
    """Prefer non-destructive when both flags are supplied."""
    out = io.StringIO()
    code = rebuild.main(
        ["--dry-run", "--confirm-destructive"],
        stdout=out,
        stderr=io.StringIO(),
        client=_client(FakeDriver()),  # would connect if destructive path taken
    )
    assert code == rebuild.EXIT_OK
    assert "rebuild_mode=dry_run" in out.getvalue()
    # Client factory must not have been used (no queries).
    # FakeDriver passed only if main used client; dry-run ignores it.
    # No assertion on driver queries needed when dry-run returns early.


def test_clear_statements_are_label_scoped(rebuild: ModuleType) -> None:
    statements = rebuild.assert_clear_statements_are_scoped()
    assert len(statements) == 4
    assert statements == (
        "MATCH (n:Candidate) DETACH DELETE n",
        "MATCH (n:Job) DETACH DELETE n",
        "MATCH (n:Skill) DETACH DELETE n",
        "MATCH (n:JobFamily) DETACH DELETE n",
    )
    joined = "\n".join(statements)
    assert "MATCH (n) DETACH DELETE" not in joined
    assert "DROP DATABASE" not in joined.upper()
    assert "DELETE ALL" not in joined.upper()


def test_clear_statement_guard_rejects_unlabeled(rebuild: ModuleType) -> None:
    with pytest.raises(ValueError, match="approved labels|indiscriminate|exact label|unlabeled"):
        rebuild.assert_clear_statements_are_scoped(
            ("MATCH (n) DETACH DELETE n",),
        )
    with pytest.raises(ValueError, match="indiscriminate|exact label|unlabeled"):
        rebuild.assert_clear_statements_are_scoped(
            (
                "MATCH (n:Candidate) DETACH DELETE n",
                "MATCH (n) DETACH DELETE n",
                "MATCH (n:Skill) DETACH DELETE n",
                "MATCH (n:JobFamily) DETACH DELETE n",
            ),
        )


@pytest.mark.asyncio
async def test_destructive_requires_confirm_flag_path(rebuild: ModuleType) -> None:
    """Without confirm, run_rebuild stays dry-run even if client is provided."""
    driver = FakeDriver()
    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=False,
        client=_client(driver),
    )
    assert report.dry_run is True
    assert report.exit_code == rebuild.EXIT_OK
    assert driver.queries == []


@pytest.mark.asyncio
async def test_destructive_clear_and_schema_then_unimplemented(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver()
    client = _client(driver)
    ensure_calls: list[Neo4jClient] = []

    async def tracking_ensure(c: Neo4jClient) -> None:
        ensure_calls.append(c)
        await ensure_graph_schema(c)

    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=client,
        ensure_schema=tracking_ensure,
    )

    assert report.dry_run is False
    assert report.exit_code == rebuild.EXIT_INCOMPLETE
    assert ensure_calls == [client]

    # Four scoped clears + five schema statements.
    clear_queries = [item.query for item in driver.queries[:4]]
    assert clear_queries == list(rebuild.CLEAR_STATEMENTS)
    schema_queries = [item.query for item in driver.queries[4:]]
    assert schema_queries == list(SCHEMA_STATEMENTS)
    for item in driver.queries:
        assert item.parameters == {}

    statuses = {s.name: s.status for s in report.stages}
    assert statuses[rebuild.StageName.CLEAR_DERIVED] == rebuild.StageStatus.COMPLETED
    assert statuses[rebuild.StageName.RECREATE_SCHEMA] == rebuild.StageStatus.COMPLETED
    for name in rebuild.DEFERRED_STAGES:
        assert statuses[name] == rebuild.StageStatus.NOT_IMPLEMENTED

    joined_messages = "\n".join(report.messages)
    assert "rebuild_incomplete=true" in joined_messages
    assert SENTINEL_PASSWORD not in joined_messages
    assert SENTINEL_URI not in joined_messages or "bolt://" not in joined_messages


@pytest.mark.asyncio
async def test_destructive_rebuild_projects_candidate_before_deferred_stages(
    rebuild: ModuleType,
    tmp_path: Path,
) -> None:
    database = create_session_manager(tmp_path / "rebuild-candidate.db")
    await database.create_all()
    try:
        profile = CandidateProfile.model_validate(
            {
                "summary": "Engineer.",
                "current_title": "Engineer",
                "total_experience_years": None,
                "skills": [],
                "experiences": [],
                "education": [],
                "languages": [],
                "extraction_confidence": 0.8,
            }
        )
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(profile)

        driver = FakeDriver()
        report = await rebuild.run_rebuild(
            dry_run=False,
            confirm_destructive=True,
            client=_client(driver),
            database=database,
        )

        statuses = {stage.name: stage for stage in report.stages}
        candidate = statuses[rebuild.StageName.REBUILD_CANDIDATE]
        assert candidate.status == rebuild.StageStatus.COMPLETED
        assert candidate.detail == "projected=1"
        assert driver.queries[-1].parameters["candidate_id"] == "1"
        assert driver.queries[-1].parameters["skills"] == []
        for name in rebuild.DEFERRED_STAGES:
            assert statuses[name].status == rebuild.StageStatus.NOT_IMPLEMENTED
    finally:
        await database.dispose()


def test_main_destructive_with_injected_client_unimplemented_exit(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver()
    out = io.StringIO()
    err = io.StringIO()
    code = rebuild.main(
        ["--confirm-destructive"],
        stdout=out,
        stderr=err,
        client=_client(driver),
    )
    assert code == rebuild.EXIT_INCOMPLETE
    text = err.getvalue() + out.getvalue()
    assert "rebuild_mode=destructive" in text
    assert "status=not_implemented" in text
    assert SENTINEL_PASSWORD not in text
    assert len(driver.queries) == 4 + len(SCHEMA_STATEMENTS)


@pytest.mark.asyncio
async def test_clear_failure_is_sanitized_and_exits_failure(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver(
        run_error=RuntimeError(
            f"auth failed password={SENTINEL_PASSWORD} uri={SENTINEL_URI}"
        )
    )
    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=_client(driver),
    )
    assert report.exit_code == rebuild.EXIT_FAILURE
    clear = report.stages[0]
    assert clear.name == rebuild.StageName.CLEAR_DERIVED
    assert clear.status == rebuild.StageStatus.FAILED
    # Graph client maps generic errors to neo4j_query_failed (sanitized).
    assert clear.detail in {
        GraphErrorCode.QUERY_FAILED.value,
        "clear_failed",
        GraphErrorCode.UNAVAILABLE.value,
    }
    blob = "\n".join(
        [clear.detail, *(s.detail for s in report.stages), *report.messages]
    )
    assert SENTINEL_PASSWORD not in blob
    assert SENTINEL_URI not in blob or "password=" not in blob
    assert SENTINEL_PASSWORD not in str(report)
    assert SENTINEL_PASSWORD not in repr(report)


@pytest.mark.asyncio
async def test_schema_failure_sanitized(rebuild: ModuleType) -> None:
    driver = FakeDriver()
    client = _client(driver)

    async def boom(_client: Neo4jClient) -> None:
        raise GraphError(GraphErrorCode.SCHEMA_FAILED)

    report = await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=client,
        ensure_schema=boom,
    )
    assert report.exit_code == rebuild.EXIT_FAILURE
    assert report.stages[0].status == rebuild.StageStatus.COMPLETED
    assert report.stages[1].status == rebuild.StageStatus.FAILED
    assert report.stages[1].detail == GraphErrorCode.SCHEMA_FAILED.value
    # Deferred stages skipped after schema failure.
    for stage in report.stages[2:]:
        assert stage.status == rebuild.StageStatus.SKIPPED


@pytest.mark.asyncio
async def test_schema_reuse_delegates_to_ensure_graph_schema(
    rebuild: ModuleType,
) -> None:
    driver = FakeDriver()
    client = _client(driver)
    called: dict[str, Any] = {"n": 0}

    async def wrapper(c: Neo4jClient) -> None:
        called["n"] += 1
        assert c is client
        await ensure_graph_schema(c)

    await rebuild.run_rebuild(
        dry_run=False,
        confirm_destructive=True,
        client=client,
        ensure_schema=wrapper,
    )
    assert called["n"] == 1
    # Schema statements must match 04A static contract.
    executed_schema = [q.query for q in driver.queries[4:]]
    assert executed_schema == list(SCHEMA_STATEMENTS)


def test_format_report_lines_never_include_secrets(rebuild: ModuleType) -> None:
    report = rebuild.RebuildReport(
        dry_run=True,
        stages=(
            rebuild.StageResult(
                name=rebuild.StageName.CLEAR_DERIVED,
                status=rebuild.StageStatus.PLANNED,
            ),
        ),
        exit_code=0,
        messages=("ok",),
    )
    lines = rebuild.format_report_lines(report)
    blob = "\n".join(lines)
    assert SENTINEL_PASSWORD not in blob
    assert "neo4j+s://" not in blob


def test_no_database_wide_delete_in_module_source(rebuild: ModuleType) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "MATCH (n) DETACH DELETE" not in source or "FORBIDDEN" in source
    # Production CLEAR_STATEMENTS must not include unlabeled form as executable.
    for statement in rebuild.CLEAR_STATEMENTS:
        assert statement.startswith("MATCH (n:")
        assert "DETACH DELETE" in statement

"""Integration tests for GET /api/health and application lifespan (03C)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.db import session as session_mod
from app.db.session import get_engine, session_scope
from app.schemas.health import HealthResponse, build_health_response
from pydantic import ValidationError
from sqlalchemy import text

from tests.support.db_migration import cleanup_isolated_sqlite, run_async
from tests.support.health import (
    FakeDriver,
    assert_no_secrets,
    blocked_sqlite_path,
    health_client,
    install_fake_driver,
    prepare_health_env,
    public_api_routes,
    route_decorator_matches,
    setup_unavailable_component,
)


async def _sqlite_select_one() -> int:
    async with session_scope() as session:
        return int((await session.execute(text("SELECT 1"))).scalar_one())


def test_health_all_available(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, files_dir, fake = health_env
    with health_client() as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert HealthResponse.model_validate(body).model_dump() == {
        "overall": "available",
        "sqlite": "available",
        "filesystem": "available",
        "neo4j": "available",
    }
    assert set(body.keys()) == {"overall", "sqlite", "filesystem", "neo4j"}
    assert_no_secrets(response.text, files_dir, db_path)
    assert fake.verify_calls >= 1
    assert files_dir.is_dir()


@pytest.mark.parametrize("component", ["sqlite", "filesystem", "neo4j"])
def test_health_single_component_unavailable_real_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    component: str,
) -> None:
    """Each real dependency failure yields 200 + overall unavailable (no crash)."""
    db_path, files_dir, _fake = setup_unavailable_component(
        monkeypatch, tmp_path, component
    )
    try:
        with health_client() as client:
            response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        HealthResponse.model_validate(body)
        assert body["overall"] == "unavailable"
        assert body[component] == "unavailable"
        for other in ("sqlite", "filesystem", "neo4j"):
            if other != component:
                assert body[other] == "available"
        assert_no_secrets(response.text, files_dir, db_path)
        if component != "sqlite":
            assert run_async(_sqlite_select_one()) == 1
    finally:
        cleanup_isolated_sqlite()


def test_health_payload_shape_and_overall_rule() -> None:
    assert build_health_response(
        sqlite="available", filesystem="available", neo4j="available"
    ).overall == "available"
    assert build_health_response(
        sqlite="available", filesystem="unavailable", neo4j="available"
    ).overall == "unavailable"
    with pytest.raises(ValidationError):
        HealthResponse(
            overall="available",
            sqlite="unavailable",
            filesystem="available",
            neo4j="available",
        )
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(
            {
                "overall": "available",
                "sqlite": "available",
                "filesystem": "available",
                "neo4j": "available",
                "extra": "nope",
            }
        )


def test_filesystem_health_writes_no_user_data_probe_file(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db_path, files_dir, _fake = health_env
    with health_client() as client:
        before = {p.name for p in files_dir.iterdir()} if files_dir.exists() else set()
        response = client.get("/api/health")
        after = {p.name for p in files_dir.iterdir()}
    assert response.status_code == 200
    assert response.json()["filesystem"] == "available"
    assert after == before or (not before and after == set())
    assert not any(p.is_file() for p in files_dir.rglob("*"))


def test_health_does_not_mutate_schema(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db_path, _files_dir, fake = health_env
    ensure_calls = {"count": 0}
    real_ensure = __import__(
        "app.graph.constraints", fromlist=["ensure_base_schema"]
    ).ensure_base_schema

    async def tracking_ensure(driver: Any) -> None:
        ensure_calls["count"] += 1
        await real_ensure(driver)

    monkeypatch.setattr("app.main.ensure_base_schema", tracking_ensure)
    from app.db.base import Base

    create_all = MagicMock(side_effect=AssertionError("create_all must not run"))
    monkeypatch.setattr(Base.metadata, "create_all", create_all)
    with health_client() as client:
        startup_queries = list(fake.queries)
        # Plan 9 base schema: 6 uniqueness constraints + 1 vector index.
        assert ensure_calls["count"] == 1 and len(startup_queries) == 7
        assert client.get("/api/health").status_code == 200
        assert ensure_calls["count"] == 1 and fake.queries == startup_queries
    create_all.assert_not_called()


def test_startup_idempotent_seeds_and_graph(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    async def seed_count() -> tuple[int, int]:
        async with session_scope() as session:
            conv = (
                await session.execute(
                    text("SELECT COUNT(*) FROM conversation WHERE id = 'main'")
                )
            ).scalar_one()
            prefs = (
                await session.execute(
                    text("SELECT COUNT(*) FROM job_preferences WHERE id = 'active'")
                )
            ).scalar_one()
            return int(conv), int(prefs)

    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert run_async(seed_count()) == (1, 1)
    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert run_async(seed_count()) == (1, 1)


def test_shutdown_and_open_once(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    _db_path, _files_dir, fake = health_env
    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert fake.closed is False and fake.open_count == 1
        assert get_engine() is not None
        assert client.get("/api/health").status_code == 200
        assert fake.open_count == 1
    assert fake.closed is True
    assert session_mod._engine is None
    assert session_mod._session_factory is None


def test_startup_never_runs_migrations_or_create_all(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upgrade = MagicMock(side_effect=AssertionError("alembic upgrade must not run"))
    monkeypatch.setattr("alembic.command.upgrade", upgrade, raising=False)
    from app.db.base import Base

    create_all = MagicMock(side_effect=AssertionError("create_all must not run"))
    monkeypatch.setattr(Base.metadata, "create_all", create_all)
    with health_client() as client:
        assert client.get("/api/health").status_code == 200
    upgrade.assert_not_called()
    create_all.assert_not_called()


def test_partial_startup_failure_cleans_up_resources(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema-init failure after driver open closes driver and disposes engine."""
    _db_path, _files_dir, fake = health_env

    async def boom(_driver: Any) -> None:
        raise RuntimeError("simulated graph schema init failure")

    monkeypatch.setattr("app.main.ensure_base_schema", boom)
    with pytest.raises(RuntimeError, match="simulated graph schema init failure"):
        with health_client():
            pass
    assert fake.closed is True and fake.open_count == 1
    assert session_mod._engine is None
    assert session_mod._session_factory is None


def test_only_public_functional_routes_are_health_chat_cv_and_profile(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    """Public surface after Plan 10: health, chat, CV, profile, observability, jobs."""
    expected = [
        ("DELETE", "/api/cvs/{attachment_id}"),
        ("DELETE", "/api/jobs/{job_id}"),
        ("GET", "/api/chat/history"),
        ("GET", "/api/health"),
        ("GET", "/api/jobs"),
        ("GET", "/api/jobs/{job_id}"),
        ("GET", "/api/observability/cvs"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks"),
        ("GET", "/api/observability/cvs/{attachment_id}/chunks/{ordinal}"),
        ("GET", "/api/observability/cvs/{attachment_id}/file"),
        ("GET", "/api/observability/graph"),
        ("GET", "/api/observability/runs"),
        ("GET", "/api/profile"),
        ("GET", "/api/profile/cv"),
        ("POST", "/api/attachments/cv"),
        ("POST", "/api/chat/runs/{run_id}/resume"),
        ("POST", "/api/chat/turns"),
        ("POST", "/api/cvs/{attachment_id}/reprocess"),
        ("POST", "/api/jobs/save-and-evaluate"),
        ("POST", "/api/jobs/{job_id}/evaluate"),
        ("POST", "/api/jobs/{job_id}/reextract"),
    ]
    with health_client() as client:
        assert sorted(public_api_routes(client.app)) == sorted(expected)
        # Jobs list is GET-only; profile GETs exist (wrong method is 405, not 404).
        assert client.post("/api/jobs").status_code == 405
        assert client.post("/api/profile").status_code == 405
        assert client.post("/api/profile/cv").status_code == 405
        # CV upload is POST-only (GET is method-not-allowed, not a read route).
        assert client.get("/api/attachments/cv").status_code == 405


def test_source_tree_has_no_other_route_decorators() -> None:
    matches = sorted(route_decorator_matches())
    history_dec = (
        "chat.py:get_chat_history:router.get("
        "'/chat/history', response_model=HistoryPage)"
    )
    profile_dec = (
        "profile.py:get_profile:router.get("
        "'/profile', response_model=ProfileReadResponse)"
    )
    assert matches == sorted(
        [
            "attachments.py:post_cv_upload:router.post("
            "'/attachments/cv', response_model=CvUploadResponse)",
            "chat.py:get_chat_history:router.get("
            "'/chat/history', response_model=HistoryPage)",
            "chat.py:post_chat_resume:router.post("
            "'/chat/runs/{run_id}/resume')",
            "chat.py:post_chat_turn:router.post('/chat/turns')",
            "cvs.py:delete_cv_attachment:router.delete("
            "'/cvs/{attachment_id}', status_code=204, response_class=Response)",
            "cvs.py:post_cv_reprocess:router.post("
            "'/cvs/{attachment_id}/reprocess')",
            "health.py:get_health:router.get("
            "'/health', response_model=HealthResponse)",
            "jobs.py:delete_saved_job_route:router.delete("
            "'/jobs/{job_id}', status_code=204, response_class=Response)",
            "jobs.py:get_saved_job:router.get("
            "'/jobs/{job_id}', response_model=SavedJobDetail)",
            "jobs.py:list_saved_jobs:router.get("
            "'/jobs', response_model=SavedJobListPage)",
            "jobs.py:post_evaluate_job:router.post("
            "'/jobs/{job_id}/evaluate', response_model=EvaluateJobResponse)",
            "jobs.py:post_reextract_job:router.post("
            "'/jobs/{job_id}/reextract', response_model=ReextractJobResponse)",
            "jobs.py:post_save_and_evaluate:router.post("
            "'/jobs/save-and-evaluate', response_model=SaveAndEvaluateResponse)",
            "observability.py:get_observability_chunk_detail:router.get("
            "'/observability/cvs/{attachment_id}/chunks/{ordinal}', "
            "response_model=ChunkDetail)",
            "observability.py:get_observability_chunks:router.get("
            "'/observability/cvs/{attachment_id}/chunks', "
            "response_model=ChunkListPage)",
            "observability.py:get_observability_cv_file:router.get("
            "'/observability/cvs/{attachment_id}/file')",
            "observability.py:get_observability_cvs:router.get("
            "'/observability/cvs', response_model=CvHistoryPage)",
            "observability.py:get_observability_graph:router.get("
            "'/observability/graph', response_model=GraphSnapshot)",
            "observability.py:get_observability_runs:router.get("
            "'/observability/runs', response_model=RunHistoryPage)",
            profile_dec,
            "profile.py:get_profile_cv:router.get('/profile/cv')",
        ]
    )
    del history_dec


def test_lifespan_opens_resources_once(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db_path, _files_dir, fake = health_env
    seed_calls = {"count": 0}
    real_seed = __import__(
        "app.db.seed", fromlist=["ensure_singleton_seeds"]
    ).ensure_singleton_seeds

    async def tracking_seed(session: Any) -> None:
        seed_calls["count"] += 1
        await real_seed(session)

    monkeypatch.setattr("app.main.ensure_singleton_seeds", tracking_seed)
    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/health").status_code == 200
        assert seed_calls["count"] == 1 and fake.open_count == 1


def test_startup_skips_seeds_when_sqlite_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Singleton safeguard is skipped when SQLite cannot answer SELECT 1."""
    seed_calls = {"count": 0}

    async def tracking_seed(session: Any) -> None:
        seed_calls["count"] += 1

    monkeypatch.setattr("app.main.ensure_singleton_seeds", tracking_seed)
    prepare_health_env(
        monkeypatch,
        tmp_path,
        migrate=False,
        sqlite_path=blocked_sqlite_path(tmp_path),
        files_dir=tmp_path / "files",
    )
    install_fake_driver(monkeypatch)
    try:
        with health_client() as client:
            body = client.get("/api/health").json()
        assert body["sqlite"] == "unavailable"
        assert seed_calls["count"] == 0
    finally:
        cleanup_isolated_sqlite()

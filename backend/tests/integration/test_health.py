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
    EXPECTED_PUBLIC_API_ROUTES,
    EXPECTED_ROUTE_DECORATORS,
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

_CV_TAILORING_ROUTE_DECORATORS = (
    "cv_tailoring.py:create_ai_version:router.post('/cv-tailoring/sessions/{session_id}/ai-versions')",
    "cv_tailoring.py:create_manual_version:router.post("
    "'/cv-tailoring/sessions/{session_id}/manual-versions', "
    "response_model=TailoringVersionMutationResponse)",
    "cv_tailoring.py:create_session:router.post('/cv-tailoring/sessions')",
    "cv_tailoring.py:delete_session:router.delete("
    "'/cv-tailoring/sessions/{session_id}', "
    "response_model=TailoringDeleteResponse)",
    "cv_tailoring.py:download_pdf:router.get('/cv-tailoring/versions/{version_id}/pdf')",
    "cv_tailoring.py:download_source:router.get('/cv-tailoring/versions/{version_id}/source')",
    "cv_tailoring.py:get_session:router.get("
    "'/cv-tailoring/sessions/{session_id}', "
    "response_model=TailoringSessionDetailResponse)",
    "cv_tailoring.py:list_sessions:router.get("
    "'/cv-tailoring/sessions', response_model=TailoringSessionListResponse)",
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
    assert (
        build_health_response(
            sqlite="available", filesystem="available", neo4j="available"
        ).overall
        == "available"
    )
    assert (
        build_health_response(
            sqlite="available", filesystem="unavailable", neo4j="available"
        ).overall
        == "unavailable"
    )
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


def test_startup_idempotent_workspace_seed_starts_without_product_rows(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    async def seed_state() -> tuple[int, str | None, int, int, int]:
        async with session_scope() as session:
            workspace = (
                await session.execute(
                    text(
                        "SELECT COUNT(*), MAX(active_profile_id) "
                        "FROM workspace_state WHERE id = 'main'"
                    )
                )
            ).one()
            profiles = int(
                (
                    await session.execute(text("SELECT COUNT(*) FROM profiles"))
                ).scalar_one()
            )
            preferences = int(
                (
                    await session.execute(
                        text("SELECT COUNT(*) FROM profile_preferences")
                    )
                ).scalar_one()
            )
            conversations = int(
                (
                    await session.execute(text("SELECT COUNT(*) FROM conversations"))
                ).scalar_one()
            )
            return (
                int(workspace[0]),
                workspace[1],
                profiles,
                preferences,
                conversations,
            )

    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert run_async(seed_state()) == (1, None, 0, 0, 0)
    with health_client() as client:
        assert client.get("/api/health").status_code == 200
        assert run_async(seed_state()) == (1, None, 0, 0, 0)


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
    """Public surface stays identical to the shared accepted route contract."""
    with health_client() as client:
        assert sorted(public_api_routes(client.app)) == sorted(
            EXPECTED_PUBLIC_API_ROUTES
        )
        # Jobs list is GET-only; profile GETs exist (wrong method is 405, not 404).
        assert client.post("/api/jobs").status_code == 405
        assert client.post("/api/profile").status_code == 405
        assert client.post("/api/profile/cv").status_code == 405
        # CV upload is POST-only (GET is method-not-allowed, not a read route).
        assert client.get("/api/attachments/cv").status_code == 405


def test_source_tree_has_no_other_route_decorators() -> None:
    matches = sorted(route_decorator_matches())
    expected = sorted((*EXPECTED_ROUTE_DECORATORS, *_CV_TAILORING_ROUTE_DECORATORS))
    assert matches == expected


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
    """Workspace seed is skipped when SQLite cannot answer SELECT 1."""
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

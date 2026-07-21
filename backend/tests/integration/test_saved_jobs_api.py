"""Integration tests for Plan 10/15 saved-JD list/detail and mutation HTTP contracts.

Covers ``GET /api/jobs`` / detail, ``POST save-and-evaluate``, ``POST evaluate``,
``POST reextract``, and ``DELETE``: source authorization, URL/text ingestion,
reuse, unavailable, strict re-extraction body/response, safe errors, and redaction.
"""

from __future__ import annotations

import ast
import inspect
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.adapters.shopaikey_embeddings import (
    FAILURE_EMBEDDING_TIMEOUT,
    EmbeddingAdapterError,
)
from app.core.ids import new_uuid
from app.db.models.chat import CHAT_MESSAGE_ROLE_USER
from app.db.session import build_async_engine
from app.graph.sync_job import NEO4J_REBUILD_INSTRUCTION, JobSyncError
from app.main import create_app
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as eval_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as prof_repo
from app.repositories import tool_executions as tools_repo
from app.schemas.job_evaluations import (
    EvaluateJobResponse,
    ReextractJobRequest,
    ReextractJobResponse,
    SaveAndEvaluateResponse,
    SavedJobDetail,
    SavedJobListItem,
    SavedJobListPage,
    decode_saved_jobs_cursor,
    encode_saved_jobs_cursor,
)
from app.schemas.profile import parse_candidate_profile
from app.schemas.tools import ToolResult
from app.services import saved_jobs as saved_jobs_service
from app.services.evaluation_context import (
    MATCHING_CONTRACT_VERSION,
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.jd_extraction import (
    FAILURE_INVALID_STRUCTURED_OUTPUT,
    FAILURE_PROVIDER_ERROR,
    ExtractedJobPost,
    JdExtractionError,
)
from app.services.job_reextraction import (
    ERROR_JOB_NOT_SCORABLE,
    ERROR_JOB_REEXTRACT_CONFLICT,
    JobReextractError,
    JobReextractResult,
)
from app.services.saved_jobs import (
    ERROR_JD_SOURCE_NOT_RECOVERABLE,
    ERROR_JOB_NOT_FOUND,
    save_and_evaluate_from_source,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.url_fetch import UrlFetchResult
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.structured_output import FakeJdInvoker
from tests.support.db_migration import (
    cleanup_isolated_sqlite,
    run_async,
    session_factory,
)
from tests.support.graph_rebuild import extraction_payload, profile_payload
from tests.support.health import (
    FAKE_SHOPAIKEY,
    FakeDriver,
    install_fake_driver,
    prepare_health_env,
    public_api_routes,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"

T0 = datetime(2024, 8, 1, 12, 0, 0, tzinfo=UTC)
_CV_SOURCE = "cv-source-saved-jobs-1"

FORBIDDEN_LIST_KEYS: frozenset[str] = frozenset(
    {
        "raw_content",
        "raw_content_hash",
        "extraction",
        "extraction_json",
        "embedding",
        "embeddings",
        "embedding_json",
        "embedding_model",
        "embedding_dimensions",
        "prompt",
        "prompts",
        "storage_path",
        "api_key",
        "SHOPAIKEY_API_KEY",
        "result_json",
        "historical",
        "evaluations",
        "graph",
        "provider",
        "cypher",
        "sql",
    }
)


@pytest.fixture
def jobs_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()


def _client() -> TestClient:
    return TestClient(create_app())


def _assert_no_forbidden_list(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert key not in FORBIDDEN_LIST_KEYS, f"forbidden list key {key!r}"
            _assert_no_forbidden_list(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_forbidden_list(item)
    elif isinstance(payload, str):
        assert FAKE_SHOPAIKEY not in payload


def _match_payload(
    job_id: str,
    *,
    summary: str = "ok",
    final_score: float = 0.81,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Berlin",
        "work_mode": "hybrid",
        "source_url": None,
        "final_score": final_score,
        "quality_multiplier": 1.0,
        "components": {
            "semantic_similarity": final_score,
            "skill_score": None,
            "seniority_score": None,
            "experience_score": None,
            "location_score": None,
            "work_mode_score": None,
        },
        "effective_weights": {"semantic_similarity": 1.0},
        "matched_required_skills": [],
        "matched_preferred_skills": [],
        "related_skills": [],
        "missing_required_skills": [],
        "summary": summary,
    }


async def _seed_profile(
    session: AsyncSession,
    *,
    source_hash: str = _CV_SOURCE,
) -> str:
    profile = parse_candidate_profile(profile_payload(include_excluded=False))
    prefs = {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Berlin"],
        "acceptable_work_modes": ["hybrid"],
        "target_seniority": ["mid"],
    }
    att = await att_repo.create_staged(
        session,
        file_hash="saved-jobs-cv-hash",
        original_name="cv.pdf",
        size_bytes=100,
        storage_path="saved/cv.pdf",
        page_count=1,
    )
    await att_repo.mark_active(session, att.id)
    await prof_repo.upsert_active_profile(
        session,
        active_attachment_id=att.id,
        profile_json=profile.model_dump(mode="json"),
    )
    await cv_doc_repo.upsert_document(
        session,
        attachment_id=att.id,
        document_json={"sections": []},
        profile_json=profile.model_dump(mode="json"),
        outline_json={"sections": []},
        extraction_version="cv-document-v1",
        source_hash=source_hash,
    )
    await prof_repo.upsert_job_preferences(session, preferences_json=prefs)
    return att.id


async def _create_processed_job(
    session: AsyncSession,
    *,
    raw_content: str,
    raw_hash: str,
    title: str = "Backend Engineer",
    company: str = "Acme",
    created_at: datetime | None = None,
) -> str:
    extraction = extraction_payload()
    extraction["title"] = title
    extraction["company"] = company
    row = await jobs_repo.create_text_job(
        session,
        raw_content=raw_content,
        raw_content_hash=raw_hash,
    )
    await jobs_repo.mark_processing(session, row.id)
    emb = [0.01 + (i * 1e-6) for i in range(1536)]
    processed = await jobs_repo.mark_processed(
        session,
        row.id,
        extraction_json=extraction,
        jd_quality="full",
        embedding_json=emb,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
    )
    if created_at is not None:
        # ORM attribute assignment matches other cursor-pagination tests.
        processed.created_at = created_at
        processed.updated_at = created_at
        await session.flush()
    return processed.id


async def _insert_evaluation(
    session: AsyncSession,
    *,
    job_id: str,
    attachment_id: str,
    context_hash: str,
    job_revision: datetime,
    profile_revision: datetime,
    preferences_revision: datetime,
    cv_source_hash: str = _CV_SOURCE,
    final_score: float = 0.81,
    summary: str = "eval",
) -> None:
    await eval_repo.insert_evaluation(
        session,
        job_id=job_id,
        active_attachment_id=attachment_id,
        evaluation_context_hash=context_hash,
        job_revision=job_revision,
        profile_revision=profile_revision,
        preferences_revision=preferences_revision,
        cv_source_hash=cv_source_hash,
        matching_contract_version=MATCHING_CONTRACT_VERSION,
        result=_match_payload(
            job_id, summary=summary, final_score=final_score
        ),
    )


async def _current_hash_for_job(
    session: AsyncSession, job_id: str
) -> str:
    job = await jobs_repo.get_by_id(session, job_id)
    assert job is not None
    profile = await prof_repo.get_active_profile(session)
    prefs = await prof_repo.get_job_preferences(session)
    assert profile is not None and prefs is not None
    cv = await cv_doc_repo.get_document(session, profile.active_attachment_id)
    assert cv is not None
    facts = EvaluationContextFacts(
        job_id=job.id,
        job_revision=job.updated_at
        if job.updated_at.tzinfo
        else job.updated_at.replace(tzinfo=UTC),
        active_attachment_id=profile.active_attachment_id,
        cv_source_hash=cv.source_hash,
        profile_revision=profile.updated_at
        if profile.updated_at.tzinfo
        else profile.updated_at.replace(tzinfo=UTC),
        preferences_revision=prefs.updated_at
        if prefs.updated_at.tzinfo
        else prefs.updated_at.replace(tzinfo=UTC),
        matching_contract_version=MATCHING_CONTRACT_VERSION,
    )
    return evaluation_context_hash(facts)


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


# Source text that grounds ``_full_extracted`` after the Plan 15 quality guard.
_FULL_EXTRACTED_SOURCE: str = (
    "Title: Backend Engineer\n"
    "Company: Acme\n"
    "Location: Berlin\n"
    "Build and maintain APIs.\n"
    "Responsibilities:\n"
    "- Design REST services\n"
    "- Own deployments\n"
    "Required: 3+ years Python\n"
    "Work mode: hybrid\n"
)


def _full_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build and maintain APIs.",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python"],
            }
        ],
        "preferred_skills": [],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


# Grounded retained source + provider payload for Plan 15 re-extraction API tests.
_REEXTRACT_GROUNDED_RAW: str = (
    "Title: Backend Engineer\n"
    "Company: Acme\n"
    "Location: Berlin\n"
    "Responsibilities:\n"
    "- Design REST services\n"
    "- Own deployments\n"
    "Required: 3+ years Python.\n"
    "Preferred: FastAPI\n"
)


def _reextract_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Design REST services",
        "responsibilities": ["Design REST services", "Own deployments"],
        "required_skills": [
            {
                "name": "Python",
                "confidence": 0.9,
                "evidence": ["Required: 3+ years Python."],
            }
        ],
        "preferred_skills": [
            {
                "name": "FastAPI",
                "confidence": 0.6,
                "evidence": ["Preferred: FastAPI"],
            }
        ],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.91,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


def _unscorable_extracted(**overrides: Any) -> ExtractedJobPost:
    base: dict[str, Any] = {
        "title": None,
        "company": None,
        "summary": "Contact us for details.",
        "responsibilities": [],
        "required_skills": [],
        "preferred_skills": [],
        "seniority": "unknown",
        "min_experience_years": None,
        "max_experience_years": None,
        "location": None,
        "work_mode": "unknown",
        "extraction_confidence": 0.1,
    }
    base.update(overrides)
    return ExtractedJobPost.model_validate(base)


def _patch_reextract_adapters(
    monkeypatch: pytest.MonkeyPatch,
    invoker: FakeJdInvoker,
    emb: FakeEmbeddingClient,
    *,
    job_sync_fn: Any | None = None,
) -> None:
    """Patch route adapters and optionally inject a graph sync seam.

    Always wraps the real coordinator (not a prior wrap) so nested patches cannot
    leave a success-only ``job_sync_fn`` sticky across cases.
    """
    from app.services import job_reextraction as reextract_mod

    monkeypatch.setattr(
        "app.api.jobs.ShopAIKeyStructuredJdInvoker",
        lambda: invoker,
    )
    monkeypatch.setattr(
        "app.api.jobs.ShopAIKeyEmbeddingAdapter",
        lambda: emb,
    )
    if job_sync_fn is None:
        return
    real = reextract_mod.reextract_job

    async def _wrapped(job_id: str, **kwargs: Any) -> Any:
        kwargs["job_sync_fn"] = job_sync_fn
        return await real(job_id, **kwargs)

    monkeypatch.setattr(saved_jobs_service, "reextract_job", _wrapped)


async def _seed_zero_result_source(
    session: AsyncSession,
    *,
    content: str,
    match_ok: bool = True,
    match_count: int = 0,
    run_completed: bool = True,
    tool_name: str = "match_jobs",
    role: str = CHAT_MESSAGE_ROLE_USER,
) -> str:
    """Insert user message + run + match_jobs tool result; return message id."""
    user = await messages_repo.insert_message(
        session, role=role, content=content
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    if match_ok:
        tool_result = ToolResult(
            ok=True,
            code=None,
            summary=f"Matched {match_count} job(s)",
            data={
                "results": []
                if match_count == 0
                else [
                    {
                        "job_id": new_uuid(),
                        "title": "X",
                        "company": "Y",
                        "location": None,
                        "work_mode": "remote",
                        "source_url": None,
                        "final_score": 0.5,
                        "quality_multiplier": 1.0,
                        "components": {
                            "semantic_similarity": 0.5,
                            "skill_score": None,
                            "seniority_score": None,
                            "experience_score": None,
                            "location_score": None,
                            "work_mode_score": None,
                        },
                        "effective_weights": {"semantic_similarity": 1.0},
                        "matched_required_skills": [],
                        "matched_preferred_skills": [],
                        "related_skills": [],
                        "missing_required_skills": [],
                        "summary": "one",
                    }
                ],
                "count": match_count,
                "limit": 10,
            },
        )
    else:
        tool_result = ToolResult(
            ok=False,
            code="NEO4J_UNAVAILABLE",
            summary="Matching failed",
            data={"results": [], "count": 0, "limit": 10},
        )
    row, _ = await tools_repo.get_or_create_pending(
        session,
        run_id=run.id,
        tool_call_id=f"tc-{user.id[:8]}",
        tool_name=tool_name,
        arguments_summary_json={"limit": 10},
    )
    await tools_repo.mark_running(session, row.id)
    if match_ok:
        await tools_repo.complete_execution(
            session, row.id, result=tool_result, duration_ms=5
        )
    else:
        await tools_repo.fail_execution(
            session, row.id, result=tool_result, duration_ms=5
        )
    if run_completed:
        await runs_repo.complete_run(session, run.id)
    return user.id


def test_routes_registered(jobs_env: tuple[Path, Path, FakeDriver]) -> None:
    app = create_app()
    routes = set(public_api_routes(app))
    assert ("GET", "/api/jobs") in routes
    assert ("GET", "/api/jobs/{job_id}") in routes
    assert ("POST", "/api/jobs/save-and-evaluate") in routes
    assert ("POST", "/api/jobs/{job_id}/evaluate") in routes
    assert ("POST", "/api/jobs/{job_id}/reextract") in routes
    assert ("DELETE", "/api/jobs/{job_id}") in routes


def test_list_limit_bounds_and_malformed_cursor(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    with _client() as client:
        assert client.get("/api/jobs", params={"limit": 0}).status_code == 422
        assert client.get("/api/jobs", params={"limit": 51}).status_code == 422
        bad = client.get("/api/jobs", params={"before": "not-a-cursor!!!"})
        assert bad.status_code == 422
        empty = client.get("/api/jobs", params={"before": ""})
        assert empty.status_code == 422
        # Valid empty page when no jobs.
        ok = client.get("/api/jobs", params={"limit": 10})
        assert ok.status_code == 200
        page = SavedJobListPage.model_validate(ok.json())
        assert page.items == []
        assert page.next_cursor is None


def test_list_stable_newest_first_cursor_no_dup_skip(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env

    async def _seed() -> list[str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        ids: list[str] = []
        try:
            async with factory() as session:
                await _seed_profile(session)
                for i in range(5):
                    jid = await _create_processed_job(
                        session,
                        raw_content=f"JD body {i}",
                        raw_hash=f"hash-{i}",
                        title=f"Role {i}",
                        company=f"Co {i}",
                        created_at=T0 + timedelta(minutes=i),
                    )
                    ids.append(jid)
                await session.commit()
        finally:
            await engine.dispose()
        # Newest-first expected order: Role 4 .. Role 0
        return list(reversed(ids))

    expected_newest_first = run_async(_seed())

    with _client() as client:
        page1 = client.get("/api/jobs", params={"limit": 2})
        assert page1.status_code == 200
        p1 = SavedJobListPage.model_validate(page1.json())
        assert [item.id for item in p1.items] == expected_newest_first[:2]
        assert p1.next_cursor is not None
        # Cursor encodes oldest of page (last item).
        cur_ts, cur_id = decode_saved_jobs_cursor(p1.next_cursor)
        assert cur_id == p1.items[-1].id
        assert cur_ts.tzinfo is not None

        page2 = client.get(
            "/api/jobs", params={"limit": 2, "before": p1.next_cursor}
        )
        p2 = SavedJobListPage.model_validate(page2.json())
        assert [item.id for item in p2.items] == expected_newest_first[2:4]
        assert p2.next_cursor is not None

        page3 = client.get(
            "/api/jobs", params={"limit": 2, "before": p2.next_cursor}
        )
        p3 = SavedJobListPage.model_validate(page3.json())
        assert [item.id for item in p3.items] == expected_newest_first[4:5]
        assert p3.next_cursor is None

        seen = [item.id for item in p1.items + p2.items + p3.items]
        assert seen == expected_newest_first
        assert len(seen) == len(set(seen))


def test_list_currentness_and_latest_score(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env

    async def _seed() -> dict[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_profile(session)
                none_id = await _create_processed_job(
                    session,
                    raw_content="none job",
                    raw_hash="hash-none",
                    title="None Job",
                    created_at=T0,
                )
                stale_id = await _create_processed_job(
                    session,
                    raw_content="stale job",
                    raw_hash="hash-stale",
                    title="Stale Job",
                    created_at=T0 + timedelta(minutes=1),
                )
                current_id = await _create_processed_job(
                    session,
                    raw_content="current job",
                    raw_hash="hash-current",
                    title="Current Job",
                    created_at=T0 + timedelta(minutes=2),
                )
                await session.commit()

            async with factory() as session:
                job_stale = await jobs_repo.get_by_id(session, stale_id)
                job_cur = await jobs_repo.get_by_id(session, current_id)
                profile = await prof_repo.get_active_profile(session)
                prefs = await prof_repo.get_job_preferences(session)
                assert job_stale and job_cur and profile and prefs
                # Stale: hash under different CV source.
                stale_facts = EvaluationContextFacts(
                    job_id=stale_id,
                    job_revision=job_stale.updated_at.replace(tzinfo=UTC)
                    if job_stale.updated_at.tzinfo is None
                    else job_stale.updated_at,
                    active_attachment_id=att_id,
                    cv_source_hash="old-cv-hash",
                    profile_revision=profile.updated_at.replace(tzinfo=UTC)
                    if profile.updated_at.tzinfo is None
                    else profile.updated_at,
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC)
                    if prefs.updated_at.tzinfo is None
                    else prefs.updated_at,
                    matching_contract_version=MATCHING_CONTRACT_VERSION,
                )
                await _insert_evaluation(
                    session,
                    job_id=stale_id,
                    attachment_id=att_id,
                    context_hash=evaluation_context_hash(stale_facts),
                    job_revision=stale_facts.job_revision,
                    profile_revision=stale_facts.profile_revision,
                    preferences_revision=stale_facts.preferences_revision,
                    cv_source_hash="old-cv-hash",
                    final_score=0.42,
                    summary="stale-score",
                )
                current_hash = await _current_hash_for_job(session, current_id)
                cur_rev = (
                    job_cur.updated_at.replace(tzinfo=UTC)
                    if job_cur.updated_at.tzinfo is None
                    else job_cur.updated_at
                )
                await _insert_evaluation(
                    session,
                    job_id=current_id,
                    attachment_id=att_id,
                    context_hash=current_hash,
                    job_revision=cur_rev,
                    profile_revision=profile.updated_at.replace(tzinfo=UTC)
                    if profile.updated_at.tzinfo is None
                    else profile.updated_at,
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC)
                    if prefs.updated_at.tzinfo is None
                    else prefs.updated_at,
                    final_score=0.91,
                    summary="current-score",
                )
                await session.commit()
        finally:
            await engine.dispose()
        return {
            "none": none_id,
            "stale": stale_id,
            "current": current_id,
        }

    ids = run_async(_seed())

    with _client() as client:
        resp = client.get("/api/jobs", params={"limit": 50})
        assert resp.status_code == 200
        page = SavedJobListPage.model_validate(resp.json())
        by_id = {item.id: item for item in page.items}
        assert by_id[ids["none"]].evaluation_state == "none"
        assert by_id[ids["none"]].latest_score is None
        assert by_id[ids["stale"]].evaluation_state == "stale"
        assert by_id[ids["stale"]].latest_score == pytest.approx(0.42)
        assert by_id[ids["current"]].evaluation_state == "current"
        assert by_id[ids["current"]].latest_score == pytest.approx(0.91)
        _assert_no_forbidden_list(resp.json())


def test_detail_extraction_evaluation_and_not_found(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_profile(session)
                job_id = await _create_processed_job(
                    session,
                    raw_content="Selected JD body text",
                    raw_hash="hash-detail",
                    title="Detail Role",
                    company="Detail Co",
                )
                await session.commit()
            async with factory() as session:
                current_hash = await _current_hash_for_job(session, job_id)
                job = await jobs_repo.get_by_id(session, job_id)
                profile = await prof_repo.get_active_profile(session)
                prefs = await prof_repo.get_job_preferences(session)
                assert job and profile and prefs
                await _insert_evaluation(
                    session,
                    job_id=job_id,
                    attachment_id=att_id,
                    context_hash=current_hash,
                    job_revision=job.updated_at.replace(tzinfo=UTC)
                    if job.updated_at.tzinfo is None
                    else job.updated_at,
                    profile_revision=profile.updated_at.replace(tzinfo=UTC)
                    if profile.updated_at.tzinfo is None
                    else profile.updated_at,
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC)
                    if prefs.updated_at.tzinfo is None
                    else prefs.updated_at,
                    final_score=0.77,
                    summary="detail-eval",
                )
                await session.commit()
                return job_id
        finally:
            await engine.dispose()

    job_id = run_async(_seed())

    with _client() as client:
        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        detail = SavedJobDetail.model_validate(resp.json())
        assert detail.compact.id == job_id
        assert detail.compact.title == "Detail Role"
        assert detail.compact.company == "Detail Co"
        assert detail.compact.evaluation_state == "current"
        assert detail.compact.latest_score == pytest.approx(0.77)
        assert detail.raw_content == "Selected JD body text"
        assert detail.extraction is not None
        assert detail.extraction.title == "Detail Role"
        assert detail.latest_evaluation is not None
        assert detail.latest_evaluation.evaluation_state == "current"
        assert detail.latest_evaluation.result.summary == "detail-eval"
        assert detail.latest_evaluation.result.final_score == pytest.approx(0.77)
        # Opaque context hash present; no revision client authority fields.
        assert detail.latest_evaluation.evaluation_context_hash
        body = resp.json()
        assert "embedding_json" not in body
        assert "raw_content_hash" not in body
        assert "storage_path" not in body
        assert FAKE_SHOPAIKEY not in resp.text

        missing = client.get(f"/api/jobs/{new_uuid()}")
        assert missing.status_code == 404
        err = missing.json()["detail"]
        assert err["code"] == "JOB_NOT_FOUND"
        assert "sql" not in err["summary"].lower()
        assert "cypher" not in err["summary"].lower()


def test_list_redaction_no_raw_or_embeddings(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env

    async def _seed() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                await _create_processed_job(
                    session,
                    raw_content="SECRET_RAW_JD_BODY_SHOULD_NOT_LEAK",
                    raw_hash="hash-redact",
                    title="Redact Me",
                )
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_seed())

    with _client() as client:
        resp = client.get("/api/jobs", params={"limit": 10})
        assert resp.status_code == 200
        blob = resp.text
        assert "SECRET_RAW_JD_BODY_SHOULD_NOT_LEAK" not in blob
        assert "hash-redact" not in blob
        _assert_no_forbidden_list(resp.json())
        page = SavedJobListPage.model_validate(resp.json())
        assert len(page.items) == 1
        item = page.items[0]
        dumped = item.model_dump(mode="json")
        assert set(dumped.keys()) == {
            "id",
            "title",
            "company",
            "processing_status",
            "jd_quality",
            "source_type",
            "source_url",
            "created_at",
            "updated_at",
            "evaluation_state",
            "latest_score",
        }


def test_gets_do_not_mutate_or_call_external_work(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, fake = jobs_env

    async def _seed_and_counts() -> tuple[str, dict[str, int]]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_profile(session)
                job_id = await _create_processed_job(
                    session,
                    raw_content="immutable job",
                    raw_hash="hash-immutable",
                )
                await session.commit()
            async with factory() as session:
                current_hash = await _current_hash_for_job(session, job_id)
                job = await jobs_repo.get_by_id(session, job_id)
                profile = await prof_repo.get_active_profile(session)
                prefs = await prof_repo.get_job_preferences(session)
                assert job and profile and prefs
                await _insert_evaluation(
                    session,
                    job_id=job_id,
                    attachment_id=att_id,
                    context_hash=current_hash,
                    job_revision=job.updated_at.replace(tzinfo=UTC)
                    if job.updated_at.tzinfo is None
                    else job.updated_at,
                    profile_revision=profile.updated_at.replace(tzinfo=UTC)
                    if profile.updated_at.tzinfo is None
                    else profile.updated_at,
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC)
                    if prefs.updated_at.tzinfo is None
                    else prefs.updated_at,
                )
                await session.commit()

            async with factory() as session:
                counts = {
                    "jobs": int(
                        (
                            await session.execute(
                                text("SELECT COUNT(*) FROM job_posts")
                            )
                        ).scalar_one()
                    ),
                    "evals": int(
                        (
                            await session.execute(
                                text("SELECT COUNT(*) FROM job_evaluations")
                            )
                        ).scalar_one()
                    ),
                    "updated": (
                        await session.execute(
                            text(
                                "SELECT updated_at FROM job_posts WHERE id = :id"
                            ),
                            {"id": job_id},
                        )
                    ).scalar_one(),
                    "eval_updated": (
                        await session.execute(
                            text(
                                "SELECT updated_at FROM job_evaluations "
                                "WHERE job_id = :id"
                            ),
                            {"id": job_id},
                        )
                    ).scalar_one(),
                }
            return job_id, counts
        finally:
            await engine.dispose()

    job_id, before = run_async(_seed_and_counts())

    with _client() as client:
        # Lifespan may init graph schema; snapshot after startup, before reads.
        neo4j_queries_before = len(fake.queries)
        assert client.get("/api/jobs").status_code == 200
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert len(fake.queries) == neo4j_queries_before

    async def _after() -> dict[str, Any]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                return {
                    "jobs": int(
                        (
                            await session.execute(
                                text("SELECT COUNT(*) FROM job_posts")
                            )
                        ).scalar_one()
                    ),
                    "evals": int(
                        (
                            await session.execute(
                                text("SELECT COUNT(*) FROM job_evaluations")
                            )
                        ).scalar_one()
                    ),
                    "updated": (
                        await session.execute(
                            text(
                                "SELECT updated_at FROM job_posts WHERE id = :id"
                            ),
                            {"id": job_id},
                        )
                    ).scalar_one(),
                    "eval_updated": (
                        await session.execute(
                            text(
                                "SELECT updated_at FROM job_evaluations "
                                "WHERE job_id = :id"
                            ),
                            {"id": job_id},
                        )
                    ).scalar_one(),
                }
        finally:
            await engine.dispose()

    after = run_async(_after())
    assert after["jobs"] == before["jobs"]
    assert after["evals"] == before["evals"]
    assert after["updated"] == before["updated"]
    assert after["eval_updated"] == before["eval_updated"]

    # Static: GET assembly does not inline scoring formulas or insert rows.
    source = inspect.getsource(saved_jobs_service)
    assert "project_single_job_match" not in source
    assert "check_graph_revision_consistency" not in source
    assert "insert_evaluation" not in source
    # Mutations delegate to evaluate_job / ingest_* owners (allowed).
    assert "evaluate_job" in source
    assert "ingest_raw_text" in source


def test_cursor_codec_reuses_chat_owner() -> None:
    """Opaque cursor encode/decode aliases the chat history codec."""
    from app.schemas import chat as chat_schemas
    from app.schemas import job_evaluations as je_schemas

    assert je_schemas.encode_saved_jobs_cursor is chat_schemas.encode_history_cursor
    assert je_schemas.decode_saved_jobs_cursor is chat_schemas.decode_history_cursor
    ts = T0
    mid = new_uuid()
    encoded = encode_saved_jobs_cursor(ts, mid)
    assert decode_saved_jobs_cursor(encoded) == (ts, mid)


def test_api_module_is_thin_transport() -> None:
    from app.api import jobs as jobs_api

    source = inspect.getsource(jobs_api)
    tree = ast.parse(source)
    # No direct SQLAlchemy model queries in the route module.
    assert "select(" not in source
    assert "JobPost" not in source
    assert "insert_evaluation" not in source
    # Routes delegate only through saved_jobs service surface.
    assert "from app.services.job_evaluation" not in source
    assert "from app.services.jd_ingestion" not in source
    assert "from app.services.job_deletion" not in source
    assert "ingest_raw_text" not in source
    # Module stays focused transport (under 300 lines).
    assert len(source.splitlines()) < 250
    names = {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {
        "list_saved_jobs",
        "get_saved_job",
        "post_save_and_evaluate",
        "post_evaluate_job",
        "post_reextract_job",
        "delete_saved_job_route",
    } <= names


def test_list_without_profile_marks_existing_eval_stale(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    """Without active profile context, stored evals cannot be current."""
    db_path, _, _ = jobs_env

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                # Profile only long enough to create attachment FK for evaluation.
                att_id = await _seed_profile(session)
                job_id = await _create_processed_job(
                    session,
                    raw_content="no profile later",
                    raw_hash="hash-no-profile",
                )
                await _insert_evaluation(
                    session,
                    job_id=job_id,
                    attachment_id=att_id,
                    context_hash="orphan-context-hash",
                    job_revision=T0,
                    profile_revision=T0,
                    preferences_revision=T0,
                    final_score=0.55,
                )
                # Remove active profile so reads have no current context.
                await session.execute(text("DELETE FROM candidate_profile"))
                await session.execute(text("DELETE FROM job_preferences"))
                await session.commit()
                return job_id
        finally:
            await engine.dispose()

    job_id = run_async(_seed())
    with _client() as client:
        page = SavedJobListPage.model_validate(
            client.get("/api/jobs").json()
        )
        item = next(i for i in page.items if i.id == job_id)
        assert item.evaluation_state == "stale"
        assert item.latest_score == pytest.approx(0.55)


# ---------------------------------------------------------------------------
# Mutations: save-and-evaluate / evaluate / delete
# ---------------------------------------------------------------------------


def test_save_and_evaluate_rejects_invalid_source_relationships(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env
    invoker = FakeJdInvoker([_full_extracted()])
    emb = FakeEmbeddingClient()
    engine = build_async_engine(db_path)
    factory = session_factory(engine)

    async def _seed() -> dict[str, str]:
        async with factory() as session:
            await _seed_profile(session)
            ok_id = await _seed_zero_result_source(
                session, content=_FULL_EXTRACTED_SOURCE
            )
            missing_run = await messages_repo.insert_message(
                session, role=CHAT_MESSAGE_ROLE_USER, content="no run"
            )
            nonzero = await _seed_zero_result_source(
                session,
                content="has matches",
                match_count=1,
            )
            failed_tool = await _seed_zero_result_source(
                session,
                content="failed match",
                match_ok=False,
            )
            incomplete = await _seed_zero_result_source(
                session,
                content="running run",
                run_completed=False,
            )
            wrong_tool = await _seed_zero_result_source(
                session,
                content="save_job only",
                tool_name="save_job",
            )
            await session.commit()
            return {
                "ok": ok_id,
                "missing_run": missing_run.id,
                "nonzero": nonzero,
                "failed_tool": failed_tool,
                "incomplete": incomplete,
                "wrong_tool": wrong_tool,
            }

    ids = run_async(_seed())

    async def _try(mid: str) -> str | None:
        try:
            await save_and_evaluate_from_source(
                mid,
                session_factory=factory,
                graph_driver=None,
                invoker=invoker,
                embedding_client=emb,
                normalizer=_normalizer(),
            )
            return None
        except saved_jobs_service.SavedJobsServiceError as exc:
            return exc.code

    assert invoker.call_count == 0
    for key in (
        "missing_run",
        "nonzero",
        "failed_tool",
        "incomplete",
        "wrong_tool",
    ):
        assert run_async(_try(ids[key])) == ERROR_JD_SOURCE_NOT_RECOVERABLE
    assert run_async(_try(new_uuid())) == ERROR_JD_SOURCE_NOT_RECOVERABLE
    # Invalid relationships never call ingestion.
    assert invoker.call_count == 0

    async def _count() -> int:
        async with factory() as session:
            return int(
                (
                    await session.execute(text("SELECT COUNT(*) FROM job_posts"))
                ).scalar_one()
            )

    assert run_async(_count()) == 0
    # Valid zero-result authorizes and reaches ingestion.
    ok_code = run_async(_try(ids["ok"]))
    assert ok_code is None
    assert invoker.call_count >= 1
    assert run_async(_count()) == 1
    run_async(engine.dispose())


def test_save_and_evaluate_text_created_and_exact_hash_existing(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env
    jd_text = _FULL_EXTRACTED_SOURCE
    invoker = FakeJdInvoker([_full_extracted(), _full_extracted()])
    emb = FakeEmbeddingClient()
    engine = build_async_engine(db_path)
    factory = session_factory(engine)

    async def _seed() -> str:
        async with factory() as session:
            await _seed_profile(session)
            mid = await _seed_zero_result_source(session, content=jd_text)
            await session.commit()
            return mid

    mid = run_async(_seed())

    async def _run() -> SaveAndEvaluateResponse:
        return await save_and_evaluate_from_source(
            mid,
            session_factory=factory,
            graph_driver=None,
            invoker=invoker,
            embedding_client=emb,
            normalizer=_normalizer(),
        )

    first = run_async(_run())
    assert first.ingest_outcome == "created"
    assert first.job.id
    # Without graph, evaluation is unavailable (no false success).
    assert first.evaluation_outcome == "unavailable"
    assert first.evaluation is None
    assert first.code == "NEO4J_UNAVAILABLE"
    assert invoker.call_count == 1

    second = run_async(_run())
    assert second.ingest_outcome == "existing"
    assert second.job.id == first.job.id
    # Exact-hash reuse: no second extraction call.
    assert invoker.call_count == 1
    assert second.evaluation_outcome == "unavailable"

    async def _job_count() -> int:
        async with factory() as session:
            return int(
                (
                    await session.execute(text("SELECT COUNT(*) FROM job_posts"))
                ).scalar_one()
            )

    assert run_async(_job_count()) == 1
    run_async(engine.dispose())


def test_save_and_evaluate_url_vs_text_and_no_latest_message_inference(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env
    url = "https://example.com/jobs/backend-engineer"
    invoker = FakeJdInvoker([_full_extracted(), _full_extracted()])
    emb = FakeEmbeddingClient()
    fetched: list[str] = []

    async def _fetcher(u: str) -> UrlFetchResult:
        fetched.append(u)
        return UrlFetchResult(
            text=_FULL_EXTRACTED_SOURCE,
            failure_code=None,
        )

    engine = build_async_engine(db_path)
    factory = session_factory(engine)

    async def _seed() -> tuple[str, str]:
        async with factory() as session:
            await _seed_profile(session)
            url_mid = await _seed_zero_result_source(session, content=url)
            # Later message must not be used when source is the earlier id.
            await messages_repo.insert_message(
                session,
                role=CHAT_MESSAGE_ROLE_USER,
                content="LATEST COMPOSER TEXT MUST NOT BE USED AS JD",
            )
            mixed = await _seed_zero_result_source(
                session,
                content=(
                    "See https://example.com/x and also paste this JD text.\n"
                    + _FULL_EXTRACTED_SOURCE
                ),
            )
            await session.commit()
            return url_mid, mixed

    url_mid, mixed_mid = run_async(_seed())

    async def _run(mid: str, fetcher: Any = None) -> SaveAndEvaluateResponse:
        return await save_and_evaluate_from_source(
            mid,
            session_factory=factory,
            graph_driver=None,
            invoker=invoker,
            embedding_client=emb,
            normalizer=_normalizer(),
            url_fetcher=fetcher,
        )

    url_resp = run_async(_run(url_mid, _fetcher))
    assert url_resp.ingest_outcome == "created"
    assert fetched == [url]
    assert url_resp.job.source_type == "url"
    assert url_resp.job.source_url == url

    # Mixed content is text (not sole URL); fetcher must not be used.
    text_resp = run_async(_run(mixed_mid, _fetcher))
    assert text_resp.job.source_type == "text"
    assert len(fetched) == 1  # no additional fetch
    run_async(engine.dispose())


def test_save_and_evaluate_unscorable_is_unavailable_not_success(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    db_path, _, _ = jobs_env
    invoker = FakeJdInvoker([JdExtractionError("EXTRACT_FAILED", "boom")])
    emb = FakeEmbeddingClient()
    engine = build_async_engine(db_path)
    factory = session_factory(engine)
    jd = "unscorable jd content for unavailable evaluation outcome"

    async def _seed() -> str:
        async with factory() as session:
            await _seed_profile(session)
            mid = await _seed_zero_result_source(session, content=jd)
            await session.commit()
            return mid

    mid = run_async(_seed())

    async def _run() -> SaveAndEvaluateResponse:
        return await save_and_evaluate_from_source(
            mid,
            session_factory=factory,
            graph_driver=None,
            invoker=invoker,
            embedding_client=emb,
            normalizer=_normalizer(),
        )

    resp = run_async(_run())
    assert resp.ingest_outcome == "created"
    assert resp.evaluation_outcome == "unavailable"
    assert resp.evaluation is None
    assert resp.code is not None
    assert resp.code not in {"created", "reused"}
    assert resp.job.processing_status == "failed"
    run_async(engine.dispose())


def test_save_and_evaluate_http_source_binding_and_redaction(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _, _ = jobs_env
    secret_token = "SECRET_JD_BODY_DO_NOT_LEAK_IN_ERRORS"
    secret_jd = f"{_FULL_EXTRACTED_SOURCE}\n{secret_token}"

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                mid = await _seed_zero_result_source(
                    session, content=secret_jd
                )
                await session.commit()
                return mid
        finally:
            await engine.dispose()

    mid = run_async(_seed())

    # Force service to raise with safe code (invalid alternate id path).
    with _client() as client:
        bad = client.post(
            "/api/jobs/save-and-evaluate",
            json={"source_message_id": new_uuid()},
        )
        assert bad.status_code == 400
        detail = bad.json()["detail"]
        assert detail["code"] == ERROR_JD_SOURCE_NOT_RECOVERABLE
        blob = str(bad.json())
        assert secret_token not in blob
        assert secret_jd not in blob
        assert FAKE_SHOPAIKEY not in blob
        assert "SELECT " not in blob
        assert "MATCH (" not in blob

        # Body must not accept replacement text.
        extra = client.post(
            "/api/jobs/save-and-evaluate",
            json={
                "source_message_id": mid,
                "text": "replacement must be rejected",
            },
        )
        assert extra.status_code == 422

        # Valid source: patch adapters so production route does not call provider.
        monkeypatch.setattr(
            "app.api.jobs.ShopAIKeyStructuredJdInvoker",
            lambda: FakeJdInvoker([_full_extracted()]),
        )
        monkeypatch.setattr(
            "app.api.jobs.ShopAIKeyEmbeddingAdapter",
            lambda: FakeEmbeddingClient(),
        )
        ok = client.post(
            "/api/jobs/save-and-evaluate",
            json={"source_message_id": mid},
        )
        assert ok.status_code == 200
        body = SaveAndEvaluateResponse.model_validate(ok.json())
        assert body.ingest_outcome in {"created", "existing", "retried"}
        assert body.evaluation_outcome in {"created", "reused", "unavailable"}
        blob_ok = str(ok.json())
        assert secret_token not in blob_ok
        assert secret_jd not in blob_ok
        assert "raw_content" not in ok.json().get("job", {})


def test_evaluate_reuses_current_without_provider_calls(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _, _ = jobs_env

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_profile(session)
                job_id = await _create_processed_job(
                    session,
                    raw_content="eval reuse job",
                    raw_hash="hash-eval-reuse",
                )
                await session.commit()
            async with factory() as session:
                job = await jobs_repo.get_by_id(session, job_id)
                profile = await prof_repo.get_active_profile(session)
                prefs = await prof_repo.get_job_preferences(session)
                assert job and profile and prefs
                ctx = await _current_hash_for_job(session, job_id)
                await _insert_evaluation(
                    session,
                    job_id=job_id,
                    attachment_id=att_id,
                    context_hash=ctx,
                    job_revision=job.updated_at
                    if job.updated_at.tzinfo
                    else job.updated_at.replace(tzinfo=UTC),
                    profile_revision=profile.updated_at
                    if profile.updated_at.tzinfo
                    else profile.updated_at.replace(tzinfo=UTC),
                    preferences_revision=prefs.updated_at
                    if prefs.updated_at.tzinfo
                    else prefs.updated_at.replace(tzinfo=UTC),
                    final_score=0.77,
                    summary="current-reuse",
                )
                await session.commit()
                return job_id
        finally:
            await engine.dispose()

    job_id = run_async(_seed())
    emb = FakeEmbeddingClient()
    monkeypatch.setattr(
        "app.api.jobs.ShopAIKeyEmbeddingAdapter",
        lambda: emb,
    )

    with _client() as client:
        first = client.post(f"/api/jobs/{job_id}/evaluate")
        assert first.status_code == 200
        body = EvaluateJobResponse.model_validate(first.json())
        assert body.outcome == "reused"
        assert body.evaluation.evaluation_state == "current"
        assert body.evaluation.result.final_score == pytest.approx(0.77)
        assert emb.call_count == 0

        second = client.post(f"/api/jobs/{job_id}/evaluate")
        assert second.status_code == 200
        assert EvaluateJobResponse.model_validate(second.json()).outcome == "reused"
        assert emb.call_count == 0

        missing = client.post(f"/api/jobs/{new_uuid()}/evaluate")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == ERROR_JOB_NOT_FOUND


def test_delete_delegates_to_coordinator_and_not_found(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _, _ = jobs_env
    deleted: list[str] = []

    async def _fake_delete(
        job_id: str,
        *,
        driver: Any,
        session_factory: Any = None,
        graph_delete_fn: Any = None,
        graph_absent_fn: Any = None,
    ) -> Any:
        del driver, session_factory, graph_delete_fn, graph_absent_fn
        from app.services.job_deletion import JobDeleteResult

        deleted.append(job_id)
        return JobDeleteResult(job_id=job_id)

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                jid = await _create_processed_job(
                    session,
                    raw_content="delete me",
                    raw_hash="hash-delete-me",
                )
                await session.commit()
                return jid
        finally:
            await engine.dispose()

    job_id = run_async(_seed())
    monkeypatch.setattr(
        "app.services.saved_jobs.delete_job",
        _fake_delete,
    )

    with _client() as client:
        resp = client.delete(f"/api/jobs/{job_id}")
        assert resp.status_code == 204
        assert resp.content == b""
        assert deleted == [job_id]

    # Unknown id without patch uses the real coordinator (separate client call
    # after restoring the production delete_job owner).
    from app.services.job_deletion import delete_job as real_delete_job

    monkeypatch.setattr("app.services.saved_jobs.delete_job", real_delete_job)
    with _client() as client:
        missing = client.delete(f"/api/jobs/{new_uuid()}")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == ERROR_JOB_NOT_FOUND
        assert FAKE_SHOPAIKEY not in str(missing.json())


def test_mutation_errors_omit_sensitive_fields(
    jobs_env: tuple[Path, Path, FakeDriver],
) -> None:
    with _client() as client:
        for path, method in (
            ("/api/jobs/save-and-evaluate", "post"),
            (f"/api/jobs/{new_uuid()}/evaluate", "post"),
            (f"/api/jobs/{new_uuid()}/reextract", "post"),
            (f"/api/jobs/{new_uuid()}", "delete"),
        ):
            if method == "post" and path.endswith("save-and-evaluate"):
                resp = client.post(path, json={"source_message_id": new_uuid()})
            elif method == "post":
                resp = client.post(path)
            else:
                resp = client.delete(path)
            assert resp.status_code in {400, 404, 409, 502}
            detail = resp.json()["detail"]
            assert "code" in detail and "summary" in detail
            blob = str(resp.json()).lower()
            for forbidden in (
                "traceback",
                "cypher",
                "select *",
                "password",
                "api_key",
                "shopaikey",
                str(FAKE_SHOPAIKEY).lower(),
            ):
                assert forbidden not in blob


# ---------------------------------------------------------------------------
# Plan 15 re-extraction public API
# ---------------------------------------------------------------------------


def test_reextract_request_schema_forbids_replacement_fields() -> None:
    """Zero-field request accepts empty payload and rejects arbitrary fields."""
    assert ReextractJobRequest.model_validate({}) is not None
    for payload in (
        {"raw_content": "x"},
        {"text": "x"},
        {"url": "https://example.com"},
        {"extraction": {}},
        {"embedding": [0.1]},
        {"jd_quality": "full"},
        {"evaluation": {}},
        {"extra": True},
    ):
        with pytest.raises(ValidationError):
            ReextractJobRequest.model_validate(payload)


def test_reextract_response_schema_sync_coupling() -> None:
    """Response coupling: true/null vs false/NEO4J_SYNC_FAILED/nonblank."""
    job = SavedJobListItem(
        id=new_uuid(),
        title="T",
        company="C",
        processing_status="processed",
        jd_quality="full",
        source_type="text",
        source_url=None,
        created_at=T0,
        updated_at=T0,
        evaluation_state="none",
        latest_score=None,
    )
    ok = ReextractJobResponse(
        outcome="updated",
        job=job,
        sync_ok=True,
        code=None,
        rebuild_instruction=None,
    )
    assert ok.sync_ok is True
    with pytest.raises(ValidationError):
        ReextractJobResponse(
            outcome="updated",
            job=job,
            sync_ok=True,
            code="NEO4J_SYNC_FAILED",
            rebuild_instruction=None,
        )
    with pytest.raises(ValidationError):
        ReextractJobResponse(
            outcome="updated",
            job=job,
            sync_ok=False,
            code=None,
            rebuild_instruction=NEO4J_REBUILD_INSTRUCTION,
        )
    with pytest.raises(ValidationError):
        ReextractJobResponse(
            outcome="updated",
            job=job,
            sync_ok=False,
            code="NEO4J_SYNC_FAILED",
            rebuild_instruction="   ",
        )
    warn = ReextractJobResponse(
        outcome="updated",
        job=job,
        sync_ok=False,
        code="NEO4J_SYNC_FAILED",
        rebuild_instruction=NEO4J_REBUILD_INSTRUCTION,
    )
    assert warn.code == "NEO4J_SYNC_FAILED"
    assert warn.rebuild_instruction


def test_reextract_absent_empty_and_forbidden_bodies(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only absent/empty bodies reach the service; replacement fields → 422."""
    db_path, _, _ = jobs_env
    service_calls: list[str] = []

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                jid = await _create_processed_job(
                    session,
                    raw_content=_REEXTRACT_GROUNDED_RAW,
                    raw_hash="hash-reextract-body",
                )
                await session.commit()
                return jid
        finally:
            await engine.dispose()

    job_id = run_async(_seed())

    async def _spy(job_id: str, **kwargs: Any) -> ReextractJobResponse:
        del kwargs
        service_calls.append(job_id)
        emb_job = SavedJobListItem(
            id=job_id,
            title="Backend Engineer",
            company="Acme",
            processing_status="processed",
            jd_quality="full",
            source_type="text",
            source_url=None,
            created_at=T0,
            updated_at=T0,
            evaluation_state="none",
            latest_score=None,
        )
        return ReextractJobResponse(
            outcome="updated",
            job=emb_job,
            sync_ok=True,
            code=None,
            rebuild_instruction=None,
        )

    monkeypatch.setattr("app.api.jobs.reextract_saved_job", _spy)

    with _client() as client:
        for forbidden in (
            {"raw_content": "client replacement"},
            {"text": "client text"},
            {"url": "https://example.com/jd"},
            {"extraction": {"title": "x"}},
            {"embedding": [0.1]},
            {"jd_quality": "full"},
            {"evaluation": {"id": new_uuid()}},
            {"unexpected": 1},
        ):
            resp = client.post(f"/api/jobs/{job_id}/reextract", json=forbidden)
            assert resp.status_code == 422, forbidden
        assert service_calls == []

        empty = client.post(f"/api/jobs/{job_id}/reextract", json={})
        assert empty.status_code == 200
        assert service_calls == [job_id]

        service_calls.clear()
        absent = client.post(f"/api/jobs/{job_id}/reextract")
        assert absent.status_code == 200
        assert service_calls == [job_id]


def test_reextract_success_and_graph_partial_stale_no_evaluate(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 200 success + graph warning; evaluation becomes stale; no evaluate."""
    db_path, _, _ = jobs_env
    evaluate_calls: list[str] = []

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                att_id = await _seed_profile(session)
                job_id = await _create_processed_job(
                    session,
                    raw_content=_REEXTRACT_GROUNDED_RAW,
                    raw_hash="hash-reextract-ok",
                    title="Prior Title",
                    company="Prior Co",
                )
                await session.commit()
            async with factory() as session:
                job = await jobs_repo.get_by_id(session, job_id)
                profile = await prof_repo.get_active_profile(session)
                prefs = await prof_repo.get_job_preferences(session)
                assert job and profile and prefs
                ctx = await _current_hash_for_job(session, job_id)
                await _insert_evaluation(
                    session,
                    job_id=job_id,
                    attachment_id=att_id,
                    context_hash=ctx,
                    job_revision=job.updated_at
                    if job.updated_at.tzinfo
                    else job.updated_at.replace(tzinfo=UTC),
                    profile_revision=profile.updated_at
                    if profile.updated_at.tzinfo
                    else profile.updated_at.replace(tzinfo=UTC),
                    preferences_revision=prefs.updated_at
                    if prefs.updated_at.tzinfo
                    else prefs.updated_at.replace(tzinfo=UTC),
                    final_score=0.77,
                    summary="pre-reextract-current",
                )
                await session.commit()
                return job_id
        finally:
            await engine.dispose()

    job_id = run_async(_seed())

    real_evaluate = saved_jobs_service.evaluate_job

    async def _eval_spy(*args: Any, **kwargs: Any) -> Any:
        evaluate_calls.append(str(kwargs.get("job_id") or (args[0] if args else "")))
        return await real_evaluate(*args, **kwargs)

    monkeypatch.setattr(saved_jobs_service, "evaluate_job", _eval_spy)

    async def _sync_ok(**_kwargs: Any) -> None:
        return None

    invoker = FakeJdInvoker([_reextract_extracted()])
    emb = FakeEmbeddingClient()
    _patch_reextract_adapters(monkeypatch, invoker, emb, job_sync_fn=_sync_ok)

    with _client() as client:
        # Confirm evaluation is current before re-extract.
        detail_before = SavedJobDetail.model_validate(
            client.get(f"/api/jobs/{job_id}").json()
        )
        assert detail_before.compact.evaluation_state == "current"

        ok = client.post(f"/api/jobs/{job_id}/reextract", json={})
        assert ok.status_code == 200
        body = ReextractJobResponse.model_validate(ok.json())
        assert body.outcome == "updated"
        assert body.job.id == job_id
        assert body.sync_ok is True
        assert body.code is None
        assert body.rebuild_instruction is None
        assert body.job.evaluation_state == "stale"
        assert body.job.latest_score == pytest.approx(0.77)
        assert body.job.title == "Backend Engineer"
        _assert_no_forbidden_list(ok.json())
        assert evaluate_calls == []
        assert invoker.call_count >= 1
        assert emb.call_count >= 1

    # Graph partial success after SQLite commit (failing same-ID sync seam).
    invoker2 = FakeJdInvoker([_reextract_extracted(extraction_confidence=0.92)])
    emb2 = FakeEmbeddingClient()

    async def _sync_fail(**_kwargs: Any) -> None:
        raise JobSyncError(
            "graph down",
            code="NEO4J_SYNC_FAILED",
            rebuild_instruction=NEO4J_REBUILD_INSTRUCTION,
        )

    _patch_reextract_adapters(
        monkeypatch, invoker2, emb2, job_sync_fn=_sync_fail
    )
    with _client() as client:
        partial = client.post(f"/api/jobs/{job_id}/reextract", json={})
        assert partial.status_code == 200
        warn = ReextractJobResponse.model_validate(partial.json())
        assert warn.outcome == "updated"
        assert warn.sync_ok is False
        assert warn.code == "NEO4J_SYNC_FAILED"
        assert warn.rebuild_instruction == NEO4J_REBUILD_INSTRUCTION
        assert warn.job.evaluation_state == "stale"
        _assert_no_forbidden_list(partial.json())
        assert evaluate_calls == []


def test_reextract_precommit_error_families(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-commit failures use safe detail and never return the success model."""
    db_path, _, _ = jobs_env

    async def _seed() -> tuple[str, str]:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                good = await _create_processed_job(
                    session,
                    raw_content=_REEXTRACT_GROUNDED_RAW,
                    raw_hash="hash-reextract-err",
                )
                blank = await jobs_repo.create_text_job(
                    session,
                    raw_content="placeholder",
                    raw_content_hash="hash-blank-raw",
                )
                # Force blank retained source after create.
                blank.raw_content = "   "
                await session.flush()
                await session.commit()
                return good, blank.id
        finally:
            await engine.dispose()

    good_id, blank_id = run_async(_seed())

    async def _sync_ok(**_kwargs: Any) -> None:
        return None

    # not found
    with _client() as client:
        missing = client.post(f"/api/jobs/{new_uuid()}/reextract", json={})
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == ERROR_JOB_NOT_FOUND
        assert "summary" in missing.json()["detail"]
        assert "raw_content" not in str(missing.json()).lower()

    # blank source
    _patch_reextract_adapters(
        monkeypatch,
        FakeJdInvoker([_reextract_extracted()]),
        FakeEmbeddingClient(),
        job_sync_fn=_sync_ok,
    )
    with _client() as client:
        blank = client.post(f"/api/jobs/{blank_id}/reextract", json={})
        assert blank.status_code == 400
        assert blank.json()["detail"]["code"] == ERROR_JD_SOURCE_NOT_RECOVERABLE
        assert "outcome" not in blank.json()

    # unscorable
    _patch_reextract_adapters(
        monkeypatch,
        FakeJdInvoker([_unscorable_extracted()]),
        FakeEmbeddingClient(),
        job_sync_fn=_sync_ok,
    )
    with _client() as client:
        unscorable = client.post(f"/api/jobs/{good_id}/reextract", json={})
        assert unscorable.status_code == 409
        assert unscorable.json()["detail"]["code"] == ERROR_JOB_NOT_SCORABLE
        assert "job" not in unscorable.json()

    # extraction provider failure
    _patch_reextract_adapters(
        monkeypatch,
        FakeJdInvoker([RuntimeError("provider down")]),
        FakeEmbeddingClient(),
        job_sync_fn=_sync_ok,
    )
    with _client() as client:
        prov = client.post(f"/api/jobs/{good_id}/reextract", json={})
        assert prov.status_code == 502
        assert prov.json()["detail"]["code"] in {
            FAILURE_PROVIDER_ERROR,
            "PROVIDER_ERROR",
        }

    # embedding failure
    _patch_reextract_adapters(
        monkeypatch,
        FakeJdInvoker([_reextract_extracted()]),
        FakeEmbeddingClient(
            error=EmbeddingAdapterError(
                FAILURE_EMBEDDING_TIMEOUT,
                "embedding timed out",
            )
        ),
        job_sync_fn=_sync_ok,
    )
    with _client() as client:
        emb_err = client.post(f"/api/jobs/{good_id}/reextract", json={})
        assert emb_err.status_code == 502
        assert emb_err.json()["detail"]["code"] == FAILURE_EMBEDDING_TIMEOUT

    # conflict mapped through service (simulated)
    async def _conflict(job_id: str, **kwargs: Any) -> JobReextractResult:
        del job_id, kwargs
        raise JobReextractError(
            ERROR_JOB_REEXTRACT_CONFLICT,
            "The Job was modified concurrently; re-extraction did not overwrite it.",
        )

    monkeypatch.setattr(saved_jobs_service, "reextract_job", _conflict)
    monkeypatch.setattr(
        "app.api.jobs.ShopAIKeyStructuredJdInvoker",
        lambda: FakeJdInvoker([_reextract_extracted()]),
    )
    monkeypatch.setattr(
        "app.api.jobs.ShopAIKeyEmbeddingAdapter",
        lambda: FakeEmbeddingClient(),
    )
    with _client() as client:
        conflict = client.post(f"/api/jobs/{good_id}/reextract", json={})
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == ERROR_JOB_REEXTRACT_CONFLICT
        assert "summary" in conflict.json()["detail"]
        blob = str(conflict.json()).lower()
        assert "traceback" not in blob
        assert FAKE_SHOPAIKEY.lower() not in blob


def test_reextract_logs_omit_raw_and_secrets(
    jobs_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Route/service logs may include job id/code/sync only — never raw/secrets."""
    db_path, _, _ = jobs_env
    secret = "SECRET_RAW_JD_DO_NOT_LOG_12345"

    async def _seed() -> str:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_profile(session)
                jid = await _create_processed_job(
                    session,
                    raw_content=_REEXTRACT_GROUNDED_RAW + "\n" + secret,
                    raw_hash="hash-reextract-log",
                )
                await session.commit()
                return jid
        finally:
            await engine.dispose()

    job_id = run_async(_seed())

    async def _sync_ok(**_kwargs: Any) -> None:
        return None

    invoker = FakeJdInvoker([_reextract_extracted()])
    emb = FakeEmbeddingClient()
    _patch_reextract_adapters(monkeypatch, invoker, emb, job_sync_fn=_sync_ok)

    with caplog.at_level(logging.INFO), _client() as client:
        resp = client.post(f"/api/jobs/{job_id}/reextract", json={})
        assert resp.status_code == 200
        text_blob = caplog.text
        assert secret not in text_blob
        assert FAKE_SHOPAIKEY not in text_blob
        assert "embedding_json" not in text_blob
        assert "SELECT " not in text_blob
        assert "MATCH (" not in text_blob
        # Failure path log redaction
        monkeypatch.setattr(
            saved_jobs_service,
            "reextract_job",
            MagicMock(
                side_effect=JobReextractError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    "structured output invalid after one repair attempt",
                )
            ),
        )
        bad = client.post(f"/api/jobs/{job_id}/reextract", json={})
        assert bad.status_code == 422
        assert secret not in caplog.text
        assert "prompt" not in caplog.text.lower() or job_id in caplog.text


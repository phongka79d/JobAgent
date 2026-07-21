"""Disposable fake-backed public-boundary E2E smoke (Plan 7 §7.2).

Exercises greeting → continuation → CV upload → propose draft → approval_required
→ save_profile resume → JD text save/extract/embed/sync → match_jobs with ordered
score and skill gaps. Dependency-overridden fakes only; never reads root ``.env``,
developer SQLite/files, live Neo4j, network, or browser.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.agent.checkpoint import open_checkpointer, thread_has_checkpoints
from app.db.models.attachments import ATTACHMENT_STATE_ACTIVE, Attachment
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    TOOL_EXECUTION_STATUS_COMPLETED,
    AgentRun,
    ChatMessage,
    ToolExecution,
)
from app.db.models.job_evaluations import JobEvaluation
from app.db.models.jobs import (
    JOB_JD_QUALITY_FULL,
    JOB_PROCESSING_STATUS_PROCESSED,
    JobPost,
)
from app.db.models.profiles import PROFILE_DRAFT_ID
from app.db.session import get_session_factory
from app.graph.rebuild_snapshot import load_source_revision_snapshot
from app.repositories import profiles as profile_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.chat import HistoryPage
from app.schemas.matching import parse_match_jobs_result_data
from app.services.jd_extraction import ExtractedJobPost
from app.services.profile_extraction import ExtractedCandidateProfile
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage
from app.tools.profile import (
    COMMIT_PROFILE_DRAFT_NAME,
    PROFILE_COMMIT_ACTIONS,
    PROFILE_COMMIT_KIND,
    PROPOSE_PROFILE_FROM_CV_NAME,
)
from app.tools.registry import production_registry
from sqlalchemy import func, select

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.fakes.fake_chat_model import FakeChatModel
from tests.fakes.matching import ScriptedRead, ScriptedReadDriver
from tests.fakes.structured_output import ScriptedStructuredInvoker
from tests.support.db_migration import run_async
from tests.support.health import FAKE_SHOPAIKEY, FakeDriver
from tests.support.public_api import (
    ai_text,
    ai_tool_call,
    client_with_fake_chat,
    override_chat_deps,
    parse_sse_wire,
)
from tests.unit.test_profile_extraction import CoveringDocumentInvoker

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CV_PDF = FIXTURES / "cv" / "digital_cv_01.pdf"
SKILLS_FIXTURE = FIXTURES / "skills_seed.yaml"

GREETING_REPLY = "Hello! I can help with your profile, jobs, and matches."
CONTINUE_REPLY = "Sure — upload a CV when you are ready, or paste a job description."
PROPOSE_REPLY = "I drafted a candidate profile from your CV for review."
SAVE_REPLY = "Your profile is saved and active."
JD_REPLY = "Job saved, extracted, embedded, and synced."
MATCH_REPLY = "Here are ordered match scores and skill gaps for your saved jobs."

SYNTHETIC_JD_TEXT = (
    "Backend Engineer at Acme Corp. Build REST APIs in Python. "
    "Required: Python and SQL. Hybrid mid-level role in Berlin."
)

FALSE_SUCCESS_MARKERS = (
    FAKE_SHOPAIKEY,
    "Traceback",
    "password=",
    "bolt://",
    "SHOPAIKEY",
    "api_key",
    "%PDF",
)


class _RecordingJobSync:
    """Zero-arg-friendly job sync counter (no real Neo4j writes)."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self.calls += 1


async def _noop_candidate_sync() -> None:
    """Profile commit graph sync stand-in (SQLite remains source of truth)."""
    return None


def _normalizer() -> SkillNormalizer:
    return SkillNormalizer.from_path(SKILLS_FIXTURE)


def _extracted_profile() -> ExtractedCandidateProfile:
    return ExtractedCandidateProfile.model_validate(
        {
            "summary": "Backend engineer with strong Python experience.",
            "current_title": "Backend Engineer",
            "total_experience_years": 4.0,
            "skills": [
                {
                    "name": "Python",
                    "confidence": 0.95,
                    "proficiency": "advanced",
                    "years": 4.0,
                    "evidence": ["4 years Python backend"],
                }
            ],
            "experiences": [
                {
                    "title": "Backend Engineer",
                    "company": "Example Co",
                    "start_date_text": "2020",
                    "end_date_text": "present",
                    "summary": "APIs and services",
                }
            ],
            "education": [
                {
                    "institution": "State U",
                    "degree": "BSc",
                    "field": "CS",
                    "graduation_year": 2019,
                }
            ],
            "languages": [{"name": "English", "proficiency": "fluent"}],
            "extraction_confidence": 0.9,
        }
    )


def _extracted_jd() -> ExtractedJobPost:
    # Grounded to SYNTHETIC_JD_TEXT (Plan 15 semantic guard).
    return ExtractedJobPost.model_validate(
        {
            "title": "Backend Engineer",
            "company": "Acme Corp",
            "summary": "Build REST APIs in Python.",
            "responsibilities": ["Build REST APIs in Python"],
            "required_skills": [
                {
                    "name": "Python",
                    "confidence": 0.95,
                    "evidence": ["Required: Python and SQL"],
                },
                {
                    "name": "SQL",
                    "confidence": 0.9,
                    "evidence": ["Required: Python and SQL"],
                },
            ],
            "preferred_skills": [],
            "seniority": "mid",
            "min_experience_years": 3.0,
            "max_experience_years": 6.0,
            "location": "Berlin",
            "work_mode": "hybrid",
            "extraction_confidence": 0.88,
        }
    )


def _as_z(value: datetime) -> str:
    if value.tzinfo is None:
        stamp = value.replace(tzinfo=UTC)
    else:
        stamp = value.astimezone(UTC)
    return stamp.isoformat().replace("+00:00", "Z")


def _assert_no_false_success(text: str) -> None:
    lower = text.lower()
    for marker in FALSE_SUCCESS_MARKERS:
        assert marker not in text, f"leaked marker {marker!r}"
    assert "exception" not in lower or "no exception" in lower


def _event_names(events: list[dict[str, Any]]) -> list[str]:
    return [e["event"] for e in events]


def _build_registry(
    *,
    files_dir: Path,
    profile_invoker: ScriptedStructuredInvoker,
    jd_invoker: ScriptedStructuredInvoker,
    embedder: FakeEmbeddingClient,
    match_driver: ScriptedReadDriver,
    job_sync: _RecordingJobSync,
) -> Any:
    storage = AttachmentStorage(files_dir)
    storage.ensure_root()
    return production_registry(
        session_factory=get_session_factory(),
        storage=storage,
        invoker=profile_invoker,
        jd_invoker=jd_invoker,
        embedding_client=embedder,
        normalizer=_normalizer(),
        driver=match_driver,  # type: ignore[arg-type]
        sync_fn=_noop_candidate_sync,
        job_sync_fn=job_sync,
    )


@pytest.fixture
def demo_env(
    chat_env: tuple[Path, Path, FakeDriver],
) -> Iterator[tuple[Path, Path]]:
    """Disposable migrated SQLite + FILES_DIR (chat_env already installs Neo4j fake)."""
    db_path, files_dir, _fake = chat_env
    yield db_path, files_dir


def test_demo_flow_greeting_to_matching_public_boundary(
    demo_env: tuple[Path, Path],
) -> None:
    """Locked Plan 7 §7.2 sequence through public FastAPI APIs + resume semantics."""
    db_path, files_dir = demo_env
    assert CV_PDF.is_file()

    # Plan 9: propose path is document-first; profile-first invokers are ignored.
    profile_invoker = CoveringDocumentInvoker()
    jd_invoker = ScriptedStructuredInvoker([_extracted_jd()])
    embedder = FakeEmbeddingClient()
    job_sync = _RecordingJobSync()
    # Match scripts filled after SQLite holds approved profile + scorable job.
    match_driver = ScriptedReadDriver(scripts=())

    registry = _build_registry(
        files_dir=files_dir,
        profile_invoker=profile_invoker,
        jd_invoker=jd_invoker,
        embedder=embedder,
        match_driver=match_driver,
        job_sync=job_sync,
    )

    with client_with_fake_chat(
        db_path, FakeChatModel(responses=[ai_text(GREETING_REPLY)]), registry
    ) as client:
        # --- 1. Greeting: natural reply, no tools ---
        greet = client.post(
            "/api/chat/turns",
            json={"message": "hi there", "attachment_ids": []},
        )
        assert greet.status_code == 200
        assert "text/event-stream" in greet.headers.get("content-type", "")
        _assert_no_false_success(greet.text)
        greet_events = parse_sse_wire(greet.text)
        greet_names = _event_names(greet_events)
        assert greet_names[0] == "run_started"
        assert greet_events[0]["payload"]["resumed"] is False
        assert "tool_status" not in greet_names
        assert "approval_required" not in greet_names
        assert "text_delta" in greet_names
        assert greet_names[-1] == "run_completed"
        deltas = [
            e["payload"]["delta"]
            for e in greet_events
            if e["event"] == "text_delta"
        ]
        assert "".join(deltas) == GREETING_REPLY

        hist = HistoryPage.model_validate(
            client.get("/api/chat/history", params={"limit": 50}).json()
        )
        assert len(hist.items) == 2
        assert hist.items[0].content == "hi there"
        assert hist.items[0].run is not None
        assert hist.items[0].run.state == AGENT_RUN_STATE_COMPLETED
        assert hist.items[0].run.tool_executions == []
        assert hist.items[1].content == GREETING_REPLY

        # --- 2. Same-conversation continuation (still no tools) ---
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text(CONTINUE_REPLY)]),
            registry=registry,
            db_path=db_path,
        )
        cont = client.post(
            "/api/chat/turns",
            json={
                "message": "yes please help me set up my profile",
                "attachment_ids": [],
            },
        )
        assert cont.status_code == 200
        cont_events = parse_sse_wire(cont.text)
        cont_names = _event_names(cont_events)
        assert cont_names[0] == "run_started"
        assert "tool_status" not in cont_names
        assert cont_names[-1] == "run_completed"
        cont_deltas = [
            e["payload"]["delta"]
            for e in cont_events
            if e["event"] == "text_delta"
        ]
        assert "".join(cont_deltas) == CONTINUE_REPLY
        _assert_no_false_success(cont.text)

        # --- 3. Upload synthetic digital PDF ---
        upload = client.post(
            "/api/attachments/cv",
            files={
                "file": (
                    "demo-cv.pdf",
                    CV_PDF.read_bytes(),
                    "application/pdf",
                )
            },
        )
        assert upload.status_code == 200, upload.text
        _assert_no_false_success(upload.text)
        upload_body = upload.json()
        assert upload_body["outcome"] == "new"
        attachment_id = upload_body["attachment"]["id"]
        assert upload_body["attachment"]["state"] == "staged"
        assert "storage_path" not in upload_body["attachment"]
        assert (files_dir / attachment_id).is_file()

        # --- 4. Attachment turn → propose_profile_from_cv → validated draft ---
        # Propose auto-chains commit_profile_draft so the UI gets Save Profile
        # without a second user turn or LLM cooperation.
        override_chat_deps(
            client,
            model=FakeChatModel(
                responses=[
                    ai_tool_call(
                        PROPOSE_PROFILE_FROM_CV_NAME,
                        call_id="call-demo-propose",
                        args={"attachment_id": attachment_id},
                    ),
                ]
            ),
            registry=registry,
            db_path=db_path,
        )
        propose = client.post(
            "/api/chat/turns",
            json={
                "message": "please extract my profile from the uploaded CV",
                "attachment_ids": [attachment_id],
            },
        )
        assert propose.status_code == 200, propose.text
        propose_events = parse_sse_wire(propose.text)
        propose_names = _event_names(propose_events)
        assert propose_names[0] == "run_started"
        assert "tool_status" in propose_names
        assert propose_names[-1] == "approval_required"
        assert "run_completed" not in propose_names
        approval = propose_events[-1]
        assert approval["payload"]["kind"] == PROFILE_COMMIT_KIND
        assert approval["payload"]["allowed_actions"] == list(
            PROFILE_COMMIT_ACTIONS
        )
        commit_run_id = approval["run_id"]
        _assert_no_false_success(propose.text)
        # Document-first path may issue one batch (+ optional consolidate).
        assert len(profile_invoker.calls) >= 1

        async def _assert_draft() -> None:
            factory = get_session_factory()
            async with factory() as session:
                draft = await profile_repo.get_current_draft(session)
                assert draft is not None
                assert draft.id == PROFILE_DRAFT_ID
                assert draft.source_attachment_id == attachment_id
                profile = draft.draft_json["candidate_profile"]
                # Document-first projection from CoveringDocumentInvoker.
                assert isinstance(profile.get("current_title"), str)
                assert profile["current_title"]
                assert any(
                    s["skill"]["canonical_key"] == "python"
                    for s in profile["skills"]
                )
                assert await profile_repo.get_active_profile(session) is None

        run_async(_assert_draft())

        blocked = client.post(
            "/api/chat/turns",
            json={"message": "should be blocked", "attachment_ids": []},
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "APPROVAL_ACTION_REQUIRED"

        # --- 6. Resume save_profile ---
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text(SAVE_REPLY)]),
            registry=registry,
            db_path=db_path,
        )
        resume = client.post(
            f"/api/chat/runs/{commit_run_id}/resume",
            json={"action": "save_profile"},
        )
        assert resume.status_code == 200, resume.text
        resume_events = parse_sse_wire(resume.text)
        resume_names = _event_names(resume_events)
        assert resume_names[0] == "run_started"
        assert resume_events[0]["payload"]["resumed"] is True
        assert resume_names[-1] == "run_completed"
        assert "approval_required" not in resume_names
        _assert_no_false_success(resume.text)

        async def _assert_active_profile() -> None:
            factory = get_session_factory()
            async with factory() as session:
                assert await profile_repo.get_current_draft(session) is None
                active = await profile_repo.get_active_profile(session)
                assert active is not None
                assert active.active_attachment_id == attachment_id
                title = active.profile_json.get("current_title")
                assert isinstance(title, str) and title
                att = await session.get(Attachment, attachment_id)
                assert att is not None
                assert att.state == ATTACHMENT_STATE_ACTIVE
                n_active = int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(Attachment)
                            .where(Attachment.state == ATTACHMENT_STATE_ACTIVE)
                        )
                    ).scalar_one()
                )
                assert n_active == 1
                tools = await tool_repo.list_for_run_ids(
                    session, [commit_run_id]
                )
                # Same run: propose_profile_from_cv then auto-chained commit.
                assert len(tools) == 2
                by_name = {t.tool_name: t for t in tools}
                assert PROPOSE_PROFILE_FROM_CV_NAME in by_name
                assert COMMIT_PROFILE_DRAFT_NAME in by_name
                commit_row = by_name[COMMIT_PROFILE_DRAFT_NAME]
                assert commit_row.status == TOOL_EXECUTION_STATUS_COMPLETED
                stored = tool_repo.load_stored_result(commit_row)
                assert stored.ok is True
                assert stored.data is not None
                assert stored.data.get("committed") is True

        run_async(_assert_active_profile())

        async def _checkpoint_gone() -> bool:
            async with open_checkpointer(db_path) as saver:
                return await thread_has_checkpoints(saver, commit_run_id)

        assert run_async(_checkpoint_gone()) is False

        # Terminal no-op resume (no replay / no false success path).
        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text("must not run")]),
            registry=registry,
            db_path=db_path,
        )
        noop = client.post(
            f"/api/chat/runs/{commit_run_id}/resume",
            json={"action": "save_profile"},
        )
        assert noop.status_code == 200
        noop_events = parse_sse_wire(noop.text)
        assert _event_names(noop_events) == ["run_started", "run_completed"]

        # --- 7. Synthetic JD text → confirm → save/extract/embed/sync ---
        override_chat_deps(
            client,
            model=FakeChatModel(
                responses=[
                    ai_tool_call(
                        "save_job",
                        call_id="call-demo-save-job",
                        args={"text": SYNTHETIC_JD_TEXT},
                    ),
                    ai_text(JD_REPLY),
                ]
            ),
            registry=registry,
            db_path=db_path,
        )
        jd_turn = client.post(
            "/api/chat/turns",
            json={
                "message": f"save this job:\n{SYNTHETIC_JD_TEXT}",
                "attachment_ids": [],
            },
        )
        assert jd_turn.status_code == 200, jd_turn.text
        jd_events = parse_sse_wire(jd_turn.text)
        jd_names = _event_names(jd_events)
        assert jd_names[0] == "run_started"
        assert jd_names[-1] == "approval_required"
        assert "run_completed" not in jd_names
        approval = jd_events[-1]
        assert approval["payload"]["kind"] == "job_save_confirmation"
        assert approval["payload"]["allowed_actions"] == [
            "save_job",
            "cancel_save_job",
        ]
        assert approval["payload"]["card"]["source"] == "current_message"
        jd_run_id = approval["run_id"]
        _assert_no_false_success(jd_turn.text)
        assert SYNTHETIC_JD_TEXT not in jd_turn.text
        assert jd_invoker.call_count == 0
        assert embedder.call_count == 0
        assert job_sync.calls == 0

        async def _assert_job_pending() -> None:
            factory = get_session_factory()
            async with factory() as session:
                job_count = await session.execute(
                    select(func.count()).select_from(JobPost)
                )
                assert int(job_count.scalar_one()) == 0
                evaluation_count = await session.execute(
                    select(func.count()).select_from(JobEvaluation)
                )
                assert int(evaluation_count.scalar_one()) == 0

        run_async(_assert_job_pending())

        override_chat_deps(
            client,
            model=FakeChatModel(responses=[ai_text(JD_REPLY)]),
            registry=registry,
            db_path=db_path,
        )
        jd_resume = client.post(
            f"/api/chat/runs/{jd_run_id}/resume",
            json={"action": "save_job"},
        )
        assert jd_resume.status_code == 200, jd_resume.text
        jd_resume_events = parse_sse_wire(jd_resume.text)
        jd_resume_names = _event_names(jd_resume_events)
        assert jd_resume_names[0] == "run_started"
        assert jd_resume_events[0]["payload"]["resumed"] is True
        assert "tool_status" in jd_resume_names
        assert jd_resume_names[-1] == "run_completed"
        assert "approval_required" not in jd_resume_names
        _assert_no_false_success(jd_resume.text)
        assert jd_invoker.call_count == 1
        assert embedder.call_count >= 1
        assert job_sync.calls == 1

        async def _assert_job() -> str:
            factory = get_session_factory()
            async with factory() as session:
                rows = (
                    await session.execute(select(JobPost))
                ).scalars().all()
                assert len(rows) == 1
                job = rows[0]
                assert job.processing_status == JOB_PROCESSING_STATUS_PROCESSED
                assert job.jd_quality == JOB_JD_QUALITY_FULL
                assert job.extraction_json is not None
                assert job.embedding_json is not None
                assert job.extraction_json["title"] == "Backend Engineer"
                assert job.extraction_json["company"] == "Acme Corp"
                tools = await tool_repo.list_for_run_ids(session, [jd_run_id])
                assert len(tools) == 1
                assert tools[0].status == TOOL_EXECUTION_STATUS_COMPLETED
                result = tool_repo.load_stored_result(tools[0])
                assert result.ok is True
                assert result.data is not None
                assert result.data.get("outcome") == "created"
                assert result.data.get("job_id") == job.id
                evaluation_count = await session.execute(
                    select(func.count()).select_from(JobEvaluation)
                )
                assert int(evaluation_count.scalar_one()) == 0
                return job.id

        job_id = run_async(_assert_job())

        # Configure revision-consistent match reads from SQLite truth.
        async def _revision_rows() -> tuple[
            list[dict[str, Any]], list[dict[str, Any]]
        ]:
            factory = get_session_factory()
            async with factory() as session:
                snapshot = await load_source_revision_snapshot(session)
            candidates: list[dict[str, Any]] = []
            if snapshot.candidate is not None:
                candidates.append(
                    {
                        "id": snapshot.candidate.id,
                        "source_updated_at": _as_z(
                            snapshot.candidate.updated_at
                        ),
                    }
                )
            jobs = [
                {
                    "id": j.id,
                    "source_updated_at": _as_z(j.updated_at),
                }
                for j in snapshot.jobs
            ]
            return candidates, jobs

        candidates, jobs = run_async(_revision_rows())
        assert candidates
        assert any(j["id"] == job_id for j in jobs)
        match_driver.reconfigure(
            (
                ScriptedRead("MATCH (c:Candidate)", candidates),
                ScriptedRead("MATCH (j:Job)", jobs),
                ScriptedRead(
                    "db.index.vector.queryNodes",
                    [{"id": job_id, "score": 0.91}],
                ),
            )
        )

        # --- 8. match_jobs → ordered score + skill gaps ---
        override_chat_deps(
            client,
            model=FakeChatModel(
                responses=[
                    ai_tool_call(
                        "match_jobs",
                        call_id="call-demo-match",
                        args={"limit": 10},
                    ),
                    ai_text(MATCH_REPLY),
                ]
            ),
            registry=registry,
            db_path=db_path,
        )
        match_turn = client.post(
            "/api/chat/turns",
            json={
                "message": "match my profile to saved jobs",
                "attachment_ids": [],
            },
        )
        assert match_turn.status_code == 200, match_turn.text
        match_events = parse_sse_wire(match_turn.text)
        match_names = _event_names(match_events)
        assert match_names[0] == "run_started"
        assert "tool_status" in match_names
        assert match_names[-1] == "run_completed"
        _assert_no_false_success(match_turn.text)

        async def _assert_match_durable() -> None:
            factory = get_session_factory()
            async with factory() as session:
                # One active CV/profile; draft still gone.
                assert await profile_repo.get_current_draft(session) is None
                active = await profile_repo.get_active_profile(session)
                assert active is not None
                n_active = int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(Attachment)
                            .where(Attachment.state == ATTACHMENT_STATE_ACTIVE)
                        )
                    ).scalar_one()
                )
                assert n_active == 1

                # Durable chat/runs/tools present.
                msg_count = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ChatMessage)
                        )
                    ).scalar_one()
                )
                run_count = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(AgentRun)
                        )
                    ).scalar_one()
                )
                tool_count = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(ToolExecution)
                        )
                    ).scalar_one()
                )
                # Greeting, continuation, propose(+auto-commit), JD, match turns.
                assert msg_count >= 8
                assert run_count >= 5
                assert tool_count >= 4

                match_rows = (
                    await session.execute(
                        select(ToolExecution).where(
                            ToolExecution.tool_name == "match_jobs"
                        )
                    )
                ).scalars().all()
                assert len(match_rows) == 1
                row = match_rows[0]
                assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
                stored = tool_repo.load_stored_result(row)
                assert stored.ok is True
                assert stored.data is not None
                data = parse_match_jobs_result_data(stored.data)
                assert data.count == 1
                assert data.results[0].job_id == job_id
                assert data.results[0].final_score > 0
                assert data.results[0].title == "Backend Engineer"
                matched_keys = {
                    s.job_skill_key
                    for s in data.results[0].matched_required_skills
                }
                assert "python" in matched_keys
                missing_keys = {
                    s.job_skill_key
                    for s in data.results[0].missing_required_skills
                }
                assert "sql" in missing_keys
                assert data.results[0].summary
                # Ordered score surface (single result is trivially ordered).
                scores = [r.final_score for r in data.results]
                assert scores == sorted(scores, reverse=True)

                # Processed scorable job still one.
                jobs_n = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(JobPost)
                        )
                    ).scalar_one()
                )
                assert jobs_n == 1

        run_async(_assert_match_durable())

        # History stays coherent after full flow.
        final_hist = HistoryPage.model_validate(
            client.get("/api/chat/history", params={"limit": 50}).json()
        )
        assert len(final_hist.items) >= 10
        roles = {item.role for item in final_hist.items}
        assert "user" in roles
        assert "assistant" in roles
        _assert_no_false_success(
            client.get("/api/chat/history", params={"limit": 50}).text
        )

        # Matching used revision scripts (no write Cypher).
        assert match_driver.write_queries == []
        assert any("MATCH (c:Candidate)" in q for q in match_driver.queries)
        assert any("queryNodes" in q for q in match_driver.queries)

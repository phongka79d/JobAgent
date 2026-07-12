"""Production tool/route exposure and Neo4j failure isolation proofs."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.enums import OutboxStatus
from app.graph.candidate_sync import (
    CANDIDATE_SYNC_OPERATION,
    process_candidate_sync_outbox,
)
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.repositories.graph_outbox import GraphOutboxRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.attachment_storage import iter_byte_chunks
from app.services.profile_service import ProfileCommitService
from app.tools.registry import CURRENT_PROFILE_TOOL_NAMES
from fastapi.testclient import TestClient
from tests.fakes.agent_tools import ScriptedDecision, decision_text
from tests.integration.profile_workflow.support import (
    API_SRC,
    APP_SRC,
    AUTHORIZED_APP_PATHS,
    FRONTEND_SRC,
    PRODUCTION_FORBIDDEN_RE,
    REPO_ROOT,
    build_app,
    build_tools,
    migrated_db,
)
from tests.integration.test_candidate_sync import StatefulCandidateGraph
from tests.tools.profile_tool_helpers import profile


def test_production_has_exactly_four_profile_tools_and_no_forbidden_exposure() -> None:
    assert CURRENT_PROFILE_TOOL_NAMES == {
        "get_candidate_context",
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
    }
    hits: list[str] = []
    for path in APP_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if PRODUCTION_FORBIDDEN_RE.search(text):
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], f"forbidden production exposure: {hits}"

    if FRONTEND_SRC.exists():
        fe_hits: list[str] = []
        for path in FRONTEND_SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            rel = path.relative_to(FRONTEND_SRC).as_posix()
            if rel.startswith("test/") or ".test." in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            if "echo_label" in text or "make_echo_label" in text:
                fe_hits.append(str(path.relative_to(REPO_ROOT)))
            if re.search(r"\braw_cv\b", text):
                fe_hits.append(str(path.relative_to(REPO_ROOT)))
        assert fe_hits == [], f"frontend forbidden exposure: {fe_hits}"


@pytest.mark.asyncio
async def test_application_routes_are_exactly_seven_authorized(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (db_path, manager, settings, storage):
        tools, _ = build_tools(
            manager, storage, settings, extraction_responses=[]
        )
        application = build_app(
            manager=manager,
            settings=settings,
            db_path=db_path,
            storage=storage,
            decision=ScriptedDecision([decision_text("route ok")]),
            tools=tools,
        )
        with TestClient(application) as client:
            paths = set(client.app.openapi()["paths"])  # type: ignore[attr-defined]
            app_paths = {p for p in paths if p.startswith("/api/")}
            assert app_paths == AUTHORIZED_APP_PATHS

            decorator_paths: set[str] = set()
            route_re = re.compile(
                r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']+)[\"']"
            )
            for path in API_SRC.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for match in route_re.finditer(text):
                    decorator_paths.add(match.group(2))
            assert decorator_paths == AUTHORIZED_APP_PATHS


@pytest.mark.asyncio
async def test_neo4j_failure_does_not_roll_back_approved_sqlite(
    tmp_path: Path,
) -> None:
    async with migrated_db(tmp_path) as (_db_path, manager, _settings, storage):
        attachment_id = uuid4()
        staged = await storage.stage(
            attachment_id, iter_byte_chunks(b"%PDF-1.4 neo4j-fail")
        )
        document = ProfileDraftDocument(
            profile=profile("Graph failure proof"),
            approval_summary=build_approval_summary(profile("Graph failure proof")),
        )
        async with manager.session_scope() as session:
            await AttachmentRepository(session).add_staged(
                StagedAttachmentInput(
                    id=attachment_id,
                    file_hash=attachment_id.hex,
                    original_name="cv.pdf",
                    mime_type="application/pdf",
                    size_bytes=16,
                    storage_path=staged.storage_path,
                    page_count=1,
                )
            )
            draft = await ProfileDraftRepository(session).create(
                document, source_attachment_id=attachment_id
            )
            draft_id = draft.id

        result = await ProfileCommitService(manager, storage).commit_draft(draft_id)
        assert result.active_attachment_id == attachment_id

        assert (
            await process_candidate_sync_outbox(
                manager, StatefulCandidateGraph(fail=True)
            )
            == 0
        )
        async with manager.session_scope() as session:
            approved = await ProfileRepository(session).get()
            assert approved is not None
            assert approved.profile.summary == "Graph failure proof"
            row = await GraphOutboxRepository(session).get_by_identity(
                CANDIDATE_SYNC_OPERATION, "1"
            )
            assert row is not None
            assert row.status == OutboxStatus.FAILED.value

        healthy = StatefulCandidateGraph()
        assert await process_candidate_sync_outbox(manager, healthy) == 1
        assert healthy.candidates == {"1"}

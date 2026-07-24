from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import job_evaluations as evaluation_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as profile_repo
from app.repositories import workspace_state as workspace_repo
from app.services.evaluation_context import (
    EvaluationContextFacts,
    evaluation_context_hash,
)
from app.services.profile_approval import commit_approved_draft
from app.services.profile_drafts import propose_profile_from_cv
from app.storage.attachments import AttachmentStorage

from tests.integration.test_profile_approval import _seed_cv_document_draft
from tests.support.db_migration import run_async, session_factory
from tests.unit.test_profile_extraction import (
    CV_DIR,
    CoveringDocumentInvoker,
    _normalizer,
    _valid_profile,
)


def _preferences() -> dict[str, Any]:
    return {
        "target_roles": ["Platform Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["senior"],
    }


def test_same_profile_reextraction_preserves_owner_preferences_and_conversations(
    migrated_sqlite: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"
    invoker = CoveringDocumentInvoker()
    scorer = Mock(side_effect=AssertionError("re-extraction must not score"))
    monkeypatch.setattr(
        "app.services.job_evaluation.project_single_job_match", scorer
    )

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="ready-reextract",
                    original_name="ready.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await att_repo.mark_active(session, attachment_id)
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_id,
                    display_name="Ready",
                    profile_json=_valid_profile().model_dump(mode="json"),
                    location=None,
                    extraction_version="old-v1",
                    source_hash="old-source-hash",
                )
                preference_row = await profile_repo.upsert_profile_preferences(
                    session,
                    profile_id=profile.id,
                    preferences_json=_preferences(),
                )
                first = await conversations_repo.create_for_profile(
                    session, profile_id=profile.id, title="First"
                )
                second = await conversations_repo.create_for_profile(
                    session, profile_id=profile.id, title="Second"
                )
                await workspace_repo.set_active_profile_id(session, profile.id)
                job = await jobs_repo.create_text_job(
                    session,
                    raw_content="Synthetic retained JD",
                    raw_content_hash="ready-reextract-job",
                )
                old_facts = EvaluationContextFacts(
                    job_id=job.id,
                    job_revision=job.updated_at,
                    active_attachment_id=attachment_id,
                    cv_source_hash=profile.source_hash,
                    profile_revision=profile.updated_at,
                    preferences_revision=preference_row.updated_at,
                )
                old_context_hash = evaluation_context_hash(old_facts)
                await evaluation_repo.insert_evaluation(
                    session,
                    job_id=job.id,
                    profile_id=profile.id,
                    evaluation_context_hash=old_context_hash,
                    job_revision=old_facts.job_revision,
                    profile_revision=old_facts.profile_revision,
                    preferences_revision=old_facts.preferences_revision,
                    cv_source_hash=old_facts.cv_source_hash,
                    matching_contract_version=old_facts.matching_contract_version,
                    result={
                        "job_id": job.id,
                        "title": "Platform Engineer",
                        "company": None,
                        "location": None,
                        "work_mode": "unknown",
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
                        "summary": "Historical evaluation",
                    },
                )
                old_revision = profile.updated_at
                await session.commit()
                profile_id = profile.id
                conversation_ids = {first.id, second.id}
                job_id = job.id

            proposed = await propose_profile_from_cv(
                attachment_id=attachment_id,
                target_profile_id=profile_id,
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=invoker,
                reprocess=True,
            )
            assert proposed.tool_result.ok is True
            async with factory() as session:
                draft = await profile_repo.get_current_draft(session)
                assert draft is not None
                assert draft.target_profile_id == profile_id
                assert draft.draft_json["job_preferences"] == _preferences()
                changed = dict(draft.draft_json)
                changed_profile = dict(changed["candidate_profile"])
                changed_profile["full_name"] = "Unsupported Person"
                changed["candidate_profile"] = changed_profile
                await profile_repo.upsert_current_draft(
                    session,
                    draft_json=changed,
                    source_attachment_id=attachment_id,
                    target_profile_id=profile_id,
                )
                await session.commit()

            async def no_sync() -> None:
                return None

            approved = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
            )
            assert approved.ok is True
            assert approved.profile_id == profile_id

            async with factory() as session:
                refreshed = await profile_repo.get_profile(session, profile_id)
                prefs = await profile_repo.get_profile_preferences(
                    session, profile_id
                )
                document = await cv_doc_repo.get_document(session, attachment_id)
                conversations = await conversations_repo.list_for_profile(
                    session, profile_id=profile_id, limit=50, before=None
                )
                assert refreshed is not None
                assert prefs is not None
                assert document is not None
                assert refreshed.attachment_id == attachment_id
                refreshed_revision = refreshed.updated_at.replace(tzinfo=None)
                assert refreshed_revision != old_revision.replace(tzinfo=None)
                assert refreshed.source_hash == document.source_hash
                assert refreshed.source_hash != "old-source-hash"
                assert refreshed.profile_json["full_name"] is None
                assert prefs.preferences_json == _preferences()
                assert {item.id for item in conversations.rows} == conversation_ids
                assert await workspace_repo.get_active_profile_id(session) == profile_id
                job = await jobs_repo.get_by_id(session, job_id)
                assert job is not None
                current_facts = EvaluationContextFacts(
                    job_id=job.id,
                    job_revision=job.updated_at.replace(tzinfo=UTC),
                    active_attachment_id=attachment_id,
                    cv_source_hash=refreshed.source_hash,
                    profile_revision=refreshed.updated_at.replace(tzinfo=UTC),
                    preferences_revision=prefs.updated_at.replace(tzinfo=UTC),
                )
                lookup = await evaluation_repo.lookup_for_job(
                    session,
                    job_id=job_id,
                    profile_id=profile_id,
                    current_context_hash=evaluation_context_hash(current_facts),
                )
                assert lookup.currentness == "stale"
                assert lookup.evaluation is not None
                assert lookup.evaluation.evaluation_context_hash == old_context_hash
            scorer.assert_not_called()
        finally:
            await engine.dispose()

    run_async(_body())


def test_approval_rejects_a_draft_without_explicit_profile_owner(
    migrated_sqlite: Path, tmp_path: Path
) -> None:
    storage = AttachmentStorage(tmp_path / "files")
    storage.ensure_root()
    pdf = CV_DIR / "digital_cv_01.pdf"

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            attachment_id = new_uuid()
            rel = storage.write_bytes(attachment_id, pdf.read_bytes())
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="ownerless-draft",
                    original_name="ownerless.pdf",
                    size_bytes=pdf.stat().st_size,
                    storage_path=rel,
                    page_count=1,
                    attachment_id=attachment_id,
                )
                await profile_repo.upsert_current_draft(
                    session,
                    draft_json={
                        "candidate_profile": _valid_profile().model_dump(mode="json"),
                        "job_preferences": _preferences(),
                    },
                    source_attachment_id=attachment_id,
                    target_profile_id=None,
                )
                await _seed_cv_document_draft(
                    session,
                    attachment_id=attachment_id,
                    profile_json=_valid_profile().model_dump(mode="json"),
                )
                await session.commit()

            async def no_sync() -> None:
                return None

            result = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
            )
            assert result.ok is False
            assert result.code == "PROFILE_INCONSISTENT"
        finally:
            await engine.dispose()

    run_async(_body())

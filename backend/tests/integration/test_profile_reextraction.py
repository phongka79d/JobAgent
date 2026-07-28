from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from app.core.ids import new_uuid
from app.db.models.chat import AgentRun, ChatMessage, Conversation, ToolExecution
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
from app.services.profile_reextraction import (
    ProfileReextractError,
    ProfileReextractionCoordinator,
)
from app.storage.attachments import AttachmentStorage
from sqlalchemy import func, select

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

    async def _unexpected_activation(*args: object, **kwargs: object) -> None:
        raise AssertionError("ready re-extraction must not activate attachments")

    async def _unexpected_archive(*args: object, **kwargs: object) -> None:
        raise AssertionError("ready re-extraction must not archive attachments")

    monkeypatch.setattr(
        "app.services.profile_approval.activate_selected_attachment",
        _unexpected_activation,
    )
    monkeypatch.setattr(
        "app.services.profile_approval.att_repo.mark_archived",
        _unexpected_archive,
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
                    profile_json=_valid_profile(
                        phone="+1 (202) 555-0147",
                        email="ready@example.test",
                        github_url="https://github.com/ready-user",
                    ).model_dump(mode="json"),
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
                old_preferences_revision = preference_row.updated_at
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert attachment is not None
                old_attachment_revision = attachment.updated_at
                await session.commit()
                profile_id = profile.id
                conversation_ids = {first.id, second.id}
                job_id = job.id

            async with factory() as session:
                before_counts: list[int | None] = []
                for model in (ChatMessage, AgentRun, ToolExecution, Conversation):
                    before_counts.append(
                        await session.scalar(
                            select(func.count()).select_from(model)
                        )
                    )

            coordinator = ProfileReextractionCoordinator(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                invoker=invoker,
                graph_driver=None,
            )
            events = [event async for event in coordinator.stream(profile_id)]
            assert [event.event for event in events] == [
                "reextract_progress",
                "reextract_progress",
                "reextract_progress",
                "reextract_progress",
                "reextract_review_ready",
            ]
            assert [
                event.payload.stage
                for event in events[:-1]
                if hasattr(event.payload, "stage")
            ] == [
                "validating_source",
                "extracting_document",
                "projecting_profile",
                "publishing_review",
            ]
            with pytest.raises(ProfileReextractError) as second_reextract:
                _ = [event async for event in coordinator.stream(profile_id)]
            assert second_reextract.value.code == "PROFILE_REVIEW_PENDING"
            review = await coordinator.get_review(profile_id)
            with pytest.raises(ProfileReextractError) as stale_discard:
                await coordinator.discard(
                    profile_id,
                    revision=datetime(2000, 1, 1, tzinfo=UTC),
                )
            assert stale_discard.value.code == "PROFILE_REEXTRACT_CONFLICT"
            await coordinator.discard(profile_id, revision=review.revision)
            async with factory() as session:
                assert await profile_repo.get_current_draft(session) is None
                assert await cv_doc_repo.get_draft(session, attachment_id) is None
            republished = [
                event async for event in coordinator.stream(profile_id)
            ]
            assert republished[-1].event == "reextract_review_ready"
            async with factory() as session:
                after_counts: list[int | None] = []
                for model in (ChatMessage, AgentRun, ToolExecution, Conversation):
                    after_counts.append(
                        await session.scalar(
                            select(func.count()).select_from(model)
                        )
                    )
                assert after_counts == before_counts
                draft = await profile_repo.get_current_draft(session)
                assert draft is not None
                original_draft_revision = draft.updated_at
                assert draft.target_profile_id == profile_id
                assert draft.draft_json["job_preferences"] == _preferences()
                approved_before_approval = await profile_repo.get_profile(
                    session, profile_id
                )
                assert approved_before_approval is not None
                assert approved_before_approval.profile_json["phone"] == "+12025550147"
                assert (
                    approved_before_approval.profile_json["email"]
                    == "ready@example.test"
                )
                assert (
                    approved_before_approval.profile_json["github_url"]
                    == "https://github.com/ready-user"
                )
                changed = dict(draft.draft_json)
                changed_profile = dict(changed["candidate_profile"])
                changed_profile["full_name"] = "Unsupported Person"
                changed["candidate_profile"] = changed_profile
                changed["job_preferences"] = {
                    "target_roles": ["Injected Draft Role"],
                    "preferred_locations": ["Injected Draft Location"],
                    "acceptable_work_modes": ["onsite"],
                    "target_seniority": ["junior"],
                }
                changed_draft = await profile_repo.upsert_current_draft(
                    session,
                    draft_json=changed,
                    source_attachment_id=attachment_id,
                    target_profile_id=profile_id,
                )
                await session.commit()

            async def no_sync() -> None:
                return None

            conflicted = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
                expected_profile_id=profile_id,
                expected_draft_updated_at=original_draft_revision,
            )
            assert conflicted.ok is False
            assert conflicted.code == "PROFILE_REEXTRACT_CONFLICT"

            approved = await commit_approved_draft(
                session_factory=factory,
                storage=storage,
                normalizer=_normalizer(),
                sync_fn=no_sync,
                expected_profile_id=profile_id,
                expected_draft_updated_at=changed_draft.updated_at,
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
                assert refreshed.display_name == "Ready"
                refreshed_revision = refreshed.updated_at.replace(tzinfo=None)
                assert refreshed_revision != old_revision.replace(tzinfo=None)
                assert refreshed.source_hash == document.source_hash
                assert refreshed.source_hash != "old-source-hash"
                assert refreshed.profile_json["full_name"] is None
                assert prefs.preferences_json == _preferences()
                assert prefs.updated_at.replace(
                    tzinfo=None
                ) == old_preferences_revision.replace(tzinfo=None)
                assert {item.id for item in conversations.rows} == conversation_ids
                assert await workspace_repo.get_active_profile_id(session) == profile_id
                attachment = await att_repo.get_by_id(session, attachment_id)
                assert attachment is not None
                assert attachment.state == "active"
                assert attachment.updated_at.replace(
                    tzinfo=None
                ) == old_attachment_revision.replace(tzinfo=None)
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
                expected_profile_id=new_uuid(),
            )
            assert result.ok is False
            assert result.code == "PROFILE_INCONSISTENT"
        finally:
            await engine.dispose()

    run_async(_body())

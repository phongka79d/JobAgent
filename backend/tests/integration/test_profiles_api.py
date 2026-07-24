from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from inspect import getsource
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_STAGED,
)
from app.db.session import get_session_factory
from app.repositories import agent_runs as runs_repo
from app.repositories import attachments as attachments_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import conversations as conversations_repo
from app.repositories import cv_documents as cv_documents_repo
from app.repositories import profiles as profiles_repo
from app.repositories import workspace_state as workspace_repo
from sqlalchemy import select, text

from tests.support.db_migration import run_async
from tests.support.health import FakeDriver, health_client


def _candidate(
    *, full_name: str | None = "Ada Lovelace", location: str | None = "Hanoi"
) -> dict[str, Any]:
    return {
        "full_name": full_name,
        "location": location,
        "summary": "Backend engineer",
        "current_title": "Engineer",
        "total_experience_years": 4.0,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": ["python3"],
                    "category": "language",
                },
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 4.0,
                "source": "cv",
                "excluded": False,
                "evidence": ["Python backend"],
            },
            {
                "skill": {
                    "canonical_key": "private-skill",
                    "display_name": "Private Skill",
                    "aliases": [],
                    "category": "other",
                },
                "confidence": 0.8,
                "proficiency": "unknown",
                "years": None,
                "source": "cv",
                "excluded": True,
                "evidence": ["Excluded by user"],
            },
        ],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.9,
    }


def _preferences() -> dict[str, Any]:
    return {
        "target_roles": ["Backend Engineer"],
        "preferred_locations": ["Remote"],
        "acceptable_work_modes": ["remote"],
        "target_seniority": ["mid"],
    }


def _document(attachment_id: str) -> dict[str, Any]:
    return {
        "attachment_id": attachment_id,
        "detected_languages": ["en"],
        "sections": [
            {
                "id": "summary",
                "ordinal": 0,
                "heading": "Summary",
                "kind": "summary",
                "entries": [
                    {
                        "id": "summary-0",
                        "ordinal": 0,
                        "title": None,
                        "subtitle": None,
                        "date_text": None,
                        "location": None,
                        "body": "Raw CV body sentinel",
                        "bullets": [],
                        "attributes": {},
                        "source_chunk_ordinals": [0],
                    }
                ],
                "source_chunk_ordinals": [0],
            }
        ],
        "extraction_warnings": [],
        "extraction_confidence": 0.9,
    }


async def _insert_attachment(
    *,
    attachment_id: str,
    state: str,
    original_name: str,
    marker: str,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        now = datetime(2026, 7, 23, tzinfo=UTC)
        await session.execute(
            text(
                "INSERT INTO attachments "
                "(id, file_hash, original_name, mime_type, size_bytes, page_count, "
                "storage_path, state, failure_code, created_at, updated_at) "
                "VALUES (:id, :hash, :name, 'application/pdf', 128, 1, :path, "
                ":state, NULL, :now, :now)"
            ),
            {
                "id": attachment_id,
                "hash": marker * 64,
                "name": original_name,
                "path": f"private/{marker}/raw-cv.pdf",
                "state": state,
                "now": now,
            },
        )
        await session.commit()


async def _create_profile(
    *,
    state: str,
    marker: str,
    display_name: str = "Ada Lovelace",
    full_name: str | None = "Ada Lovelace",
    location: str | None = "Hanoi",
    original_name: str = "ada.pdf",
) -> tuple[str, str, str]:
    attachment_id = new_uuid()
    await _insert_attachment(
        attachment_id=attachment_id,
        state=state,
        original_name=original_name,
        marker=marker,
    )
    factory = get_session_factory()
    async with factory() as session:
        profile_json = _candidate(full_name=full_name, location=location)
        profile = await profiles_repo.create_profile(
            session,
            attachment_id=attachment_id,
            display_name=display_name,
            profile_json=profile_json,
            location=location,
            extraction_version=f"extract-{marker}",
            source_hash=marker * 64,
        )
        await profiles_repo.upsert_profile_preferences(
            session,
            profile_id=profile.id,
            preferences_json=_preferences(),
        )
        await cv_documents_repo.upsert_document(
            session,
            attachment_id=attachment_id,
            document_json=_document(attachment_id),
            profile_json=profile_json,
            outline_json={"sections": ["summary"]},
            extraction_version=f"extract-{marker}",
            source_hash=marker * 64,
        )
        conversation = await conversations_repo.create_for_profile(
            session, profile_id=profile.id
        )
        await session.commit()
        return profile.id, attachment_id, conversation.id


async def _set_active(profile_id: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await workspace_repo.set_active_profile_id(session, profile_id)
        await session.commit()


def _seed_two_profiles() -> tuple[str, str, str, str, str, str]:
    async def seed() -> tuple[str, str, str, str, str, str]:
        first = await _create_profile(
            state=ATTACHMENT_STATE_ACTIVE,
            marker="a",
            display_name="Ada",
        )
        second = await _create_profile(
            state=ATTACHMENT_STATE_ARCHIVED,
            marker="b",
            display_name="Grace",
            full_name="Grace Hopper",
            location="New York",
            original_name="grace.pdf",
        )
        await _set_active(first[0])
        return (*first, *second)

    return run_async(seed())


def test_profile_list_and_detail_are_exact_safe_row_keyed_projections(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    del health_env

    async def seed() -> tuple[str, str]:
        profile_id, _attachment_id, conversation_id = await _create_profile(
            state=ATTACHMENT_STATE_ACTIVE,
            marker="c",
            display_name="temporary",
            full_name=None,
            location=None,
            original_name="../Ada CV.pdf",
        )
        factory = get_session_factory()
        async with factory() as session:
            profile = await profiles_repo.get_profile(session, profile_id)
            assert profile is not None
            profile.display_name = ""
            await session.commit()
        await _set_active(profile_id)
        return profile_id, conversation_id

    profile_id, conversation_id = run_async(seed())

    with health_client() as client:
        list_response = client.get("/api/profiles")
        detail_response = client.get(f"/api/profiles/{profile_id}")

    assert list_response.status_code == 200, list_response.text
    listed = list_response.json()
    assert set(listed) == {"items", "active_profile_id"}
    assert listed["active_profile_id"] == profile_id
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert set(item) == {
        "id",
        "display_name",
        "cv_filename",
        "attachment_state",
        "location",
        "skill_tags",
        "skill_count",
        "extraction_version",
        "source_hash",
        "state",
        "setup_status",
        "is_active",
        "created_at",
        "updated_at",
        "last_opened_at",
    }
    assert item["display_name"] == "Ada CV.pdf"
    assert item["cv_filename"] == "Ada CV.pdf"
    assert item["attachment_state"] == "active"
    assert item["skill_tags"] == [{"key": "python", "label": "Python"}]
    assert item["skill_count"] == 1
    assert item["setup_status"] is None
    assert item["is_active"] is True

    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert set(detail) == set(item) | {
        "profile",
        "preferences",
        "attachment",
        "selected_conversation_id",
    }
    assert detail["selected_conversation_id"] == conversation_id
    assert detail["profile"]["full_name"] is None
    assert detail["preferences"] == _preferences()
    assert set(detail["attachment"]) == {
        "id",
        "original_name",
        "mime_type",
        "size_bytes",
        "page_count",
        "state",
        "failure_code",
    }
    payload = detail_response.text
    for forbidden in (
        "storage_path",
        "private/c/raw-cv.pdf",
        "Raw CV body sentinel",
        "provider_payload",
        "api_key",
        "secret",
    ):
        assert forbidden not in payload


@pytest.mark.parametrize("corruption", ("document_revision", "attachment_state"))
def test_profile_projection_rejects_inconsistent_persisted_ownership(
    health_env: tuple[Path, Path, FakeDriver],
    corruption: str,
) -> None:
    del health_env
    profile_id, attachment_id, _conversation_id = run_async(
        _create_profile(
            state=ATTACHMENT_STATE_ACTIVE,
            marker="i",
            display_name="Inconsistent",
        )
    )
    run_async(_set_active(profile_id))

    async def corrupt() -> None:
        factory = get_session_factory()
        async with factory() as session:
            if corruption == "document_revision":
                document = await cv_documents_repo.get_document(
                    session, attachment_id
                )
                assert document is not None
                document.source_hash = "z" * 64
            else:
                attachment = await attachments_repo.get_by_id(
                    session, attachment_id
                )
                assert attachment is not None
                attachment.state = ATTACHMENT_STATE_STAGED
            await session.commit()

    run_async(corrupt())
    with health_client() as client:
        detail = client.get(f"/api/profiles/{profile_id}")
        listed = client.get("/api/profiles")

    for response in (detail, listed):
        assert response.status_code == 500
        assert response.json()["detail"] == {
            "code": "PROFILE_INCONSISTENT",
            "summary": "profile data is inconsistent",
        }


def test_profile_patch_is_strict_trimmed_and_rename_only(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    del health_env
    profile_id, attachment_id, _conversation_id = run_async(
        _create_profile(
            state=ATTACHMENT_STATE_ACTIVE,
            marker="d",
            display_name="Before",
        )
    )
    run_async(_set_active(profile_id))

    async def snapshot() -> tuple[Any, ...]:
        factory = get_session_factory()
        async with factory() as session:
            profile = await profiles_repo.get_profile(session, profile_id)
            prefs = await profiles_repo.get_profile_preferences(session, profile_id)
            attachment = await attachments_repo.get_by_id(session, attachment_id)
            assert profile is not None and prefs is not None and attachment is not None
            return (
                profile.attachment_id,
                profile.profile_json,
                profile.location,
                profile.extraction_version,
                profile.source_hash,
                profile.state,
                profile.created_at,
                profile.last_opened_at,
                prefs.preferences_json,
                attachment.state,
                attachment.storage_path,
            )

    before = run_async(snapshot())
    with health_client() as client:
        extra = client.patch(
            f"/api/profiles/{profile_id}",
            json={"display_name": "No", "profile": _candidate()},
        )
        blank = client.patch(
            f"/api/profiles/{profile_id}", json={"display_name": "   "}
        )
        too_long = client.patch(
            f"/api/profiles/{profile_id}", json={"display_name": "x" * 121}
        )
        padded_maximum = client.patch(
            f"/api/profiles/{profile_id}",
            json={"display_name": f"  {'y' * 120}  "},
        )
        renamed = client.patch(
            f"/api/profiles/{profile_id}", json={"display_name": "  After  "}
        )

    assert extra.status_code == 422
    assert blank.status_code == 422
    assert blank.json()["detail"] == {
        "code": "INVALID_DISPLAY_NAME",
        "summary": "display name must not be blank",
    }
    assert too_long.status_code == 422
    assert too_long.json()["detail"] == {
        "code": "INVALID_DISPLAY_NAME",
        "summary": "display name must be between 1 and 120 characters",
    }
    assert padded_maximum.status_code == 200
    assert padded_maximum.json()["display_name"] == "y" * 120
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "After"
    assert run_async(snapshot()) == before


def test_profile_routes_validate_uuid_and_delegate_activation_to_service(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    del health_env
    from app.api.profiles import activate_profile
    from app.services import profile_activation

    assert callable(profile_activation.refresh_profile_branch)

    source = getsource(activate_profile)
    assert "activate_profile_by_id" in source
    for forbidden in (
        "assert_workspace_idle",
        "activate_selected_attachment",
        "set_active_profile_id",
        "most_recent_for_profile",
        "session.commit",
    ):
        assert forbidden not in source

    with health_client() as client:
        assert client.get("/api/profiles/not-a-uuid").status_code == 422
        assert client.patch(
            "/api/profiles/not-a-uuid", json={"display_name": "Name"}
        ).status_code == 422
        assert client.post("/api/profiles/not-a-uuid/activate").status_code == 422


def test_profile_activation_maps_not_found_not_ready_and_activity_blocked(
    health_env: tuple[Path, Path, FakeDriver],
) -> None:
    del health_env
    (
        active_id,
        _active_attachment,
        active_conversation,
        target_id,
        target_attachment,
        _,
    ) = _seed_two_profiles()

    async def block_and_mark_not_ready() -> str:
        factory = get_session_factory()
        async with factory() as session:
            target = await profiles_repo.get_profile(session, target_id)
            attachment = await attachments_repo.get_by_id(
                session, target_attachment
            )
            assert target is not None and attachment is not None
            target.state = "deleting"
            attachment.state = "deleting"
            await session.commit()
        return active_id

    run_async(block_and_mark_not_ready())
    with health_client() as client:
        missing = client.post(f"/api/profiles/{new_uuid()}/activate")
        not_ready = client.post(f"/api/profiles/{target_id}/activate")
        listed = client.get("/api/profiles")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PROFILE_NOT_FOUND"
    assert not_ready.status_code == 409
    assert not_ready.json()["detail"]["code"] == "PROFILE_NOT_READY"
    assert listed.status_code == 200
    deleting_item = next(
        item for item in listed.json()["items"] if item["id"] == target_id
    )
    assert deleting_item["state"] == "deleting"
    assert deleting_item["attachment_state"] == "deleting"

    async def restore_and_block() -> None:
        factory = get_session_factory()
        async with factory() as session:
            target = await profiles_repo.get_profile(session, target_id)
            attachment = await attachments_repo.get_by_id(
                session, target_attachment
            )
            assert target is not None and attachment is not None
            target.state = "ready"
            attachment.state = "archived"
            message = await messages_repo.insert_message(
                session,
                conversation_id=active_conversation,
                role="user",
                content="keep current profile",
            )
            await runs_repo.create_run(session, user_message_id=message.id)
            await session.commit()

    run_async(restore_and_block())
    with health_client() as client:
        blocked = client.post(f"/api/profiles/{target_id}/activate")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "PROFILE_SWITCH_BLOCKED"


class _GraphResult:
    async def consume(self) -> None:
        return None


class _GraphSession:
    def __init__(self, driver: _CommitAwareDriver) -> None:
        self.driver = driver

    async def __aenter__(self) -> _GraphSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def run(
        self, query: str, parameters: dict[str, Any] | None = None, **kwargs: Any
    ) -> _GraphResult:
        del kwargs
        self.driver.queries.append((query, parameters))
        if self.driver.capture:
            factory = get_session_factory()
            async with factory() as session:
                active_id = await workspace_repo.get_active_profile_id(session)
                states = dict(
                    (
                        await session.execute(
                            select(
                                profiles_repo.Profile.id,
                                attachments_repo.Attachment.state,
                            ).join(
                                attachments_repo.Attachment,
                                profiles_repo.Profile.attachment_id
                                == attachments_repo.Attachment.id,
                            )
                        )
                    ).all()
                )
            self.driver.committed_snapshots.append((active_id, states))
        if self.driver.fail_sync and self.driver.capture:
            raise OSError("raw neo4j credential-like failure must stay private")
        return _GraphResult()


class _CommitAwareDriver:
    def __init__(self) -> None:
        self.capture = False
        self.fail_sync = False
        self.queries: list[tuple[str, dict[str, Any] | None]] = []
        self.committed_snapshots: list[tuple[str | None, dict[str, str]]] = []

    async def verify_connectivity(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def session(self, **config: Any) -> _GraphSession:
        del config
        return _GraphSession(self)


def _install_driver(
    monkeypatch: pytest.MonkeyPatch, driver: _CommitAwareDriver
) -> None:
    monkeypatch.setattr("app.main.open_driver", lambda _settings: driver)


def test_profile_activation_commits_then_refreshes_exact_graph_branch_without_work(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del health_env
    active_id, _active_attachment, _active_conversation, target_id, _, first = (
        _seed_two_profiles()
    )

    async def add_recent() -> str:
        factory = get_session_factory()
        async with factory() as session:
            older = await conversations_repo.get_owned(
                session, conversation_id=first
            )
            assert older is not None
            recent = await conversations_repo.create_for_profile(
                session, profile_id=target_id
            )
            base = datetime(2026, 7, 23, tzinfo=UTC)
            older.last_opened_at = base
            recent.last_opened_at = base + timedelta(minutes=1)
            await session.commit()
            return recent.id

    recent_id = run_async(add_recent())
    zero_call_spies = [Mock() for _ in range(5)]
    monkeypatch.setattr(
        "app.services.profile_extraction.extract_document_and_profile_from_chunks",
        zero_call_spies[0],
    )
    monkeypatch.setattr(
        "app.services.pdf_extraction.extract_pdf_text", zero_call_spies[1]
    )
    monkeypatch.setattr(
        "app.services.cv_document_extraction.ShopAIKeyStructuredCVDocumentInvoker.invoke_structured",
        zero_call_spies[2],
    )
    monkeypatch.setattr(
        "app.adapters.shopaikey_embeddings.ShopAIKeyEmbeddingAdapter.embed_texts",
        zero_call_spies[3],
    )
    monkeypatch.setattr(
        "app.services.match_scoring.score_single_job", zero_call_spies[4]
    )
    driver = _CommitAwareDriver()
    _install_driver(monkeypatch, driver)

    with health_client() as client:
        driver.queries.clear()
        driver.capture = True
        response = client.post(f"/api/profiles/{target_id}/activate")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"profile", "conversation", "warning"}
    assert body["profile"]["id"] == target_id
    assert body["conversation"]["id"] == recent_id
    assert body["conversation"]["is_selected"] is True
    assert body["warning"] is None
    assert driver.committed_snapshots
    assert all(snapshot[0] == target_id for snapshot in driver.committed_snapshots)
    assert all(
        snapshot[1][active_id] == ATTACHMENT_STATE_ARCHIVED
        and snapshot[1][target_id] == ATTACHMENT_STATE_ACTIVE
        for snapshot in driver.committed_snapshots
    )
    candidate_params = [
        params
        for query, params in driver.queries
        if "MERGE (c:Candidate" in query and params is not None
    ]
    cv_params = [
        params
        for query, params in driver.queries
        if "MERGE (cv:CV" in query and params is not None
    ]
    assert candidate_params[0]["profile_id"] == target_id
    assert cv_params[0]["profile_id"] == target_id
    for spy in zero_call_spies:
        spy.assert_not_called()


def test_profile_activation_graph_failure_warns_and_preserves_selection(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del health_env
    _active_id, _active_attachment, _active_conversation, target_id, _, _ = (
        _seed_two_profiles()
    )
    driver = _CommitAwareDriver()
    _install_driver(monkeypatch, driver)

    with health_client() as client:
        driver.capture = True
        driver.fail_sync = True
        response = client.post(f"/api/profiles/{target_id}/activate")

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["id"] == target_id
    assert body["warning"] == {
        "code": "NEO4J_SYNC_FAILED",
        "summary": (
            "Profile selection was saved, but its graph projection could not be "
            "refreshed."
        ),
        "guidance": (
            "Restore Neo4j connectivity and run the local graph rebuild command to "
            "reproject Candidate/Job/Skill data from SQLite."
        ),
    }
    assert "credential-like" not in response.text

    async def selected() -> tuple[str | None, str | None]:
        factory = get_session_factory()
        async with factory() as session:
            active = await workspace_repo.get_active_profile_id(session)
            row = await profiles_repo.get_profile(session, target_id)
            attachment = (
                await attachments_repo.get_by_id(session, row.attachment_id)
                if row is not None
                else None
            )
            return active, attachment.state if attachment is not None else None

    assert run_async(selected()) == (target_id, ATTACHMENT_STATE_ACTIVE)


def test_profile_reextract_uses_server_owned_attachment_and_conversation(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del health_env
    profile_id, attachment_id, conversation_id = run_async(
        _create_profile(
            state=ATTACHMENT_STATE_ACTIVE,
            marker="r",
            display_name="Reextract",
        )
    )
    run_async(_set_active(profile_id))
    captured: dict[str, Any] = {}

    async def fake_stream(**kwargs: Any) -> Any:
        from app.schemas.sse import build_sse_event

        captured.update(kwargs)
        run_id = new_uuid()
        yield build_sse_event(
            "run_started", run_id, {"state": "running", "resumed": False}
        )
        yield build_sse_event("run_completed", run_id, {"state": "completed"})

    monkeypatch.setattr("app.api.profiles.stream_cv_reprocess", fake_stream)
    with health_client() as client:
        response = client.post(f"/api/profiles/{profile_id}/reextract", json={})
        assert response.status_code == 200
        assert client.post(
            f"/api/profiles/{profile_id}/reextract",
            json={"attachment_id": attachment_id},
        ).status_code == 422
        assert client.post(f"/api/cvs/{attachment_id}/reprocess").status_code == 404

    assert captured["attachment_id"] == attachment_id
    assert captured["target_profile_id"] == profile_id
    assert captured["conversation_id"] == conversation_id


def test_exact_hash_archived_ready_upload_reuses_profile_without_external_work(
    health_env: tuple[Path, Path, FakeDriver],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.attachments import AttachmentStorage

    from tests.fakes.embeddings import FakeEmbeddingClient
    from tests.fakes.structured_output import ScriptedStructuredInvoker

    _db_path, files_dir, _driver = health_env
    pdf_path = (
        Path(__file__).resolve().parents[1] / "fixtures" / "cv" / "digital_cv_01.pdf"
    )
    pdf_bytes = pdf_path.read_bytes()
    provider = ScriptedStructuredInvoker()
    embedder = FakeEmbeddingClient()
    extractor = Mock(side_effect=AssertionError("extractor must not run"))
    scorer = Mock(side_effect=AssertionError("scorer must not run"))
    monkeypatch.setattr(
        "app.services.profile_drafts.extract_document_publication_from_pdf",
        extractor,
    )
    monkeypatch.setattr("app.services.matching.match_jobs", scorer)

    async def seed() -> tuple[str, str]:
        factory = get_session_factory()
        storage = AttachmentStorage(files_dir)
        attachment_id = new_uuid()
        rel = storage.write_bytes(attachment_id, pdf_bytes)
        async with factory() as session:
            await attachments_repo.create_staged(
                session,
                file_hash=hashlib.sha256(pdf_bytes).hexdigest(),
                original_name="archived.pdf",
                size_bytes=len(pdf_bytes),
                storage_path=rel,
                page_count=1,
                attachment_id=attachment_id,
            )
            await attachments_repo.mark_active(session, attachment_id)
            await attachments_repo.mark_archived(session, attachment_id)
            profile = await profiles_repo.create_profile(
                session,
                attachment_id=attachment_id,
                display_name="Archived Ready",
                profile_json=_candidate(),
                location="Hanoi",
                extraction_version="existing-v1",
                source_hash="existing-source",
            )
            await conversations_repo.create_for_profile(
                session, profile_id=profile.id
            )
            await session.commit()
            return attachment_id, profile.id

    attachment_id, profile_id = run_async(seed())
    with health_client() as client:
        response = client.post(
            "/api/attachments/cv",
            files={"file": ("same.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "existing_profile"
    assert body["attachment"]["id"] == attachment_id
    assert body["profile"]["profile_id"] == profile_id
    assert provider.call_count == 0
    assert embedder.call_count == 0
    extractor.assert_not_called()
    scorer.assert_not_called()

    async def assert_no_pending() -> None:
        factory = get_session_factory()
        async with factory() as session:
            assert await profiles_repo.get_incomplete_profile(session) is None

    run_async(assert_no_pending())

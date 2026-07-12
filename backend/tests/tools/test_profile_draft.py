"""Profile draft proposal tool behavior and state authorization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from app.repositories.preferences import PreferencesRepository
from app.repositories.profile_drafts import ProfileDraftRepository
from app.repositories.profiles import ProfileRepository
from app.schemas.profile_draft import ProfileDraftDocument, build_approval_summary
from app.services.cv_ingestion import CvIngestionError
from app.tools.profile_draft import (
    ProfileDraftToolService,
    create_profile_draft_tools,
)
from pydantic import ValidationError
from tests.tools.profile_tool_helpers import (
    active_attachment,
    preferences,
    profile,
    temporary_db,
)


class FakeCvProposal:
    def __init__(self, database: Any, attachment_id: UUID) -> None:
        self.database = database
        self.attachment_id = attachment_id
        self.calls: list[UUID] = []
        self.error: CvIngestionError | None = None

    async def propose_profile_from_cv(self, attachment_id: UUID) -> Any:
        self.calls.append(attachment_id)
        if self.error is not None:
            raise self.error
        async with self.database.session_scope() as session:
            proposed = profile("Proposed from CV")
            return await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=proposed,
                    approval_summary=build_approval_summary(proposed),
                ),
                source_attachment_id=self.attachment_id,
            )


def _approval_payload(value: str) -> dict[str, object]:
    assert value.startswith("APPROVAL_REQUIRED:")
    return json.loads(value.removeprefix("APPROVAL_REQUIRED:"))


@pytest.mark.asyncio
async def test_cv_proposal_creates_one_pending_draft_without_approved_write(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        propose_cv, _ = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        payload = _approval_payload(
            await propose_cv.ainvoke({"attachment_id": str(attachment_id)})
        )

        assert payload["kind"] == "approval_required"
        assert payload["draft_id"]
        assert fake.calls == [attachment_id]
        async with database.session_scope() as session:
            assert await ProfileRepository(session).get() is None
            assert await PreferencesRepository(session).get() is None
            assert await ProfileDraftRepository(session).get_pending() is not None


@pytest.mark.asyncio
async def test_cv_proposal_is_unavailable_while_draft_is_pending(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        async with database.session_scope() as session:
            await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=profile(),
                    approval_summary=build_approval_summary(profile()),
                ),
                source_attachment_id=attachment_id,
            )
        propose_cv, _ = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        result = await propose_cv.ainvoke({"attachment_id": str(attachment_id)})

        assert result == 'ERROR:{"code":"PROFILE_DRAFT_PENDING","ok":false}'
        assert fake.calls == []


@pytest.mark.asyncio
async def test_cv_failure_returns_only_stable_sanitized_code(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = uuid4()
        fake = FakeCvProposal(database, attachment_id)
        fake.error = CvIngestionError("INVALID_ATTACHMENT_STATE")
        propose_cv, _ = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        result = await propose_cv.ainvoke({"attachment_id": str(attachment_id)})

        assert result == 'ERROR:{"code":"INVALID_ATTACHMENT_STATE","ok":false}'


@pytest.mark.asyncio
async def test_update_reuses_same_pending_draft_and_never_writes_approved_state(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        async with database.session_scope() as session:
            original = profile("Original draft")
            draft = await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=original,
                    approval_summary=build_approval_summary(original),
                ),
                source_attachment_id=attachment_id,
            )
        _, propose_update = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        payload = _approval_payload(
            await propose_update.ainvoke(
                {
                    "draft_id": str(draft.id),
                    "profile": profile("Corrected draft").model_dump(mode="json"),
                    "preferences": preferences("Platform").model_dump(mode="json"),
                }
            )
        )

        assert payload["draft_id"] == str(draft.id)
        async with database.session_scope() as session:
            updated = await ProfileDraftRepository(session).get(draft.id)
            assert updated is not None
            assert updated.document.profile.summary == "Corrected draft"
            assert updated.document.preferences == preferences("Platform")
            assert await ProfileRepository(session).get() is None
            assert await PreferencesRepository(session).get() is None


@pytest.mark.asyncio
async def test_same_draft_update_preserves_existing_preference_proposal_when_omitted(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        original = profile("Original draft")
        async with database.session_scope() as session:
            draft = await ProfileDraftRepository(session).create(
                ProfileDraftDocument(
                    profile=original,
                    preferences=preferences("Platform"),
                    approval_summary=build_approval_summary(
                        original, preferences=preferences("Platform")
                    ),
                ),
                source_attachment_id=attachment_id,
            )
        _, propose_update = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        await propose_update.ainvoke(
            {
                "draft_id": str(draft.id),
                "profile": profile("Corrected only").model_dump(mode="json"),
            }
        )

        async with database.session_scope() as session:
            updated = await ProfileDraftRepository(session).get(draft.id)
            assert updated is not None
            assert updated.document.preferences == preferences("Platform")


@pytest.mark.asyncio
async def test_update_rejects_explicit_null_preferences(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        _, propose_update = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )
        with pytest.raises(ValidationError):
            await propose_update.ainvoke(
                {
                    "profile": profile().model_dump(mode="json"),
                    "preferences": None,
                }
            )


@pytest.mark.asyncio
async def test_update_from_active_context_creates_draft_with_active_source(
    tmp_path: Path,
) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        async with database.session_scope() as session:
            await ProfileRepository(session).replace(
                profile("Approved"), active_attachment_id=attachment_id
            )
            await PreferencesRepository(session).replace(preferences("Backend"))
        _, propose_update = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )

        payload = _approval_payload(
            await propose_update.ainvoke(
                {
                    "profile": profile("Active correction").model_dump(mode="json"),
                    "preferences": preferences("Platform").model_dump(mode="json"),
                }
            )
        )

        async with database.session_scope() as session:
            draft = await ProfileDraftRepository(session).get(UUID(str(payload["draft_id"])))
            assert draft is not None
            assert draft.source_attachment_id == attachment_id
            approved = await ProfileRepository(session).get()
            assert approved is not None and approved.profile.summary == "Approved"
            assert await PreferencesRepository(session).get() == preferences("Backend")


@pytest.mark.asyncio
async def test_stale_draft_id_fails_closed(tmp_path: Path) -> None:
    async with temporary_db(tmp_path) as database:
        attachment_id = await active_attachment(database)
        fake = FakeCvProposal(database, attachment_id)
        _, propose_update = create_profile_draft_tools(
            ProfileDraftToolService(database, fake)
        )
        result = await propose_update.ainvoke(
            {
                "draft_id": str(uuid4()),
                "profile": profile().model_dump(mode="json"),
            }
        )
        assert result == 'ERROR:{"code":"PROFILE_DRAFT_NOT_FOUND","ok":false}'

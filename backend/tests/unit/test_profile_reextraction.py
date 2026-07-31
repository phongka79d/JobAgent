from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from app.schemas.profile import CandidateProfile
from app.schemas.profile_reextraction import (
    ProfileReextractEvent,
    ProfileReextractProgress,
    ProfileReextractReviewReady,
)
from app.services.profile_reextraction import (
    ProfileReextractError,
    ProfileReextractionCoordinator,
    build_review,
)
from pydantic import ValidationError

PROFILE_ID = "11111111-1111-4111-8111-111111111111"
EVENT_ID = "22222222-2222-4222-8222-222222222222"
OPERATION_ID = "33333333-3333-4333-8333-333333333333"
REVISION = datetime(2026, 7, 28, 10, tzinfo=UTC)


def _profile(**overrides: object) -> CandidateProfile:
    payload: dict[str, object] = {
        "full_name": "Alex Example",
        "location": "Da Nang",
        "phone": "+84 901 234 567",
        "email": "alex@example.com",
        "github_url": "https://github.com/alex-example",
        "summary": "Backend engineer",
        "current_title": "Software Engineer",
        "total_experience_years": 5,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": [],
                    "category": "language",
                },
                "confidence": 0.9,
                "proficiency": "advanced",
                "years": 5,
                "source": "cv",
                "excluded": False,
                "evidence": ["Built Python APIs"],
            }
        ],
        "experiences": [],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.8,
    }
    payload.update(overrides)
    return CandidateProfile.model_validate(payload)


def test_build_review_projects_scalar_skill_collection_and_confidence_deltas() -> None:
    current = _profile()
    proposed = _profile(
        summary="Senior backend engineer",
        skills=[
            {
                "skill": {
                    "canonical_key": "fastapi",
                    "display_name": "FastAPI",
                    "aliases": [],
                    "category": "framework",
                },
                "confidence": 0.85,
                "proficiency": "advanced",
                "years": 4,
                "source": "cv",
                "excluded": False,
                "evidence": ["Built FastAPI services"],
            }
        ],
        experiences=[
            {
                "title": "Senior Engineer",
                "company": "Acme",
                "start_date_text": "2022",
                "end_date_text": "present",
                "summary": "Built APIs",
            }
        ],
        extraction_confidence=0.9,
    )

    review = build_review(
        current=current,
        proposed=proposed,
        profile_id=PROFILE_ID,
        revision=REVISION,
    )

    assert [
        (change.field, change.before, change.after) for change in review.changed_fields
    ] == [("summary", "Backend engineer", "Senior backend engineer")]
    assert review.skills_added == ["FastAPI"]
    assert review.skills_removed == ["Python"]
    assert review.collection_deltas.experiences == 1
    assert review.collection_deltas.education == 0
    assert review.collection_deltas.languages == 0
    assert review.collection_deltas.certifications == 0
    assert review.extraction_confidence is not None
    assert review.extraction_confidence.before == 0.8
    assert review.extraction_confidence.after == 0.9
    assert review.can_approve is True
    assert review.can_discard is True


def test_build_review_is_bounded_and_contains_no_private_provider_fields() -> None:
    current = _profile()
    proposed = _profile(
        summary="x" * 600,
        skills=[
            {
                "skill": {
                    "canonical_key": f"skill_{index}",
                    "display_name": f"Skill {index}",
                    "aliases": [],
                    "category": None,
                },
                "confidence": 0.8,
                "proficiency": "unknown",
                "years": None,
                "source": "cv",
                "excluded": False,
                "evidence": ["bounded evidence"],
            }
            for index in range(50)
        ],
    )

    encoded = build_review(
        current=current,
        proposed=proposed,
        profile_id=PROFILE_ID,
        revision=REVISION,
    ).model_dump_json()

    for forbidden in (
        "raw_text",
        "storage_path",
        "source_attachment_id",
        "fact_id",
        "provider",
    ):
        assert forbidden not in encoded


def test_profile_reextract_event_rejects_mismatched_payload() -> None:
    with pytest.raises(ValidationError):
        ProfileReextractEvent(
            event_id=EVENT_ID,
            operation_id=OPERATION_ID,
            profile_id=PROFILE_ID,
            timestamp=REVISION,
            event="reextract_progress",
            payload=ProfileReextractReviewReady(revision=REVISION),
        )

    event = ProfileReextractEvent(
        event_id=EVENT_ID,
        operation_id=OPERATION_ID,
        profile_id=PROFILE_ID,
        timestamp=REVISION,
        event="reextract_progress",
        payload=ProfileReextractProgress(
            stage="validating_source",
            message="Validating retained CV",
        ),
    )
    assert event.event == "reextract_progress"


@pytest.mark.asyncio
async def test_stream_claims_before_first_event_or_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class TestCoordinator(ProfileReextractionCoordinator):
        async def _claim(self, profile_id: str) -> Any:
            calls.append("claim")
            return SimpleNamespace(
                operation_id=OPERATION_ID,
                profile_id=profile_id,
                attachment_id="attachment",
                storage_path="attachment.pdf",
            )

    async def stage(**_kwargs: Any) -> None:
        calls.append("provider")

    monkeypatch.setattr("app.services.profile_reextraction.stage_cv_document", stage)
    coordinator = TestCoordinator(
        session_factory=object(),  # type: ignore[arg-type]
        storage=object(),  # type: ignore[arg-type]
        normalizer=object(),  # type: ignore[arg-type]
        invoker=object(),
    )
    stream = coordinator.stream(PROFILE_ID)
    first = await anext(stream)
    assert first.operation_id == OPERATION_ID
    assert calls == ["claim"]


@pytest.mark.asyncio
async def test_cancelled_stream_persists_interrupted_after_session_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False
    transitioned = False

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            nonlocal closed
            closed = True

    class TestCoordinator(ProfileReextractionCoordinator):
        async def _claim(self, profile_id: str) -> Any:
            return SimpleNamespace(
                operation_id=OPERATION_ID,
                profile_id=profile_id,
                attachment_id="attachment",
                storage_path="attachment.pdf",
            )

    async def transition(*_args: Any, **_kwargs: Any) -> bool:
        nonlocal transitioned
        assert closed is False
        transitioned = True
        return True

    monkeypatch.setattr(
        "app.services.profile_reextraction.operation_repo.transition_running_operation",
        transition,
    )
    monkeypatch.setattr(
        "app.services.profile_reextraction.session_scope",
        lambda _factory: FakeSession(),
    )
    coordinator = TestCoordinator(
        session_factory=object(),  # type: ignore[arg-type]
        storage=object(),  # type: ignore[arg-type]
        normalizer=object(),  # type: ignore[arg-type]
        invoker=object(),
    )
    stream = coordinator.stream(PROFILE_ID)
    await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    assert transitioned is True
    assert closed is True


@pytest.mark.asyncio
async def test_claim_maps_immediate_busy_to_retryable_profile_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BusyScope:
        async def __aenter__(self) -> Any:
            from app.db.session import ImmediateTransactionBusy

            raise ImmediateTransactionBusy

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        "app.services.profile_reextraction.immediate_session_scope",
        lambda _factory: BusyScope(),
    )
    coordinator = ProfileReextractionCoordinator(
        session_factory=object(),  # type: ignore[arg-type]
        storage=object(),  # type: ignore[arg-type]
        normalizer=object(),  # type: ignore[arg-type]
        invoker=object(),
    )
    with pytest.raises(ProfileReextractError) as caught:
        await coordinator._claim(PROFILE_ID)
    assert caught.value.code == "PROFILE_LIFECYCLE_BUSY"
    assert caught.value.operation_id is None

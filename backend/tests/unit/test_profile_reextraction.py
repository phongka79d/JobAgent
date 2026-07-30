from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from app.schemas.profile import CandidateProfile
from app.schemas.profile_reextraction import (
    ProfileReextractEvent,
    ProfileReextractProgress,
    ProfileReextractReviewReady,
)
from app.services.profile_reextraction import (
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
async def test_stream_propagates_cancellation_before_draft_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TestCoordinator(ProfileReextractionCoordinator):
        async def _preflight(self, profile_id: str) -> str:
            assert profile_id == PROFILE_ID
            return "44444444-4444-4444-8444-444444444444"

    async def cancelled(**_kwargs: Any) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(
        "app.services.profile_reextraction.propose_profile_from_cv",
        cancelled,
    )
    coordinator = TestCoordinator(
        session_factory=object(),  # type: ignore[arg-type]
        storage=object(),  # type: ignore[arg-type]
        normalizer=object(),  # type: ignore[arg-type]
        invoker=object(),
    )
    stream = coordinator.stream(PROFILE_ID)
    assert (await anext(stream)).event == "reextract_progress"
    assert (await anext(stream)).event == "reextract_progress"
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)

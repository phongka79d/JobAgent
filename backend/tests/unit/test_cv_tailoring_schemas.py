"""Strict durable and provider-facing CV tailoring contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.schemas.cv_tailoring import (
    TAILORING_TEMPLATE_VERSION,
    CreateTailoringAiVersionRequest,
    CreateTailoringSessionRequest,
    SourceBoundText,
    TailoredAttribute,
    TailoredCVContent,
    TailoredHeaderSnapshot,
    TailoredItem,
    TailoredSection,
    TailoringSourceRevision,
    TailoringVersionMutationResponse,
    parse_tailored_content,
    tailored_content_equal,
)
from app.schemas.sse import RunCompletedPayload
from pydantic import ValidationError


def _text(value: str = "Synthetic fact", *fact_ids: str) -> SourceBoundText:
    return SourceBoundText(text=value, source_fact_ids=list(fact_ids))


def _item(item_id: str = "entry-1") -> TailoredItem:
    return TailoredItem(
        id=item_id,
        source_entry_id=item_id,
        title=None,
        subtitle=None,
        date_text=None,
        location=None,
        body=_text("Synthetic fact", "sf_11111111111111111111111111111111"),
        bullets=[],
        attributes=[
            TailoredAttribute(
                name="tools",
                values=[_text("Python", "sf_22222222222222222222222222222222")],
            )
        ],
    )


def _content() -> TailoredCVContent:
    return TailoredCVContent(
        header=TailoredHeaderSnapshot(
            full_name="Synthetic Candidate",
            location=None,
            phone=None,
            email=None,
            github_url=None,
        ),
        sections=[
            TailoredSection(
                id="section-1",
                ordinal=0,
                heading="Summary",
                kind="summary",
                items=[_item()],
            )
        ],
    )


def test_tailored_content_round_trips_and_models_are_strict() -> None:
    content = _content()
    assert parse_tailored_content(content.model_dump(mode="json")) == content
    with pytest.raises(ValidationError):
        TailoredCVContent.model_validate(
            {**content.model_dump(mode="json"), "latex": "forbidden"}
        )


def test_canonical_content_equality_and_mutation_terminal_identity_are_coupled() -> None:
    content = _content()
    assert tailored_content_equal(content, content.model_copy(deep=True))
    response = TailoringVersionMutationResponse(
        outcome="no_change",
        session_id="11111111-1111-4111-8111-111111111111",
        version_id="22222222-2222-4222-8222-222222222222",
        version_number=2,
    )
    assert response.outcome == "no_change"
    chat_terminal = RunCompletedPayload(state="completed")
    assert chat_terminal.model_dump(mode="json") == {"state": "completed"}
    RunCompletedPayload(
        state="completed",
        outcome="no_change",
        version_id=response.version_id,
        version_number=response.version_number,
    )
    with pytest.raises(ValidationError):
        RunCompletedPayload(state="completed", outcome="no_change")
    with pytest.raises(ValidationError):
        RunCompletedPayload(
            state="completed",
            version_id=response.version_id,
            version_number=response.version_number,
        )


def test_source_fact_ids_are_nonempty_unique_and_bounded() -> None:
    with pytest.raises(ValidationError):
        SourceBoundText(text="x", source_fact_ids=[""])
    with pytest.raises(ValidationError):
        SourceBoundText(text="x", source_fact_ids=["sf_a", "sf_a"])
    with pytest.raises(ValidationError):
        SourceBoundText(text="x" * 4_001, source_fact_ids=[])


def test_section_identity_is_unique_and_contiguous() -> None:
    section = _content().sections[0]
    with pytest.raises(ValidationError):
        TailoredCVContent(
            header=_content().header,
            sections=[section, section.model_copy(update={"ordinal": 1})],
        )
    with pytest.raises(ValidationError):
        TailoredCVContent(
            header=_content().header,
            sections=[section.model_copy(update={"ordinal": 1})],
        )


def test_header_requires_name_and_validates_optional_github() -> None:
    with pytest.raises(ValidationError):
        TailoredHeaderSnapshot(full_name="", github_url=None)
    with pytest.raises(ValidationError):
        TailoredHeaderSnapshot(
            full_name="Synthetic Candidate",
            github_url="https://github.com/sample/repository",
        )


def test_request_shapes_enforce_initial_and_scoped_ai_contracts() -> None:
    with pytest.raises(ValidationError):
        CreateTailoringSessionRequest(job_id=None, instruction="   ")
    request = CreateTailoringSessionRequest(job_id=None, instruction="  concise  ")
    assert request.instruction == "concise"

    with pytest.raises(ValidationError):
        CreateTailoringAiVersionRequest(
            parent_version_id=None,
            instruction="retry",
            target_section_ids=["section-1"],
        )
    with pytest.raises(ValidationError):
        CreateTailoringAiVersionRequest(
            parent_version_id="11111111-1111-4111-8111-111111111111",
            instruction="",
            target_section_ids=["section-1"],
        )


def test_source_revision_uses_frozen_template_literal_and_aware_times() -> None:
    source = TailoringSourceRevision(
        profile_updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_hash="revision-a",
        job_updated_at=None,
        template_version=TAILORING_TEMPLATE_VERSION,
    )
    assert source.template_version == "latex-cv-v1"
    with pytest.raises(ValidationError):
        TailoringSourceRevision(
            profile_updated_at=datetime(2026, 1, 1),
            source_hash="revision-a",
            job_updated_at=None,
            template_version="latex-cv-v2",
        )

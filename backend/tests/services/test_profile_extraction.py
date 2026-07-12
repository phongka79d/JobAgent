from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.db.models.attachments import Attachment
from app.db.session import create_session_manager
from app.repositories.profile_drafts import ProfileDraftRepository
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.cv_ingestion import CvIngestionError, CvIngestionService
from app.services.shopaikey_chat import ShopAIKeyChatAdapter
from tests.fakes.profile_extraction import StructuredFactory

CONTACT_EMAIL = "unique-contact-sentinel@example.test"
CONTACT_PHONE = "+1 555 010 0199"
ADDRESS = "Address: 99 Unique Sentinel Street"


def _payload(*, evidence: str = "Python 2020-2024") -> dict[str, object]:
    return {
        "summary": "Backend engineer with Python experience.",
        "current_title": "Backend Engineer",
        "total_experience_years": 4,
        "skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": [],
                    "category": None,
                    "status": "provisional",
                    "confidence": 0.9,
                    "evidence": [evidence],
                },
                "proficiency": "advanced",
                "years": 4,
                "source": "cv",
                "excluded": False,
                "evidence": [evidence],
            }
        ],
        "experiences": [
            {
                "title": "Backend Engineer",
                "organization": "Example Co",
                "date_range": "2020-2024",
                "summary": "Built Python services.",
                "evidence": ["Backend Engineer 2020-2024"],
            }
        ],
        "education": [],
        "languages": [],
        "extraction_confidence": 0.9,
    }


def _missing_skill_evidence_payload() -> dict[str, object]:
    payload = _payload()
    skills = payload["skills"]
    assert isinstance(skills, list)
    assert isinstance(skills[0], dict)
    skill = skills[0]["skill"]
    assert isinstance(skill, dict)
    skill["evidence"] = []
    return payload


async def _service(
    tmp_path: Path, responses: list[object], *, attachment_state: str = "staged"
) -> tuple[CvIngestionService, StructuredFactory, UUID, object]:
    db = create_session_manager(tmp_path / "profile_extraction.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    source_text = (
        f"{CONTACT_EMAIL}\n{CONTACT_PHONE}\n{ADDRESS}\n"
        "Backend Engineer 2020-2024\nPython 2020-2024\n"
    )
    staged = await storage.stage(
        attachment_id, _chunks(b"%PDF-not-read-by-monkeypatch")
    )
    storage_path = staged.storage_path
    if attachment_state == "active":
        storage_path = await storage.promote(storage_path)
    async with db.session_scope() as session:
        session.add(
            Attachment(
                id=attachment_id,
                file_hash=uuid4().hex,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=staged.size_bytes,
                storage_path=storage_path,
                state=attachment_state,
            )
        )
    factory = StructuredFactory(responses)
    adapter = ShopAIKeyChatAdapter(
        base_url="https://provider.invalid/v1",
        api_key="test-key",
        model="gpt-4o-mini",
        model_factory=factory,
    )
    service = CvIngestionService(
        db,
        storage,
        max_size_bytes=10_000,
        max_pages=10,
        profile_adapter=adapter,
    )
    return service, factory, attachment_id, (db, source_text)


async def _chunks(payload: bytes):
    yield payload


@pytest.mark.asyncio
async def test_redacted_cv_creates_normalized_pending_draft_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload()
    skills = payload["skills"]
    assert isinstance(skills, list) and isinstance(skills[0], dict)
    skills[0]["excluded"] = True
    service, factory, attachment_id, state = await _service(tmp_path, [payload])
    db, source_text = state
    monkeypatch.setattr("app.services.cv_ingestion.extract_pdf_text", lambda *_args, **_kwargs: _pdf_text(source_text))

    result = await service.propose_profile_from_cv(attachment_id)

    assert result.source_attachment_id == attachment_id
    assert result.document.preferences is None
    assert result.document.profile.skills[0].skill.canonical_key == "python"
    assert result.document.profile.skills[0].excluded is True
    assert len(factory.model.structured_calls) == 1
    request = repr(factory.model.structured_calls[0])
    draft = result.document.to_storage_dict()
    assert all(token not in request for token in (CONTACT_EMAIL, CONTACT_PHONE, ADDRESS))
    assert all(token not in repr(draft) for token in (CONTACT_EMAIL, CONTACT_PHONE, ADDRESS))
    async with db.session_scope() as session:
        stored = await ProfileDraftRepository(session).get(result.id)
        assert stored is not None
        attachment = await session.get(Attachment, attachment_id)
        assert attachment is not None and attachment.state == "staged"
    await db.dispose()


@pytest.mark.asyncio
async def test_invalid_schema_is_repaired_once_before_draft_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = _payload()
    invalid["skills"] = "not-a-list"
    service, factory, attachment_id, state = await _service(tmp_path, [invalid, _payload()])
    db, source_text = state
    monkeypatch.setattr("app.services.cv_ingestion.extract_pdf_text", lambda *_args, **_kwargs: _pdf_text(source_text))

    result = await service.propose_profile_from_cv(attachment_id)

    assert result.id
    assert len(factory.model.structured_calls) == 2
    await db.dispose()


@pytest.mark.asyncio
async def test_active_attachment_remains_valid_draft_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _factory, attachment_id, state = await _service(
        tmp_path, [_payload()], attachment_state="active"
    )
    db, source_text = state
    monkeypatch.setattr("app.services.cv_ingestion.extract_pdf_text", lambda *_args, **_kwargs: _pdf_text(source_text))

    result = await service.propose_profile_from_cv(attachment_id)

    assert result.source_attachment_id == attachment_id
    async with db.session_scope() as session:
        attachment = await session.get(Attachment, attachment_id)
        assert attachment is not None and attachment.state == "active"
    await db.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "responses, expected_code",
    [
        ([_payload(evidence="invented 2020"), _payload(evidence="still invented 2021")], "PROFILE_EVIDENCE_INVALID"),
        ([_missing_skill_evidence_payload()], "PROFILE_EVIDENCE_INVALID"),
        ([RuntimeError("provider failed")], "shopaikey_provider_error"),
        ([{"summary": "bad"}, {"summary": "still bad"}], "shopaikey_schema_invalid"),
        ([_payload(evidence="Python"), _payload(evidence="Python")], "shopaikey_schema_invalid"),
    ],
)
async def test_invalid_or_provider_output_creates_no_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    responses: list[object],
    expected_code: str,
) -> None:
    service, factory, attachment_id, state = await _service(tmp_path, responses)
    db, source_text = state
    monkeypatch.setattr("app.services.cv_ingestion.extract_pdf_text", lambda *_args, **_kwargs: _pdf_text(source_text))

    with pytest.raises(CvIngestionError) as raised:
        await service.propose_profile_from_cv(attachment_id)

    assert raised.value.code == expected_code
    request = repr(factory.model.structured_calls[0])
    safe_surfaces = "\n".join((request, str(raised.value), caplog.text))
    assert all(token not in safe_surfaces for token in (CONTACT_EMAIL, CONTACT_PHONE, ADDRESS))
    async with db.session_scope() as session:
        assert await ProfileDraftRepository(session).get_pending() is None
    if expected_code == "shopaikey_schema_invalid":
        assert len(factory.model.structured_calls) == 2
    await db.dispose()


def _pdf_text(text: str):
    from app.services.pdf_text import PdfTextResult

    return PdfTextResult(page_count=1, text=text, usable_character_count=len(text))

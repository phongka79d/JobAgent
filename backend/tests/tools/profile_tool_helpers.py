"""Shared fixtures for Candidate profile tool tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from app.db.session import DatabaseSessionManager, create_session_manager
from app.repositories.attachments import AttachmentRepository, StagedAttachmentInput
from app.schemas.candidate import CandidateProfile
from app.schemas.preferences import JobPreferences


@asynccontextmanager
async def temporary_db(tmp_path: Path) -> AsyncIterator[DatabaseSessionManager]:
    database = create_session_manager(tmp_path / "profile-tools.db")
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


def profile(summary: str = "Backend engineer") -> CandidateProfile:
    return CandidateProfile.model_validate(
        {
            "summary": summary,
            "current_title": "Engineer",
            "total_experience_years": None,
            "skills": [],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.8,
        }
    )


def preferences(role: str = "Backend") -> JobPreferences:
    return JobPreferences.model_validate(
        {
            "target_roles": [role],
            "preferred_locations": ["Remote"],
            "acceptable_work_modes": ["remote"],
            "target_seniority": ["mid"],
        }
    )


async def active_attachment(database: DatabaseSessionManager) -> UUID:
    attachment_id = uuid4()
    async with database.session_scope() as session:
        repository = AttachmentRepository(session)
        await repository.add_staged(
            StagedAttachmentInput(
                id=attachment_id,
                file_hash=attachment_id.hex,
                original_name="cv.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                storage_path=f"staged/{attachment_id}",
                page_count=1,
            )
        )
        await repository.mark_active(
            attachment_id,
            storage_path=f"active/{attachment_id}",
        )
    return attachment_id

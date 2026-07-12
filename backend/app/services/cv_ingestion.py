"""Validated, deduplicating CV upload intake."""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from uuid import UUID, uuid4

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.db.enums import AttachmentState
from app.db.models.attachments import Attachment
from app.db.session import DatabaseSessionManager
from app.repositories.attachments import (
    AttachmentDuplicateError,
    AttachmentRepository,
    StagedAttachmentInput,
    require_canonical_service_path,
)
from app.repositories.profile_drafts import ProfileDraftRecord, ProfileDraftRepository
from app.schemas.candidate import CandidateProfile
from app.services.attachment_storage import AttachmentStorage, AttachmentStorageError
from app.services.pdf_text import PdfTextError, extract_pdf_text
from app.services.pii_redaction import PiiRedactionError, redact_pii
from app.services.profile_extraction import (
    ProfileExtractionError,
    build_cv_extraction_messages,
    build_profile_draft,
)
from app.services.shopaikey_chat import ShopAIKeyChatAdapter, ShopAIKeyChatError


class CvIngestionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StagedCvResult:
    id: UUID
    original_name: str
    mime_type: str
    size_bytes: int
    page_count: int
    state: str


class CvIngestionService:
    def __init__(
        self,
        db: DatabaseSessionManager,
        storage: AttachmentStorage,
        *,
        max_size_bytes: int,
        max_pages: int,
        profile_adapter: ShopAIKeyChatAdapter | None = None,
    ) -> None:
        self._db = db
        self._storage = storage
        self._max_size_bytes = max_size_bytes
        self._max_pages = max_pages
        self._profile_adapter = profile_adapter

    async def intake(self, original_name: str, mime_type: str, content: AsyncIterator[bytes]) -> StagedCvResult:
        if mime_type.lower().split(";", 1)[0].strip() != "application/pdf":
            raise CvIngestionError("UNSUPPORTED_MEDIA_TYPE")
        attachment_id = uuid4()
        digest = hashlib.sha256()
        prefix = bytearray()
        total = 0

        async def validated() -> AsyncIterator[bytes]:
            nonlocal total
            async for chunk in content:
                total += len(chunk)
                if total > self._max_size_bytes:
                    raise CvIngestionError("PDF_TOO_LARGE")
                if len(prefix) < 5:
                    prefix.extend(chunk[: 5 - len(prefix)])
                    if len(prefix) == 5 and bytes(prefix) != b"%PDF-":
                        raise CvIngestionError("INVALID_PDF_MAGIC")
                digest.update(chunk)
                yield chunk
            if bytes(prefix) != b"%PDF-":
                raise CvIngestionError("INVALID_PDF_MAGIC")

        stored = await self._storage.stage(attachment_id, validated())
        try:
            pdf_bytes = await self._read_all(stored.storage_path)
            try:
                page_count = len(PdfReader(BytesIO(pdf_bytes), strict=False).pages)
            except (PdfReadError, ValueError, OSError):
                raise CvIngestionError("MALFORMED_PDF") from None
            if page_count > self._max_pages:
                raise CvIngestionError("PDF_PAGE_LIMIT_EXCEEDED")
            safe_name = PurePath(original_name.replace("\\", "/")).name or "cv.pdf"
            file_hash = digest.hexdigest()
            async with self._db.session_scope() as session:
                repo = AttachmentRepository(session)
                duplicate = await repo.get_by_hash(file_hash)
                if duplicate is not None:
                    if await self._valid_duplicate(duplicate):
                        await self._storage.delete(stored.storage_path)
                        return self._result(duplicate)
                    await repo.delete(duplicate.id)
                try:
                    row = await repo.add_staged(StagedAttachmentInput(id=attachment_id, file_hash=file_hash, original_name=safe_name, mime_type="application/pdf", size_bytes=stored.size_bytes, storage_path=stored.storage_path, page_count=page_count))
                except AttachmentDuplicateError:
                    raise
                return self._result(row)
        except AttachmentDuplicateError:
            await self._storage.delete(stored.storage_path)
            await asyncio.sleep(0)
            async with self._db.session_scope() as session:
                duplicate = await AttachmentRepository(session).get_by_hash(digest.hexdigest())
                if duplicate is not None and await self._valid_duplicate(duplicate):
                    return self._result(duplicate)
            raise CvIngestionError("UPLOAD_CONFLICT") from None
        except BaseException:
            try:
                await self._storage.delete(stored.storage_path)
            except AttachmentStorageError:
                pass
            raise

    async def propose_profile_from_cv(
        self, attachment_id: UUID
    ) -> ProfileDraftRecord:
        """Turn one staged/active CV into a pending profile draft only.

        Pipeline order remains here: validate attachment, layout extraction,
        deterministic redaction, locked structured extraction, normalization,
        and one transactional draft insert. The adapter owns its single repair
        ceiling; this method deliberately never retries structured output.
        """
        if self._profile_adapter is None:
            raise CvIngestionError("PROFILE_EXTRACTION_NOT_CONFIGURED")

        storage_path = await self._valid_attachment_path(attachment_id)
        try:
            raw_pdf = await self._read_all(storage_path)
            extracted = extract_pdf_text(raw_pdf, max_pages=self._max_pages)
            redacted = redact_pii(extracted.text)
        except PdfTextError as exc:
            raise CvIngestionError(exc.code.value) from None
        except PiiRedactionError as exc:
            raise CvIngestionError(exc.code.value) from None

        try:
            profile = self._profile_adapter.invoke_structured(
                CandidateProfile,
                build_cv_extraction_messages(redacted.text),
            )
            draft = build_profile_draft(profile, redacted_text=redacted.text)
        except ShopAIKeyChatError as exc:
            raise CvIngestionError(exc.code.value) from None
        except ProfileExtractionError as exc:
            raise CvIngestionError(exc.code.value) from None

        # The attachment must still be a valid source at the write boundary;
        # neither approved state nor attachment state changes in this task.
        async with self._db.session_scope() as session:
            attachment = await AttachmentRepository(session).get_by_id(attachment_id)
            if attachment is None or not self._is_valid_attachment(attachment):
                raise CvIngestionError("INVALID_ATTACHMENT_STATE")
            return await ProfileDraftRepository(session).create(
                draft,
                source_attachment_id=attachment_id,
            )

    async def _read_all(self, storage_path: str) -> bytes:
        parts: list[bytes] = []
        stream = await self._storage.open(storage_path)
        async for chunk in stream:
            parts.append(chunk)
        return b"".join(parts)

    async def _valid_attachment_path(self, attachment_id: UUID) -> str:
        async with self._db.session_scope() as session:
            attachment = await AttachmentRepository(session).get_by_id(attachment_id)
            if attachment is None or not self._is_valid_attachment(attachment):
                raise CvIngestionError("INVALID_ATTACHMENT_STATE")
            return str(attachment.storage_path)

    @staticmethod
    def _is_valid_attachment(attachment: Attachment) -> bool:
        state = str(attachment.state)
        if state not in {AttachmentState.STAGED.value, AttachmentState.ACTIVE.value}:
            return False
        try:
            require_canonical_service_path(
                str(attachment.storage_path), attachment.id, expected_area=state
            )
        except Exception:
            return False
        return True

    async def _valid_duplicate(self, row: Attachment) -> bool:
        try:
            state = str(row.state)
            require_canonical_service_path(str(row.storage_path), row.id, expected_area=state)
            await self._read_all(str(row.storage_path))
            return state in {AttachmentState.STAGED.value, AttachmentState.ACTIVE.value}
        except Exception:
            return False

    @staticmethod
    def _result(row: Attachment) -> StagedCvResult:
        if row.page_count is None:
            raise CvIngestionError("MALFORMED_PDF")
        return StagedCvResult(id=row.id, original_name=str(row.original_name), mime_type=str(row.mime_type), size_bytes=int(row.size_bytes), page_count=row.page_count, state=str(row.state))

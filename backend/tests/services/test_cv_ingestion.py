from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from app.db.session import create_session_manager
from app.services.attachment_storage import FilesystemAttachmentStorage
from app.services.cv_ingestion import CvIngestionError, CvIngestionService
from pypdf import PdfWriter


def pdf_bytes(pages: int = 1) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return output.getvalue()


async def chunks(payload: bytes):
    for offset in range(0, len(payload), 7):
        await asyncio.sleep(0)
        yield payload[offset : offset + 7]


@pytest.mark.asyncio
async def test_valid_pdf_is_staged_and_duplicate_reuses_one_row(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)
    payload = pdf_bytes()
    first = await service.intake("../resume.pdf", "application/pdf", chunks(payload))
    second = await service.intake("copy.pdf", "application/pdf", chunks(payload))
    assert second == first
    assert first.original_name == "resume.pdf"
    assert first.page_count == 1
    assert len(list((tmp_path / "files" / "staged").iterdir())) == 1
    await db.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(("mime", "payload", "code"), [("text/plain", b"%PDF-1.4", "UNSUPPORTED_MEDIA_TYPE"), ("application/pdf", b"not-a-pdf", "INVALID_PDF_MAGIC"), ("application/pdf", b"%PDF-" + b"x" * 100, "PDF_TOO_LARGE")])
async def test_invalid_uploads_leave_no_files(tmp_path: Path, mime: str, payload: bytes, code: str) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=32, max_pages=2)
    with pytest.raises(CvIngestionError) as error:
        await service.intake("../../cv.pdf", mime, chunks(payload))
    assert error.value.code == code
    assert str(tmp_path) not in str(error.value)
    assert not list((tmp_path / "files" / "staged").iterdir())
    await db.dispose()


@pytest.mark.asyncio
async def test_over_page_and_broken_duplicate_cleanup(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=100_000, max_pages=1)
    with pytest.raises(CvIngestionError, match="PDF_PAGE_LIMIT_EXCEEDED"):
        await service.intake("cv.pdf", "application/pdf", chunks(pdf_bytes(2)))
    assert not list((tmp_path / "files" / "staged").iterdir())
    service = CvIngestionService(db, storage, max_size_bytes=100_000, max_pages=2)
    first = await service.intake("cv.pdf", "application/pdf", chunks(pdf_bytes()))
    (tmp_path / "files" / "staged" / str(first.id)).unlink()
    replacement = await service.intake("cv.pdf", "application/pdf", chunks(pdf_bytes()))
    assert replacement.id != first.id
    await db.dispose()

async def _row_count(db) -> int:
    from app.db.models.attachments import Attachment
    from sqlalchemy import func, select

    async with db.session_scope() as session:
        value = await session.scalar(select(func.count()).select_from(Attachment))
        return int(value or 0)


@pytest.mark.asyncio
async def test_malformed_pdf_returns_stable_code_and_cleans_staged_bytes(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)

    with pytest.raises(CvIngestionError) as error:
        await service.intake("cv.pdf", "application/pdf", chunks(b"%PDF-malformed"))

    assert error.value.code == "MALFORMED_PDF"
    assert await _row_count(db) == 0
    assert not list((tmp_path / "files" / "staged").iterdir())
    await db.dispose()


@pytest.mark.asyncio
async def test_image_only_pdf_is_validated_by_page_count(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)

    result = await service.intake("scan.pdf", "application/pdf", chunks(pdf_bytes()))

    assert result.page_count == 1
    assert await _row_count(db) == 1
    await db.dispose()


@pytest.mark.asyncio
async def test_concurrent_identical_uploads_resolve_to_one_attachment(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)
    payload = pdf_bytes()

    results = await asyncio.gather(*(service.intake(f"cv-{index}.pdf", "application/pdf", chunks(payload)) for index in range(4)))

    assert len({result.id for result in results}) == 1
    assert await _row_count(db) == 1
    assert len(list((tmp_path / "files" / "staged").iterdir())) == 1
    await db.dispose()


@pytest.mark.asyncio
async def test_cancellation_during_streaming_leaves_no_partial_or_row(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)

    async def cancelled_stream():
        yield b"%PDF-"
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await service.intake("cv.pdf", "application/pdf", cancelled_stream())

    assert await _row_count(db) == 0
    assert not list((tmp_path / "files" / "staged").iterdir())
    await db.dispose()


@pytest.mark.asyncio
async def test_partial_stream_failure_leaves_no_partial_or_row(tmp_path: Path) -> None:
    db = create_session_manager(tmp_path / "db.sqlite")
    await db.create_all()
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    service = CvIngestionService(db, storage, max_size_bytes=10_000, max_pages=2)

    async def broken_stream():
        yield b"%PDF-"
        raise RuntimeError("sentinel stream failure")

    with pytest.raises(RuntimeError, match="sentinel stream failure"):
        await service.intake("cv.pdf", "application/pdf", broken_stream())

    assert await _row_count(db) == 0
    assert not list((tmp_path / "files" / "staged").iterdir())
    await db.dispose()
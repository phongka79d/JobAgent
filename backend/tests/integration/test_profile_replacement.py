"""Filesystem/SQLite replacement integration proof."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from app.services.attachment_storage import (
    FilesystemAttachmentStorage,
    iter_byte_chunks,
)


@pytest.mark.asyncio
async def test_promoted_file_can_be_restored_to_staged(tmp_path: Path) -> None:
    storage = FilesystemAttachmentStorage(tmp_path / "files")
    attachment_id = uuid4()
    staged = await storage.stage(attachment_id, iter_byte_chunks(b"recoverable"))
    active_path = await storage.promote(staged.storage_path)

    restored_path = await storage.restore(active_path)

    assert restored_path == staged.storage_path
    stream = await storage.open(restored_path)
    assert b"".join([chunk async for chunk in stream]) == b"recoverable"

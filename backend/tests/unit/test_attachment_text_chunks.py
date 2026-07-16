"""Unit tests for deterministic CV chunking and attachment_text_chunks repo."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.db.models.attachments import ATTACHMENT_STATE_ARCHIVED
from app.db.session import build_async_engine
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories.attachment_text_chunks import (
    AttachmentTextChunkRepositoryError,
    build_chunk_write,
    preview_for_text,
    token_estimate_for_chars,
)
from app.services.profile_extraction import (
    CHUNK_JOIN,
    CHUNK_OVERLAP,
    MAX_CHUNK_CHARS,
    ProfileExtractionError,
    chunk_parsed_text,
    join_chunks_for_model,
    persist_canonical_chunks,
)

from tests.support.db_migration import run_async, session_factory


def test_chunker_constants_and_empty_rejection() -> None:
    assert MAX_CHUNK_CHARS == 1200
    assert CHUNK_OVERLAP == 0
    assert CHUNK_JOIN == "\n\n"
    with pytest.raises(ProfileExtractionError) as ei:
        chunk_parsed_text("   \n\n  ")
    assert ei.value.code == "EMPTY_CHUNKS"


def test_chunker_paragraph_then_whitespace_and_join() -> None:
    para_a = "Alpha paragraph one."
    para_b = "Beta paragraph two."
    text = f"{para_a}\n\n{para_b}"
    chunks = chunk_parsed_text(text)
    assert len(chunks) >= 1
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    assert all(c.text for c in chunks)
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    joined = join_chunks_for_model(chunks)
    assert joined == CHUNK_JOIN.join(c.text for c in chunks)
    # Model input is exactly the joined sequence (identity).
    assert joined == join_chunks_for_model(chunks)


def test_chunker_splits_long_paragraph_without_overlap() -> None:
    long_words = " ".join(f"word{i:04d}" for i in range(400))
    assert len(long_words) > MAX_CHUNK_CHARS
    chunks = chunk_parsed_text(long_words)
    assert len(chunks) >= 2
    assert all(len(c.text) <= MAX_CHUNK_CHARS for c in chunks)
    # Zero overlap: consecutive chunk texts are not identical prefixes.
    for i in range(1, len(chunks)):
        assert chunks[i].text != chunks[i - 1].text
        assert not chunks[i].text.startswith(chunks[i - 1].text[:40])


def test_preview_and_token_estimate_helpers() -> None:
    assert token_estimate_for_chars(1) == 1
    assert token_estimate_for_chars(4) == 1
    assert token_estimate_for_chars(5) == 2
    long = "x" * 300
    prev = preview_for_text(long)
    assert len(prev) == 240
    assert prev == long[:240]
    write = build_chunk_write(0, long)
    assert write.preview == prev
    assert write.char_count == 300
    assert write.token_estimate == token_estimate_for_chars(300)


def test_replace_list_and_historic_unavailable(migrated_sqlite: Path) -> None:
    db = migrated_sqlite

    async def _body() -> None:
        engine = build_async_engine(db)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            historic_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="chunk-hash-1",
                    original_name="cv.pdf",
                    size_bytes=10,
                    storage_path=f"{att_id}.pdf",
                    page_count=1,
                    attachment_id=att_id,
                )
                await att_repo.create_staged(
                    session,
                    file_hash="chunk-hash-hist",
                    original_name="old.pdf",
                    size_bytes=10,
                    storage_path=f"{historic_id}.pdf",
                    page_count=1,
                    attachment_id=historic_id,
                )
                # Historic attachment: no chunk rows, never backfilled.
                hist_count = await chunk_repo.count_for_attachment(
                    session, historic_id
                )
                assert hist_count == 0
                hist_rows = await chunk_repo.list_for_attachment(
                    session, historic_id
                )
                assert hist_rows == []

                text_a = "First chunk body with enough content."
                text_b = "Second chunk body also nonempty."
                chunks = chunk_parsed_text(f"{text_a}\n\n{text_b}")
                rows = await persist_canonical_chunks(
                    session, attachment_id=att_id, chunks=chunks
                )
                await session.commit()
                assert len(rows) == len(chunks)
                listed = await chunk_repo.list_for_attachment(session, att_id)
                assert [r.ordinal for r in listed] == list(range(len(chunks)))
                assert [r.text for r in listed] == [c.text for c in chunks]
                assert listed[0].preview == preview_for_text(chunks[0].text)
                assert listed[0].token_estimate == token_estimate_for_chars(
                    len(chunks[0].text)
                )
                # Replace is idempotent for same attachment.
                again = await persist_canonical_chunks(
                    session, attachment_id=att_id, chunks=chunks[:1]
                )
                await session.commit()
                assert len(again) == 1
                listed2 = await chunk_repo.list_for_attachment(session, att_id)
                assert len(listed2) == 1

                # Archive retains chunks; delete of archived is refused.
                await att_repo.mark_active(session, att_id)
                await att_repo.mark_archived(session, att_id)
                await session.commit()
                archived = await att_repo.get_by_id(session, att_id)
                assert archived is not None
                assert archived.state == ATTACHMENT_STATE_ARCHIVED
                assert await chunk_repo.count_for_attachment(session, att_id) == 1
                with pytest.raises(Exception):
                    await att_repo.delete(session, att_id)
        finally:
            await engine.dispose()

    run_async(_body())


def test_replace_rejects_non_contiguous_ordinals(migrated_sqlite: Path) -> None:
    db = migrated_sqlite

    async def _body() -> None:
        engine = build_async_engine(db)
        factory = session_factory(engine)
        try:
            att_id = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="bad-ord",
                    original_name="cv.pdf",
                    size_bytes=10,
                    storage_path=f"{att_id}.pdf",
                    page_count=1,
                    attachment_id=att_id,
                )
                with pytest.raises(AttachmentTextChunkRepositoryError):
                    await chunk_repo.replace_for_attachment(
                        session,
                        att_id,
                        [
                            build_chunk_write(0, "a"),
                            build_chunk_write(2, "b"),
                        ],
                    )
        finally:
            await engine.dispose()

    run_async(_body())

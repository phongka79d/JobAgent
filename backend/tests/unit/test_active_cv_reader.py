"""Unit tests for bounded active-CV reader and outline context (Plan 9 06A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.agent.active_cv_context import (
    LEGACY_EXTRACTION_VERSION,
    load_active_cv_context,
    project_active_cv_context,
)
from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo
from app.repositories.attachment_text_chunks import build_chunk_write
from app.services.active_cv_reader import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_RESULTS,
    ERROR_ACTIVE_CV_CHANGED,
    ERROR_CV_DOCUMENT_REPROCESS_REQUIRED,
    ERROR_INVALID_INPUT,
    ERROR_MALFORMED_CURSOR,
    ERROR_NO_ACTIVE_CV,
    ERROR_SECTION_NOT_FOUND,
    MAX_MAX_CHARS,
    MAX_MAX_RESULTS,
    MIN_MAX_CHARS,
    MIN_MAX_RESULTS,
    decode_active_cv_cursor,
    encode_active_cv_cursor,
    read_active_cv,
)

from tests.support.db_migration import run_async, session_factory

_ATTACHMENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_SECTION_ID = "cv-document-v1:s0:experience"
_ENTRY_0 = "cv-document-v1:s0:e0:role"
_ENTRY_1 = "cv-document-v1:s0:e1:lead"
_SOURCE_HASH = "abc123sourcehashfixed000000000000000000000000000000000000001"


def _entry(
    *,
    entry_id: str,
    ordinal: int,
    title: str,
    body: str,
    bullets: list[str] | None = None,
    source_chunk_ordinals: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "id": entry_id,
        "ordinal": ordinal,
        "title": title,
        "subtitle": "Acme",
        "date_text": "2019",
        "location": None,
        "body": body,
        "bullets": bullets if bullets is not None else ["Python"],
        "attributes": {},
        "source_chunk_ordinals": source_chunk_ordinals or [ordinal],
    }


def _document(
    attachment_id: str = _ATTACHMENT,
    *,
    entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if entries is None:
        entries = [
            _entry(
                entry_id=_ENTRY_0,
                ordinal=0,
                title="Engineer",
                body="Built APIs with Python",
                source_chunk_ordinals=[0],
            ),
            _entry(
                entry_id=_ENTRY_1,
                ordinal=1,
                title="Lead",
                body="Led platform Kubernetes work",
                source_chunk_ordinals=[1],
            ),
        ]
    section_ords = sorted(
        {o for e in entries for o in e["source_chunk_ordinals"]}
    )
    return {
        "attachment_id": attachment_id,
        "detected_languages": ["en"],
        "sections": [
            {
                "id": _SECTION_ID,
                "ordinal": 0,
                "heading": "Experience",
                "kind": "experience",
                "entries": entries,
                "source_chunk_ordinals": section_ords,
            },
            {
                "id": "cv-document-v1:s1:certifications",
                "ordinal": 1,
                "heading": "Certifications",
                "kind": "certifications",
                "entries": [
                    _entry(
                        entry_id="cv-document-v1:s1:e0:aws",
                        ordinal=0,
                        title="AWS CSA",
                        body="Issued 2022",
                        bullets=[],
                        source_chunk_ordinals=[2],
                    )
                ],
                "source_chunk_ordinals": [2],
            },
        ],
        "extraction_warnings": [],
        "extraction_confidence": 0.9,
    }


def _outline_from_document(document: dict[str, Any]) -> dict[str, Any]:
    sections = []
    for section in document["sections"]:
        ords = section["source_chunk_ordinals"]
        sections.append(
            {
                "id": section["id"],
                "ordinal": section["ordinal"],
                "heading": section["heading"],
                "kind": section["kind"],
                "entry_count": len(section["entries"]),
                "source_chunk_ordinals": list(ords),
                "source_chunk_range": [ords[0], ords[-1]] if ords else [],
            }
        )
    return {"sections": sections}


async def _seed_active_document(
    session: Any,
    *,
    attachment_id: str = _ATTACHMENT,
    with_document: bool = True,
    with_chunks: bool = True,
    document: dict[str, Any] | None = None,
    source_hash: str = _SOURCE_HASH,
) -> str:
    await att_repo.create_staged(
        session,
        file_hash=f"hash-{attachment_id[:8]}",
        original_name="cv.pdf",
        size_bytes=10,
        storage_path=f"{attachment_id}.pdf",
        page_count=1,
        attachment_id=attachment_id,
    )
    await att_repo.mark_active(session, attachment_id, page_count=1)
    await profile_repo.upsert_active_profile(
        session,
        active_attachment_id=attachment_id,
        profile_json={
            "summary": "Engineer",
            "current_title": "Engineer",
            "total_experience_years": 5.0,
            "skills": [],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.9,
        },
    )
    doc = document or _document(attachment_id)
    if with_document:
        await cv_doc_repo.upsert_document(
            session,
            attachment_id=attachment_id,
            document_json=doc,
            profile_json={"summary": "Engineer"},
            outline_json=_outline_from_document(doc),
            extraction_version="cv-document-v1",
            source_hash=source_hash,
        )
    if with_chunks:
        texts = [
            "Built APIs with Python",
            "Led platform Kubernetes work",
            "AWS Certified Solutions Architect Issued 2022",
        ]
        await chunk_repo.replace_for_attachment(
            session,
            attachment_id,
            [build_chunk_write(i, t) for i, t in enumerate(texts)],
        )
    await session.commit()
    return attachment_id


# ---------------------------------------------------------------------------
# Outline / active_cv_context
# ---------------------------------------------------------------------------


def test_project_active_cv_context_outline_only_no_bodies() -> None:
    outline = _outline_from_document(_document())
    # Inject bodies into outline payload to prove projection strips them.
    outline["sections"][0]["body"] = "SECRET_BODY"
    outline["sections"][0]["entries"] = [{"body": "ENTRY_BODY"}]
    ctx = project_active_cv_context(
        attachment_id=_ATTACHMENT,
        extraction_version="cv-document-v1",
        source_hash=_SOURCE_HASH,
        outline_json=outline,
        reprocess_required=False,
    )
    assert ctx["attachment_id"] == _ATTACHMENT
    assert ctx["source_hash"] == _SOURCE_HASH
    assert ctx["reprocess_required"] is False
    assert len(ctx["sections"]) == 2
    for section in ctx["sections"]:
        assert set(section) == {
            "id",
            "ordinal",
            "heading",
            "kind",
            "entry_count",
            "source_chunk_range",
        }
        assert "body" not in section
        assert "entries" not in section
        assert "source_chunk_ordinals" not in section
    blob = str(ctx)
    assert "SECRET_BODY" not in blob
    assert "ENTRY_BODY" not in blob
    assert "storage_path" not in blob
    assert "%PDF" not in blob


def test_project_legacy_reprocess_required_no_synthetic_sections() -> None:
    ctx = project_active_cv_context(
        attachment_id=_ATTACHMENT,
        extraction_version=LEGACY_EXTRACTION_VERSION,
        source_hash=None,
        outline_json=None,
        reprocess_required=True,
    )
    assert ctx["reprocess_required"] is True
    assert ctx["sections"] == []
    assert ctx["extraction_version"] == LEGACY_EXTRACTION_VERSION


def test_load_active_cv_context_document_and_legacy(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session)
            async with factory() as session:
                ctx = await load_active_cv_context(session)
            assert ctx is not None
            assert ctx["attachment_id"] == _ATTACHMENT
            assert ctx["reprocess_required"] is False
            assert ctx["sections"]
            assert all("body" not in s for s in ctx["sections"])
            blob = str(ctx)
            assert "Built APIs" not in blob
            assert "storage_path" not in blob

            # Switch to legacy: drop document row, keep active attachment.
            async with factory() as session:
                await cv_doc_repo.delete_document(session, _ATTACHMENT)
                await session.commit()
            async with factory() as session:
                legacy = await load_active_cv_context(session)
            assert legacy is not None
            assert legacy["reprocess_required"] is True
            assert legacy["sections"] == []
            assert legacy["extraction_version"] == LEGACY_EXTRACTION_VERSION
        finally:
            await engine.dispose()

    run_async(_body())


def test_load_active_cv_context_empty_without_profile(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                ctx = await load_active_cv_context(session)
            assert ctx is None
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Reader: modes, caps, cursors, auth, legacy
# ---------------------------------------------------------------------------


def test_read_no_active_cv(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                result = await read_active_cv(session, mode="chunk", chunk_ordinal=0)
            assert result.ok is False
            assert result.code == ERROR_NO_ACTIVE_CV
        finally:
            await engine.dispose()

    run_async(_body())


def test_section_mode_stable_order_and_caps(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session)
            async with factory() as session:
                result = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    max_results=1,
                    max_chars=DEFAULT_MAX_CHARS,
                )
            assert result.ok is True
            assert result.data is not None
            assert result.data["mode"] == "section"
            assert result.data["attachment_id"] == _ATTACHMENT
            assert result.data["source_hash"] == _SOURCE_HASH
            records = result.data["records"]
            assert len(records) == 1
            assert records[0]["entry_id"] == _ENTRY_0
            assert result.data["next_cursor"] is not None
            assert "storage_path" not in str(result.data)
            assert "%PDF" not in str(result.data)

            async with factory() as session:
                page2 = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    cursor=result.data["next_cursor"],
                    max_results=5,
                )
            assert page2.ok is True
            assert page2.data is not None
            assert len(page2.data["records"]) == 1
            assert page2.data["records"][0]["entry_id"] == _ENTRY_1
            assert page2.data["next_cursor"] is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_section_not_found_and_invalid_input(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session)
            async with factory() as session:
                missing = await read_active_cv(
                    session, mode="section", section_id="missing-section"
                )
                bad_mode = await read_active_cv(session, mode="vector")  # type: ignore[arg-type]
                bad_bounds = await read_active_cv(
                    session,
                    mode="chunk",
                    chunk_ordinal=0,
                    max_results=0,
                )
                bad_chars = await read_active_cv(
                    session,
                    mode="chunk",
                    chunk_ordinal=0,
                    max_chars=1,
                )
            assert missing.ok is False and missing.code == ERROR_SECTION_NOT_FOUND
            assert bad_mode.ok is False and bad_mode.code == ERROR_INVALID_INPUT
            assert bad_bounds.ok is False and bad_bounds.code == ERROR_INVALID_INPUT
            assert bad_chars.ok is False and bad_chars.code == ERROR_INVALID_INPUT
            assert MIN_MAX_RESULTS == 1
            assert MAX_MAX_RESULTS == 10
            assert MIN_MAX_CHARS == 500
            assert MAX_MAX_CHARS == 12_000
            assert DEFAULT_MAX_RESULTS == 5
            assert DEFAULT_MAX_CHARS == 6000
        finally:
            await engine.dispose()

    run_async(_body())


def test_search_matches_entries_and_chunks_stable_order(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session)
            async with factory() as session:
                result = await read_active_cv(
                    session,
                    mode="search",
                    query="Python",
                    max_results=10,
                )
            assert result.ok is True
            assert result.data is not None
            records = result.data["records"]
            assert records
            # Entries before chunks; first entry contains Python.
            kinds = [r["kind"] for r in records]
            assert "entry_match" in kinds
            first_entry = next(r for r in records if r["kind"] == "entry_match")
            assert first_entry["entry_id"] == _ENTRY_0
            blob = str(result.data)
            assert "storage_path" not in blob
            assert "FILES_DIR" not in blob
        finally:
            await engine.dispose()

    run_async(_body())


def test_chunk_mode_page_and_character_truncation(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            big = "Z" * 800
            doc = _document(
                entries=[
                    _entry(
                        entry_id=_ENTRY_0,
                        ordinal=0,
                        title="Big",
                        body=big,
                        bullets=[],
                        source_chunk_ordinals=[0],
                    )
                ]
            )
            async with factory() as session:
                await _seed_active_document(session, document=doc, with_chunks=False)
                await chunk_repo.replace_for_attachment(
                    session,
                    _ATTACHMENT,
                    [
                        build_chunk_write(0, big),
                        build_chunk_write(1, "second chunk"),
                    ],
                )
                await session.commit()

            async with factory() as session:
                result = await read_active_cv(
                    session,
                    mode="chunk",
                    chunk_ordinal=0,
                    max_results=1,
                    max_chars=500,
                )
            assert result.ok is True
            assert result.data is not None
            assert result.data["truncated"] is True
            rec = result.data["records"][0]
            assert rec["kind"] == "chunk"
            assert rec["record_truncated"] is True
            assert len(rec["text"]) == 500
            assert result.data["returned_chars"] == 500
            assert result.data["next_cursor"] is not None

            async with factory() as session:
                page2 = await read_active_cv(
                    session,
                    mode="chunk",
                    chunk_ordinal=0,
                    cursor=result.data["next_cursor"],
                    max_results=5,
                    max_chars=6000,
                )
            assert page2.ok is True
            assert page2.data is not None
            assert page2.data["records"][0]["ordinal"] == 1
            assert page2.data["records"][0]["text"] == "second chunk"
        finally:
            await engine.dispose()

    run_async(_body())


def test_malformed_cursor_and_active_switch_invalidation(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session)
            async with factory() as session:
                first = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    max_results=1,
                )
            assert first.ok and first.data and first.data["next_cursor"]
            cursor = first.data["next_cursor"]
            decoded = decode_active_cv_cursor(cursor)
            assert decoded["attachment_id"] == _ATTACHMENT
            assert decoded["source_hash"] == _SOURCE_HASH

            async with factory() as session:
                bad = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    cursor="!!!not-a-cursor!!!",
                )
            assert bad.ok is False
            assert bad.code == ERROR_MALFORMED_CURSOR

            # Active switch: new attachment becomes active with new hash.
            other = new_uuid()
            async with factory() as session:
                await att_repo.create_staged(
                    session,
                    file_hash="hash-other",
                    original_name="other.pdf",
                    size_bytes=10,
                    storage_path=f"{other}.pdf",
                    page_count=1,
                    attachment_id=other,
                )
                await att_repo.mark_archived(session, _ATTACHMENT)
                await att_repo.mark_active(session, other, page_count=1)
                await profile_repo.upsert_active_profile(
                    session,
                    active_attachment_id=other,
                    profile_json={
                        "summary": "Other",
                        "current_title": "Other",
                        "total_experience_years": 1.0,
                        "skills": [],
                        "experiences": [],
                        "education": [],
                        "languages": [],
                        "extraction_confidence": 0.5,
                    },
                )
                other_doc = _document(other)
                await cv_doc_repo.upsert_document(
                    session,
                    attachment_id=other,
                    document_json=other_doc,
                    profile_json={"summary": "Other"},
                    outline_json=_outline_from_document(other_doc),
                    extraction_version="cv-document-v1",
                    source_hash="different-hash-value-0000000000000000000002",
                )
                await session.commit()

            async with factory() as session:
                changed = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    cursor=cursor,
                )
            assert changed.ok is False
            assert changed.code == ERROR_ACTIVE_CV_CHANGED

            # Revision change on the new active attachment invalidates cursors
            # bound to a prior source_hash.
            other_cursor = encode_active_cv_cursor(
                attachment_id=other,
                source_hash="different-hash-value-0000000000000000000002",
                mode="section",
                selector=f"section:{_SECTION_ID}",
                after=f"entry:{_ENTRY_0}",
            )
            async with factory() as session:
                await cv_doc_repo.upsert_document(
                    session,
                    attachment_id=other,
                    document_json=other_doc,
                    profile_json={"summary": "Other"},
                    outline_json=_outline_from_document(other_doc),
                    extraction_version="cv-document-v1",
                    source_hash="revised-hash-value-000000000000000000000003",
                )
                await session.commit()
            async with factory() as session:
                revised = await read_active_cv(
                    session,
                    mode="section",
                    section_id=_SECTION_ID,
                    cursor=other_cursor,
                )
            assert revised.ok is False
            assert revised.code == ERROR_ACTIVE_CV_CHANGED
        finally:
            await engine.dispose()

    run_async(_body())


def test_legacy_section_reprocess_search_chunk(migrated_sqlite: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _seed_active_document(session, with_document=False)
            async with factory() as session:
                section = await read_active_cv(
                    session, mode="section", section_id=_SECTION_ID
                )
                search = await read_active_cv(
                    session, mode="search", query="Python"
                )
                chunk = await read_active_cv(
                    session, mode="chunk", chunk_ordinal=0
                )
            assert section.ok is False
            assert section.code == ERROR_CV_DOCUMENT_REPROCESS_REQUIRED
            assert search.ok is True
            assert search.data is not None
            assert any(r["kind"] == "chunk_match" for r in search.data["records"])
            assert chunk.ok is True
            assert chunk.data is not None
            assert chunk.data["records"][0]["kind"] == "chunk"
            assert chunk.data["extraction_version"] == LEGACY_EXTRACTION_VERSION
            assert chunk.data["source_hash"] is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_cursor_roundtrip_helpers() -> None:
    encoded = encode_active_cv_cursor(
        attachment_id=_ATTACHMENT,
        source_hash=_SOURCE_HASH,
        mode="search",
        selector="search:python",
        after="entry:x",
    )
    decoded = decode_active_cv_cursor(encoded)
    assert decoded["attachment_id"] == _ATTACHMENT
    assert decoded["after"] == "entry:x"
    with pytest.raises(ValueError):
        decode_active_cv_cursor("")
    with pytest.raises(ValueError):
        decode_active_cv_cursor("%%%")


def test_reader_never_accepts_archived_guess_via_server_resolve(
    migrated_sqlite: Path,
) -> None:
    """Archived CVs are unreachable because active is resolved server-side."""

    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            archived = new_uuid()
            async with factory() as session:
                await _seed_active_document(session, attachment_id=archived)
                await att_repo.mark_archived(session, archived)
                # No profile -> no active.
                from app.db.models.profiles import CANDIDATE_PROFILE_ID

                row = await session.get(
                    __import__(
                        "app.db.models.profiles", fromlist=["CandidateProfile"]
                    ).CandidateProfile,
                    CANDIDATE_PROFILE_ID,
                )
                if row is not None:
                    await session.delete(row)
                await session.commit()
            async with factory() as session:
                result = await read_active_cv(
                    session, mode="chunk", chunk_ordinal=0
                )
            assert result.ok is False
            assert result.code == ERROR_NO_ACTIVE_CV
        finally:
            await engine.dispose()

    run_async(_body())

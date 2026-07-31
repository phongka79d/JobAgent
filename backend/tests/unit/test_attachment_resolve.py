"""Focused attachment provenance tests for profile proposal resolution."""

from __future__ import annotations

from pathlib import Path

from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo
from app.services.attachment_resolve import resolve_attachment_id_for_propose

from tests.support.db_migration import run_async, session_factory


async def _create_attachment(
    session: object,
    *,
    attachment_id: str,
    file_hash: str,
) -> None:
    await att_repo.create_staged(
        session,  # type: ignore[arg-type]
        file_hash=file_hash,
        original_name=f"{file_hash}.pdf",
        size_bytes=10,
        storage_path=f"{attachment_id}.pdf",
        page_count=1,
        attachment_id=attachment_id,
    )


def test_single_turn_attachment_overrides_model_supplied_active_id(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            active_id = new_uuid()
            staged_id = new_uuid()
            async with factory() as session:
                await _create_attachment(
                    session,
                    attachment_id=active_id,
                    file_hash="active-a",
                )
                await att_repo.mark_active(session, active_id)
                await _create_attachment(
                    session,
                    attachment_id=staged_id,
                    file_hash="staged-b",
                )
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=active_id,
                    display_name="Profile A",
                    profile_json={"owner": "A"},
                    location=None,
                    extraction_version="test-v1",
                    source_hash="active-a",
                )
                await session.commit()

            async with factory() as session:
                resolved = await resolve_attachment_id_for_propose(
                    session,
                    active_id,
                    profile_id=profile.id,
                    turn_attachment_ids=[staged_id],
                )
                assert resolved == staged_id
        finally:
            await engine.dispose()

    run_async(_body())


def test_multiple_turn_attachments_require_requested_member(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            outside_id = new_uuid()
            staged_b = new_uuid()
            staged_c = new_uuid()
            async with factory() as session:
                await _create_attachment(
                    session,
                    attachment_id=outside_id,
                    file_hash="outside-active",
                )
                await att_repo.mark_active(session, outside_id)
                await _create_attachment(
                    session,
                    attachment_id=staged_b,
                    file_hash="staged-b",
                )
                await _create_attachment(
                    session,
                    attachment_id=staged_c,
                    file_hash="staged-c",
                )
                profile = await profile_repo.create_profile(
                    session,
                    attachment_id=outside_id,
                    display_name="Profile A",
                    profile_json={"owner": "A"},
                    location=None,
                    extraction_version="test-v1",
                    source_hash="outside-active",
                )
                await session.commit()

            async with factory() as session:
                assert (
                    await resolve_attachment_id_for_propose(
                        session,
                        outside_id,
                        profile_id=profile.id,
                        turn_attachment_ids=[staged_b, staged_c],
                    )
                    is None
                )
                assert (
                    await resolve_attachment_id_for_propose(
                        session,
                        staged_b,
                        profile_id=profile.id,
                        turn_attachment_ids=[staged_b, staged_c],
                    )
                    == staged_b
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_attachment_resolution_uses_only_the_requested_profile_draft(
    migrated_sqlite: Path,
) -> None:
    async def _body() -> None:
        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                attachment_a = new_uuid()
                attachment_b = new_uuid()
                await _create_attachment(
                    session, attachment_id=attachment_a, file_hash="resolver-owner-a"
                )
                await _create_attachment(
                    session, attachment_id=attachment_b, file_hash="resolver-owner-b"
                )
                profile_a = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_a,
                    display_name="Profile A",
                    profile_json={"owner": "A"},
                    location=None,
                    extraction_version="test-v1",
                    source_hash="resolver-owner-a",
                )
                profile_b = await profile_repo.create_profile(
                    session,
                    attachment_id=attachment_b,
                    display_name="Profile B",
                    profile_json={"owner": "B"},
                    location=None,
                    extraction_version="test-v1",
                    source_hash="resolver-owner-b",
                )
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_a.id,
                    source_attachment_id=attachment_a,
                    draft_json={"owner": "A"},
                )
                await profile_repo.upsert_draft_for_profile(
                    session,
                    profile_id=profile_b.id,
                    source_attachment_id=attachment_b,
                    draft_json={"owner": "B"},
                )
                await session.commit()

            async with factory() as session:
                resolved = await resolve_attachment_id_for_propose(
                    session,
                    "current",
                    profile_id=profile_a.id,
                )
            assert resolved == attachment_a
        finally:
            await engine.dispose()

    run_async(_body())

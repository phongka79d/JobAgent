"""Focused attachment provenance tests for profile proposal resolution."""

from __future__ import annotations

from pathlib import Path

from app.core.ids import new_uuid
from app.db.session import build_async_engine
from app.repositories import attachments as att_repo
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
                await session.commit()

            async with factory() as session:
                resolved = await resolve_attachment_id_for_propose(
                    session,
                    active_id,
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
                await session.commit()

            async with factory() as session:
                assert (
                    await resolve_attachment_id_for_propose(
                        session,
                        outside_id,
                        turn_attachment_ids=[staged_b, staged_c],
                    )
                    is None
                )
                assert (
                    await resolve_attachment_id_for_propose(
                        session,
                        staged_b,
                        turn_attachment_ids=[staged_b, staged_c],
                    )
                    == staged_b
                )
        finally:
            await engine.dispose()

    run_async(_body())

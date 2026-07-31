from __future__ import annotations

import sqlite3

import anyio
import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.models.attachments import Attachment
from app.db.models.profiles import Profile, ProfileDraft, ProfileReextractOperation
from app.db.session import build_async_engine
from app.repositories import workspace_state as workspace_repo
from app.services.activity_gate import ActivityBlockedError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import run_async, session_factory


async def _seed_profile(session: AsyncSession, *, suffix: str) -> Profile:
    attachment = Attachment(
        file_hash=f"operation-{suffix}",
        original_name=f"{suffix}.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        page_count=1,
        storage_path=f"{suffix}.pdf",
        state="archived",
    )
    session.add(attachment)
    await session.flush()
    profile = Profile(
        attachment_id=attachment.id,
        display_name=suffix,
        profile_json={"full_name": suffix},
        location=None,
        extraction_version="test-v1",
        source_hash=suffix,
        state="ready",
    )
    session.add(profile)
    await session.flush()
    return profile


def test_concurrent_claims_persist_one_operation_and_report_exact_conflict(
    migrated_sqlite,
) -> None:
    async def _body() -> None:
        from app.db.session import immediate_session_scope
        from app.repositories.profile_reextract_operations import (
            ProfileReextractOperationConflict,
            claim_operation,
            get_operation,
        )

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await _seed_profile(session, suffix="contended")
                state = await workspace_repo.get_state(session)
                assert state is not None
                profile_id, attachment_id = profile.id, profile.attachment_id
                profile_revision, workspace_revision = (
                    profile.updated_at,
                    state.updated_at,
                )
                await session.commit()

            barrier = anyio.Event()
            results: list[tuple[str, str]] = []

            async def contender() -> None:
                await barrier.wait()
                try:
                    async with immediate_session_scope(factory) as session:
                        operation = await claim_operation(
                            session,
                            profile_id=profile_id,
                            source_attachment_id=attachment_id,
                            base_profile_updated_at=profile_revision,
                            base_workspace_updated_at=workspace_revision,
                        )
                    results.append(("claimed", operation.id))
                except ProfileReextractOperationConflict as exc:
                    assert exc.code == "PROFILE_REEXTRACT_IN_PROGRESS"
                    results.append(("conflict", exc.operation_id))

            async with anyio.create_task_group() as group:
                group.start_soon(contender)
                group.start_soon(contender)
                barrier.set()
            assert [kind for kind, _ in results].count("claimed") == 1
            assert [kind for kind, _ in results].count("conflict") == 1
            operation_id = next(value for kind, value in results if kind == "claimed")
            conflict_id = next(value for kind, value in results if kind == "conflict")
            assert conflict_id == operation_id
            async with factory() as session:
                durable = await get_operation(
                    session, profile_id=profile_id, operation_id=operation_id
                )
                assert durable is not None and durable.state == "running"
        finally:
            await engine.dispose()

    run_async(_body())


def test_claim_replaces_draftless_terminal_rows(
    migrated_sqlite,
) -> None:
    async def _body() -> None:
        from app.db.session import immediate_session_scope
        from app.repositories.profile_reextract_operations import claim_operation

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await _seed_profile(session, suffix="terminal")
                old_time = utc_now().replace(microsecond=100000)
                terminal_rows = [
                    ProfileReextractOperation(
                        id=new_uuid(),
                        profile_id=profile.id,
                        source_attachment_id=profile.attachment_id,
                        base_profile_updated_at=old_time,
                        base_workspace_updated_at=old_time,
                        state=state,
                        error_code=f"old-{state}",
                        created_at=old_time,
                        updated_at=old_time,
                    )
                    for state in ("interrupted", "failed", "stale")
                ]
                session.add_all(terminal_rows)
                await session.commit()
                state = await workspace_repo.get_state(session)
                assert state is not None
                profile_id = profile.id
                attachment_id = profile.attachment_id
                profile_revision = profile.updated_at
                workspace_revision = state.updated_at
                terminal_ids = [row.id for row in terminal_rows]
                await session.rollback()
                async with immediate_session_scope(factory) as session:
                    replacement = await claim_operation(
                        session,
                        profile_id=profile_id,
                        source_attachment_id=attachment_id,
                        base_profile_updated_at=profile_revision,
                        base_workspace_updated_at=workspace_revision,
                    )
                async with factory() as session:
                    for operation_id in terminal_ids:
                        assert (
                            await session.get(
                                ProfileReextractOperation, operation_id
                            )
                            is None
                        )
                    stored = await session.get(
                        ProfileReextractOperation, replacement.id
                    )
                    assert stored is not None and stored.state == "running"
        finally:
            await engine.dispose()

    run_async(_body())


def test_claim_preserves_owned_terminal_rows_and_makes_no_mutation(
    migrated_sqlite,
) -> None:
    async def _body() -> None:
        from app.db.session import immediate_session_scope
        from app.repositories.profile_reextract_operations import (
            ProfileReextractOperationConflict,
            claim_operation,
        )

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await _seed_profile(session, suffix="owned-terminal")
                now = utc_now()
                owned = ProfileReextractOperation(
                    id=new_uuid(), profile_id=profile.id,
                    source_attachment_id=profile.attachment_id,
                    base_profile_updated_at=now, base_workspace_updated_at=now,
                    state="stale", error_code="old-stale",
                    created_at=now, updated_at=now,
                )
                draftless = ProfileReextractOperation(
                    id=new_uuid(), profile_id=profile.id,
                    source_attachment_id=profile.attachment_id,
                    base_profile_updated_at=now, base_workspace_updated_at=now,
                    state="failed", error_code="old-failure",
                    created_at=now, updated_at=now,
                )
                session.add_all([owned, draftless])
                await session.flush()
                session.add(ProfileDraft(
                    id=new_uuid(), target_profile_id=profile.id,
                    reextract_operation_id=owned.id,
                    source_attachment_id=profile.attachment_id,
                    draft_json={"original": "must survive"},
                    created_at=now, updated_at=now,
                ))
                await session.commit()
                with pytest.raises(ProfileReextractOperationConflict) as raised:
                    async with immediate_session_scope(factory) as claim_session:
                        await claim_operation(
                            claim_session, profile_id=profile.id,
                            source_attachment_id=profile.attachment_id,
                            base_profile_updated_at=profile.updated_at,
                            base_workspace_updated_at=now,
                        )
                assert raised.value.code == "PROFILE_REVIEW_PENDING"
                assert raised.value.operation_id == owned.id
            async with factory() as session:
                assert (
                    await session.get(ProfileReextractOperation, owned.id) is not None
                )
                assert (
                    await session.get(ProfileReextractOperation, draftless.id)
                    is not None
                )
                draft = await session.scalar(select(ProfileDraft).where(
                    ProfileDraft.reextract_operation_id == owned.id
                ))
                assert draft is not None
                assert draft.draft_json == {"original": "must survive"}
        finally:
            await engine.dispose()

    run_async(_body())


def test_operation_repository_requires_exact_owner_and_cas_and_restricts_delete(
    migrated_sqlite,
) -> None:
    async def _body() -> None:
        from app.repositories.profile_reextract_operations import (
            delete_operation,
            get_latest_operation_for_profile,
            get_operation,
            list_running_operations,
            transition_running_operation,
        )

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await _seed_profile(session, suffix="cas")
                other = await _seed_profile(session, suffix="other")
                old_time = utc_now().replace(microsecond=100000)
                latest_time = utc_now().replace(microsecond=200000)
                first = ProfileReextractOperation(
                    id="op-old",
                    profile_id=profile.id,
                    source_attachment_id=profile.attachment_id,
                    base_profile_updated_at=old_time,
                    base_workspace_updated_at=old_time,
                    state="failed",
                    error_code="x",
                    created_at=old_time,
                    updated_at=old_time,
                )
                latest = ProfileReextractOperation(
                    id="op-latest",
                    profile_id=profile.id,
                    source_attachment_id=profile.attachment_id,
                    base_profile_updated_at=latest_time,
                    base_workspace_updated_at=latest_time,
                    state="running",
                    error_code=None,
                    created_at=latest_time,
                    updated_at=latest_time,
                )
                other_running = ProfileReextractOperation(
                    id="op-other", profile_id=other.id,
                    source_attachment_id=other.attachment_id,
                    base_profile_updated_at=latest_time,
                    base_workspace_updated_at=latest_time,
                    state="running", error_code=None,
                    created_at=latest_time, updated_at=latest_time,
                )
                session.add_all([first, latest, other_running])
                await session.flush()
                session.add(
                    ProfileDraft(
                        id=new_uuid(),
                        target_profile_id=profile.id,
                        reextract_operation_id=latest.id,
                        source_attachment_id=profile.attachment_id,
                        draft_json={"owned": True},
                        created_at=latest_time,
                        updated_at=latest_time,
                    )
                )
                await session.commit()
                assert (
                    await get_operation(
                        session, profile_id=other.id, operation_id=latest.id
                    )
                    is None
                )
                assert (
                    await get_latest_operation_for_profile(session, profile.id)
                ).id == latest.id
                assert {
                    row.id for row in await list_running_operations(session)
                } == {latest.id, other_running.id}
                assert [
                    row.id for row in await list_running_operations(session, profile.id)
                ] == [latest.id]
                assert await transition_running_operation(
                    session, profile_id=profile.id, operation_id=latest.id,
                    to_state="review_ready", error_code=None
                ) is True
                await session.commit()
                assert await transition_running_operation(
                    session, profile_id=profile.id, operation_id=latest.id,
                    to_state="failed", error_code="late"
                ) is False
                assert await transition_running_operation(
                    session, profile_id=other.id, operation_id=latest.id,
                    to_state="failed", error_code="wrong-owner"
                ) is False
            async with factory() as session:
                assert await delete_operation(
                    session, profile_id=other.id, operation_id=latest.id,
                    expected_state="review_ready"
                ) is False
                assert await delete_operation(
                    session, profile_id=profile.id, operation_id=latest.id,
                    expected_state="running"
                ) is False
                with pytest.raises(IntegrityError):
                    await delete_operation(
                        session, profile_id=profile.id, operation_id=latest.id,
                        expected_state="review_ready"
                    )
                await session.rollback()
            async with factory() as session:
                await session.execute(ProfileDraft.__table__.delete().where(
                    ProfileDraft.reextract_operation_id == latest.id
                ))
                assert await delete_operation(
                    session, profile_id=profile.id, operation_id=latest.id,
                    expected_state="review_ready"
                ) is True
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_unique_integrity_mapping_is_narrow() -> None:
    from app.repositories.profile_reextract_operations import (
        is_actionable_operation_unique_conflict,
    )

    sqlite_unique = IntegrityError(
        "insert",
        {},
        sqlite3.IntegrityError(
            "UNIQUE constraint failed: profile_reextract_operations.profile_id"
        ),
    )
    unrelated = [
        IntegrityError(
            "insert", {}, sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        ),
        IntegrityError(
            "insert", {}, sqlite3.IntegrityError("CHECK constraint failed: state")
        ),
        IntegrityError(
            "insert",
            {},
            sqlite3.IntegrityError(
                "UNIQUE constraint failed: profile_reextract_operations.id"
            ),
        ),
    ]
    assert is_actionable_operation_unique_conflict(sqlite_unique) is True
    assert all(
        not is_actionable_operation_unique_conflict(error) for error in unrelated
    )


def test_claim_reraises_unrelated_unique_id_integrity_error(
    migrated_sqlite, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _body() -> None:
        from app.db.session import immediate_session_scope
        from app.repositories import profile_reextract_operations as operations_repo
        from app.repositories.profile_reextract_operations import claim_operation

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                target = await _seed_profile(session, suffix="collision-target")
                other = await _seed_profile(session, suffix="collision-owner")
                now = utc_now()
                session.add(ProfileReextractOperation(
                    id="colliding-operation", profile_id=other.id,
                    source_attachment_id=other.attachment_id,
                    base_profile_updated_at=now, base_workspace_updated_at=now,
                    state="failed", error_code="old", created_at=now, updated_at=now,
                ))
                await session.commit()
                monkeypatch.setattr(
                    operations_repo, "new_uuid", lambda: "colliding-operation"
                )
                with pytest.raises(IntegrityError) as raised:
                    async with immediate_session_scope(factory) as claim_session:
                        await claim_operation(
                            claim_session, profile_id=target.id,
                            source_attachment_id=target.attachment_id,
                            base_profile_updated_at=target.updated_at,
                            base_workspace_updated_at=now,
                        )
                assert "profile_reextract_operations.id" in str(raised.value)
        finally:
            await engine.dispose()

    run_async(_body())


def test_profile_reextract_gate_blocks_actionable_or_owned_draft_only(
    migrated_sqlite,
) -> None:
    async def _body() -> None:
        from app.services.activity_gate import assert_profile_reextract_clear

        engine = build_async_engine(migrated_sqlite)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                profile = await _seed_profile(session, suffix="gate")
                await assert_profile_reextract_clear(session, profile_id=profile.id)
                now = utc_now()
                terminal = ProfileReextractOperation(
                    id=new_uuid(),
                    profile_id=profile.id,
                    source_attachment_id=profile.attachment_id,
                    base_profile_updated_at=now,
                    base_workspace_updated_at=now,
                    state="failed",
                    error_code="done",
                    created_at=now,
                    updated_at=now,
                )
                session.add(terminal)
                await session.flush()
                await assert_profile_reextract_clear(session, profile_id=profile.id)
                terminal.state = "running"
                terminal.error_code = None
                await session.flush()
                with pytest.raises(ActivityBlockedError) as running_blocked:
                    await assert_profile_reextract_clear(session, profile_id=profile.id)
                assert running_blocked.value.code == "PROFILE_REEXTRACT_IN_PROGRESS"
                terminal.state = "failed"
                terminal.error_code = "done"
                session.add(
                    ProfileDraft(
                        id=new_uuid(),
                        target_profile_id=profile.id,
                        reextract_operation_id=terminal.id,
                        source_attachment_id=profile.attachment_id,
                        draft_json={"owned": True},
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()
                with pytest.raises(ActivityBlockedError) as draft_blocked:
                    await assert_profile_reextract_clear(session, profile_id=profile.id)
                assert draft_blocked.value.code == "PROFILE_REVIEW_PENDING"
        finally:
            await engine.dispose()

    run_async(_body())

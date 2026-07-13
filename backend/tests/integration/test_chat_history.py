"""Integration tests for opaque cursor history pagination and hydration.

Uses a migrated temporary SQLite file (Alembic head). Covers equal-timestamp
tie-break IDs, first/middle/final pages, limits 1 and 100, null next_cursor,
malformed cursors (encoding/shape/time/UUID), and user-turn run/tool hydration
without any ``role='tool'`` history items.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.db.models.chat import (
    AGENT_RUN_STATE_COMPLETED,
    CHAT_MESSAGE_ROLE_ASSISTANT,
    CHAT_MESSAGE_ROLE_USER,
    CONVERSATION_ID,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import tool_executions as tool_repo
from app.schemas.chat import (
    HistoryPage,
    HistoryQuery,
    decode_history_cursor,
    encode_history_cursor,
)
from app.schemas.tools import ToolResult
from app.services.chat_history import get_history_page, history_page_as_dict
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import run_async, session_factory

T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


async def _insert_with_time(
    session: AsyncSession,
    *,
    role: str,
    content: str,
    created_at: datetime,
) -> str:
    msg = await messages_repo.insert_message(
        session, role=role, content=content
    )
    msg.created_at = created_at
    msg.updated_at = created_at
    await session.flush()
    return msg.id


def _encode_raw(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# Cursor encode / decode and malformed classes
# ---------------------------------------------------------------------------


def test_encode_decode_roundtrip() -> None:
    mid = new_uuid()
    cursor = encode_history_cursor(T0, mid)
    # URL-safe: no + / =
    assert "+" not in cursor and "/" not in cursor and "=" not in cursor
    decoded_t, decoded_id = decode_history_cursor(cursor)
    assert decoded_id == mid
    assert decoded_t == T0


def test_malformed_cursor_classes_raise_validation_error() -> None:
    """Every malformed class is a ValidationError (FastAPI 422-suitable)."""
    good_id = new_uuid()
    good = encode_history_cursor(T0, good_id)

    # Encoding: garbage / not base64
    with pytest.raises(ValidationError):
        HistoryQuery(before="!!!not-base64!!!")
    with pytest.raises(ValidationError):
        HistoryQuery(before="a")  # invalid padding/content after decode

    # Encoding: standard base64 alphabet (+/) not url-safe
    with pytest.raises(ValidationError):
        HistoryQuery(before=base64.b64encode(b'{"created_at":"x","id":"y"}').decode())

    # Shape: not a JSON object
    not_object = base64.urlsafe_b64encode(b"[1,2]").decode().rstrip("=")
    with pytest.raises(ValidationError):
        HistoryQuery(before=not_object)

    # Shape: missing / extra keys
    with pytest.raises(ValidationError):
        HistoryQuery(before=_encode_raw({"created_at": T0.isoformat()}))
    with pytest.raises(ValidationError):
        HistoryQuery(
            before=_encode_raw(
                {
                    "created_at": T0.isoformat(),
                    "id": good_id,
                    "extra": True,
                }
            )
        )

    # Time: naive ISO (no timezone)
    with pytest.raises(ValidationError):
        HistoryQuery(
            before=_encode_raw(
                {
                    "created_at": "2024-06-01T12:00:00",
                    "id": good_id,
                }
            )
        )

    # Time: non-UTC offset
    with pytest.raises(ValidationError):
        HistoryQuery(
            before=_encode_raw(
                {
                    "created_at": "2024-06-01T12:00:00+02:00",
                    "id": good_id,
                }
            )
        )

    # UUID: invalid / non-v4
    with pytest.raises(ValidationError):
        HistoryQuery(
            before=_encode_raw(
                {
                    "created_at": T0.isoformat(),
                    "id": "not-a-uuid",
                }
            )
        )
    with pytest.raises(ValidationError):
        HistoryQuery(
            before=_encode_raw(
                {
                    "created_at": T0.isoformat(),
                    # UUID v1 sample shape (version nibble 1)
                    "id": "550e8400-e29b-11d4-a716-446655440000",
                }
            )
        )

    # Blank
    with pytest.raises(ValidationError):
        HistoryQuery(before="")

    # Valid still works
    q = HistoryQuery(before=good, limit=10)
    assert q.before == good
    assert q.limit == 10


# ---------------------------------------------------------------------------
# Pagination: ties, pages, limits, null cursor
# ---------------------------------------------------------------------------


def test_pagination_equal_timestamps_tie_break_no_duplicates_or_gaps(
    db_path: Path,
) -> None:
    """Tied created_at uses id lexicographic order; pages cover all rows once."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            t1 = T0 + timedelta(seconds=1)

            async with factory() as session:
                id_late = await _insert_with_time(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="late",
                    created_at=t1,
                )
                # Three messages at identical created_at; order by id only.
                tied_ids: list[str] = []
                for label in ("t0", "t1", "t2"):
                    mid = await _insert_with_time(
                        session,
                        role=CHAT_MESSAGE_ROLE_USER,
                        content=label,
                        created_at=T0,
                    )
                    tied_ids.append(mid)
                await session.commit()

            tied_sorted = sorted(tied_ids)
            id_a, id_b, id_c = tied_sorted  # oldest..newest among ties
            expected_chrono = [id_a, id_b, id_c, id_late]

            async with factory() as session:
                # Newest-first: late, then id_c > id_b > id_a among ties.
                # limit=2 page: [late, id_c] newest-first -> chrono [id_c, late]
                page1 = await get_history_page(session, limit=2, before=None)
                assert [i.id for i in page1.items] == [id_c, id_late]
                assert page1.next_cursor is not None
                ct, cid = decode_history_cursor(page1.next_cursor)
                assert cid == id_c
                assert ct == T0 or _as_utc(ct) == T0

                page2 = await get_history_page(
                    session, limit=2, before=page1.next_cursor
                )
                assert [i.id for i in page2.items] == [id_a, id_b]
                assert page2.next_cursor is None

                all_ids = [i.id for i in page2.items] + [i.id for i in page1.items]
                assert all_ids == expected_chrono
                assert len(set(all_ids)) == 4
        finally:
            await engine.dispose()

    run_async(_body())


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_first_middle_final_pages_and_null_cursor(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            ids: list[str] = []
            async with factory() as session:
                for i in range(5):
                    mid = await _insert_with_time(
                        session,
                        role=CHAT_MESSAGE_ROLE_USER,
                        content=f"m{i}",
                        created_at=T0 + timedelta(seconds=i),
                    )
                    ids.append(mid)
                await session.commit()
            # Chronological ids[0]..ids[4] (oldest..newest)

            async with factory() as session:
                first = await get_history_page(session, limit=2, before=None)
                assert [i.content for i in first.items] == ["m3", "m4"]
                assert first.next_cursor is not None

                middle = await get_history_page(
                    session, limit=2, before=first.next_cursor
                )
                assert [i.content for i in middle.items] == ["m1", "m2"]
                assert middle.next_cursor is not None

                final = await get_history_page(
                    session, limit=2, before=middle.next_cursor
                )
                assert [i.content for i in final.items] == ["m0"]
                assert final.next_cursor is None

                # Response shape exactly items + next_cursor
                dumped = history_page_as_dict(final)
                assert set(dumped.keys()) == {"items", "next_cursor"}
                assert dumped["next_cursor"] is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_limit_one_and_limit_one_hundred(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                for i in range(3):
                    await _insert_with_time(
                        session,
                        role=CHAT_MESSAGE_ROLE_USER,
                        content=f"n{i}",
                        created_at=T0 + timedelta(seconds=i),
                    )
                await session.commit()

            async with factory() as session:
                page = await get_history_page(session, limit=1, before=None)
                assert len(page.items) == 1
                assert page.items[0].content == "n2"
                assert page.next_cursor is not None

                # limit=100 with only 3 rows: full set, no next_cursor
                full = await get_history_page(session, limit=100, before=None)
                assert len(full.items) == 3
                assert [i.content for i in full.items] == ["n0", "n1", "n2"]
                assert full.next_cursor is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_next_cursor_only_when_older_rows_exist(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await _insert_with_time(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="only",
                    created_at=T0,
                )
                await session.commit()

            async with factory() as session:
                page = await get_history_page(session, limit=50, before=None)
                assert len(page.items) == 1
                assert page.next_cursor is None
        finally:
            await engine.dispose()

    run_async(_body())


def test_service_rejects_malformed_before_cursor(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                with pytest.raises(ValueError):
                    await get_history_page(
                        session, limit=10, before="not-a-valid-cursor"
                    )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Hydration: runs + tools on user turn only; no tool role
# ---------------------------------------------------------------------------


def test_user_turn_run_and_tool_hydration(db_path: Path) -> None:
    """Runs/tools attach only via user_message_id; no tool-role items."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                user = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="please run tool",
                )
                assistant = await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_ASSISTANT,
                    content="done",
                )
                run = await runs_repo.create_run(
                    session, user_message_id=user.id
                )
                tool, created = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run.id,
                    tool_call_id="call_hydrate_1",
                    tool_name="stub_tool",
                    arguments_summary_json={"q": "x"},
                )
                assert created is True
                await tool_repo.mark_running(session, tool.id)
                result = ToolResult(
                    ok=True,
                    code=None,
                    summary="ok",
                    data={"n": 1},
                )
                await tool_repo.complete_execution(
                    session,
                    tool.id,
                    result=result,
                    duration_ms=12,
                )
                await runs_repo.complete_run(session, run.id)
                await session.commit()
                user_id, assistant_id, run_id = user.id, assistant.id, run.id

            async with factory() as session:
                page = await get_history_page(session, limit=50, before=None)
                assert isinstance(page, HistoryPage)
                assert set(history_page_as_dict(page).keys()) == {
                    "items",
                    "next_cursor",
                }
                assert all(item.role != "tool" for item in page.items)
                assert [i.id for i in page.items] == [user_id, assistant_id]

                user_item = page.items[0]
                assert user_item.role == CHAT_MESSAGE_ROLE_USER
                assert user_item.run is not None
                assert user_item.run.id == run_id
                assert user_item.run.user_message_id == user_id
                assert user_item.run.state == AGENT_RUN_STATE_COMPLETED
                assert len(user_item.run.tool_executions) == 1
                te = user_item.run.tool_executions[0]
                assert te.tool_call_id == "call_hydrate_1"
                assert te.tool_name == "stub_tool"
                assert te.status == "completed"
                assert te.duration_ms == 12
                assert te.result is not None
                assert te.result.ok is True
                assert te.result.data == {"n": 1}
                assert te.arguments_summary == {"q": "x"}

                # Assistant has no run attachment
                assert page.items[1].role == CHAT_MESSAGE_ROLE_ASSISTANT
                assert page.items[1].run is None

                # No tool result copied into chat message content/payload
                assert user_item.content == "please run tool"
                assert user_item.structured_payload is None
                assert page.items[1].content == "done"

                # Durable tool activity lives only on tool_executions
                count_tool_role = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM chat_messages WHERE role = 'tool'"
                        )
                    )
                ).scalar_one()
                assert int(count_tool_role) == 0
                assert all(m.conversation_id == CONVERSATION_ID for m in (
                    await messages_repo.list_messages(session)
                ))
        finally:
            await engine.dispose()

    run_async(_body())


def test_hydration_without_run_leaves_run_null(db_path: Path) -> None:
    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                await messages_repo.insert_message(
                    session,
                    role=CHAT_MESSAGE_ROLE_USER,
                    content="no run yet",
                )
                await session.commit()

            async with factory() as session:
                page = await get_history_page(session, limit=10)
                assert len(page.items) == 1
                assert page.items[0].run is None
                assert page.next_cursor is None
        finally:
            await engine.dispose()

    run_async(_body())

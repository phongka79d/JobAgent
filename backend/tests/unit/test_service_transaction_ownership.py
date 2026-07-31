from __future__ import annotations

import inspect
import sqlite3
from typing import Self

import pytest
from app.services import (
    chat_turns,
    cv_manager,
    cv_upload,
    profile_approval,
    profile_drafts,
    tool_execution,
)


@pytest.mark.parametrize(
    "module",
    (
        chat_turns,
        cv_manager,
        cv_upload,
        profile_approval,
        profile_drafts,
        tool_execution,
    ),
)
def test_service_reuses_shared_session_scope(module: object) -> None:
    source = inspect.getsource(module)
    assert "def _short_transaction" not in source
    assert "session_scope" in source


class _ImmediateSessionStub:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.execute_error = execute_error
        self.commit_error = commit_error
        self.events: list[str] = []
        self.rollback_calls = 0

    async def __aenter__(self) -> Self:
        self.events.append("enter")
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.events.append("exit")

    async def execute(self, statement: object) -> None:
        self.events.append(f"execute:{statement}")
        if self.execute_error is not None:
            raise self.execute_error

    async def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")
        self.rollback_calls += 1


class _SessionFactoryStub:
    def __init__(self, session: _ImmediateSessionStub) -> None:
        self.session = session

    def __call__(self) -> _ImmediateSessionStub:
        return self.session


def _sqlite_operational_error(message: str, code: int | None = None) -> Exception:
    error = sqlite3.OperationalError(message)
    if code is not None:
        error.sqlite_errorcode = code  # type: ignore[attr-defined]
    from sqlalchemy.exc import OperationalError

    return OperationalError("transaction", {}, error)


@pytest.mark.asyncio
async def test_immediate_scope_maps_busy_from_begin_before_yield() -> None:
    from app.db.session import ImmediateTransactionBusy, immediate_session_scope

    session = _ImmediateSessionStub(
        execute_error=_sqlite_operational_error("database is locked")
    )
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(_SessionFactoryStub(session)):
            pytest.fail("BEGIN IMMEDIATE must fail before yielding")
    assert session.events == ["enter", "execute:BEGIN IMMEDIATE", "rollback", "exit"]
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_immediate_scope_commits_after_body_without_rollback() -> None:
    from app.db.session import immediate_session_scope

    session = _ImmediateSessionStub()
    async with immediate_session_scope(_SessionFactoryStub(session)):
        assert session.events == ["enter", "execute:BEGIN IMMEDIATE"]
        session.events.append("body")
    assert session.events == [
        "enter",
        "execute:BEGIN IMMEDIATE",
        "body",
        "commit",
        "exit",
    ]
    assert session.rollback_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["body", "commit"])
async def test_immediate_scope_maps_busy_from_body_or_commit_once(
    phase: str,
) -> None:
    from app.db.session import ImmediateTransactionBusy, immediate_session_scope

    busy = _sqlite_operational_error("database is locked")
    session = _ImmediateSessionStub(commit_error=busy if phase == "commit" else None)
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(_SessionFactoryStub(session)):
            assert session.events[-1] == "execute:BEGIN IMMEDIATE"
            if phase == "body":
                raise busy
    assert session.rollback_calls == 1
    assert session.events.index("execute:BEGIN IMMEDIATE") < session.events.index(
        "commit" if phase == "commit" else "rollback"
    )


@pytest.mark.asyncio
async def test_immediate_scope_maps_busy_snapshot_code() -> None:
    from app.db.session import ImmediateTransactionBusy, immediate_session_scope

    busy_snapshot = _sqlite_operational_error("database snapshot is stale", 517)
    session = _ImmediateSessionStub(execute_error=busy_snapshot)
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(_SessionFactoryStub(session)):
            pytest.fail("busy snapshot must fail before yielding")


@pytest.mark.asyncio
async def test_immediate_scope_maps_extended_busy_code_without_message_fallback(
) -> None:
    from app.db.session import ImmediateTransactionBusy, immediate_session_scope

    extended_busy = _sqlite_operational_error("unclassified contention", 261)
    session = _ImmediateSessionStub(execute_error=extended_busy)
    with pytest.raises(ImmediateTransactionBusy):
        async with immediate_session_scope(_SessionFactoryStub(session)):
            pytest.fail("extended SQLite BUSY must fail before yielding")


@pytest.mark.asyncio
async def test_immediate_scope_reraises_unrelated_operational_error() -> None:
    from app.db.session import immediate_session_scope
    from sqlalchemy.exc import OperationalError

    unrelated = OperationalError(
        "transaction", {}, sqlite3.OperationalError("disk I/O error")
    )
    session = _ImmediateSessionStub(execute_error=unrelated)
    with pytest.raises(OperationalError) as raised:
        async with immediate_session_scope(_SessionFactoryStub(session)):
            pytest.fail("unrelated operational error must fail before yielding")
    assert raised.value is unrelated
    assert session.rollback_calls == 1

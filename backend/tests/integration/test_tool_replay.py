"""Integration tests for durable tool transitions and identity replay.

Uses a migrated temporary SQLite file (Alembic head). Proves repeated
``(run_id, tool_call_id)`` stores one row, invokes the side effect once, and
returns byte-equivalent validated ``ToolResult`` data for success and failure.
Also covers illegal transitions and mismatched result/error coupling. No second
idempotency key is introduced.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
    TOOL_EXECUTION_STATUS_PENDING,
    TOOL_EXECUTION_STATUS_RUNNING,
    ToolExecution,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import tool_executions as tool_repo
from app.repositories.tool_executions import (
    InvalidToolTransitionError,
    ToolResultCouplingError,
    load_stored_result,
    serialize_result,
)
from app.schemas.tools import ToolResult
from app.services.tool_execution import (
    ToolExecutionInProgressError,
    execute_tool,
)
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.support.db_migration import run_async, session_factory

TOOL_CALL_ID_OK = "call_success_001"
TOOL_CALL_ID_FAIL = "call_failure_001"
TOOL_NAME = "stub_side_effect"


@pytest.fixture
def db_path(migrated_sqlite: Path) -> Path:
    """Migrated isolated SQLite file (Alembic head + singleton seeds)."""
    return migrated_sqlite


async def _seed_run(session: AsyncSession, content: str = "tool turn") -> str:
    """Insert one user message + running agent run; return run_id."""
    user = await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content=content,
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    await session.flush()
    return run.id


async def _count_tool_rows(
    session: AsyncSession,
    *,
    run_id: str,
    tool_call_id: str,
) -> int:
    stmt = select(func.count()).select_from(ToolExecution).where(
        ToolExecution.run_id == run_id,
        ToolExecution.tool_call_id == tool_call_id,
    )
    return int((await session.execute(stmt)).scalar_one())


# ---------------------------------------------------------------------------
# Success / failure replay via service
# ---------------------------------------------------------------------------


def test_success_replay_one_row_one_invocation(db_path: Path) -> None:
    """Repeated identity: one row, one invoke, byte-equivalent success result."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "success path")
                await session.commit()

            invocations = {"n": 0}
            success_result = ToolResult(
                ok=True,
                code=None,
                summary="stub completed",
                data={"value": 42, "nested": ["a", 1]},
            )

            async def stub() -> ToolResult:
                invocations["n"] += 1
                return success_result

            first = await execute_tool(
                run_id=run_id,
                tool_call_id=TOOL_CALL_ID_OK,
                tool_name=TOOL_NAME,
                arguments_summary_json={"arg": "x"},
                invoke=stub,
                session_factory=factory,
            )
            second = await execute_tool(
                run_id=run_id,
                tool_call_id=TOOL_CALL_ID_OK,
                tool_name=TOOL_NAME,
                arguments_summary_json={"arg": "ignored-on-replay"},
                invoke=stub,
                session_factory=factory,
            )

            assert invocations["n"] == 1
            assert first.model_dump(mode="json") == second.model_dump(mode="json")
            assert first.model_dump(mode="json") == success_result.model_dump(
                mode="json"
            )
            # Byte-for-byte equivalence of validated JSON payloads.
            assert json.dumps(
                first.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ) == json.dumps(
                second.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )

            async with factory() as session:
                assert (
                    await _count_tool_rows(
                        session, run_id=run_id, tool_call_id=TOOL_CALL_ID_OK
                    )
                    == 1
                )
                row = await tool_repo.get_by_identity(
                    session, run_id=run_id, tool_call_id=TOOL_CALL_ID_OK
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
                assert row.duration_ms is not None
                assert row.duration_ms >= 0
                assert row.error_code is None
                assert row.result_json is not None
                stored = load_stored_result(row)
                assert stored.model_dump(mode="json") == success_result.model_dump(
                    mode="json"
                )
                assert row.result_json == serialize_result(success_result)
                # No tool-role chat message created by tool persistence path.
                tool_msgs = (
                    await session.execute(
                        text(
                            "SELECT COUNT(*) FROM chat_messages WHERE role = 'tool'"
                        )
                    )
                ).scalar_one()
                assert int(tool_msgs) == 0
        finally:
            await engine.dispose()

    run_async(_body())


def test_running_reentry_allowed_for_interrupt_tools(db_path: Path) -> None:
    """allow_running_reentry reuses the same running identity (no second row)."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "reentry path")
                await session.commit()

            gate = {"pass": 0}

            async def first_invoke() -> ToolResult:
                gate["pass"] += 1
                if gate["pass"] == 1:
                    # Simulate interrupt: leave running without terminalizing.
                    raise RuntimeError("simulated_interrupt_control")
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="resumed once",
                    data={"n": gate["pass"]},
                )

            with pytest.raises(RuntimeError, match="simulated_interrupt_control"):
                await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_reentry",
                    tool_name=TOOL_NAME,
                    invoke=first_invoke,
                    session_factory=factory,
                    allow_running_reentry=True,
                )

            async with factory() as session:
                row = await tool_repo.get_by_identity(
                    session, run_id=run_id, tool_call_id="call_reentry"
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_RUNNING
                assert (
                    await _count_tool_rows(
                        session, run_id=run_id, tool_call_id="call_reentry"
                    )
                    == 1
                )

            # Without reentry flag, running identity is rejected.
            async def noop() -> ToolResult:
                return ToolResult(ok=True, summary="should not run")

            with pytest.raises(ToolExecutionInProgressError):
                await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_reentry",
                    tool_name=TOOL_NAME,
                    invoke=noop,
                    session_factory=factory,
                    allow_running_reentry=False,
                )

            async def second_invoke() -> ToolResult:
                gate["pass"] += 1
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="resumed once",
                    data={"n": gate["pass"]},
                )

            result = await execute_tool(
                run_id=run_id,
                tool_call_id="call_reentry",
                tool_name=TOOL_NAME,
                invoke=second_invoke,
                session_factory=factory,
                allow_running_reentry=True,
            )
            assert result.ok is True
            assert result.data == {"n": 2}

            async with factory() as session:
                assert (
                    await _count_tool_rows(
                        session, run_id=run_id, tool_call_id="call_reentry"
                    )
                    == 1
                )
                row = await tool_repo.get_by_identity(
                    session, run_id=run_id, tool_call_id="call_reentry"
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
        finally:
            await engine.dispose()

    run_async(_body())


def test_failure_replay_one_row_one_invocation(db_path: Path) -> None:
    """Repeated identity: one row, one invoke, byte-equivalent failure result."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "failure path")
                await session.commit()

            invocations = {"n": 0}
            failure_result = ToolResult(
                ok=False,
                code="STUB_SIDE_EFFECT_FAILED",
                summary="stub failed on purpose",
                data={"reason": "counted"},
            )

            async def stub() -> ToolResult:
                invocations["n"] += 1
                return failure_result

            first = await execute_tool(
                run_id=run_id,
                tool_call_id=TOOL_CALL_ID_FAIL,
                tool_name=TOOL_NAME,
                invoke=stub,
                session_factory=factory,
            )
            second = await execute_tool(
                run_id=run_id,
                tool_call_id=TOOL_CALL_ID_FAIL,
                tool_name=TOOL_NAME,
                invoke=stub,
                session_factory=factory,
            )

            assert invocations["n"] == 1
            assert first.model_dump(mode="json") == second.model_dump(mode="json")
            assert first.ok is False
            assert first.code == "STUB_SIDE_EFFECT_FAILED"
            assert json.dumps(
                first.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ) == json.dumps(
                second.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            )

            async with factory() as session:
                assert (
                    await _count_tool_rows(
                        session, run_id=run_id, tool_call_id=TOOL_CALL_ID_FAIL
                    )
                    == 1
                )
                row = await tool_repo.get_by_identity(
                    session, run_id=run_id, tool_call_id=TOOL_CALL_ID_FAIL
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_FAILED
                assert row.error_code == "STUB_SIDE_EFFECT_FAILED"
                assert row.error_code == first.code
                assert row.duration_ms is not None
                assert row.duration_ms >= 0
                stored = load_stored_result(row)
                assert stored.model_dump(mode="json") == failure_result.model_dump(
                    mode="json"
                )
        finally:
            await engine.dispose()

    run_async(_body())


def test_get_or_create_returns_same_row_without_second_insert(
    db_path: Path,
) -> None:
    """Repository get-or-create is identity-stable under the unique constraint."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session)
                a, created_a = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call_stable",
                    tool_name=TOOL_NAME,
                )
                b, created_b = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call_stable",
                    tool_name=TOOL_NAME,
                )
                await session.commit()
                assert created_a is True
                assert created_b is False
                assert a.id == b.id
                assert a.status == TOOL_EXECUTION_STATUS_PENDING
                assert (
                    await _count_tool_rows(
                        session, run_id=run_id, tool_call_id="call_stable"
                    )
                    == 1
                )
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Illegal transitions and coupling
# ---------------------------------------------------------------------------


def test_illegal_transitions_rejected(db_path: Path) -> None:
    """Skipped, backward, and terminal transitions are rejected."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "illegal transitions")
                pending, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call_illegal",
                    tool_name=TOOL_NAME,
                )
                ok = ToolResult(ok=True, summary="should not apply")
                fail = ToolResult(
                    ok=False, code="X", summary="should not apply"
                )

                # pending → completed (skip running)
                with pytest.raises(InvalidToolTransitionError):
                    await tool_repo.complete_execution(
                        session, pending.id, result=ok, duration_ms=1
                    )
                # pending → failed (skip running)
                with pytest.raises(InvalidToolTransitionError):
                    await tool_repo.fail_execution(
                        session, pending.id, result=fail, duration_ms=1
                    )

                running = await tool_repo.mark_running(session, pending.id)
                assert running.status == TOOL_EXECUTION_STATUS_RUNNING

                # running → pending is not a repository method; complete works
                done = await tool_repo.complete_execution(
                    session, running.id, result=ok, duration_ms=5
                )
                assert done.status == TOOL_EXECUTION_STATUS_COMPLETED

                # terminal → anything
                with pytest.raises(InvalidToolTransitionError):
                    await tool_repo.mark_running(session, done.id)
                with pytest.raises(InvalidToolTransitionError):
                    await tool_repo.complete_execution(
                        session, done.id, result=ok, duration_ms=1
                    )
                with pytest.raises(InvalidToolTransitionError):
                    await tool_repo.fail_execution(
                        session, done.id, result=fail, duration_ms=1
                    )
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_mismatched_result_error_coupling_rejected(db_path: Path) -> None:
    """Completed requires success result/no error; failed requires matching code."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "coupling")
                row, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call_couple",
                    tool_name=TOOL_NAME,
                )
                await tool_repo.mark_running(session, row.id)

                bad_for_complete = ToolResult(
                    ok=False, code="SHOULD_NOT", summary="not success"
                )
                with pytest.raises(ToolResultCouplingError):
                    await tool_repo.complete_execution(
                        session,
                        row.id,
                        result=bad_for_complete,
                        duration_ms=1,
                    )

                bad_for_fail = ToolResult(ok=True, summary="not failure")
                with pytest.raises(ToolResultCouplingError):
                    await tool_repo.fail_execution(
                        session,
                        row.id,
                        result=bad_for_fail,
                        duration_ms=1,
                    )

                # Still running after rejected coupling attempts
                reloaded = await tool_repo.get_by_id(session, row.id)
                assert reloaded is not None
                assert reloaded.status == TOOL_EXECUTION_STATUS_RUNNING
                assert reloaded.result_json is None
                assert reloaded.error_code is None
                assert reloaded.duration_ms is None

                good_fail = ToolResult(
                    ok=False, code="STABLE_CODE", summary="failed correctly"
                )
                failed = await tool_repo.fail_execution(
                    session, row.id, result=good_fail, duration_ms=3
                )
                assert failed.status == TOOL_EXECUTION_STATUS_FAILED
                assert failed.error_code == "STABLE_CODE"
                assert failed.result_json == serialize_result(good_fail)
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


def test_approved_status_path_pending_running_completed(db_path: Path) -> None:
    """Durable state moves only through pending → running → completed."""

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "status path")
                row, _ = await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id="call_path",
                    tool_name=TOOL_NAME,
                )
                assert row.status == TOOL_EXECUTION_STATUS_PENDING
                assert row.duration_ms is None
                assert row.result_json is None
                assert row.error_code is None

                running = await tool_repo.mark_running(session, row.id)
                assert running.status == TOOL_EXECUTION_STATUS_RUNNING
                assert running.duration_ms is None
                assert running.result_json is None

                result = ToolResult(
                    ok=True, summary="path ok", data={"done": True}
                )
                done = await tool_repo.complete_execution(
                    session, running.id, result=result, duration_ms=10
                )
                assert done.status == TOOL_EXECUTION_STATUS_COMPLETED
                assert done.duration_ms == 10
                assert done.error_code is None
                assert done.result_json == serialize_result(result)
                await session.commit()
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# tool_status publication seam (03C) — durable transitions only
# ---------------------------------------------------------------------------


def test_execute_tool_publishes_ordered_statuses_and_terminal_replay(
    db_path: Path,
) -> None:
    """Listener sees pending/running/completed once; replay projects terminal only."""
    from app.services.tool_execution import (
        ToolStatusPublication,
        tool_status_publication_scope,
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "status pub")
                await session.commit()

            pubs: list[ToolStatusPublication] = []

            def _listen(pub: ToolStatusPublication) -> None:
                pubs.append(pub)

            success = ToolResult(
                ok=True,
                code=None,
                summary="published ok",
                data={"value": 1},
            )
            invocations = {"n": 0}

            async def stub() -> ToolResult:
                invocations["n"] += 1
                return success

            with tool_status_publication_scope(_listen):
                first = await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_pub_1",
                    tool_name=TOOL_NAME,
                    invoke=stub,
                    session_factory=factory,
                )
            assert first.ok is True
            assert [p.status for p in pubs] == ["pending", "running", "completed"]
            assert len({p.tool_execution_id for p in pubs}) == 1
            terminal = pubs[-1]
            assert terminal.duration_ms is not None
            assert terminal.duration_ms >= 0
            assert terminal.summary == "published ok"
            assert terminal.error_code is None
            assert terminal.tool_call_id == "call_pub_1"
            assert invocations["n"] == 1

            pubs.clear()
            with tool_status_publication_scope(_listen):
                second = await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_pub_1",
                    tool_name=TOOL_NAME,
                    invoke=stub,
                    session_factory=factory,
                )
            assert second.model_dump(mode="json") == first.model_dump(mode="json")
            assert invocations["n"] == 1
            # Terminal replay projects stored truth once — no side effect.
            assert [p.status for p in pubs] == ["completed"]
            assert pubs[0].tool_execution_id == terminal.tool_execution_id
            assert pubs[0].duration_ms == terminal.duration_ms
            assert pubs[0].summary == "published ok"
        finally:
            await engine.dispose()

    run_async(_body())


def test_execute_tool_publishes_failed_coupling(db_path: Path) -> None:
    from app.services.tool_execution import (
        ToolStatusPublication,
        tool_status_publication_scope,
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "fail pub")
                await session.commit()

            pubs: list[ToolStatusPublication] = []

            async def stub() -> ToolResult:
                return ToolResult(
                    ok=False,
                    code="PUB_FAIL",
                    summary="failed summary",
                    data=None,
                )

            with tool_status_publication_scope(pubs.append):
                await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_pub_fail",
                    tool_name=TOOL_NAME,
                    invoke=stub,
                    session_factory=factory,
                )
            assert [p.status for p in pubs] == ["pending", "running", "failed"]
            failed = pubs[-1]
            assert failed.error_code == "PUB_FAIL"
            assert failed.summary == "failed summary"
            assert failed.duration_ms is not None
        finally:
            await engine.dispose()

    run_async(_body())


def test_running_reentry_publishes_terminal_only_on_resume(db_path: Path) -> None:
    """Interrupt path: pending/running then resume terminalizes without re-pending."""
    from app.services.tool_execution import (
        ToolStatusPublication,
        tool_status_publication_scope,
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "reentry pub")
                await session.commit()

            pubs: list[ToolStatusPublication] = []
            gate = {"pass": 0}

            async def first_invoke() -> ToolResult:
                gate["pass"] += 1
                raise RuntimeError("simulated_interrupt_control")

            with tool_status_publication_scope(pubs.append):
                with pytest.raises(RuntimeError, match="simulated_interrupt_control"):
                    await execute_tool(
                        run_id=run_id,
                        tool_call_id="call_reentry_pub",
                        tool_name=TOOL_NAME,
                        invoke=first_invoke,
                        session_factory=factory,
                        allow_running_reentry=True,
                    )
            assert [p.status for p in pubs] == ["pending", "running"]
            exec_id = pubs[0].tool_execution_id

            pubs.clear()

            async def second_invoke() -> ToolResult:
                gate["pass"] += 1
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="resumed terminal",
                    data={"n": gate["pass"]},
                )

            with tool_status_publication_scope(pubs.append):
                result = await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_reentry_pub",
                    tool_name=TOOL_NAME,
                    invoke=second_invoke,
                    session_factory=factory,
                    allow_running_reentry=True,
                )
            assert result.ok is True
            assert [p.status for p in pubs] == ["completed"]
            assert pubs[0].tool_execution_id == exec_id
            assert pubs[0].summary == "resumed terminal"
        finally:
            await engine.dispose()

    run_async(_body())


def test_publish_matches_committed_sqlite_via_separate_reader(db_path: Path) -> None:
    """Listener never observes uncommitted/stale advertised state.

    At each publish, a separate sqlite3 connection reads committed status only
    (A2 durable-visibility probe). Async reader tasks can race past the short
    pending window; a blocking separate-connection read cannot.
    """
    import sqlite3

    from app.services.tool_execution import (
        ToolStatusPublication,
        tool_status_publication_scope,
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "commit visibility")
                await session.commit()

            published_vs_persisted: list[tuple[str, str | None]] = []

            def _listen(pub: ToolStatusPublication) -> None:
                # Separate process-local connection: sees only committed rows.
                conn = sqlite3.connect(str(db_path))
                try:
                    row = conn.execute(
                        "SELECT status FROM tool_executions WHERE id = ?",
                        (pub.tool_execution_id,),
                    ).fetchone()
                    published_vs_persisted.append(
                        (pub.status, None if row is None else str(row[0]))
                    )
                finally:
                    conn.close()

            async def stub() -> ToolResult:
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="visible after commit",
                    data={"v": 1},
                )

            with tool_status_publication_scope(_listen):
                await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_commit_vis",
                    tool_name=TOOL_NAME,
                    invoke=stub,
                    session_factory=factory,
                )

            assert published_vs_persisted == [
                ("pending", "pending"),
                ("running", "running"),
                ("completed", "completed"),
            ]
            assert all(p == d for p, d in published_vs_persisted)
        finally:
            await engine.dispose()

    run_async(_body())


def test_overlapping_identities_gather_isolated_order_and_replay(
    db_path: Path,
) -> None:
    """True concurrent execute_tool identities via asyncio.gather.

    Proves per-identity status order, distinct durable execution IDs, no
    cross-identity listener pollution, and same-identity replay with no second
    side effect under race with an overlapping peer.
    """
    import asyncio

    from app.services.tool_execution import (
        ToolStatusPublication,
        tool_status_publication_scope,
    )

    async def _body() -> None:
        engine = build_async_engine(db_path)
        factory = session_factory(engine)
        try:
            async with factory() as session:
                run_id = await _seed_run(session, "gather concurrent")
                await session.commit()

            barrier = asyncio.Barrier(2)
            side: dict[str, int] = {"a": 0, "b": 0}
            pubs: list[ToolStatusPublication] = []

            async def invoke_a() -> ToolResult:
                await barrier.wait()
                side["a"] += 1
                return ToolResult(
                    ok=True, code=None, summary="A done", data={"who": "a"}
                )

            async def invoke_b() -> ToolResult:
                await barrier.wait()
                side["b"] += 1
                return ToolResult(
                    ok=True, code=None, summary="B done", data={"who": "b"}
                )

            with tool_status_publication_scope(pubs.append):
                results = await asyncio.gather(
                    execute_tool(
                        run_id=run_id,
                        tool_call_id="call_gather_a",
                        tool_name=TOOL_NAME,
                        invoke=invoke_a,
                        session_factory=factory,
                    ),
                    execute_tool(
                        run_id=run_id,
                        tool_call_id="call_gather_b",
                        tool_name=TOOL_NAME,
                        invoke=invoke_b,
                        session_factory=factory,
                    ),
                )
            assert all(r.ok for r in results)
            assert side == {"a": 1, "b": 1}

            by_call: dict[str, list[str]] = {}
            exec_by_call: dict[str, set[str]] = {}
            for p in pubs:
                by_call.setdefault(p.tool_call_id, []).append(p.status)
                exec_by_call.setdefault(p.tool_call_id, set()).add(
                    p.tool_execution_id
                )
            assert by_call["call_gather_a"] == ["pending", "running", "completed"]
            assert by_call["call_gather_b"] == ["pending", "running", "completed"]
            assert len(exec_by_call["call_gather_a"]) == 1
            assert len(exec_by_call["call_gather_b"]) == 1
            assert exec_by_call["call_gather_a"].isdisjoint(
                exec_by_call["call_gather_b"]
            )

            # Same-identity replay: no second side effect for A.
            pubs.clear()
            with tool_status_publication_scope(pubs.append):
                replay = await execute_tool(
                    run_id=run_id,
                    tool_call_id="call_gather_a",
                    tool_name=TOOL_NAME,
                    invoke=invoke_a,
                    session_factory=factory,
                )
            assert replay.summary == "A done"
            assert side["a"] == 1
            assert [p.status for p in pubs] == ["completed"]
            assert pubs[0].tool_call_id == "call_gather_a"
            assert pubs[0].tool_execution_id in exec_by_call["call_gather_a"]
        finally:
            await engine.dispose()

    run_async(_body())


# ---------------------------------------------------------------------------
# Static / ownership invariants
# ---------------------------------------------------------------------------


def test_repository_does_not_commit_or_open_session() -> None:
    """Repository methods accept a session and do not finalize transactions."""
    for name in (
        "get_or_create_pending",
        "mark_running",
        "complete_execution",
        "fail_execution",
        "get_by_identity",
    ):
        fn = getattr(tool_repo, name)
        source = inspect.getsource(fn)
        assert "commit(" not in source
        assert "session_scope" not in source
        assert "get_session_factory" not in source
        assert "create_async_engine" not in source


def test_no_second_idempotency_key_in_tool_modules() -> None:
    """Only (run_id, tool_call_id) / result_json identity — no second key."""
    for path in (
        Path("app/repositories/tool_executions.py"),
        Path("app/services/tool_execution.py"),
    ):
        text_src = path.read_text(encoding="utf-8")
        # No second-key field, parameter, or column name.
        assert "idempotency_key" not in text_src
        assert "tool_call_id" in text_src
        assert "run_id" in text_src
    # result_json is the durable result store (repository owns serialization)
    repo_src = Path("app/repositories/tool_executions.py").read_text(encoding="utf-8")
    assert "result_json" in repo_src
    assert "serialize_result" in repo_src


def test_no_create_all_or_provider_in_tool_modules() -> None:
    for path in (
        Path("app/repositories/tool_executions.py"),
        Path("app/services/tool_execution.py"),
    ):
        text_src = path.read_text(encoding="utf-8")
        assert "create_all" not in text_src
        assert "ChatOpenAI" not in text_src
        assert "httpx" not in text_src
        assert "shopaikey" not in text_src.lower()

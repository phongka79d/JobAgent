"""Metadata tests for chat-family ORM contracts (migrations: task 02E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base
from app.db.models import chat as m
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects import sqlite
from sqlalchemy.sql.schema import Column, Table

_MODELS = (m.Conversation, m.ChatMessage, m.AgentRun, m.ToolExecution)
_NAMES = {
    m.Conversation: "conversation",
    m.ChatMessage: "chat_messages",
    m.AgentRun: "agent_runs",
    m.ToolExecution: "tool_executions",
}
_COLS: dict[str, tuple[set[str], set[str], str]] = {
    "conversation": ({"id", "created_at", "updated_at"}, set(), "pk_conversation"),
    "chat_messages": (
        {
            "id", "conversation_id", "role", "content", "structured_payload",
            "created_at", "updated_at",
        },
        {"structured_payload"},
        "pk_chat_messages",
    ),
    "agent_runs": (
        {
            "id", "user_message_id", "state", "pending_approval_json", "error_code",
            "completed_at", "created_at", "updated_at",
        },
        {"pending_approval_json", "error_code", "completed_at"},
        "pk_agent_runs",
    ),
    "tool_executions": (
        {
            "id", "run_id", "tool_call_id", "tool_name", "arguments_summary_json",
            "status", "duration_ms", "error_code", "result_json", "created_at",
            "updated_at",
        },
        {"arguments_summary_json", "duration_ms", "error_code", "result_json"},
        "pk_tool_executions",
    ),
}
_CHECKS: dict[str, dict[str, tuple[str, ...]]] = {
    "conversation": {"ck_conversation__singleton_id": (m.CONVERSATION_ID,)},
    "chat_messages": {
        "ck_chat_messages__role": tuple(m.CHAT_MESSAGE_ROLES),
        "ck_chat_messages__content_payload_coupling": ("content", "structured_payload"),
    },
    "agent_runs": {
        "ck_agent_runs__state": tuple(m.AGENT_RUN_STATES),
        "ck_agent_runs__pending_approval_coupling": (
            m.AGENT_RUN_STATE_INTERRUPTED, "pending_approval_json",
        ),
        "ck_agent_runs__completed_at_coupling": (
            m.AGENT_RUN_STATE_COMPLETED, m.AGENT_RUN_STATE_FAILED, "completed_at",
        ),
    },
    "tool_executions": {
        "ck_tool_executions__status": tuple(m.TOOL_EXECUTION_STATUSES),
        "ck_tool_executions__duration_ms_non_negative": ("duration_ms",),
        "ck_tool_executions__terminal_result_duration": (
            m.TOOL_EXECUTION_STATUS_COMPLETED, m.TOOL_EXECUTION_STATUS_FAILED,
            "duration_ms", "result_json",
        ),
        "ck_tool_executions__error_coupling": (
            m.TOOL_EXECUTION_STATUS_FAILED, "error_code",
        ),
    },
}
_FKS = (
    ("chat_messages", "fk_chat_messages__conversation_id", "conversation_id",
     "conversation", "id", "CASCADE"),
    ("agent_runs", "fk_agent_runs__user_message_id", "user_message_id",
     "chat_messages", "id", "CASCADE"),
    ("tool_executions", "fk_tool_executions__run_id", "run_id",
     "agent_runs", "id", "CASCADE"),
)
_IXS = (
    ("chat_messages", "ix_chat_messages__conversation_created_at",
     ["conversation_id", "created_at", "id"]),
    ("agent_runs", "ix_agent_runs__state", ["state"]),
    ("tool_executions", "ix_tool_executions__run_status", ["run_id", "status"]),
)


def _t(name: str) -> Table:
    return Base.metadata.tables[name]


def _c(table: Table, name: str) -> Column[Any]:
    return table.c[name]


def _sql(clause: Any) -> str:
    if isinstance(clause, str):
        return clause
    kw = {"literal_binds": True}
    return str(clause.compile(dialect=sqlite.dialect(), compile_kwargs=kw)).replace(
        "\n", " "
    )


def _check_sql(table: Table) -> dict[str, str]:
    return {
        str(c.name): _sql(c.sqltext)
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def _default_name(col: Column[Any]) -> str:
    assert col.default is not None and callable(col.default.arg)
    return getattr(col.default.arg, "__wrapped__", col.default.arg).__name__


def _assert_cols(table: Table, expected: set[str], nullable: set[str]) -> None:
    assert set(table.c.keys()) == expected
    for name in expected - nullable:
        assert _c(table, name).nullable is False, name
    for name in nullable:
        assert _c(table, name).nullable is True, name


def _assert_utc(table: Table) -> None:
    for name in ("created_at", "updated_at"):
        col = _c(table, name)
        assert _default_name(col) == "utc_now"
        assert col.type.timezone is True  # type: ignore[attr-defined]


def _assert_checks(table: Table, needles: dict[str, tuple[str, ...]]) -> None:
    sql = _check_sql(table)
    assert set(sql) == set(needles)
    for name, parts in needles.items():
        for needle in parts:
            assert needle in sql[name], (name, needle, sql[name])


def _assert_const_default(col: Column[Any], value: str) -> None:
    assert col.default is not None and col.default.arg == value
    assert col.server_default is not None
    assert value in str(col.server_default.arg)


def _assert_json(table: Table, *names: str) -> None:
    for name in names:
        assert "JSON" in str(_c(table, name).type).upper()


def _uq_names(table: Table) -> set[str | None]:
    return {c.name for c in table.constraints if isinstance(c, UniqueConstraint)}


def test_chat_models_register_on_shared_base() -> None:
    assert set(_NAMES.values()).issubset(set(Base.metadata.tables))
    for model, tablename in _NAMES.items():
        assert issubclass(model, Base)
        assert model.metadata is Base.metadata
        assert model.__tablename__ == tablename


@pytest.mark.parametrize("table_name", sorted(_COLS))
def test_chat_table_columns_pk_utc_and_checks(table_name: str) -> None:
    cols, nullable, pk = _COLS[table_name]
    table = _t(table_name)
    _assert_cols(table, cols, nullable)
    assert table.primary_key is not None and table.primary_key.name == pk
    _assert_utc(table)
    _assert_checks(table, _CHECKS[table_name])


def test_conversation_singleton_id_default() -> None:
    table = _t("conversation")
    assert _c(table, "id").primary_key
    assert m.CONVERSATION_ID == "main"
    _assert_const_default(_c(table, "id"), m.CONVERSATION_ID)


def test_chat_messages_role_payload_and_uuid() -> None:
    table = _t("chat_messages")
    assert _default_name(_c(table, "id")) == "new_uuid"
    uuid_val = new_uuid()
    assert isinstance(uuid_val, str) and uuid_val == uuid_val.lower()
    assert len(uuid_val) == 36
    _assert_json(table, "structured_payload")
    assert m.CHAT_MESSAGE_ROLES == frozenset(
        {
            m.CHAT_MESSAGE_ROLE_USER,
            m.CHAT_MESSAGE_ROLE_ASSISTANT,
            m.CHAT_MESSAGE_ROLE_SYSTEM,
        }
    )
    assert "tool" not in m.CHAT_MESSAGE_ROLES
    # No persisted provider tool-role message vocabulary.
    assert "tool" not in _check_sql(table)["ck_chat_messages__role"]


def test_agent_runs_state_unique_and_completed_at() -> None:
    table = _t("agent_runs")
    assert _default_name(_c(table, "id")) == "new_uuid"
    _assert_json(table, "pending_approval_json")
    completed = _c(table, "completed_at")
    assert completed.nullable is True
    assert completed.type.timezone is True  # type: ignore[attr-defined]
    assert m.AGENT_RUN_STATES == frozenset(
        {
            m.AGENT_RUN_STATE_RUNNING, m.AGENT_RUN_STATE_INTERRUPTED,
            m.AGENT_RUN_STATE_COMPLETED, m.AGENT_RUN_STATE_FAILED,
        }
    )
    assert m.AGENT_RUN_STATE_DEFAULT == m.AGENT_RUN_STATE_RUNNING == "running"
    _assert_const_default(_c(table, "state"), m.AGENT_RUN_STATE_DEFAULT)
    assert _c(table, "user_message_id").unique is True
    assert "uq_agent_runs__user_message_id" in _uq_names(table)


def test_tool_executions_status_unique_and_types() -> None:
    table = _t("tool_executions")
    assert _default_name(_c(table, "id")) == "new_uuid"
    assert str(_c(table, "duration_ms").type).upper().startswith("INT")
    _assert_json(table, "arguments_summary_json", "result_json")
    assert m.TOOL_EXECUTION_STATUSES == frozenset(
        {
            m.TOOL_EXECUTION_STATUS_PENDING, m.TOOL_EXECUTION_STATUS_RUNNING,
            m.TOOL_EXECUTION_STATUS_COMPLETED, m.TOOL_EXECUTION_STATUS_FAILED,
        }
    )
    assert (
        m.TOOL_EXECUTION_STATUS_DEFAULT
        == m.TOOL_EXECUTION_STATUS_PENDING
        == "pending"
    )
    _assert_const_default(_c(table, "status"), m.TOOL_EXECUTION_STATUS_DEFAULT)
    assert "uq_tool_executions__run_tool_call" in _uq_names(table)
    uq = next(
        c
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
        and c.name == "uq_tool_executions__run_tool_call"
    )
    assert [col.name for col in uq.columns] == ["run_id", "tool_call_id"]


def test_chat_family_fks_and_indexes() -> None:
    for table_name, fk_name, column, parent, parent_col, ondelete in _FKS:
        fks = [
            c
            for c in _t(table_name).constraints
            if isinstance(c, ForeignKeyConstraint)
        ]
        assert len(fks) == 1
        fk, el = fks[0], list(fks[0].elements)
        assert fk.name == fk_name and len(el) == 1
        assert el[0].parent.name == column
        assert el[0].column.table.name == parent
        assert el[0].column.name == parent_col
        assert el[0].ondelete == ondelete
    for table_name, ix_name, columns in _IXS:
        matches = [ix for ix in _t(table_name).indexes if ix.name == ix_name]
        assert len(matches) == 1
        ix = matches[0]
        assert isinstance(ix, Index) and ix.unique is False
        assert [c.name for c in ix.columns] == columns


def test_chat_models_no_checkpoint_tool_role_or_service_behavior() -> None:
    for forbidden in (
        "checkpoints", "checkpoint_blobs", "checkpoint_writes",
        "checkpoint_migrations", "langgraph_checkpoints", "score_cache",
        "match_scores", "idempotency_keys",
    ):
        assert forbidden not in Base.metadata.tables
    banned = {
        "stream", "sse", "checkpoint", "invoke_tool", "approve",
        "resume_run", "send_message", "idempotency",
    }
    for model in _MODELS:
        public = {n for n in dir(model) if not n.startswith("_")}
        assert banned.isdisjoint(public), model.__name__
    # Role enum is only user|assistant|system — no durable tool role.
    role_sql = _check_sql(_t("chat_messages"))["ck_chat_messages__role"]
    assert m.CHAT_MESSAGE_ROLE_USER in role_sql
    assert m.CHAT_MESSAGE_ROLE_ASSISTANT in role_sql
    assert m.CHAT_MESSAGE_ROLE_SYSTEM in role_sql
    assert "tool" not in role_sql
    ts = utc_now()
    assert isinstance(ts, datetime) and ts.tzinfo is not None

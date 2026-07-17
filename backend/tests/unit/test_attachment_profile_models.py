"""Metadata tests for attachment/profile ORM contracts (migrations: task 02E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base
from app.db.models import Attachment, CandidateProfile, JobPreferences, ProfileDraft
from app.db.models.attachments import (
    ATTACHMENT_MIME_TYPE_PDF,
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_ARCHIVED,
    ATTACHMENT_STATE_DEFAULT,
    ATTACHMENT_STATE_DELETING,
    ATTACHMENT_STATE_FAILED,
    ATTACHMENT_STATE_STAGED,
    ATTACHMENT_STATES,
)
from app.db.models.profiles import (
    CANDIDATE_PROFILE_ID,
    JOB_PREFERENCE_KEYS,
    JOB_PREFERENCES_ID,
    PROFILE_DRAFT_ID,
    _empty_job_preferences,
)
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects import sqlite
from sqlalchemy.sql.schema import Column, Table

_MODELS = (Attachment, CandidateProfile, ProfileDraft, JobPreferences)
_ATTACHMENT_COLS = {
    "id", "file_hash", "original_name", "mime_type", "size_bytes", "page_count",
    "storage_path", "state", "failure_code", "created_at", "updated_at",
}
_ATTACHMENT_NOT_NULL = _ATTACHMENT_COLS - {"page_count", "failure_code"}
_CANDIDATE_COLS = {
    "id", "active_attachment_id", "profile_json", "created_at", "updated_at",
}
_DRAFT_COLS = {
    "id", "source_attachment_id", "draft_json", "created_at", "updated_at",
}
_PREF_COLS = {"id", "preferences_json", "created_at", "updated_at"}


def _t(name: str) -> Table:
    return Base.metadata.tables[name]


def _c(table: Table, name: str) -> Column[Any]:
    return table.c[name]


def _literal_sql(clause: Any) -> str:
    if isinstance(clause, str):
        return clause
    return str(clause.compile(
        dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True},
    )).replace("\n", " ")


def _check_sql(table: Table) -> dict[str, str]:
    return {
        str(c.name): _literal_sql(c.sqltext) for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def _uq(table: Table) -> set[str | None]:
    return {c.name for c in table.constraints if isinstance(c, UniqueConstraint)}


def _fk(table: Table) -> ForeignKeyConstraint:
    fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
    assert len(fks) == 1
    return fks[0]


def _default_name(col: Column[Any]) -> str:
    assert col.default is not None and callable(col.default.arg)
    return getattr(col.default.arg, "__wrapped__", col.default.arg).__name__


def _assert_cols(
    table: Table,
    expected: set[str],
    *,
    not_null: set[str] | None = None,
    nullable: set[str] | None = None,
) -> None:
    assert set(table.c.keys()) == expected
    for name in not_null if not_null is not None else expected:
        assert _c(table, name).nullable is False, name
    for name in nullable or ():
        assert _c(table, name).nullable is True, name


def _assert_utc(table: Table, *names: str) -> None:
    for name in names:
        col = _c(table, name)
        assert _default_name(col) == "utc_now"
        assert col.type.timezone is True  # type: ignore[attr-defined]


def _assert_singleton(table: Table, table_name: str, value: str) -> None:
    sql = _check_sql(table)
    key = f"ck_{table_name}__singleton_id"
    assert key in sql and value in sql[key]


def _assert_att_fk(
    table: Table, *, name: str, column: str, ondelete: str, uq: str
) -> None:
    fk = _fk(table)
    assert fk.name == name
    el = list(fk.elements)
    assert len(el) == 1
    assert el[0].column.table.name == "attachments"
    assert el[0].column.name == "id"
    assert el[0].ondelete == ondelete
    assert uq in _uq(table)
    assert _c(table, column).unique is True


def test_registry_and_shared_base() -> None:
    expected = {
        "attachments", "candidate_profile", "profile_drafts", "job_preferences",
    }
    assert expected.issubset(set(Base.metadata.tables))
    for model in _MODELS:
        assert issubclass(model, Base) and model.metadata is Base.metadata


def test_attachment_columns_defaults_and_types() -> None:
    table = _t("attachments")
    _assert_cols(
        table, _ATTACHMENT_COLS,
        not_null=_ATTACHMENT_NOT_NULL,
        nullable={"page_count", "failure_code"},
    )
    assert _c(table, "id").primary_key
    assert str(_c(table, "id").type) in {"TEXT", "VARCHAR"}
    assert str(_c(table, "size_bytes").type).upper().startswith("INT")
    assert str(_c(table, "page_count").type).upper().startswith("INT")
    state = _c(table, "state")
    assert state.default is not None or state.server_default is not None
    if state.default is not None and state.default.arg is not None:
        assert state.default.arg == ATTACHMENT_STATE_DEFAULT
    if state.server_default is not None:
        assert ATTACHMENT_STATE_DEFAULT in str(state.server_default.arg)
    assert _default_name(_c(table, "id")) == "new_uuid"
    uuid_val = new_uuid()
    assert isinstance(uuid_val, str) and uuid_val == uuid_val.lower()
    assert len(uuid_val) == 36
    _assert_utc(table, "created_at", "updated_at")
    ts = utc_now()
    assert isinstance(ts, datetime) and ts.tzinfo is not None


def test_attachment_uniques_checks_partial_index() -> None:
    table = _t("attachments")
    assert _c(table, "file_hash").unique and _c(table, "storage_path").unique
    names = _uq(table)
    assert "uq_attachments__file_hash" in names
    assert "uq_attachments__storage_path" in names
    sql = _check_sql(table)
    checks = {
        "ck_attachments__mime_type": (ATTACHMENT_MIME_TYPE_PDF,),
        "ck_attachments__size_bytes_positive": ("size_bytes > 0",),
        "ck_attachments__page_count_positive": ("page_count",),
        "ck_attachments__state": tuple(ATTACHMENT_STATES),
        "ck_attachments__failure_coupling": ("failure_code", ATTACHMENT_STATE_FAILED),
        "ck_attachments__active_requires_page_count": (
            ATTACHMENT_STATE_ACTIVE, "page_count",
        ),
    }
    for name, needles in checks.items():
        assert name in sql
        for needle in needles:
            assert needle in sql[name]
    partial = [ix for ix in table.indexes if ix.name == "uq_attachments__single_active"]
    assert len(partial) == 1
    ix = partial[0]
    assert ix.unique is True
    assert [c.name if hasattr(c, "name") else str(c) for c in ix.columns] == ["state"]
    where = ix.dialect_options.get("sqlite", {}).get("where")
    assert where is not None
    predicate = _literal_sql(where)
    assert "state" in predicate and ATTACHMENT_STATE_ACTIVE in predicate
    partial_unique = [
        p for p in table.indexes
        if p.unique and p.dialect_options.get("sqlite", {}).get("where") is not None
    ]
    assert len(partial_unique) == 1 and isinstance(partial_unique[0], Index)


def test_attachment_pk_constants_and_construct_defaults() -> None:
    table = _t("attachments")
    assert table.primary_key is not None
    assert table.primary_key.name == "pk_attachments"
    assert ATTACHMENT_STATES == frozenset({
        ATTACHMENT_STATE_STAGED,
        ATTACHMENT_STATE_ACTIVE,
        ATTACHMENT_STATE_ARCHIVED,
        ATTACHMENT_STATE_FAILED,
        ATTACHMENT_STATE_DELETING,
    })
    assert ATTACHMENT_MIME_TYPE_PDF == "application/pdf"
    assert ATTACHMENT_STATE_DEFAULT == ATTACHMENT_STATE_STAGED == "staged"
    assert ATTACHMENT_STATE_DELETING == "deleting"
    assert _default_name(Attachment.__table__.c.id) == "new_uuid"
    state_default = Attachment.__table__.c.state.default
    assert state_default is not None and state_default.arg == ATTACHMENT_STATE_DEFAULT
    _assert_utc(Attachment.__table__, "created_at", "updated_at")


def test_candidate_profile_contract() -> None:
    table = _t("candidate_profile")
    _assert_cols(table, _CANDIDATE_COLS)
    assert _c(table, "id").primary_key
    assert CANDIDATE_PROFILE_ID == "active"
    _assert_singleton(table, "candidate_profile", CANDIDATE_PROFILE_ID)
    assert "JSON" in str(_c(table, "profile_json").type).upper()
    _assert_att_fk(
        table,
        name="fk_candidate_profile__active_attachment_id",
        column="active_attachment_id",
        ondelete="RESTRICT",
        uq="uq_candidate_profile__active_attachment_id",
    )


def test_profile_drafts_contract() -> None:
    table = _t("profile_drafts")
    _assert_cols(
        table, _DRAFT_COLS,
        not_null={"id", "draft_json", "created_at", "updated_at"},
        nullable={"source_attachment_id"},
    )
    assert PROFILE_DRAFT_ID == "current"
    _assert_singleton(table, "profile_drafts", PROFILE_DRAFT_ID)
    assert "JSON" in str(_c(table, "draft_json").type).upper()
    _assert_att_fk(
        table,
        name="fk_profile_drafts__source_attachment_id",
        column="source_attachment_id",
        ondelete="CASCADE",
        uq="uq_profile_drafts__source_attachment_id",
    )


def test_job_preferences_contract() -> None:
    table = _t("job_preferences")
    _assert_cols(table, _PREF_COLS)
    assert JOB_PREFERENCES_ID == "active"
    _assert_singleton(table, "job_preferences", JOB_PREFERENCES_ID)
    assert "JSON" in str(_c(table, "preferences_json").type).upper()
    assert _default_name(_c(table, "preferences_json")) == "_empty_job_preferences"
    empty = _empty_job_preferences()
    assert list(empty) == list(JOB_PREFERENCE_KEYS)
    assert all(v == [] for v in empty.values())
    a, b = _empty_job_preferences(), _empty_job_preferences()
    assert a is not b
    a["target_roles"].append("x")
    assert b["target_roles"] == []


@pytest.mark.parametrize(
    ("table_name", "pk_name"),
    [
        ("candidate_profile", "pk_candidate_profile"),
        ("profile_drafts", "pk_profile_drafts"),
        ("job_preferences", "pk_job_preferences"),
    ],
)
def test_profile_family_pk_names(table_name: str, pk_name: str) -> None:
    pk = _t(table_name).primary_key
    assert pk is not None and pk.name == pk_name


@pytest.mark.parametrize(
    "table_name",
    ["candidate_profile", "profile_drafts", "job_preferences"],
)
def test_profile_family_timestamps_use_utc_now(table_name: str) -> None:
    _assert_utc(_t(table_name), "created_at", "updated_at")


def test_no_service_methods_on_models() -> None:
    banned = {
        "transition", "approve", "activate", "mark_failed", "save_file", "delete_file",
    }
    for model in _MODELS:
        public = {n for n in dir(model) if not n.startswith("_")}
        assert banned.isdisjoint(public)

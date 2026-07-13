"""Metadata tests for the job_posts ORM contract (migrations: task 02E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.ids import new_uuid
from app.core.time import utc_now
from app.db.base import Base
from app.db.models.jobs import (
    JOB_JD_QUALITIES,
    JOB_JD_QUALITY_FULL,
    JOB_JD_QUALITY_PARTIAL,
    JOB_JD_QUALITY_UNSCORABLE,
    JOB_PROCESSING_STATUS_DEFAULT,
    JOB_PROCESSING_STATUS_FAILED,
    JOB_PROCESSING_STATUS_PROCESSED,
    JOB_PROCESSING_STATUS_PROCESSING,
    JOB_PROCESSING_STATUS_RECEIVED,
    JOB_PROCESSING_STATUSES,
    JOB_SOURCE_TYPE_TEXT,
    JOB_SOURCE_TYPE_URL,
    JOB_SOURCE_TYPES,
    JobPost,
)
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects import sqlite
from sqlalchemy.sql.schema import Column, Table

_COLS = {
    "id",
    "source_type",
    "source_url",
    "raw_content",
    "raw_content_hash",
    "extraction_json",
    "processing_status",
    "jd_quality",
    "failure_code",
    "embedding_json",
    "embedding_model",
    "embedding_dimensions",
    "created_at",
    "updated_at",
}
_NULLABLE = {
    "source_url",
    "raw_content",
    "raw_content_hash",
    "extraction_json",
    "jd_quality",
    "failure_code",
    "embedding_json",
    "embedding_model",
    "embedding_dimensions",
}
_CHECK_NEEDLES: dict[str, tuple[str, ...]] = {
    "ck_job_posts__source_type": (JOB_SOURCE_TYPE_URL, JOB_SOURCE_TYPE_TEXT),
    "ck_job_posts__url_text_coupling": (
        JOB_SOURCE_TYPE_URL,
        JOB_SOURCE_TYPE_TEXT,
        "source_url",
        "raw_content",
    ),
    "ck_job_posts__raw_content_hash_coupling": ("raw_content", "raw_content_hash"),
    "ck_job_posts__processing_status": tuple(JOB_PROCESSING_STATUSES),
    "ck_job_posts__jd_quality": tuple(JOB_JD_QUALITIES),
    "ck_job_posts__processed_requires_extraction_quality": (
        JOB_PROCESSING_STATUS_PROCESSED,
        "extraction_json",
        "jd_quality",
    ),
    "ck_job_posts__failure_coupling": (
        JOB_PROCESSING_STATUS_FAILED,
        "failure_code",
    ),
    "ck_job_posts__embedding_all_or_none": (
        "embedding_json",
        "embedding_model",
        "embedding_dimensions",
    ),
    "ck_job_posts__embedding_dimensions_positive": ("embedding_dimensions",),
    "ck_job_posts__processed_scorable_embedding": (
        JOB_PROCESSING_STATUS_PROCESSED,
        JOB_JD_QUALITY_FULL,
        JOB_JD_QUALITY_PARTIAL,
        "embedding_json",
        "embedding_model",
        "embedding_dimensions",
    ),
}


def _table() -> Table:
    return Base.metadata.tables["job_posts"]


def _col(name: str) -> Column[Any]:
    return _table().c[name]


def _literal_sql(clause: Any) -> str:
    if isinstance(clause, str):
        return clause
    return str(
        clause.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).replace("\n", " ")


def _check_sql() -> dict[str, str]:
    return {
        str(c.name): _literal_sql(c.sqltext)
        for c in _table().constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def _default_name(col: Column[Any]) -> str:
    assert col.default is not None and callable(col.default.arg)
    return getattr(col.default.arg, "__wrapped__", col.default.arg).__name__


def test_job_post_registers_on_shared_base() -> None:
    assert "job_posts" in Base.metadata.tables
    assert issubclass(JobPost, Base)
    assert JobPost.metadata is Base.metadata
    assert JobPost.__tablename__ == "job_posts"


def test_job_post_exact_columns_nullability_types() -> None:
    table = _table()
    assert set(table.c.keys()) == _COLS
    for name in _COLS - _NULLABLE:
        assert _col(name).nullable is False, name
    for name in _NULLABLE:
        assert _col(name).nullable is True, name
    assert _col("id").primary_key
    assert table.primary_key is not None
    assert table.primary_key.name == "pk_job_posts"
    assert str(_col("id").type) in {"TEXT", "VARCHAR"}
    assert "JSON" in str(_col("extraction_json").type).upper()
    assert "JSON" in str(_col("embedding_json").type).upper()
    assert str(_col("embedding_dimensions").type).upper().startswith("INT")
    assert _default_name(_col("id")) == "new_uuid"
    uuid_val = new_uuid()
    assert isinstance(uuid_val, str) and uuid_val == uuid_val.lower()
    assert len(uuid_val) == 36
    for ts_name in ("created_at", "updated_at"):
        col = _col(ts_name)
        assert _default_name(col) == "utc_now"
        assert col.type.timezone is True  # type: ignore[attr-defined]
    ts = utc_now()
    assert isinstance(ts, datetime) and ts.tzinfo is not None


def test_job_post_status_quality_constants_and_default() -> None:
    assert JOB_SOURCE_TYPES == frozenset({JOB_SOURCE_TYPE_URL, JOB_SOURCE_TYPE_TEXT})
    assert JOB_PROCESSING_STATUSES == frozenset(
        {
            JOB_PROCESSING_STATUS_RECEIVED,
            JOB_PROCESSING_STATUS_PROCESSING,
            JOB_PROCESSING_STATUS_PROCESSED,
            JOB_PROCESSING_STATUS_FAILED,
        }
    )
    assert JOB_JD_QUALITIES == frozenset(
        {
            JOB_JD_QUALITY_FULL,
            JOB_JD_QUALITY_PARTIAL,
            JOB_JD_QUALITY_UNSCORABLE,
        }
    )
    assert JOB_PROCESSING_STATUS_DEFAULT == JOB_PROCESSING_STATUS_RECEIVED == "received"
    status = _col("processing_status")
    assert status.default is not None
    assert status.default.arg == JOB_PROCESSING_STATUS_DEFAULT
    assert status.server_default is not None
    assert JOB_PROCESSING_STATUS_DEFAULT in str(status.server_default.arg)


def test_job_post_named_checks_cover_coupling_and_enums() -> None:
    sql = _check_sql()
    assert set(sql) == set(_CHECK_NEEDLES)
    for name, needles in _CHECK_NEEDLES.items():
        for needle in needles:
            assert needle in sql[name], (name, needle, sql[name])
    # No hard-coded configured embedding length (e.g. 1536) in static checks.
    for body in sql.values():
        assert "1536" not in body


def test_job_post_unique_hash_and_processing_quality_index() -> None:
    table = _table()
    assert _col("raw_content_hash").unique is True
    uq_names = {
        c.name for c in table.constraints if isinstance(c, UniqueConstraint)
    }
    assert "uq_job_posts__raw_content_hash" in uq_names
    matches = [
        ix for ix in table.indexes if ix.name == "ix_job_posts__processing_quality"
    ]
    assert len(matches) == 1
    ix = matches[0]
    assert isinstance(ix, Index)
    assert ix.unique is False
    assert [c.name for c in ix.columns] == ["processing_status", "jd_quality"]


def test_job_post_no_extra_tables_or_service_behavior() -> None:
    # job_posts is defined here; chat tables are owned by chat models.
    for forbidden in (
        "score_cache",
        "match_scores",
    ):
        assert forbidden not in Base.metadata.tables
    banned = {
        "transition",
        "extract",
        "embed",
        "dedupe",
        "score",
        "sync_graph",
        "fetch_url",
    }
    public = {n for n in dir(JobPost) if not n.startswith("_")}
    assert banned.isdisjoint(public)

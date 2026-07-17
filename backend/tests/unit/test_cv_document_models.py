"""Metadata tests for CV document ORM contracts (Plan 9 Batch01)."""

from __future__ import annotations

from typing import Any

from app.db.base import Base
from app.db.models import CVDocument, CVDocumentDraft
from app.db.models.attachment_text_chunks import AttachmentTextChunk
from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.sql.schema import Column, Table

_DOC_COLS = {
    "attachment_id",
    "document_json",
    "profile_json",
    "outline_json",
    "extraction_version",
    "source_hash",
    "created_at",
    "updated_at",
}


def _t(name: str) -> Table:
    return Base.metadata.tables[name]


def _c(table: Table, name: str) -> Column[Any]:
    return table.c[name]


def _default_name(col: Column[Any]) -> str:
    assert col.default is not None and callable(col.default.arg)
    return getattr(col.default.arg, "__wrapped__", col.default.arg).__name__


def test_cv_document_tables_register_on_shared_base() -> None:
    assert {"cv_documents", "cv_document_drafts"}.issubset(set(Base.metadata.tables))
    for model, name in (
        (CVDocument, "cv_documents"),
        (CVDocumentDraft, "cv_document_drafts"),
    ):
        assert issubclass(model, Base)
        assert model.metadata is Base.metadata
        assert model.__tablename__ == name


def test_cv_document_and_draft_columns_and_pk() -> None:
    for table_name, pk_name in (
        ("cv_documents", "pk_cv_documents"),
        ("cv_document_drafts", "pk_cv_document_drafts"),
    ):
        table = _t(table_name)
        assert set(table.c.keys()) == _DOC_COLS
        assert table.primary_key is not None
        assert table.primary_key.name == pk_name
        assert list(table.primary_key.columns)[0].name == "attachment_id"
        for col in _DOC_COLS:
            assert _c(table, col).nullable is False
        for json_col in ("document_json", "profile_json", "outline_json"):
            assert "JSON" in str(_c(table, json_col).type).upper()
        assert _default_name(_c(table, "created_at")) == "utc_now"
        assert _default_name(_c(table, "updated_at")) == "utc_now"
        assert _c(table, "created_at").type.timezone is True  # type: ignore[attr-defined]
        assert _c(table, "updated_at").type.timezone is True  # type: ignore[attr-defined]


def test_cv_document_fks_cascade_to_attachments() -> None:
    for table_name, fk_name in (
        ("cv_documents", "fk_cv_documents__attachment_id"),
        ("cv_document_drafts", "fk_cv_document_drafts__attachment_id"),
    ):
        fks = [
            c
            for c in _t(table_name).constraints
            if isinstance(c, ForeignKeyConstraint)
        ]
        assert len(fks) == 1
        fk = fks[0]
        assert fk.name == fk_name
        el = list(fk.elements)
        assert len(el) == 1
        assert el[0].parent.name == "attachment_id"
        assert el[0].column.table.name == "attachments"
        assert el[0].column.name == "id"
        assert el[0].ondelete == "CASCADE"


def test_chunk_ownership_fk_is_cascade() -> None:
    fks = [
        c
        for c in AttachmentTextChunk.__table__.constraints
        if isinstance(c, ForeignKeyConstraint)
    ]
    assert len(fks) == 1
    el = list(fks[0].elements)
    assert el[0].ondelete == "CASCADE"
    assert fks[0].name == "fk_attachment_text_chunks__attachment_id"


def test_cv_document_models_have_no_service_methods() -> None:
    banned = {
        "extract",
        "approve",
        "reprocess",
        "delete_cv",
        "sync_graph",
        "transition",
    }
    for model in (CVDocument, CVDocumentDraft):
        public = {n for n in dir(model) if not n.startswith("_")}
        assert banned.isdisjoint(public)

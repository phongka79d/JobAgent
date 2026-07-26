"""Metadata contracts for derivative CV-tailoring persistence."""

from __future__ import annotations

from app.db.models.cv_tailoring import CVTailoringSession, CVTailoringVersion
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.types import JSON, DateTime, Text


def _constraint_names(
    model: type[CVTailoringSession] | type[CVTailoringVersion],
) -> set[str]:
    return {
        str(constraint.name)
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def _index_names(
    model: type[CVTailoringSession] | type[CVTailoringVersion],
) -> set[str]:
    return {str(index.name) for index in model.__table__.indexes}


def test_tailoring_session_exact_columns_types_constraints_and_indexes() -> None:
    table = CVTailoringSession.__table__
    assert set(table.c.keys()) == {
        "id",
        "profile_id",
        "source_attachment_id",
        "source_hash",
        "profile_updated_at",
        "job_id",
        "job_updated_at",
        "job_label_json",
        "instruction",
        "template_version",
        "state",
        "latest_version_number",
        "error_code",
        "created_at",
        "updated_at",
    }
    assert isinstance(table.c.id.type, Text)
    assert isinstance(table.c.profile_updated_at.type, DateTime)
    assert table.c.profile_updated_at.type.timezone is True
    assert isinstance(table.c.job_label_json.type, JSON)
    assert table.c.job_id.nullable is True
    assert table.c.job_updated_at.nullable is True
    assert table.c.error_code.nullable is True
    assert {
        "pk_cv_tailoring_sessions",
        "ck_cv_tailoring_sessions__state",
        "ck_cv_tailoring_sessions__latest_version_non_negative",
        "ck_cv_tailoring_sessions__error_coupling",
        "fk_cv_tailoring_sessions__profile_id",
        "fk_cv_tailoring_sessions__source_attachment_id",
        "fk_cv_tailoring_sessions__job_id",
    } <= _constraint_names(CVTailoringSession)
    assert _index_names(CVTailoringSession) == {
        "ix_cv_tailoring_sessions__profile_updated",
        "ix_cv_tailoring_sessions__job_id",
        "ix_cv_tailoring_sessions__state",
    }


def test_tailoring_version_exact_columns_types_constraints_and_indexes() -> None:
    table = CVTailoringVersion.__table__
    assert set(table.c.keys()) == {
        "id",
        "session_id",
        "version_number",
        "parent_version_id",
        "created_by",
        "content_json",
        "provenance_json",
        "source_revision_json",
        "tex_relative_path",
        "pdf_relative_path",
        "tex_sha256",
        "pdf_sha256",
        "page_count",
        "page_warning",
        "created_at",
    }
    for name in ("content_json", "provenance_json", "source_revision_json"):
        assert isinstance(table.c[name].type, JSON)
        assert table.c[name].nullable is False
    assert table.c.parent_version_id.nullable is True
    assert table.c.page_warning.nullable is True
    names = _constraint_names(CVTailoringVersion)
    assert {
        "pk_cv_tailoring_versions",
        "uq_cv_tailoring_versions__session_version",
        "uq_cv_tailoring_versions__session_id_id",
        "fk_cv_tailoring_versions__session_id",
        "fk_cv_tailoring_versions__session_parent",
        "ck_cv_tailoring_versions__version_positive",
        "ck_cv_tailoring_versions__created_by",
        "ck_cv_tailoring_versions__page_count_positive",
        "ck_cv_tailoring_versions__parent_coupling",
    } <= names
    assert _index_names(CVTailoringVersion) == {
        "ix_cv_tailoring_versions__session_created"
    }


def test_tailoring_foreign_key_delete_actions_are_exact() -> None:
    observed: set[tuple[str, tuple[str, ...], str, str]] = set()
    for model in (CVTailoringSession, CVTailoringVersion):
        for constraint in model.__table__.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            observed.add(
                (
                    str(constraint.name),
                    tuple(element.parent.name for element in constraint.elements),
                    ",".join(
                        f"{element.column.table.name}.{element.column.name}"
                        for element in constraint.elements
                    ),
                    str(constraint.ondelete),
                )
            )
    assert (
        "fk_cv_tailoring_sessions__profile_id",
        ("profile_id",),
        "profiles.id",
        "CASCADE",
    ) in observed
    assert (
        "fk_cv_tailoring_sessions__source_attachment_id",
        ("source_attachment_id",),
        "attachments.id",
        "CASCADE",
    ) in observed
    assert (
        "fk_cv_tailoring_sessions__job_id",
        ("job_id",),
        "job_posts.id",
        "SET NULL",
    ) in observed
    assert (
        "fk_cv_tailoring_versions__session_parent",
        ("session_id", "parent_version_id"),
        "cv_tailoring_versions.session_id,cv_tailoring_versions.id",
        "CASCADE",
    ) in observed


def test_tailoring_models_are_data_only() -> None:
    for model in (CVTailoringSession, CVTailoringVersion):
        assert not {
            "commit",
            "compile",
            "render",
            "write_artifact",
            "call_provider",
        }.intersection(name for name in dir(model) if not name.startswith("_"))
        assert any(
            isinstance(constraint, CheckConstraint)
            for constraint in model.__table__.constraints
        )
        assert any(isinstance(index, Index) for index in model.__table__.indexes)
        assert any(
            isinstance(constraint, UniqueConstraint)
            for constraint in model.__table__.constraints
        ) or model is CVTailoringSession

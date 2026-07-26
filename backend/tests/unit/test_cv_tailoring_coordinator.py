from __future__ import annotations

import inspect
from dataclasses import fields

import pytest


def test_coordinator_exposes_only_the_approved_orchestration_methods() -> None:
    from app.services.cv_tailoring import TailoringCoordinator

    expected = {
        "prepare_session": [
            "self",
            "profile_id",
            "job_id",
            "instruction",
            "parent_run_id",
        ],
        "stream_initial_version": ["self", "launch"],
        "get_completed_version": ["self", "launch"],
        "prepare_ai_version": [
            "self",
            "session_id",
            "parent_version_id",
            "instruction",
            "target_section_ids",
        ],
        "create_manual_version": [
            "self",
            "session_id",
            "parent_version_id",
            "content",
        ],
    }
    for name, parameters in expected.items():
        signature = inspect.signature(getattr(TailoringCoordinator, name))
        assert list(signature.parameters) == parameters


def test_launch_and_source_snapshot_do_not_carry_raw_or_artifact_inputs() -> None:
    from app.services.cv_tailoring import TailoringLaunch, TailoringSourceSnapshot

    assert [item.name for item in fields(TailoringLaunch)] == [
        "session_id",
        "run_id",
        "profile_id",
    ]
    snapshot_fields = {item.name for item in fields(TailoringSourceSnapshot)}
    assert snapshot_fields == {
        "profile_id",
        "attachment_id",
        "source_hash",
        "profile_updated_at",
        "profile",
        "document",
        "outline",
        "job_id",
        "job_updated_at",
        "job_label",
        "job_context",
    }
    assert not snapshot_fields & {
        "raw_cv",
        "raw_job",
        "reference_template",
        "storage_path",
        "latex",
    }


@pytest.mark.parametrize(("code", "message"), [("", "safe"), ("SAFE", "")])
def test_tailoring_error_requires_safe_nonempty_code_and_message(
    code: str, message: str
) -> None:
    from app.services.cv_tailoring import TailoringError

    with pytest.raises(ValueError):
        TailoringError(code, message)

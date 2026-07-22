from __future__ import annotations

import inspect

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

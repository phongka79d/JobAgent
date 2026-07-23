from app.services.activity_gate import ActivityBlockedError


def test_activity_blocked_error_exposes_only_stable_code_and_summary() -> None:
    error = ActivityBlockedError("PROFILE_SWITCH_BLOCKED", "finish active run")
    assert error.code == "PROFILE_SWITCH_BLOCKED"
    assert error.summary == "finish active run"
    assert str(error) == "finish active run"

from __future__ import annotations

import io
import logging
import traceback

import pytest

from scripts.check_shopaikey_compatibility import (
    EXPECTED_ECHO_LABEL,
    FUNCTION_CALL_PROMPT,
    MASTER_LOCKED_CHAT_MODEL,
    SYNTHETIC_TOOL_NAME,
    SYNTHETIC_TOOL_RESULT,
    Capability,
    DiagnosticHarness,
    EchoLabelArgs,
    FunctionCallObservation,
    ObservedToolCall,
    ResultStatus,
    ShopAIKeyConfig,
    ToolRoundTripObservation,
    check_function_call,
    check_tool_round_trip,
    synthetic_echo_label_tool,
)


SENTINEL_SECRET = "sentinel-secret-never-emit"


def make_config(*, model: str = MASTER_LOCKED_CHAT_MODEL) -> ShopAIKeyConfig:
    return ShopAIKeyConfig(
        base_url="https://provider.example/v1",
        api_key=SENTINEL_SECRET,
        model=model,
    )


def make_harness() -> DiagnosticHarness:
    return DiagnosticHarness(secrets=[SENTINEL_SECRET])


def valid_call(
    *,
    name: str = SYNTHETIC_TOOL_NAME,
    arguments: object | None = None,
    tool_call_id: str = "call-1",
) -> ObservedToolCall:
    if arguments is None:
        arguments = {"label": EXPECTED_ECHO_LABEL}
    return ObservedToolCall(name=name, arguments=arguments, tool_call_id=tool_call_id)


def test_synthetic_tool_schema_has_no_private_document_fields() -> None:
    tool = synthetic_echo_label_tool()
    schema = EchoLabelArgs.model_json_schema()
    properties = schema.get("properties", {})
    field_names = {str(name).lower() for name in properties}
    description = str(tool).lower()

    assert tool["type"] == "function"
    assert tool["function"]["name"] == SYNTHETIC_TOOL_NAME
    assert field_names == {"label"}
    for prohibited in (
        "document",
        "document_text",
        "cv",
        "resume",
        "jd",
        "job_description",
        "content",
        "text",
        "api_key",
    ):
        assert prohibited not in field_names
    for prohibited in ("cv text", "job description", "private document"):
        assert prohibited not in description


def test_function_call_prompt_is_content_neutral() -> None:
    lowered = FUNCTION_CALL_PROMPT.lower()
    for prohibited in ("cv", "resume", "job description", "jd", "candidate", "salary"):
        assert prohibited not in lowered
    assert SYNTHETIC_TOOL_NAME in lowered
    assert EXPECTED_ECHO_LABEL in lowered


def test_function_call_pass_with_valid_name_and_typed_args() -> None:
    def invoke(
        _config: ShopAIKeyConfig, prompt: str, tools: object
    ) -> FunctionCallObservation:
        assert prompt == FUNCTION_CALL_PROMPT
        assert tools == (synthetic_echo_label_tool(),)
        return FunctionCallObservation(tool_calls=(valid_call(),))

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.capability is Capability.FUNCTION_CALL
    assert result.status is ResultStatus.PASS
    assert result.failure_code is None
    assert result.selected_mode == "bind_tools"
    assert result.evidence["tool_name_match"] is True
    assert result.evidence["argument_json_valid"] is True
    assert result.evidence["argument_schema_valid"] is True
    assert result.evidence["match_status"] == "valid_function_call"
    # Raw argument values must not enter durable evidence.
    assert EXPECTED_ECHO_LABEL not in str(result.evidence)
    assert "arguments" not in result.evidence
    assert "tool_arguments" not in result.evidence


def test_function_call_pass_with_json_string_arguments() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(
            tool_calls=(valid_call(arguments='{"label":"ping"}'),)
        )

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.PASS
    assert result.evidence["argument_json_valid"] is True
    assert result.evidence["argument_schema_valid"] is True


def test_function_call_fail_missing_tool_call() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(tool_calls=())

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "missing_tool_call"
    assert result.evidence["match_status"] == "missing_tool_call"
    assert result.evidence["tool_call_count"] == 0


def test_function_call_fail_wrong_tool() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(
            tool_calls=(valid_call(name="other_tool"),)
        )

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "wrong_tool"
    assert result.evidence["match_status"] == "wrong_tool"
    assert result.evidence["tool_name_match"] is False


def test_function_call_fail_malformed_json() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(
            tool_calls=(valid_call(arguments="{not-json"),)
        )

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "malformed_json_arguments"
    assert result.evidence["argument_json_valid"] is False
    assert result.evidence["match_status"] == "malformed_json_arguments"
    assert "{not-json" not in str(result.evidence)


def test_function_call_fail_multiple_unexpected_calls() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(
            tool_calls=(
                valid_call(tool_call_id="a"),
                valid_call(tool_call_id="b"),
            )
        )

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "multiple_unexpected_calls"
    assert result.evidence["tool_call_count"] == 2
    assert result.evidence["match_status"] == "multiple_unexpected_calls"


def test_function_call_fail_invalid_typed_arguments() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        return FunctionCallObservation(
            tool_calls=(valid_call(arguments={"label": 123}),)
        )

    result = check_function_call(
        make_config(), make_harness(), invoke_function_call=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "invalid_typed_arguments"
    assert result.evidence["argument_json_valid"] is True
    assert result.evidence["argument_schema_valid"] is False


def test_tool_round_trip_pass_with_non_empty_final_response() -> None:
    seen: dict[str, object] = {}

    def invoke(
        _config: ShopAIKeyConfig,
        prompt: str,
        tools: object,
        prior_call: ObservedToolCall,
        tool_result: str,
    ) -> ToolRoundTripObservation:
        seen["prompt"] = prompt
        seen["tools"] = tools
        seen["prior_call"] = prior_call
        seen["tool_result"] = tool_result
        return ToolRoundTripObservation(final_assistant_text="Tool result acknowledged.")

    result = check_tool_round_trip(
        make_config(), make_harness(), invoke_tool_round_trip=invoke
    )

    assert result.capability is Capability.TOOL_ROUND_TRIP
    assert result.status is ResultStatus.PASS
    assert result.failure_code is None
    assert result.selected_mode == "tool_result_round_trip"
    assert result.evidence["final_response_non_empty"] is True
    assert result.evidence["match_status"] == "final_response_after_tool_result"
    assert seen["prompt"] == FUNCTION_CALL_PROMPT
    assert seen["tool_result"] == SYNTHETIC_TOOL_RESULT
    assert seen["tools"] == (synthetic_echo_label_tool(),)
    assert isinstance(seen["prior_call"], ObservedToolCall)
    # Final body text must not be copied into durable evidence.
    assert "acknowledged" not in str(result.evidence)
    assert "final_assistant_text" not in result.evidence


def test_tool_round_trip_fail_missing_final_response() -> None:
    def invoke(
        _config: ShopAIKeyConfig,
        _prompt: str,
        _tools: object,
        _prior_call: ObservedToolCall,
        _tool_result: str,
    ) -> ToolRoundTripObservation:
        return ToolRoundTripObservation(final_assistant_text="   ")

    result = check_tool_round_trip(
        make_config(), make_harness(), invoke_tool_round_trip=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "missing_final_response"
    assert result.evidence["final_response_non_empty"] is False
    assert result.evidence["match_status"] == "missing_final_response"


def test_provider_errors_are_safe_and_do_not_claim_live_compatibility(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness()

    def boom_function_call(
        _config: ShopAIKeyConfig, _prompt: str, _tools: object
    ) -> FunctionCallObservation:
        raise RuntimeError(f"Authorization: Bearer {SENTINEL_SECRET}")

    def boom_round_trip(
        _config: ShopAIKeyConfig,
        _prompt: str,
        _tools: object,
        _prior_call: ObservedToolCall,
        _tool_result: str,
    ) -> ToolRoundTripObservation:
        raise RuntimeError(f"api_key={SENTINEL_SECRET}")

    function_call = check_function_call(
        make_config(), harness, invoke_function_call=boom_function_call
    )
    round_trip = check_tool_round_trip(
        make_config(), harness, invoke_tool_round_trip=boom_round_trip
    )
    rendered = harness.render([function_call, round_trip])
    report = io.StringIO()
    logger = logging.getLogger("shopaikey-function-call-test")

    print(rendered)
    print(rendered, file=__import__("sys").stderr)
    logger.warning("%s", rendered)
    report.write(rendered)
    authorization_name = "".join(("Author", "ization"))
    with pytest.raises(RuntimeError) as raised:
        try:
            raise RuntimeError(f"{authorization_name}: Bearer {SENTINEL_SECRET}")
        except RuntimeError as source:
            raise harness.safe_exception(SENTINEL_SECRET) from source

    captured = capsys.readouterr()
    combined = "\n".join(
        [
            captured.out,
            captured.err,
            caplog.text,
            report.getvalue(),
            str(raised.value),
            "".join(traceback.format_exception(raised.value)),
            harness.render([function_call, round_trip]),
        ]
    )
    for prohibited in (
        SENTINEL_SECRET,
        "sentinel_secret_never_emit",
        "Authorization",
        "api_key",
        "Bearer",
    ):
        assert prohibited not in combined

    assert function_call.status is ResultStatus.FAIL
    assert round_trip.status is ResultStatus.FAIL
    assert function_call.failure_code == "provider_error"
    assert round_trip.failure_code == "provider_error"
    assert function_call.evidence == {"summary": "function_call_failed"}
    assert round_trip.evidence == {"summary": "tool_round_trip_failed"}
    assert function_call.status is not ResultStatus.PASS
    assert round_trip.status is not ResultStatus.PASS
    assert str(raised.value) == "diagnostic_failed"

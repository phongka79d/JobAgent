from __future__ import annotations

import io
import logging
import traceback

import pytest
from scripts.check_shopaikey_compatibility import (
    APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT,
    APPROVED_RELIABILITY_ATTEMPT_COUNT,
    MASTER_LOCKED_CHAT_MODEL,
    STRICT_ENABLED_BY_DEFAULT,
    STRUCTURED_SCHEMA_PROMPT,
    STRUCTURED_SCHEMA_REPAIR_PROMPT,
    Capability,
    DiagnosticHarness,
    ReliabilityEvaluation,
    ResultStatus,
    SchemaAttemptResult,
    SchemaMode,
    SchemaProbeResponse,
    ShopAIKeyConfig,
    StructuredSchemaObservation,
    check_structured_schema,
    evaluate_mode_reliability,
    run_structured_schema_attempt,
    validate_schema_probe_payload,
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


def valid_payload() -> dict[str, object]:
    return {"item_id": "probe-1", "count": 1, "active": True}


def test_schema_probe_model_has_no_private_document_fields() -> None:
    schema = SchemaProbeResponse.model_json_schema()
    properties = schema.get("properties", {})
    field_names = {str(name).lower() for name in properties}
    required = {str(name).lower() for name in schema.get("required", [])}

    assert field_names == {"item_id", "count", "active"}
    assert required == {"item_id", "count", "active"}
    for prohibited in (
        "document",
        "document_text",
        "cv",
        "resume",
        "jd",
        "job_description",
        "content",
        "api_key",
    ):
        assert prohibited not in field_names
    assert STRICT_ENABLED_BY_DEFAULT is False


def test_structured_prompts_are_content_neutral() -> None:
    combined = f"{STRUCTURED_SCHEMA_PROMPT}\n{STRUCTURED_SCHEMA_REPAIR_PROMPT}".lower()
    for prohibited in ("cv", "resume", "job description", "jd", "candidate", "salary"):
        assert prohibited not in combined


def test_validate_valid_output() -> None:
    model, failure = validate_schema_probe_payload(valid_payload())
    assert failure is None
    assert model is not None
    assert model.item_id == "probe-1"
    assert model.count == 1
    assert model.active is True


def test_validate_invalid_types() -> None:
    model, failure = validate_schema_probe_payload(
        {"item_id": "probe-1", "count": "not-an-int", "active": True}
    )
    assert model is None
    assert failure == "invalid_types"


def test_attempt_valid_first_response_no_repair() -> None:
    calls: list[tuple[SchemaMode, str, bool]] = []

    def invoke(
        _config: ShopAIKeyConfig, mode: SchemaMode, prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        calls.append((mode, prompt, is_repair))
        return StructuredSchemaObservation(payload=valid_payload())

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.FUNCTION_SCHEMA,
        attempt_index=0,
        invoke_structured=invoke,
    )

    assert result.validation_passed is True
    assert result.repair_requests_used == 0
    assert result.failure_code is None
    assert result.match_status == "valid_first_response"
    assert len(calls) == 1
    assert calls[0] == (SchemaMode.FUNCTION_SCHEMA, STRUCTURED_SCHEMA_PROMPT, False)


def test_attempt_first_response_repair_success() -> None:
    calls: list[bool] = []

    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        calls.append(is_repair)
        if not is_repair:
            return StructuredSchemaObservation(
                payload={"item_id": "probe-1", "count": "bad", "active": True}
            )
        return StructuredSchemaObservation(payload=valid_payload())

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.FUNCTION_SCHEMA,
        attempt_index=1,
        invoke_structured=invoke,
    )

    assert result.validation_passed is True
    assert result.repair_requests_used == 1
    assert result.failure_code is None
    assert result.match_status == "valid_after_one_repair"
    assert calls == [False, True]


def test_attempt_second_failure_after_one_repair() -> None:
    call_count = 0

    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        nonlocal call_count
        call_count += 1
        return StructuredSchemaObservation(
            payload={"item_id": "probe-1", "count": "bad", "active": True}
        )

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.JSON_MODE,
        attempt_index=0,
        invoke_structured=invoke,
    )

    assert result.validation_passed is False
    assert result.repair_requests_used == 1
    assert result.failure_code == "invalid_types"
    assert result.match_status == "invalid_after_one_repair"
    # Exactly one initial request plus one repair — never a third call.
    assert call_count == 2


def test_attempt_strict_incompatibility() -> None:
    def invoke(
        _config: ShopAIKeyConfig, mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        assert mode is SchemaMode.STRICT_SCHEMA
        return StructuredSchemaObservation(
            mode_supported=False,
            incompatibility_reason="strict_incompatible",
        )

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.STRICT_SCHEMA,
        attempt_index=0,
        invoke_structured=invoke,
    )

    assert result.validation_passed is False
    assert result.repair_requests_used == 0
    assert result.failure_code == "strict_incompatible"
    assert result.match_status == "strict_incompatible"


def test_attempt_invalid_types_without_claiming_valid() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        return StructuredSchemaObservation(
            payload={"item_id": 99, "count": 1, "active": "yes"}
        )

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.FUNCTION_SCHEMA,
        attempt_index=0,
        invoke_structured=invoke,
    )

    assert result.validation_passed is False
    assert result.repair_requests_used == 1
    assert result.failure_code == "invalid_types"
    assert result.match_status == "invalid_after_one_repair"


def test_repair_limit_enforcement_zero_repairs_allowed() -> None:
    call_count = 0

    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        nonlocal call_count
        call_count += 1
        return StructuredSchemaObservation(
            payload={"item_id": "probe-1", "count": "bad", "active": True}
        )

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.FUNCTION_SCHEMA,
        attempt_index=0,
        invoke_structured=invoke,
        max_repair_requests=0,
    )

    assert result.validation_passed is False
    assert result.repair_requests_used == 0
    assert result.match_status == "repair_limit_enforced"
    assert call_count == 1


def test_repair_limit_ceiling_cannot_exceed_approved_max() -> None:
    call_count = 0

    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, is_repair: bool
    ) -> StructuredSchemaObservation:
        nonlocal call_count
        call_count += 1
        return StructuredSchemaObservation(
            payload={"item_id": "probe-1", "count": "bad", "active": True}
        )

    result = run_structured_schema_attempt(
        make_config(),
        SchemaMode.FUNCTION_SCHEMA,
        attempt_index=0,
        invoke_structured=invoke,
        max_repair_requests=5,
    )

    assert APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT == 1
    assert result.repair_requests_used == 1
    assert call_count == 2
    assert result.match_status == "invalid_after_one_repair"


def test_evaluate_reliability_three_consecutive_pass() -> None:
    attempts = [
        SchemaAttemptResult(
            mode=SchemaMode.FUNCTION_SCHEMA,
            attempt_index=i,
            validation_passed=True,
            repair_requests_used=1 if i == 1 else 0,
            match_status="valid_after_one_repair" if i == 1 else "valid_first_response",
        )
        for i in range(APPROVED_RELIABILITY_ATTEMPT_COUNT)
    ]
    evaluation = evaluate_mode_reliability(attempts)
    assert evaluation.reliable is True
    assert evaluation.reason == "approved_criterion_met"
    assert evaluation.mode is SchemaMode.FUNCTION_SCHEMA
    assert evaluation.required_attempt_count == 3
    assert evaluation.max_repair_per_attempt == 1


def test_evaluate_reliability_fails_when_one_attempt_fails() -> None:
    attempts = [
        SchemaAttemptResult(
            mode=SchemaMode.JSON_MODE,
            attempt_index=0,
            validation_passed=True,
            repair_requests_used=0,
            match_status="valid_first_response",
        ),
        SchemaAttemptResult(
            mode=SchemaMode.JSON_MODE,
            attempt_index=1,
            validation_passed=False,
            repair_requests_used=1,
            failure_code="invalid_types",
            match_status="invalid_after_one_repair",
        ),
        SchemaAttemptResult(
            mode=SchemaMode.JSON_MODE,
            attempt_index=2,
            validation_passed=True,
            repair_requests_used=0,
            match_status="valid_first_response",
        ),
    ]
    evaluation = evaluate_mode_reliability(attempts)
    assert evaluation.reliable is False
    assert evaluation.reason == "not_all_attempts_passed"


def test_check_structured_schema_selects_first_reliable_mode_for_run() -> None:
    def invoke(
        _config: ShopAIKeyConfig, mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        if mode is SchemaMode.STRICT_SCHEMA:
            return StructuredSchemaObservation(
                mode_supported=False,
                incompatibility_reason="strict_incompatible",
            )
        return StructuredSchemaObservation(payload=valid_payload())

    result = check_structured_schema(
        make_config(), make_harness(), invoke_structured=invoke
    )

    assert result.capability is Capability.STRUCTURED_SCHEMA
    assert result.status is ResultStatus.PASS
    assert result.selected_mode == SchemaMode.FUNCTION_SCHEMA.value
    assert result.evidence["live_mode_locked"] is False
    assert result.evidence["strict_enabled_by_default"] is False
    assert result.evidence["selected_for_run"] == "function_schema"
    assert "strict_schema" in result.evidence["modes_tried"]
    assert result.evidence["reliability"]["reliable"] is True
    # Must not claim a live locked mode in durable evidence wording.
    assert result.evidence.get("live_mode_locked") is False


def test_check_structured_schema_strict_incompatible_then_function_pass() -> None:
    seen_modes: list[SchemaMode] = []

    def invoke(
        _config: ShopAIKeyConfig, mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        seen_modes.append(mode)
        if mode is SchemaMode.STRICT_SCHEMA:
            return StructuredSchemaObservation(
                mode_supported=False,
                incompatibility_reason="strict_incompatible",
            )
        return StructuredSchemaObservation(payload=valid_payload())

    result = check_structured_schema(
        make_config(), make_harness(), invoke_structured=invoke
    )

    assert result.status is ResultStatus.PASS
    assert result.selected_mode == "function_schema"
    assert SchemaMode.STRICT_SCHEMA in seen_modes
    assert SchemaMode.FUNCTION_SCHEMA in seen_modes
    # JSON mode should not be required once function_schema is reliable.
    assert SchemaMode.JSON_MODE not in seen_modes


def test_check_structured_schema_fails_when_no_mode_reliable() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        return StructuredSchemaObservation(
            payload={"item_id": "probe-1", "count": "bad", "active": True}
        )

    result = check_structured_schema(
        make_config(), make_harness(), invoke_structured=invoke
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "no_reliable_mode"
    assert result.selected_mode is None
    assert result.evidence["live_mode_locked"] is False
    assert result.evidence["match_status"] == "no_reliable_mode"
    assert set(result.evidence["modes_tried"]) == {
        "strict_schema",
        "function_schema",
        "json_mode",
    }


def test_check_structured_schema_does_not_claim_live_lock_on_pass() -> None:
    def invoke(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        return StructuredSchemaObservation(payload=valid_payload())

    result = check_structured_schema(
        make_config(),
        make_harness(),
        invoke_structured=invoke,
        modes=(SchemaMode.JSON_MODE,),
    )

    assert result.status is ResultStatus.PASS
    assert result.evidence["live_mode_locked"] is False
    assert "locked_live" not in result.evidence
    assert result.selected_mode == "json_mode"


def test_provider_errors_and_payloads_stay_out_of_evidence(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness()

    def boom(
        _config: ShopAIKeyConfig, _mode: SchemaMode, _prompt: str, _is_repair: bool
    ) -> StructuredSchemaObservation:
        raise RuntimeError(f"Authorization: Bearer {SENTINEL_SECRET}")

    result = check_structured_schema(
        make_config(), harness, invoke_structured=boom, modes=(SchemaMode.JSON_MODE,)
    )
    rendered = harness.render([result])
    report = io.StringIO()
    logger = logging.getLogger("shopaikey-structured-schema-test")

    print(rendered)
    print(rendered, file=__import__("sys").stderr)
    logger.warning("%s", rendered)
    report.write(rendered)

    captured = capsys.readouterr()
    combined = "\n".join(
        [
            captured.out,
            captured.err,
            caplog.text,
            report.getvalue(),
            str(result.evidence),
            "".join(traceback.format_exception(RuntimeError("diagnostic_failed"))),
        ]
    )
    for prohibited in (
        SENTINEL_SECRET,
        "sentinel_secret_never_emit",
        "Authorization",
        "Bearer",
        "probe-1",
    ):
        assert prohibited not in combined

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "no_reliable_mode"
    assert "payload" not in result.evidence
    assert isinstance(
        evaluate_mode_reliability(
            [
                SchemaAttemptResult(
                    mode=SchemaMode.JSON_MODE,
                    attempt_index=0,
                    validation_passed=False,
                    repair_requests_used=0,
                    failure_code="provider_error",
                    match_status="provider_error",
                )
            ]
        ),
        ReliabilityEvaluation,
    )

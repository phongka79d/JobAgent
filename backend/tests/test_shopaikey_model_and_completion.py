from __future__ import annotations

import io
import logging
import traceback

import pytest

from scripts.check_shopaikey_compatibility import (
    MASTER_LOCKED_CHAT_MODEL,
    MINIMAL_COMPLETION_PROMPT,
    BasicCompletionObservation,
    Capability,
    DiagnosticHarness,
    ResultStatus,
    ShopAIKeyConfig,
    check_basic_completion,
    check_model_discovery,
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


def test_minimal_completion_prompt_is_content_neutral() -> None:
    lowered = MINIMAL_COMPLETION_PROMPT.lower()
    for prohibited in ("cv", "resume", "job description", "jd", "candidate", "salary"):
        assert prohibited not in lowered


def test_model_discovery_pass_when_gpt4o_mini_present() -> None:
    result = check_model_discovery(
        make_config(),
        make_harness(),
        list_model_ids=lambda _config: (MASTER_LOCKED_CHAT_MODEL, "text-embedding-3-small"),
    )

    assert result.capability is Capability.MODEL_DISCOVERY
    assert result.status is ResultStatus.PASS
    assert result.failure_code is None
    assert result.selected_mode == MASTER_LOCKED_CHAT_MODEL
    assert result.evidence["match_status"] == "exact_master_lock"
    assert result.evidence["configured_present"] is True
    assert result.evidence["master_present"] is True
    assert result.evidence["silent_substitution"] is False
    # Full provider catalog must not be copied into evidence.
    assert "model_ids" not in result.evidence
    assert MASTER_LOCKED_CHAT_MODEL not in str(result.evidence.get("listed_models", ""))


def test_model_discovery_fail_when_model_absent() -> None:
    result = check_model_discovery(
        make_config(),
        make_harness(),
        list_model_ids=lambda _config: ("other-model", "text-embedding-3-small"),
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "model_absent"
    assert result.evidence["match_status"] == "model_absent"
    assert result.evidence["configured_present"] is False
    assert result.evidence["master_present"] is False


def test_model_discovery_equivalent_requires_source_revision() -> None:
    equivalent = "gpt-4o-mini-equivalent"
    result = check_model_discovery(
        make_config(model=equivalent),
        make_harness(),
        list_model_ids=lambda _config: (equivalent, "other-model"),
    )

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "equivalent_requires_source_revision"
    assert result.evidence["match_status"] == "equivalent_requires_source_revision"
    assert result.evidence["configured_present"] is True
    assert result.evidence["master_present"] is False
    assert result.evidence["configured_model"] == equivalent
    assert result.selected_mode == equivalent


def test_basic_completion_non_empty_response_passes() -> None:
    def complete(_config: ShopAIKeyConfig, prompt: str) -> BasicCompletionObservation:
        assert prompt == MINIMAL_COMPLETION_PROMPT
        return BasicCompletionObservation(
            assistant_text="ok",
            response_model=MASTER_LOCKED_CHAT_MODEL,
        )

    result = check_basic_completion(make_config(), make_harness(), complete=complete)

    assert result.capability is Capability.BASIC_COMPLETION
    assert result.status is ResultStatus.PASS
    assert result.failure_code is None
    assert result.evidence["response_non_empty"] is True
    assert result.evidence["match_status"] == "non_empty_response"
    assert result.evidence["model_match"] is True
    # Do not copy the assistant body into durable evidence.
    assert "ok" not in str(result.evidence)
    assert "assistant_text" not in result.evidence


def test_basic_completion_empty_response_fails() -> None:
    def complete(_config: ShopAIKeyConfig, _prompt: str) -> BasicCompletionObservation:
        return BasicCompletionObservation(
            assistant_text="   ",
            response_model=MASTER_LOCKED_CHAT_MODEL,
        )

    result = check_basic_completion(make_config(), make_harness(), complete=complete)

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "empty_response"
    assert result.evidence["response_non_empty"] is False
    assert result.evidence["match_status"] == "empty_response"


def test_basic_completion_rejects_silent_model_substitution() -> None:
    def complete(_config: ShopAIKeyConfig, _prompt: str) -> BasicCompletionObservation:
        return BasicCompletionObservation(
            assistant_text="ok",
            response_model="silently-switched-model",
        )

    result = check_basic_completion(make_config(), make_harness(), complete=complete)

    assert result.status is ResultStatus.FAIL
    assert result.failure_code == "silent_substitution_rejected"
    assert result.evidence["match_status"] == "silent_substitution_rejected"
    assert result.evidence["model_match"] is False


def test_provider_errors_are_safe_and_do_not_claim_live_compatibility(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness()

    def list_models(_config: ShopAIKeyConfig) -> tuple[str, ...]:
        raise RuntimeError(f"Authorization: Bearer {SENTINEL_SECRET}")

    def complete(_config: ShopAIKeyConfig, _prompt: str) -> BasicCompletionObservation:
        raise RuntimeError(f"api_key={SENTINEL_SECRET}")

    discovery = check_model_discovery(
        make_config(), harness, list_model_ids=list_models
    )
    completion = check_basic_completion(make_config(), harness, complete=complete)
    rendered = harness.render([discovery, completion])
    report = io.StringIO()
    logger = logging.getLogger("shopaikey-model-completion-test")

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
            harness.render([discovery, completion]),
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

    assert discovery.status is ResultStatus.FAIL
    assert completion.status is ResultStatus.FAIL
    assert discovery.failure_code == "provider_error"
    assert completion.failure_code == "provider_error"
    assert discovery.evidence == {"summary": "model_discovery_failed"}
    assert completion.evidence == {"summary": "basic_completion_failed"}
    # Fake classification only; no live PASS claim.
    assert discovery.status is not ResultStatus.PASS
    assert completion.status is not ResultStatus.PASS
    assert str(raised.value) == "diagnostic_failed"

from __future__ import annotations

import io
import logging
import traceback

import pytest
from scripts.check_shopaikey_compatibility import (
    DIAGNOSTIC_EXIT_REQUIRED_FAILURE,
    DIAGNOSTIC_EXIT_SUCCESS,
    MASTER_LOCKED_CHAT_MODEL,
    REQUIRED_PASS_CAPABILITIES,
    STREAMING_PROMPT,
    Capability,
    DiagnosticHarness,
    DiagnosticResult,
    ResultStatus,
    ShopAIKeyConfig,
    StreamChunkMeta,
    StreamingObservation,
    check_streaming,
    compute_diagnostic_exit_code,
    format_sanitized_summary,
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


def ordered_chunks(
    lengths: tuple[int, ...] = (2, 3),
    *,
    with_sequence: bool = True,
) -> tuple[StreamChunkMeta, ...]:
    metas: list[StreamChunkMeta] = []
    for arrival_index, text_length in enumerate(lengths):
        metas.append(
            StreamChunkMeta(
                arrival_index=arrival_index,
                text_length=text_length,
                sequence_index=arrival_index if with_sequence else None,
            )
        )
    return tuple(metas)


def result(
    capability: Capability,
    status: ResultStatus,
    *,
    failure_code: str | None = None,
    selected_mode: str | None = None,
) -> DiagnosticResult:
    return DiagnosticResult(
        capability=capability,
        status=status,
        evidence={"summary": status.value},
        failure_code=failure_code,
        selected_mode=selected_mode,
    )


def all_required_pass_results(
    *,
    streaming: DiagnosticResult | None = None,
) -> list[DiagnosticResult]:
    items = [
        result(capability, ResultStatus.PASS, selected_mode="ok")
        for capability in REQUIRED_PASS_CAPABILITIES
    ]
    if streaming is not None:
        items.append(streaming)
    else:
        items.append(
            result(
                Capability.STREAMING,
                ResultStatus.UNSUPPORTED,
                selected_mode="unsupported",
            )
        )
    return items


def test_streaming_prompt_is_content_neutral() -> None:
    lowered = STREAMING_PROMPT.lower()
    for prohibited in ("cv", "resume", "job description", "jd", "candidate", "salary"):
        assert prohibited not in lowered


def test_streaming_supported_ordered_chunks() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(chunks=ordered_chunks((1, 2, 3)))

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.capability is Capability.STREAMING
    assert outcome.status is ResultStatus.PASS
    assert outcome.failure_code is None
    assert outcome.selected_mode == "streaming_text"
    assert outcome.evidence["match_status"] == "ordered_text_chunks"
    assert outcome.evidence["chunk_count"] == 3
    assert outcome.evidence["non_empty_chunk_count"] == 3
    assert outcome.evidence["sequence_ordered"] is True
    assert outcome.evidence["total_text_length"] == 6
    assert outcome.evidence["live_streaming_claimed"] is False
    # Raw text deltas must never appear in evidence.
    assert "chunks" not in outcome.evidence
    assert "text" not in outcome.evidence


def test_streaming_supported_without_provider_sequence_ids() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(
            chunks=ordered_chunks((4, 1), with_sequence=False)
        )

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.PASS
    assert outcome.evidence["sequence_ordered"] is True
    assert outcome.evidence["match_status"] == "ordered_text_chunks"


def test_streaming_out_of_order_chunks() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(
            chunks=(
                StreamChunkMeta(arrival_index=0, text_length=2, sequence_index=2),
                StreamChunkMeta(arrival_index=1, text_length=2, sequence_index=1),
            )
        )

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.FAIL
    assert outcome.failure_code == "out_of_order_chunks"
    assert outcome.evidence["match_status"] == "out_of_order_chunks"
    assert outcome.evidence["sequence_ordered"] is False
    assert outcome.evidence["live_streaming_claimed"] is False


def test_streaming_empty_chunks() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(
            chunks=(
                StreamChunkMeta(arrival_index=0, text_length=0, sequence_index=0),
                StreamChunkMeta(arrival_index=1, text_length=0, sequence_index=1),
            )
        )

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.FAIL
    assert outcome.failure_code == "empty_chunks"
    assert outcome.evidence["match_status"] == "empty_chunks"
    assert outcome.evidence["non_empty_chunk_count"] == 0


def test_streaming_no_chunks_is_empty() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(chunks=())

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.FAIL
    assert outcome.failure_code == "empty_chunks"


def test_streaming_explicit_unsupported() -> None:
    def stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        return StreamingObservation(
            explicitly_unsupported=True,
            unsupported_reason="provider_streaming_unsupported",
        )

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.UNSUPPORTED
    assert outcome.failure_code is None
    assert outcome.selected_mode == "unsupported"
    assert outcome.evidence["explicitly_unsupported"] is True
    assert outcome.evidence["match_status"] == "explicitly_unsupported"
    assert outcome.evidence["unsupported_reason"] == "provider_streaming_unsupported"
    assert outcome.evidence["live_streaming_claimed"] is False


def test_streaming_unknown_failure() -> None:
    def stream(_config: ShopAIKeyConfig, _prompt: str) -> StreamingObservation:
        raise RuntimeError(f"Authorization: Bearer {SENTINEL_SECRET}")

    outcome = check_streaming(make_config(), make_harness(), stream=stream)

    assert outcome.status is ResultStatus.FAIL
    assert outcome.failure_code == "unknown_failure"
    assert outcome.evidence["match_status"] == "unknown_failure"
    assert outcome.evidence["live_streaming_claimed"] is False
    assert SENTINEL_SECRET not in str(outcome.evidence)
    assert "Authorization" not in str(outcome.evidence)


def test_exit_zero_when_required_pass_and_streaming_unsupported() -> None:
    results = all_required_pass_results(
        streaming=result(
            Capability.STREAMING,
            ResultStatus.UNSUPPORTED,
            selected_mode="unsupported",
        )
    )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_SUCCESS


def test_exit_zero_when_required_pass_and_streaming_pass() -> None:
    results = all_required_pass_results(
        streaming=result(
            Capability.STREAMING,
            ResultStatus.PASS,
            selected_mode="streaming_text",
        )
    )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_SUCCESS


def test_exit_zero_when_required_pass_and_streaming_fail() -> None:
    """Streaming is knowledge-only; a streaming FAIL alone must not fail the gate."""
    results = all_required_pass_results(
        streaming=result(
            Capability.STREAMING,
            ResultStatus.FAIL,
            failure_code="empty_chunks",
        )
    )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_SUCCESS


def test_exit_nonzero_on_function_call_failure() -> None:
    results = all_required_pass_results()
    for index, item in enumerate(results):
        if item.capability is Capability.FUNCTION_CALL:
            results[index] = result(
                Capability.FUNCTION_CALL,
                ResultStatus.FAIL,
                failure_code="missing_tool_call",
            )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_REQUIRED_FAILURE


def test_exit_nonzero_on_structured_schema_failure() -> None:
    results = all_required_pass_results()
    for index, item in enumerate(results):
        if item.capability is Capability.STRUCTURED_SCHEMA:
            results[index] = result(
                Capability.STRUCTURED_SCHEMA,
                ResultStatus.FAIL,
                failure_code="no_reliable_mode",
            )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_REQUIRED_FAILURE


@pytest.mark.parametrize(
    "status",
    [ResultStatus.FAIL, ResultStatus.PENDING, ResultStatus.UNSUPPORTED],
)
def test_exit_nonzero_when_any_required_not_pass(status: ResultStatus) -> None:
    results = all_required_pass_results()
    for index, item in enumerate(results):
        if item.capability is Capability.BASIC_COMPLETION:
            results[index] = result(
                Capability.BASIC_COMPLETION,
                status,
                failure_code="empty_response" if status is ResultStatus.FAIL else None,
            )
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_REQUIRED_FAILURE


def test_exit_nonzero_when_required_capability_missing() -> None:
    results = [
        result(Capability.MODEL_DISCOVERY, ResultStatus.PASS),
        result(Capability.STREAMING, ResultStatus.PASS),
    ]
    assert compute_diagnostic_exit_code(results) == DIAGNOSTIC_EXIT_REQUIRED_FAILURE


def test_streaming_is_not_required_pass_capability() -> None:
    assert Capability.STREAMING not in REQUIRED_PASS_CAPABILITIES


def test_sanitized_summary_and_render_hide_secrets(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    harness = make_harness()

    def failing_stream(
        _config: ShopAIKeyConfig, _prompt: str
    ) -> StreamingObservation:
        raise RuntimeError(f"Authorization: Bearer {SENTINEL_SECRET}")

    streaming_result = check_streaming(
        make_config(),
        harness,
        stream=failing_stream,
    )
    required = [
        harness.record(
            capability,
            ResultStatus.PASS,
            evidence={"summary": "ok", "note": f"key={SENTINEL_SECRET}"},
            selected_mode="ok",
        )
        for capability in REQUIRED_PASS_CAPABILITIES
    ]
    results = [*required, streaming_result]
    exit_code = compute_diagnostic_exit_code(results)
    summary = format_sanitized_summary(results, exit_code=exit_code)
    rendered = harness.render(results)

    print(summary)
    print(rendered)
    print(summary, file=__import__("sys").stderr)
    logging.getLogger("shopaikey-streaming-exit").warning("%s", summary)
    report = io.StringIO()
    report.write(summary)
    report.write(rendered)

    captured = capsys.readouterr()
    combined = "\n".join(
        [
            captured.out,
            captured.err,
            caplog.text,
            report.getvalue(),
            summary,
            rendered,
            str(streaming_result),
            "".join(traceback.format_exception(Exception(summary))),
        ]
    )
    for prohibited in (
        SENTINEL_SECRET,
        "sentinel_secret_never_emit",
        "Authorization",
    ):
        assert prohibited not in combined
    assert "exit=0" in summary
    assert "streaming status=fail" in summary
    assert "function_call status=pass" in summary
    assert exit_code == DIAGNOSTIC_EXIT_SUCCESS

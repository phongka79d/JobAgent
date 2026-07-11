from __future__ import annotations

import io
import logging
import traceback

import pytest

from scripts.check_shopaikey_compatibility import (
    Capability,
    ConfigurationError,
    DiagnosticHarness,
    ResultStatus,
    ShopAIKeyConfig,
    bind_diagnostic_tools,
    load_config,
)


SENTINEL_SECRET = "sentinel-secret-never-emit"


def valid_environment() -> dict[str, str]:
    return {
        "SHOPAIKEY_BASE_URL": "https://provider.example/v1",
        "SHOPAIKEY_API_KEY": SENTINEL_SECRET,
        "LLM_MODEL": "gpt-4o-mini",
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SHOPAIKEY_BASE_URL", ""),
        ("SHOPAIKEY_BASE_URL", "file:///private/provider"),
        (
            "SHOPAIKEY_BASE_URL",
            f"https://user:{SENTINEL_SECRET}@provider.example/v1",
        ),
        ("SHOPAIKEY_API_KEY", ""),
        ("LLM_MODEL", ""),
    ],
)
def test_configuration_rejects_missing_or_invalid_values_without_echoing_them(
    name: str, value: str
) -> None:
    environment = valid_environment()
    environment[name] = value

    with pytest.raises(ConfigurationError) as raised:
        load_config(environment)

    rendered_error = str(raised.value)
    assert SENTINEL_SECRET not in rendered_error
    assert "Authorization" not in rendered_error
    assert "SHOPAIKEY_API_KEY" not in rendered_error


@pytest.mark.parametrize(
    "base_url",
    [
        f"https://provider.example/v1?api_key={SENTINEL_SECRET}",
        f"https://provider.example/v1#api-key={SENTINEL_SECRET}",
        f"https://user:{SENTINEL_SECRET}@provider.example/v1",
    ],
)
def test_configuration_rejects_credential_bearing_url_components(
    base_url: str,
) -> None:
    environment = valid_environment()
    environment["SHOPAIKEY_BASE_URL"] = base_url

    with pytest.raises(ConfigurationError) as raised:
        load_config(environment)

    assert SENTINEL_SECRET not in str(raised.value)


def test_configuration_is_typed_and_hides_key_from_representations() -> None:
    config = load_config(valid_environment())

    assert isinstance(config, ShopAIKeyConfig)
    assert config.model == "gpt-4o-mini"
    assert SENTINEL_SECRET not in repr(config)
    assert SENTINEL_SECRET not in str(config)


def test_model_factory_receives_custom_endpoint_and_binds_tools() -> None:
    calls: list[dict[str, object]] = []
    tools = [{"name": "synthetic_tool"}]

    class FakeModel:
        def bind_tools(self, supplied_tools: object) -> tuple[str, object]:
            return ("bound", supplied_tools)

    def fake_factory(**kwargs: object) -> FakeModel:
        calls.append(kwargs)
        return FakeModel()

    bound = bind_diagnostic_tools(load_config(valid_environment()), tools, fake_factory)

    assert bound == ("bound", tools)
    assert calls == [
        {
            "api_key": SENTINEL_SECRET,
            "base_url": "https://provider.example/v1",
            "model": "gpt-4o-mini",
            "temperature": 0,
        }
    ]


def test_records_are_deterministic_and_streaming_is_not_required_pass() -> None:
    harness = DiagnosticHarness(secrets=[SENTINEL_SECRET])
    result = harness.record(
        Capability.BASIC_COMPLETION,
        ResultStatus.PASS,
        evidence={"observed": True, "summary": "non-empty"},
        selected_mode="chat",
    )

    assert harness.required_pass_capabilities == (
        Capability.MODEL_DISCOVERY,
        Capability.BASIC_COMPLETION,
        Capability.FUNCTION_CALL,
        Capability.TOOL_ROUND_TRIP,
        Capability.STRUCTURED_SCHEMA,
    )
    assert Capability.STREAMING not in harness.required_pass_capabilities
    assert harness.render([result]) == (
        '[{"capability":"basic_completion","evidence":{"observed":true,'
        '"summary":"non-empty"},"failure_code":null,"selected_mode":"chat",'
        '"status":"pass"}]'
    )


def test_sentinel_and_sensitive_fields_never_reach_any_output_surface(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    harness = DiagnosticHarness(secrets=[SENTINEL_SECRET])
    result = harness.record(
        Capability.FUNCTION_CALL,
        ResultStatus.FAIL,
        evidence={
            "summary": f"Authorization: Bearer {SENTINEL_SECRET}",
            "tool_arguments": {"document_text": "private CV text"},
            "provider_headers": {"x-request-id": "private-header"},
        },
        failure_code="provider_error",
    )
    rendered = harness.render([result])
    report = io.StringIO()
    logger = logging.getLogger("shopaikey-sentinel-test")

    print(rendered)
    print(rendered, file=__import__("sys").stderr)
    logger.warning("%s", rendered)
    report.write(rendered)
    with pytest.raises(RuntimeError) as raised:
        raise harness.safe_exception(SENTINEL_SECRET) from RuntimeError(
            f"Authorization: Bearer {SENTINEL_SECRET}"
        )

    captured = capsys.readouterr()
    combined = "\n".join(
        [captured.out, captured.err, caplog.text, report.getvalue(), str(raised.value)]
    )
    for prohibited in (
        SENTINEL_SECRET,
        "sentinel_secret_never_emit",
        "Authorization",
        "provider_headers",
        "tool_arguments",
        "document_text",
        "private CV text",
        "private-header",
    ):
        assert prohibited not in combined
    assert "[REDACTED]" in combined


def test_sensitive_header_variants_and_chained_causes_are_sanitized() -> None:
    harness = DiagnosticHarness(secrets=[SENTINEL_SECRET])
    authorization_name = "".join(("Author", "ization"))
    failure_name = "_".join(("api", "key"))
    result = harness.record(
        Capability.FUNCTION_CALL,
        ResultStatus.FAIL,
        evidence={
            "Authorization": f"Bearer {SENTINEL_SECRET}",
            "X-API-Key": SENTINEL_SECRET,
            "x_api_key": SENTINEL_SECRET,
            "api-key": SENTINEL_SECRET,
            "api_key": SENTINEL_SECRET,
        },
        failure_code=f"api-key:{SENTINEL_SECRET}",
    )

    with pytest.raises(RuntimeError) as raised:
        try:
            raise RuntimeError(f"{authorization_name}: Bearer {SENTINEL_SECRET}")
        except RuntimeError as source:
            raise harness.safe_exception(f"{failure_name}:{SENTINEL_SECRET}") from source

    combined = "\n".join(
        [
            harness.render([result]),
            "".join(traceback.format_exception(raised.value)),
            str(raised.value),
        ]
    )
    for prohibited in (
        SENTINEL_SECRET,
        "sentinel_secret_never_emit",
        "Authorization",
        "X-API-Key",
        "x_api_key",
        "api-key",
        "api_key",
    ):
        assert prohibited not in combined
    assert str(raised.value) == "diagnostic_failed"


def test_safe_exception_never_exposes_normalized_configured_secrets() -> None:
    harness = DiagnosticHarness(secrets=[SENTINEL_SECRET])
    normalized_secret = SENTINEL_SECRET.replace("-", "_").upper()
    error = harness.safe_exception(normalized_secret)
    rendered = "\n".join(
        [str(error), repr(error), "".join(traceback.format_exception(error))]
    )

    assert SENTINEL_SECRET not in rendered
    assert normalized_secret not in rendered
    assert normalized_secret.lower() not in rendered.lower()
    assert str(error) == "diagnostic_failed"


@pytest.mark.parametrize(
    "material",
    [
        SENTINEL_SECRET,
        SENTINEL_SECRET.replace("-", "_").upper(),
    ],
)
def test_record_redacts_raw_and_normalized_configured_secrets(material: str) -> None:
    harness = DiagnosticHarness(secrets=[SENTINEL_SECRET])
    normalized_secret = SENTINEL_SECRET.replace("-", "_").upper()
    result = harness.record(
        Capability.FUNCTION_CALL,
        ResultStatus.FAIL,
        evidence={"summary": f"provider said {material}"},
        failure_code=f"code:{material}",
        selected_mode=f"mode:{material}",
    )
    error = harness.safe_exception(material)
    combined = "\n".join(
        [
            harness.render([result]),
            str(result),
            repr(result),
            str(error),
            repr(error),
            "".join(traceback.format_exception(error)),
        ]
    )

    for prohibited in (
        SENTINEL_SECRET,
        normalized_secret,
        "sentinel_secret_never_emit",
        "sentinelsecretneveremit",
    ):
        assert prohibited not in combined
        assert prohibited not in combined.lower()
    assert result.evidence == {"summary": "[REDACTED]"}
    assert result.failure_code == "[REDACTED]"
    assert result.selected_mode == "[REDACTED]"
    assert str(error) == "diagnostic_failed"

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError


ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
REDACTED = "[REDACTED]"
MASTER_LOCKED_CHAT_MODEL = "gpt-4o-mini"
# Content-neutral prompt only; never include CV/JD or private document text.
MINIMAL_COMPLETION_PROMPT = "Reply with the single word ok."
# Harmless synthetic tool: short label only; no document or private-data fields.
SYNTHETIC_TOOL_NAME = "echo_label"
EXPECTED_ECHO_LABEL = "ping"
FUNCTION_CALL_PROMPT = (
    "Call the echo_label tool exactly once with label set to the word ping."
)
SYNTHETIC_TOOL_RESULT = "ok:ping"
# Content-neutral structured probe; no CV/JD or private document fields.
STRUCTURED_SCHEMA_PROMPT = (
    "Return one JSON object with item_id set to probe-1, count set to 1, "
    "and active set to true."
)
STRUCTURED_SCHEMA_REPAIR_PROMPT = (
    "Previous output failed schema validation. Return only one JSON object "
    "with required fields item_id (string), count (integer), and active (boolean)."
)
# Content-neutral streaming probe; no CV/JD or private document text.
STREAMING_PROMPT = "Reply with the single word ok."
# 03A-approved reliability criterion (do not invent a different rule).
APPROVED_RELIABILITY_ATTEMPT_COUNT = 3
APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT = 1
# strict=True stays off by default until a mode run verifies it.
STRICT_ENABLED_BY_DEFAULT = False
# Diagnostic process exit: non-zero when any required-pass is not PASS.
DIAGNOSTIC_EXIT_SUCCESS = 0
DIAGNOSTIC_EXIT_REQUIRED_FAILURE = 1
_SENSITIVE_MARKERS = (
    "authorization",
    "apikey",
    "documenttext",
    "headers",
    "providerheaders",
    "toolarguments",
)


class Capability(StrEnum):
    MODEL_DISCOVERY = "model_discovery"
    BASIC_COMPLETION = "basic_completion"
    FUNCTION_CALL = "function_call"
    TOOL_ROUND_TRIP = "tool_round_trip"
    STRUCTURED_SCHEMA = "structured_schema"
    STREAMING = "streaming"


class ResultStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"
    UNSUPPORTED = "unsupported"


REQUIRED_PASS_CAPABILITIES = (
    Capability.MODEL_DISCOVERY,
    Capability.BASIC_COMPLETION,
    Capability.FUNCTION_CALL,
    Capability.TOOL_ROUND_TRIP,
    Capability.STRUCTURED_SCHEMA,
)


class DiagnosticResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    capability: Capability
    evidence: dict[str, Any]
    failure_code: str | None = None
    selected_mode: str | None = None
    status: ResultStatus


class ConfigurationError(RuntimeError):
    pass


class SanitizedDiagnosticError(RuntimeError):
    def __getattribute__(self, name: str) -> object:
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@dataclass(frozen=True)
class ShopAIKeyConfig:
    base_url: str
    api_key: str
    model: str

    def __repr__(self) -> str:
        return (
            "ShopAIKeyConfig(base_url="
            f"{self.base_url!r}, api_key={REDACTED!r}, model={self.model!r})"
        )

    __str__ = __repr__


class ToolBindableModel(Protocol):
    def bind_tools(self, tools: Sequence[object]) -> object: ...


ModelFactory = Callable[..., ToolBindableModel]


def load_config(environment: Mapping[str, str]) -> ShopAIKeyConfig:
    base_url = environment.get("SHOPAIKEY_BASE_URL", "").strip()
    api_key = environment.get("SHOPAIKEY_API_KEY", "").strip()
    model = environment.get("LLM_MODEL", "").strip()
    try:
        parsed_url = urlsplit(base_url)
    except ValueError as error:
        raise ConfigurationError("Invalid diagnostic configuration.") from None

    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ConfigurationError("Invalid diagnostic configuration.")
    if not api_key or not model:
        raise ConfigurationError("Invalid diagnostic configuration.")
    return ShopAIKeyConfig(base_url=base_url, api_key=api_key, model=model)


def load_root_config() -> ShopAIKeyConfig:
    file_values = {
        key: value for key, value in dotenv_values(ROOT_ENV).items() if value is not None
    }
    values = {
        name: os.environ.get(name, file_values.get(name, ""))
        for name in ("SHOPAIKEY_BASE_URL", "SHOPAIKEY_API_KEY", "LLM_MODEL")
    }
    return load_config(values)


def _chat_model_factory(**kwargs: object) -> ToolBindableModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(**kwargs)


def bind_diagnostic_tools(
    config: ShopAIKeyConfig,
    tools: Sequence[object],
    model_factory: ModelFactory = _chat_model_factory,
) -> object:
    model = model_factory(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0,
    )
    return model.bind_tools(tools)


ListModelIdsFn = Callable[[ShopAIKeyConfig], Sequence[str]]
BasicCompletionFn = Callable[[ShopAIKeyConfig, str], "BasicCompletionObservation"]
FunctionCallFn = Callable[
    [ShopAIKeyConfig, str, Sequence[object]], "FunctionCallObservation"
]
ToolRoundTripFn = Callable[
    [ShopAIKeyConfig, str, Sequence[object], "ObservedToolCall", str],
    "ToolRoundTripObservation",
]
StructuredSchemaFn = Callable[
    [ShopAIKeyConfig, "SchemaMode", str, bool],
    "StructuredSchemaObservation",
]
StreamingFn = Callable[[ShopAIKeyConfig, str], "StreamingObservation"]


@dataclass(frozen=True)
class BasicCompletionObservation:
    assistant_text: str
    response_model: str | None = None


class EchoLabelArgs(BaseModel):
    """Minimal synthetic tool input. Short label only; no document fields."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=32)


@dataclass(frozen=True)
class ObservedToolCall:
    name: str
    arguments: object
    tool_call_id: str | None = None


@dataclass(frozen=True)
class FunctionCallObservation:
    tool_calls: tuple[ObservedToolCall, ...]


@dataclass(frozen=True)
class ToolRoundTripObservation:
    final_assistant_text: str


def synthetic_echo_label_tool() -> dict[str, object]:
    """OpenAI-format tool schema for the harmless echo_label contract."""
    return {
        "type": "function",
        "function": {
            "name": SYNTHETIC_TOOL_NAME,
            "description": (
                "Echo a short neutral label token. "
                "Do not accept documents, CV, JD, or private content."
            ),
            "parameters": EchoLabelArgs.model_json_schema(),
        },
    }


def _parse_and_validate_tool_arguments(
    raw: object,
) -> tuple[EchoLabelArgs | None, str | None]:
    """Parse tool args as JSON object and validate against EchoLabelArgs.

    Returns (parsed_model, failure_code). failure_code is set on error.
    Does not return raw document payloads into evidence paths.
    """
    if isinstance(raw, str):
        try:
            data: object = json.loads(raw)
        except json.JSONDecodeError:
            return None, "malformed_json_arguments"
    elif isinstance(raw, Mapping):
        data = dict(raw)
    else:
        return None, "malformed_json_arguments"

    if not isinstance(data, Mapping):
        return None, "malformed_json_arguments"

    try:
        return EchoLabelArgs.model_validate(data), None
    except ValidationError:
        return None, "invalid_typed_arguments"


def _default_list_model_ids(config: ShopAIKeyConfig) -> tuple[str, ...]:
    # OpenAI-compatible GET {base_url}/models. Do not log request headers.
    from openai import OpenAI

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    page = client.models.list()
    return tuple(str(item.id) for item in page.data)


def _assistant_text_from_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Mapping):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _default_basic_completion(
    config: ShopAIKeyConfig, prompt: str
) -> BasicCompletionObservation:
    from langchain_core.messages import HumanMessage

    model = _chat_model_factory(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0,
    )
    # Always request the configured model; never substitute another ID.
    message = model.invoke([HumanMessage(content=prompt)])  # type: ignore[attr-defined]
    metadata = getattr(message, "response_metadata", None) or {}
    response_model = metadata.get("model_name") or metadata.get("model")
    if response_model is not None:
        response_model = str(response_model)
    return BasicCompletionObservation(
        assistant_text=_assistant_text_from_content(getattr(message, "content", None)),
        response_model=response_model,
    )


def check_model_discovery(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    list_model_ids: ListModelIdsFn = _default_list_model_ids,
) -> DiagnosticResult:
    """Classify whether the configured/master-locked chat model is discoverable.

    Live PASS requires the master-locked ID. An equivalent may be characterized
    but cannot pass until the master-plan adapter decision is revised.
    """
    try:
        model_ids = tuple(list_model_ids(config))
    except Exception:
        return harness.record(
            Capability.MODEL_DISCOVERY,
            ResultStatus.FAIL,
            evidence={"summary": "model_discovery_failed"},
            failure_code="provider_error",
        )

    id_set = set(model_ids)
    configured = config.model
    configured_present = configured in id_set
    master_present = MASTER_LOCKED_CHAT_MODEL in id_set
    # Bounded evidence only: presence flags, not the full provider model catalog.
    base_evidence: dict[str, object] = {
        "configured_model": configured,
        "configured_present": configured_present,
        "master_locked_model": MASTER_LOCKED_CHAT_MODEL,
        "master_present": master_present,
        "listed_model_count": len(model_ids),
    }

    if configured_present and configured == MASTER_LOCKED_CHAT_MODEL:
        return harness.record(
            Capability.MODEL_DISCOVERY,
            ResultStatus.PASS,
            evidence={
                **base_evidence,
                "match_status": "exact_master_lock",
                "silent_substitution": False,
            },
            selected_mode=MASTER_LOCKED_CHAT_MODEL,
        )

    if configured_present and configured != MASTER_LOCKED_CHAT_MODEL:
        return harness.record(
            Capability.MODEL_DISCOVERY,
            ResultStatus.FAIL,
            evidence={
                **base_evidence,
                "match_status": "equivalent_requires_source_revision",
                "silent_substitution": False,
            },
            failure_code="equivalent_requires_source_revision",
            selected_mode=configured,
        )

    return harness.record(
        Capability.MODEL_DISCOVERY,
        ResultStatus.FAIL,
        evidence={
            **base_evidence,
            "match_status": "model_absent",
            "silent_substitution": False,
        },
        failure_code="model_absent",
    )


def check_basic_completion(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    complete: BasicCompletionFn = _default_basic_completion,
    prompt: str = MINIMAL_COMPLETION_PROMPT,
) -> DiagnosticResult:
    """Run a content-neutral minimal completion and classify the assistant text.

    Does not silently switch models. Empty assistant text fails. Non-empty
    text with a matching (or unreported) response model passes.
    """
    try:
        observation = complete(config, prompt)
    except Exception:
        return harness.record(
            Capability.BASIC_COMPLETION,
            ResultStatus.FAIL,
            evidence={"summary": "basic_completion_failed"},
            failure_code="provider_error",
        )

    response_model = observation.response_model
    if response_model is not None and response_model != config.model:
        return harness.record(
            Capability.BASIC_COMPLETION,
            ResultStatus.FAIL,
            evidence={
                "configured_model": config.model,
                "response_model_reported": True,
                "model_match": False,
                "response_non_empty": False,
                "match_status": "silent_substitution_rejected",
                "summary": "provider_reported_different_model",
            },
            failure_code="silent_substitution_rejected",
        )

    text = observation.assistant_text or ""
    non_empty = bool(text.strip())
    if not non_empty:
        return harness.record(
            Capability.BASIC_COMPLETION,
            ResultStatus.FAIL,
            evidence={
                "configured_model": config.model,
                "response_model_reported": response_model is not None,
                "model_match": True,
                "response_non_empty": False,
                "match_status": "empty_response",
                "summary": "empty_assistant_response",
            },
            failure_code="empty_response",
        )

    return harness.record(
        Capability.BASIC_COMPLETION,
        ResultStatus.PASS,
        evidence={
            "configured_model": config.model,
            "response_model_reported": response_model is not None,
            "model_match": True,
            "response_non_empty": True,
            "match_status": "non_empty_response",
            "summary": "non_empty_assistant_response",
        },
        selected_mode="chat",
    )


def _tool_call_from_provider_item(item: object) -> ObservedToolCall:
    if isinstance(item, Mapping):
        name = item.get("name", "")
        arguments = item.get("args", item.get("arguments"))
        tool_call_id = item.get("id")
        return ObservedToolCall(
            name=str(name) if name is not None else "",
            arguments=arguments,
            tool_call_id=str(tool_call_id) if tool_call_id is not None else None,
        )
    name = getattr(item, "name", "")
    arguments = getattr(item, "args", None)
    if arguments is None:
        arguments = getattr(item, "arguments", None)
    tool_call_id = getattr(item, "id", None)
    return ObservedToolCall(
        name=str(name) if name is not None else "",
        arguments=arguments,
        tool_call_id=str(tool_call_id) if tool_call_id is not None else None,
    )


def _default_function_call(
    config: ShopAIKeyConfig,
    prompt: str,
    tools: Sequence[object],
) -> FunctionCallObservation:
    from langchain_core.messages import HumanMessage

    bound = bind_diagnostic_tools(config, tools)
    message = bound.invoke([HumanMessage(content=prompt)])  # type: ignore[attr-defined]
    raw_calls = getattr(message, "tool_calls", None) or ()
    return FunctionCallObservation(
        tool_calls=tuple(_tool_call_from_provider_item(item) for item in raw_calls)
    )


def _default_tool_round_trip(
    config: ShopAIKeyConfig,
    prompt: str,
    tools: Sequence[object],
    prior_call: ObservedToolCall,
    tool_result_content: str,
) -> ToolRoundTripObservation:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    bound = bind_diagnostic_tools(config, tools)
    tool_call_id = prior_call.tool_call_id or "synthetic-call-1"
    if isinstance(prior_call.arguments, Mapping):
        args_payload: dict[str, object] = dict(prior_call.arguments)
    else:
        args_payload = {}
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": prior_call.name,
                "args": args_payload,
                "id": tool_call_id,
                "type": "tool_call",
            }
        ],
    )
    tool_message = ToolMessage(
        content=tool_result_content,
        tool_call_id=tool_call_id,
    )
    message = bound.invoke(  # type: ignore[attr-defined]
        [HumanMessage(content=prompt), ai_message, tool_message]
    )
    return ToolRoundTripObservation(
        final_assistant_text=_assistant_text_from_content(
            getattr(message, "content", None)
        )
    )


def check_function_call(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    invoke_function_call: FunctionCallFn = _default_function_call,
    prompt: str = FUNCTION_CALL_PROMPT,
    tools: Sequence[object] | None = None,
    expected_tool_name: str = SYNTHETIC_TOOL_NAME,
) -> DiagnosticResult:
    """Bind one synthetic tool, request a call, validate name and typed JSON args.

    Evidence is bounded to flags only; raw tool argument values are never recorded.
    """
    bound_tools = tuple(tools) if tools is not None else (synthetic_echo_label_tool(),)
    try:
        observation = invoke_function_call(config, prompt, bound_tools)
    except Exception:
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={"summary": "function_call_failed"},
            failure_code="provider_error",
        )

    calls = observation.tool_calls
    call_count = len(calls)
    if call_count == 0:
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={
                "tool_call_count": 0,
                "tool_name_match": False,
                "argument_json_valid": False,
                "argument_schema_valid": False,
                "match_status": "missing_tool_call",
                "summary": "missing_tool_call",
            },
            failure_code="missing_tool_call",
        )

    if call_count > 1:
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={
                "tool_call_count": call_count,
                "tool_name_match": False,
                "argument_json_valid": False,
                "argument_schema_valid": False,
                "match_status": "multiple_unexpected_calls",
                "summary": "multiple_unexpected_calls",
            },
            failure_code="multiple_unexpected_calls",
        )

    call = calls[0]
    if call.name != expected_tool_name:
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={
                "tool_call_count": 1,
                "tool_name_match": False,
                "argument_json_valid": False,
                "argument_schema_valid": False,
                "match_status": "wrong_tool",
                "summary": "wrong_tool",
            },
            failure_code="wrong_tool",
        )

    parsed, arg_failure = _parse_and_validate_tool_arguments(call.arguments)
    if arg_failure == "malformed_json_arguments":
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={
                "tool_call_count": 1,
                "tool_name_match": True,
                "argument_json_valid": False,
                "argument_schema_valid": False,
                "match_status": "malformed_json_arguments",
                "summary": "malformed_json_arguments",
            },
            failure_code="malformed_json_arguments",
        )
    if arg_failure is not None or parsed is None:
        return harness.record(
            Capability.FUNCTION_CALL,
            ResultStatus.FAIL,
            evidence={
                "tool_call_count": 1,
                "tool_name_match": True,
                "argument_json_valid": True,
                "argument_schema_valid": False,
                "match_status": "invalid_typed_arguments",
                "summary": "invalid_typed_arguments",
            },
            failure_code="invalid_typed_arguments",
        )

    return harness.record(
        Capability.FUNCTION_CALL,
        ResultStatus.PASS,
        evidence={
            "tool_call_count": 1,
            "tool_name_match": True,
            "argument_json_valid": True,
            "argument_schema_valid": True,
            "expected_tool_name": expected_tool_name,
            "match_status": "valid_function_call",
            "summary": "valid_tool_name_and_typed_arguments",
        },
        selected_mode="bind_tools",
    )


def check_tool_round_trip(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    invoke_tool_round_trip: ToolRoundTripFn = _default_tool_round_trip,
    prompt: str = FUNCTION_CALL_PROMPT,
    tools: Sequence[object] | None = None,
    prior_call: ObservedToolCall | None = None,
    tool_result_content: str = SYNTHETIC_TOOL_RESULT,
) -> DiagnosticResult:
    """Supply a synthetic tool result and require a non-empty final assistant reply.

    Uses the provider-compatible Human/AI/Tool message contract via the bound model.
    """
    bound_tools = tuple(tools) if tools is not None else (synthetic_echo_label_tool(),)
    call = prior_call or ObservedToolCall(
        name=SYNTHETIC_TOOL_NAME,
        arguments={"label": EXPECTED_ECHO_LABEL},
        tool_call_id="synthetic-call-1",
    )
    try:
        observation = invoke_tool_round_trip(
            config, prompt, bound_tools, call, tool_result_content
        )
    except Exception:
        return harness.record(
            Capability.TOOL_ROUND_TRIP,
            ResultStatus.FAIL,
            evidence={"summary": "tool_round_trip_failed"},
            failure_code="provider_error",
        )

    text = observation.final_assistant_text or ""
    if not text.strip():
        return harness.record(
            Capability.TOOL_ROUND_TRIP,
            ResultStatus.FAIL,
            evidence={
                "final_response_non_empty": False,
                "match_status": "missing_final_response",
                "summary": "missing_final_response",
            },
            failure_code="missing_final_response",
        )

    return harness.record(
        Capability.TOOL_ROUND_TRIP,
        ResultStatus.PASS,
        evidence={
            "final_response_non_empty": True,
            "match_status": "final_response_after_tool_result",
            "summary": "non_empty_final_assistant_response",
        },
        selected_mode="tool_result_round_trip",
    )


class SchemaMode(StrEnum):
    """Permitted structured-output strategies in diagnostic order."""

    STRICT_SCHEMA = "strict_schema"
    FUNCTION_SCHEMA = "function_schema"
    JSON_MODE = "json_mode"


# Master-plan order: observe strict first; fall back to ordinary function or JSON.
PERMITTED_SCHEMA_MODES_IN_ORDER: tuple[SchemaMode, ...] = (
    SchemaMode.STRICT_SCHEMA,
    SchemaMode.FUNCTION_SCHEMA,
    SchemaMode.JSON_MODE,
)


class SchemaProbeResponse(BaseModel):
    """Local Pydantic v2 probe for structured output. No private content fields."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    count: int
    active: bool


@dataclass(frozen=True)
class StructuredSchemaObservation:
    """One provider response for a structured-schema strategy.

    mode_supported=False marks strategy incompatibility (e.g. strict rejected)
    without treating it as a validated payload failure.
    """

    payload: object | None = None
    mode_supported: bool = True
    incompatibility_reason: str | None = None


@dataclass(frozen=True)
class SchemaAttemptResult:
    """Typed per-attempt result for reliability evaluation (03F consumes this)."""

    mode: SchemaMode
    attempt_index: int
    validation_passed: bool
    repair_requests_used: int
    failure_code: str | None = None
    match_status: str = "unknown"

    def bounded_evidence(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "attempt_index": self.attempt_index,
            "validation_passed": self.validation_passed,
            "repair_requests_used": self.repair_requests_used,
            "max_repair_per_attempt": APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT,
            "match_status": self.match_status,
        }


@dataclass(frozen=True)
class ReliabilityEvaluation:
    """Whether a sequence of attempts satisfies the 03A-approved criterion."""

    reliable: bool
    mode: SchemaMode | None
    attempt_count: int
    required_attempt_count: int
    max_repair_per_attempt: int
    all_validation_passed: bool
    repair_limit_respected: bool
    reason: str

    def bounded_evidence(self) -> dict[str, object]:
        return {
            "reliable": self.reliable,
            "mode": self.mode.value if self.mode is not None else None,
            "attempt_count": self.attempt_count,
            "required_attempt_count": self.required_attempt_count,
            "max_repair_per_attempt": self.max_repair_per_attempt,
            "all_validation_passed": self.all_validation_passed,
            "repair_limit_respected": self.repair_limit_respected,
            "reason": self.reason,
        }


def validate_schema_probe_payload(
    payload: object,
) -> tuple[SchemaProbeResponse | None, str | None]:
    """Validate structured output against SchemaProbeResponse.

    Returns (model, failure_code). failure_code is set on error.
    Does not echo raw payload values into caller evidence paths.
    """
    if payload is None:
        return None, "missing_payload"
    if isinstance(payload, SchemaProbeResponse):
        try:
            return SchemaProbeResponse.model_validate(payload.model_dump()), None
        except ValidationError:
            return None, "invalid_types"
    if isinstance(payload, str):
        try:
            data: object = json.loads(payload)
        except json.JSONDecodeError:
            return None, "malformed_json_payload"
    elif isinstance(payload, Mapping):
        data = dict(payload)
    elif isinstance(payload, BaseModel):
        data = payload.model_dump()
    else:
        return None, "invalid_payload_shape"

    if not isinstance(data, Mapping):
        return None, "invalid_payload_shape"

    try:
        return SchemaProbeResponse.model_validate(data), None
    except ValidationError as error:
        # Prefer a type-oriented code when errors look type-related.
        type_markers = (
            "type_error",
            "int_type",
            "bool_type",
            "string_type",
            "float_type",
            "int_parsing",
            "bool_parsing",
            "float_parsing",
            "string_parsing",
        )
        for item in error.errors():
            error_type = str(item.get("type", ""))
            if error_type.startswith("type_error") or error_type in type_markers:
                return None, "invalid_types"
            if error_type.endswith("_type") or error_type.endswith("_parsing"):
                return None, "invalid_types"
        return None, "schema_validation_failed"


def _default_structured_schema(
    config: ShopAIKeyConfig,
    mode: SchemaMode,
    prompt: str,
    is_repair: bool,
) -> StructuredSchemaObservation:
    """Invoke ChatOpenAI structured output for the requested strategy.

    strict=True is used only for SchemaMode.STRICT_SCHEMA observation runs.
    STRICT_ENABLED_BY_DEFAULT remains False until a mode is verified live (03F).
    """
    del is_repair  # prompt already encodes repair vs initial; keep signature stable
    from langchain_core.messages import HumanMessage

    # Guardrail: never enable strict outside the explicit strict observation mode.
    if mode is not SchemaMode.STRICT_SCHEMA and STRICT_ENABLED_BY_DEFAULT:
        pass

    model = _chat_model_factory(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0,
    )
    try:
        if mode is SchemaMode.STRICT_SCHEMA:
            structured = model.with_structured_output(  # type: ignore[attr-defined]
                SchemaProbeResponse,
                method="function_calling",
                strict=True,
            )
        elif mode is SchemaMode.FUNCTION_SCHEMA:
            structured = model.with_structured_output(  # type: ignore[attr-defined]
                SchemaProbeResponse,
                method="function_calling",
                strict=False,
            )
        elif mode is SchemaMode.JSON_MODE:
            structured = model.with_structured_output(  # type: ignore[attr-defined]
                SchemaProbeResponse,
                method="json_mode",
            )
        else:
            return StructuredSchemaObservation(
                mode_supported=False,
                incompatibility_reason="unknown_mode",
            )
        result = structured.invoke([HumanMessage(content=prompt)])
    except Exception as error:
        message = str(error).lower()
        if mode is SchemaMode.STRICT_SCHEMA and (
            "strict" in message or "unsupported" in message or "invalid schema" in message
        ):
            return StructuredSchemaObservation(
                mode_supported=False,
                incompatibility_reason="strict_incompatible",
            )
        raise

    if isinstance(result, BaseModel):
        return StructuredSchemaObservation(payload=result.model_dump())
    return StructuredSchemaObservation(payload=result)


def run_structured_schema_attempt(
    config: ShopAIKeyConfig,
    mode: SchemaMode,
    *,
    attempt_index: int,
    invoke_structured: StructuredSchemaFn = _default_structured_schema,
    prompt: str = STRUCTURED_SCHEMA_PROMPT,
    repair_prompt: str = STRUCTURED_SCHEMA_REPAIR_PROMPT,
    max_repair_requests: int = APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT,
) -> SchemaAttemptResult:
    """Run one structured-schema attempt with at most one repair request.

    Repair count is explicit. A second repair is never issued even if still invalid.
    """
    if max_repair_requests > APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT:
        # Enforce the approved one-repair ceiling regardless of caller.
        max_repair_requests = APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT

    repair_requests_used = 0
    try:
        observation = invoke_structured(config, mode, prompt, False)
    except Exception:
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=False,
            repair_requests_used=0,
            failure_code="provider_error",
            match_status="provider_error",
        )

    if not observation.mode_supported:
        reason = observation.incompatibility_reason or "mode_unsupported"
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=False,
            repair_requests_used=0,
            failure_code=reason,
            match_status=reason,
        )

    parsed, failure = validate_schema_probe_payload(observation.payload)
    if parsed is not None and failure is None:
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=True,
            repair_requests_used=0,
            failure_code=None,
            match_status="valid_first_response",
        )

    # First response invalid: at most one repair request.
    if repair_requests_used >= max_repair_requests:
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=False,
            repair_requests_used=repair_requests_used,
            failure_code=failure or "schema_validation_failed",
            match_status="repair_limit_enforced",
        )

    repair_requests_used = 1
    try:
        repair_observation = invoke_structured(config, mode, repair_prompt, True)
    except Exception:
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=False,
            repair_requests_used=repair_requests_used,
            failure_code="provider_error",
            match_status="repair_provider_error",
        )

    if not repair_observation.mode_supported:
        reason = repair_observation.incompatibility_reason or "mode_unsupported"
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=False,
            repair_requests_used=repair_requests_used,
            failure_code=reason,
            match_status=reason,
        )

    repaired, repair_failure = validate_schema_probe_payload(repair_observation.payload)
    if repaired is not None and repair_failure is None:
        return SchemaAttemptResult(
            mode=mode,
            attempt_index=attempt_index,
            validation_passed=True,
            repair_requests_used=repair_requests_used,
            failure_code=None,
            match_status="valid_after_one_repair",
        )

    return SchemaAttemptResult(
        mode=mode,
        attempt_index=attempt_index,
        validation_passed=False,
        repair_requests_used=repair_requests_used,
        failure_code=repair_failure or failure or "schema_validation_failed",
        match_status="invalid_after_one_repair",
    )


def evaluate_mode_reliability(
    attempts: Sequence[SchemaAttemptResult],
    *,
    required_attempt_count: int = APPROVED_RELIABILITY_ATTEMPT_COUNT,
    max_repair_per_attempt: int = APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT,
) -> ReliabilityEvaluation:
    """Apply the 03A-approved reliability criterion to per-attempt results.

    Criterion: three consecutive attempts using one schema mode; all three pass
    local Pydantic validation; at most one repair request per attempt.
    """
    attempt_list = list(attempts)
    mode = attempt_list[0].mode if attempt_list else None
    if len(attempt_list) < required_attempt_count:
        return ReliabilityEvaluation(
            reliable=False,
            mode=mode,
            attempt_count=len(attempt_list),
            required_attempt_count=required_attempt_count,
            max_repair_per_attempt=max_repair_per_attempt,
            all_validation_passed=False,
            repair_limit_respected=True,
            reason="insufficient_attempts",
        )

    consecutive = attempt_list[:required_attempt_count]
    if any(item.mode != consecutive[0].mode for item in consecutive):
        return ReliabilityEvaluation(
            reliable=False,
            mode=consecutive[0].mode,
            attempt_count=len(consecutive),
            required_attempt_count=required_attempt_count,
            max_repair_per_attempt=max_repair_per_attempt,
            all_validation_passed=False,
            repair_limit_respected=True,
            reason="mixed_modes",
        )

    if any(
        item.failure_code
        in {"strict_incompatible", "mode_unsupported", "unknown_mode"}
        for item in consecutive
    ):
        return ReliabilityEvaluation(
            reliable=False,
            mode=consecutive[0].mode,
            attempt_count=len(consecutive),
            required_attempt_count=required_attempt_count,
            max_repair_per_attempt=max_repair_per_attempt,
            all_validation_passed=False,
            repair_limit_respected=True,
            reason="mode_incompatible",
        )

    repair_limit_respected = all(
        item.repair_requests_used <= max_repair_per_attempt for item in consecutive
    )
    all_passed = all(item.validation_passed for item in consecutive)
    if not repair_limit_respected:
        return ReliabilityEvaluation(
            reliable=False,
            mode=consecutive[0].mode,
            attempt_count=len(consecutive),
            required_attempt_count=required_attempt_count,
            max_repair_per_attempt=max_repair_per_attempt,
            all_validation_passed=all_passed,
            repair_limit_respected=False,
            reason="repair_limit_exceeded",
        )
    if not all_passed:
        return ReliabilityEvaluation(
            reliable=False,
            mode=consecutive[0].mode,
            attempt_count=len(consecutive),
            required_attempt_count=required_attempt_count,
            max_repair_per_attempt=max_repair_per_attempt,
            all_validation_passed=False,
            repair_limit_respected=True,
            reason="not_all_attempts_passed",
        )
    return ReliabilityEvaluation(
        reliable=True,
        mode=consecutive[0].mode,
        attempt_count=len(consecutive),
        required_attempt_count=required_attempt_count,
        max_repair_per_attempt=max_repair_per_attempt,
        all_validation_passed=True,
        repair_limit_respected=True,
        reason="approved_criterion_met",
    )


def check_structured_schema(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    invoke_structured: StructuredSchemaFn = _default_structured_schema,
    modes: Sequence[SchemaMode] = PERMITTED_SCHEMA_MODES_IN_ORDER,
    attempts_per_mode: int = APPROVED_RELIABILITY_ATTEMPT_COUNT,
    prompt: str = STRUCTURED_SCHEMA_PROMPT,
    repair_prompt: str = STRUCTURED_SCHEMA_REPAIR_PROMPT,
) -> DiagnosticResult:
    """Exercise permitted schema strategies and evaluate reliability per mode.

    Selects the first mode that meets the approved three-attempt criterion for
    this diagnostic run only. Does not lock a live provider mode in the report;
    live selection remains pending until 03F.
    """
    modes_tried: list[str] = []
    mode_summaries: list[dict[str, object]] = []

    for mode in modes:
        modes_tried.append(mode.value)
        attempts: list[SchemaAttemptResult] = []
        for index in range(attempts_per_mode):
            attempt = run_structured_schema_attempt(
                config,
                mode,
                attempt_index=index,
                invoke_structured=invoke_structured,
                prompt=prompt,
                repair_prompt=repair_prompt,
            )
            attempts.append(attempt)
            # Strict / mode incompatibility: stop early and try next strategy.
            if attempt.failure_code in {
                "strict_incompatible",
                "mode_unsupported",
                "unknown_mode",
            }:
                break

        if attempts and attempts[0].failure_code in {
            "strict_incompatible",
            "mode_unsupported",
            "unknown_mode",
        }:
            reliability = ReliabilityEvaluation(
                reliable=False,
                mode=mode,
                attempt_count=len(attempts),
                required_attempt_count=attempts_per_mode,
                max_repair_per_attempt=APPROVED_MAX_REPAIR_REQUESTS_PER_ATTEMPT,
                all_validation_passed=False,
                repair_limit_respected=True,
                reason="mode_incompatible",
            )
        else:
            reliability = evaluate_mode_reliability(attempts)
        mode_summaries.append(
            {
                "mode": mode.value,
                "attempt_count": len(attempts),
                "reliable": reliability.reliable,
                "reason": reliability.reason,
                "repairs_used_total": sum(
                    item.repair_requests_used for item in attempts
                ),
                "any_validation_passed": any(
                    item.validation_passed for item in attempts
                ),
            }
        )
        if reliability.reliable:
            return harness.record(
                Capability.STRUCTURED_SCHEMA,
                ResultStatus.PASS,
                evidence={
                    "modes_tried": modes_tried,
                    "selected_for_run": mode.value,
                    "reliability": reliability.bounded_evidence(),
                    "mode_summaries": mode_summaries,
                    "strict_enabled_by_default": STRICT_ENABLED_BY_DEFAULT,
                    "live_mode_locked": False,
                    "match_status": "reliable_mode_for_run",
                    "summary": "approved_reliability_criterion_met",
                },
                selected_mode=mode.value,
            )

    return harness.record(
        Capability.STRUCTURED_SCHEMA,
        ResultStatus.FAIL,
        evidence={
            "modes_tried": modes_tried,
            "selected_for_run": None,
            "mode_summaries": mode_summaries,
            "strict_enabled_by_default": STRICT_ENABLED_BY_DEFAULT,
            "live_mode_locked": False,
            "match_status": "no_reliable_mode",
            "summary": "no_permitted_mode_met_reliability_criterion",
        },
        failure_code="no_reliable_mode",
    )


@dataclass(frozen=True)
class StreamChunkMeta:
    """Bounded metadata for one stream chunk. Raw text is never retained."""

    arrival_index: int
    text_length: int
    sequence_index: int | None = None


@dataclass(frozen=True)
class StreamingObservation:
    """Provider streaming outcome for classification.

    explicitly_unsupported=True records a documented unsupported capability
    (knowledge-only; does not alone fail the required gate).
    """

    chunks: tuple[StreamChunkMeta, ...] = ()
    explicitly_unsupported: bool = False
    unsupported_reason: str | None = None


def _stream_chunks_sequence_ordered(chunks: Sequence[StreamChunkMeta]) -> bool:
    """True when provider sequence indices are strictly increasing, or absent.

    Arrival order alone is always ordered for a single consumer. Out-of-order
    is detected only when the provider supplies sequence indices.
    """
    if not chunks:
        return True
    with_sequence = [chunk for chunk in chunks if chunk.sequence_index is not None]
    if not with_sequence:
        return True
    if len(with_sequence) != len(chunks):
        return False
    indices = [int(chunk.sequence_index) for chunk in chunks]  # type: ignore[arg-type]
    return all(indices[i] < indices[i + 1] for i in range(len(indices) - 1))


def _default_streaming(
    config: ShopAIKeyConfig, prompt: str
) -> StreamingObservation:
    """Observe content-neutral streaming; retain only chunk metadata.

    Live transport for 03F. Normal automated tests inject fakes instead.
    """
    from langchain_core.messages import HumanMessage

    model = _chat_model_factory(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0,
        streaming=True,
    )
    try:
        stream = model.stream([HumanMessage(content=prompt)])  # type: ignore[attr-defined]
    except Exception as error:
        message = str(error).lower()
        if any(
            marker in message
            for marker in (
                "stream",
                "streaming",
                "not supported",
                "unsupported",
                "does not support",
            )
        ):
            return StreamingObservation(
                explicitly_unsupported=True,
                unsupported_reason="provider_streaming_unsupported",
            )
        raise

    metas: list[StreamChunkMeta] = []
    for arrival_index, chunk in enumerate(stream):
        text = _assistant_text_from_content(getattr(chunk, "content", None))
        sequence_index: int | None = None
        metadata = getattr(chunk, "response_metadata", None) or {}
        raw_index = metadata.get("chunk_index", metadata.get("index"))
        if isinstance(raw_index, int):
            sequence_index = raw_index
        elif isinstance(raw_index, str) and raw_index.isdigit():
            sequence_index = int(raw_index)
        metas.append(
            StreamChunkMeta(
                arrival_index=arrival_index,
                text_length=len(text),
                sequence_index=sequence_index,
            )
        )
    return StreamingObservation(chunks=tuple(metas))


def check_streaming(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
    *,
    stream: StreamingFn = _default_streaming,
    prompt: str = STREAMING_PROMPT,
) -> DiagnosticResult:
    """Classify streaming as supported, unsupported, or failed/unknown.

    Streaming is knowledge-only: UNSUPPORTED is a valid known outcome and is
    not a required-pass capability. Evidence is chunk metadata only (counts,
    lengths, ordering flags); raw text deltas are never recorded.
    """
    try:
        observation = stream(config, prompt)
    except Exception:
        return harness.record(
            Capability.STREAMING,
            ResultStatus.FAIL,
            evidence={
                "match_status": "unknown_failure",
                "summary": "streaming_unknown_failure",
                "live_streaming_claimed": False,
            },
            failure_code="unknown_failure",
        )

    if observation.explicitly_unsupported:
        reason = observation.unsupported_reason or "provider_streaming_unsupported"
        return harness.record(
            Capability.STREAMING,
            ResultStatus.UNSUPPORTED,
            evidence={
                "chunk_count": 0,
                "non_empty_chunk_count": 0,
                "sequence_ordered": None,
                "total_text_length": 0,
                "explicitly_unsupported": True,
                "unsupported_reason": reason,
                "match_status": "explicitly_unsupported",
                "summary": "streaming_documented_unsupported",
                "live_streaming_claimed": False,
            },
            failure_code=None,
            selected_mode="unsupported",
        )

    chunks = observation.chunks
    chunk_count = len(chunks)
    non_empty = sum(1 for chunk in chunks if chunk.text_length > 0)
    total_text_length = sum(chunk.text_length for chunk in chunks)
    ordered = _stream_chunks_sequence_ordered(chunks)

    base_evidence: dict[str, object] = {
        "chunk_count": chunk_count,
        "non_empty_chunk_count": non_empty,
        "sequence_ordered": ordered,
        "total_text_length": total_text_length,
        "explicitly_unsupported": False,
        "live_streaming_claimed": False,
    }

    if chunk_count == 0 or non_empty == 0 or total_text_length == 0:
        return harness.record(
            Capability.STREAMING,
            ResultStatus.FAIL,
            evidence={
                **base_evidence,
                "match_status": "empty_chunks",
                "summary": "streaming_empty_chunks",
            },
            failure_code="empty_chunks",
        )

    if not ordered:
        return harness.record(
            Capability.STREAMING,
            ResultStatus.FAIL,
            evidence={
                **base_evidence,
                "match_status": "out_of_order_chunks",
                "summary": "streaming_out_of_order_chunks",
            },
            failure_code="out_of_order_chunks",
        )

    return harness.record(
        Capability.STREAMING,
        ResultStatus.PASS,
        evidence={
            **base_evidence,
            "match_status": "ordered_text_chunks",
            "summary": "streaming_supported_ordered_chunks",
        },
        selected_mode="streaming_text",
    )


def compute_diagnostic_exit_code(results: Sequence[DiagnosticResult]) -> int:
    """Central exit contract for the diagnostic process.

    Non-zero when any required-pass capability is missing, fails, is pending,
    or is otherwise not PASS. Streaming is knowledge-only: explicit UNSUPPORTED
    (or any non-required streaming outcome) alone does not force non-zero exit.
    """
    by_capability = {result.capability: result for result in results}
    for capability in REQUIRED_PASS_CAPABILITIES:
        result = by_capability.get(capability)
        if result is None or result.status is not ResultStatus.PASS:
            return DIAGNOSTIC_EXIT_REQUIRED_FAILURE
    return DIAGNOSTIC_EXIT_SUCCESS


def format_sanitized_summary(
    results: Sequence[DiagnosticResult],
    *,
    exit_code: int | None = None,
) -> str:
    """One compact sanitized summary line set for the single-purpose command.

    Emits only capability, status, optional failure_code, and exit code.
    Relies on DiagnosticResult already being harness-sanitized.
    """
    resolved_exit = (
        exit_code if exit_code is not None else compute_diagnostic_exit_code(results)
    )
    lines = [f"shopaikey_diagnostic exit={resolved_exit}"]
    for result in results:
        failure = result.failure_code or "-"
        mode = result.selected_mode or "-"
        lines.append(
            f"{result.capability.value} status={result.status.value} "
            f"failure_code={failure} mode={mode}"
        )
    return "\n".join(lines)


def _normalize_secret_material(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


class DiagnosticHarness:
    required_pass_capabilities = REQUIRED_PASS_CAPABILITIES

    def __init__(self, secrets: Iterable[str]) -> None:
        self._secrets = tuple(secret for secret in secrets if secret)
        self._normalized_secrets = tuple(
            normalized
            for secret in self._secrets
            if (normalized := _normalize_secret_material(secret))
        )

    def _sanitize_text(self, value: str) -> str:
        normalized = _normalize_secret_material(value)
        if any(marker in normalized for marker in _SENSITIVE_MARKERS):
            return REDACTED
        for secret in self._secrets:
            if secret in value:
                return REDACTED
        if any(
            normalized_secret in normalized
            for normalized_secret in self._normalized_secrets
        ):
            return REDACTED
        return value

    def _sanitize(self, value: object) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            redacted = False
            for key, item in value.items():
                if self._sanitize_text(str(key)) == REDACTED:
                    redacted = True
                    continue
                sanitized[str(key)] = self._sanitize(item)
            if redacted:
                sanitized["redacted"] = REDACTED
            return dict(sorted(sanitized.items()))
        if isinstance(value, (list, tuple)):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            return self._sanitize_text(value)
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        return self._sanitize_text(type(value).__name__)

    def record(
        self,
        capability: Capability,
        status: ResultStatus,
        *,
        evidence: Mapping[str, object],
        selected_mode: str | None = None,
        failure_code: str | None = None,
    ) -> DiagnosticResult:
        return DiagnosticResult(
            capability=capability,
            evidence=self._sanitize(evidence),
            failure_code=(
                self._sanitize_text(failure_code) if failure_code is not None else None
            ),
            selected_mode=(
                self._sanitize_text(selected_mode) if selected_mode is not None else None
            ),
            status=status,
        )

    def render(self, results: Sequence[DiagnosticResult]) -> str:
        payload = [result.model_dump(mode="json") for result in results]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def safe_exception(self, _failure_code: str) -> RuntimeError:
        return SanitizedDiagnosticError("diagnostic_failed")


def run_live_compatibility_checks(
    config: ShopAIKeyConfig,
    harness: DiagnosticHarness,
) -> list[DiagnosticResult]:
    """Execute all six capabilities once against the configured live provider.

    Normal automated tests must inject fakes and must not call this path.
    Authorized 03F smoke uses this single-purpose orchestration only.
    """
    results: list[DiagnosticResult] = []
    results.append(check_model_discovery(config, harness))
    results.append(check_basic_completion(config, harness))

    tools = (synthetic_echo_label_tool(),)
    captured_calls: list[ObservedToolCall] = []

    def capture_function_call(
        live_config: ShopAIKeyConfig,
        prompt: str,
        bound_tools: Sequence[object],
    ) -> FunctionCallObservation:
        observation = _default_function_call(live_config, prompt, bound_tools)
        captured_calls.extend(observation.tool_calls)
        return observation

    results.append(
        check_function_call(
            config,
            harness,
            invoke_function_call=capture_function_call,
            tools=tools,
        )
    )
    prior_call = captured_calls[0] if captured_calls else None
    results.append(
        check_tool_round_trip(
            config,
            harness,
            tools=tools,
            prior_call=prior_call,
        )
    )
    results.append(check_structured_schema(config, harness))
    results.append(check_streaming(config, harness))
    return results


def main() -> int:
    """Single-purpose live ShopAIKey compatibility diagnostic (authorized smoke).

    Loads root `.env`, runs all six capability checks once, prints a sanitized
    summary plus JSON evidence, and exits non-zero when any required-pass
    capability is not PASS. Does not print secrets or raw provider headers.
    """
    try:
        config = load_root_config()
    except ConfigurationError:
        print("shopaikey_diagnostic exit=1")
        print("configuration_error summary=invalid_or_missing_root_env")
        return DIAGNOSTIC_EXIT_REQUIRED_FAILURE

    harness = DiagnosticHarness(secrets=[config.api_key])
    results = run_live_compatibility_checks(config, harness)
    exit_code = compute_diagnostic_exit_code(results)
    print(format_sanitized_summary(results, exit_code=exit_code))
    print(harness.render(results))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

"""Fake/socket-blocked tests for the production ShopAIKey chat adapter.

Never opens a provider network connection. Never logs or asserts raw secrets
into durable surfaces beyond local variables used only for leak scanning.
"""

from __future__ import annotations

import io
import logging
import socket
import traceback
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from app.config import DEFAULT_LLM_MODEL, Settings, load_settings
from app.services.shopaikey_chat import (
    LOCKED_SCHEMA_MODE,
    LOCKED_STREAMING_MODE,
    LOCKED_TEMPERATURE,
    LOCKED_TOOL_MODE,
    MAX_SCHEMA_REPAIR_REQUESTS,
    MAX_TRANSIENT_RETRIES,
    DecisionResult,
    ShopAIKeyChatAdapter,
    ShopAIKeyChatError,
    ShopAIKeyErrorCode,
    StreamChunk,
    classify_provider_failure,
    is_transient_failure,
    validate_structured_payload,
)
from pydantic import BaseModel, ConfigDict, Field

SENTINEL_API_KEY = "sentinel-shopaikey-chat-never-emit"
SENTINEL_NEO4J_PASSWORD = "sentinel-neo4j-chat-never-emit"
SENTINEL_BASE_URL = "https://provider.example/v1"
CREDENTIAL_URL = f"https://user:{SENTINEL_API_KEY}@provider.example/v1"
AUTH_HEADER = f"Bearer {SENTINEL_API_KEY}"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeMessage:
    content: object = ""
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    response_metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class FakeChunk:
    content: object = ""
    response_metadata: dict[str, object] = field(default_factory=dict)


class FakeStructuredRunnable:
    def __init__(self, parent: FakeChatModel) -> None:
        self._parent = parent

    def invoke(self, messages: object, **kwargs: Any) -> object:
        del kwargs
        return self._parent.structured_invoke(messages)


class FakeBoundModel:
    def __init__(self, parent: FakeChatModel, tools: Sequence[object]) -> None:
        self.parent = parent
        self.tools = list(tools)

    def invoke(self, messages: object, **kwargs: Any) -> FakeMessage:
        del kwargs
        self.parent.bound_invoke_calls.append({"tools": self.tools, "messages": messages})
        return self.parent.decision_invoke(messages, tools=self.tools)


class FakeChatModel:
    """Injectable ChatOpenAI stand-in; never uses the network."""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = dict(kwargs)
        self.bound_tools: list[object] | None = None
        self.decision_invoke_calls: list[object] = []
        self.bound_invoke_calls: list[dict[str, object]] = []
        self.stream_calls: list[object] = []
        self.structured_calls: list[dict[str, object]] = []
        self.structured_kwargs: list[dict[str, object]] = []
        # Controllable behaviors (set by tests on the factory-held template).
        self.decision_handler: Any = None
        self.stream_handler: Any = None
        self.structured_handler: Any = None
        self.decision_side_effects: list[BaseException | FakeMessage] = []
        self.stream_side_effects: list[BaseException | list[FakeChunk]] = []
        self.structured_side_effects: list[BaseException | object] = []

    def bind_tools(self, tools: Sequence[object], **kwargs: Any) -> FakeBoundModel:
        del kwargs
        self.bound_tools = list(tools)
        return FakeBoundModel(self, tools)

    def invoke(self, messages: object, **kwargs: Any) -> FakeMessage:
        del kwargs
        return self.decision_invoke(messages, tools=None)

    def stream(self, messages: object, **kwargs: Any) -> Iterator[FakeChunk]:
        del kwargs
        self.stream_calls.append(messages)
        if self.stream_side_effects:
            effect = self.stream_side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return iter(effect)
        if self.stream_handler is not None:
            return iter(self.stream_handler(messages))
        return iter([FakeChunk(content="ok")])

    def with_structured_output(self, schema: object, **kwargs: Any) -> FakeStructuredRunnable:
        self.structured_kwargs.append(dict(kwargs))
        self._last_schema = schema
        return FakeStructuredRunnable(self)

    def decision_invoke(
        self, messages: object, *, tools: Sequence[object] | None
    ) -> FakeMessage:
        self.decision_invoke_calls.append({"messages": messages, "tools": tools})
        if self.decision_side_effects:
            effect = self.decision_side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        if self.decision_handler is not None:
            return self.decision_handler(messages, tools)
        return FakeMessage(
            content="decide",
            tool_calls=[],
            response_metadata={"model_name": self.kwargs.get("model")},
        )

    def structured_invoke(self, messages: object) -> object:
        self.structured_calls.append({"messages": messages, "schema": self._last_schema})
        if self.structured_side_effects:
            effect = self.structured_side_effects.pop(0)
            if isinstance(effect, BaseException):
                raise effect
            return effect
        if self.structured_handler is not None:
            return self.structured_handler(messages)
        return {"item_id": "probe-1", "count": 1, "active": True}


class RecordingFactory:
    """Factory that records construction kwargs and returns a shared FakeChatModel."""

    def __init__(self, template: FakeChatModel | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.template = template or FakeChatModel()

    def __call__(self, **kwargs: object) -> FakeChatModel:
        self.calls.append(dict(kwargs))
        # Share one template so side-effect queues are visible across builds,
        # but refresh construction kwargs to the latest call.
        model = self.template
        model.kwargs = dict(kwargs)
        return model


class ProbeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    count: int
    active: bool = Field(...)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _settings(**overrides: str) -> Settings:
    environ = {
        "NEO4J_PASSWORD": SENTINEL_NEO4J_PASSWORD,
        "SHOPAIKEY_API_KEY": SENTINEL_API_KEY,
        "SHOPAIKEY_BASE_URL": SENTINEL_BASE_URL,
        "LLM_MODEL": DEFAULT_LLM_MODEL,
        **overrides,
    }
    return load_settings(environ=environ)


@pytest.fixture
def block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed if any code path tries to open a real socket."""

    def _blocked(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("network socket construction is forbidden in adapter tests")

    monkeypatch.setattr(socket, "socket", _blocked)


@pytest.fixture
def factory() -> RecordingFactory:
    return RecordingFactory()


@pytest.fixture
def adapter(factory: RecordingFactory) -> ShopAIKeyChatAdapter:
    return ShopAIKeyChatAdapter.from_settings(_settings(), model_factory=factory)


def _assert_no_secrets(*surfaces: str) -> None:
    combined = "\n".join(surfaces)
    for prohibited in (
        SENTINEL_API_KEY,
        SENTINEL_NEO4J_PASSWORD,
        AUTH_HEADER,
        "Authorization",
        CREDENTIAL_URL,
        f"user:{SENTINEL_API_KEY}",
    ):
        assert prohibited not in combined


# ---------------------------------------------------------------------------
# Construction / configuration / binding
# ---------------------------------------------------------------------------


def test_from_settings_uses_typed_backend_fields_only(
    block_sockets: None, factory: RecordingFactory
) -> None:
    settings = _settings()
    adapter = ShopAIKeyChatAdapter.from_settings(settings, model_factory=factory)

    assert adapter.base_url == SENTINEL_BASE_URL
    assert adapter.model_id == DEFAULT_LLM_MODEL
    assert adapter.schema_mode == LOCKED_SCHEMA_MODE == "strict_schema"
    assert adapter.streaming_mode == LOCKED_STREAMING_MODE == "streaming_text"
    assert adapter.tool_mode == LOCKED_TOOL_MODE == "bind_tools"
    assert SENTINEL_API_KEY not in repr(adapter)
    assert SENTINEL_API_KEY not in str(adapter)


def test_build_model_uses_locked_temperature_zero_and_settings_endpoint(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    model = adapter.build_model()

    assert isinstance(model, FakeChatModel)
    assert factory.calls == [
        {
            "api_key": SENTINEL_API_KEY,
            "base_url": SENTINEL_BASE_URL,
            "model": DEFAULT_LLM_MODEL,
            "temperature": LOCKED_TEMPERATURE,
        }
    ]
    assert LOCKED_TEMPERATURE == 0.0
    assert model.kwargs["temperature"] == 0


def test_bind_tools_uses_public_bind_tools_api(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    tools = [{"name": "echo_label"}]
    bound = adapter.bind_tools(tools)

    assert isinstance(bound, FakeBoundModel)
    assert bound.tools == tools
    assert factory.template.bound_tools == tools


def test_non_zero_temperature_rejected_at_construction(block_sockets: None) -> None:
    with pytest.raises(ShopAIKeyChatError) as raised:
        ShopAIKeyChatAdapter(
            base_url=SENTINEL_BASE_URL,
            api_key=SENTINEL_API_KEY,
            model=DEFAULT_LLM_MODEL,
            temperature=0.7,
            model_factory=RecordingFactory(),
        )
    assert raised.value.code is ShopAIKeyErrorCode.CONFIG
    _assert_no_secrets(str(raised.value), repr(raised.value))


def test_empty_config_fields_rejected_without_echoing_secrets(
    block_sockets: None,
) -> None:
    with pytest.raises(ShopAIKeyChatError) as raised:
        ShopAIKeyChatAdapter(
            base_url="",
            api_key=SENTINEL_API_KEY,
            model=DEFAULT_LLM_MODEL,
            model_factory=RecordingFactory(),
        )
    assert raised.value.code is ShopAIKeyErrorCode.CONFIG
    _assert_no_secrets(str(raised.value), repr(raised.value))


# ---------------------------------------------------------------------------
# Decision calls
# ---------------------------------------------------------------------------


def test_invoke_decision_binds_tools_and_returns_result(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    tools = [{"name": "echo_label"}]
    factory.template.decision_side_effects = [
        FakeMessage(
            content="",
            tool_calls=[
                {
                    "name": "echo_label",
                    "args": {"label": "ping"},
                    "id": "call-1",
                }
            ],
            response_metadata={"model_name": DEFAULT_LLM_MODEL},
        )
    ]

    result = adapter.invoke_decision([{"role": "user", "content": "hi"}], tools=tools)

    assert isinstance(result, DecisionResult)
    assert result.tool_mode == "bind_tools"
    assert result.schema_mode == "strict_schema"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "echo_label"
    assert result.tool_calls[0].arguments == {"label": "ping"}
    assert result.response_model == DEFAULT_LLM_MODEL


def test_invoke_decision_rejects_silent_model_switch(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.decision_side_effects = [
        FakeMessage(
            content="x",
            response_metadata={"model_name": "gpt-other-model"},
        )
    ]

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_decision([{"role": "user", "content": "hi"}])

    assert raised.value.code is ShopAIKeyErrorCode.MODEL_MISMATCH
    # No second attempt for non-transient failures.
    assert len(factory.template.decision_invoke_calls) == 1


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_stream_final_text_yields_ordered_non_empty_chunks(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.stream_side_effects = [
        [
            FakeChunk(content="Hel"),
            FakeChunk(content=""),
            FakeChunk(content="lo"),
            FakeChunk(content={"text": "!"}),
        ]
    ]

    chunks = list(adapter.stream_final_text([{"role": "user", "content": "say hi"}]))

    assert chunks == [
        StreamChunk(index=0, text="Hel"),
        StreamChunk(index=1, text="lo"),
        StreamChunk(index=2, text="!"),
    ]
    assert factory.calls[-1].get("streaming") is True
    assert factory.calls[-1]["temperature"] == 0
    assert factory.calls[-1]["model"] == DEFAULT_LLM_MODEL


def test_stream_empty_response_fails_closed(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.stream_side_effects = [[FakeChunk(content=""), FakeChunk(content="")]]

    with pytest.raises(ShopAIKeyChatError) as raised:
        list(adapter.stream_final_text([{"role": "user", "content": "x"}]))

    assert raised.value.code is ShopAIKeyErrorCode.EMPTY_RESPONSE


# ---------------------------------------------------------------------------
# Retry ceilings
# ---------------------------------------------------------------------------


def test_timeout_retries_once_then_succeeds(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.decision_side_effects = [
        TimeoutError("simulated timeout"),
        FakeMessage(
            content="ok",
            response_metadata={"model_name": DEFAULT_LLM_MODEL},
        ),
    ]

    result = adapter.invoke_decision([{"role": "user", "content": "hi"}])

    assert result.content == "ok"
    assert len(factory.template.decision_invoke_calls) == 2


def test_rate_limit_retries_once_then_fails(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.decision_side_effects = [
        RuntimeError("Rate limit exceeded 429"),
        RuntimeError("Rate limit exceeded 429 again"),
    ]

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_decision([{"role": "user", "content": "hi"}])

    assert raised.value.code is ShopAIKeyErrorCode.RATE_LIMIT
    assert len(factory.template.decision_invoke_calls) == 2
    _assert_no_secrets(str(raised.value), repr(raised.value))


def test_non_transient_provider_error_is_not_retried(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.decision_side_effects = [
        RuntimeError(f"Authorization: {AUTH_HEADER} body={SENTINEL_API_KEY}"),
    ]

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_decision([{"role": "user", "content": "hi"}])

    assert raised.value.code is ShopAIKeyErrorCode.PROVIDER_ERROR
    assert len(factory.template.decision_invoke_calls) == 1
    _assert_no_secrets(
        str(raised.value),
        repr(raised.value),
        "".join(traceback.format_exception(raised.value)),
    )


def test_stream_timeout_retries_once_before_first_chunk(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.stream_side_effects = [
        TimeoutError("stream timeout"),
        [FakeChunk(content="chunk-a"), FakeChunk(content="chunk-b")],
    ]

    chunks = list(adapter.stream_final_text([{"role": "user", "content": "x"}]))

    assert [c.text for c in chunks] == ["chunk-a", "chunk-b"]
    assert len(factory.template.stream_calls) == 2


def test_stream_does_not_retry_after_first_chunk(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    def _mid_fail(_messages: object) -> Iterator[FakeChunk]:
        yield FakeChunk(content="partial")
        raise TimeoutError("late timeout")

    factory.template.stream_handler = _mid_fail

    gen = adapter.stream_final_text([{"role": "user", "content": "x"}])
    first = next(gen)
    assert first.text == "partial"
    with pytest.raises(ShopAIKeyChatError) as raised:
        next(gen)
    assert raised.value.code is ShopAIKeyErrorCode.TIMEOUT
    # Only one stream attempt (no retry after yield).
    assert len(factory.template.stream_calls) == 1


# ---------------------------------------------------------------------------
# Schema repair ceiling / strict_schema
# ---------------------------------------------------------------------------


def test_structured_uses_strict_schema_and_validates(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.structured_side_effects = [
        {"item_id": "probe-1", "count": 1, "active": True}
    ]

    result = adapter.invoke_structured(
        ProbeSchema,
        [{"role": "user", "content": "extract"}],
    )

    assert result == ProbeSchema(item_id="probe-1", count=1, active=True)
    assert factory.template.structured_kwargs[0] == {
        "method": "function_calling",
        "strict": True,
    }
    assert len(factory.template.structured_calls) == 1


def test_structured_repairs_once_then_succeeds(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.structured_side_effects = [
        {"item_id": "bad", "count": "nope", "active": True},
        {"item_id": "probe-1", "count": 1, "active": True},
    ]

    result = adapter.invoke_structured(
        ProbeSchema,
        [{"role": "user", "content": "extract"}],
    )

    assert result.item_id == "probe-1"
    assert len(factory.template.structured_calls) == 2
    assert MAX_SCHEMA_REPAIR_REQUESTS == 1


def test_structured_repair_ceiling_then_fails(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.structured_side_effects = [
        {"item_id": "bad", "count": "x", "active": True},
        {"item_id": "still-bad", "count": "y", "active": False},
        {"item_id": "would-be-third", "count": 1, "active": True},
    ]

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_structured(
            ProbeSchema,
            [{"role": "user", "content": "extract"}],
        )

    assert raised.value.code is ShopAIKeyErrorCode.SCHEMA_INVALID
    # Initial + one repair only; third effect unused.
    assert len(factory.template.structured_calls) == 2


def test_structured_does_not_convert_provider_error_to_success(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.structured_side_effects = [
        RuntimeError(f"raw body Authorization: {AUTH_HEADER}"),
    ]

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_structured(
            ProbeSchema,
            [{"role": "user", "content": "extract"}],
        )

    assert raised.value.code is ShopAIKeyErrorCode.PROVIDER_ERROR
    assert len(factory.template.structured_calls) == 1
    _assert_no_secrets(str(raised.value), repr(raised.value))


def test_structured_shares_single_transient_retry_budget(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    factory.template.structured_side_effects = [
        TimeoutError("first timeout"),
        {"item_id": "bad", "count": "x", "active": True},
        TimeoutError("repair timeout"),
        {"item_id": "probe-1", "count": 1, "active": True},
    ]

    # Budget is one transient retry total: first timeout consumes it; repair
    # timeout must fail closed rather than succeed via a second retry.
    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_structured(
            ProbeSchema,
            [{"role": "user", "content": "extract"}],
        )

    assert raised.value.code is ShopAIKeyErrorCode.TIMEOUT
    assert len(factory.template.structured_calls) == 3
    assert MAX_TRANSIENT_RETRIES == 1


def test_validate_structured_payload_rejects_invalid_types() -> None:
    model, failure = validate_structured_payload(
        ProbeSchema, {"item_id": "x", "count": "no", "active": True}
    )
    assert model is None
    assert failure is ShopAIKeyErrorCode.SCHEMA_INVALID


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancellation_before_decision_raises_sanitized_code(
    block_sockets: None, factory: RecordingFactory
) -> None:
    cancelled = True
    adapter = ShopAIKeyChatAdapter.from_settings(
        _settings(),
        model_factory=factory,
        is_cancelled=lambda: cancelled,
    )

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_decision([{"role": "user", "content": "hi"}])

    assert raised.value.code is ShopAIKeyErrorCode.CANCELLED
    assert factory.calls == []


def test_cancellation_mid_stream_raises_sanitized_code(
    block_sockets: None, factory: RecordingFactory
) -> None:
    state = {"cancel": False}

    def _chunks(_messages: object) -> Iterator[FakeChunk]:
        yield FakeChunk(content="a")
        state["cancel"] = True
        yield FakeChunk(content="b")

    factory.template.stream_handler = _chunks
    adapter = ShopAIKeyChatAdapter.from_settings(
        _settings(),
        model_factory=factory,
        is_cancelled=lambda: state["cancel"],
    )

    gen = adapter.stream_final_text([{"role": "user", "content": "x"}])
    assert next(gen).text == "a"
    with pytest.raises(ShopAIKeyChatError) as raised:
        next(gen)
    assert raised.value.code is ShopAIKeyErrorCode.CANCELLED


# ---------------------------------------------------------------------------
# Failure classification / secret safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "code", "transient"),
    [
        (TimeoutError("t"), ShopAIKeyErrorCode.TIMEOUT, True),
        (RuntimeError("rate limit exceeded"), ShopAIKeyErrorCode.RATE_LIMIT, True),
        (RuntimeError("boom"), ShopAIKeyErrorCode.PROVIDER_ERROR, False),
        (
            ShopAIKeyChatError(ShopAIKeyErrorCode.CANCELLED),
            ShopAIKeyErrorCode.CANCELLED,
            False,
        ),
    ],
)
def test_classify_provider_failure_is_deterministic(
    exc: BaseException, code: ShopAIKeyErrorCode, transient: bool
) -> None:
    assert classify_provider_failure(exc) is code
    assert is_transient_failure(code) is transient


def test_secret_safe_failures_across_output_surfaces(
    block_sockets: None,
    factory: RecordingFactory,
    adapter: ShopAIKeyChatAdapter,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    factory.template.decision_side_effects = [
        RuntimeError(
            f"Authorization: {AUTH_HEADER}; url={CREDENTIAL_URL}; key={SENTINEL_API_KEY}"
        )
    ]
    logger = logging.getLogger("shopaikey-chat-secret-test")

    with pytest.raises(ShopAIKeyChatError) as raised:
        adapter.invoke_decision([{"role": "user", "content": "hi"}])

    err = raised.value
    report = io.StringIO()
    print(str(err))
    print(repr(err), file=__import__("sys").stderr)
    logger.warning("%s %r", err, err)
    report.write(f"{err!s}\n{err!r}\n")
    rendered_tb = "".join(traceback.format_exception(err))

    captured = capsys.readouterr()
    combined = "\n".join(
        [captured.out, captured.err, caplog.text, report.getvalue(), rendered_tb]
    )
    _assert_no_secrets(combined)
    assert err.code is ShopAIKeyErrorCode.PROVIDER_ERROR
    assert err.__cause__ is None
    assert err.__context__ is None
    assert str(err) == "shopaikey_provider_error"


def test_default_factory_is_not_used_when_injectable_factory_provided(
    block_sockets: None, factory: RecordingFactory, adapter: ShopAIKeyChatAdapter
) -> None:
    # Building must not import/construct a live client when factory is injected.
    model = adapter.build_model(streaming=True)
    assert isinstance(model, FakeChatModel)
    assert factory.calls[-1]["streaming"] is True

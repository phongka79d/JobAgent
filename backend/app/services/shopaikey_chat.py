"""Production ShopAIKey ChatOpenAI adapter with bounded failure policy.

Constructs ``ChatOpenAI`` from typed root settings (base URL, key, model) at
temperature zero, binds tools via ``bind_tools()``, and reuses the Phase 0
locked decisions:

- structured schema mode: ``strict_schema`` (function_calling + strict=True)
- streaming mode: ``streaming_text``
- tool mode: ``bind_tools``

Failure ceilings (application-owned, never LLM-controlled):

- at most one structured-output repair after invalid schema validation
- at most one timeout / rate-limit retry per adapter operation
- all other failures fail closed as sanitized codes

Normal tests inject fakes and must never open a provider network connection.
Secrets, Authorization headers, raw provider bodies, and credential-bearing
URLs never appear in exception strings or public failure surfaces.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol, TypeVar, cast, runtime_checkable

from pydantic import BaseModel, ValidationError

from app.config import DEFAULT_LLM_MODEL, REDACTED, Settings

# Locked Phase 0 decisions — do not re-benchmark or silently switch.
LOCKED_CHAT_MODEL: Final[str] = DEFAULT_LLM_MODEL
LOCKED_SCHEMA_MODE: Final[str] = "strict_schema"
LOCKED_STREAMING_MODE: Final[str] = "streaming_text"
LOCKED_TOOL_MODE: Final[str] = "bind_tools"
LOCKED_TEMPERATURE: Final[float] = 0.0
MAX_SCHEMA_REPAIR_REQUESTS: Final[int] = 1
MAX_TRANSIENT_RETRIES: Final[int] = 1

_DEFAULT_REPAIR_INSTRUCTION: Final[str] = (
    "Previous output failed schema validation. Return only one JSON object "
    "that satisfies the required schema fields and types."
)

_TResult = TypeVar("_TResult")
IsCancelledFn = Callable[[], bool]
ModelFactory = Callable[..., "ChatModelLike"]


class ShopAIKeyErrorCode(StrEnum):
    """Stable, non-sensitive provider failure codes."""

    TIMEOUT = "shopaikey_timeout"
    RATE_LIMIT = "shopaikey_rate_limit"
    SCHEMA_INVALID = "shopaikey_schema_invalid"
    PROVIDER_ERROR = "shopaikey_provider_error"
    CANCELLED = "shopaikey_cancelled"
    EMPTY_RESPONSE = "shopaikey_empty_response"
    MODEL_MISMATCH = "shopaikey_model_mismatch"
    CONFIG = "shopaikey_config_error"


class ShopAIKeyChatError(Exception):
    """Sanitized ShopAIKey failure (code-only str/repr; no chained secrets)."""

    def __init__(self, code: ShopAIKeyErrorCode) -> None:
        self.code = code
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"ShopAIKeyChatError(code={self.code.value!r})"

    def __getattribute__(self, name: str) -> object:
        # Drop chained cause/context so raw provider text cannot leak.
        if name in {"__cause__", "__context__"}:
            return None
        return super().__getattribute__(name)


@runtime_checkable
class ChatModelLike(Protocol):
    """Minimal ChatOpenAI surface used by the production adapter."""

    def bind_tools(self, tools: Sequence[object], **kwargs: Any) -> object: ...

    def invoke(self, input: object, **kwargs: Any) -> object: ...

    def stream(self, input: object, **kwargs: Any) -> Iterator[object]: ...

    def with_structured_output(
        self,
        schema: object,
        **kwargs: Any,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ObservedToolCall:
    """Bounded tool-call view for decision results (no raw document bodies)."""

    name: str
    arguments: object
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Outcome of one tool-bound decision invoke."""

    content: str
    tool_calls: tuple[ObservedToolCall, ...]
    response_model: str | None
    schema_mode: str = LOCKED_SCHEMA_MODE
    tool_mode: str = LOCKED_TOOL_MODE


@dataclass(frozen=True, slots=True)
class StreamChunk:
    """One ordered final-text stream chunk."""

    index: int
    text: str


def _default_model_factory(**kwargs: Any) -> ChatModelLike:
    """Construct live ChatOpenAI. Tests inject fakes instead of this factory."""
    from langchain_openai import ChatOpenAI

    # ChatOpenAI accepts a wide keyword surface; kwargs are built only by
    # model_construction_kwargs (api_key/base_url/model/temperature[/streaming]).
    return cast(ChatModelLike, ChatOpenAI(**kwargs))


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


def _response_model_from_message(message: object) -> str | None:
    metadata = getattr(message, "response_metadata", None) or {}
    if not isinstance(metadata, Mapping):
        return None
    response_model = metadata.get("model_name") or metadata.get("model")
    if response_model is None:
        return None
    return str(response_model)


def classify_provider_failure(exc: BaseException) -> ShopAIKeyErrorCode:
    """Map a provider/runtime exception to a stable sanitized code.

    Classification is deterministic and never embeds exception text in the code.
    """
    if isinstance(exc, ShopAIKeyChatError):
        return exc.code
    if isinstance(exc, TimeoutError):
        return ShopAIKeyErrorCode.TIMEOUT

    # Prefer type-name markers over full message bodies (messages may hold secrets).
    type_name = type(exc).__name__.lower()
    module_name = type(exc).__module__.lower()
    combined_names = f"{module_name}.{type_name}"

    if "cancel" in type_name or "cancelled" in type_name or "canceled" in type_name:
        return ShopAIKeyErrorCode.CANCELLED
    if "timeout" in type_name or "timeout" in combined_names:
        return ShopAIKeyErrorCode.TIMEOUT
    if "ratelimit" in type_name.replace("_", "") or "rate_limit" in type_name:
        return ShopAIKeyErrorCode.RATE_LIMIT

    # Bounded message scan for common provider markers only.
    try:
        message = str(exc).lower()
    except Exception:
        message = ""
    if "cancelled" in message or "canceled" in message or "operation cancelled" in message:
        return ShopAIKeyErrorCode.CANCELLED
    if "timeout" in message or "timed out" in message or "deadline exceeded" in message:
        return ShopAIKeyErrorCode.TIMEOUT
    if (
        "rate limit" in message
        or "rate_limit" in message
        or "too many requests" in message
        or "429" in message
    ):
        return ShopAIKeyErrorCode.RATE_LIMIT
    return ShopAIKeyErrorCode.PROVIDER_ERROR


def is_transient_failure(code: ShopAIKeyErrorCode) -> bool:
    """True only for the single allowed retry class (timeout / rate limit)."""
    return code in {
        ShopAIKeyErrorCode.TIMEOUT,
        ShopAIKeyErrorCode.RATE_LIMIT,
    }


def validate_structured_payload[TModel: BaseModel](
    schema: type[TModel],
    payload: object,
) -> tuple[TModel | None, ShopAIKeyErrorCode | None]:
    """Validate structured output against a Pydantic model without echoing raw data."""
    if payload is None:
        return None, ShopAIKeyErrorCode.SCHEMA_INVALID
    if isinstance(payload, schema):
        try:
            return schema.model_validate(payload.model_dump()), None
        except ValidationError:
            return None, ShopAIKeyErrorCode.SCHEMA_INVALID
    if isinstance(payload, str):
        try:
            data: object = json.loads(payload)
        except json.JSONDecodeError:
            return None, ShopAIKeyErrorCode.SCHEMA_INVALID
    elif isinstance(payload, Mapping):
        data = dict(payload)
    elif isinstance(payload, BaseModel):
        data = payload.model_dump()
    else:
        return None, ShopAIKeyErrorCode.SCHEMA_INVALID

    if not isinstance(data, Mapping):
        return None, ShopAIKeyErrorCode.SCHEMA_INVALID
    try:
        return schema.model_validate(data), None
    except ValidationError:
        return None, ShopAIKeyErrorCode.SCHEMA_INVALID


class ShopAIKeyChatAdapter:
    """Injectable production adapter for decision, tools, stream, and schema.

    Construction uses only typed settings fields. The model factory is injectable
    so normal tests never construct a live network client.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = LOCKED_TEMPERATURE,
        model_factory: ModelFactory | None = None,
        is_cancelled: IsCancelledFn | None = None,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.CONFIG)
        if temperature != LOCKED_TEMPERATURE:
            # Production chat path is locked at temperature zero.
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.CONFIG)
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._temperature = LOCKED_TEMPERATURE
        self._model_factory: ModelFactory = model_factory or _default_model_factory
        self._is_cancelled = is_cancelled
        self._secrets: tuple[str, ...] = (api_key,) if api_key else ()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        model_factory: ModelFactory | None = None,
        is_cancelled: IsCancelledFn | None = None,
    ) -> ShopAIKeyChatAdapter:
        """Build from typed backend settings without reading root ``.env``."""
        return cls(
            base_url=settings.shopaikey_base_url,
            api_key=settings.shopaikey_api_key.get_secret_value(),
            model=settings.llm_model,
            temperature=LOCKED_TEMPERATURE,
            model_factory=model_factory,
            is_cancelled=is_cancelled,
        )

    def __repr__(self) -> str:
        return (
            "ShopAIKeyChatAdapter("
            f"base_url={self._base_url!r}, "
            f"api_key={REDACTED!r}, "
            f"model={self._model!r}, "
            f"temperature={self._temperature!r}, "
            f"schema_mode={LOCKED_SCHEMA_MODE!r}, "
            f"streaming_mode={LOCKED_STREAMING_MODE!r}, "
            f"tool_mode={LOCKED_TOOL_MODE!r})"
        )

    __str__ = __repr__

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def schema_mode(self) -> str:
        return LOCKED_SCHEMA_MODE

    @property
    def streaming_mode(self) -> str:
        return LOCKED_STREAMING_MODE

    @property
    def tool_mode(self) -> str:
        return LOCKED_TOOL_MODE

    def model_construction_kwargs(self, *, streaming: bool = False) -> dict[str, object]:
        """Return the exact ChatOpenAI kwargs used for construction."""
        kwargs: dict[str, object] = {
            "api_key": self._api_key,
            "base_url": self._base_url,
            "model": self._model,
            "temperature": self._temperature,
        }
        if streaming:
            kwargs["streaming"] = True
        return kwargs

    def build_model(self, *, streaming: bool = False) -> ChatModelLike:
        """Construct the chat model via the injectable factory."""
        self._raise_if_cancelled()
        return self._model_factory(**self.model_construction_kwargs(streaming=streaming))

    def bind_tools(self, tools: Sequence[object], **kwargs: Any) -> object:
        """Bind tools through the public ``bind_tools()`` API (locked tool mode)."""
        model = self.build_model(streaming=False)
        return model.bind_tools(tools, **kwargs)

    def invoke_decision(
        self,
        messages: Sequence[object],
        *,
        tools: Sequence[object] | None = None,
    ) -> DecisionResult:
        """Run one tool-capable decision call with at most one transient retry."""

        def _once() -> DecisionResult:
            self._raise_if_cancelled()
            if tools is not None:
                runnable: object = self.bind_tools(tools)
            else:
                runnable = self.build_model(streaming=False)
            invoke = getattr(runnable, "invoke", None)
            if not callable(invoke):
                raise ShopAIKeyChatError(ShopAIKeyErrorCode.PROVIDER_ERROR)
            message = invoke(list(messages))
            response_model = _response_model_from_message(message)
            self._reject_model_switch(response_model)
            raw_calls = getattr(message, "tool_calls", None) or ()
            tool_calls = tuple(
                _tool_call_from_provider_item(item) for item in raw_calls
            )
            content = _assistant_text_from_content(getattr(message, "content", None))
            return DecisionResult(
                content=content,
                tool_calls=tool_calls,
                response_model=response_model,
            )

        return self._with_transient_retry(_once)

    def stream_final_text(
        self,
        messages: Sequence[object],
    ) -> Iterator[StreamChunk]:
        """Yield ordered final assistant text chunks (``streaming_text`` mode).

        Empty chunks are skipped. Cancellation mid-stream raises a sanitized
        cancelled failure. Transient failures before the first yielded chunk are
        retried at most once; after the first yield they fail closed.
        """
        self._raise_if_cancelled()
        transient_retries_used = 0
        while True:
            yielded_any = False
            try:
                for chunk in self._stream_once(messages):
                    yielded_any = True
                    yield chunk
                return
            except ShopAIKeyChatError as err:
                if (
                    not yielded_any
                    and is_transient_failure(err.code)
                    and transient_retries_used < MAX_TRANSIENT_RETRIES
                ):
                    transient_retries_used += 1
                    self._raise_if_cancelled()
                    continue
                raise
            except Exception as exc:
                code = classify_provider_failure(exc)
                if (
                    not yielded_any
                    and is_transient_failure(code)
                    and transient_retries_used < MAX_TRANSIENT_RETRIES
                ):
                    transient_retries_used += 1
                    self._raise_if_cancelled()
                    continue
                raise ShopAIKeyChatError(code) from None

    def invoke_structured[TModel: BaseModel](
        self,
        schema: type[TModel],
        messages: Sequence[object],
        *,
        repair_messages: Sequence[object] | None = None,
    ) -> TModel:
        """Invoke locked ``strict_schema`` structured output with one repair ceiling.

        Shared transient-retry budget: at most one timeout/rate-limit retry for
        the whole operation. Schema validation failures trigger at most one
        repair request, never converted to success without validation.
        """
        transient_retries_used = 0

        def _transport(call_messages: Sequence[object]) -> object:
            nonlocal transient_retries_used
            while True:
                self._raise_if_cancelled()
                try:
                    return self._structured_once(schema, call_messages)
                except ShopAIKeyChatError as err:
                    if (
                        is_transient_failure(err.code)
                        and transient_retries_used < MAX_TRANSIENT_RETRIES
                    ):
                        transient_retries_used += 1
                        continue
                    raise
                except Exception as exc:
                    code = classify_provider_failure(exc)
                    if (
                        is_transient_failure(code)
                        and transient_retries_used < MAX_TRANSIENT_RETRIES
                    ):
                        transient_retries_used += 1
                        continue
                    raise ShopAIKeyChatError(code) from None

        payload = _transport(messages)
        parsed, failure = validate_structured_payload(schema, payload)
        if parsed is not None and failure is None:
            return parsed

        # Exactly one repair request ceiling.
        if MAX_SCHEMA_REPAIR_REQUESTS < 1:
            raise ShopAIKeyChatError(
                failure or ShopAIKeyErrorCode.SCHEMA_INVALID
            ) from None

        repair_input = (
            list(repair_messages)
            if repair_messages is not None
            else list(messages) + [_text_message(_DEFAULT_REPAIR_INSTRUCTION)]
        )
        repair_payload = _transport(repair_input)
        repaired, repair_failure = validate_structured_payload(schema, repair_payload)
        if repaired is not None and repair_failure is None:
            return repaired
        raise ShopAIKeyChatError(
            repair_failure or failure or ShopAIKeyErrorCode.SCHEMA_INVALID
        ) from None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled is not None and self._is_cancelled():
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.CANCELLED) from None

    def _reject_model_switch(self, response_model: str | None) -> None:
        if response_model is not None and response_model != self._model:
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.MODEL_MISMATCH) from None

    def _with_transient_retry(self, fn: Callable[[], _TResult]) -> _TResult:
        try:
            return fn()
        except ShopAIKeyChatError as err:
            if not is_transient_failure(err.code):
                raise
            # Budget: one retry for transient classes only.
            try:
                return fn()
            except ShopAIKeyChatError:
                raise
            except Exception as exc:
                raise ShopAIKeyChatError(classify_provider_failure(exc)) from None
        except Exception as exc:
            code = classify_provider_failure(exc)
            if not is_transient_failure(code):
                raise ShopAIKeyChatError(code) from None
            try:
                return fn()
            except ShopAIKeyChatError:
                raise
            except Exception as exc2:
                raise ShopAIKeyChatError(classify_provider_failure(exc2)) from None

    def _structured_once(
        self,
        schema: type[BaseModel],
        messages: Sequence[object],
    ) -> object:
        """One strict_schema structured-output call (no repair, no retry)."""
        model = self.build_model(streaming=False)
        # Locked Phase 0 mode: function_calling + strict=True (strict_schema).
        structured = model.with_structured_output(
            schema,
            method="function_calling",
            strict=True,
        )
        invoke = getattr(structured, "invoke", None)
        if not callable(invoke):
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.PROVIDER_ERROR)
        result = invoke(list(messages))
        if isinstance(result, BaseModel):
            response_model = _response_model_from_message(result)
            self._reject_model_switch(response_model)
            return result.model_dump()
        if isinstance(result, Mapping):
            return dict(result)
        return result

    def _stream_once(self, messages: Sequence[object]) -> Iterator[StreamChunk]:
        model = self.build_model(streaming=True)
        stream = model.stream(list(messages))
        index = 0
        any_text = False
        for chunk in stream:
            self._raise_if_cancelled()
            response_model = _response_model_from_message(chunk)
            self._reject_model_switch(response_model)
            text = _assistant_text_from_content(getattr(chunk, "content", None))
            if not text:
                continue
            any_text = True
            yield StreamChunk(index=index, text=text)
            index += 1
        if not any_text:
            raise ShopAIKeyChatError(ShopAIKeyErrorCode.EMPTY_RESPONSE) from None


def _text_message(content: str) -> object:
    """Build a human message without importing langchain at module import time."""
    try:
        from langchain_core.messages import HumanMessage

        return HumanMessage(content=content)
    except Exception:
        return {"role": "user", "content": content}

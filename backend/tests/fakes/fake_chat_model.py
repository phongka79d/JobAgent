"""Deterministic fake chat model for Agent graph unit tests.

Never performs network I/O. Supports scripted ``AIMessage`` responses including
tool calls, records every invoke for assertion, and accepts ``bind_tools``
without changing scripted behavior.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import Field, PrivateAttr

# Exact Plan 13 repair forced-choice object (not a bare tool-name string).
CANONICAL_SAVE_JOB_TOOL_CHOICE: dict[str, Any] = {
    "type": "function",
    "function": {"name": "save_job"},
}


class FakeChatModel(BaseChatModel):
    """Scripted chat model: returns preconfigured AIMessages in order.

    When the script is exhausted, returns a plain text AIMessage so loops can
    terminate safely in misconfigured tests.
    """

    responses: list[AIMessage] = Field(default_factory=list)
    # Call log: each entry is the message list passed to ``_generate``.
    call_log: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)
    bound_kwargs: dict[str, Any] = Field(default_factory=dict)
    _call_index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Record a shallow copy of the prompt for test assertions.
        self.call_log.append(list(messages))
        if self._call_index < len(self.responses):
            message = self.responses[self._call_index]
            self._call_index += 1
        else:
            message = AIMessage(content="(fake model: no more scripted responses)")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> FakeChatModel:
        """Record bound tools/kwargs and return self (scripted responses unchanged)."""
        self.bound_tools = list(tools)
        self.bound_kwargs = dict(kwargs)
        return self

    def reset(self) -> None:
        """Clear call log and restart the response script."""
        self.call_log.clear()
        self.bound_tools.clear()
        self.bound_kwargs.clear()
        self._call_index = 0

    @property
    def invoke_count(self) -> int:
        """Number of model generations requested so far."""
        return len(self.call_log)


class PassiveJdBindingAwareFake(FakeChatModel):
    """Emit a valid source-only repair only for compatible schema + forced choice.

    RED until the repair binding exposes exactly the ordinary provider-visible
    ``save_job`` definition **and** the canonical forced-choice object. Any
    other binding (or ``permit_valid_repair=False``) repeats a mixed-source call.
    """

    mixed_text: str = ""
    preview_value: str = ""
    argument_value: str = ""
    provider_payload_value: str = ""
    permit_valid_repair: bool = True
    binding_log: list[tuple[list[Any], dict[str, Any]]] = Field(
        default_factory=list
    )

    @staticmethod
    def _has_compatible_ordinary_save_job_schema(tools: list[Any]) -> bool:
        """True when tools is exactly the ordinary compatible save_job definition."""
        if len(tools) != 1 or not isinstance(tools[0], dict):
            return False
        try:
            if tools[0].get("type") != "function":
                return False
            function = tools[0]["function"]
            params = function["parameters"]
            props = params["properties"]
        except (KeyError, TypeError):
            return False
        if function.get("name") != "save_job":
            return False
        if params.get("type") != "object":
            return False
        if set(props) != {"url", "text", "source", "preview"}:
            return False
        if "oneOf" in params or "anyOf" in params or "allOf" in params:
            return False
        if "required" in params or "additionalProperties" in params:
            return False
        for key in ("url", "text", "source"):
            prop = props.get(key)
            if not isinstance(prop, dict) or prop.get("type") != "string":
                return False
            if any(c in prop for c in ("const", "enum", "oneOf", "anyOf")):
                return False
        source = props["source"]
        if source.get("minLength") != 15 or source.get("maxLength") != 15:
            return False
        preview = props["preview"]
        if not isinstance(preview, dict) or preview.get("type") != "object":
            return False
        if "oneOf" in preview or "anyOf" in preview:
            return False
        preview_props = preview.get("properties")
        if not isinstance(preview_props, dict):
            return False
        if set(preview_props) != {"title", "company", "skills"}:
            return False
        try:
            title_max = preview_props["title"]["maxLength"]
            company_max = preview_props["company"]["maxLength"]
            skills = preview_props["skills"]
            items = skills["items"]
        except (KeyError, TypeError):
            return False
        return (
            title_max == 160
            and company_max == 160
            and skills.get("type") == "array"
            and skills.get("maxItems") == 5
            and items.get("type") == "string"
            and items.get("minLength") == 1
            and items.get("maxLength") == 80
        )

    def _bound_response(
        self,
        messages: list[BaseMessage],
        tools: list[Any],
        kwargs: dict[str, Any],
    ) -> AIMessage:
        self.call_log.append(list(messages))
        compatible_and_forced = (
            self._has_compatible_ordinary_save_job_schema(tools)
            and kwargs.get("tool_choice") == CANONICAL_SAVE_JOB_TOOL_CHOICE
        )
        valid = self.permit_valid_repair and compatible_and_forced
        args: dict[str, Any] = (
            {"source": "current_message"}
            if valid
            else {
                "text": self.mixed_text,
                "source": "current_message",
                "preview": {
                    "title": self.preview_value,
                    "company": self.argument_value,
                },
            }
        )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "save_job",
                    "args": args,
                    "id": f"bind-aware-{len(self.call_log)}",
                    "type": "tool_call",
                }
            ],
            additional_kwargs={
                "provider_payload": self.provider_payload_value,
            },
        )

    def bind_tools(
        self,
        tools: Sequence[Any],
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        """Return a binding-scoped runnable; valid repair depends on this bind."""
        bound_tools = list(tools)
        bound_kwargs = dict(kwargs)
        self.binding_log.append((bound_tools, bound_kwargs))
        self.bound_tools = bound_tools
        self.bound_kwargs = bound_kwargs
        return RunnableLambda(
            lambda messages: self._bound_response(
                list(messages), bound_tools, bound_kwargs
            )
        )

    def reset(self) -> None:
        """Clear call/binding logs and restart."""
        super().reset()
        self.binding_log.clear()

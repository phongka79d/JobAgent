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
from pydantic import Field, PrivateAttr


class FakeChatModel(BaseChatModel):
    """Scripted chat model: returns preconfigured AIMessages in order.

    When the script is exhausted, returns a plain text AIMessage so loops can
    terminate safely in misconfigured tests.
    """

    responses: list[AIMessage] = Field(default_factory=list)
    # Call log: each entry is the message list passed to ``_generate``.
    call_log: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)
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
        """Record bound tools and return self (scripted responses unchanged)."""
        self.bound_tools = list(tools)
        return self

    def reset(self) -> None:
        """Clear call log and restart the response script."""
        self.call_log.clear()
        self.bound_tools.clear()
        self._call_index = 0

    @property
    def invoke_count(self) -> int:
        """Number of model generations requested so far."""
        return len(self.call_log)

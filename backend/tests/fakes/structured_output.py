"""Shared scripted structured-output invoker for extraction unit/integration tests.

One owner for JD (and reusable profile-shaped) invoker fakes. Do not add a
second local FakeJdInvoker / ScriptedStructuredInvoker copy in product test
modules when this protocol is sufficient.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ScriptedStructuredInvoker:
    """Scripted ``invoke_structured`` seam: returns payloads or raises in order.

    Compatible with JD and profile extraction invoker Protocols used by
    ``extract_job_post_from_text`` / ``propose_profile_from_cv`` tests.
    Records call metadata for zero-external-call and repair-count assertions.
    """

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []

    @property
    def call_count(self) -> int:
        """Number of ``invoke_structured`` invocations recorded so far."""
        return len(self.calls)

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> Any:
        """Record the call, then return the next scripted payload or raise."""
        self.calls.append(
            {
                "is_repair": is_repair,
                "message_count": len(list(messages)),
            }
        )
        if not self.script:
            raise RuntimeError("fake invoker script exhausted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item("fake error")
        return item


# Historical JD test alias — same owner as ScriptedStructuredInvoker.
FakeJdInvoker = ScriptedStructuredInvoker

__all__ = [
    "FakeJdInvoker",
    "ScriptedStructuredInvoker",
]

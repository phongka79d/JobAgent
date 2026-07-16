"""Test-only fakes (never imported by production registration)."""

from tests.fakes.fake_chat_model import FakeChatModel
from tests.fakes.structured_output import FakeJdInvoker, ScriptedStructuredInvoker
from tests.fakes.synthetic_tool import (
    SYNTHETIC_ALLOWED_ACTIONS,
    SYNTHETIC_APPROVAL_KIND,
    SYNTHETIC_TOOL_NAME,
    build_synthetic_interrupt_tool,
)

__all__ = [
    "FakeChatModel",
    "FakeJdInvoker",
    "ScriptedStructuredInvoker",
    "SYNTHETIC_ALLOWED_ACTIONS",
    "SYNTHETIC_APPROVAL_KIND",
    "SYNTHETIC_TOOL_NAME",
    "build_synthetic_interrupt_tool",
]

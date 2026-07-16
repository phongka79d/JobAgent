"""Shared public FastAPI + SSE helpers for chat integration and E2E tests.

Single owner for wire SSE parsing, chat dependency overrides, and disposable
chat API environment. Integration modules import from here; do not copy local
``_parse_sse`` / ``_client_with_fake`` variants.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.dependencies import ChatAgentDeps, get_chat_agent_deps
from app.main import create_app
from app.schemas.sse import parse_sse_event
from app.tools.registry import ToolRegistry, production_registry
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import cleanup_isolated_sqlite
from tests.support.health import (
    FakeDriver,
    install_fake_driver,
    prepare_health_env,
)

FRONTEND_ORIGIN = "http://127.0.0.1:5173"
OTHER_ORIGIN = "http://evil.example:9999"


def ai_text(content: str) -> AIMessage:
    """Plain-text scripted assistant message (no tool calls)."""
    return AIMessage(content=content)


def ai_tool_call(
    name: str,
    *,
    call_id: str = "call-api-1",
    args: dict[str, Any] | None = None,
) -> AIMessage:
    """Scripted assistant message that requests one tool call."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": dict(args or {}),
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def parse_sse_wire(body: str) -> list[dict[str, Any]]:
    """Parse SSE wire text into validated event dicts (full data envelope)."""
    events: list[dict[str, Any]] = []
    for chunk in re.split(r"\n\n+", body.strip()):
        if not chunk.strip() or chunk.strip().startswith(":"):
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        event_id: str | None = None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
            elif line.startswith("id:"):
                event_id = line[len("id:") :].strip()
        if not data_lines:
            continue
        data = json.loads("\n".join(data_lines))
        typed = parse_sse_event(data)
        assert typed.event == event_name or event_name is None
        if event_id is not None:
            assert typed.event_id == event_id
        events.append(data)
    return events


def override_chat_deps(
    client: TestClient,
    *,
    model: FakeChatModel,
    registry: ToolRegistry | None = None,
    db_path: Path,
) -> None:
    """Inject fake chat model + optional registry for turn/resume routes."""
    deps = ChatAgentDeps(
        model=model,
        registry=registry if registry is not None else production_registry(),
        sqlite_path=db_path,
        include_assistant_status=False,
    )
    client.app.dependency_overrides[get_chat_agent_deps] = lambda: deps


def client_with_fake_chat(
    db_path: Path,
    model: FakeChatModel,
    registry: ToolRegistry | None = None,
) -> TestClient:
    """Build TestClient with dependency-overridden fake chat model/registry."""
    app = create_app()
    client = TestClient(app)
    override_chat_deps(client, model=model, registry=registry, db_path=db_path)
    return client


def direct_model(
    text: str = "Hello! How can I help with your job search?",
) -> FakeChatModel:
    """One-shot direct-answer model for greeting/history smoke tests."""
    return FakeChatModel(responses=[ai_text(text)])


@pytest.fixture
def chat_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, Path, FakeDriver]]:
    """Migrated temp SQLite + FILES_DIR + fake Neo4j for public chat API tests."""
    db_path, files_dir = prepare_health_env(monkeypatch, tmp_path, migrate=True)
    fake = install_fake_driver(monkeypatch)
    yield db_path, files_dir, fake
    cleanup_isolated_sqlite()


__all__ = [
    "FRONTEND_ORIGIN",
    "OTHER_ORIGIN",
    "ai_text",
    "ai_tool_call",
    "chat_env",
    "client_with_fake_chat",
    "direct_model",
    "override_chat_deps",
    "parse_sse_wire",
]

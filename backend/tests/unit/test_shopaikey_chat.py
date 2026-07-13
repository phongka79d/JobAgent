"""Unit tests for ShopAIKey ChatOpenAI adapter and conversation-first prompt.

Normal tests use fakes / local construction only — never the real provider.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.adapters.shopaikey_chat import (
    LOCKED_CHAT_MODEL,
    LOCKED_CHAT_TEMPERATURE,
    PHASE_0_CHAT_TOOL_MODE,
    bind_chat_tools,
    build_shopaikey_chat,
)
from app.agent.prompt import (
    PRODUCTION_DOMAIN_TOOL_NAMES,
    build_system_prompt,
)
from app.core.settings import Settings, clear_settings_cache
from langchain_openai import ChatOpenAI
from pydantic import AnyHttpUrl, SecretStr

# ---------------------------------------------------------------------------
# Sanitized settings helpers (never the developer's real root .env)
# ---------------------------------------------------------------------------

SANITIZED_ENV: dict[str, str] = {
    "FRONTEND_ORIGIN": "http://localhost:5173",
    "SQLITE_PATH": "/tmp/jobagent-test.db",
    "FILES_DIR": "/tmp/jobagent-files",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "test-neo4j-password-not-real",
    "SHOPAIKEY_BASE_URL": "https://api.shopaikey.com/v1",
    "SHOPAIKEY_API_KEY": "test-shopaikey-secret-not-real",
}

SECRET_API_KEY = "super-secret-shopaikey-api-key-FOR-UNIT-TEST-only"


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure adapter tests never load the real root ``.env`` secrets."""
    clear_settings_cache()
    for key in (
        "FRONTEND_ORIGIN",
        "SQLITE_PATH",
        "FILES_DIR",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "SHOPAIKEY_BASE_URL",
        "SHOPAIKEY_API_KEY",
        "LLM_MODEL",
        "LLM_TEMPERATURE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    clear_settings_cache()


def _settings(**overrides: Any) -> Settings:
    """Build Settings without file load (process values only via kwargs)."""
    base: dict[str, Any] = {
        "FRONTEND_ORIGIN": SANITIZED_ENV["FRONTEND_ORIGIN"],
        "SQLITE_PATH": SANITIZED_ENV["SQLITE_PATH"],
        "FILES_DIR": SANITIZED_ENV["FILES_DIR"],
        "NEO4J_URI": SANITIZED_ENV["NEO4J_URI"],
        "NEO4J_USER": SANITIZED_ENV["NEO4J_USER"],
        "NEO4J_PASSWORD": SecretStr(SANITIZED_ENV["NEO4J_PASSWORD"]),
        "SHOPAIKEY_BASE_URL": AnyHttpUrl(SANITIZED_ENV["SHOPAIKEY_BASE_URL"]),
        "SHOPAIKEY_API_KEY": SecretStr(SANITIZED_ENV["SHOPAIKEY_API_KEY"]),
        "LLM_MODEL": LOCKED_CHAT_MODEL,
        "LLM_TEMPERATURE": LOCKED_CHAT_TEMPERATURE,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Adapter configuration
# ---------------------------------------------------------------------------


def test_phase_0_tool_mode_constant() -> None:
    assert PHASE_0_CHAT_TOOL_MODE == "openai_function_calling"
    assert LOCKED_CHAT_MODEL == "gpt-4o-mini"
    assert LOCKED_CHAT_TEMPERATURE == 0.0


def test_build_shopaikey_chat_uses_injected_settings() -> None:
    settings = _settings(
        SHOPAIKEY_BASE_URL=AnyHttpUrl("https://api.shopaikey.com/v1/"),
        SHOPAIKEY_API_KEY=SecretStr(SECRET_API_KEY),
        LLM_MODEL="gpt-4o-mini",
        LLM_TEMPERATURE=0,
    )
    model = build_shopaikey_chat(settings)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o-mini"
    assert model.temperature == 0.0
    assert model.openai_api_base == "https://api.shopaikey.com/v1"
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == SECRET_API_KEY


def test_build_shopaikey_chat_uses_get_settings_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _settings(
        SHOPAIKEY_API_KEY=SecretStr(SECRET_API_KEY),
        LLM_MODEL="gpt-4o-mini",
        LLM_TEMPERATURE=0,
    )
    monkeypatch.setattr("app.adapters.shopaikey_chat.get_settings", lambda: cfg)
    model = build_shopaikey_chat()
    assert model.model_name == "gpt-4o-mini"
    assert model.temperature == 0.0
    assert model.openai_api_base == str(cfg.SHOPAIKEY_BASE_URL).rstrip("/")
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == SECRET_API_KEY


def test_build_does_not_call_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construction must not perform outbound HTTP."""

    def _block(*_a: Any, **_k: Any) -> None:
        raise AssertionError("network call during ChatOpenAI construction")

    monkeypatch.setattr("httpx.Client.request", _block)
    monkeypatch.setattr("httpx.AsyncClient.request", _block)
    # Also block OpenAI client HTTP if construction opened a client early.
    settings = _settings()
    model = build_shopaikey_chat(settings)
    assert model.model_name == "gpt-4o-mini"


def test_secret_not_exposed_in_model_repr_or_str() -> None:
    settings = _settings(SHOPAIKEY_API_KEY=SecretStr(SECRET_API_KEY))
    model = build_shopaikey_chat(settings)
    for rendered in (repr(model), str(model)):
        assert SECRET_API_KEY not in rendered
        assert "Authorization" not in rendered
        assert "Bearer " not in rendered


def test_bind_chat_tools_empty_returns_unbound_model() -> None:
    model = build_shopaikey_chat(_settings())
    assert bind_chat_tools(model, None) is model
    assert bind_chat_tools(model, []) is model


def test_bind_chat_tools_injects_tools_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = build_shopaikey_chat(_settings())
    bound_result = object()
    recorded: dict[str, Any] = {}

    def _fake_bind(self: Any, tools: list[Any], **kwargs: Any) -> object:
        recorded["tools"] = tools
        recorded["kwargs"] = kwargs
        recorded["self"] = self
        return bound_result

    monkeypatch.setattr(ChatOpenAI, "bind_tools", _fake_bind)
    fake_tools = [MagicMock(name="synthetic_probe")]
    out = bind_chat_tools(model, fake_tools)
    assert out is bound_result
    assert recorded["tools"] == fake_tools
    assert recorded["self"] is model


# ---------------------------------------------------------------------------
# Conversation-first prompt
# ---------------------------------------------------------------------------


def test_prompt_allows_direct_conversation_when_registry_empty() -> None:
    prompt = build_system_prompt(None)
    lower = prompt.lower()
    assert "greeting" in lower or "greetings" in lower
    assert "general knowledge" in lower
    assert "natural conversation" in lower or "answer every request" in lower
    assert "registered jobagent tools: none" in lower
    assert "do not call or invent tools" in lower


def test_prompt_empty_registry_has_no_domain_or_synthetic_tools() -> None:
    prompt = build_system_prompt([])
    for name in PRODUCTION_DOMAIN_TOOL_NAMES:
        assert name not in prompt
    assert "synthetic" not in prompt.lower()
    assert "match_jobs" not in prompt


def test_prompt_enumerates_only_injected_tools() -> None:
    prompt = build_system_prompt(["alpha_tool", "beta_tool"])
    assert "- alpha_tool" in prompt
    assert "- beta_tool" in prompt
    assert "use only these" in prompt.lower()
    # Still forbids inventing tools and false success.
    assert "do not invent" in prompt.lower()
    for name in PRODUCTION_DOMAIN_TOOL_NAMES:
        assert name not in prompt


def test_prompt_forbids_false_success_after_failed_tool_result() -> None:
    prompt = build_system_prompt(["any_tool"])
    lower = prompt.lower()
    assert "ok=false" in lower
    assert "never claim" in lower and "succeeded" in lower


def test_prompt_deduplicates_and_strips_tool_names() -> None:
    prompt = build_system_prompt(["  a  ", "a", "", "  b"])
    assert prompt.count("- a") == 1
    assert "- b" in prompt


def test_prompt_contains_no_secrets() -> None:
    prompt = build_system_prompt([SECRET_API_KEY])
    # Listing a tool named like a secret is caller error; adapter still must
    # not embed Authorization headers or provider key material by itself.
    empty = build_system_prompt()
    assert "Authorization" not in empty
    assert "SHOPAIKEY_API_KEY" not in empty
    assert "Bearer " not in empty
    # And the constant secret string is not baked into the empty prompt.
    assert SECRET_API_KEY not in empty
    # When intentionally injected as a tool name it may appear; that is not a leak.
    del prompt


def test_adapter_module_is_sole_chatopenai_construction_owner() -> None:
    """Static evidence: only the adapter constructs ChatOpenAI under app/."""
    app_root = Path(__file__).resolve().parents[2] / "app"
    hits: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "ChatOpenAI(" in text:
            rel = path.relative_to(app_root).as_posix()
            hits.append(rel)
    assert hits == ["adapters/shopaikey_chat.py"]

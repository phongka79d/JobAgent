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
    # Normal binding must omit tool_choice entirely.
    assert recorded["kwargs"] == {}


def test_bind_chat_tools_accepts_one_forced_tool_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repair binding passes the exact canonical forced-choice object only."""
    from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema

    model = build_shopaikey_chat(_settings())
    bound_result = object()
    recorded: dict[str, Any] = {}

    def _fake_bind(self: Any, tools: list[Any], **kwargs: Any) -> object:
        recorded["self"] = self
        recorded["tools"] = tools
        recorded["kwargs"] = kwargs
        return bound_result

    monkeypatch.setattr(ChatOpenAI, "bind_tools", _fake_bind)
    tool = save_job_openai_tool_schema()
    canonical_choice = {
        "type": "function",
        "function": {"name": SAVE_JOB_NAME},
    }

    bound = bind_chat_tools(model, [tool], tool_choice=canonical_choice)

    assert bound is bound_result
    assert recorded == {
        "self": model,
        "tools": [tool],
        "kwargs": {"tool_choice": canonical_choice},
    }


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


# ---------------------------------------------------------------------------
# Plan 12: readable responses, active-CV evidence, passive-JD policy
# ---------------------------------------------------------------------------


def test_prompt_response_style_is_conclusion_first_and_bounded() -> None:
    """Direct answer first; simple vs long structure; hide internals."""
    prompt = build_system_prompt(None)
    lower = prompt.lower()
    assert "response style" in lower
    assert "lead with the direct answer" in lower
    assert "first sentence" in lower or "first paragraph" in lower
    assert "simple answer" in lower
    assert "no heading" in lower
    assert "at most three" in lower
    assert "user's language" in lower or "user language" in lower
    assert "điểm chính" in lower or "diem chinh" in lower
    assert "hide internal" in lower or "hide internal selectors" in lower
    assert "cursor" in lower
    assert "hash" in lower
    # Existing general-conversation rules remain.
    assert "greeting" in lower or "greetings" in lower
    assert "general knowledge" in lower


def test_prompt_active_cv_requires_narrow_reads_and_no_invented_source() -> None:
    prompt = build_system_prompt(["read_active_cv"])
    lower = prompt.lower()
    assert "read_active_cv" in prompt
    assert "narrowest" in lower
    assert "never final body evidence" in lower or "never final body" in lower
    assert "entry_count" in lower or "outline" in lower
    assert "fact" in lower or "value" in lower or "quote" in lower
    assert "count" in lower
    assert "next_cursor" in lower
    assert "six-pass" in lower or "six pass" in lower
    assert "do not invent" in lower or "not invent" in lower
    assert "source url" in lower or "citation" in lower or "nguồn" in lower
    # Section absent when tool not registered.
    empty = build_system_prompt([])
    assert "Active CV evidence" not in empty


def test_prompt_passive_jd_current_message_opt_outs_and_no_auto_eval() -> None:
    prompt = build_system_prompt(["save_job", "match_jobs"])
    lower = prompt.lower()
    assert "save_job truthfulness" in lower
    assert "source='current_message'" in prompt or 'source="current_message"' in prompt
    assert "unsaved" in lower
    assert "confirmation card" in lower or "card decision" in lower
    assert "không lưu" in lower
    assert "đừng lưu" in lower or "dung luu" in lower
    assert "do not save" in lower
    assert "don't save" in lower or "don\u2019t save" in lower
    assert "sole public" in lower or "sole" in lower
    assert "match_jobs" in prompt
    assert "do not call match_jobs" in lower
    assert "evaluation" in lower
    # Named save truthfulness preserved (Plan 11).
    assert "before a toolresult exists" in lower
    assert "returned" in lower
    # Passive section absent without save_job.
    no_save = build_system_prompt(["match_jobs"])
    assert "Passive pasted" not in no_save
    assert "current_message" not in no_save


def test_prompt_intent_matrix_pure_paste_nl_save_analysis_and_opt_out() -> None:
    """Plan 14 (01A): semantic save-versus-analysis without phrase/layout gates."""
    prompt = build_system_prompt(["save_job", "match_jobs"])
    lower = prompt.lower()

    # Pure paste and natural-language save → passive current_message confirmation.
    assert "pure pasted" in lower or "pure paste" in lower
    assert "natural-language" in lower or "natural language" in lower
    assert "source='current_message'" in prompt or 'source="current_message"' in prompt
    assert "semantic" in lower
    # No exact-phrase / newline / line-count gate for semantic JD/save decisions.
    assert "exact command phrase" in lower or "exact" in lower
    assert "newline layout" in lower or "line count" in lower
    assert "do not require" in lower or "not require" in lower

    # Analysis-only: no save_job / no confirmation.
    assert "analyse" in lower or "analyze" in lower
    assert "summarise" in lower or "summarize" in lower
    assert "compare" in lower
    assert "without asking to save" in lower or "without" in lower and "save" in lower
    # Analysis-only must not call save_job (wording present near analysis policy).
    assert "do not call save_job" in lower

    # Analyse-and-save: answer plus confirmation-gated save.
    assert "analyse-and-save" in lower or "analyze-and-save" in lower
    assert "confirmation-gated" in lower or "confirmation gated" in lower

    # Clear opt-out guidance retained.
    assert "không lưu" in lower
    assert "do not save" in lower
    assert "suppresses" in lower or "do not call save_job" in lower

    # Direct URL/path and no auto-eval retained.
    assert "sole public" in lower
    assert "direct" in lower and ("url" in lower or "text" in lower)
    assert "do not call match_jobs" in lower
    assert "evaluation" in lower

    # ToolResult-only success claims retained (truthfulness section).
    assert "toolresult" in lower
    assert "before a toolresult exists" in lower

    # Still gated on save_job registration.
    no_save = build_system_prompt(["match_jobs"])
    assert "pure pasted" not in no_save.lower()
    assert "analyse-and-save" not in no_save.lower()
    assert "current_message" not in no_save


def test_prompt_profile_and_failure_rules_remain_with_plan12_policy() -> None:
    """Plan 12 additions must not drop profile or false-success rules."""
    prompt = build_system_prompt(
        [
            "propose_profile_from_cv",
            "commit_profile_draft",
            "save_job",
            "read_active_cv",
        ]
    )
    lower = prompt.lower()
    assert "ok=false" in lower
    assert "never claim" in lower and "succeeded" in lower
    assert "propose_profile_from_cv" in prompt
    assert "commit_profile_draft" in prompt
    assert "draft_id" in lower or "draft_id='current'" in lower
    assert "response style" in lower
    assert "active cv evidence" in lower
    assert "passive pasted" in lower


# ---------------------------------------------------------------------------
# Plan 13 (01A): ShopAIKey-compatible provider-visible save_job object
# ---------------------------------------------------------------------------


def test_save_job_provider_schema_is_ordinary_object_without_combinators() -> None:
    """Actual OpenAI-format payload: ordinary properties, no required combinators."""
    from app.schemas.jobs import (
        SAVE_JOB_PREVIEW_COMPANY_MAX,
        SAVE_JOB_PREVIEW_SKILL_MAX,
        SAVE_JOB_PREVIEW_SKILLS_MAX,
        SAVE_JOB_PREVIEW_TITLE_MAX,
    )
    from app.tools.jobs import (
        SAVE_JOB_DESCRIPTION,
        SAVE_JOB_NAME,
        save_job_openai_tool_schema,
    )
    from langchain_core.utils.function_calling import convert_to_openai_tool

    raw = save_job_openai_tool_schema()
    spec = convert_to_openai_tool(raw)
    assert spec["type"] == "function"
    assert spec["function"]["name"] == SAVE_JOB_NAME
    assert spec["function"]["description"] == SAVE_JOB_DESCRIPTION
    params = spec["function"]["parameters"]
    assert params["type"] == "object"
    assert set(params["properties"]) == {"url", "text", "source", "preview"}
    assert "required" not in params
    assert "oneOf" not in params
    assert "anyOf" not in params
    assert "allOf" not in params
    assert "additionalProperties" not in params

    for key in ("url", "text", "source"):
        prop = params["properties"][key]
        assert prop["type"] == "string"
        assert "const" not in prop
        assert "enum" not in prop
        assert "anyOf" not in prop
        assert "oneOf" not in prop
        assert "description" in prop
    # Exact runtime token length only; not a provider combinator.
    source_prop = params["properties"]["source"]
    assert source_prop.get("minLength") == 15
    assert source_prop.get("maxLength") == 15

    preview = params["properties"]["preview"]
    assert preview["type"] == "object"
    assert "oneOf" not in preview
    assert "anyOf" not in preview
    assert "additionalProperties" not in preview
    assert set(preview["properties"]) == {"title", "company", "skills"}
    assert preview["properties"]["title"]["maxLength"] == SAVE_JOB_PREVIEW_TITLE_MAX
    assert (
        preview["properties"]["company"]["maxLength"] == SAVE_JOB_PREVIEW_COMPANY_MAX
    )
    skills = preview["properties"]["skills"]
    assert skills["maxItems"] == SAVE_JOB_PREVIEW_SKILLS_MAX
    assert skills["items"]["minLength"] == 1
    assert skills["items"]["maxLength"] == SAVE_JOB_PREVIEW_SKILL_MAX

    rendered = str(params)
    assert "tool_call_id" not in rendered
    assert "state" not in rendered
    assert "Injected" not in rendered
    assert "oneOf" not in rendered
    assert "const" not in rendered
    assert "anyOf" not in rendered


def test_save_job_provider_schema_owner_has_ponytail_upgrade_path() -> None:
    """Provider-schema owner documents limitation and verified-upgrade path."""
    schemas_path = (
        Path(__file__).resolve().parents[2] / "app" / "schemas" / "jobs.py"
    )
    source = schemas_path.read_text(encoding="utf-8")
    assert "ponytail:" in source
    assert "ShopAIKey" in source
    assert "oneOf" in source
    assert "const" in source
    assert "anyOf" in source
    assert "documents" in source or "documented" in source
    assert "probe" in source


def test_normal_model_binding_uses_provider_dict_without_forced_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph normal bind: provider dict, no tool_choice; repair bind separate."""
    from app.agent.graph import PASSIVE_JD_REPAIR_TOOL_CHOICE, build_agent_graph
    from app.tools.jobs import SAVE_JOB_NAME, save_job_openai_tool_schema
    from app.tools.registry import production_registry

    from tests.fakes.fake_chat_model import FakeChatModel

    model = FakeChatModel(responses=[])
    binds: list[dict[str, Any]] = []
    original_bind = FakeChatModel.bind_tools

    def _capture_bind(
        self: FakeChatModel, tools: list[Any], **kwargs: Any
    ) -> FakeChatModel:
        binds.append({"tools": list(tools), "kwargs": dict(kwargs)})
        return original_bind(self, tools, **kwargs)

    monkeypatch.setattr(FakeChatModel, "bind_tools", _capture_bind)
    registry = production_registry()
    registry_save = next(t for t in registry.list_tools() if t.name == SAVE_JOB_NAME)
    bundle = build_agent_graph(model=model, registry=registry)

    assert len(binds) == 2
    normal = binds[0]
    repair = binds[1]
    assert "tool_choice" not in normal["kwargs"]
    bound = normal["tools"]
    assert len(bound) == 7
    save_defs = [
        item
        for item in bound
        if isinstance(item, dict)
        and item.get("type") == "function"
        and item.get("function", {}).get("name") == SAVE_JOB_NAME
    ]
    assert len(save_defs) == 1
    assert save_defs[0] == save_job_openai_tool_schema()
    # Repair binding: only compatible save_job + exact canonical choice.
    assert repair["tools"] == [save_job_openai_tool_schema()]
    assert repair["kwargs"] == {"tool_choice": PASSIVE_JD_REPAIR_TOOL_CHOICE}
    assert PASSIVE_JD_REPAIR_TOOL_CHOICE == {
        "type": "function",
        "function": {"name": SAVE_JOB_NAME},
    }
    # Runtime ToolNode still owns the original registry BaseTool instance.
    runtime = bundle.tool_node.tools_by_name[SAVE_JOB_NAME]
    assert runtime is registry_save
    assert not isinstance(runtime, dict)

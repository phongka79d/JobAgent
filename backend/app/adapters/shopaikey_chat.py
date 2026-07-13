"""Verified ShopAIKey ChatOpenAI adapter (Plan 3 §7.5 / Master §16.1).

Owns construction of the single production chat model from the root Settings
boundary. Uses the Phase 0-proven OpenAI-compatible base URL, masked API key,
locked ``gpt-4o-mini`` model, temperature zero, and function-calling tool mode.

Normal tests must not invoke the provider; construction performs no network I/O.
No classifier or fallback provider/model is defined here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.core.settings import Settings, get_settings

# Phase 0 gate: function_calling + tool_result_round_trip PASS via ordinary
# OpenAI-format tools. Chat uses bind_tools() in that mode only.
PHASE_0_CHAT_TOOL_MODE: str = "openai_function_calling"

# Locked defaults mirrored from Settings when callers assert configuration.
LOCKED_CHAT_MODEL: str = "gpt-4o-mini"
LOCKED_CHAT_TEMPERATURE: float = 0.0


def build_shopaikey_chat(
    settings: Settings | None = None,
) -> ChatOpenAI:
    """Build ``ChatOpenAI`` from the cached root settings boundary.

    Parameters
    ----------
    settings:
        Optional injected ``Settings`` (tests / graph factory). When omitted,
        uses :func:`app.core.settings.get_settings` — the sole configuration
        owner. Does not load a second env file or hard-code a provider host.

    Returns
    -------
    ChatOpenAI
        Configured client. Construction does not perform HTTP. The API key
        remains a ``SecretStr``-compatible value and is masked in repr/str.
    """
    cfg = settings if settings is not None else get_settings()
    # AnyHttpUrl string form; strip trailing slash for OpenAI-compatible clients.
    base_url = str(cfg.SHOPAIKEY_BASE_URL).rstrip("/")
    return ChatOpenAI(
        model=cfg.LLM_MODEL,
        temperature=float(cfg.LLM_TEMPERATURE),
        api_key=cfg.SHOPAIKEY_API_KEY,
        base_url=base_url,
    )


def bind_chat_tools(
    model: BaseChatModel,
    tools: Sequence[Any] | None = None,
) -> BaseChatModel | Runnable[Any, Any]:
    """Bind injected registry tools using Phase 0 OpenAI function-calling mode.

    Empty or missing ``tools`` returns the model unchanged so direct
    conversation remains tool-free. Callers inject fakes or production
    BaseTool/dict schemas; this adapter never registers domain tools itself.
    """
    if not tools:
        return model
    return model.bind_tools(list(tools))

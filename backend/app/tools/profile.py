"""Profile-domain Agent tools (Plan 4 §7.5) — boundaries without registration.

``propose_profile_from_cv`` and ``propose_profile_update`` are defined here for
later production registration (03B). This module does **not** register tools
into :func:`app.tools.registry.production_registry`.

Tool results are compact :class:`~app.schemas.tools.ToolResult` objects. Raw CV
text never appears in arguments summaries, ToolResult data, or logs.
There is no separate preference tool; ``propose_profile_update`` covers both
Candidate Profile facts and Job Preferences and never writes active singletons.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.tools import ToolResult
from app.services.profile_drafts import (
    arguments_summary_for_propose_cv,
    arguments_summary_for_propose_update,
    propose_profile_from_cv,
    propose_profile_update,
)
from app.services.profile_extraction import StructuredProfileInvoker
from app.services.skill_normalization import SkillNormalizer
from app.storage.attachments import AttachmentStorage

PROPOSE_PROFILE_FROM_CV_NAME: str = "propose_profile_from_cv"
PROPOSE_PROFILE_UPDATE_NAME: str = "propose_profile_update"


def build_propose_profile_from_cv_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    invoker: StructuredProfileInvoker,
    normalizer: SkillNormalizer,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> Any:
    """Build the compact ``propose_profile_from_cv`` LangChain tool.

    Dependencies are closed over (injected) so they never appear in the
    LLM-visible tool schema. Not registered for production in Plan 4 Batch02.
    """

    @tool(PROPOSE_PROFILE_FROM_CV_NAME)
    async def propose_profile_from_cv_tool(attachment_id: str) -> dict[str, Any]:
        """Propose a Candidate Profile draft from a staged CV attachment.

        Input is only ``attachment_id``. Active attachments return the approved
        profile; a staged attachment already backing the current draft is
        reused; other staged attachments run extraction into
        ``profile_drafts('current')``. Never commits active profile/preferences.
        """
        # arguments_summary_json contract (for later tool_execution rows): IDs only.
        _ = arguments_summary_for_propose_cv(attachment_id)

        result = await propose_profile_from_cv(
            attachment_id=attachment_id,
            session_factory=session_factory,
            storage=storage,
            invoker=invoker,
            normalizer=normalizer,
            extract_text_fn=extract_text_fn,
        )
        tool_result: ToolResult = result.tool_result
        return tool_result.model_dump(mode="json")

    return propose_profile_from_cv_tool


def build_propose_profile_update_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    normalizer: SkillNormalizer,
) -> Any:
    """Build the compact ``propose_profile_update`` LangChain tool.

    Covers profile facts and Job Preferences in one tool. Dependencies are
    injected and absent from the LLM-visible schema. Never writes active
    profile/preferences. Not registered for production in Plan 4 Batch02.
    """

    @tool(PROPOSE_PROFILE_UPDATE_NAME)
    async def propose_profile_update_tool(
        profile_changes: dict[str, Any] | None = None,
        preference_changes: dict[str, Any] | None = None,
        skill_corrections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Propose updates to the current draft or a copy of the approved profile.

        Applies profile and/or preference changes plus skill corrections
        (``source='user_correction'``, optional ``excluded=true``). Upserts only
        ``profile_drafts('current')``. Does not write active profile or
        preferences.
        """
        profile_map: Mapping[str, Any] | None = profile_changes
        prefs_map: Mapping[str, Any] | None = preference_changes
        skills_seq: Sequence[Mapping[str, Any]] | None = skill_corrections

        _ = arguments_summary_for_propose_update(
            profile_changes=profile_map,
            preference_changes=prefs_map,
            skill_corrections=skills_seq,
        )

        result = await propose_profile_update(
            session_factory=session_factory,
            normalizer=normalizer,
            profile_changes=profile_map,
            preference_changes=prefs_map,
            skill_corrections=skills_seq,
        )
        tool_result: ToolResult = result.tool_result
        return tool_result.model_dump(mode="json")

    return propose_profile_update_tool


__all__ = [
    "PROPOSE_PROFILE_FROM_CV_NAME",
    "PROPOSE_PROFILE_UPDATE_NAME",
    "build_propose_profile_from_cv_tool",
    "build_propose_profile_update_tool",
]

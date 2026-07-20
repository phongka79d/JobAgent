"""Profile-domain Agent tools (Plan 4 §7.5) — first production tool set.

Registers via :func:`build_production_profile_tools` / ``production_registry``:

* ``propose_profile_from_cv``
* ``propose_profile_update``
* ``commit_profile_draft`` (interrupt-guarded)

Tool results are compact :class:`~app.schemas.tools.ToolResult` objects. Raw CV
text never appears in arguments summaries, ToolResult data, or logs.
There is no separate preference tool; ``propose_profile_update`` covers both
Candidate Profile facts and Job Preferences and never writes active singletons.

All three tools use Plan 3 ``(run_id, tool_call_id)`` replay via
:func:`~app.services.tool_execution.execute_tool`. Hidden
``InjectedToolCallId`` / ``InjectedState`` identity matches Job tools.
``commit_profile_draft`` enables running re-entry so one tool_executions row
stays ``running`` across interrupt and terminalizes once.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.profiles import PROFILE_DRAFT_ID
from app.db.session import get_session_factory
from app.graph.sync_candidate import AsyncGraphDriver
from app.repositories import profiles as profile_repo
from app.schemas.tools import ToolResult
from app.services.profile_approval import ApprovalCommitResult, commit_approved_draft
from app.services.profile_drafts import (
    ERROR_INVALID_PROFILE_UPDATE,
    arguments_summary_for_propose_cv,
    arguments_summary_for_propose_update,
    propose_profile_from_cv,
    propose_profile_update,
)
from app.services.profile_extraction import StructuredProfileInvoker
from app.services.skill_normalization import SkillNormalizer
from app.services.tool_execution import execute_tool
from app.storage.attachments import AttachmentStorage

PROPOSE_PROFILE_FROM_CV_NAME: str = "propose_profile_from_cv"
PROPOSE_PROFILE_UPDATE_NAME: str = "propose_profile_update"
COMMIT_PROFILE_DRAFT_NAME: str = "commit_profile_draft"

# Durable interrupt projection (Master §10.3 / Plan 4 §7.5–7.6).
PROFILE_COMMIT_KIND: str = "profile_commit"
PROFILE_COMMIT_ACTIONS: tuple[str, str] = ("save_profile", "request_changes")

ERROR_INVALID_DRAFT_ID: str = "INVALID_DRAFT_ID"
ERROR_DRAFT_NOT_FOUND: str = "DRAFT_NOT_FOUND"
ERROR_MISSING_RUN_ID: str = "MISSING_RUN_ID"
ERROR_INVALID_APPROVAL_ACTION: str = "INVALID_APPROVAL_ACTION"

CommitApprovedFn = Callable[..., Awaitable[ApprovalCommitResult]]


def build_profile_commit_projection(
    *,
    tool_call_id: str,
    draft_id: str = PROFILE_DRAFT_ID,
    card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact ``pending_approval`` / ``approval_required`` projection."""
    return {
        "kind": PROFILE_COMMIT_KIND,
        "draft_id": draft_id,
        "allowed_actions": list(PROFILE_COMMIT_ACTIONS),
        "card": {
            "tool_name": COMMIT_PROFILE_DRAFT_NAME,
            "tool_call_id": tool_call_id,
            "draft_id": draft_id,
            **(card or {}),
        },
    }


def build_propose_profile_from_cv_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: AttachmentStorage | None = None,
    invoker: StructuredProfileInvoker | None = None,
    normalizer: SkillNormalizer | None = None,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> Any:
    """Build the compact ``propose_profile_from_cv`` LangChain tool.

    Dependencies and ``run_id`` / ``tool_call_id`` identity are closed over or
    injected so they do not appear in the LLM-visible tool schema (only
    ``attachment_id``). Resolve process defaults only at invoke time when
    omitted so registry construction stays free of eager provider/IO work.
    Durable execution and ``tool_status`` publication go through
    :func:`~app.services.tool_execution.execute_tool`.
    """

    @tool(PROPOSE_PROFILE_FROM_CV_NAME)
    async def propose_profile_from_cv_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        attachment_id: str,
        reprocess: bool = False,
    ) -> dict[str, Any]:
        """Propose a Candidate Profile draft from a CV attachment.

        Pass an exact attachment UUID for this turn (never invent IDs, paths,
        or placeholders like ``current`` / ``latest``). With ``reprocess=false``
        (default): active attachments return the approved profile; a staged
        attachment already backing the current draft is reused; other staged
        attachments run extraction into ``profile_drafts('current')``. With
        ``reprocess=true``: active or archived attachments re-run document-first
        extraction into drafts without changing active selection. Never commits
        active profile/preferences.
        """
        from app.core.settings import get_settings
        from app.services.profile_extraction import ShopAIKeyStructuredProfileInvoker

        factory = (
            session_factory
            if session_factory is not None
            else get_session_factory()
        )
        run_id = state.get("run_id") if isinstance(state, dict) else None
        if not isinstance(run_id, str) or run_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="propose_profile_from_cv requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="propose_profile_from_cv requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        turn_ids = (
            list(state.get("attachment_ids") or [])
            if isinstance(state, dict)
            else []
        )
        # CV Manager reprocess turns stamp source_attachment_id on the run.
        # Live models often omit reprocess=true; force re-extract for owned runs
        # so active short-circuit / archived miss cannot skip draft publication.
        from app.repositories import agent_runs as runs_repo

        owned_attachment_id: str | None = None
        async with factory() as session:
            run = await runs_repo.get_run(session, run_id)
            if (
                run is not None
                and isinstance(run.source_attachment_id, str)
                and run.source_attachment_id.strip() != ""
            ):
                owned_attachment_id = run.source_attachment_id.strip()
        do_reprocess = bool(reprocess) or owned_attachment_id is not None
        normalized_turn_ids = [
            item.strip()
            for item in turn_ids
            if isinstance(item, str) and item.strip()
        ]
        unique_turn_ids = list(dict.fromkeys(normalized_turn_ids))
        effective_attachment_id = attachment_id
        if not do_reprocess and len(unique_turn_ids) == 1:
            # The single upload returned by this turn is authoritative; a model
            # cannot replace it with an older active UUID.
            effective_attachment_id = unique_turn_ids[0]

        async def _invoke() -> ToolResult:
            from app.db.models.attachments import (
                ATTACHMENT_STATE_ACTIVE,
                ATTACHMENT_STATE_ARCHIVED,
            )
            from app.repositories import attachments as att_repo
            from app.services.attachment_resolve import (
                looks_like_attachment_uuid,
                resolve_attachment_id_for_propose,
            )

            store = (
                storage
                if storage is not None
                else AttachmentStorage(get_settings().FILES_DIR)
            )
            inv = (
                invoker
                if invoker is not None
                else ShopAIKeyStructuredProfileInvoker()
            )
            norm = (
                normalizer
                if normalizer is not None
                else SkillNormalizer.production()
            )
            async with factory() as session:
                if do_reprocess:
                    # Reprocess targets active/archived; staged resolve would miss.
                    candidates: list[str] = []
                    # Prefer the CV-owned attachment stamped on the reprocess run.
                    if owned_attachment_id is not None:
                        candidates.append(owned_attachment_id)
                    raw = (
                        attachment_id.strip()
                        if isinstance(attachment_id, str)
                        else ""
                    )
                    if (
                        raw
                        and looks_like_attachment_uuid(raw)
                        and raw not in candidates
                    ):
                        candidates.append(raw)
                    for item in turn_ids:
                        if (
                            isinstance(item, str)
                            and item.strip()
                            and looks_like_attachment_uuid(item.strip())
                            and item.strip() not in candidates
                        ):
                            candidates.append(item.strip())
                    resolved = None
                    for candidate in candidates:
                        row = await att_repo.get_by_id(session, candidate)
                        if row is not None and row.state in (
                            ATTACHMENT_STATE_ACTIVE,
                            ATTACHMENT_STATE_ARCHIVED,
                        ):
                            resolved = candidate
                            break
                else:
                    # Resolve placeholders like "current" to a staged/active UUID.
                    resolved = await resolve_attachment_id_for_propose(
                        session,
                        effective_attachment_id,
                        turn_attachment_ids=turn_ids,
                    )
            if resolved is None:
                return ToolResult(
                    ok=False,
                    code="ATTACHMENT_NOT_FOUND",
                    summary=(
                    f"attachment {effective_attachment_id!r} not found; upload a CV "
                        "or pass a staged attachment UUID"
                        if not do_reprocess
                        else (
                            f"attachment {effective_attachment_id!r} not found or not "
                            "eligible for reprocess"
                        )
                    ),
                    data={"attachment_id": effective_attachment_id},
                )
            result = await propose_profile_from_cv(
                attachment_id=resolved,
                session_factory=factory,
                storage=store,
                invoker=inv,
                normalizer=norm,
                extract_text_fn=extract_text_fn,
                reprocess=do_reprocess,
            )
            return result.tool_result

        # Report the authoritative upload UUID; reprocess keeps its owned UUID.
        args_summary = arguments_summary_for_propose_cv(
            effective_attachment_id, reprocess=do_reprocess
        )
        # CV-scoped reprocess: stamp tool ownership from the owned id when set.
        if do_reprocess and owned_attachment_id is not None:
            from app.repositories import tool_executions as tool_repo

            async with factory() as session:
                await tool_repo.get_or_create_pending(
                    session,
                    run_id=run_id,
                    tool_call_id=tool_call_id,
                    tool_name=PROPOSE_PROFILE_FROM_CV_NAME,
                    arguments_summary_json=args_summary,
                    source_attachment_id=owned_attachment_id,
                )
                await session.commit()

        tool_result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=PROPOSE_PROFILE_FROM_CV_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
        )
        return tool_result.model_dump(mode="json")

    return propose_profile_from_cv_tool


def build_propose_profile_update_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    normalizer: SkillNormalizer | None = None,
) -> Any:
    """Build the compact ``propose_profile_update`` LangChain tool.

    Covers profile facts and Job Preferences in one tool. Dependencies and
    ``run_id`` / ``tool_call_id`` identity are injected and absent from the
    LLM-visible schema (update fields only). Never writes active
    profile/preferences. Durable execution uses the shared
    :func:`~app.services.tool_execution.execute_tool` owner.
    """

    @tool(PROPOSE_PROFILE_UPDATE_NAME)
    async def propose_profile_update_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
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
        factory = (
            session_factory
            if session_factory is not None
            else get_session_factory()
        )
        run_id = state.get("run_id") if isinstance(state, dict) else None
        if not isinstance(run_id, str) or run_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="propose_profile_update requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="propose_profile_update requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        profile_map: Mapping[str, Any] | None = profile_changes
        prefs_map: Mapping[str, Any] | None = preference_changes
        skills_seq: Sequence[Mapping[str, Any]] | None = skill_corrections

        args_summary = arguments_summary_for_propose_update(
            profile_changes=profile_map,
            preference_changes=prefs_map,
            skill_corrections=skills_seq,
        )

        async def _invoke() -> ToolResult:
            norm = (
                normalizer
                if normalizer is not None
                else SkillNormalizer.production()
            )
            result = await propose_profile_update(
                session_factory=factory,
                normalizer=norm,
                profile_changes=profile_map,
                preference_changes=prefs_map,
                skill_corrections=skills_seq,
            )
            return result.tool_result

        tool_result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=PROPOSE_PROFILE_UPDATE_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
        )
        return tool_result.model_dump(mode="json")

    return propose_profile_update_tool


def build_commit_profile_draft_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: AttachmentStorage | None = None,
    normalizer: SkillNormalizer | None = None,
    driver: AsyncGraphDriver | None = None,
    sync_fn: Callable[..., Awaitable[None]] | None = None,
    commit_fn: CommitApprovedFn | None = None,
) -> Any:
    """Build interrupt-guarded ``commit_profile_draft`` LangChain tool.

    Validates authorization/draft, claims durable ``(run_id, tool_call_id)``,
    calls ``interrupt()`` before any active profile/preference side effect, and
    on resume applies ``save_profile`` or ``request_changes`` under the same
    identity. Hidden injected args never appear in the LLM-visible schema.
    """

    @tool(COMMIT_PROFILE_DRAFT_NAME)
    async def commit_profile_draft_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        draft_id: str = PROFILE_DRAFT_ID,
    ) -> dict[str, Any]:
        """Request approval to commit ``profile_drafts('current')``.

        Pauses for ``save_profile`` or ``request_changes`` before any active
        profile write. Input is only ``draft_id`` (must be ``current``).
        """
        from app.core.settings import get_settings

        factory = (
            session_factory
            if session_factory is not None
            else get_session_factory()
        )
        run_id = state.get("run_id") if isinstance(state, dict) else None
        if not isinstance(run_id, str) or run_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="commit_profile_draft requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="commit_profile_draft requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        async def _invoke() -> ToolResult:
            if draft_id != PROFILE_DRAFT_ID:
                return ToolResult(
                    ok=False,
                    code=ERROR_INVALID_DRAFT_ID,
                    summary=(
                        f"draft_id must be {PROFILE_DRAFT_ID!r}; "
                        f"got {draft_id!r}"
                    ),
                    data={"draft_id": draft_id},
                )

            # Validate draft exists before interrupt (no active-side effects).
            async with factory() as session:
                draft_row = await profile_repo.get_current_draft(session)
            if draft_row is None:
                return ToolResult(
                    ok=False,
                    code=ERROR_DRAFT_NOT_FOUND,
                    summary="No current profile draft to commit",
                    data={"draft_id": PROFILE_DRAFT_ID},
                )

            # Pause before any active profile/preference side effect.
            decision = interrupt(
                build_profile_commit_projection(
                    tool_call_id=tool_call_id,
                    draft_id=PROFILE_DRAFT_ID,
                )
            )
            action = decision if isinstance(decision, str) else str(decision)

            if action == "request_changes":
                return ToolResult(
                    ok=True,
                    code=None,
                    summary=(
                        "Changes requested; draft preserved for a new "
                        "correction turn"
                    ),
                    data={
                        "committed": False,
                        "draft_id": PROFILE_DRAFT_ID,
                        "action": "request_changes",
                    },
                )

            if action != "save_profile":
                return ToolResult(
                    ok=False,
                    code=ERROR_INVALID_APPROVAL_ACTION,
                    summary=f"unsupported approval action {action!r}",
                    data={"action": action},
                )

            store = (
                storage
                if storage is not None
                else AttachmentStorage(get_settings().FILES_DIR)
            )
            norm = (
                normalizer
                if normalizer is not None
                else SkillNormalizer.production()
            )
            do_commit: CommitApprovedFn = (
                commit_fn if commit_fn is not None else commit_approved_draft
            )
            outcome = await do_commit(
                session_factory=factory,
                storage=store,
                normalizer=norm,
                driver=driver,
                sync_fn=sync_fn,
            )

            data: dict[str, Any] = {
                "committed": bool(outcome.sqlite_committed),
                "draft_id": PROFILE_DRAFT_ID,
                "action": "save_profile",
                "sqlite_committed": outcome.sqlite_committed,
                "cleanup_ok": outcome.cleanup_ok,
                "sync_ok": outcome.sync_ok,
            }
            if outcome.data:
                # Compact IDs/flags only; never raw CV text.
                for key in (
                    "active_attachment_id",
                    "previous_attachment_id",
                    "preferences_updated",
                    "profile_updated_at",
                    "rebuild_instruction",
                    "code",
                ):
                    if key in outcome.data:
                        data[key] = outcome.data[key]

            if outcome.ok:
                return ToolResult(
                    ok=True,
                    code=None,
                    summary=outcome.summary,
                    data=data,
                )

            # Pre-commit failure vs committed-SQLite/failed-derived-sync.
            if outcome.sqlite_committed:
                summary = outcome.summary
                if not summary:
                    summary = (
                        "Profile committed to SQLite but derived Candidate "
                        "sync failed"
                    )
                return ToolResult(
                    ok=False,
                    code=outcome.code,
                    summary=summary,
                    data=data,
                )

            return ToolResult(
                ok=False,
                code=outcome.code,
                summary=outcome.summary
                or "Profile commit failed before SQLite approval",
                data=data,
            )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=COMMIT_PROFILE_DRAFT_NAME,
            invoke=_invoke,
            arguments_summary_json={"draft_id": draft_id},
            session_factory=factory,
            allow_running_reentry=True,
        )
        return result.model_dump(mode="json")

    return commit_profile_draft_tool


def build_production_profile_tools(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: AttachmentStorage | None = None,
    invoker: StructuredProfileInvoker | None = None,
    normalizer: SkillNormalizer | None = None,
    driver: AsyncGraphDriver | None = None,
    extract_text_fn: Callable[[Any], Any] | None = None,
    sync_fn: Callable[..., Awaitable[None]] | None = None,
    commit_fn: CommitApprovedFn | None = None,
) -> list[Any]:
    """Build exactly the three Plan 4 production profile tools (no match_jobs)."""
    return [
        build_propose_profile_from_cv_tool(
            session_factory=session_factory,
            storage=storage,
            invoker=invoker,
            normalizer=normalizer,
            extract_text_fn=extract_text_fn,
        ),
        build_propose_profile_update_tool(
            session_factory=session_factory,
            normalizer=normalizer,
        ),
        build_commit_profile_draft_tool(
            session_factory=session_factory,
            storage=storage,
            normalizer=normalizer,
            driver=driver,
            sync_fn=sync_fn,
            commit_fn=commit_fn,
        ),
    ]


__all__ = [
    "COMMIT_PROFILE_DRAFT_NAME",
    "ERROR_INVALID_PROFILE_UPDATE",
    "ERROR_DRAFT_NOT_FOUND",
    "ERROR_INVALID_APPROVAL_ACTION",
    "ERROR_INVALID_DRAFT_ID",
    "ERROR_MISSING_RUN_ID",
    "PROFILE_COMMIT_ACTIONS",
    "PROFILE_COMMIT_KIND",
    "PROPOSE_PROFILE_FROM_CV_NAME",
    "PROPOSE_PROFILE_UPDATE_NAME",
    "build_commit_profile_draft_tool",
    "build_production_profile_tools",
    "build_profile_commit_projection",
    "build_propose_profile_from_cv_tool",
    "build_propose_profile_update_tool",
]

"""Active-CV read tool (Master §13.7) — production tool seven.

Registers via :func:`build_read_active_cv_tool` / ``production_registry``:

* ``read_active_cv`` — bounded active-only section/search/chunk evidence

Delegates body reading solely to
:func:`~app.services.active_cv_reader.read_active_cv`. Durable identity and
replay use :func:`~app.services.tool_execution.execute_tool`. Argument
summaries store selector/count metadata only — never returned CV bodies.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_session_factory
from app.schemas.tools import ToolResult
from app.services import active_cv_reader as active_cv_reader_service
from app.services.tool_execution import execute_tool

logger = logging.getLogger(__name__)

READ_ACTIVE_CV_NAME: str = "read_active_cv"

ERROR_MISSING_RUN_ID: str = "MISSING_RUN_ID"
ERROR_READ_ACTIVE_CV_FAILED: str = "READ_ACTIVE_CV_FAILED"


def arguments_summary_for_read_active_cv(
    *,
    mode: str,
    section_id: str | None,
    query: str | None,
    chunk_ordinal: int | None,
    max_results: int,
    max_chars: int,
    cursor: str | None,
) -> dict[str, Any]:
    """Compact args summary: selectors and bounds only (no CV body text)."""
    summary: dict[str, Any] = {
        "mode": mode,
        "max_results": max_results,
        "max_chars": max_chars,
        "cursor_present": bool(cursor),
    }
    if section_id is not None:
        summary["section_id"] = section_id
    if query is not None:
        summary["query"] = query
    if chunk_ordinal is not None:
        summary["chunk_ordinal"] = chunk_ordinal
    return summary


def build_read_active_cv_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Any:
    """Build read-only ``read_active_cv`` LangChain tool.

    Active attachment is resolved server-side by the (06A) reader. The LLM
    schema exposes mode and selectors only — never attachment IDs, paths, or
    PDF bytes. Requires an active approved profile for successful body pages.
    """

    @tool(READ_ACTIVE_CV_NAME)
    async def read_active_cv_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        mode: str,
        section_id: str | None = None,
        query: str | None = None,
        chunk_ordinal: int | None = None,
        cursor: str | None = None,
        max_results: int = active_cv_reader_service.DEFAULT_MAX_RESULTS,
        max_chars: int = active_cv_reader_service.DEFAULT_MAX_CHARS,
    ) -> dict[str, Any]:
        """Read one bounded page of the active CV (section, search, or chunk).

        Resolves the active attachment server-side; never pass archived or
        staged attachment IDs. Prefer the narrowest mode that answers the
        user. Use ``section`` with an outline section_id for structured
        entries, ``search`` with a short query for matching excerpts, or
        ``chunk`` with chunk_ordinal for raw ordered pages. Paginate with
        next_cursor only when the user request genuinely needs more evidence;
        do not walk every cursor automatically. Independent caps:
        max_results 1..10 (default 5), max_chars 500..12000 (default 6000).
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
                summary="read_active_cv requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="read_active_cv requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        effective_mode = mode.strip() if isinstance(mode, str) else ""
        args_summary = arguments_summary_for_read_active_cv(
            mode=effective_mode,
            section_id=section_id,
            query=query,
            chunk_ordinal=chunk_ordinal,
            max_results=max_results,
            max_chars=max_chars,
            cursor=cursor,
        )

        async with factory() as session:
            identity_or_error = (
                await active_cv_reader_service.resolve_active_cv_identity(session)
            )
        if isinstance(identity_or_error, ToolResult):
            identity = None
            preflight_error = identity_or_error
        else:
            identity = identity_or_error
            preflight_error = None
        owner = identity.attachment_id if identity is not None else None

        async def _invoke() -> ToolResult:
            if preflight_error is not None:
                return preflight_error
            assert identity is not None
            try:
                async with factory() as session:
                    result = await active_cv_reader_service.read_active_cv(
                        session,
                        mode=effective_mode,
                        section_id=section_id,
                        query=query,
                        chunk_ordinal=chunk_ordinal,
                        cursor=cursor,
                        max_results=max_results,
                        max_chars=max_chars,
                        expected_identity=identity,
                    )
                if not result.ok:
                    return result
                async with factory() as session:
                    current = (
                        await active_cv_reader_service.resolve_active_cv_identity(
                            session
                        )
                    )
                if isinstance(current, ToolResult) or current != identity:
                    return ToolResult(
                        ok=False,
                        code=active_cv_reader_service.ERROR_ACTIVE_CV_CHANGED,
                        summary=active_cv_reader_service.ACTIVE_CV_CHANGED_SUMMARY,
                        data=None,
                    )
                return result
            except Exception as exc:
                logger.info(
                    "read_active_cv unexpected failure type=%s",
                    type(exc).__name__,
                )
                return ToolResult(
                    ok=False,
                    code=ERROR_READ_ACTIVE_CV_FAILED,
                    summary=(
                        "Active CV read failed unexpectedly; retry later "
                        "or reprocess the active document."
                    ),
                    data=None,
                )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=READ_ACTIVE_CV_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
            source_attachment_id=owner,
        )
        return result.model_dump(mode="json")

    return read_active_cv_tool


def build_production_active_cv_tools(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> list[Any]:
    """Build exactly the one Plan 9 active-CV read tool."""
    return [
        build_read_active_cv_tool(session_factory=session_factory),
    ]


__all__ = [
    "ERROR_MISSING_RUN_ID",
    "ERROR_READ_ACTIVE_CV_FAILED",
    "READ_ACTIVE_CV_NAME",
    "arguments_summary_for_read_active_cv",
    "build_production_active_cv_tools",
    "build_read_active_cv_tool",
]

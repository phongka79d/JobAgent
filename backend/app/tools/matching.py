"""Match-domain Agent tool (Plan 6 §7.8) — production tool six.

Registers via :func:`build_match_jobs_tool` / ``production_registry``:

* ``match_jobs`` — read/compute-only ranking against the approved profile

Tool results are compact :class:`~app.schemas.tools.ToolResult` objects carrying
:class:`~app.schemas.matching.MatchJobsResultData` (or an empty failure payload).
Uses Plan 3 ``(run_id, tool_call_id)`` replay via
:func:`~app.services.tool_execution.execute_tool`. Does not re-implement
matching orchestration; delegates to :func:`~app.services.matching.match_jobs`.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, cast

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.shopaikey_embeddings import ShopAIKeyEmbeddingAdapter
from app.db.session import get_session_factory
from app.graph.consistency import NEO4J_UNAVAILABLE, AsyncGraphReadDriver
from app.graph.sync_shared import AsyncGraphDriver
from app.schemas.tools import ToolResult
from app.services.job_projection import EmbeddingClient
from app.services.matching import (
    DEFAULT_MATCH_LIMIT,
    MATCH_LIMIT_MAX,
    MATCH_LIMIT_MIN,
    MatchJobsServiceResult,
    match_jobs,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.tool_execution import execute_tool

logger = logging.getLogger(__name__)

MATCH_JOBS_NAME: str = "match_jobs"

ERROR_MISSING_RUN_ID: str = "MISSING_RUN_ID"
ERROR_INVALID_MATCH_LIMIT: str = "INVALID_MATCH_LIMIT"
ERROR_MATCH_JOBS_FAILED: str = "MATCH_JOBS_FAILED"


def _arguments_summary_match(*, limit: int) -> dict[str, Any]:
    """Compact args summary: only the effective integer limit."""
    return {"limit": limit}


def _tool_result_from_service(result: MatchJobsServiceResult) -> ToolResult:
    """Map service outcome to strict ToolResult success/failure coupling."""
    data: dict[str, Any] = result.data.model_dump(mode="json")
    if result.rebuild_instruction is not None:
        data["rebuild_instruction"] = result.rebuild_instruction

    if result.ok:
        count = result.data.count
        summary = result.message if result.message else f"Matched {count} job(s)"
        return ToolResult(ok=True, code=None, summary=summary, data=data)

    code = result.error_code or ERROR_MATCH_JOBS_FAILED
    return ToolResult(
        ok=False,
        code=code,
        summary=result.message or "Matching failed",
        data=data,
    )


def _empty_failure_data(limit: int) -> dict[str, Any]:
    return {"results": [], "count": 0, "limit": limit}


def build_match_jobs_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    driver: AsyncGraphDriver | None = None,
    embedding_client: EmbeddingClient | None = None,
    normalizer: SkillNormalizer | None = None,
) -> Any:
    """Build read/compute-only ``match_jobs`` LangChain tool.

    Dependencies are closed over and absent from the LLM-visible schema.
    Requires an active approved profile (including while a replacement draft
    is pending). Available only when the matching service preconditions pass.
    """

    @tool(MATCH_JOBS_NAME)
    async def match_jobs_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Rank saved jobs against the active approved candidate profile.

        Optional ``limit`` defaults to 10 and must be in 1..10. Read/compute-only;
        never writes applications, graph rows, or a score cache. During a pending
        profile replacement, matches against the approved profile only.
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
                summary="match_jobs requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="match_jobs requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        effective_limit = DEFAULT_MATCH_LIMIT if limit is None else limit
        if (
            not isinstance(effective_limit, int)
            or isinstance(effective_limit, bool)
            or effective_limit < MATCH_LIMIT_MIN
            or effective_limit > MATCH_LIMIT_MAX
        ):
            return ToolResult(
                ok=False,
                code=ERROR_INVALID_MATCH_LIMIT,
                summary=(
                    f"match_jobs limit must be an integer in "
                    f"{MATCH_LIMIT_MIN}..{MATCH_LIMIT_MAX}"
                ),
                data=_empty_failure_data(DEFAULT_MATCH_LIMIT),
            ).model_dump(mode="json")

        args_summary = _arguments_summary_match(limit=effective_limit)

        async def _invoke() -> ToolResult:
            if driver is None:
                return ToolResult(
                    ok=False,
                    code=NEO4J_UNAVAILABLE,
                    summary="Neo4j is unavailable for job matching.",
                    data=_empty_failure_data(effective_limit),
                )

            emb: EmbeddingClient = (
                embedding_client
                if embedding_client is not None
                else ShopAIKeyEmbeddingAdapter()
            )
            skill_norm = (
                normalizer
                if normalizer is not None
                else SkillNormalizer.production()
            )

            try:
                # Production Neo4j driver satisfies the read-only protocol.
                graph_driver = cast(AsyncGraphReadDriver, driver)
                service_result = await match_jobs(
                    session_factory=factory,
                    graph_driver=graph_driver,
                    embedding_client=emb,
                    normalizer=skill_norm,
                    limit=effective_limit,
                )
            except Exception as exc:
                # Terminalize every escape so durable row never stays running.
                logger.info(
                    "match_jobs unexpected failure type=%s",
                    type(exc).__name__,
                )
                return ToolResult(
                    ok=False,
                    code=ERROR_MATCH_JOBS_FAILED,
                    summary=(
                        "Matching failed unexpectedly; retry later or "
                        "check graph/provider health."
                    ),
                    data=_empty_failure_data(effective_limit),
                )

            return _tool_result_from_service(service_result)

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=MATCH_JOBS_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
        )
        return result.model_dump(mode="json")

    return match_jobs_tool


def build_production_match_tools(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    driver: AsyncGraphDriver | None = None,
    embedding_client: EmbeddingClient | None = None,
    normalizer: SkillNormalizer | None = None,
) -> list[Any]:
    """Build exactly the one Plan 6 matching tool."""
    return [
        build_match_jobs_tool(
            session_factory=session_factory,
            driver=driver,
            embedding_client=embedding_client,
            normalizer=normalizer,
        )
    ]


__all__ = [
    "ERROR_INVALID_MATCH_LIMIT",
    "ERROR_MATCH_JOBS_FAILED",
    "ERROR_MISSING_RUN_ID",
    "MATCH_JOBS_NAME",
    "build_match_jobs_tool",
    "build_production_match_tools",
]

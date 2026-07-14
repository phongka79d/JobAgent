"""Job-domain Agent tools (Plan 5 §7.6) — production tools four and five.

Registers via :func:`build_production_job_tools` / ``production_registry``:

* ``save_job`` — persistence-first ingest + direct sync; no approval
* ``query_jobs`` — read-only compact listing; default limit 10

Tool results are compact :class:`~app.schemas.tools.ToolResult` objects. Raw
JD text and embeddings never appear in arguments summaries, ToolResult data,
or logs. Both tools use Plan 3 ``(run_id, tool_call_id)`` replay via
:func:`~app.services.tool_execution.execute_tool`.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.jobs import JOB_PROCESSING_STATUS_FAILED
from app.db.session import get_session_factory
from app.graph.sync_job import AsyncGraphDriver
from app.graph.sync_shared import NEO4J_REBUILD_INSTRUCTION, NEO4J_SYNC_FAILED
from app.repositories import jobs as jobs_repo
from app.repositories.jobs import JobCompact, JobRepositoryError
from app.schemas.jobs import (
    JOB_INGEST_OUTCOME_RETRIED,
    JOB_INGEST_OUTCOME_RETURNED,
    QUERY_JOBS_DEFAULT_LIMIT,
    CompactJobToolRow,
    JobJdQuality,
    JobProcessingStatus,
    QueryJobsInput,
    QueryJobsResultData,
    SaveJobInput,
    SaveJobResultData,
)
from app.schemas.tools import ToolResult
from app.services.jd_extraction import StructuredJdInvoker
from app.services.jd_ingestion import (
    EmbeddingClient,
    JdIngestionError,
    JdIngestResult,
    JobSyncFn,
    UrlFetcher,
    ingest_raw_text,
    ingest_url,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.tool_execution import execute_tool

SAVE_JOB_NAME: str = "save_job"
QUERY_JOBS_NAME: str = "query_jobs"

ERROR_INVALID_JOB_INPUT: str = "INVALID_JOB_INPUT"
ERROR_MISSING_RUN_ID: str = "MISSING_RUN_ID"
ERROR_INVALID_QUERY: str = "INVALID_QUERY"
ERROR_JOB_INGESTION: str = "JOB_INGESTION_FAILED"


def _arguments_summary_save(
    *,
    url: str | None,
    text: str | None,
) -> dict[str, Any]:
    """Compact args summary: never include raw JD body."""
    has_url = isinstance(url, str) and url.strip() != ""
    has_text = isinstance(text, str) and text.strip() != ""
    if has_url and not has_text:
        return {"source": "url", "url": url.strip() if url else None}
    if has_text and not has_url:
        return {
            "source": "text",
            "text_length": len(text) if isinstance(text, str) else 0,
        }
    return {
        "source": "invalid",
        "has_url": has_url,
        "has_text": has_text,
    }


def _arguments_summary_query(args: QueryJobsInput) -> dict[str, Any]:
    return {
        "job_id": args.job_id,
        "processing_status": args.processing_status,
        "jd_quality": args.jd_quality,
        "limit": args.limit,
    }


def _compact_from_repo_row(row: JobCompact) -> CompactJobToolRow:
    created = row["created_at"]
    updated = row["updated_at"]
    quality = row["jd_quality"]
    return CompactJobToolRow(
        job_id=row["id"],
        title=row["title"],
        company=row["company"],
        source_url=row["source_url"],
        processing_status=cast(JobProcessingStatus, row["processing_status"]),
        jd_quality=cast(JobJdQuality | None, quality),
        failure_code=row["failure_code"],
        created_at=created.isoformat() if created is not None else None,
        updated_at=updated.isoformat() if updated is not None else None,
    )


async def _load_compact_for_job(
    factory: async_sessionmaker[AsyncSession],
    job_id: str,
) -> CompactJobToolRow | None:
    async with factory() as session:
        rows = await jobs_repo.list_compact(session, limit=1, job_id=job_id)
    if not rows:
        return None
    return _compact_from_repo_row(rows[0])


def _save_result_data(
    ingest: JdIngestResult,
    compact: CompactJobToolRow | None,
    *,
    sqlite_committed: bool,
) -> dict[str, Any]:
    title = compact.title if compact is not None else None
    company = compact.company if compact is not None else None
    payload = SaveJobResultData(
        job_id=ingest.job_id,
        title=title,
        company=company,
        source_url=ingest.source_url,
        processing_status=cast(JobProcessingStatus, ingest.processing_status),
        jd_quality=cast(JobJdQuality | None, ingest.jd_quality),
        outcome=ingest.outcome,
        sqlite_committed=sqlite_committed,
        sync_ok=ingest.sync_ok,
        failure_code=ingest.failure_code,
        rebuild_instruction=ingest.rebuild_instruction,
        paste_instruction=ingest.paste_instruction,
    )
    return payload.model_dump(mode="json")


def _tool_result_from_ingest(
    ingest: JdIngestResult,
    compact: CompactJobToolRow | None,
) -> ToolResult:
    """Map ingestion outcome to exact ToolResult success/failure coupling."""
    data = _save_result_data(ingest, compact, sqlite_committed=True)

    # Post-commit graph failure: SQLite truth stays processed; tool fails.
    if ingest.sync_ok is False:
        code = ingest.sync_code or NEO4J_SYNC_FAILED
        rebuild = ingest.rebuild_instruction or NEO4J_REBUILD_INSTRUCTION
        data["rebuild_instruction"] = rebuild
        data["sync_ok"] = False
        return ToolResult(
            ok=False,
            code=code,
            summary=(
                "Job saved to SQLite but Neo4j sync failed; "
                "run local graph rebuild to reproject from SQLite"
            ),
            data=data,
        )

    if ingest.processing_status == JOB_PROCESSING_STATUS_FAILED:
        code = ingest.failure_code or ERROR_JOB_INGESTION
        summary = f"Job ingestion failed ({code})"
        if ingest.paste_instruction:
            summary = f"{summary}. {ingest.paste_instruction}"
        return ToolResult(
            ok=False,
            code=code,
            summary=summary,
            data=data,
        )

    outcome = ingest.outcome
    if outcome == JOB_INGEST_OUTCOME_RETURNED:
        summary = "Returned existing job for exact content match"
    elif outcome == JOB_INGEST_OUTCOME_RETRIED:
        summary = "Retried failed job in place after exact content match"
    else:
        summary = "Saved job description"
    if ingest.jd_quality is not None:
        summary = f"{summary} ({ingest.processing_status}/{ingest.jd_quality})"
    else:
        summary = f"{summary} ({ingest.processing_status})"

    return ToolResult(ok=True, code=None, summary=summary, data=data)


def build_save_job_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    invoker: StructuredJdInvoker | None = None,
    normalizer: SkillNormalizer | None = None,
    embedding_client: EmbeddingClient | None = None,
    url_fetcher: UrlFetcher | None = None,
    driver: AsyncGraphDriver | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> Any:
    """Build compact ``save_job`` LangChain tool (no approval; any auth state).

    Dependencies are closed over and absent from the LLM-visible schema.
    """

    @tool(SAVE_JOB_NAME)
    async def save_job_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        url: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Save a public job URL or pasted JD text.

        Provide exactly one of ``url`` or ``text``. No profile or approval is
        required. Returns compact job identity/status/outcome only (never raw JD).
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
                summary="save_job requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="save_job requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        args_summary = _arguments_summary_save(url=url, text=text)

        async def _invoke() -> ToolResult:
            try:
                SaveJobInput.model_validate({"url": url, "text": text})
            except ValidationError:
                return ToolResult(
                    ok=False,
                    code=ERROR_INVALID_JOB_INPUT,
                    summary=(
                        "save_job requires exactly one of non-empty url or text"
                    ),
                    data={"has_url": url is not None, "has_text": text is not None},
                )

            from app.services.jd_extraction import ShopAIKeyStructuredJdInvoker

            inv: StructuredJdInvoker = (
                invoker
                if invoker is not None
                else ShopAIKeyStructuredJdInvoker()
            )
            norm = (
                normalizer
                if normalizer is not None
                else SkillNormalizer.production()
            )

            try:
                if isinstance(url, str) and url.strip() != "":
                    ingest = await ingest_url(
                        url.strip(),
                        invoker=inv,
                        normalizer=norm,
                        embedding_client=embedding_client,
                        session_factory=factory,
                        url_fetcher=url_fetcher,
                        graph_driver=driver,
                        job_sync_fn=job_sync_fn,
                    )
                else:
                    assert isinstance(text, str)
                    ingest = await ingest_raw_text(
                        text,
                        invoker=inv,
                        normalizer=norm,
                        embedding_client=embedding_client,
                        session_factory=factory,
                        graph_driver=driver,
                        job_sync_fn=job_sync_fn,
                    )
            except JdIngestionError as exc:
                return ToolResult(
                    ok=False,
                    code=exc.code,
                    summary=exc.message,
                    data={"sqlite_committed": False},
                )

            compact = await _load_compact_for_job(factory, ingest.job_id)
            return _tool_result_from_ingest(ingest, compact)

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=SAVE_JOB_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
        )
        return result.model_dump(mode="json")

    return save_job_tool


def build_query_jobs_tool(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> Any:
    """Build read-only compact ``query_jobs`` LangChain tool."""

    @tool(QUERY_JOBS_NAME)
    async def query_jobs_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        job_id: str | None = None,
        processing_status: str | None = None,
        jd_quality: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List compact saved jobs (newest first).

        Optional filters: ``job_id``, ``processing_status``, ``jd_quality``.
        ``limit`` defaults to 10 and must be in 1..50. Never returns raw JD or
        embeddings.
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
                summary="query_jobs requires run_id in graph state",
                data=None,
            ).model_dump(mode="json")

        if not isinstance(tool_call_id, str) or tool_call_id.strip() == "":
            return ToolResult(
                ok=False,
                code=ERROR_MISSING_RUN_ID,
                summary="query_jobs requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        # Default omitted limit to exactly 10 before validation.
        effective_limit = (
            QUERY_JOBS_DEFAULT_LIMIT if limit is None else limit
        )
        try:
            args = QueryJobsInput.model_validate(
                {
                    "job_id": job_id,
                    "processing_status": processing_status,
                    "jd_quality": jd_quality,
                    "limit": effective_limit,
                }
            )
        except ValidationError as exc:
            return ToolResult(
                ok=False,
                code=ERROR_INVALID_QUERY,
                summary=f"query_jobs input invalid: {exc.errors()[0]['msg']}",
                data=None,
            ).model_dump(mode="json")

        args_summary = _arguments_summary_query(args)

        async def _invoke() -> ToolResult:
            try:
                async with factory() as session:
                    rows = await jobs_repo.list_compact(
                        session,
                        limit=args.limit,
                        job_id=args.job_id,
                        processing_status=args.processing_status,
                        jd_quality=args.jd_quality,
                    )
            except JobRepositoryError as exc:
                return ToolResult(
                    ok=False,
                    code=ERROR_INVALID_QUERY,
                    summary=str(exc),
                    data=None,
                )

            compact_rows = [_compact_from_repo_row(r) for r in rows]
            data = QueryJobsResultData(
                jobs=compact_rows,
                count=len(compact_rows),
                limit=args.limit,
            )
            return ToolResult(
                ok=True,
                code=None,
                summary=f"Found {len(compact_rows)} job(s)",
                data=data.model_dump(mode="json"),
            )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=QUERY_JOBS_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
        )
        return result.model_dump(mode="json")

    return query_jobs_tool


def build_production_job_tools(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    invoker: StructuredJdInvoker | None = None,
    normalizer: SkillNormalizer | None = None,
    embedding_client: EmbeddingClient | None = None,
    url_fetcher: UrlFetcher | None = None,
    driver: AsyncGraphDriver | None = None,
    job_sync_fn: JobSyncFn | None = None,
) -> list[Any]:
    """Build exactly the two Plan 5 Job tools (matching tools stay absent)."""
    return [
        build_save_job_tool(
            session_factory=session_factory,
            invoker=invoker,
            normalizer=normalizer,
            embedding_client=embedding_client,
            url_fetcher=url_fetcher,
            driver=driver,
            job_sync_fn=job_sync_fn,
        ),
        build_query_jobs_tool(session_factory=session_factory),
    ]


__all__ = [
    "ERROR_INVALID_JOB_INPUT",
    "ERROR_INVALID_QUERY",
    "ERROR_JOB_INGESTION",
    "ERROR_MISSING_RUN_ID",
    "QUERY_JOBS_NAME",
    "SAVE_JOB_NAME",
    "build_production_job_tools",
    "build_query_jobs_tool",
    "build_save_job_tool",
]

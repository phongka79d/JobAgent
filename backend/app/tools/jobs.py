"""Job-domain Agent tools (Plan 5 §7.6) — production tools four and five.

Registers via :func:`build_production_job_tools` / ``production_registry``:

* ``save_job`` — persistence-first ingest + direct sync; current-message mode
  interrupts for confirmation before ingestion side effects
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
from langgraph.types import interrupt
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
    SAVE_JOB_SOURCE_CURRENT_MESSAGE,
    CompactJobToolRow,
    JobJdQuality,
    JobProcessingStatus,
    QueryJobsInput,
    QueryJobsResultData,
    SaveJobInput,
    SaveJobResultData,
    save_job_provider_parameters,
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
from app.services.job_save_confirmation import (
    InitiatingMessage,
    SourceLookupFailure,
    build_cancellation_tool_result,
    build_job_save_confirmation_projection,
    message_has_clear_opt_out,
    resolve_initiating_user_message,
)
from app.services.skill_normalization import SkillNormalizer
from app.services.tool_execution import execute_tool

SAVE_JOB_NAME: str = "save_job"
QUERY_JOBS_NAME: str = "query_jobs"

# Shared description for runtime BaseTool and provider-visible OpenAI definition.
SAVE_JOB_DESCRIPTION: str = (
    "Save a public job URL, pasted JD text, or the current user message. "
    "Provide exactly one of url, text, or source='current_message'. "
    "Omit unused properties entirely; never send empty strings for unused "
    "fields. Current-message mode pauses for confirmation before ingestion; "
    "optional preview is presentation-only. Returns compact status only, "
    "never raw JD."
)

ERROR_INVALID_JOB_INPUT: str = "INVALID_JOB_INPUT"
ERROR_MISSING_RUN_ID: str = "MISSING_RUN_ID"
ERROR_INVALID_QUERY: str = "INVALID_QUERY"
ERROR_JOB_INGESTION: str = "JOB_INGESTION_FAILED"
ERROR_INVALID_APPROVAL_ACTION: str = "INVALID_APPROVAL_ACTION"

ACTION_SAVE_JOB: str = "save_job"
ACTION_CANCEL_SAVE_JOB: str = "cancel_save_job"


def _arguments_summary_save(
    *,
    url: str | None,
    text: str | None,
    source: str | None = None,
) -> dict[str, Any]:
    """Compact args summary: never include raw JD body or preview guesses."""
    has_url = isinstance(url, str) and url.strip() != ""
    has_text = isinstance(text, str) and text.strip() != ""
    has_source = source == SAVE_JOB_SOURCE_CURRENT_MESSAGE
    if has_source and not has_url and not has_text:
        return {"source": SAVE_JOB_SOURCE_CURRENT_MESSAGE}
    if has_url and not has_text and not has_source:
        return {"source": "url", "url": url.strip() if url else None}
    if has_text and not has_url and not has_source:
        return {
            "source": "text",
            "text_length": len(text) if isinstance(text, str) else 0,
        }
    return {
        "source": "invalid",
        "has_url": has_url,
        "has_text": has_text,
        "has_source": has_source,
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


def _is_current_message_only(
    *,
    url: str | None,
    text: str | None,
    source: str | None,
) -> bool:
    has_url = isinstance(url, str) and url.strip() != ""
    has_text = isinstance(text, str) and text.strip() != ""
    return (
        source == SAVE_JOB_SOURCE_CURRENT_MESSAGE
        and not has_url
        and not has_text
    )


async def _resolve_opt_out(
    factory: async_sessionmaker[AsyncSession],
    run_id: str,
) -> ToolResult | None:
    """Return cancellation when the initiating message has a clear opt-out.

    Lookup failure is not an opt-out (URL/text may still proceed; current-message
    mode handles lookup failures on its own path).
    """
    async with factory() as session:
        resolved = await resolve_initiating_user_message(session, run_id)
    if isinstance(resolved, SourceLookupFailure):
        return None
    if message_has_clear_opt_out(resolved.content):
        return build_cancellation_tool_result()
    return None


async def _ingest_with_deps(
    *,
    factory: async_sessionmaker[AsyncSession],
    url: str | None,
    text: str | None,
    invoker: StructuredJdInvoker | None,
    normalizer: SkillNormalizer | None,
    embedding_client: EmbeddingClient | None,
    url_fetcher: UrlFetcher | None,
    driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> ToolResult:
    """Construct provider/ingestion deps and run direct URL or text ingest."""
    from app.services.jd_extraction import ShopAIKeyStructuredJdInvoker

    inv: StructuredJdInvoker = (
        invoker if invoker is not None else ShopAIKeyStructuredJdInvoker()
    )
    norm = (
        normalizer if normalizer is not None else SkillNormalizer.production()
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


async def _ingest_current_message_content(
    *,
    factory: async_sessionmaker[AsyncSession],
    content: str,
    invoker: StructuredJdInvoker | None,
    normalizer: SkillNormalizer | None,
    embedding_client: EmbeddingClient | None,
    driver: AsyncGraphDriver | None,
    job_sync_fn: JobSyncFn | None,
) -> ToolResult:
    """Construct deps only after confirmation and ingest exact durable text."""
    from app.services.jd_extraction import ShopAIKeyStructuredJdInvoker

    inv: StructuredJdInvoker = (
        invoker if invoker is not None else ShopAIKeyStructuredJdInvoker()
    )
    norm = (
        normalizer if normalizer is not None else SkillNormalizer.production()
    )

    try:
        ingest = await ingest_raw_text(
            content,
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


def save_job_openai_tool_schema() -> dict[str, Any]:
    """OpenAI-format provider-visible ``save_job`` definition (model binding only).

    Not the runtime ToolNode ``BaseTool``. Injected ``tool_call_id``/``state`` are
    omitted; ``SaveJobInput`` remains the dispatch-time authority.
    """
    return {
        "type": "function",
        "function": {
            "name": SAVE_JOB_NAME,
            "description": SAVE_JOB_DESCRIPTION,
            "parameters": save_job_provider_parameters(),
        },
    }


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
    """Build compact ``save_job`` LangChain tool (URL/text direct; CM interrupt).

    Dependencies are closed over and absent from the LLM-visible schema.
    Current-message mode enables running re-entry for the same identity.
    """

    @tool(SAVE_JOB_NAME, description=SAVE_JOB_DESCRIPTION)
    async def save_job_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        url: str | None = None,
        text: str | None = None,
        source: str | None = None,
        preview: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a public job URL, pasted JD text, or the current user message.

        Provide exactly one of ``url``, ``text``, or ``source='current_message'``.
        Current-message mode pauses for confirmation before ingestion. Optional
        ``preview`` is presentation-only and only valid with current_message.
        Returns compact job identity/status/outcome only (never raw JD).
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

        args_summary = _arguments_summary_save(
            url=url, text=text, source=source
        )
        allow_reentry = _is_current_message_only(
            url=url, text=text, source=source
        )

        async def _invoke() -> ToolResult:
            try:
                validated = SaveJobInput.model_validate(
                    {
                        "url": url,
                        "text": text,
                        "source": source,
                        "preview": preview,
                    }
                )
            except ValidationError:
                return ToolResult(
                    ok=False,
                    code=ERROR_INVALID_JOB_INPUT,
                    summary=(
                        "save_job requires exactly one of non-empty url, text, "
                        "or source='current_message'"
                    ),
                    data={
                        "has_url": url is not None,
                        "has_text": text is not None,
                        "has_source": source is not None,
                    },
                )

            if validated.source == SAVE_JOB_SOURCE_CURRENT_MESSAGE:
                # One durable lookup feeds opt-out, card, and re-entry ingest.
                # Initial path: one pre-interrupt read. LangGraph re-entry:
                # one fresh read (no third post-decision reload).
                async with factory() as session:
                    resolved = await resolve_initiating_user_message(
                        session, run_id
                    )
                if isinstance(resolved, SourceLookupFailure):
                    return ToolResult(
                        ok=False,
                        code=resolved.code,
                        summary=resolved.summary,
                        data=None,
                    )
                assert isinstance(resolved, InitiatingMessage)
                if message_has_clear_opt_out(resolved.content):
                    return build_cancellation_tool_result()

                decision = interrupt(
                    build_job_save_confirmation_projection(
                        tool_call_id=tool_call_id,
                        content=resolved.content,
                        preview=validated.preview,
                    )
                )
                action = decision if isinstance(decision, str) else str(decision)

                if action == ACTION_CANCEL_SAVE_JOB:
                    # No provider/normalizer/embedding/graph dependency on cancel.
                    return build_cancellation_tool_result()

                if action != ACTION_SAVE_JOB:
                    return ToolResult(
                        ok=False,
                        code=ERROR_INVALID_APPROVAL_ACTION,
                        summary=f"unsupported approval action {action!r}",
                        data={"action": action},
                    )

                # Re-entry's single fresh lookup supplies ingest content.
                return await _ingest_current_message_content(
                    factory=factory,
                    content=resolved.content,
                    invoker=invoker,
                    normalizer=normalizer,
                    embedding_client=embedding_client,
                    driver=driver,
                    job_sync_fn=job_sync_fn,
                )

            # Direct URL / text: shared opt-out then construct deps.
            opt_out = await _resolve_opt_out(factory, run_id)
            if opt_out is not None:
                return opt_out
            return await _ingest_with_deps(
                factory=factory,
                url=validated.url,
                text=validated.text,
                invoker=invoker,
                normalizer=normalizer,
                embedding_client=embedding_client,
                url_fetcher=url_fetcher,
                driver=driver,
                job_sync_fn=job_sync_fn,
            )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=SAVE_JOB_NAME,
            invoke=_invoke,
            arguments_summary_json=args_summary,
            session_factory=factory,
            allow_running_reentry=allow_reentry,
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
    "ACTION_CANCEL_SAVE_JOB",
    "ACTION_SAVE_JOB",
    "ERROR_INVALID_APPROVAL_ACTION",
    "ERROR_INVALID_JOB_INPUT",
    "ERROR_INVALID_QUERY",
    "ERROR_JOB_INGESTION",
    "ERROR_MISSING_RUN_ID",
    "QUERY_JOBS_NAME",
    "SAVE_JOB_DESCRIPTION",
    "SAVE_JOB_NAME",
    "build_production_job_tools",
    "build_query_jobs_tool",
    "build_save_job_tool",
    "save_job_openai_tool_schema",
]

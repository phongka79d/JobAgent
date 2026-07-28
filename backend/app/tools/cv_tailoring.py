"""Compact replay-safe Main-Agent entry to the bounded tailoring coordinator."""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from app.schemas.tools import ToolResult
from app.services.cv_tailoring import (
    JOB_NOT_SCORABLE,
    TAILORING_GROUNDING_FAILED,
    TailoringCoordinator,
    TailoringError,
)
from app.services.tool_execution import execute_tool

CREATE_TAILORED_CV_NAME = "create_tailored_cv"


def build_create_tailored_cv_tool(
    *, coordinator: TailoringCoordinator | None = None
) -> Any:
    """Build the one compact tailoring tool; sources resolve server-side."""

    active_coordinator = coordinator

    @tool(CREATE_TAILORED_CV_NAME)
    async def create_tailored_cv_tool(
        tool_call_id: Annotated[str, InjectedToolCallId],
        state: Annotated[dict[str, Any], InjectedState],
        instruction: Annotated[str, Field(max_length=4_000)] = "",
    ) -> dict[str, Any]:
        """Create a tailored CV for an explicit user request.

        Pass only the user's bounded tailoring instruction. The selected saved
        Job, approved Profile/CV, grounding evidence, template, and artifacts
        are resolved by the server. Never pass raw CV, JD, LaTeX, contacts,
        paths, or a Job ID in arguments.
        """
        nonlocal active_coordinator
        run_id = state.get("run_id") if isinstance(state, dict) else None
        profile_id = state.get("profile_id") if isinstance(state, dict) else None
        selected_job_id = (
            state.get("selected_job_id") if isinstance(state, dict) else None
        )
        if not isinstance(run_id, str) or not run_id.strip():
            return ToolResult(
                ok=False,
                code="MISSING_RUN_ID",
                summary="create_tailored_cv requires a durable run",
                data=None,
            ).model_dump(mode="json")
        if not isinstance(profile_id, str) or not profile_id.strip():
            return ToolResult(
                ok=False,
                code="PROFILE_NOT_READY",
                summary="A ready profile is required for CV tailoring",
                data=None,
            ).model_dump(mode="json")
        cleaned = instruction.strip() if isinstance(instruction, str) else ""
        if selected_job_id is None and not cleaned:
            return ToolResult(
                ok=False,
                code=JOB_NOT_SCORABLE,
                summary="Select a ready Job or provide a tailoring instruction",
                data=None,
            ).model_dump(mode="json")
        if not isinstance(tool_call_id, str) or not tool_call_id.strip():
            return ToolResult(
                ok=False,
                code="MISSING_RUN_ID",
                summary="create_tailored_cv requires tool_call_id",
                data=None,
            ).model_dump(mode="json")

        async def _invoke() -> ToolResult:
            nonlocal active_coordinator
            if active_coordinator is None:
                active_coordinator = TailoringCoordinator()
            try:
                launch = await active_coordinator.prepare_session(
                    profile_id=profile_id,
                    job_id=(
                        selected_job_id
                        if isinstance(selected_job_id, str)
                        else None
                    ),
                    instruction=cleaned,
                    parent_run_id=run_id,
                )
                terminal = None
                stream = active_coordinator.stream_initial_version(launch)
                try:
                    async for event in stream:
                        if event.event in {"run_completed", "run_failed"}:
                            terminal = event
                finally:
                    close = getattr(stream, "aclose", None)
                    if close is not None:
                        await close()
                if terminal is None or terminal.event != "run_completed":
                    code = (
                        terminal.payload.error_code
                        if terminal is not None and terminal.event == "run_failed"
                        else TAILORING_GROUNDING_FAILED
                    )
                    return ToolResult(
                        ok=False,
                        code=code,
                        summary="Tailored CV generation failed",
                        data=None,
                    )
                created = await active_coordinator.get_completed_version(launch)
                return ToolResult(
                    ok=True,
                    code=None,
                    summary="Tailored CV is ready",
                    data={
                        "outcome": created.outcome,
                        "session_id": str(created.session_id),
                        "version_id": str(created.version_id),
                        "status": "ready",
                        "currentness": "current",
                    },
                )
            except TailoringError as exc:
                return ToolResult(
                    ok=False,
                    code=exc.code,
                    summary=exc.message,
                    data=None,
                )
            except Exception:
                return ToolResult(
                    ok=False,
                    code=TAILORING_GROUNDING_FAILED,
                    summary="Tailored CV generation failed",
                    data=None,
                )

        result = await execute_tool(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name=CREATE_TAILORED_CV_NAME,
            display_label="Create tailored CV",
            invoke=_invoke,
            arguments_summary_json={
                "instruction_length": len(cleaned),
                "selected_job_present": selected_job_id is not None,
            },
        )
        return result.model_dump(mode="json")

    return create_tailored_cv_tool


__all__ = ["CREATE_TAILORED_CV_NAME", "build_create_tailored_cv_tool"]

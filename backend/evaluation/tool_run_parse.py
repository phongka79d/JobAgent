"""Parse tool-selection run envelopes with production argument contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from app.tools.candidate_context import CandidateContextInput
from app.tools.match_jobs import MatchJobsInput
from app.tools.profile_commit import CommitProfileDraftInput
from app.tools.profile_draft import ProposeProfileFromCvInput, ProposeProfileUpdateInput
from app.tools.query_jobs import QueryJobsInput
from app.tools.registry import PRODUCTION_TOOL_NAMES
from app.tools.save_job import SaveJobInput
from pydantic import BaseModel, ValidationError

from evaluation.dataset_contracts import assert_no_forbidden_fields

RUN_STATUSES: Final[frozenset[str]] = frozenset({"ok", "failure", "invalid", "missing"})

_TOOL_ARG_SCHEMAS: Final[Mapping[str, type[BaseModel]]] = {
    "get_candidate_context": CandidateContextInput,
    "propose_profile_from_cv": ProposeProfileFromCvInput,
    "propose_profile_update": ProposeProfileUpdateInput,
    "commit_profile_draft": CommitProfileDraftInput,
    "save_job": SaveJobInput,
    "query_jobs": QueryJobsInput,
    "match_jobs": MatchJobsInput,
}


class ToolSelectionRunnerError(ValueError):
    """Raised when tool-selection evaluation inputs are invalid."""


@dataclass(frozen=True, slots=True)
class ToolScenarioRun:
    scenario_id: str
    selected_tools: tuple[str, ...]
    arguments_valid: bool
    outcome: str
    unauthorized_profile_commit: bool
    pii_leak_to_adapter: bool
    false_success_after_failure: bool
    first_sse_event_seconds: float
    status: str
    tool_arguments: Mapping[str, Mapping[str, Any]]


def validate_tool_arguments(
    tool_name: str,
    arguments: Mapping[str, Any] | None,
) -> bool:
    name = tool_name.strip()
    if name not in PRODUCTION_TOOL_NAMES:
        return False
    schema = _TOOL_ARG_SCHEMAS.get(name)
    if schema is None:
        return False
    payload: Mapping[str, Any] = {} if arguments is None else arguments
    try:
        schema.model_validate(dict(payload))
    except ValidationError:
        return False
    return True


def _as_tool_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ToolSelectionRunnerError(f"{field} must be a list of strings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ToolSelectionRunnerError(f"{field} items must be strings")
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _as_bool(value: object, *, field: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolSelectionRunnerError(f"{field} must be a boolean")
    return value


def _as_nonneg_float(value: object, *, field: str, default: float = 0.0) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ToolSelectionRunnerError(f"{field} must be a number")
    number = float(value)
    if number < 0.0 or number != number or number in (float("inf"), float("-inf")):
        raise ToolSelectionRunnerError(f"{field} must be finite and >= 0")
    return number


def parse_tool_scenario_runs(
    payload: Mapping[str, Any],
) -> dict[str, ToolScenarioRun]:
    assert_no_forbidden_fields(payload)
    raw_items = payload.get("runs")
    if not isinstance(raw_items, list):
        raise ToolSelectionRunnerError("runs must be a list")
    parsed: dict[str, ToolScenarioRun] = {}
    for index, entry in enumerate(raw_items):
        if not isinstance(entry, Mapping):
            raise ToolSelectionRunnerError(f"runs[{index}] must be an object")
        assert_no_forbidden_fields(entry, path=f"$.runs[{index}]")
        scenario_id = entry.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ToolSelectionRunnerError(f"runs[{index}].scenario_id required")
        key = scenario_id.strip()
        if key in parsed:
            raise ToolSelectionRunnerError(f"duplicate scenario_id {key!r}")
        status_raw = entry.get("status", "ok")
        if not isinstance(status_raw, str) or status_raw not in RUN_STATUSES:
            raise ToolSelectionRunnerError(
                f"runs[{index}].status must be one of "
                + ", ".join(sorted(RUN_STATUSES))
            )
        selected = _as_tool_list(entry.get("selected_tools"), field="selected_tools")
        tool_args_raw = entry.get("tool_arguments") or {}
        if not isinstance(tool_args_raw, Mapping):
            raise ToolSelectionRunnerError(
                f"runs[{index}].tool_arguments must be an object"
            )
        tool_arguments: dict[str, Mapping[str, Any]] = {}
        for tool_name, args in tool_args_raw.items():
            if not isinstance(tool_name, str):
                raise ToolSelectionRunnerError("tool_arguments keys must be strings")
            if not isinstance(args, Mapping):
                raise ToolSelectionRunnerError(
                    f"tool_arguments[{tool_name!r}] must be an object"
                )
            tool_arguments[tool_name.strip()] = dict(args)

        if "arguments_valid" in entry:
            arguments_valid = _as_bool(
                entry.get("arguments_valid"), field="arguments_valid"
            )
        else:
            arguments_valid = all(
                validate_tool_arguments(name, tool_arguments.get(name))
                for name in selected
            )

        outcome = entry.get("outcome", "")
        if not isinstance(outcome, str):
            raise ToolSelectionRunnerError(f"runs[{index}].outcome must be a string")

        parsed[key] = ToolScenarioRun(
            scenario_id=key,
            selected_tools=tuple(selected),
            arguments_valid=arguments_valid,
            outcome=outcome.strip(),
            unauthorized_profile_commit=_as_bool(
                entry.get("unauthorized_profile_commit"),
                field="unauthorized_profile_commit",
            ),
            pii_leak_to_adapter=_as_bool(
                entry.get("pii_leak_to_adapter"),
                field="pii_leak_to_adapter",
            ),
            false_success_after_failure=_as_bool(
                entry.get("false_success_after_failure"),
                field="false_success_after_failure",
            ),
            first_sse_event_seconds=_as_nonneg_float(
                entry.get("first_sse_event_seconds"),
                field="first_sse_event_seconds",
            ),
            status=status_raw,
            tool_arguments=tool_arguments,
        )
    return parsed

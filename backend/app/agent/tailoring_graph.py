"""Fixed, bounded CV-tailoring graph with one shared repair budget."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field, field_validator

from app.adapters.shopaikey_chat import build_shopaikey_chat
from app.schemas.common import StrictModelConfig
from app.schemas.cv_tailoring import (
    TailoredCVContent,
    TailoredFactEvidence,
    TailoredPatchSet,
    TailoredSection,
)
from app.services.cv_tailoring_guard import guard_tailored_patch
from app.services.provider_retry import invoke_with_provider_retry

SELECT_SECTIONS_NODE = "select_sections"
LOAD_SELECTED_SECTIONS_NODE = "load_selected_sections"
REWRITE_SECTIONS_NODE = "rewrite_sections"
GROUND_PATCH_NODE = "ground_patch"
REPAIR_ONCE_NODE = "repair_once"

TAILORING_GRAPH_NODE_NAMES = frozenset(
    {
        SELECT_SECTIONS_NODE,
        LOAD_SELECTED_SECTIONS_NODE,
        REWRITE_SECTIONS_NODE,
        GROUND_PATCH_NODE,
        REPAIR_ONCE_NODE,
    }
)
TAILORING_GROUNDING_FAILED = "TAILORING_GROUNDING_FAILED"

_SELECTION_SYSTEM = (
    "Select the CV section IDs relevant to the structured role context and "
    "bounded user instruction. Return only the strict structured response."
)
_REWRITE_SYSTEM = (
    "Rewrite only the supplied selected CV sections using only their supplied "
    "source facts. Preserve section scope and cite source_fact_ids for every "
    "non-empty output field. Return only the strict structured response."
)
_REPAIR_SYSTEM = (
    "Repair the prior structured patch once. Use only the supplied selected "
    "sections, source facts, prior patch, and sanitized issue code/path pairs."
)
_SUPPORT_SYSTEM = (
    "Decide whether the output assertion is supported by the cited evidence. "
    "Return only the strict structured response."
)


class TailoringSectionSelection(BaseModel):
    model_config = StrictModelConfig

    section_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("section_ids")
    @classmethod
    def section_ids_are_nonempty_unique(cls, value: list[str]) -> list[str]:
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("section_ids entries must be non-empty")
        if len(value) != len(set(value)):
            raise ValueError("section_ids must be unique")
        return value


class _SemanticSupportResult(BaseModel):
    model_config = StrictModelConfig

    supported: bool


class TailoringAgentState(TypedDict):
    run_id: str
    instruction: str
    job_context: dict[str, Any] | None
    outline: list[dict[str, Any]]
    requested_section_ids: list[str]
    selected_section_ids: list[str]
    selected_sections: list[dict[str, Any]]
    fact_bank: dict[str, dict[str, Any]]
    patch: dict[str, Any] | None
    repair_count: int
    issues: list[dict[str, str]]
    error: str | None


class TailoringStructuredInvoker(Protocol):
    def select_sections(
        self, messages: Sequence[Any]
    ) -> TailoringSectionSelection: ...

    def rewrite_sections(
        self, messages: Sequence[Any], *, is_repair: bool
    ) -> TailoredPatchSet: ...

    def supports(
        self, *, output_text: str, cited_evidence: Sequence[str]
    ) -> bool: ...


SelectedContextLoader = Callable[
    [Sequence[str]],
    tuple[list[TailoredSection], dict[str, TailoredFactEvidence]],
]


@dataclass(frozen=True, slots=True)
class TailoringGraphBundle:
    compiled: CompiledStateGraph[Any, Any, Any, Any]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _coerce_selection(value: Any) -> TailoringSectionSelection:
    if isinstance(value, TailoringSectionSelection):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    return TailoringSectionSelection.model_validate(value)


def _coerce_patch(value: Any) -> TailoredPatchSet:
    if isinstance(value, TailoredPatchSet):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    return TailoredPatchSet.model_validate(value)


class ShopAIKeyTailoringStructuredInvoker:
    """Strict ShopAIKey structured-output seam for the bounded graph."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model if model is not None else build_shopaikey_chat()
        self._selection = self._model.with_structured_output(
            TailoringSectionSelection,
            method="json_schema",
            strict=True,
        )
        self._rewrite = self._model.with_structured_output(
            TailoredPatchSet,
            method="json_schema",
            strict=True,
        )
        self._support = self._model.with_structured_output(
            _SemanticSupportResult,
            method="json_schema",
            strict=True,
        )

    def select_sections(
        self, messages: Sequence[Any]
    ) -> TailoringSectionSelection:
        result, _ = invoke_with_provider_retry(
            lambda: self._selection.invoke(list(messages))
        )
        return _coerce_selection(result)

    def rewrite_sections(
        self, messages: Sequence[Any], *, is_repair: bool
    ) -> TailoredPatchSet:
        del is_repair
        result, _ = invoke_with_provider_retry(
            lambda: self._rewrite.invoke(list(messages))
        )
        return _coerce_patch(result)

    def supports(
        self, *, output_text: str, cited_evidence: Sequence[str]
    ) -> bool:
        messages = [
            SystemMessage(content=_SUPPORT_SYSTEM),
            HumanMessage(
                content=_json(
                    {
                        "output_text": output_text,
                        "cited_evidence": list(cited_evidence),
                    }
                )
            ),
        ]
        result, _ = invoke_with_provider_retry(
            lambda: self._support.invoke(messages)
        )
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="python")
        return _SemanticSupportResult.model_validate(result).supported


def initial_tailoring_state(
    *,
    run_id: str,
    instruction: str,
    job_context: Mapping[str, Any] | None,
    outline: Sequence[Mapping[str, Any]],
    requested_section_ids: Sequence[str],
) -> TailoringAgentState:
    return TailoringAgentState(
        run_id=run_id,
        instruction=instruction,
        job_context=dict(job_context) if job_context is not None else None,
        outline=[dict(item) for item in outline],
        requested_section_ids=list(requested_section_ids),
        selected_section_ids=[],
        selected_sections=[],
        fact_bank={},
        patch=None,
        repair_count=0,
        issues=[],
        error=None,
    )


def build_tailoring_graph(
    *,
    invoker: TailoringStructuredInvoker,
    load_selected_context: SelectedContextLoader,
    parent: TailoredCVContent,
    approved_skill_labels: Sequence[str],
    checkpointer: Any | None = None,
) -> TailoringGraphBundle:
    """Compile the five-node graph; dependencies stay in server-owned closures."""

    def select_sections(state: TailoringAgentState) -> dict[str, Any]:
        messages = [
            SystemMessage(content=_SELECTION_SYSTEM),
            HumanMessage(
                content=_json(
                    {
                        "instruction": state["instruction"],
                        "job_context": state["job_context"],
                        "outline": state["outline"],
                    }
                )
            ),
        ]
        try:
            selected = invoker.select_sections(messages).section_ids
        except Exception:
            return {"error": TAILORING_GROUNDING_FAILED}
        requested = state["requested_section_ids"]
        if requested and selected != requested:
            return {"error": TAILORING_GROUNDING_FAILED}
        outline_ids = [item.get("id") for item in state["outline"]]
        if any(section_id not in outline_ids for section_id in selected):
            return {"error": TAILORING_GROUNDING_FAILED}
        return {"selected_section_ids": selected}

    def load_selected_sections(state: TailoringAgentState) -> dict[str, Any]:
        try:
            sections, facts = load_selected_context(
                state["selected_section_ids"]
            )
        except Exception:
            return {"error": TAILORING_GROUNDING_FAILED}
        return {
            "selected_sections": [
                section.model_dump(mode="json") for section in sections
            ],
            "fact_bank": {
                fact_id: evidence.model_dump(mode="json")
                for fact_id, evidence in facts.items()
            },
        }

    def rewrite_sections(state: TailoringAgentState) -> dict[str, Any]:
        messages = [
            SystemMessage(content=_REWRITE_SYSTEM),
            HumanMessage(
                content=_json(
                    {
                        "selected_sections": state["selected_sections"],
                        "fact_bank": state["fact_bank"],
                    }
                )
            ),
        ]
        try:
            patch = invoker.rewrite_sections(messages, is_repair=False)
        except Exception:
            return {
                "patch": None,
                "issues": [
                    {"code": "SCHEMA_VALIDATION_FAILED", "path": "patch"}
                ],
            }
        return {"patch": patch.model_dump(mode="json"), "issues": []}

    def ground_patch(state: TailoringAgentState) -> dict[str, Any]:
        raw_patch = state["patch"]
        if raw_patch is None:
            if state["repair_count"] > 0:
                return {"error": TAILORING_GROUNDING_FAILED}
            return {}
        try:
            patch = TailoredPatchSet.model_validate(raw_patch)
            facts = {
                fact_id: TailoredFactEvidence.model_validate(raw)
                for fact_id, raw in state["fact_bank"].items()
            }
            guarded, issues = guard_tailored_patch(
                patch,
                parent=parent,
                allowed_section_ids=state["selected_section_ids"],
                fact_bank=facts,
                approved_skill_labels=approved_skill_labels,
                semantic_checker=invoker,
            )
        except Exception:
            guarded = None
            issues = ()
        if guarded is not None:
            return {
                "patch": guarded.model_dump(mode="json"),
                "issues": [],
                "error": None,
            }
        sanitized = [
            {"code": issue.code, "path": issue.path} for issue in issues
        ] or [{"code": "SCHEMA_VALIDATION_FAILED", "path": "patch"}]
        if state["repair_count"] > 0:
            return {
                "issues": sanitized,
                "error": TAILORING_GROUNDING_FAILED,
            }
        return {"issues": sanitized}

    def repair_once(state: TailoringAgentState) -> dict[str, Any]:
        messages = [
            SystemMessage(content=_REPAIR_SYSTEM),
            HumanMessage(
                content=_json(
                    {
                        "selected_sections": state["selected_sections"],
                        "fact_bank": state["fact_bank"],
                        "prior_patch": state["patch"],
                        "issues": state["issues"],
                    }
                )
            ),
        ]
        try:
            patch = invoker.rewrite_sections(messages, is_repair=True)
        except Exception:
            return {
                "patch": None,
                "repair_count": 1,
                "issues": [
                    {"code": "SCHEMA_VALIDATION_FAILED", "path": "patch"}
                ],
            }
        return {
            "patch": patch.model_dump(mode="json"),
            "repair_count": 1,
            "issues": [],
        }

    def continue_or_end(state: TailoringAgentState) -> str:
        return END if state["error"] is not None else "continue"

    def after_ground(state: TailoringAgentState) -> str:
        if state["error"] is not None or not state["issues"]:
            return END
        return REPAIR_ONCE_NODE

    builder: StateGraph[
        TailoringAgentState, None, TailoringAgentState, TailoringAgentState
    ] = StateGraph(TailoringAgentState)
    builder.add_node(SELECT_SECTIONS_NODE, select_sections)
    builder.add_node(LOAD_SELECTED_SECTIONS_NODE, load_selected_sections)
    builder.add_node(REWRITE_SECTIONS_NODE, rewrite_sections)
    builder.add_node(GROUND_PATCH_NODE, ground_patch)
    builder.add_node(REPAIR_ONCE_NODE, repair_once)
    builder.add_edge(START, SELECT_SECTIONS_NODE)
    builder.add_conditional_edges(
        SELECT_SECTIONS_NODE,
        continue_or_end,
        {"continue": LOAD_SELECTED_SECTIONS_NODE, END: END},
    )
    builder.add_conditional_edges(
        LOAD_SELECTED_SECTIONS_NODE,
        continue_or_end,
        {"continue": REWRITE_SECTIONS_NODE, END: END},
    )
    builder.add_edge(REWRITE_SECTIONS_NODE, GROUND_PATCH_NODE)
    builder.add_conditional_edges(
        GROUND_PATCH_NODE,
        after_ground,
        {REPAIR_ONCE_NODE: REPAIR_ONCE_NODE, END: END},
    )
    builder.add_edge(REPAIR_ONCE_NODE, GROUND_PATCH_NODE)
    compiled = cast(
        CompiledStateGraph[Any, Any, Any, Any],
        builder.compile(checkpointer=checkpointer),
    )
    return TailoringGraphBundle(compiled=compiled)


__all__ = [
    "GROUND_PATCH_NODE",
    "LOAD_SELECTED_SECTIONS_NODE",
    "REPAIR_ONCE_NODE",
    "REWRITE_SECTIONS_NODE",
    "SELECT_SECTIONS_NODE",
    "ShopAIKeyTailoringStructuredInvoker",
    "TAILORING_GRAPH_NODE_NAMES",
    "TAILORING_GROUNDING_FAILED",
    "TailoringAgentState",
    "TailoringGraphBundle",
    "TailoringSectionSelection",
    "TailoringStructuredInvoker",
    "build_tailoring_graph",
    "initial_tailoring_state",
]

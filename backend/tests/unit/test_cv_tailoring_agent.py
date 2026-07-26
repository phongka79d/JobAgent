from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.schemas.cv_tailoring import (
    TailoredItemPatch,
    TailoredPatchSet,
    TailoredSectionPatch,
)
from app.services.cv_tailoring_projection import (
    project_tailoring_baseline,
    select_section_context,
)

from tests.unit.test_cv_tailoring_projection import _document, _profile


def _baseline():
    return project_tailoring_baseline(
        _document(), profile=_profile(), source_hash="revision-a"
    )


def _patch(section_id: str, *, unknown_fact: bool = False) -> TailoredPatchSet:
    baseline = _baseline()
    section = next(item for item in baseline.content.sections if item.id == section_id)
    items: list[TailoredItemPatch] = []
    for source in section.items:
        body = source.body.model_copy(deep=True)
        if unknown_fact:
            body.source_fact_ids = ["sf_unknown"]
        items.append(
            TailoredItemPatch(
                source_entry_id=source.source_entry_id,
                title=source.title,
                subtitle=source.subtitle,
                date_text=source.date_text,
                location=source.location,
                body=body,
                bullets=source.bullets,
                attributes=source.attributes,
            )
        )
    return TailoredPatchSet(
        sections=[TailoredSectionPatch(section_id=section_id, items=items)]
    )


@dataclass
class RecordingInvoker:
    patches: list[TailoredPatchSet]
    selection_calls: list[Sequence[Any]] = field(default_factory=list)
    rewrite_calls: list[tuple[Sequence[Any], bool]] = field(default_factory=list)

    def select_sections(self, messages: Sequence[Any]):
        from app.agent.tailoring_graph import TailoringSectionSelection

        self.selection_calls.append(messages)
        return TailoringSectionSelection(section_ids=["summary"])

    def rewrite_sections(
        self, messages: Sequence[Any], *, is_repair: bool
    ) -> TailoredPatchSet:
        self.rewrite_calls.append((messages, is_repair))
        return self.patches.pop(0)

    def supports(
        self, *, output_text: str, cited_evidence: Sequence[str]
    ) -> bool:
        del output_text, cited_evidence
        return True


def _messages_text(messages: Sequence[Any]) -> str:
    return "\n".join(str(getattr(message, "content", message)) for message in messages)


def _build(invoker: RecordingInvoker):
    from app.agent.tailoring_graph import build_tailoring_graph

    baseline = _baseline()

    def load_selected(section_ids: Sequence[str]):
        return select_section_context(baseline, section_ids=section_ids)

    return build_tailoring_graph(
        invoker=invoker,
        load_selected_context=load_selected,
        parent=baseline.content,
        approved_skill_labels=baseline.approved_skill_labels,
    )


def _state(*, requested_section_ids: list[str] | None = None):
    from app.agent.tailoring_graph import initial_tailoring_state

    return initial_tailoring_state(
        run_id="00000000-0000-4000-8000-000000000001",
        instruction="Prioritize the structured role requirements",
        job_context={
            "title": "Structured role",
            "summary": "JOB_STRUCTURED_SENTINEL",
        },
        outline=[
            {
                "id": "summary",
                "ordinal": 0,
                "heading": "Summary",
                "kind": "summary",
                "entry_count": 1,
            },
            {
                "id": "experience",
                "ordinal": 1,
                "heading": "Experience",
                "kind": "experience",
                "entry_count": 1,
            },
        ],
        requested_section_ids=requested_section_ids or [],
    )


def test_graph_has_exact_fixed_nodes_and_no_tool_or_spawn_topology() -> None:
    invoker = RecordingInvoker(patches=[_patch("summary")])
    bundle = _build(invoker)

    node_names = set(bundle.compiled.get_graph().nodes) - {"__start__", "__end__"}

    assert node_names == {
        "select_sections",
        "load_selected_sections",
        "rewrite_sections",
        "ground_patch",
        "repair_once",
    }
    assert "tools" not in node_names
    assert "main_agent" not in node_names
    assert "spawn" not in node_names


def test_prompts_are_split_by_selection_and_selected_source_context() -> None:
    invoker = RecordingInvoker(patches=[_patch("summary")])
    result = _build(invoker).compiled.invoke(_state())

    assert result["error"] is None
    assert result["selected_section_ids"] == ["summary"]
    assert len(invoker.selection_calls) == 1
    assert len(invoker.rewrite_calls) == 1

    selection_text = _messages_text(invoker.selection_calls[0])
    rewrite_text = _messages_text(invoker.rewrite_calls[0][0])
    assert "JOB_STRUCTURED_SENTINEL" in selection_text
    assert "Prioritize the structured role requirements" in selection_text
    assert "Summary" in selection_text and "Experience" in selection_text

    assert "JOB_STRUCTURED_SENTINEL" not in rewrite_text
    assert "Prioritize the structured role requirements" not in rewrite_text
    assert "Synthetic Candidate" not in rewrite_text
    assert "+84900000000" not in rewrite_text
    assert "experience" not in rewrite_text.casefold()
    assert "REFERENCE_ONLY_SENTINEL_7429" not in selection_text + rewrite_text
    assert "RAW_JOB_SENTINEL" not in selection_text + rewrite_text
    assert "SERVER_PATH_SENTINEL" not in selection_text + rewrite_text


def test_requested_scope_cannot_be_widened_by_selection() -> None:
    invoker = RecordingInvoker(patches=[_patch("summary")])

    result = _build(invoker).compiled.invoke(
        _state(requested_section_ids=["experience"])
    )

    assert result["error"] == "TAILORING_GROUNDING_FAILED"
    assert invoker.rewrite_calls == []


def test_one_grounding_failure_gets_one_shared_repair() -> None:
    invoker = RecordingInvoker(
        patches=[_patch("summary", unknown_fact=True), _patch("summary")]
    )

    result = _build(invoker).compiled.invoke(_state())

    assert result["error"] is None
    assert result["repair_count"] == 1
    assert [is_repair for _, is_repair in invoker.rewrite_calls] == [False, True]
    repair_text = _messages_text(invoker.rewrite_calls[1][0])
    assert "UNKNOWN_FACT" in repair_text


def test_second_grounding_failure_stops_without_a_second_repair() -> None:
    invoker = RecordingInvoker(
        patches=[
            _patch("summary", unknown_fact=True),
            _patch("summary", unknown_fact=True),
        ]
    )

    result = _build(invoker).compiled.invoke(_state())

    assert result["error"] == "TAILORING_GROUNDING_FAILED"
    assert result["repair_count"] == 1
    assert len(invoker.rewrite_calls) == 2

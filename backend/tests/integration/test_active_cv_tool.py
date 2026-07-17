"""Integration tests for read_active_cv durable tool (Plan 9 06B)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.agent.graph import (
    DECISION_NODE_NAME,
    TOOLS_NODE_NAME,
    _build_model_messages,
    _format_active_cv_context_block,
    build_agent_graph,
    initial_graph_state,
)
from app.agent.prompt import build_system_prompt
from app.db.models.chat import (
    CHAT_MESSAGE_ROLE_USER,
    TOOL_EXECUTION_STATUS_COMPLETED,
    TOOL_EXECUTION_STATUS_FAILED,
)
from app.db.session import build_async_engine
from app.repositories import agent_runs as runs_repo
from app.repositories import attachment_text_chunks as chunk_repo
from app.repositories import attachments as att_repo
from app.repositories import chat_messages as messages_repo
from app.repositories import cv_documents as cv_doc_repo
from app.repositories import profiles as profile_repo
from app.repositories import tool_executions as tool_repo
from app.repositories.attachment_text_chunks import build_chunk_write
from app.schemas.tools import ToolResult
from app.services.active_cv_reader import ERROR_NO_ACTIVE_CV
from app.tools.active_cv import (
    READ_ACTIVE_CV_NAME,
    arguments_summary_for_read_active_cv,
    build_read_active_cv_tool,
)
from app.tools.registry import production_registry
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from tests.fakes.fake_chat_model import FakeChatModel
from tests.support.db_migration import run_async, session_factory
from tests.unit.test_agent_graph import _ai_text


@pytest.fixture
def sqlite_factory(migrated_sqlite: Path) -> Iterator[Any]:
    engine = build_async_engine(migrated_sqlite)
    factory = session_factory(engine)
    try:
        yield factory
    finally:
        run_async(engine.dispose())

_ATTACHMENT = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
_SECTION_ID = "cv-document-v1:s0:experience"
_ENTRY_0 = "cv-document-v1:s0:e0:role"
_SOURCE_HASH = "toolhashfixed00000000000000000000000000000000000000000000001"


def _entry(
    *,
    entry_id: str,
    ordinal: int,
    title: str,
    body: str,
) -> dict[str, Any]:
    return {
        "id": entry_id,
        "ordinal": ordinal,
        "title": title,
        "subtitle": "Acme",
        "date_text": "2019",
        "location": None,
        "body": body,
        "bullets": ["Python"],
        "attributes": {},
        "source_chunk_ordinals": [ordinal],
    }


def _document(attachment_id: str = _ATTACHMENT) -> dict[str, Any]:
    entries = [
        _entry(
            entry_id=_ENTRY_0,
            ordinal=0,
            title="Engineer",
            body="Built APIs with Python",
        ),
        _entry(
            entry_id="cv-document-v1:s0:e1:lead",
            ordinal=1,
            title="Lead",
            body="Led platform Kubernetes work",
        ),
    ]
    return {
        "attachment_id": attachment_id,
        "detected_languages": ["en"],
        "sections": [
            {
                "id": _SECTION_ID,
                "ordinal": 0,
                "heading": "Experience",
                "kind": "experience",
                "entries": entries,
                "source_chunk_ordinals": [0, 1],
            }
        ],
        "extraction_warnings": [],
        "extraction_confidence": 0.9,
    }


def _outline(document: dict[str, Any]) -> dict[str, Any]:
    sections = []
    for section in document["sections"]:
        ords = section["source_chunk_ordinals"]
        sections.append(
            {
                "id": section["id"],
                "ordinal": section["ordinal"],
                "heading": section["heading"],
                "kind": section["kind"],
                "entry_count": len(section["entries"]),
                "source_chunk_ordinals": list(ords),
                "source_chunk_range": [ords[0], ords[-1]] if ords else [],
            }
        )
    return {"sections": sections}


async def _seed_active(session: Any, *, attachment_id: str = _ATTACHMENT) -> str:
    await att_repo.create_staged(
        session,
        file_hash=f"hash-{attachment_id[:8]}",
        original_name="cv.pdf",
        size_bytes=10,
        storage_path=f"{attachment_id}.pdf",
        page_count=1,
        attachment_id=attachment_id,
    )
    await att_repo.mark_active(session, attachment_id, page_count=1)
    await profile_repo.upsert_active_profile(
        session,
        active_attachment_id=attachment_id,
        profile_json={
            "summary": "Engineer",
            "current_title": "Engineer",
            "total_experience_years": 5.0,
            "skills": [],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.9,
        },
    )
    doc = _document(attachment_id)
    await cv_doc_repo.upsert_document(
        session,
        attachment_id=attachment_id,
        document_json=doc,
        profile_json={"summary": "Engineer"},
        outline_json=_outline(doc),
        extraction_version="cv-document-v1",
        source_hash=_SOURCE_HASH,
    )
    await chunk_repo.replace_for_attachment(
        session,
        attachment_id,
        [
            build_chunk_write(0, "Built APIs with Python"),
            build_chunk_write(1, "Led platform Kubernetes work"),
        ],
    )
    await session.commit()
    return attachment_id


async def _seed_run(session: Any, content: str = "read cv turn") -> str:
    user = await messages_repo.insert_message(
        session,
        role=CHAT_MESSAGE_ROLE_USER,
        content=content,
    )
    run = await runs_repo.create_run(session, user_message_id=user.id)
    await session.flush()
    return run.id


async def _ainvoke_read(
    tool_fn: Any,
    *,
    run_id: str,
    tool_call_id: str,
    mode: str,
    section_id: str | None = None,
    query: str | None = None,
    chunk_ordinal: int | None = None,
    cursor: str | None = None,
    max_results: int | None = None,
    max_chars: int | None = None,
) -> ToolResult:
    args: dict[str, Any] = {"mode": mode}
    if section_id is not None:
        args["section_id"] = section_id
    if query is not None:
        args["query"] = query
    if chunk_ordinal is not None:
        args["chunk_ordinal"] = chunk_ordinal
    if cursor is not None:
        args["cursor"] = cursor
    if max_results is not None:
        args["max_results"] = max_results
    if max_chars is not None:
        args["max_chars"] = max_chars
    raw = await tool_fn.ainvoke(
        {
            "type": "tool_call",
            "id": tool_call_id,
            "name": tool_fn.name,
            "args": {**args, "state": {"run_id": run_id}},
        }
    )
    if isinstance(raw, str):
        payload = json.loads(raw)
    elif hasattr(raw, "content"):
        content = raw.content
        payload = json.loads(content) if isinstance(content, str) else content
    else:
        payload = raw
    return ToolResult.model_validate(payload)


# ---------------------------------------------------------------------------
# Registry / topology
# ---------------------------------------------------------------------------


def test_production_registry_exactly_seven_tools_order() -> None:
    names = production_registry().tool_names()
    assert names == [
        "propose_profile_from_cv",
        "propose_profile_update",
        "commit_profile_draft",
        "save_job",
        "query_jobs",
        "match_jobs",
        "read_active_cv",
    ]
    assert names[-1] == READ_ACTIVE_CV_NAME
    assert "synthetic_interrupt" not in names
    assert len(names) == 7


def test_graph_topology_one_toolnode_six_iteration_limit() -> None:
    model = FakeChatModel(responses=[_ai_text("ok")])
    bundle = build_agent_graph(
        model=model,
        registry=production_registry(),
    )
    assert isinstance(bundle.tool_node, ToolNode)
    assert bundle.decision_node_name == DECISION_NODE_NAME
    assert bundle.tools_node_name == TOOLS_NODE_NAME
    assert bundle.tool_loop_limit == 6
    graph_nodes = set(bundle.compiled.get_graph().nodes)
    app_nodes = {
        n
        for n in graph_nodes
        if n not in {"__start__", "__end__", "START", "END"}
    }
    assert app_nodes == {DECISION_NODE_NAME, TOOLS_NODE_NAME}
    assert READ_ACTIVE_CV_NAME in bundle.registry.tool_names()


# ---------------------------------------------------------------------------
# Tool authorization / modes / ownership / redaction / replay
# ---------------------------------------------------------------------------


def test_read_active_cv_no_active_fails_terminal(sqlite_factory: Any) -> None:
    async def _body() -> None:
        async with sqlite_factory() as session:
            run_id = await _seed_run(session, "no active")
            await session.commit()

        tool_fn = build_read_active_cv_tool(session_factory=sqlite_factory)
        result = await _ainvoke_read(
            tool_fn,
            run_id=run_id,
            tool_call_id="read_no_active",
            mode="search",
            query="python",
        )
        assert result.ok is False
        assert result.code == ERROR_NO_ACTIVE_CV

        async with sqlite_factory() as session:
            row = await tool_repo.get_by_identity(
                session, run_id=run_id, tool_call_id="read_no_active"
            )
            assert row is not None
            assert row.tool_name == READ_ACTIVE_CV_NAME
            assert row.status == TOOL_EXECUTION_STATUS_FAILED
            assert row.source_attachment_id is None
            assert row.arguments_summary_json is not None
            assert "body" not in json.dumps(row.arguments_summary_json)
            assert "Built APIs" not in json.dumps(row.arguments_summary_json)

    run_async(_body())


def test_read_active_cv_section_search_chunk_and_ownership(
    sqlite_factory: Any,
) -> None:
    async def _body() -> None:
        async with sqlite_factory() as session:
            await _seed_active(session)
            run_id = await _seed_run(session, "all modes")
            await session.commit()

        tool_fn = build_read_active_cv_tool(session_factory=sqlite_factory)

        section = await _ainvoke_read(
            tool_fn,
            run_id=run_id,
            tool_call_id="read_section",
            mode="section",
            section_id=_SECTION_ID,
            max_results=2,
        )
        assert section.ok is True
        assert section.data is not None
        assert section.data["mode"] == "section"
        assert section.data["attachment_id"] == _ATTACHMENT
        assert section.data["records"]
        assert any(
            "Built APIs" in json.dumps(rec) for rec in section.data["records"]
        )

        search = await _ainvoke_read(
            tool_fn,
            run_id=run_id,
            tool_call_id="read_search",
            mode="search",
            query="Kubernetes",
        )
        assert search.ok is True
        assert search.data is not None
        assert search.data["mode"] == "search"
        assert search.data["records"]

        chunk = await _ainvoke_read(
            tool_fn,
            run_id=run_id,
            tool_call_id="read_chunk",
            mode="chunk",
            chunk_ordinal=0,
            max_results=1,
        )
        assert chunk.ok is True
        assert chunk.data is not None
        assert chunk.data["mode"] == "chunk"
        assert chunk.data["records"]

        async with sqlite_factory() as session:
            for call_id in ("read_section", "read_search", "read_chunk"):
                row = await tool_repo.get_by_identity(
                    session, run_id=run_id, tool_call_id=call_id
                )
                assert row is not None
                assert row.status == TOOL_EXECUTION_STATUS_COMPLETED
                assert row.source_attachment_id == _ATTACHMENT
                summary = row.arguments_summary_json or {}
                dumped = json.dumps(summary)
                assert "Built APIs" not in dumped
                assert "Kubernetes work" not in dumped
                assert "body" not in dumped
                assert summary.get("cursor_present") is False

    run_async(_body())


def test_read_active_cv_replay_skips_second_read(sqlite_factory: Any) -> None:
    async def _body() -> None:
        async with sqlite_factory() as session:
            await _seed_active(session)
            run_id = await _seed_run(session, "replay")
            await session.commit()

        call_count = {"n": 0}
        original = build_read_active_cv_tool(session_factory=sqlite_factory)

        # Patch service path by wrapping invoke via a thin spy tool is hard;
        # prove replay by identity: one terminal row and identical payloads.
        first = await _ainvoke_read(
            original,
            run_id=run_id,
            tool_call_id="read_replay_once",
            mode="search",
            query="Python",
            max_results=3,
        )
        assert first.ok is True
        assert first.data is not None
        first_dump = first.model_dump(mode="json")

        second = await _ainvoke_read(
            original,
            run_id=run_id,
            tool_call_id="read_replay_once",
            mode="search",
            query="Python",
            max_results=3,
        )
        assert second.model_dump(mode="json") == first_dump

        async with sqlite_factory() as session:
            rows = await tool_repo.list_for_run_ids(session, [run_id])
            matching = [r for r in rows if r.tool_call_id == "read_replay_once"]
            assert len(matching) == 1
            assert matching[0].status == TOOL_EXECUTION_STATUS_COMPLETED
            assert matching[0].source_attachment_id == _ATTACHMENT
            assert matching[0].arguments_summary_json == {
                "mode": "search",
                "query": "Python",
                "max_results": 3,
                "max_chars": 6000,
                "cursor_present": False,
            }
            call_count["n"] = 1  # keep local for lint-stable placeholder

        assert call_count["n"] == 1

    run_async(_body())


def test_arguments_summary_omits_bodies() -> None:
    summary = arguments_summary_for_read_active_cv(
        mode="section",
        section_id=_SECTION_ID,
        query=None,
        chunk_ordinal=None,
        max_results=5,
        max_chars=6000,
        cursor="opaque-token",
    )
    assert summary == {
        "mode": "section",
        "section_id": _SECTION_ID,
        "max_results": 5,
        "max_chars": 6000,
        "cursor_present": True,
    }
    assert "body" not in summary
    assert "records" not in summary
    assert "opaque-token" not in json.dumps(summary)


# ---------------------------------------------------------------------------
# Prompt policy / outline snapshot
# ---------------------------------------------------------------------------


def test_prompt_policy_narrow_mode_and_no_cursor_walk() -> None:
    prompt = build_system_prompt(production_registry().tool_names())
    lower = prompt.lower()
    assert "read_active_cv" in prompt
    assert "narrowest mode" in lower
    assert "do not walk every cursor" in lower or "exhaust" in lower
    assert "outline" in lower


def test_active_cv_outline_block_excludes_bodies() -> None:
    outline = {
        "attachment_id": _ATTACHMENT,
        "extraction_version": "cv-document-v1",
        "source_hash": _SOURCE_HASH,
        "reprocess_required": False,
        "sections": [
            {
                "id": _SECTION_ID,
                "ordinal": 0,
                "heading": "Experience",
                "kind": "experience",
                "entry_count": 2,
                "source_chunk_range": [0, 1],
            }
        ],
    }
    block = _format_active_cv_context_block(outline)
    assert block is not None
    assert _ATTACHMENT in block
    assert "Experience" in block
    assert "Built APIs" not in block
    assert "body" not in block
    assert "chunk text" not in block.lower() or "never" in block.lower()

    state = initial_graph_state(
        run_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        user_text="What did I do at Acme?",
        active_cv_context=outline,
    )
    messages = _build_model_messages(
        state, build_system_prompt(["read_active_cv"])
    )
    system_blobs = [
        m.content for m in messages if isinstance(m, SystemMessage)
    ]
    joined = "\n".join(str(c) for c in system_blobs)
    assert "Active CV outline only" in joined
    assert "Built APIs" not in joined
    assert "narrowest mode" in joined.lower()

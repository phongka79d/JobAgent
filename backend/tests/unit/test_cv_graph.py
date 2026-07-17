"""Unit tests for CV graph projection (Plan 9 05A / Master §6.6, §8).

Deterministic fake driver only — no live Neo4j. Covers fixed labels/IDs,
bounded preview, ordinal order, idempotent active PROJECTS_TO, archived
branch retention, exact-delete compatibility, and allowlisted payloads.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph import constraints as constraints_mod
from app.graph import delete_cv as delete_mod
from app.graph import sync_cv as sync_mod
from app.graph.constraints import (
    CV_ENTRY_ID_UNIQUE,
    CV_ID_UNIQUE,
    CV_SECTION_ID_UNIQUE,
    SCHEMA_STATEMENTS,
)
from app.graph.delete_cv import (
    DELETE_CV_BRANCH_CYPHER,
    assert_delete_cv_query_allowlisted,
    delete_cv_branch,
)
from app.graph.sync_cv import (
    CV_ENTRY_PREVIEW_MAX_CHARS,
    NEO4J_SYNC_FAILED,
    CvSyncError,
    assert_payload_safe,
    bounded_entry_preview,
    build_cv_graph_payload,
    cypher_statement_templates,
    scoped_entry_id,
    scoped_section_id,
    sync_cv,
)
from app.schemas.cv_document import parse_cv_document

from tests.support.db_migration import run_async

_ATTACHMENT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_SECTION_ID = "cv-document-v1:s0:experience"
_ENTRY_ID = "cv-document-v1:s0:e0:role"
_LONG_BODY = "X" * (CV_ENTRY_PREVIEW_MAX_CHARS + 80)


# ---------------------------------------------------------------------------
# Fake Neo4j driver
# ---------------------------------------------------------------------------


class _FakeResult:
    async def consume(self) -> None:
        return None


class _FakeSession:
    def __init__(self, driver: FakeNeo4jDriver) -> None:
        self._driver = driver

    async def __aenter__(self) -> _FakeSession:
        self._driver.session_enter += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        self._driver.session_exit += 1

    async def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        del kwargs
        if self._driver.fail_on_run:
            raise OSError("simulated neo4j write failure")
        self._driver.queries.append(query)
        self._driver.parameters.append(
            dict(parameters) if parameters is not None else {}
        )
        return _FakeResult()


class FakeNeo4jDriver:
    def __init__(self, *, fail_on_run: bool = False) -> None:
        self.fail_on_run = fail_on_run
        self.queries: list[str] = []
        self.parameters: list[dict[str, Any]] = []
        self.session_enter = 0
        self.session_exit = 0

    def session(self, **config: Any) -> _FakeSession:
        del config
        return _FakeSession(self)


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": _ENTRY_ID,
        "ordinal": 0,
        "title": "Engineer",
        "subtitle": "Acme",
        "date_text": "2020-2024",
        "location": "Berlin",
        "body": "Built APIs with Python and FastAPI.",
        "bullets": ["Designed services", "Owned deploy"],
        "attributes": {"team": "platform", "stack": ["python", "k8s"]},
        "source_chunk_ordinals": [0],
    }
    base.update(overrides)
    return base


def _section(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": _SECTION_ID,
        "ordinal": 0,
        "heading": "Experience",
        "kind": "experience",
        "entries": [_entry()],
        "source_chunk_ordinals": [0],
    }
    base.update(overrides)
    return base


def _document(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "attachment_id": _ATTACHMENT,
        "detected_languages": ["en"],
        "sections": [_section()],
        "extraction_warnings": [],
        "extraction_confidence": 0.9,
    }
    base.update(overrides)
    return parse_cv_document(base)


def _updated() -> datetime:
    return datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Identity / payload
# ---------------------------------------------------------------------------


def test_scoped_ids_match_master_mapping() -> None:
    assert scoped_section_id(_ATTACHMENT, _SECTION_ID) == (
        f"{_ATTACHMENT}:{_SECTION_ID}"
    )
    assert scoped_entry_id(_ATTACHMENT, _SECTION_ID, _ENTRY_ID) == (
        f"{_ATTACHMENT}:{_SECTION_ID}:{_ENTRY_ID}"
    )


def test_bounded_preview_matches_safe_prefix_pattern() -> None:
    assert bounded_entry_preview("short") == "short"
    long_preview = bounded_entry_preview(_LONG_BODY)
    assert len(long_preview) == CV_ENTRY_PREVIEW_MAX_CHARS
    assert long_preview == _LONG_BODY[:CV_ENTRY_PREVIEW_MAX_CHARS]
    assert CV_ENTRY_PREVIEW_MAX_CHARS == 240


def test_payload_allowlist_order_and_no_raw_content() -> None:
    sec_a = _section(
        id=_SECTION_ID,
        ordinal=0,
        heading="Experience",
        kind="experience",
        entries=[
            _entry(
                ordinal=0,
                id="e0",
                body=_LONG_BODY,
                bullets=["secret bullet"],
                attributes={"k": "v", "team": "platform"},
            ),
            _entry(
                ordinal=1,
                id="e1",
                body="second",
                bullets=[],
                attributes={},
            ),
        ],
        source_chunk_ordinals=[0],
    )
    sec_b = _section(
        id="cv-document-v1:s1:skills",
        ordinal=1,
        heading="Skills",
        kind="skills",
        entries=[
            _entry(
                id="cv-document-v1:s1:e0:py",
                ordinal=0,
                title="Python",
                body="Python advanced",
                bullets=[],
                attributes={},
                source_chunk_ordinals=[1],
            )
        ],
        source_chunk_ordinals=[1],
    )
    doc = _document(sections=[sec_a, sec_b])
    payload = build_cv_graph_payload(
        doc,
        original_name="cv.pdf",
        extraction_version="cv-document-v1",
        source_updated_at=_updated(),
    )
    assert_payload_safe(payload)

    assert payload["cv_id"] == _ATTACHMENT
    assert payload["original_name"] == "cv.pdf"
    assert payload["extraction_version"] == "cv-document-v1"
    assert payload["candidate_id"] == CANDIDATE_PROFILE_ID
    assert "2024-07-01" in payload["source_updated_at"]

    sections = payload["sections"]
    assert [s["ordinal"] for s in sections] == [0, 1]
    assert sections[0]["heading"] == "Experience"
    assert sections[0]["kind"] == "experience"
    assert sections[0]["entry_count"] == 2
    assert sections[0]["id"] == scoped_section_id(_ATTACHMENT, _SECTION_ID)
    assert "source_chunk_ordinals" not in sections[0]

    entries = payload["entries"]
    # Section 0 entries by ordinal, then section 1.
    assert [e["ordinal"] for e in entries[:2]] == [0, 1]
    first = entries[0]
    assert first["id"] == scoped_entry_id(_ATTACHMENT, _SECTION_ID, "e0")
    assert first["preview"] == _LONG_BODY[:CV_ENTRY_PREVIEW_MAX_CHARS]
    assert len(first["preview"]) == CV_ENTRY_PREVIEW_MAX_CHARS
    for forbidden in ("body", "bullets", "attributes", "location"):
        assert forbidden not in first
    # Bullets/attributes never serialized as collections in payload JSON shape.
    raw = str(payload)
    assert "secret bullet" not in raw
    assert "platform" not in raw
    assert "source_chunk_ordinals" not in raw


def test_payload_rejects_non_document() -> None:
    with pytest.raises(CvSyncError):
        build_cv_graph_payload(
            object(),  # type: ignore[arg-type]
            original_name="cv.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
        )


# ---------------------------------------------------------------------------
# Sync behavior
# ---------------------------------------------------------------------------


def test_sync_active_creates_branch_and_single_projects_to() -> None:
    driver = FakeNeo4jDriver()
    doc = _document()

    async def _body() -> None:
        await sync_cv(
            driver,
            document=doc,
            original_name="resume.pdf",
            extraction_version="cv-document-v1",
            source_updated_at=_updated(),
            is_active=True,
        )

    run_async(_body())

    joined = "\n".join(driver.queries)
    assert "MERGE (cv:CV {id: $cv_id})" in joined
    assert "MERGE (sec:CVSection {id: row.id})" in joined
    assert "MERGE (entry:CVEntry {id: row.id})" in joined
    assert "HAS_SECTION" in joined
    assert "HAS_ENTRY" in joined
    assert "PROJECTS_TO" in joined
    assert "DETACH DELETE entry, sec" in joined
    # Active path clears all PROJECTS_TO then MERGEs one.
    assert any("PROJECTS_TO" in q and "DELETE r" in q for q in driver.queries)
    assert any("MERGE (cv)-[:PROJECTS_TO]->(c)" in q for q in driver.queries)

    first = driver.parameters[0]
    assert first["cv_id"] == _ATTACHMENT
    assert first["original_name"] == "resume.pdf"
    assert first["sections"][0]["heading"] == "Experience"
    assert "body" not in str(first["entries"])
    assert driver.session_enter == 1
    assert driver.session_exit == 1


def test_sync_archived_clears_own_projects_to_only() -> None:
    driver = FakeNeo4jDriver()
    doc = _document()

    async def _body() -> None:
        await sync_cv(
            driver,
            document=doc,
            original_name="old.pdf",
            extraction_version="cv-document-v1",
            source_updated_at=_updated(),
            is_active=False,
        )

    run_async(_body())
    joined = "\n".join(driver.queries)
    assert "MERGE (cv:CV {id: $cv_id})" in joined
    assert "MATCH (cv:CV {id: $cv_id})-[r:PROJECTS_TO]->()" in joined
    # Must not clear other CVs' PROJECTS_TO when archived.
    assert "MATCH (:CV)-[r:PROJECTS_TO]->(c:Candidate" not in joined
    assert "MERGE (cv)-[:PROJECTS_TO]->(c)" not in joined


def test_active_switch_is_idempotent_single_projects_to() -> None:
    driver = FakeNeo4jDriver()
    active_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    archived = _document()
    active = _document(
        attachment_id=active_id,
        sections=[
            _section(
                id="s0",
                entries=[
                    _entry(
                        id="e0",
                        body="Active body",
                        bullets=[],
                        attributes={},
                    )
                ],
            )
        ],
    )

    async def _body() -> None:
        await sync_cv(
            driver,
            document=archived,
            original_name="old.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=True,
        )
        await sync_cv(
            driver,
            document=archived,
            original_name="old.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=False,
        )
        await sync_cv(
            driver,
            document=active,
            original_name="new.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=True,
        )
        # Repeat active sync converges.
        await sync_cv(
            driver,
            document=active,
            original_name="new.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=True,
        )

    run_async(_body())

    # Last two active syncs each clear all PROJECTS_TO then MERGE active.
    projects_merge = [
        q for q in driver.queries if "MERGE (cv)-[:PROJECTS_TO]->(c)" in q
    ]
    assert len(projects_merge) == 3  # first active + two final active
    last_params = [
        p
        for p, q in zip(driver.parameters, driver.queries, strict=True)
        if "MERGE (cv)-[:PROJECTS_TO]->(c)" in q
    ]
    assert last_params[-1]["cv_id"] == active_id
    assert last_params[-2]["cv_id"] == active_id


def test_sync_failure_maps_to_neo4j_sync_failed() -> None:
    driver = FakeNeo4jDriver(fail_on_run=True)
    doc = _document()

    async def _body() -> None:
        with pytest.raises(CvSyncError) as ei:
            await sync_cv(
                driver,
                document=doc,
                original_name="cv.pdf",
                extraction_version="v1",
                source_updated_at=_updated(),
                is_active=True,
            )
        assert ei.value.code == NEO4J_SYNC_FAILED
        assert "rebuild" in ei.value.rebuild_instruction.lower()

    run_async(_body())


def test_sync_empty_sections_still_merges_cv_and_projects_to() -> None:
    driver = FakeNeo4jDriver()
    doc = _document(sections=[])

    async def _body() -> None:
        await sync_cv(
            driver,
            document=doc,
            original_name="empty.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=True,
        )

    run_async(_body())
    joined = "\n".join(driver.queries)
    assert "MERGE (cv:CV {id: $cv_id})" in joined
    assert "MERGE (cv)-[:PROJECTS_TO]->(c)" in joined
    assert "UNWIND $sections" not in joined
    assert "UNWIND $entries" not in joined


# ---------------------------------------------------------------------------
# Exact delete compatibility + constraints allowlist
# ---------------------------------------------------------------------------


def test_exact_delete_compatible_with_synced_branch() -> None:
    driver = FakeNeo4jDriver()
    doc = _document()

    async def _body() -> None:
        await sync_cv(
            driver,
            document=doc,
            original_name="cv.pdf",
            extraction_version="v1",
            source_updated_at=_updated(),
            is_active=True,
        )
        await delete_cv_branch(driver, _ATTACHMENT)
        await delete_cv_branch(driver, _ATTACHMENT)  # idempotent

    run_async(_body())
    delete_queries = [
        q for q in driver.queries if "DETACH DELETE entry, sec, cv" in q
    ]
    assert len(delete_queries) == 2
    for q in delete_queries:
        assert_delete_cv_query_allowlisted(q)
    # Shared labels never appear in delete template.
    assert "Job" not in DELETE_CV_BRANCH_CYPHER
    assert "Skill" not in DELETE_CV_BRANCH_CYPHER
    assert "Candidate" not in DELETE_CV_BRANCH_CYPHER


def test_cv_constraints_present_in_base_schema() -> None:
    assert CV_ID_UNIQUE in SCHEMA_STATEMENTS
    assert CV_SECTION_ID_UNIQUE in SCHEMA_STATEMENTS
    assert CV_ENTRY_ID_UNIQUE in SCHEMA_STATEMENTS
    joined = "\n".join(SCHEMA_STATEMENTS)
    assert "FOR (cv:CV) REQUIRE cv.id IS UNIQUE" in joined
    assert "FOR (s:CVSection) REQUIRE s.id IS UNIQUE" in joined
    assert "FOR (e:CVEntry) REQUIRE e.id IS UNIQUE" in joined
    assert all("IF NOT EXISTS" in s for s in SCHEMA_STATEMENTS)
    assert "$" not in joined


def test_cypher_templates_parameterized_and_allowlisted() -> None:
    templates = cypher_statement_templates()
    joined = "\n".join(templates)
    assert "MERGE (cv:CV {id: $cv_id})" in joined
    assert "PROJECTS_TO" in joined
    assert "HAS_SECTION" in joined
    assert "HAS_ENTRY" in joined
    # No dynamic labels / unrestricted deletes.
    assert "MATCH (n)" not in joined
    assert "DETACH DELETE n" not in joined
    src = inspect.getsource(sync_mod)
    assert "NEO4J_SYNC_FAILED" in src
    assert "body" in src  # preview source only
    # Module must not open SQLite sessions.
    assert "sessionmaker" not in src
    assert "app.repositories" not in src


def test_delete_and_sync_owners_do_not_share_skill_logic() -> None:
    sync_src = inspect.getsource(sync_mod)
    del_src = inspect.getsource(delete_mod)
    assert "HAS_SKILL" not in sync_src
    assert "RELATED_TO" not in sync_src
    assert "project_seed_skills" not in sync_src
    # Exact-branch delete template never targets shared domain labels.
    assert ":Job" not in DELETE_CV_BRANCH_CYPHER
    assert ":Skill" not in DELETE_CV_BRANCH_CYPHER
    assert ":Candidate" not in DELETE_CV_BRANCH_CYPHER
    assert "HAS_SKILL" not in del_src
    # Constraints remain DDL-only (no domain writes).
    c_src = Path(constraints_mod.__file__).read_text(encoding="utf-8")
    assert "MERGE (" not in c_src
    assert "PROJECTS_TO" not in c_src


# ---------------------------------------------------------------------------
# Rebuild path (05B): sole path wires sync_cv; no provider
# ---------------------------------------------------------------------------


def test_rebuild_owner_calls_sync_cv_and_clears_cv_labels() -> None:
    from app.graph import rebuild as rebuild_mod
    from app.graph import rebuild_ops as ops

    src = inspect.getsource(rebuild_mod.rebuild_graph)
    assert "sync_cv" in src
    assert "approved_cvs" in src
    assert "legacy_active" in src
    assert ops.CLEAR_CV_CYPHER in ops.CLEAR_STATEMENTS
    assert ops.CLEAR_CV_SECTION_CYPHER in ops.CLEAR_STATEMENTS
    assert ops.CLEAR_CV_ENTRY_CYPHER in ops.CLEAR_STATEMENTS
    public = inspect.getsource(rebuild_mod)
    assert "from app.adapters" not in public
    assert "embed_text" not in public
    assert "commit(" not in public


def test_active_cv_consistency_id_and_revision_mismatch() -> None:
    from app.graph.consistency import (
        ActiveCvGraphRevision,
        _active_cv_matches,
    )
    from app.graph.rebuild_snapshot import ActiveCvConsistencyFacts

    stamp = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
    other = datetime(2024, 8, 1, 12, 0, 0, tzinfo=UTC)
    facts = ActiveCvConsistencyFacts(
        active_attachment_id=_ATTACHMENT,
        source_hash="abc123hash",
        document_updated_at=stamp,
        has_document=True,
    )
    # Matching id + revision.
    assert _active_cv_matches(
        facts,
        ActiveCvGraphRevision(
            attachment_id=_ATTACHMENT, source_updated_at=stamp
        ),
    )
    # Active ID mismatch → stale.
    assert not _active_cv_matches(
        facts,
        ActiveCvGraphRevision(
            attachment_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            source_updated_at=stamp,
        ),
    )
    # Document source revision mismatch (source_hash co-mutates with updated_at).
    assert not _active_cv_matches(
        facts,
        ActiveCvGraphRevision(
            attachment_id=_ATTACHMENT, source_updated_at=other
        ),
    )
    # Missing graph branch when document exists → stale.
    assert not _active_cv_matches(facts, None)
    # Legacy (no document): empty graph allowed; wrong id not allowed.
    legacy = ActiveCvConsistencyFacts(
        active_attachment_id=_ATTACHMENT,
        source_hash=None,
        document_updated_at=None,
        has_document=False,
    )
    assert _active_cv_matches(legacy, None)
    assert _active_cv_matches(
        legacy,
        ActiveCvGraphRevision(
            attachment_id=_ATTACHMENT, source_updated_at=stamp
        ),
    )
    assert not _active_cv_matches(
        legacy,
        ActiveCvGraphRevision(
            attachment_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            source_updated_at=stamp,
        ),
    )

"""Static ownership, Cypher, count, and reuse contracts for rebuild (03D)."""

from __future__ import annotations

import inspect
import re

from app.db.models.profiles import CANDIDATE_PROFILE_ID
from app.graph import rebuild as rebuild_mod
from app.graph import rebuild_ops as rebuild_ops_mod
from app.graph import rebuild_snapshot as rebuild_snapshot_mod
from app.graph import rebuild_target as rebuild_target_mod
from app.graph.rebuild import format_counts
from app.graph.rebuild_ops import RebuildCounts
from app.graph.sync_candidate import sync_candidate
from app.graph.sync_job import sync_job


def test_clear_cypher_is_label_scoped_not_unrestricted() -> None:
    clear_consts = [
        rebuild_ops_mod.CLEAR_CANDIDATE_CYPHER,
        rebuild_ops_mod.CLEAR_JOB_CYPHER,
        rebuild_ops_mod.CLEAR_SKILL_CYPHER,
    ]
    for stmt in clear_consts:
        assert "DETACH DELETE" in stmt
        assert re.search(r":(Candidate|Job|Skill)", stmt)
        assert not re.search(r"MATCH\s*\(\s*\w+\s*\)\s*DETACH", stmt)
    joined_clear = "\n".join(clear_consts)
    assert "MATCH (n) DETACH DELETE n" not in joined_clear
    # Public module re-exports the same constants for inspectability.
    assert rebuild_mod._CLEAR_CANDIDATE_CYPHER == clear_consts[0]  # noqa: SLF001


def test_relationship_counts_are_endpoint_scoped() -> None:
    cypher = rebuild_ops_mod.COUNT_CYPHER
    assert tuple(rebuild_ops_mod.COUNT_ORDER) == (
        "Candidate",
        "Job",
        "Skill",
        "HAS_SKILL",
        "REQUIRES",
        "PREFERS",
        "RELATED_TO",
    )
    assert cypher["Candidate"] == "MATCH (c:Candidate) RETURN count(c) AS n"
    assert cypher["Job"] == "MATCH (j:Job) RETURN count(j) AS n"
    assert cypher["Skill"] == "MATCH (s:Skill) RETURN count(s) AS n"
    assert cypher["HAS_SKILL"] == (
        "MATCH (:Candidate)-[r:HAS_SKILL]->(:Skill) RETURN count(r) AS n"
    )
    assert cypher["REQUIRES"] == (
        "MATCH (:Job)-[r:REQUIRES]->(:Skill) RETURN count(r) AS n"
    )
    assert cypher["PREFERS"] == (
        "MATCH (:Job)-[r:PREFERS]->(:Skill) RETURN count(r) AS n"
    )
    assert cypher["RELATED_TO"] == (
        "MATCH (:Skill)-[r:RELATED_TO]->(:Skill) RETURN count(r) AS n"
    )
    for key in ("HAS_SKILL", "REQUIRES", "PREFERS", "RELATED_TO"):
        assert "MATCH ()-[r:" not in cypher[key]
        assert "MATCH ()-[" not in cypher[key]


def test_rebuild_module_forbids_provider_and_sqlite_writes() -> None:
    forbidden = (
        "shopaikey_embeddings",
        "embed_text",
        "EmbeddingClient",
        "from app.adapters",
        "openai",
        "httpx",
    )
    for mod in (
        rebuild_mod,
        rebuild_ops_mod,
        rebuild_snapshot_mod,
        rebuild_target_mod,
    ):
        source = inspect.getsource(mod)
        for token in forbidden:
            assert token not in source, f"{mod.__name__} must not reference {token}"
    public_src = inspect.getsource(rebuild_mod)
    assert "session_scope" not in public_src
    assert "commit(" not in public_src
    assert "sync_candidate" in public_src
    assert "sync_job" in public_src
    assert "ensure_base_schema" in public_src
    snap_src = inspect.getsource(rebuild_snapshot_mod)
    assert "commit(" not in snap_src
    assert "flush(" not in snap_src
    assert "delete(" not in snap_src


def test_format_counts_includes_all_required_keys() -> None:
    text_out = format_counts(
        RebuildCounts(
            Candidate=1,
            Job=2,
            Skill=10,
            HAS_SKILL=3,
            REQUIRES=4,
            PREFERS=1,
            RELATED_TO=5,
        )
    )
    assert text_out.startswith(
        "Neo4j rebuild complete (provider-free, SQLite read-only):"
    )
    for key, value in (
        ("Candidate", 1),
        ("Job", 2),
        ("Skill", 10),
        ("HAS_SKILL", 3),
        ("REQUIRES", 4),
        ("PREFERS", 1),
        ("RELATED_TO", 5),
    ):
        assert f"  {key}: {value}" in text_out


def test_sync_owners_still_exported_for_reuse() -> None:
    assert callable(sync_candidate)
    assert callable(sync_job)
    assert CANDIDATE_PROFILE_ID == "active"

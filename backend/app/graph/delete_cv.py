"""Exact CV-branch Neo4j deletion (Plan 9 / Master §6.4, §8).

Deletes only the ``CV`` node identified by attachment id and CVSection/CVEntry
nodes reached through allowlisted ``HAS_SECTION`` / ``HAS_ENTRY`` edges.
Never matches Job, Skill, Candidate, seed relationships, or unrestricted
``DETACH DELETE`` patterns. Idempotent when the CV node is already absent.
"""

from __future__ import annotations

from app.graph.sync_shared import AsyncGraphDriver, consume_result

# Exact branch only: parameterised CV.id, owned section/entry labels, fixed rels.
DELETE_CV_BRANCH_CYPHER: str = (
    "MATCH (cv:CV {id: $cv_id}) "
    "OPTIONAL MATCH (cv)-[:HAS_SECTION]->(sec:CVSection) "
    "OPTIONAL MATCH (sec)-[:HAS_ENTRY]->(entry:CVEntry) "
    "DETACH DELETE entry, sec, cv"
)

# Static review allowlist — no other delete patterns live in this module.
_ALLOWED_LABELS: frozenset[str] = frozenset({"CV", "CVSection", "CVEntry"})
_ALLOWED_RELS: frozenset[str] = frozenset({"HAS_SECTION", "HAS_ENTRY"})


class CvGraphDeleteError(Exception):
    """Raised when exact CV-branch deletion fails at the driver boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def assert_delete_cv_query_allowlisted(query: str) -> None:
    """Raise ``ValueError`` when *query* is not the exact CV-branch template.

    Guards callers/tests against broad ``DETACH DELETE`` or shared-label wipes.
    """
    normalized = " ".join(query.split())
    expected = " ".join(DELETE_CV_BRANCH_CYPHER.split())
    if normalized != expected:
        raise ValueError("CV graph delete query is not the allowlisted template")
    upper = normalized.upper()
    if "MATCH (N)" in upper or "MATCH (N:" in upper:
        raise ValueError("unrestricted node match is forbidden")
    for label in ("JOB", "SKILL", "CANDIDATE"):
        if f":{label}" in upper:
            raise ValueError(f"shared label {label!r} must not appear in CV delete")


async def delete_cv_branch(
    driver: AsyncGraphDriver,
    cv_id: str,
) -> None:
    """Idempotently delete the Neo4j branch for exact ``CV.id`` = *cv_id*.

    *cv_id* is the attachment UUID. Missing nodes are a no-op. Does not open
    SQLite transactions or touch shared Job/Skill/Candidate data.
    """
    if not isinstance(cv_id, str) or cv_id.strip() == "":
        raise CvGraphDeleteError(
            "CV_DELETE_GRAPH_FAILED",
            "cv_id must be a non-empty attachment id",
        )
    aid = cv_id.strip()
    assert_delete_cv_query_allowlisted(DELETE_CV_BRANCH_CYPHER)
    try:
        async with driver.session() as session:
            result = await session.run(
                DELETE_CV_BRANCH_CYPHER,
                {"cv_id": aid},
            )
            await consume_result(result)
    except CvGraphDeleteError:
        raise
    except Exception as exc:
        raise CvGraphDeleteError(
            "CV_DELETE_GRAPH_FAILED",
            "failed to delete CV-owned Neo4j branch; retry DELETE",
        ) from exc


def allowed_delete_labels() -> frozenset[str]:
    """Labels reachable by exact CV-branch deletion."""
    return _ALLOWED_LABELS


def allowed_delete_relationships() -> frozenset[str]:
    """Relationship types used to reach owned section/entry nodes."""
    return _ALLOWED_RELS


__all__ = [
    "DELETE_CV_BRANCH_CYPHER",
    "CvGraphDeleteError",
    "allowed_delete_labels",
    "allowed_delete_relationships",
    "assert_delete_cv_query_allowlisted",
    "delete_cv_branch",
]

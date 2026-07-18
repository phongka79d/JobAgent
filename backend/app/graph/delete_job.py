"""Exact Job Neo4j deletion (Plan 10 / Master §6.4, §14.1).

Deletes only the ``Job`` node identified by SQLite ``job_posts.id`` and its
incident relationships (``REQUIRES`` / ``PREFERS``). Never matches Skill,
seed ``RELATED_TO``, Candidate, CV, or unrestricted ``DETACH DELETE``
patterns. Idempotent when the Job node is already absent.
"""

from __future__ import annotations

from typing import Any

from app.graph.sync_shared import AsyncGraphDriver, consume_result

# Exact Job only: parameterised Job.id; DETACH removes incident Job edges only.
DELETE_JOB_CYPHER: str = "MATCH (j:Job {id: $job_id}) DETACH DELETE j"

# Confirm absence after delete (or when node was already missing).
JOB_ABSENCE_CYPHER: str = (
    "MATCH (j:Job {id: $job_id}) RETURN count(j) AS n"
)

# Static review allowlist — no other delete patterns live in this module.
_ALLOWED_LABELS: frozenset[str] = frozenset({"Job"})
_ALLOWED_RELS: frozenset[str] = frozenset()  # DETACH; no explicit rel match


class JobGraphDeleteError(Exception):
    """Raised when exact Job graph deletion fails at the driver boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def delete_job_cypher() -> str:
    """Return the fixed exact-Job Cypher template (for static review/tests)."""
    return DELETE_JOB_CYPHER


def job_absence_cypher() -> str:
    """Return the fixed absence-check Cypher template."""
    return JOB_ABSENCE_CYPHER


def assert_delete_job_query_allowlisted(query: str) -> None:
    """Raise ``ValueError`` when *query* is not the exact Job delete template.

    Guards callers/tests against broad ``DETACH DELETE`` or shared-label wipes.
    """
    normalized = " ".join(query.split())
    expected = " ".join(DELETE_JOB_CYPHER.split())
    if normalized != expected:
        raise ValueError("Job graph delete query is not the allowlisted template")
    upper = normalized.upper()
    if "MATCH (N)" in upper or "MATCH (N:" in upper:
        raise ValueError("unrestricted node match is forbidden")
    if "$job_id" not in normalized:
        raise ValueError("Job graph delete must bind $job_id")
    if "{id:" not in normalized.replace(" ", "").lower():
        raise ValueError("Job graph delete must match exact Job.id property")
    for label in ("SKILL", "CANDIDATE", "CV", "CVSECTION", "CVENTRY"):
        if f":{label}" in upper:
            raise ValueError(f"shared label {label!r} must not appear in Job delete")


async def job_node_absent(driver: AsyncGraphDriver, job_id: str) -> bool:
    """Return True when no ``(:Job {id: job_id})`` exists."""
    aid = _require_job_id(job_id)
    try:
        async with driver.session() as session:
            result = await session.run(
                JOB_ABSENCE_CYPHER,
                {"job_id": aid},
            )
            rows = await _result_rows(result)
            await consume_result(result)
    except JobGraphDeleteError:
        raise
    except Exception as exc:
        raise JobGraphDeleteError(
            "JOB_DELETE_GRAPH_FAILED",
            "failed to confirm Job graph absence; retry DELETE",
        ) from exc
    if not rows:
        return True
    count = rows[0].get("n", 0)
    try:
        return int(count) == 0
    except (TypeError, ValueError):
        return False


async def delete_job_node(
    driver: AsyncGraphDriver,
    job_id: str,
) -> None:
    """Idempotently delete the Neo4j node for exact ``Job.id`` = *job_id*.

    *job_id* is the SQLite ``job_posts`` UUID. Missing nodes are a no-op success
    after absence is confirmed. Does not open SQLite transactions or touch
    shared Skill/Candidate/CV data or other Jobs.
    """
    aid = _require_job_id(job_id)
    assert_delete_job_query_allowlisted(DELETE_JOB_CYPHER)
    try:
        async with driver.session() as session:
            result = await session.run(
                DELETE_JOB_CYPHER,
                {"job_id": aid},
            )
            await consume_result(result)
            check = await session.run(
                JOB_ABSENCE_CYPHER,
                {"job_id": aid},
            )
            rows = await _result_rows(check)
            await consume_result(check)
    except JobGraphDeleteError:
        raise
    except Exception as exc:
        raise JobGraphDeleteError(
            "JOB_DELETE_GRAPH_FAILED",
            "failed to delete exact Job Neo4j node; retry DELETE",
        ) from exc

    if rows:
        try:
            remaining = int(rows[0].get("n", 0))
        except (TypeError, ValueError):
            remaining = -1
        if remaining != 0:
            raise JobGraphDeleteError(
                "JOB_DELETE_GRAPH_FAILED",
                "Job graph node still present after delete; retry DELETE",
            )


def allowed_delete_labels() -> frozenset[str]:
    """Labels reachable by exact Job deletion."""
    return _ALLOWED_LABELS


def allowed_delete_relationships() -> frozenset[str]:
    """Explicit relationship types matched by the delete template (none)."""
    return _ALLOWED_RELS


def _require_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or job_id.strip() == "":
        raise JobGraphDeleteError(
            "JOB_DELETE_GRAPH_FAILED",
            "job_id must be a non-empty Job UUID",
        )
    return job_id.strip()


async def _result_rows(result: Any) -> list[dict[str, Any]]:
    data_fn = getattr(result, "data", None)
    if callable(data_fn):
        rows = await data_fn()
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    single_fn = getattr(result, "single", None)
    if callable(single_fn):
        row = await single_fn()
        if isinstance(row, dict):
            return [row]
    return []


__all__ = [
    "DELETE_JOB_CYPHER",
    "JOB_ABSENCE_CYPHER",
    "JobGraphDeleteError",
    "allowed_delete_labels",
    "allowed_delete_relationships",
    "assert_delete_job_query_allowlisted",
    "delete_job_cypher",
    "delete_job_node",
    "job_absence_cypher",
    "job_node_absent",
]

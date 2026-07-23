"""Allowlisted deletion of one profile's Candidate and CV graph branches."""

from __future__ import annotations

from app.graph.sync_shared import AsyncGraphDriver, consume_result

DELETE_PROFILE_BRANCH_CYPHER = (
    "MATCH (c:Candidate {profile_id: $profile_id}) "
    "OPTIONAL MATCH (cv:CV {profile_id: $profile_id}) "
    "OPTIONAL MATCH (cv)-[:HAS_SECTION]->(sec:CVSection) "
    "OPTIONAL MATCH (sec)-[:HAS_ENTRY]->(entry:CVEntry) "
    "DETACH DELETE entry, sec, cv, c"
)


class ProfileGraphDeleteError(Exception):
    def __init__(self, code: str, summary: str) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary


def assert_delete_profile_query_allowlisted(query: str) -> None:
    normalized = " ".join(query.split())
    expected = " ".join(DELETE_PROFILE_BRANCH_CYPHER.split())
    if normalized != expected:
        raise ValueError("profile graph delete query is not allowlisted")
    upper = normalized.upper()
    if "MATCH (N)" in upper or ":JOB" in upper or ":SKILL" in upper:
        raise ValueError("shared graph labels are forbidden in profile deletion")


async def delete_profile_branch(driver: AsyncGraphDriver, profile_id: str) -> None:
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ProfileGraphDeleteError(
            "PROFILE_DELETE_GRAPH_FAILED", "profile id must be non-empty"
        )
    assert_delete_profile_query_allowlisted(DELETE_PROFILE_BRANCH_CYPHER)
    try:
        async with driver.session() as session:
            result = await session.run(
                DELETE_PROFILE_BRANCH_CYPHER,
                {"profile_id": profile_id.strip()},
            )
            await consume_result(result)
    except Exception as exc:
        raise ProfileGraphDeleteError(
            "PROFILE_DELETE_GRAPH_FAILED",
            "profile graph branch could not be removed; retry the deletion",
        ) from exc


__all__ = [
    "DELETE_PROFILE_BRANCH_CYPHER",
    "ProfileGraphDeleteError",
    "assert_delete_profile_query_allowlisted",
    "delete_profile_branch",
]

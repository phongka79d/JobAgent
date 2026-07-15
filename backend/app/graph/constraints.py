"""Idempotent JobAgent Neo4j base schema (constraints + vector index).

Creates only the three uniqueness constraints and one cosine/1536 vector index
required by Plan 2 §7.6 / Master §8.3. No domain nodes, relationships, or
graph synchronization behavior.

Fixed identities (for later callers; not seeded here):
- Candidate.id is the singleton key ``active``
- Job.id is the SQLite ``job_posts.id`` UUID
- Skill.canonical_key is the normalized skill key
"""

from __future__ import annotations

from neo4j import AsyncDriver

# Locked embedding dimension (Master embedding contract / settings default).
VECTOR_DIMENSIONS = 1536
VECTOR_SIMILARITY = "cosine"
JOB_EMBEDDING_VECTOR_INDEX_NAME = "job_embedding_vector"

# Fixed, idempotent DDL. Identifiers and options are source constants only —
# never interpolate runtime values or secrets into these statements.
CANDIDATE_ID_UNIQUE = (
    "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS "
    "FOR (c:Candidate) REQUIRE c.id IS UNIQUE"
)
JOB_ID_UNIQUE = (
    "CREATE CONSTRAINT job_id_unique IF NOT EXISTS "
    "FOR (j:Job) REQUIRE j.id IS UNIQUE"
)
SKILL_CANONICAL_KEY_UNIQUE = (
    "CREATE CONSTRAINT skill_canonical_key_unique IF NOT EXISTS "
    "FOR (s:Skill) REQUIRE s.canonical_key IS UNIQUE"
)
JOB_EMBEDDING_VECTOR_INDEX = (
    f"CREATE VECTOR INDEX {JOB_EMBEDDING_VECTOR_INDEX_NAME} IF NOT EXISTS "
    "FOR (j:Job) ON (j.embedding) "
    "OPTIONS {indexConfig: {"
    "`vector.dimensions`: 1536, "
    "`vector.similarity_function`: 'cosine'"
    "}}"
)

SCHEMA_STATEMENTS: tuple[str, ...] = (
    CANDIDATE_ID_UNIQUE,
    JOB_ID_UNIQUE,
    SKILL_CANONICAL_KEY_UNIQUE,
    JOB_EMBEDDING_VECTOR_INDEX,
)


async def ensure_base_schema(driver: AsyncDriver) -> None:
    """Issue the idempotent base schema statements exactly once per call.

    Safe to repeat: every statement uses ``IF NOT EXISTS``. Runtime data is
    never interpolated into these fixed DDL statements.
    """
    async with driver.session() as session:
        for statement in SCHEMA_STATEMENTS:
            await session.run(statement)

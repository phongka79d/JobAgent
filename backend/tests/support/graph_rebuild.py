"""Shared Settings, payloads, SQLite seed, and snapshot builders for rebuild tests.

Owned helpers for Plan 5 / 03D integration modules — import and reuse; do not copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.db.models.jobs import JobPost
from app.repositories import attachments as att_repo
from app.repositories import jobs as jobs_repo
from app.repositories import profiles as prof_repo
from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS, LOCKED_EMBEDDING_MODEL
from app.schemas.jobs import parse_job_post_extraction
from app.schemas.profile import parse_candidate_profile
from pydantic import AnyHttpUrl, SecretStr
from sqlalchemy import select, text


def skills_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "skills_seed.yaml"


def embedding_vector(seed: float = 0.01) -> list[float]:
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


def settings(
    *,
    uri: str = "bolt://neo4j:7687",
    app_env: str = "local",
    sqlite_path: str = "/data/jobagent.db",
    model: str = LOCKED_EMBEDDING_MODEL,
    dimensions: int = LOCKED_EMBEDDING_DIMENSIONS,
) -> Settings:
    return Settings(
        APP_ENV=app_env,
        FRONTEND_ORIGIN="http://127.0.0.1:5173",
        SQLITE_PATH=sqlite_path,
        FILES_DIR="files",
        NEO4J_URI=uri,
        NEO4J_USER="neo4j",
        NEO4J_PASSWORD=SecretStr("unit-test-neo4j-password-NOT-A-REAL-SECRET"),
        SHOPAIKEY_BASE_URL=AnyHttpUrl("https://example.test/v1"),
        SHOPAIKEY_API_KEY=SecretStr("unit-test-shopaikey-not-real"),
        EMBEDDING_MODEL=model,
        EMBEDDING_DIMENSIONS=dimensions,
    )


def extraction_payload() -> dict[str, Any]:
    return {
        "title": "Backend Engineer",
        "company": "Acme",
        "summary": "Build APIs.",
        "responsibilities": ["Design services"],
        "required_skills": [
            {
                "skill": {
                    "canonical_key": "python",
                    "display_name": "Python",
                    "aliases": ["python3"],
                    "category": "language",
                },
                "confidence": 0.91,
                "evidence": ["Required: Python 3+"],
            }
        ],
        "preferred_skills": [
            {
                "skill": {
                    "canonical_key": "fastapi",
                    "display_name": "FastAPI",
                    "aliases": ["fast api"],
                    "category": "framework",
                },
                "confidence": 0.7,
                "evidence": ["Preferred: FastAPI"],
            }
        ],
        "seniority": "mid",
        "min_experience_years": 3.0,
        "max_experience_years": 5.0,
        "location": "Berlin",
        "work_mode": "hybrid",
        "extraction_confidence": 0.85,
    }


def profile_payload(*, include_excluded: bool = True) -> dict[str, Any]:
    skills: list[dict[str, Any]] = [
        {
            "skill": {
                "canonical_key": "python",
                "display_name": "Python",
                "aliases": ["python3"],
                "category": "language",
            },
            "confidence": 0.9,
            "proficiency": "advanced",
            "years": 4.0,
            "source": "cv",
            "excluded": False,
            "evidence": ["Python backend"],
        }
    ]
    if include_excluded:
        skills.append(
            {
                "skill": {
                    "canonical_key": "react",
                    "display_name": "React",
                    "aliases": ["reactjs"],
                    "category": "framework",
                },
                "confidence": 0.5,
                "proficiency": "beginner",
                "years": None,
                "source": "user_correction",
                "excluded": True,
                "evidence": ["User excluded React"],
            }
        )
    return {
        "summary": "Backend engineer",
        "current_title": "Backend Engineer",
        "total_experience_years": 4.0,
        "skills": skills,
        "experiences": [
            {
                "title": "Engineer",
                "company": "Co",
                "start_date_text": "2020",
                "end_date_text": "present",
                "summary": "APIs",
            }
        ],
        "education": [
            {
                "institution": "U",
                "degree": "BSc",
                "field": "CS",
                "graduation_year": 2019,
            }
        ],
        "languages": [{"name": "English", "proficiency": "fluent"}],
        "extraction_confidence": 0.8,
    }


async def seed_scorable_job(
    factory: Any,
    *,
    raw_hash: str,
    quality: str = "full",
    vector: list[float] | None = None,
    model: str = LOCKED_EMBEDDING_MODEL,
    dimensions: int = LOCKED_EMBEDDING_DIMENSIONS,
    raw_content: str = "JD body",
) -> str:
    vec = vector if vector is not None else embedding_vector()
    extraction = parse_job_post_extraction(extraction_payload())
    async with factory() as session:
        row = await jobs_repo.create_text_job(
            session,
            raw_content=raw_content,
            raw_content_hash=raw_hash,
        )
        job_id = row.id
        await jobs_repo.mark_processing(session, job_id)
        await jobs_repo.mark_processed(
            session,
            job_id,
            extraction_json=extraction.model_dump(mode="json"),
            jd_quality=quality,
            embedding_json=vec,
            embedding_model=model,
            embedding_dimensions=dimensions,
        )
        await session.commit()
    return job_id


async def seed_unscorable_job(factory: Any, *, raw_hash: str) -> str:
    extraction = parse_job_post_extraction(
        {
            **extraction_payload(),
            "title": None,
            "required_skills": [],
            "preferred_skills": [],
            "responsibilities": [],
            "summary": "Contact only",
            "extraction_confidence": 0.1,
        }
    )
    async with factory() as session:
        row = await jobs_repo.create_text_job(
            session,
            raw_content="thin",
            raw_content_hash=raw_hash,
        )
        job_id = row.id
        await jobs_repo.mark_processing(session, job_id)
        await jobs_repo.mark_processed(
            session,
            job_id,
            extraction_json=extraction.model_dump(mode="json"),
            jd_quality="unscorable",
            embedding_json=None,
            embedding_model=None,
            embedding_dimensions=None,
        )
        await session.commit()
    return job_id


async def seed_candidate(factory: Any) -> None:
    profile = parse_candidate_profile(profile_payload())
    async with factory() as session:
        att = await att_repo.create_staged(
            session,
            file_hash="rebuild-cv-hash",
            original_name="cv.pdf",
            size_bytes=100,
            storage_path="rebuild/cv.pdf",
            page_count=1,
        )
        await att_repo.mark_active(session, att.id)
        await prof_repo.upsert_active_profile(
            session,
            active_attachment_id=att.id,
            profile_json=profile.model_dump(mode="json"),
        )
        await session.commit()


async def snapshot_sqlite(factory: Any) -> list[tuple[Any, ...]]:
    async with factory() as session:
        jobs = (
            await session.execute(
                select(
                    JobPost.id,
                    JobPost.processing_status,
                    JobPost.jd_quality,
                    JobPost.embedding_model,
                    JobPost.embedding_dimensions,
                    JobPost.raw_content_hash,
                    JobPost.updated_at,
                ).order_by(JobPost.id)
            )
        ).all()
        profile = await session.execute(
            text(
                "SELECT id, active_attachment_id, updated_at "
                "FROM candidate_profile ORDER BY id"
            )
        )
        return list(jobs) + list(profile.all())

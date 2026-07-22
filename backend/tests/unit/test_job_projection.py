from __future__ import annotations

import inspect

import pytest
from app.schemas.embeddings import EmbeddingVectorError
from app.schemas.jobs import JobPostExtraction
from app.services import jd_ingestion, job_reextraction
from app.services.job_projection import EmbeddingClient, embed_job_extraction

from tests.fakes.embeddings import FakeEmbeddingClient
from tests.support.graph_rebuild import embedding_vector


def _extraction() -> JobPostExtraction:
    return JobPostExtraction(
        title="Synthetic role",
        company="Synthetic company",
        summary="Synthetic summary",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        seniority="unknown",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="unknown",
        extraction_confidence=0.8,
    )


def test_embed_job_extraction_returns_locked_finite_contract() -> None:
    client: EmbeddingClient = FakeEmbeddingClient(
        vector=embedding_vector(0.25)
    )
    vector, model, dimensions = embed_job_extraction(_extraction(), client)
    assert vector == embedding_vector(0.25)
    assert dimensions == 1536
    assert model


def test_embed_job_extraction_rejects_non_finite_vectors() -> None:
    client = FakeEmbeddingClient(vector=[float("nan")] * 1536)
    with pytest.raises(EmbeddingVectorError):
        embed_job_extraction(_extraction(), client)


@pytest.mark.parametrize("module", (jd_ingestion, job_reextraction))
def test_embedding_protocol_has_one_owner(module: object) -> None:
    assert "class EmbeddingClient" not in inspect.getsource(module)

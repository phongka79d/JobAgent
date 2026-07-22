"""Shared low-level Job embedding and post-commit projection mechanics."""

from __future__ import annotations

from typing import Protocol

from app.schemas.embeddings import (
    LOCKED_EMBEDDING_DIMENSIONS,
    LOCKED_EMBEDDING_MODEL,
    validate_finite_vector,
)
from app.schemas.jobs import JobPostExtraction
from app.services.embedding_text import build_job_embedding_text_v1


class EmbeddingClient(Protocol):
    """Minimal fake-testable embedding surface."""

    def embed_text(self, text: str) -> list[float]:
        """Return one locked finite embedding vector."""
        ...


def embed_job_extraction(
    extraction: JobPostExtraction,
    embedding_client: EmbeddingClient,
) -> tuple[list[float], str, int]:
    """Build and validate the locked Job embedding contract."""
    text = build_job_embedding_text_v1(extraction)
    vector = embedding_client.embed_text(text)
    validated = validate_finite_vector(vector)
    return validated, LOCKED_EMBEDDING_MODEL, LOCKED_EMBEDDING_DIMENSIONS


__all__ = ["EmbeddingClient", "embed_job_extraction"]

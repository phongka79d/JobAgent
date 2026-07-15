"""Shared counting embedding fakes for ingestion, tools, and matching tests.

One FakeEmbeddingClient owner for Plan 5/6 integration tests. Do not add a
second local protocol/fake copy in product test modules.
"""

from __future__ import annotations

from app.schemas.embeddings import LOCKED_EMBEDDING_DIMENSIONS


def default_embedding_vector(seed: float = 0.01) -> list[float]:
    """Deterministic finite 1536-d vector used by default fake responses."""
    return [seed + (i * 1e-6) for i in range(LOCKED_EMBEDDING_DIMENSIONS)]


class FakeEmbeddingClient:
    """Deterministic embedding client recording call count and input texts.

    Compatible with :class:`~app.services.jd_ingestion.EmbeddingClient` and the
    matching orchestrator. Optionally raises a configured error to simulate
    provider failures without a second fake implementation.
    """

    def __init__(
        self,
        *,
        vector: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.vector = (
            list(vector) if vector is not None else default_embedding_vector()
        )
        self.error = error
        self.calls: list[str] = []

    @property
    def call_count(self) -> int:
        """Number of ``embed_text`` invocations recorded so far."""
        return len(self.calls)

    def embed_text(self, text: str) -> list[float]:
        """Record *text*, then return a copy of the scripted vector or raise."""
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        return list(self.vector)


__all__ = [
    "FakeEmbeddingClient",
    "default_embedding_vector",
]

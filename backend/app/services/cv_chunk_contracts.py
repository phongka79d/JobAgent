from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

from app.db.models.attachment_text_chunks import CHUNK_PREVIEW_MAX_CHARS

FAILURE_EMPTY_CHUNKS: Final[str] = "EMPTY_CHUNKS"
CHUNK_JOIN: Final[str] = "\n\n"


@dataclass(frozen=True, slots=True)
class CanonicalChunk:
    """One nonempty source-ordered text segment."""

    ordinal: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def token_estimate(self) -> int:
        return int(ceil(self.char_count / 4))

    @property
    def preview(self) -> str:
        return self.text[:CHUNK_PREVIEW_MAX_CHARS]

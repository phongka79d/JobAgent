"""Combined contained filesystem ops for staged/active attachment bytes.

Composes focused ownership modules: descriptor create/open, publication and
partial finalization, and public unlink. Callers import ContainedPathOps and
write helpers from here; platform handle adapters remain private siblings.
"""

from __future__ import annotations

from app.services.attachment_storage_fd import (
    ContainedFdOps,
    close_fd,
    coerce_chunk,
    fsync_fd,
    write_all,
)
from app.services.attachment_storage_publish import ContainedPublishOps

__all__ = [
    "ContainedPathOps",
    "close_fd",
    "coerce_chunk",
    "fsync_fd",
    "write_all",
]


class ContainedPathOps(ContainedFdOps, ContainedPublishOps):
    """Root-scoped filesystem primitives for staged/active attachment bytes."""

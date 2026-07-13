"""Single-source lowercase UUID v4 helpers for entity primary keys."""

from __future__ import annotations

import uuid


def new_uuid() -> str:
    """Return a new lowercase UUID v4 string for non-singleton entity IDs."""
    return str(uuid.uuid4()).lower()

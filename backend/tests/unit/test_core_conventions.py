"""Unit tests for shared UUID and UTC helpers (Plan 2 §7.2)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from app.core.ids import new_uuid
from app.core.time import utc_now

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def test_new_uuid_is_lowercase_uuid_v4() -> None:
    value = new_uuid()
    assert isinstance(value, str)
    assert value == value.lower()
    assert _UUID_V4_RE.match(value)
    parsed = uuid.UUID(value)
    assert parsed.version == 4
    assert str(parsed) == value


def test_new_uuid_values_are_unique() -> None:
    samples = {new_uuid() for _ in range(50)}
    assert len(samples) == 50


def test_utc_now_is_timezone_aware_utc() -> None:
    value = utc_now()
    assert isinstance(value, datetime)
    assert value.tzinfo is not None
    assert value.utcoffset() is not None
    assert value.utcoffset().total_seconds() == 0
    assert value.tzinfo is UTC


def test_utc_now_is_close_to_wall_clock() -> None:
    before = datetime.now(UTC)
    value = utc_now()
    after = datetime.now(UTC)
    assert before <= value <= after

"""Job Preferences contract (Master Plan §7.3; Plan 4 §7.2).

Profile facts and job preferences are separate documents. A CV address is not
automatically a preferred work location — preferences are only accepted when
explicitly proposed and validated here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.schemas.candidate import _normalize_string_list

MAX_PREFERENCE_LIST_ITEMS: Final[int] = 32
MAX_PREFERENCE_ITEM_LEN: Final[int] = 256


class WorkMode(StrEnum):
    """Acceptable work arrangement preference."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class TargetSeniority(StrEnum):
    """Target seniority preference; ``unknown`` is an explicit allowed value."""

    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class JobPreferences(BaseModel):
    """Explicit job-seeking preferences (singleton JSON document)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_roles: list[str] = Field(
        default_factory=list,
        max_length=MAX_PREFERENCE_LIST_ITEMS,
    )
    preferred_locations: list[str] = Field(
        default_factory=list,
        max_length=MAX_PREFERENCE_LIST_ITEMS,
    )
    acceptable_work_modes: list[WorkMode] = Field(
        default_factory=list,
        max_length=len(WorkMode),
    )
    target_seniority: list[TargetSeniority] = Field(
        default_factory=list,
        max_length=len(TargetSeniority),
    )

    @field_validator("target_roles", "preferred_locations")
    @classmethod
    def _string_lists(cls, value: list[str], info: ValidationInfo) -> list[str]:
        field_name = info.field_name or "preferences"
        return _normalize_string_list(
            value,
            max_items=MAX_PREFERENCE_LIST_ITEMS,
            max_item_len=MAX_PREFERENCE_ITEM_LEN,
            field_name=str(field_name),
        )

    @field_validator("acceptable_work_modes")
    @classmethod
    def _work_modes(cls, value: list[WorkMode]) -> list[WorkMode]:
        if not isinstance(value, list):
            raise ValueError("acceptable_work_modes must be a list")
        if len(value) > len(WorkMode):
            raise ValueError("too many acceptable_work_modes items")
        # Preserve order; drop exact duplicates while keeping enum identity.
        seen: set[WorkMode] = set()
        cleaned: list[WorkMode] = []
        for item in value:
            mode = item if isinstance(item, WorkMode) else WorkMode(str(item))
            if mode in seen:
                continue
            seen.add(mode)
            cleaned.append(mode)
        return cleaned

    @field_validator("target_seniority")
    @classmethod
    def _seniority(cls, value: list[TargetSeniority]) -> list[TargetSeniority]:
        if not isinstance(value, list):
            raise ValueError("target_seniority must be a list")
        if len(value) > len(TargetSeniority):
            raise ValueError("too many target_seniority items")
        seen: set[TargetSeniority] = set()
        cleaned: list[TargetSeniority] = []
        for item in value:
            level = (
                item
                if isinstance(item, TargetSeniority)
                else TargetSeniority(str(item))
            )
            if level in seen:
                continue
            seen.add(level)
            cleaned.append(level)
        return cleaned


__all__ = [
    "MAX_PREFERENCE_ITEM_LEN",
    "MAX_PREFERENCE_LIST_ITEMS",
    "JobPreferences",
    "TargetSeniority",
    "WorkMode",
]

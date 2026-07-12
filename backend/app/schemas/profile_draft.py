"""Pending profile-draft envelope (Plan 4 §7.2 / §7.4).

One pending draft is a validated ``CandidateProfile`` plus:

- optional **explicit** ``JobPreferences`` replacement (key present), or
- **omitted** preferences meaning "preferences unchanged"
- safe, bounded approval-summary display data

Serialization distinguishes omitted preference changes from a validated
preference replacement. Untyped provider extras are rejected.
"""

from __future__ import annotations

from typing import Any, Final, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.schemas.candidate import (
    MAX_DISPLAY_NAME_LEN,
    MAX_TITLE_LEN,
    CandidateProfile,
    _normalize_string_list,
)
from app.schemas.preferences import JobPreferences

MAX_APPROVAL_SUMMARY_TEXT_LEN: Final[int] = 512
MAX_APPROVAL_SKILL_PREVIEW: Final[int] = 20
MAX_APPROVAL_ROLE_PREVIEW: Final[int] = 16


class ProfileApprovalSummary(BaseModel):
    """Bounded, display-safe approval card fields (no raw CV / PII / paths)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(..., min_length=1, max_length=MAX_APPROVAL_SUMMARY_TEXT_LEN)
    current_title: str | None = Field(default=None, max_length=MAX_TITLE_LEN)
    skill_names: list[str] = Field(
        default_factory=list,
        max_length=MAX_APPROVAL_SKILL_PREVIEW,
    )
    experience_count: int = Field(default=0, ge=0)
    education_count: int = Field(default=0, ge=0)
    has_preference_changes: bool = False
    target_roles_preview: list[str] = Field(
        default_factory=list,
        max_length=MAX_APPROVAL_ROLE_PREVIEW,
    )

    @field_validator("summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("summary must be a non-empty string")
        return value.strip()

    @field_validator("current_title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("skill_names", "target_roles_preview")
    @classmethod
    def _previews(cls, value: list[str], info: ValidationInfo) -> list[str]:
        field_name = info.field_name or "preview"
        max_items = (
            MAX_APPROVAL_SKILL_PREVIEW
            if field_name == "skill_names"
            else MAX_APPROVAL_ROLE_PREVIEW
        )
        return _normalize_string_list(
            value,
            max_items=max_items,
            max_item_len=MAX_DISPLAY_NAME_LEN,
            field_name=str(field_name),
        )


class ProfileDraftDocument(BaseModel):
    """Validated pending draft JSON document for ``profile_drafts.draft_json``.

    Preference semantics:

    - ``preferences`` key **absent** → preferences unchanged on commit
    - ``preferences`` key **present** with a valid ``JobPreferences`` →
      explicit replacement
    - ``preferences: null`` is rejected (use omission for unchanged)
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile: CandidateProfile
    preferences: JobPreferences | None = None
    approval_summary: ProfileApprovalSummary

    @model_validator(mode="before")
    @classmethod
    def _reject_null_preferences(cls, data: Any) -> Any:
        if isinstance(data, dict) and "preferences" in data and data["preferences"] is None:
            raise ValueError(
                "preferences must be omitted when unchanged; null is not allowed"
            )
        return data

    def replaces_preferences(self) -> bool:
        """True when this draft proposes an explicit preference replacement."""
        return "preferences" in self.model_fields_set and self.preferences is not None

    @model_validator(mode="after")
    def _align_summary_preference_flag(self) -> Self:
        # Keep the display flag consistent with envelope semantics when the
        # draft actually carries a preference replacement.
        if self.replaces_preferences() and not self.approval_summary.has_preference_changes:
            raise ValueError(
                "approval_summary.has_preference_changes must be true when "
                "preferences are explicitly replaced"
            )
        if (
            not self.replaces_preferences()
            and self.approval_summary.has_preference_changes
        ):
            raise ValueError(
                "approval_summary.has_preference_changes must be false when "
                "preferences are omitted (unchanged)"
            )
        return self

    def to_storage_dict(self) -> dict[str, Any]:
        """Serialize for SQLite JSON: omit preferences when unchanged."""
        payload: dict[str, Any] = {
            "profile": self.profile.model_dump(mode="json"),
            "approval_summary": self.approval_summary.model_dump(mode="json"),
        }
        if self.replaces_preferences():
            assert self.preferences is not None
            payload["preferences"] = self.preferences.model_dump(mode="json")
        return payload

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> ProfileDraftDocument:
        """Parse a stored draft document with omit-vs-replace semantics."""
        return cls.model_validate(data)


def build_approval_summary(
    profile: CandidateProfile,
    *,
    preferences: JobPreferences | None = None,
    summary: str | None = None,
) -> ProfileApprovalSummary:
    """Derive a safe approval summary from a validated profile (+ optional prefs)."""
    skill_names = [item.skill.display_name for item in profile.skills][
        :MAX_APPROVAL_SKILL_PREVIEW
    ]
    has_prefs = preferences is not None
    roles = (
        list(preferences.target_roles)[:MAX_APPROVAL_ROLE_PREVIEW]
        if preferences is not None
        else []
    )
    text = summary
    if text is None:
        title = profile.current_title or "candidate profile"
        text = f"Review proposed {title}"
        if has_prefs:
            text = f"{text} and preference updates"
    return ProfileApprovalSummary(
        summary=text[:MAX_APPROVAL_SUMMARY_TEXT_LEN],
        current_title=profile.current_title,
        skill_names=skill_names,
        experience_count=len(profile.experiences),
        education_count=len(profile.education),
        has_preference_changes=has_prefs,
        target_roles_preview=roles,
    )


__all__ = [
    "MAX_APPROVAL_ROLE_PREVIEW",
    "MAX_APPROVAL_SKILL_PREVIEW",
    "MAX_APPROVAL_SUMMARY_TEXT_LEN",
    "ProfileApprovalSummary",
    "ProfileDraftDocument",
    "build_approval_summary",
]

"""Pure source-grounding guard for candidate identity fields."""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.profile import CandidateProfile
from app.services.skill_assertion_guard import normalize_assertion_text


def guard_profile_identity(
    profile: CandidateProfile,
    *,
    source_fragments: Sequence[str],
) -> CandidateProfile:
    """Null identity values that are not directly present in source text."""
    joined_source = normalize_assertion_text(" ".join(source_fragments))

    def grounded(value: str | None) -> str | None:
        if value is None:
            return None
        normalized_value = normalize_assertion_text(value)
        if normalized_value and normalized_value in joined_source:
            return value
        return None

    return profile.model_copy(
        update={
            "full_name": grounded(profile.full_name),
            "location": grounded(profile.location),
        }
    )

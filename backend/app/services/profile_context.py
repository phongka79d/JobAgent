"""Compact approved Candidate context projection (Plan 4 / Master §13.1).

Loads validated approved profile and preferences and returns a bounded display
summary for chat assembly and the future ``get_candidate_context`` tool.
Excludes raw PDF text, contact PII, internal storage paths, and provider
payloads. Callers own the ``AsyncSession`` transaction.

Repository imports are deferred inside methods to avoid package-level import
cycles (``schemas`` → ``chat`` → ``chat_context`` → this module).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.candidate import CandidateProfile, CandidateSkill
from app.schemas.preferences import JobPreferences

if TYPE_CHECKING:
    from app.repositories.preferences import PreferencesRepository
    from app.repositories.profiles import ProfileRepository

# Hard ceiling for compact skill / experience / education previews.
MAX_COMPACT_SKILLS: Final[int] = 40
MAX_COMPACT_EXPERIENCES: Final[int] = 20
MAX_COMPACT_EDUCATION: Final[int] = 15
MAX_COMPACT_LANGUAGES: Final[int] = 12
MAX_COMPACT_STRING: Final[int] = 2_000

# Keys that must never appear in compact context even if stored erroneously.
_PROHIBITED_CONTEXT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "pdf_body",
        "pdf_bytes",
        "pdf_text",
        "cv_body",
        "cv_text",
        "resume_body",
        "resume_text",
        "raw_document",
        "raw_content",
        "raw_text",
        "full_text",
        "document_body",
        "document_text",
        "document_bytes",
        "file_bytes",
        "content_bytes",
        "storage_path",
        "file_path",
        "filepath",
        "absolute_path",
        "email",
        "phone",
        "phone_number",
        "contact_address",
        "address",
        "provider_payload",
        "provider_raw",
        "repair_history",
        "llm_raw",
        "embedding",
        "embedding_vector",
    }
)


class ProfileContextError(ValueError):
    """Compact context assembly failed without disclosing payload values."""


@dataclass(frozen=True, slots=True)
class CompactCandidateContext:
    """Bounded approved profile/preferences projection for Agent/tools."""

    profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    active_attachment_id: str | None

    def as_dict(self) -> dict[str, Any] | None:
        """Return a mapping for Agent state, or ``None`` when empty."""
        if (
            self.profile is None
            and self.preferences is None
            and self.active_attachment_id is None
        ):
            return None
        out: dict[str, Any] = {}
        if self.profile is not None:
            out["profile"] = self.profile
        if self.preferences is not None:
            out["preferences"] = self.preferences
        if self.active_attachment_id is not None:
            out["active_attachment_id"] = self.active_attachment_id
        return out


def _truncate_str(value: str, *, max_len: int = MAX_COMPACT_STRING) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _compact_skill(skill: CandidateSkill) -> dict[str, Any]:
    ref = skill.skill
    return {
        "canonical_key": ref.canonical_key,
        "display_name": ref.display_name,
        "status": str(ref.status),
        "proficiency": str(skill.proficiency),
        "years": skill.years,
        "source": str(skill.source),
        "excluded": skill.excluded,
    }


def project_compact_profile(profile: CandidateProfile) -> dict[str, Any]:
    """Project a validated profile to bounded display facts (no raw CV body)."""
    skills = [
        _compact_skill(skill_item)
        for skill_item in profile.skills[:MAX_COMPACT_SKILLS]
    ]
    experiences: list[dict[str, Any]] = []
    for exp in profile.experiences[:MAX_COMPACT_EXPERIENCES]:
        experiences.append(
            {
                "title": exp.title,
                "organization": exp.organization,
                "date_range": exp.date_range,
                "summary": (
                    _truncate_str(exp.summary) if exp.summary is not None else None
                ),
            }
        )
    education: list[dict[str, Any]] = []
    for edu in profile.education[:MAX_COMPACT_EDUCATION]:
        education.append(
            {
                "institution": edu.institution,
                "credential": edu.credential,
                "field_of_study": edu.field_of_study,
                "date_range": edu.date_range,
            }
        )
    languages: list[dict[str, Any]] = []
    for lang in profile.languages[:MAX_COMPACT_LANGUAGES]:
        languages.append(
            {
                "language": lang.language,
                "proficiency": lang.proficiency,
            }
        )
    return {
        "summary": _truncate_str(profile.summary),
        "current_title": profile.current_title,
        "total_experience_years": profile.total_experience_years,
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "languages": languages,
        "extraction_confidence": profile.extraction_confidence,
    }


def project_compact_preferences(preferences: JobPreferences) -> dict[str, Any]:
    """Project validated preferences to a plain JSON-safe mapping."""
    return {
        "target_roles": list(preferences.target_roles),
        "preferred_locations": list(preferences.preferred_locations),
        "acceptable_work_modes": [str(m) for m in preferences.acceptable_work_modes],
        "target_seniority": [str(s) for s in preferences.target_seniority],
    }


def _assert_no_prohibited_keys(data: Mapping[str, Any], *, path: str = "") -> None:
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized = key.strip().lower().replace("-", "_")
        if normalized in _PROHIBITED_CONTEXT_KEYS:
            raise ProfileContextError("prohibited field in compact context")
        if any(
            token in normalized
            for token in (
                "pdf_body",
                "cv_text",
                "storage_path",
                "provider_payload",
                "raw_document",
            )
        ):
            raise ProfileContextError("prohibited field in compact context")
        if isinstance(value, Mapping):
            _assert_no_prohibited_keys(value, path=f"{path}.{key}" if path else key)


class ProfileContextService:
    """Load compact approved context via validated repositories."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        profiles: ProfileRepository | None = None,
        preferences: PreferencesRepository | None = None,
    ) -> None:
        self._session = session
        self._profiles = profiles
        self._preferences = preferences

    def _profile_repo(self) -> ProfileRepository:
        if self._profiles is not None:
            return self._profiles
        from app.repositories.profiles import ProfileRepository

        self._profiles = ProfileRepository(self._session)
        return self._profiles

    def _prefs_repo(self) -> PreferencesRepository:
        if self._preferences is not None:
            return self._preferences
        from app.repositories.preferences import PreferencesRepository

        self._preferences = PreferencesRepository(self._session)
        return self._preferences

    async def load_compact_approved_context(self) -> CompactCandidateContext:
        """Return bounded approved profile/preferences, or empty slices.

        Invalid stored JSON never crosses as an approved domain object: it
        raises ``ProfileContextError`` (fail closed).
        """
        from app.repositories.preferences import (
            PreferencesRepositoryError,
            PreferencesValidationError,
        )
        from app.repositories.profiles import (
            ProfileRepositoryError,
            ProfileValidationError,
        )

        try:
            approved = await self._profile_repo().get()
        except ProfileValidationError as exc:
            raise ProfileContextError("invalid stored profile") from exc
        except ProfileRepositoryError as exc:
            raise ProfileContextError("profile load failed") from exc

        try:
            prefs = await self._prefs_repo().get()
        except PreferencesValidationError as exc:
            raise ProfileContextError("invalid stored preferences") from exc
        except PreferencesRepositoryError as exc:
            raise ProfileContextError("preferences load failed") from exc

        profile_view: dict[str, Any] | None = None
        active_id: str | None = None
        if approved is not None:
            profile_view = project_compact_profile(approved.profile)
            _assert_no_prohibited_keys(profile_view)
            if approved.active_attachment_id is not None:
                active_id = str(approved.active_attachment_id)

        prefs_view: dict[str, Any] | None = None
        if prefs is not None:
            prefs_view = project_compact_preferences(prefs)
            _assert_no_prohibited_keys(prefs_view)

        return CompactCandidateContext(
            profile=profile_view,
            preferences=prefs_view,
            active_attachment_id=active_id,
        )

    async def load_optional_context_dict(self) -> dict[str, Any] | None:
        """Convenience wrapper used by chat assembly and tools."""
        return (await self.load_compact_approved_context()).as_dict()


def active_attachment_id_str(value: UUID | None) -> str | None:
    """Format attachment UUID as an ID-only string (no path)."""
    if value is None:
        return None
    return str(value)

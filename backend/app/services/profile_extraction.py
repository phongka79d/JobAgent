"""Structured CV profile extraction via ShopAIKey (Plan 4 §7.4).

Owns the LLM-backed Candidate Profile extraction path:

* pypdf layout/normal text from :mod:`app.services.pdf_extraction`
* locked ``gpt-4o-mini`` via the ShopAIKey adapter and
  ``with_structured_output(..., method='json_schema', strict=True)``
* at most one schema-repair request when structured output is invalid
* at most one timeout/rate-limit retry
* deterministic skill normalization through the sole normalizer

Raw extracted CV text is transient: never logged, persisted, or returned in
tool/public contracts. Callers pass file paths or openable sources only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL, build_shopaikey_chat
from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    EducationItem,
    ExperienceItem,
    JobPreferences,
    LanguageItem,
    ProfileDraftPayload,
    parse_candidate_profile,
    parse_profile_draft_payload,
)
from app.schemas.skills import SkillRef
from app.services.pdf_extraction import (
    NO_EXTRACTABLE_TEXT,
    PdfMalformedError,
    extract_pdf_text,
)
from app.services.provider_retry import (
    FAILURE_PROVIDER_ERROR,
    FAILURE_PROVIDER_RATE_LIMIT,
    FAILURE_PROVIDER_TIMEOUT,
    ProviderRetryError,
    classify_provider_error,
    invoke_with_provider_retry,
)
from app.services.skill_normalization import SkillNormalizer

logger = logging.getLogger(__name__)

# Stable failure codes (attachment / tool surfaces).
# Provider codes are owned by provider_retry; re-exported for callers/tests.
FAILURE_NO_EXTRACTABLE_TEXT: Final[str] = NO_EXTRACTABLE_TEXT
FAILURE_MALFORMED_PDF: Final[str] = "MALFORMED_PDF"
FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"

STRUCTURED_OUTPUT_METHOD: Final[str] = "json_schema"
STRUCTURED_OUTPUT_STRICT: Final[bool] = True
EXTRACTION_SCHEMA_STRATEGY: Final[str] = "strict_json_schema"

_MAX_EVIDENCE_SNIPPET_LEN: Final[int] = 240
_MAX_REPAIR_ATTEMPTS: Final[int] = 1

_SYSTEM_PROMPT: Final[str] = (
    "You extract a Candidate Profile from CV text. Return only structured JSON "
    "matching the schema. Rules: (1) facts only — never invent job preferences; "
    "(2) evidence must be short verbatim snippets from the CV; (3) do not invent "
    "precise years or proficiency without explicit evidence — use null years and "
    "proficiency 'unknown' when unsure; (4) skill names are free-text labels only "
    "(aliases/categories are filled by a separate normalizer); (5) source is always "
    "'cv' and excluded is always false for extraction."
)


class ProfileExtractionError(Exception):
    """Extraction failed with a stable application failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- LLM-facing extraction schema (no Field min/max; strict JSON schema safe) ---


class ExtractedSkillItem(BaseModel):
    """LLM skill row before deterministic SkillRef normalization."""

    name: str
    confidence: float
    proficiency: Literal["beginner", "intermediate", "advanced", "unknown"]
    years: float | None
    evidence: list[str]


class ExtractedCandidateProfile(BaseModel):
    """LLM structured output for CV facts (validated again as CandidateProfile)."""

    summary: str
    current_title: str | None
    total_experience_years: float | None
    skills: list[ExtractedSkillItem]
    experiences: list[ExperienceItem]
    education: list[EducationItem]
    languages: list[LanguageItem]
    extraction_confidence: float


class StructuredProfileInvoker(Protocol):
    """Fake-testable structured extraction call surface.

    Production uses ShopAIKey ``with_structured_output``; tests inject fakes
    that never touch the network.
    """

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedCandidateProfile | dict[str, Any]:
        """Return structured profile payload or raise provider/validation errors."""
        ...


@dataclass(frozen=True, slots=True)
class ExtractionOutcome:
    """Validated draft payload after extraction + normalization (no DB work)."""

    draft: ProfileDraftPayload
    schema_repairs_used: int
    provider_retries_used: int


def empty_job_preferences() -> JobPreferences:
    """CV extraction never invents preferences (facts/preferences separation)."""
    return JobPreferences(
        target_roles=[],
        preferred_locations=[],
        acceptable_work_modes=[],
        target_seniority=[],
    )


def _clip_evidence(snippets: list[str]) -> list[str]:
    clipped: list[str] = []
    for item in snippets:
        text = " ".join(str(item).split())
        if not text:
            continue
        if len(text) > _MAX_EVIDENCE_SNIPPET_LEN:
            text = text[:_MAX_EVIDENCE_SNIPPET_LEN]
        clipped.append(text)
    return clipped


def extracted_to_candidate_profile(
    extracted: ExtractedCandidateProfile,
    normalizer: SkillNormalizer,
) -> CandidateProfile:
    """Map LLM extraction to validated CandidateProfile with normalized skills."""
    skills: list[CandidateSkill] = []
    for row in extracted.skills:
        name = " ".join(row.name.split())
        if not name:
            continue
        ref: SkillRef = normalizer.normalize_name(name)
        # Clamp confidence defensively before full model validation.
        conf = float(row.confidence)
        if conf < 0.0:
            conf = 0.0
        elif conf > 1.0:
            conf = 1.0
        skills.append(
            CandidateSkill(
                skill=ref,
                confidence=conf,
                proficiency=row.proficiency,
                years=row.years,
                source="cv",
                excluded=False,
                evidence=_clip_evidence(list(row.evidence)),
            )
        )

    ext_conf = float(extracted.extraction_confidence)
    if ext_conf < 0.0:
        ext_conf = 0.0
    elif ext_conf > 1.0:
        ext_conf = 1.0

    raw_profile = {
        "summary": extracted.summary,
        "current_title": extracted.current_title,
        "total_experience_years": extracted.total_experience_years,
        "skills": [s.model_dump(mode="json") for s in skills],
        "experiences": [e.model_dump(mode="json") for e in extracted.experiences],
        "education": [e.model_dump(mode="json") for e in extracted.education],
        "languages": [lang.model_dump(mode="json") for lang in extracted.languages],
        "extraction_confidence": ext_conf,
    }
    return parse_candidate_profile(raw_profile)


def build_draft_from_extracted(
    extracted: ExtractedCandidateProfile,
    normalizer: SkillNormalizer,
) -> ProfileDraftPayload:
    """Build a fully validated ProfileDraftPayload (empty preferences)."""
    profile = extracted_to_candidate_profile(extracted, normalizer)
    return parse_profile_draft_payload(
        {
            "candidate_profile": profile.model_dump(mode="json"),
            "job_preferences": empty_job_preferences().model_dump(mode="json"),
        }
    )


def _coerce_extracted(raw: Any) -> ExtractedCandidateProfile:
    if isinstance(raw, ExtractedCandidateProfile):
        return raw
    if isinstance(raw, BaseModel):
        return ExtractedCandidateProfile.model_validate(raw.model_dump())
    if isinstance(raw, str):
        return ExtractedCandidateProfile.model_validate(json.loads(raw))
    return ExtractedCandidateProfile.model_validate(raw)


class ShopAIKeyStructuredProfileInvoker:
    """Production invoker: ShopAIKey + strict JSON schema structured output."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model if model is not None else build_shopaikey_chat()
        # Verified Phase 0 strategy: response_format json_schema with strict=true.
        self._structured = self._model.with_structured_output(
            ExtractedCandidateProfile,
            method=STRUCTURED_OUTPUT_METHOD,
            strict=STRUCTURED_OUTPUT_STRICT,
        )

    @property
    def model_name(self) -> str:
        name = getattr(self._model, "model_name", None)
        if isinstance(name, str) and name:
            return name
        return LOCKED_CHAT_MODEL

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedCandidateProfile:
        del is_repair  # repair is encoded in the message list by the caller
        result = self._structured.invoke(list(messages))
        return _coerce_extracted(result)


def _build_messages(cv_text: str, *, repair_error: str | None) -> list[Any]:
    # Raw CV text appears only in this transient prompt; never in ToolResult/logs.
    messages: list[Any] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Extract the Candidate Profile from the following CV text.\n\n"
                f"--- CV TEXT START ---\n{cv_text}\n--- CV TEXT END ---"
            )
        ),
    ]
    if repair_error is not None:
        messages.append(
            HumanMessage(
                content=(
                    "Your previous structured output failed validation with this "
                    f"error:\n{repair_error}\n"
                    "Repair: return one valid ExtractedCandidateProfile JSON object "
                    "only. Keep evidence short and do not invent preferences."
                )
            )
        )
    return messages


def _invoke_with_provider_retry(
    invoker: StructuredProfileInvoker,
    messages: Sequence[Any],
    *,
    is_repair: bool,
) -> tuple[ExtractedCandidateProfile, int]:
    """Call structured invoker via shared provider retry; map domain errors."""

    def _call() -> ExtractedCandidateProfile:
        raw = invoker.invoke_structured(messages, is_repair=is_repair)
        return _coerce_extracted(raw)

    try:
        return invoke_with_provider_retry(_call)
    except ProviderRetryError as exc:
        raise ProfileExtractionError(exc.code, exc.message) from exc


def extract_profile_from_pdf(
    source: Path | str | bytes | BinaryIO,
    *,
    invoker: StructuredProfileInvoker,
    normalizer: SkillNormalizer,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> ExtractionOutcome:
    """Extract + validate a ProfileDraftPayload from a PDF source.

    Parameters
    ----------
    source:
        PDF path, bytes, or binary stream (same as pdf_extraction).
    invoker:
        Structured LLM invoker (production ShopAIKey or test fake).
    normalizer:
        Sole skill normalizer instance.
    extract_text_fn:
        Optional override for unit tests (defaults to extract_pdf_text).
    """
    extract = extract_text_fn if extract_text_fn is not None else extract_pdf_text
    try:
        extraction = extract(source)
    except PdfMalformedError as exc:
        raise ProfileExtractionError(
            FAILURE_MALFORMED_PDF,
            str(exc) or "PDF is malformed or unreadable",
        ) from exc

    if not extraction.has_meaningful_text or extraction.preferred_text is None:
        raise ProfileExtractionError(
            FAILURE_NO_EXTRACTABLE_TEXT,
            "PDF has no meaningful extractable digital text",
        )

    cv_text = extraction.preferred_text
    # Do not log cv_text or full extraction payloads.
    logger.debug(
        "profile extraction starting pages=%s strategy=%s",
        extraction.page_count,
        EXTRACTION_SCHEMA_STRATEGY,
    )

    repairs_used = 0
    provider_retries_total = 0
    repair_error: str | None = None

    while True:
        messages = _build_messages(cv_text, repair_error=repair_error)
        is_repair = repair_error is not None
        try:
            extracted, retries = _invoke_with_provider_retry(
                invoker, messages, is_repair=is_repair
            )
            provider_retries_total += retries
            draft = build_draft_from_extracted(extracted, normalizer)
            return ExtractionOutcome(
                draft=draft,
                schema_repairs_used=repairs_used,
                provider_retries_used=provider_retries_total,
            )
        except ProfileExtractionError:
            raise
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if repairs_used >= _MAX_REPAIR_ATTEMPTS:
                raise ProfileExtractionError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    "structured output invalid after one repair attempt",
                ) from exc
            repairs_used += 1
            repair_error = str(exc)[:500]
            continue


def compact_profile_summary(profile: CandidateProfile) -> dict[str, Any]:
    """IDs-and-counts summary only — no evidence bodies or raw CV text."""
    return {
        "current_title": profile.current_title,
        "skill_count": len(profile.skills),
        "experience_count": len(profile.experiences),
        "education_count": len(profile.education),
        "language_count": len(profile.languages),
        "extraction_confidence": profile.extraction_confidence,
        "summary_excerpt": (profile.summary or "")[:160],
    }


def compact_draft_summary(draft: ProfileDraftPayload) -> dict[str, Any]:
    """Compact draft summary for ToolResult.data / arguments_summary_json."""
    base = compact_profile_summary(draft.candidate_profile)
    base["draft_id"] = "current"
    base["preference_role_count"] = len(draft.job_preferences.target_roles)
    return base


__all__ = [
    "EXTRACTION_SCHEMA_STRATEGY",
    "ExtractedCandidateProfile",
    "ExtractedSkillItem",
    "ExtractionOutcome",
    "FAILURE_INVALID_STRUCTURED_OUTPUT",
    "FAILURE_MALFORMED_PDF",
    "FAILURE_NO_EXTRACTABLE_TEXT",
    "FAILURE_PROVIDER_ERROR",
    "FAILURE_PROVIDER_RATE_LIMIT",
    "FAILURE_PROVIDER_TIMEOUT",
    "ProfileExtractionError",
    "STRUCTURED_OUTPUT_METHOD",
    "STRUCTURED_OUTPUT_STRICT",
    "ShopAIKeyStructuredProfileInvoker",
    "StructuredProfileInvoker",
    "build_draft_from_extracted",
    "classify_provider_error",
    "compact_draft_summary",
    "compact_profile_summary",
    "empty_job_preferences",
    "extract_profile_from_pdf",
    "extracted_to_candidate_profile",
]

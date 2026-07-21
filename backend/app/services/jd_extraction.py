"""Structured JD extraction via ShopAIKey (Plan 5 §7.4 / Plan 15).

Locked gpt-4o-mini structured output, at most one schema-or-guard repair, shared
provider retry, pure semantic guard before SkillNormalizer projection. Raw JD
text is transient; no SQLite, embeddings, Neo4j, or jd_quality assignment.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, ValidationError

from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL, build_shopaikey_chat
from app.schemas.jobs import JobPostExtraction, JobSkill, parse_job_post_extraction
from app.schemas.skills import SkillRef
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

FAILURE_INVALID_STRUCTURED_OUTPUT: Final[str] = "INVALID_STRUCTURED_OUTPUT"
_INVALID_AFTER_REPAIR_MESSAGE: Final[str] = (
    "structured output invalid after one repair attempt"
)

STRUCTURED_OUTPUT_METHOD: Final[str] = "json_schema"
STRUCTURED_OUTPUT_STRICT: Final[bool] = True
EXTRACTION_SCHEMA_STRATEGY: Final[str] = "strict_json_schema"

_MAX_EVIDENCE_SNIPPET_LEN: Final[int] = 240
_MAX_REPAIR_ATTEMPTS: Final[int] = 1

_SYSTEM_PROMPT: Final[str] = (
    "You extract structured Job Description facts from JD text. Return only "
    "structured JSON matching the schema. Rules: "
    "(1) extract title, company, and location only when directly supported by "
    "the source — do not infer them from general role content; "
    "(2) responsibilities are concise verbatim source facts, not rewritten "
    "marketing summaries; "
    "(3) every skill name is one atomic capability or technology — lists and "
    "alternatives such as 'Python, FastAPI' or 'Git/Docker/Kubernetes' become "
    "separate rows that may share evidence; "
    "(4) technical names containing punctuation, including C/C++, .NET, Node.js, "
    "and CI/CD, remain single labels; "
    "(5) mandatory or neutrally listed qualifications are required; a skill is "
    "preferred only when the source explicitly marks it optional, preferred, "
    "advantageous, or equivalent wording; "
    "(6) a canonical skill may occur at most once and never in both required "
    "and preferred groups; "
    "(7) skill evidence is a short verbatim source snippet — do not produce "
    "aliases, canonical keys, categories, relationships, or jd_quality. "
    "(8) extract every source-supported technical skill, framework, model, "
    "method, or platform named in responsibilities or qualifications; do not omit "
    "methods listed in qualification enumerations. "
    "Use seniority/work_mode 'unknown' when not explicit; use null for missing "
    "title/company/location/experience years."
)

_SCHEMA_REPAIR_INSTRUCTION: Final[str] = (
    "Previous structured output failed schema validation for ExtractedJobPost. "
    "Return one valid ExtractedJobPost JSON object only matching the schema. "
    "Use one atomic skill per row; protect C/C++, .NET, Node.js, and CI/CD as "
    "single labels; mandatory or neutral skills are required; preferred only "
    "when the source explicitly marks optional/preferred; keep canonical skills "
    "unique and required/preferred disjoint; evidence short and verbatim. "
    "Extract every source-supported technical skill and do not omit methods listed "
    "in qualification enumerations. "
    "Do not invent aliases, relationships, or jd_quality."
)

_GUARD_REPAIR_TRAILER: Final[str] = (
    "Repair: return one valid ExtractedJobPost JSON object only. "
    "Use one atomic skill per row; mandatory or neutral skills are required; "
    "preferred only when the source explicitly marks optional/preferred; keep "
    "canonical skills unique and required/preferred disjoint. Do not invent "
    "aliases, relationships, or jd_quality. Evidence must be short and verbatim. "
    "Extract every source-supported technical skill and do not omit methods listed "
    "in qualification enumerations."
)


class JdExtractionError(Exception):
    """JD extraction failed with a stable application failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- LLM-facing extraction schema (no SkillRef; strict JSON schema safe) ---


class ExtractedJobSkillItem(BaseModel):
    """LLM skill row before deterministic SkillRef normalization."""

    model_config = ConfigDict(extra="forbid")

    name: str
    confidence: float
    evidence: list[str]


class ExtractedJobPost(BaseModel):
    """LLM structured output for JD facts (validated again as JobPostExtraction)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None
    company: str | None
    summary: str
    responsibilities: list[str]
    required_skills: list[ExtractedJobSkillItem]
    preferred_skills: list[ExtractedJobSkillItem]
    seniority: Literal["intern", "junior", "mid", "senior", "lead", "unknown"]
    min_experience_years: float | None
    max_experience_years: float | None
    location: str | None
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"]
    extraction_confidence: float


class StructuredJdInvoker(Protocol):
    """Fake-testable structured JD extraction call surface.

    Production uses ShopAIKey ``with_structured_output``; tests inject fakes
    that never touch the network.
    """

    def invoke_structured(
        self,
        messages: Sequence[Any],
        *,
        is_repair: bool = False,
    ) -> ExtractedJobPost | dict[str, Any]:
        """Return structured JD payload or raise provider/validation errors."""
        ...


@dataclass(frozen=True, slots=True)
class JdExtractionOutcome:
    """Validated normalized JobPostExtraction (no DB, quality, or embeddings)."""

    extraction: JobPostExtraction
    schema_repairs_used: int
    provider_retries_used: int


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


def _normalize_skill_rows(
    rows: list[ExtractedJobSkillItem],
    normalizer: SkillNormalizer,
) -> list[JobSkill]:
    """Normalize free-text skills; preserve confidences for JobSkill validation.

    Whitespace-only names are not dropped: SkillNormalizer raises
    ``SkillTaxonomyError`` (a ``ValueError``), which the extract loop treats as
    schema-invalid and routes through the single repair path.
    """
    skills: list[JobSkill] = []
    for row in rows:
        name = " ".join(row.name.split())
        ref: SkillRef = normalizer.normalize_name(name)
        # No clamping: authoritative JobSkill bounds reject out-of-range values.
        skills.append(
            JobSkill(
                skill=ref,
                confidence=float(row.confidence),
                evidence=_clip_evidence(list(row.evidence)),
            )
        )
    return skills


def extracted_to_job_post(
    extracted: ExtractedJobPost,
    normalizer: SkillNormalizer,
) -> JobPostExtraction:
    """Map LLM extraction to validated JobPostExtraction with normalized skills."""
    raw = {
        "title": extracted.title,
        "company": extracted.company,
        "summary": extracted.summary,
        "responsibilities": list(extracted.responsibilities),
        "required_skills": [
            s.model_dump(mode="json")
            for s in _normalize_skill_rows(extracted.required_skills, normalizer)
        ],
        "preferred_skills": [
            s.model_dump(mode="json")
            for s in _normalize_skill_rows(extracted.preferred_skills, normalizer)
        ],
        "seniority": extracted.seniority,
        "min_experience_years": extracted.min_experience_years,
        "max_experience_years": extracted.max_experience_years,
        "location": extracted.location,
        "work_mode": extracted.work_mode,
        # No clamping: JobPostExtraction Field(ge=0, le=1) is authoritative.
        "extraction_confidence": float(extracted.extraction_confidence),
    }
    return parse_job_post_extraction(raw)


def _coerce_extracted(raw: Any) -> ExtractedJobPost:
    if isinstance(raw, ExtractedJobPost):
        return raw
    if isinstance(raw, BaseModel):
        return ExtractedJobPost.model_validate(raw.model_dump())
    if isinstance(raw, str):
        return ExtractedJobPost.model_validate(json.loads(raw))
    return ExtractedJobPost.model_validate(raw)


class ShopAIKeyStructuredJdInvoker:
    """Production invoker: ShopAIKey + strict JSON schema structured output."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model if model is not None else build_shopaikey_chat()
        self._structured = self._model.with_structured_output(
            ExtractedJobPost,
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
    ) -> ExtractedJobPost:
        del is_repair  # repair is encoded in the message list by the caller
        result = self._structured.invoke(list(messages))
        return _coerce_extracted(result)


def _format_guard_repair_instruction(
    issues: Sequence[Any],
    omitted_issue_count: int,
) -> str:
    """Build a sanitized guard-repair message (codes/paths/counts only)."""
    lines = [
        "Previous structured output failed semantic validation.",
        "Issues (code path count):",
    ]
    for issue in issues:
        lines.append(f"- {issue.code} {issue.field_path} {issue.count}")
    if omitted_issue_count > 0:
        lines.append(f"omitted_issue_count={omitted_issue_count}")
    lines.append(_GUARD_REPAIR_TRAILER)
    return "\n".join(lines)


def _build_messages(jd_text: str, *, repair_instruction: str | None) -> list[Any]:
    # Raw JD text appears only in this transient prompt; never in ToolResult/logs.
    messages: list[Any] = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Extract Job Description facts from the following JD text.\n\n"
                f"--- JD TEXT START ---\n{jd_text}\n--- JD TEXT END ---"
            )
        ),
    ]
    if repair_instruction is not None:
        messages.append(HumanMessage(content=repair_instruction))
    return messages


def _invoke_structured(
    invoker: StructuredJdInvoker,
    messages: Sequence[Any],
    *,
    is_repair: bool,
) -> tuple[ExtractedJobPost, int]:
    """Call structured invoker via shared provider retry; map domain errors."""

    def _call() -> ExtractedJobPost:
        raw = invoker.invoke_structured(messages, is_repair=is_repair)
        return _coerce_extracted(raw)

    try:
        return invoke_with_provider_retry(_call)
    except ProviderRetryError as exc:
        raise JdExtractionError(exc.code, exc.message) from exc


def extract_job_post_from_text(
    jd_text: str,
    *,
    invoker: StructuredJdInvoker,
    normalizer: SkillNormalizer,
) -> JdExtractionOutcome:
    """Extract, guard, then normalize a JobPostExtraction from transient JD text.

    Order: provider structured output → pure semantic guard → SkillNormalizer
    projection. Schema and guard failures share one repair attempt; only an
    accepted guarded result is normalized.
    """
    # Lazy import avoids circular load with jd_extraction_guard.
    from app.services.jd_extraction_guard import guard_extracted_job_post

    if not isinstance(jd_text, str):
        raise JdExtractionError(
            FAILURE_INVALID_STRUCTURED_OUTPUT,
            "jd text must be a string",
        )

    # Do not log jd_text, evidence, or full extraction payloads.
    logger.debug("jd extraction starting strategy=%s", EXTRACTION_SCHEMA_STRATEGY)

    repairs_used = 0
    provider_retries_total = 0
    repair_instruction: str | None = None

    while True:
        messages = _build_messages(jd_text, repair_instruction=repair_instruction)
        is_repair = repair_instruction is not None
        try:
            extracted, retries = _invoke_structured(
                invoker, messages, is_repair=is_repair
            )
            provider_retries_total += retries

            guard_result = guard_extracted_job_post(jd_text, extracted, normalizer)
            if not guard_result.accepted:
                if repairs_used >= _MAX_REPAIR_ATTEMPTS:
                    raise JdExtractionError(
                        FAILURE_INVALID_STRUCTURED_OUTPUT,
                        _INVALID_AFTER_REPAIR_MESSAGE,
                    )
                repairs_used += 1
                repair_instruction = _format_guard_repair_instruction(
                    guard_result.issues,
                    guard_result.omitted_issue_count,
                )
                logger.debug(
                    "jd extraction guard repair issue_count=%s omitted=%s",
                    len(guard_result.issues),
                    guard_result.omitted_issue_count,
                )
                continue

            # Only after guard acceptance: final SkillNormalizer projection.
            extraction = extracted_to_job_post(extracted, normalizer)
            return JdExtractionOutcome(
                extraction=extraction,
                schema_repairs_used=repairs_used,
                provider_retries_used=provider_retries_total,
            )
        except JdExtractionError:
            raise
        except (ValidationError, json.JSONDecodeError, TypeError, ValueError):
            if repairs_used >= _MAX_REPAIR_ATTEMPTS:
                raise JdExtractionError(
                    FAILURE_INVALID_STRUCTURED_OUTPUT,
                    _INVALID_AFTER_REPAIR_MESSAGE,
                ) from None
            repairs_used += 1
            # Fixed generic schema instruction — never echo exception/payload values.
            repair_instruction = _SCHEMA_REPAIR_INSTRUCTION
            logger.debug("jd extraction schema repair attempt=%s", repairs_used)
            continue


__all__ = [
    "EXTRACTION_SCHEMA_STRATEGY",
    "ExtractedJobPost",
    "ExtractedJobSkillItem",
    "FAILURE_INVALID_STRUCTURED_OUTPUT",
    "FAILURE_PROVIDER_ERROR",
    "FAILURE_PROVIDER_RATE_LIMIT",
    "FAILURE_PROVIDER_TIMEOUT",
    "JdExtractionError",
    "JdExtractionOutcome",
    "STRUCTURED_OUTPUT_METHOD",
    "STRUCTURED_OUTPUT_STRICT",
    "ShopAIKeyStructuredJdInvoker",
    "StructuredJdInvoker",
    "classify_provider_error",
    "extract_job_post_from_text",
    "extracted_to_job_post",
]

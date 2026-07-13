"""Profile draft proposal orchestration (Plan 4 §7.4–7.5).

Owns ``propose_profile_from_cv`` and ``propose_profile_update`` service behavior:

* Active attachment → return approved profile (no extraction / no draft write)
* Staged attachment already backing ``profile_drafts('current')`` → return draft
* Other valid staged attachment → extract, validate, upsert singleton draft,
  then remove the prior unreferenced staged row and best-effort delete its file
* Extraction failure → mark the same staged row ``failed`` with a stable code;
  retain file for exact-hash retry
* ``propose_profile_update`` applies profile/preference/skill corrections to the
  current draft or an active-context copy, validates the full
  ``ProfileDraftPayload``, and upserts only ``profile_drafts('current')``

Never writes active profile/preferences. Never registers tools.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.attachments import (
    ATTACHMENT_STATE_ACTIVE,
    ATTACHMENT_STATE_STAGED,
    Attachment,
)
from app.db.models.profiles import (
    CANDIDATE_PROFILE_ID,
    JOB_PREFERENCE_KEYS,
    PROFILE_DRAFT_ID,
)
from app.repositories import attachments as att_repo
from app.repositories import profiles as profile_repo
from app.schemas.profile import (
    CandidateProfile,
    CandidateSkill,
    JobPreferences,
    ProfileDraftPayload,
    parse_candidate_profile,
    parse_job_preferences,
    parse_profile_draft_payload,
)
from app.schemas.tools import ToolResult
from app.services.profile_extraction import (
    FAILURE_NO_EXTRACTABLE_TEXT,
    ProfileExtractionError,
    StructuredProfileInvoker,
    compact_draft_summary,
    compact_profile_summary,
    empty_job_preferences,
    extract_profile_from_pdf,
)
from app.services.skill_normalization import SkillNormalizer, SkillTaxonomyError
from app.storage.attachments import AttachmentStorage

logger = logging.getLogger(__name__)

# Tool / service stable codes beyond extraction failures.
ERROR_ATTACHMENT_NOT_FOUND: str = "ATTACHMENT_NOT_FOUND"
ERROR_ATTACHMENT_NOT_PROCESSABLE: str = "ATTACHMENT_NOT_PROCESSABLE"
ERROR_ACTIVE_PROFILE_MISSING: str = "ACTIVE_PROFILE_MISSING"
ERROR_FILE_MISSING: str = "ATTACHMENT_FILE_MISSING"
ERROR_NO_PROFILE_CONTEXT: str = "NO_PROFILE_CONTEXT"
ERROR_EMPTY_UPDATE: str = "EMPTY_UPDATE"
ERROR_INVALID_PROFILE_UPDATE: str = "INVALID_PROFILE_UPDATE"

ProposalKind = Literal["active_profile", "existing_draft", "new_draft"]
UpdateBaseKind = Literal["current_draft", "active_context"]

# Candidate-profile fields that may be patched without skill merge rules.
_PROFILE_PATCH_KEYS: frozenset[str] = frozenset(
    {
        "summary",
        "current_title",
        "total_experience_years",
        "experiences",
        "education",
        "languages",
        "extraction_confidence",
    }
)


@dataclass(frozen=True, slots=True)
class ProposeFromCvResult:
    """Service outcome for propose_profile_from_cv (compact ToolResult source)."""

    kind: ProposalKind
    tool_result: ToolResult
    draft: ProfileDraftPayload | None = None
    profile: CandidateProfile | None = None
    attachment_id: str | None = None
    schema_repairs_used: int = 0
    provider_retries_used: int = 0


@asynccontextmanager
async def _short_transaction(
    factory: async_sessionmaker[AsyncSession],
) -> Any:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _tool_ok(summary: str, data: dict[str, Any]) -> ToolResult:
    return ToolResult(ok=True, code=None, summary=summary, data=data)


def _tool_fail(
    code: str,
    summary: str,
    data: dict[str, Any] | None = None,
) -> ToolResult:
    return ToolResult(ok=False, code=code, summary=summary, data=data)


def arguments_summary_for_propose_cv(attachment_id: str) -> dict[str, Any]:
    """Compact ``arguments_summary_json`` — IDs only, never raw CV text."""
    return {"attachment_id": attachment_id}


async def _mark_failed(
    factory: async_sessionmaker[AsyncSession],
    attachment_id: str,
    failure_code: str,
) -> None:
    async with _short_transaction(factory) as session:
        row = await att_repo.get_by_id(session, attachment_id)
        if row is None:
            return
        if row.state == ATTACHMENT_STATE_STAGED:
            await att_repo.mark_failed(
                session, attachment_id, failure_code=failure_code
            )


async def _load_attachment(
    session: AsyncSession, attachment_id: str
) -> Attachment | None:
    return await att_repo.get_by_id(session, attachment_id)


async def propose_profile_from_cv(
    *,
    attachment_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    storage: AttachmentStorage,
    invoker: StructuredProfileInvoker,
    normalizer: SkillNormalizer,
    extract_text_fn: Callable[[Any], Any] | None = None,
) -> ProposeFromCvResult:
    """Run active/draft reuse or staged CV extraction into the singleton draft.

    Does not mutate active profile or job preferences. Provider and PDF work
    occur outside any long-lived transaction; draft upsert is a short unit of
    work after successful validation.
    """
    if not isinstance(attachment_id, str) or attachment_id.strip() == "":
        return ProposeFromCvResult(
            kind="new_draft",
            tool_result=_tool_fail(
                ERROR_ATTACHMENT_NOT_FOUND,
                "attachment_id is required",
            ),
            attachment_id=None,
        )

    async with session_factory() as session:
        attachment = await _load_attachment(session, attachment_id)
        if attachment is None:
            return ProposeFromCvResult(
                kind="new_draft",
                tool_result=_tool_fail(
                    ERROR_ATTACHMENT_NOT_FOUND,
                    f"attachment {attachment_id!r} not found",
                    {"attachment_id": attachment_id},
                ),
                attachment_id=attachment_id,
            )

        state = attachment.state
        storage_path = attachment.storage_path
        original_name = attachment.original_name

        # --- Active: return approved profile without extraction/draft ---
        if state == ATTACHMENT_STATE_ACTIVE:
            profile_row = await profile_repo.get_active_profile(session)
            if profile_row is None or profile_row.active_attachment_id != attachment_id:
                return ProposeFromCvResult(
                    kind="active_profile",
                    tool_result=_tool_fail(
                        ERROR_ACTIVE_PROFILE_MISSING,
                        "active attachment has no matching approved profile",
                        {"attachment_id": attachment_id},
                    ),
                    attachment_id=attachment_id,
                )
            profile = parse_candidate_profile(profile_row.profile_json)
            data = {
                "profile_id": CANDIDATE_PROFILE_ID,
                "attachment_id": attachment_id,
                "reused": True,
                "kind": "active_profile",
                **compact_profile_summary(profile),
            }
            return ProposeFromCvResult(
                kind="active_profile",
                tool_result=_tool_ok(
                    "returned existing approved candidate profile without extraction",
                    data,
                ),
                profile=profile,
                attachment_id=attachment_id,
            )

        # --- Staged already backing current draft: reuse ---
        if state == ATTACHMENT_STATE_STAGED:
            draft_row = await profile_repo.get_current_draft(session)
            if (
                draft_row is not None
                and draft_row.source_attachment_id == attachment_id
            ):
                draft = parse_profile_draft_payload(draft_row.draft_json)
                data = {
                    "draft_id": PROFILE_DRAFT_ID,
                    "attachment_id": attachment_id,
                    "reused": True,
                    "kind": "existing_draft",
                    **compact_draft_summary(draft),
                }
                return ProposeFromCvResult(
                    kind="existing_draft",
                    tool_result=_tool_ok(
                        "returned existing current draft for this staged attachment",
                        data,
                    ),
                    draft=draft,
                    attachment_id=attachment_id,
                )
        else:
            return ProposeFromCvResult(
                kind="new_draft",
                tool_result=_tool_fail(
                    ERROR_ATTACHMENT_NOT_PROCESSABLE,
                    f"attachment state {state!r} cannot be processed for proposal",
                    {"attachment_id": attachment_id, "state": state},
                ),
                attachment_id=attachment_id,
            )

    # --- New staged extraction (outside the read transaction above) ---
    if not storage.exists(storage_path):
        await _mark_failed(session_factory, attachment_id, ERROR_FILE_MISSING)
        return ProposeFromCvResult(
            kind="new_draft",
            tool_result=_tool_fail(
                ERROR_FILE_MISSING,
                "staged attachment file is missing",
                {"attachment_id": attachment_id},
            ),
            attachment_id=attachment_id,
        )

    absolute = storage.resolve_path(storage_path)
    try:
        outcome = extract_profile_from_pdf(
            absolute,
            invoker=invoker,
            normalizer=normalizer,
            extract_text_fn=extract_text_fn,
        )
    except ProfileExtractionError as exc:
        await _mark_failed(session_factory, attachment_id, exc.code)
        # Never include raw CV text in the failure ToolResult.
        return ProposeFromCvResult(
            kind="new_draft",
            tool_result=_tool_fail(
                exc.code,
                exc.message,
                {"attachment_id": attachment_id, "original_name": original_name},
            ),
            attachment_id=attachment_id,
        )

    draft_payload = outcome.draft
    draft_json = draft_payload.model_dump(mode="json")
    # Full model already validated by extract_profile_from_pdf / parse helpers.
    parse_profile_draft_payload(draft_json)

    prior_storage_path: str | None = None
    prior_attachment_id: str | None = None

    async with _short_transaction(session_factory) as session:
        # Re-check attachment still staged (no concurrent approval assumed for MVP).
        row = await att_repo.get_by_id(session, attachment_id)
        if row is None or row.state != ATTACHMENT_STATE_STAGED:
            return ProposeFromCvResult(
                kind="new_draft",
                tool_result=_tool_fail(
                    ERROR_ATTACHMENT_NOT_PROCESSABLE,
                    "attachment is no longer staged for proposal",
                    {"attachment_id": attachment_id},
                ),
                attachment_id=attachment_id,
            )

        existing = await profile_repo.get_current_draft(session)
        if existing is not None and existing.source_attachment_id is not None:
            prior_id = existing.source_attachment_id
            if prior_id != attachment_id:
                prior = await att_repo.get_by_id(session, prior_id)
                if prior is not None and prior.state == ATTACHMENT_STATE_STAGED:
                    prior_attachment_id = prior.id
                    prior_storage_path = prior.storage_path

        await profile_repo.upsert_current_draft(
            session,
            draft_json=draft_json,
            source_attachment_id=attachment_id,
        )

        if prior_attachment_id is not None:
            # Remove prior unreferenced staged row only after new draft succeeds.
            await att_repo.delete(session, prior_attachment_id)

    if prior_storage_path is not None:
        # Best-effort file cleanup after SQLite commit (never rolls draft back).
        try:
            storage.delete(prior_storage_path)
        except Exception:
            logger.warning(
                "best-effort delete of prior staged file failed path=%s",
                prior_storage_path,
            )

    data = {
        "draft_id": PROFILE_DRAFT_ID,
        "attachment_id": attachment_id,
        "reused": False,
        "kind": "new_draft",
        "schema_repairs_used": outcome.schema_repairs_used,
        "provider_retries_used": outcome.provider_retries_used,
        "prior_staged_removed": prior_attachment_id is not None,
        **compact_draft_summary(draft_payload),
    }
    return ProposeFromCvResult(
        kind="new_draft",
        tool_result=_tool_ok(
            "created validated current profile draft from staged CV",
            data,
        ),
        draft=draft_payload,
        attachment_id=attachment_id,
        schema_repairs_used=outcome.schema_repairs_used,
        provider_retries_used=outcome.provider_retries_used,
    )


# ---------------------------------------------------------------------------
# propose_profile_update — correction-preserving draft-only path
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProposeUpdateResult:
    """Service outcome for propose_profile_update (compact ToolResult source)."""

    base_kind: UpdateBaseKind | None
    tool_result: ToolResult
    draft: ProfileDraftPayload | None = None
    source_attachment_id: str | None = None


def arguments_summary_for_propose_update(
    *,
    profile_changes: Mapping[str, Any] | None = None,
    preference_changes: Mapping[str, Any] | None = None,
    skill_corrections: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compact ``arguments_summary_json`` — keys/counts only, never raw CV text."""
    profile_keys = sorted(profile_changes.keys()) if profile_changes else []
    preference_keys = (
        sorted(preference_changes.keys()) if preference_changes else []
    )
    correction_names: list[str] = []
    if skill_corrections:
        for item in skill_corrections:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name") or item.get("display_name") or item.get(
                "canonical_key"
            )
            if isinstance(name, str) and name.strip():
                correction_names.append(name.strip()[:80])
    return {
        "profile_change_keys": profile_keys,
        "preference_change_keys": preference_keys,
        "skill_correction_count": len(skill_corrections or ()),
        "skill_correction_names": correction_names[:20],
    }


def _skill_lookup_key(skill: CandidateSkill) -> str:
    return skill.skill.canonical_key


def _merge_preferences(
    base: JobPreferences,
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    data = base.model_dump(mode="json")
    if not patch:
        return data
    for key in JOB_PREFERENCE_KEYS:
        if key in patch:
            data[key] = patch[key]
    # Reject unknown preference keys early via full-document validation later;
    # surface extras here so they cannot silently drop into facts.
    extras = set(patch.keys()) - set(JOB_PREFERENCE_KEYS)
    if extras:
        # Attach so parse_job_preferences fails rather than strip silently.
        for extra in extras:
            data[extra] = patch[extra]
    return data


def _merge_profile_fields(
    base: CandidateProfile,
    patch: Mapping[str, Any] | None,
) -> dict[str, Any]:
    data = base.model_dump(mode="json")
    if not patch:
        return data
    for key, value in patch.items():
        if key == "skills":
            # Skills are applied through correction merge, not blind replace.
            continue
        if key in _PROFILE_PATCH_KEYS:
            data[key] = value
        else:
            # Unknown keys retained so full CandidateProfile validation rejects.
            data[key] = value
    return data


def _correction_to_skill(
    item: Mapping[str, Any],
    *,
    normalizer: SkillNormalizer,
    prior: CandidateSkill | None,
) -> CandidateSkill:
    """Build one ``CandidateSkill`` with ``source='user_correction'``."""
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        name = item.get("display_name")
    if not isinstance(name, str) or not name.strip():
        name = item.get("canonical_key")
    if not isinstance(name, str) or not name.strip():
        raise SkillTaxonomyError("skill correction requires name or canonical_key")

    ref = normalizer.normalize_name(name.strip())

    excluded = item.get("excluded")
    if excluded is None:
        excluded = prior.excluded if prior is not None else False
    if not isinstance(excluded, bool):
        raise ValueError(f"skill correction excluded must be bool, got {excluded!r}")

    proficiency = item.get("proficiency")
    if proficiency is None:
        proficiency = prior.proficiency if prior is not None else "unknown"

    years = item.get("years") if "years" in item else (
        prior.years if prior is not None else None
    )

    confidence = item.get("confidence")
    if confidence is None:
        confidence = prior.confidence if prior is not None else 1.0

    evidence = item.get("evidence")
    if evidence is None:
        evidence = (
            list(prior.evidence)
            if prior is not None
            else ["user correction"]
        )
    if not isinstance(evidence, list):
        evidence = [str(evidence)]

    skill = CandidateSkill(
        skill=ref,
        confidence=float(confidence),
        proficiency=proficiency,
        years=years if years is None else float(years),
        source="user_correction",
        excluded=excluded,
        evidence=[str(e) for e in evidence],
    )
    return normalizer.normalize_candidate_skill(skill)


def _apply_skill_corrections(
    base_skills: list[CandidateSkill],
    corrections: Sequence[Mapping[str, Any]] | None,
    *,
    normalizer: SkillNormalizer,
) -> list[CandidateSkill]:
    """Merge skill corrections; preserve exclusions unless explicitly cleared."""
    by_key: dict[str, CandidateSkill] = {
        _skill_lookup_key(s): normalizer.normalize_candidate_skill(s)
        for s in base_skills
    }
    # Snapshot excluded keys from the base (same-CV silent re-add protection).
    base_excluded: set[str] = {
        key for key, skill in by_key.items() if skill.excluded
    }

    # Track keys the user explicitly re-included (excluded=false in correction).
    explicit_reinclude: set[str] = set()

    if corrections:
        for raw in corrections:
            if not isinstance(raw, Mapping):
                raise ValueError(
                    f"skill correction must be a mapping, got {type(raw).__name__}"
                )
            name = (
                raw.get("name")
                or raw.get("display_name")
                or raw.get("canonical_key")
            )
            if not isinstance(name, str) or not name.strip():
                raise SkillTaxonomyError(
                    "skill correction requires name or canonical_key"
                )
            provisional_key = normalizer.normalize_name(name.strip()).canonical_key
            prior = by_key.get(provisional_key)
            corrected = _correction_to_skill(
                raw, normalizer=normalizer, prior=prior
            )
            key = corrected.skill.canonical_key
            if raw.get("excluded") is False:
                explicit_reinclude.add(key)
            by_key[key] = corrected

    # Re-assert base exclusions unless an explicit correction set excluded=false.
    for key in base_excluded:
        if key in explicit_reinclude:
            continue
        skill = by_key.get(key)
        if skill is None:
            # Dropped from list — restore excluded marker so the same CV cannot
            # silently drop the exclusion record.
            for base in base_skills:
                norm = normalizer.normalize_candidate_skill(base)
                if norm.skill.canonical_key == key:
                    by_key[key] = CandidateSkill(
                        skill=norm.skill,
                        confidence=norm.confidence,
                        proficiency=norm.proficiency,
                        years=norm.years,
                        source="user_correction",
                        excluded=True,
                        evidence=list(norm.evidence),
                    )
                    break
            continue
        if not skill.excluded:
            by_key[key] = CandidateSkill(
                skill=skill.skill,
                confidence=skill.confidence,
                proficiency=skill.proficiency,
                years=skill.years,
                source="user_correction",
                excluded=True,
                evidence=list(skill.evidence),
            )

    # Stable order: original base order, then newly added keys.
    ordered: list[CandidateSkill] = []
    seen: set[str] = set()
    for base in base_skills:
        key = normalizer.normalize_candidate_skill(base).skill.canonical_key
        if key in by_key and key not in seen:
            ordered.append(by_key[key])
            seen.add(key)
    for key, skill in by_key.items():
        if key not in seen:
            ordered.append(skill)
            seen.add(key)
    return ordered


def _build_updated_draft(
    base: ProfileDraftPayload,
    *,
    profile_changes: Mapping[str, Any] | None,
    preference_changes: Mapping[str, Any] | None,
    skill_corrections: Sequence[Mapping[str, Any]] | None,
    normalizer: SkillNormalizer,
) -> ProfileDraftPayload:
    profile_data = _merge_profile_fields(base.candidate_profile, profile_changes)
    prefs_data = _merge_preferences(base.job_preferences, preference_changes)

    skills = _apply_skill_corrections(
        base.candidate_profile.skills,
        skill_corrections,
        normalizer=normalizer,
    )
    # Optional skills list in profile_changes: treat entries as corrections.
    if profile_changes and "skills" in profile_changes:
        skills_raw = profile_changes["skills"]
        if not isinstance(skills_raw, list):
            raise ValueError("profile_changes.skills must be a list")
        as_corrections: list[Mapping[str, Any]] = []
        for entry in skills_raw:
            if not isinstance(entry, Mapping):
                raise ValueError("each skills entry must be a mapping")
            # Promote nested skill.display_name / free name into correction form.
            name = entry.get("name")
            if name is None and isinstance(entry.get("skill"), Mapping):
                skill_obj = entry["skill"]
                name = skill_obj.get("display_name") or skill_obj.get(
                    "canonical_key"
                )
            correction = dict(entry)
            if name is not None:
                correction["name"] = name
            as_corrections.append(correction)
        skills = _apply_skill_corrections(
            skills,
            as_corrections,
            normalizer=normalizer,
        )

    profile_data["skills"] = [s.model_dump(mode="json") for s in skills]
    return parse_profile_draft_payload(
        {
            "candidate_profile": profile_data,
            "job_preferences": prefs_data,
        }
    )


async def propose_profile_update(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    normalizer: SkillNormalizer,
    profile_changes: Mapping[str, Any] | None = None,
    preference_changes: Mapping[str, Any] | None = None,
    skill_corrections: Sequence[Mapping[str, Any]] | None = None,
) -> ProposeUpdateResult:
    """Apply profile/preference corrections into ``profile_drafts('current')``.

    Base document is the current draft when present, otherwise a copy of the
    approved profile plus job preferences. Never mutates active profile or
    preferences rows. Invalid merges leave prior draft/active truth unchanged.
    """
    has_profile = bool(profile_changes)
    has_prefs = bool(preference_changes)
    has_skills = bool(skill_corrections)
    if not has_profile and not has_prefs and not has_skills:
        return ProposeUpdateResult(
            base_kind=None,
            tool_result=_tool_fail(
                ERROR_EMPTY_UPDATE,
                "propose_profile_update requires profile, preference, or skill changes",
            ),
        )

    async with session_factory() as session:
        draft_row = await profile_repo.get_current_draft(session)
        if draft_row is not None:
            try:
                base = parse_profile_draft_payload(draft_row.draft_json)
            except ValidationError as exc:
                return ProposeUpdateResult(
                    base_kind="current_draft",
                    tool_result=_tool_fail(
                        ERROR_INVALID_PROFILE_UPDATE,
                        "current draft is not a valid ProfileDraftPayload",
                        {"errors": str(exc)[:400]},
                    ),
                )
            source_attachment_id = draft_row.source_attachment_id
            base_kind: UpdateBaseKind = "current_draft"
        else:
            profile_row = await profile_repo.get_active_profile(session)
            if profile_row is None:
                return ProposeUpdateResult(
                    base_kind=None,
                    tool_result=_tool_fail(
                        ERROR_NO_PROFILE_CONTEXT,
                        "no current draft or approved profile to update",
                    ),
                )
            try:
                profile = parse_candidate_profile(profile_row.profile_json)
            except ValidationError as exc:
                return ProposeUpdateResult(
                    base_kind="active_context",
                    tool_result=_tool_fail(
                        ERROR_INVALID_PROFILE_UPDATE,
                        "active profile is not a valid CandidateProfile",
                        {"errors": str(exc)[:400]},
                    ),
                )
            prefs_row = await profile_repo.get_job_preferences(session)
            if prefs_row is None:
                prefs = empty_job_preferences()
            else:
                try:
                    prefs = parse_job_preferences(prefs_row.preferences_json)
                except ValidationError:
                    prefs = empty_job_preferences()
            base = parse_profile_draft_payload(
                {
                    "candidate_profile": profile.model_dump(mode="json"),
                    "job_preferences": prefs.model_dump(mode="json"),
                }
            )
            # Preference-only or profile corrections from active context are
            # not CV-backed drafts; source attachment stays null.
            source_attachment_id = None
            base_kind = "active_context"

    try:
        updated = _build_updated_draft(
            base,
            profile_changes=profile_changes,
            preference_changes=preference_changes,
            skill_corrections=skill_corrections,
            normalizer=normalizer,
        )
    except (ValidationError, SkillTaxonomyError, TypeError, ValueError) as exc:
        return ProposeUpdateResult(
            base_kind=base_kind,
            tool_result=_tool_fail(
                ERROR_INVALID_PROFILE_UPDATE,
                "requested changes failed ProfileDraftPayload validation",
                {"errors": str(exc)[:400]},
            ),
            source_attachment_id=source_attachment_id,
        )

    draft_json = updated.model_dump(mode="json")
    # Validate again at the write boundary (complete model only).
    parse_profile_draft_payload(draft_json)

    try:
        async with _short_transaction(session_factory) as session:
            await profile_repo.upsert_current_draft(
                session,
                draft_json=draft_json,
                source_attachment_id=source_attachment_id,
            )
    except Exception as exc:
        logger.exception("draft upsert failed during propose_profile_update")
        return ProposeUpdateResult(
            base_kind=base_kind,
            tool_result=_tool_fail(
                ERROR_INVALID_PROFILE_UPDATE,
                "failed to persist current draft",
                {"errors": str(exc)[:200]},
            ),
            source_attachment_id=source_attachment_id,
        )

    excluded_count = sum(
        1 for s in updated.candidate_profile.skills if s.excluded
    )
    correction_count = sum(
        1
        for s in updated.candidate_profile.skills
        if s.source == "user_correction"
    )
    data: dict[str, Any] = {
        "draft_id": PROFILE_DRAFT_ID,
        "source_attachment_id": source_attachment_id,
        "base_kind": base_kind,
        "preference_only": has_prefs and not has_profile and not has_skills,
        "excluded_skill_count": excluded_count,
        "user_correction_skill_count": correction_count,
        **compact_draft_summary(updated),
    }
    return ProposeUpdateResult(
        base_kind=base_kind,
        tool_result=_tool_ok(
            "updated validated current profile draft with requested changes",
            data,
        ),
        draft=updated,
        source_attachment_id=source_attachment_id,
    )


__all__ = [
    "ERROR_ACTIVE_PROFILE_MISSING",
    "ERROR_ATTACHMENT_NOT_FOUND",
    "ERROR_ATTACHMENT_NOT_PROCESSABLE",
    "ERROR_EMPTY_UPDATE",
    "ERROR_FILE_MISSING",
    "ERROR_INVALID_PROFILE_UPDATE",
    "ERROR_NO_PROFILE_CONTEXT",
    "FAILURE_NO_EXTRACTABLE_TEXT",
    "ProposeFromCvResult",
    "ProposeUpdateResult",
    "arguments_summary_for_propose_cv",
    "arguments_summary_for_propose_update",
    "propose_profile_from_cv",
    "propose_profile_update",
]

"""Grounded optional-contact facts extracted from bounded CV chunks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.contact import (
    normalize_email,
    normalize_github_profile_url,
    normalize_phone,
)
from app.services.cv_chunk_contracts import CanonicalChunk
from app.services.skill_assertion_guard import normalize_assertion_text

ContactKind = Literal["phone", "email", "github_url"]
_CONTACT_KINDS: tuple[ContactKind, ...] = ("phone", "email", "github_url")


class ExtractedContactFact(BaseModel):
    """One provider-supplied contact assertion tied to one source chunk."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: ContactKind
    value: str
    evidence: str
    source_chunk_ordinal: int


@dataclass(frozen=True, slots=True)
class AcceptedContacts:
    phone: str | None
    email: str | None
    github_url: str | None
    warnings: tuple[str, ...]


def _normalize(kind: ContactKind, value: str) -> str:
    if kind == "phone":
        return normalize_phone(value)
    if kind == "email":
        return normalize_email(value)
    return normalize_github_profile_url(value)


def _value_in_evidence(
    kind: ContactKind, value: str, normalized: str, evidence: str
) -> bool:
    if kind == "phone":
        evidence_digits = "".join(
            char for char in evidence if char.isascii() and char.isdigit()
        )
        return normalized.lstrip("+") in evidence_digits
    return normalize_assertion_text(value) in normalize_assertion_text(evidence)


def validate_and_project_contact_facts(
    facts: Sequence[ExtractedContactFact], chunks: Sequence[CanonicalChunk]
) -> AcceptedContacts:
    """Drop ungrounded facts and deterministically project unique contacts."""
    source_by_ordinal = {chunk.ordinal: chunk.text for chunk in chunks}
    accepted: dict[ContactKind, dict[str, str]] = {kind: {} for kind in _CONTACT_KINDS}
    for fact in facts:
        source = source_by_ordinal.get(fact.source_chunk_ordinal)
        evidence = fact.evidence.strip()
        display = fact.value.strip()
        if source is None or not evidence or not display:
            continue
        if normalize_assertion_text(evidence) not in normalize_assertion_text(source):
            continue
        try:
            normalized = _normalize(fact.kind, display)
        except ValueError:
            continue
        if not _value_in_evidence(fact.kind, display, normalized, evidence):
            continue
        accepted[fact.kind].setdefault(normalized, display)

    values: dict[ContactKind, str | None] = {}
    warnings: list[str] = []
    for kind in _CONTACT_KINDS:
        options = accepted[kind]
        if len(options) == 1:
            values[kind] = next(iter(options.values()))
        elif len(options) > 1:
            values[kind] = None
            warnings.append(f"ambiguous_contact:{kind}")
        else:
            values[kind] = None
    return AcceptedContacts(
        phone=values["phone"],
        email=values["email"],
        github_url=values["github_url"],
        warnings=tuple(warnings),
    )


__all__ = [
    "AcceptedContacts",
    "ContactKind",
    "ExtractedContactFact",
    "validate_and_project_contact_facts",
]

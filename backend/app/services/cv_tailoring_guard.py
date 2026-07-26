"""Pure structural, provenance, anchor, and semantic CV-tailoring guard."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

from app.core.ids import new_uuid
from app.schemas.common import StrictModelConfig
from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredCVContent,
    TailoredFactEvidence,
    TailoredItem,
    TailoredItemPatch,
    TailoredPatchSet,
    TailoredSection,
    TailoredSectionPatch,
)
from app.services.skill_assertion_guard import normalize_assertion_text

_NUMBER_TOKEN_RE = re.compile(r"(?<!\w)\d+(?:[.,:/+%-]\d+)*(?:%)?")
_URL_TOKEN_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_EMAIL_TOKEN_RE = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9.-]+"
)


class GroundingIssue(BaseModel):
    model_config = StrictModelConfig

    code: Literal[
        "UNKNOWN_FACT",
        "CROSS_SECTION_FACT",
        "UNSUPPORTED_ANCHOR",
        "EMPTY_PROVENANCE",
        "SECTION_IDENTITY_CHANGED",
        "ATTRIBUTE_IDENTITY_CHANGED",
        "CONTENT_BOUNDS_EXCEEDED",
    ]
    path: str


class SemanticSupportChecker(Protocol):
    def supports(
        self, *, output_text: str, cited_evidence: Sequence[str]
    ) -> bool: ...


def _text_fields(
    item: TailoredItemPatch, *, path: str
) -> Iterator[tuple[str, SourceBoundText]]:
    optional = (
        ("title", item.title),
        ("subtitle", item.subtitle),
        ("date_text", item.date_text),
        ("location", item.location),
    )
    for field_name, value in optional:
        if value is not None:
            yield f"{path}.{field_name}", value
    yield f"{path}.body", item.body
    for index, value in enumerate(item.bullets):
        yield f"{path}.bullets[{index}]", value
    for attribute_index, attribute in enumerate(item.attributes):
        for value_index, value in enumerate(attribute.values):
            yield (
                f"{path}.attributes[{attribute_index}].values[{value_index}]",
                value,
            )


def _tokens(pattern: re.Pattern[str], text: str, *, url: bool = False) -> set[str]:
    values: set[str] = set()
    for match in pattern.finditer(text):
        value = match.group(0)
        if url:
            value = value.rstrip(".,;:!?)]}")
        normalized = normalize_assertion_text(value)
        if normalized:
            values.add(normalized)
    return values


def _label_occurs(label: str, text: str) -> bool:
    normalized_label = normalize_assertion_text(label)
    normalized_text = normalize_assertion_text(text)
    return bool(normalized_label) and bool(
        re.search(rf"(?<!\w){re.escape(normalized_label)}(?!\w)", normalized_text)
    )


def _unsupported_anchor(
    text: str,
    *,
    evidence: Sequence[str],
    approved_skill_labels: Sequence[str],
) -> bool:
    token_specs = (
        (_NUMBER_TOKEN_RE, False),
        (_URL_TOKEN_RE, True),
        (_EMAIL_TOKEN_RE, False),
    )
    for pattern, is_url in token_specs:
        output_tokens = _tokens(pattern, text, url=is_url)
        evidence_tokens = set().union(
            *(_tokens(pattern, item, url=is_url) for item in evidence)
        )
        if not output_tokens.issubset(evidence_tokens):
            return True
    for label in approved_skill_labels:
        if _label_occurs(label, text):
            if not any(_label_occurs(label, item) for item in evidence):
                return True
    return False


def _attribute_names_for_section(parent_section: TailoredSection) -> list[str]:
    names: list[str] = []
    for item in parent_section.items:
        for attribute in item.attributes:
            if attribute.name not in names:
                names.append(attribute.name)
    return names


def _manual_content_identity_issues(
    content: TailoredCVContent, *, parent: TailoredCVContent
) -> list[GroundingIssue]:
    if content.header != parent.header:
        return [GroundingIssue(code="SECTION_IDENTITY_CHANGED", path="header")]
    if len(content.sections) != len(parent.sections):
        return [GroundingIssue(code="SECTION_IDENTITY_CHANGED", path="sections")]
    for index, (section, parent_section) in enumerate(
        zip(content.sections, parent.sections, strict=True)
    ):
        if (
            section.id,
            section.heading,
            section.kind,
            section.ordinal,
        ) != (
            parent_section.id,
            parent_section.heading,
            parent_section.kind,
            parent_section.ordinal,
        ):
            return [
                GroundingIssue(
                    code="SECTION_IDENTITY_CHANGED",
                    path=f"sections[{index}]",
                )
            ]
    return []


def _manual_content_patch(
    content: TailoredCVContent, *, allowed_section_ids: Sequence[str]
) -> TailoredPatchSet:
    allowed = set(allowed_section_ids)
    return TailoredPatchSet(
        sections=[
            TailoredSectionPatch(
                section_id=section.id,
                items=[
                    TailoredItemPatch(
                        source_entry_id=item.source_entry_id,
                        title=item.title,
                        subtitle=item.subtitle,
                        date_text=item.date_text,
                        location=item.location,
                        body=item.body,
                        bullets=item.bullets,
                        attributes=item.attributes,
                    )
                    for item in section.items
                ],
            )
            for section in content.sections
            if section.id in allowed
        ]
    )


def validate_patch_structure_and_facts(
    patch: TailoredPatchSet,
    *,
    parent: TailoredCVContent,
    allowed_section_ids: Sequence[str],
    fact_bank: Mapping[str, TailoredFactEvidence],
    approved_skill_labels: Sequence[str],
    semantic_checker: SemanticSupportChecker | None,
) -> list[GroundingIssue]:
    issues: list[GroundingIssue] = []
    allowed = list(allowed_section_ids)
    parent_by_id = {section.id: section for section in parent.sections}
    patch_ids = [section.section_id for section in patch.sections]
    if len(patch.sections) > 20:
        return [GroundingIssue(code="CONTENT_BOUNDS_EXCEEDED", path="sections")]
    if (
        len(allowed) != len(set(allowed))
        or any(section_id not in parent_by_id for section_id in allowed)
        or patch_ids != allowed
    ):
        issues.append(
            GroundingIssue(code="SECTION_IDENTITY_CHANGED", path="sections")
        )
        return issues

    for section_index, section_patch in enumerate(patch.sections):
        section_path = f"sections[{section_index}]"
        parent_section = parent_by_id[section_patch.section_id]
        parent_items = {item.id: item for item in parent_section.items}
        seen_source_ids: set[str] = set()
        section_attribute_names = _attribute_names_for_section(parent_section)
        if len(section_patch.items) > 30:
            issues.append(
                GroundingIssue(
                    code="CONTENT_BOUNDS_EXCEEDED",
                    path=f"{section_path}.items",
                )
            )
        for item_index, item in enumerate(section_patch.items):
            item_path = f"{section_path}.items[{item_index}]"
            source_id = item.source_entry_id
            if source_id is not None:
                if source_id not in parent_items or source_id in seen_source_ids:
                    issues.append(
                        GroundingIssue(
                            code="SECTION_IDENTITY_CHANGED",
                            path=f"{item_path}.source_entry_id",
                        )
                    )
                seen_source_ids.add(source_id)
            parent_item = parent_items.get(source_id or "")
            attribute_names = [attribute.name for attribute in item.attributes]
            expected_names = (
                [attribute.name for attribute in parent_item.attributes]
                if parent_item is not None
                else [
                    name
                    for name in section_attribute_names
                    if name in attribute_names
                ]
            )
            if attribute_names != expected_names or len(attribute_names) != len(
                set(attribute_names)
            ):
                issues.append(
                    GroundingIssue(
                        code="ATTRIBUTE_IDENTITY_CHANGED",
                        path=f"{item_path}.attributes",
                    )
                )
            if (
                len(item.bullets) > 30
                or len(item.attributes) > 30
                or any(len(attribute.values) > 30 for attribute in item.attributes)
            ):
                issues.append(
                    GroundingIssue(code="CONTENT_BOUNDS_EXCEEDED", path=item_path)
                )

            for field_path, bound_text in _text_fields(item, path=item_path):
                if bound_text.text and not bound_text.source_fact_ids:
                    issues.append(
                        GroundingIssue(code="EMPTY_PROVENANCE", path=field_path)
                    )
                    continue
                if len(bound_text.source_fact_ids) != len(
                    set(bound_text.source_fact_ids)
                ):
                    issues.append(
                        GroundingIssue(code="UNKNOWN_FACT", path=field_path)
                    )
                    continue
                cited: list[str] = []
                valid_facts = True
                for fact_id in bound_text.source_fact_ids:
                    evidence = fact_bank.get(fact_id)
                    if evidence is None:
                        issues.append(
                            GroundingIssue(code="UNKNOWN_FACT", path=field_path)
                        )
                        valid_facts = False
                        continue
                    if evidence.section_id != section_patch.section_id:
                        issues.append(
                            GroundingIssue(code="CROSS_SECTION_FACT", path=field_path)
                        )
                        valid_facts = False
                        continue
                    cited.append(evidence.source_text)
                if not bound_text.text or not valid_facts:
                    continue
                if _unsupported_anchor(
                    bound_text.text,
                    evidence=cited,
                    approved_skill_labels=approved_skill_labels,
                ):
                    issues.append(
                        GroundingIssue(code="UNSUPPORTED_ANCHOR", path=field_path)
                    )
                    continue
                if cited and not any(
                    normalize_assertion_text(bound_text.text)
                    in normalize_assertion_text(evidence)
                    for evidence in cited
                ):
                    if semantic_checker is None or not semantic_checker.supports(
                        output_text=bound_text.text, cited_evidence=cited
                    ):
                        issues.append(
                            GroundingIssue(code="UNSUPPORTED_ANCHOR", path=field_path)
                        )
    return issues


def assemble_guarded_content(
    patch: TailoredPatchSet,
    *,
    parent: TailoredCVContent,
) -> TailoredCVContent:
    patch_by_id = {section.section_id: section for section in patch.sections}
    sections = []
    for parent_section in parent.sections:
        section_patch = patch_by_id.get(parent_section.id)
        if section_patch is None:
            sections.append(parent_section.model_copy(deep=True))
            continue
        used_ids: set[str] = set()
        items: list[TailoredItem] = []
        for item_patch in section_patch.items:
            item_id = item_patch.source_entry_id or new_uuid()
            if item_id in used_ids:
                item_id = new_uuid()
            used_ids.add(item_id)
            items.append(
                TailoredItem(
                    id=item_id,
                    source_entry_id=item_patch.source_entry_id,
                    title=item_patch.title,
                    subtitle=item_patch.subtitle,
                    date_text=item_patch.date_text,
                    location=item_patch.location,
                    body=item_patch.body,
                    bullets=item_patch.bullets,
                    attributes=item_patch.attributes,
                )
            )
        sections.append(parent_section.model_copy(update={"items": items}, deep=True))
    return TailoredCVContent(
        header=parent.header.model_copy(deep=True),
        sections=sections,
    )


def guard_tailored_patch(
    patch: TailoredPatchSet,
    *,
    parent: TailoredCVContent,
    allowed_section_ids: Sequence[str],
    fact_bank: Mapping[str, TailoredFactEvidence],
    approved_skill_labels: Sequence[str],
    semantic_checker: SemanticSupportChecker | None,
) -> tuple[TailoredCVContent | None, tuple[GroundingIssue, ...]]:
    issues = validate_patch_structure_and_facts(
        patch,
        parent=parent,
        allowed_section_ids=allowed_section_ids,
        fact_bank=fact_bank,
        approved_skill_labels=approved_skill_labels,
        semantic_checker=semantic_checker,
    )
    if issues:
        return None, tuple(issues)
    return assemble_guarded_content(patch, parent=parent), ()


def guard_manual_tailored_content(
    content: TailoredCVContent,
    *,
    parent: TailoredCVContent,
    allowed_section_ids: Sequence[str],
    fact_bank: Mapping[str, TailoredFactEvidence],
    approved_skill_labels: Sequence[str],
    semantic_checker: SemanticSupportChecker | None,
) -> tuple[TailoredCVContent | None, tuple[GroundingIssue, ...]]:
    identity_issues = _manual_content_identity_issues(content, parent=parent)
    if identity_issues:
        return None, tuple(identity_issues)
    return guard_tailored_patch(
        _manual_content_patch(content, allowed_section_ids=allowed_section_ids),
        parent=parent,
        allowed_section_ids=allowed_section_ids,
        fact_bank=fact_bank,
        approved_skill_labels=approved_skill_labels,
        semantic_checker=semantic_checker,
    )


__all__ = [
    "GroundingIssue",
    "SemanticSupportChecker",
    "assemble_guarded_content",
    "guard_manual_tailored_content",
    "guard_tailored_patch",
    "validate_patch_structure_and_facts",
]

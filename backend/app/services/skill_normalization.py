"""Deterministic Candidate skill normalization and approval-only seed loading.

Plan 4 / Master Plan §9 shared seam:

1. Unicode normalize, trim/collapse whitespace, casefold, normalize separators.
2. Resolve only checked-in approved seed aliases as ``verified``.
3. Unknown skills receive a deterministic provisional canonical key.
4. Preserve evidence/source/exclusion fields; never re-add an excluded skill
   from the same extraction input without new approval.
5. Never create trusted ``RELATED_TO`` relationships.

This module is pure (no I/O beyond explicit seed path load) and is the single
normalization entry point Plan 5 must reuse unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from app.schemas.candidate import (
    MAX_ALIASES,
    CandidateSkill,
    SkillRef,
    SkillStatus,
)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DEFAULT_SKILLS_SEED_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "data" / "skills_seed.yaml"
)

# Separators and punctuation collapsed to whitespace before matching.
# Includes ASCII separators and common Unicode dash/separator variants
# (en dash, em dash, middle dot, soft hyphen, minus sign, etc.).
# Keep + and # for tech labels (C++, C#).
_SEPARATOR_RE: Final[re.Pattern[str]] = re.compile(
    r"["
    r"\s/\\_|.,;:|&()\[\]{}<>\"'`~!?*=\-"
    r"\u00ad\u00b7"  # soft hyphen, middle dot
    r"\u2010-\u2015"  # hyphen .. horizontal bar (incl. en/em dash)
    r"\u2022\u2027"  # bullet, hyphenation point
    r"\u2212"  # minus sign
    r"]+",
    re.UNICODE,
)

# Canonical keys: lowercase alphanumerics, underscore, plus, hash (C++, C#).
_CANONICAL_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"[^a-z0-9_+#]+",
)


class SkillSeedError(ValueError):
    """Raised when a skills seed document is missing or malformed."""


@dataclass(frozen=True, slots=True)
class SeedSkillEntry:
    """One approval-only verified skill row from the seed."""

    canonical_key: str
    display_name: str
    aliases: tuple[str, ...]
    category: str | None = None


@dataclass(frozen=True, slots=True)
class SkillSeedCatalog:
    """In-memory approved seed: match-key → verified entry."""

    entries: tuple[SeedSkillEntry, ...]
    _by_match_key: Mapping[str, SeedSkillEntry]

    def resolve(self, match_key: str) -> SeedSkillEntry | None:
        """Return the verified entry for a normalized match key, if any."""
        if not match_key:
            return None
        return self._by_match_key.get(match_key)

    def __len__(self) -> int:
        return len(self.entries)


# ---------------------------------------------------------------------------
# Text normalization primitives
# ---------------------------------------------------------------------------


def normalize_skill_match_key(text: str) -> str:
    """Return the deterministic comparison form for a skill label.

    Pipeline (Master §9.1): Unicode NFKC → trim/collapse whitespace → casefold
    → normalize punctuation and common separators → collapse again.
    """
    if not isinstance(text, str):
        raise TypeError("skill text must be a string")
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.casefold()
    normalized = _SEPARATOR_RE.sub(" ", normalized)
    normalized = " ".join(normalized.split())
    return normalized


def provisional_canonical_key(text: str) -> str:
    """Build a deterministic provisional ``canonical_key`` from skill text."""
    match_key = normalize_skill_match_key(text)
    if not match_key:
        raise ValueError("cannot derive provisional key from empty skill text")
    # Spaces → underscore; drop residual non-key characters.
    key = match_key.replace(" ", "_")
    key = _CANONICAL_KEY_RE.sub("", key)
    key = re.sub(r"_+", "_", key).strip("_")
    if not key:
        raise ValueError("cannot derive provisional key from empty skill text")
    return key


def dedupe_aliases(aliases: Sequence[str]) -> list[str]:
    """Deduplicate aliases by match key; order by match key then first form."""
    best_form: dict[str, str] = {}
    for raw in aliases:
        if not isinstance(raw, str):
            continue
        form = raw.strip()
        if not form:
            continue
        match_key = normalize_skill_match_key(form)
        if not match_key:
            continue
        # Keep the first surface form for a given match key.
        if match_key not in best_form:
            best_form[match_key] = form
    ordered_keys = sorted(best_form.keys())
    result = [best_form[k] for k in ordered_keys]
    if len(result) > MAX_ALIASES:
        return result[:MAX_ALIASES]
    return result


# ---------------------------------------------------------------------------
# Seed loading
# ---------------------------------------------------------------------------

_PROHIBITED_SEED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "related_to",
        "relatedto",
        "relationships",
        "edges",
        "trusted_edges",
        "graph_edges",
    }
)


def _require_nonblank_str(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSeedError(f"seed skill {field} must be a non-empty string")
    return value.strip()


def _parse_seed_skill(raw: object, *, index: int) -> SeedSkillEntry:
    if not isinstance(raw, dict):
        raise SkillSeedError(f"seed skills[{index}] must be a mapping")

    lowered = {str(k).strip().casefold(): k for k in raw}
    for prohibited in _PROHIBITED_SEED_KEYS:
        if prohibited in lowered:
            raise SkillSeedError(
                f"seed skills[{index}] must not define trusted relationship "
                f"field {prohibited!r}"
            )

    try:
        canonical_key = _require_nonblank_str(
            raw.get("canonical_key"), field="canonical_key"
        )
        display_name = _require_nonblank_str(
            raw.get("display_name"), field="display_name"
        )
    except SkillSeedError as exc:
        raise SkillSeedError(f"seed skills[{index}]: {exc}") from exc

    aliases_raw = raw.get("aliases", [])
    if aliases_raw is None:
        aliases_raw = []
    if not isinstance(aliases_raw, list):
        raise SkillSeedError(f"seed skills[{index}].aliases must be a list")

    alias_list: list[str] = []
    for item in aliases_raw:
        if not isinstance(item, str) or not item.strip():
            raise SkillSeedError(
                f"seed skills[{index}].aliases items must be non-empty strings"
            )
        alias_list.append(item.strip())

    # Always include display_name and canonical_key as alias surfaces.
    alias_list = [display_name, canonical_key, *alias_list]
    aliases = tuple(dedupe_aliases(alias_list))

    category_raw = raw.get("category", None)
    category: str | None
    if category_raw is None:
        category = None
    elif isinstance(category_raw, str):
        category = category_raw.strip() or None
    else:
        raise SkillSeedError(
            f"seed skills[{index}].category must be a string or null"
        )

    return SeedSkillEntry(
        canonical_key=canonical_key,
        display_name=display_name,
        aliases=aliases,
        category=category,
    )


def skill_seed_catalog_from_data(data: object) -> SkillSeedCatalog:
    """Parse and validate an in-memory seed document into a catalog."""
    if data is None:
        raise SkillSeedError("seed document is empty")
    if not isinstance(data, dict):
        raise SkillSeedError("seed document must be a mapping")

    if "related_to" in data or "relationships" in data:
        raise SkillSeedError(
            "seed document must not define top-level trusted relationships"
        )

    skills_raw = data.get("skills", [])
    if skills_raw is None:
        skills_raw = []
    if not isinstance(skills_raw, list):
        raise SkillSeedError("seed 'skills' must be a list")

    entries: list[SeedSkillEntry] = []
    by_match: dict[str, SeedSkillEntry] = {}

    for index, raw in enumerate(skills_raw):
        entry = _parse_seed_skill(raw, index=index)
        entries.append(entry)

        surfaces = [entry.canonical_key, entry.display_name, *entry.aliases]
        for surface in surfaces:
            match_key = normalize_skill_match_key(surface)
            if not match_key:
                continue
            existing = by_match.get(match_key)
            if existing is not None and existing.canonical_key != entry.canonical_key:
                raise SkillSeedError(
                    f"seed alias {surface!r} maps to both "
                    f"{existing.canonical_key!r} and {entry.canonical_key!r}"
                )
            by_match[match_key] = entry

    # Stable entry order by canonical_key for determinism.
    entries_sorted = tuple(sorted(entries, key=lambda e: e.canonical_key))
    return SkillSeedCatalog(entries=entries_sorted, _by_match_key=by_match)


def load_skills_seed(path: Path | str | None = None) -> SkillSeedCatalog:
    """Load the approval-only skills seed YAML from *path* (or production default)."""
    seed_path = Path(path) if path is not None else DEFAULT_SKILLS_SEED_PATH
    if not seed_path.is_file():
        raise SkillSeedError(f"skills seed not found: {seed_path}")
    try:
        text = seed_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillSeedError(f"cannot read skills seed: {seed_path}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SkillSeedError(f"invalid YAML in skills seed: {seed_path}") from exc
    return skill_seed_catalog_from_data(data)


def empty_skill_seed_catalog() -> SkillSeedCatalog:
    """Return a catalog with no verified aliases (empty production seed)."""
    return SkillSeedCatalog(entries=(), _by_match_key={})


# ---------------------------------------------------------------------------
# Candidate skill list normalization
# ---------------------------------------------------------------------------


def _lookup_texts_for_skill(skill: CandidateSkill) -> list[str]:
    """Surface strings used to match seed / existing / exclusion keys."""
    ref = skill.skill
    texts: list[str] = []
    for value in (ref.display_name, ref.canonical_key, *ref.aliases):
        if isinstance(value, str) and value.strip():
            texts.append(value.strip())
    return texts


def _resolve_seed_entry(
    skill: CandidateSkill,
    catalog: SkillSeedCatalog,
) -> SeedSkillEntry | None:
    for text in _lookup_texts_for_skill(skill):
        entry = catalog.resolve(normalize_skill_match_key(text))
        if entry is not None:
            return entry
    return None


def _match_existing_canonical_key(
    skill: CandidateSkill,
    existing_by_match: Mapping[str, str],
) -> str | None:
    for text in _lookup_texts_for_skill(skill):
        match_key = normalize_skill_match_key(text)
        if match_key in existing_by_match:
            return existing_by_match[match_key]
    return None


def _is_excluded(
    *,
    skill: CandidateSkill,
    resolved_key: str,
    excluded_canonical: set[str],
    excluded_match: set[str],
) -> bool:
    if resolved_key in excluded_canonical:
        return True
    if normalize_skill_match_key(resolved_key) in excluded_match:
        return True
    for text in _lookup_texts_for_skill(skill):
        if normalize_skill_match_key(text) in excluded_match:
            return True
    return False


def _build_resolved_ref(
    skill: CandidateSkill,
    *,
    catalog: SkillSeedCatalog,
    existing_by_match: Mapping[str, str],
) -> SkillRef:
    ref = skill.skill
    seed_entry = _resolve_seed_entry(skill, catalog)
    if seed_entry is not None:
        return SkillRef(
            canonical_key=seed_entry.canonical_key,
            display_name=seed_entry.display_name,
            aliases=list(seed_entry.aliases),
            category=seed_entry.category,
            status=SkillStatus.VERIFIED,
            confidence=ref.confidence,
            evidence=list(ref.evidence),
        )

    existing_key = _match_existing_canonical_key(skill, existing_by_match)
    source_text = ref.display_name.strip() or ref.canonical_key.strip()
    if existing_key is not None:
        return SkillRef(
            canonical_key=existing_key,
            display_name=ref.display_name,
            aliases=dedupe_aliases([ref.display_name, ref.canonical_key, *ref.aliases]),
            category=ref.category,
            status=SkillStatus.PROVISIONAL,
            confidence=ref.confidence,
            evidence=list(ref.evidence),
        )

    return SkillRef(
        canonical_key=provisional_canonical_key(source_text),
        display_name=ref.display_name,
        aliases=dedupe_aliases([ref.display_name, ref.canonical_key, *ref.aliases]),
        category=ref.category,
        status=SkillStatus.PROVISIONAL,
        confidence=ref.confidence,
        evidence=list(ref.evidence),
    )


def normalize_candidate_skills(
    skills: Sequence[CandidateSkill],
    *,
    catalog: SkillSeedCatalog | None = None,
    existing_canonical_keys: Iterable[str] = (),
    excluded_canonical_keys: Iterable[str] = (),
) -> list[CandidateSkill]:
    """Normalize, resolve, dedupe, and apply exclusion rules to Candidate skills.

    - Seed-matched aliases become ``verified`` with seed identity fields.
    - Unknown skills become ``provisional`` with deterministic keys.
    - Existing canonical keys are preferred over minting a new provisional key
      when the match form aligns, but remain ``provisional`` unless seed-verified.
    - Skills listed in *excluded_canonical_keys* (or already ``excluded=True``)
      are not re-added from non-excluded extraction rows.
    - Explicit exclusion / ``user_correction`` rows are preserved once.
    - Proficiency, years, source, excluded, and evidence fields stay intact.
    - Output order is stable by ``canonical_key``.
    """
    if catalog is None:
        catalog = load_skills_seed()

    existing_by_match: dict[str, str] = {}
    for key in existing_canonical_keys:
        if not isinstance(key, str) or not key.strip():
            continue
        cleaned = key.strip()
        match_key = normalize_skill_match_key(cleaned)
        if match_key and match_key not in existing_by_match:
            existing_by_match[match_key] = cleaned

    excluded_canonical: set[str] = set()
    excluded_match: set[str] = set()
    for key in excluded_canonical_keys:
        if not isinstance(key, str) or not key.strip():
            continue
        cleaned = key.strip()
        excluded_canonical.add(cleaned)
        match_key = normalize_skill_match_key(cleaned)
        if match_key:
            excluded_match.add(match_key)

    # First pass: register exclusions present in the input list itself.
    for skill in skills:
        if not skill.excluded:
            continue
        # Resolve identity only to register the exclusion key; do not drop yet.
        ref = _build_resolved_ref(
            skill,
            catalog=catalog,
            existing_by_match=existing_by_match,
        )
        excluded_canonical.add(ref.canonical_key)
        match_key = normalize_skill_match_key(ref.canonical_key)
        if match_key:
            excluded_match.add(match_key)
        for text in _lookup_texts_for_skill(skill):
            mk = normalize_skill_match_key(text)
            if mk:
                excluded_match.add(mk)

    resolved_by_key: dict[str, CandidateSkill] = {}

    for skill in skills:
        new_ref = _build_resolved_ref(
            skill,
            catalog=catalog,
            existing_by_match=existing_by_match,
        )
        excluded_hit = _is_excluded(
            skill=skill,
            resolved_key=new_ref.canonical_key,
            excluded_canonical=excluded_canonical,
            excluded_match=excluded_match,
        )

        # Do not re-add the same excluded skill from CV / non-excluded input.
        if excluded_hit and not skill.excluded:
            continue

        new_skill = skill.model_copy(
            update={
                "skill": new_ref,
                # proficiency, years, source, excluded, evidence preserved
            }
        )

        prior = resolved_by_key.get(new_ref.canonical_key)
        if prior is None:
            resolved_by_key[new_ref.canonical_key] = new_skill
            continue

        # Prefer an explicit exclusion / user_correction over a plain CV row.
        if new_skill.excluded and not prior.excluded:
            resolved_by_key[new_ref.canonical_key] = new_skill
            continue
        if (
            new_skill.source.value == "user_correction"
            and prior.source.value != "user_correction"
            and new_skill.excluded == prior.excluded
        ):
            resolved_by_key[new_ref.canonical_key] = new_skill
            continue
        # Otherwise keep the first occurrence (stable relative to input order
        # among equal-priority rows); final list is sorted by canonical_key.

    ordered_keys = sorted(resolved_by_key.keys())
    return [resolved_by_key[k] for k in ordered_keys]


__all__ = [
    "DEFAULT_SKILLS_SEED_PATH",
    "SeedSkillEntry",
    "SkillSeedCatalog",
    "SkillSeedError",
    "dedupe_aliases",
    "empty_skill_seed_catalog",
    "load_skills_seed",
    "normalize_candidate_skills",
    "normalize_skill_match_key",
    "provisional_canonical_key",
    "skill_seed_catalog_from_data",
]

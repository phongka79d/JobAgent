"""Sole deterministic skill taxonomy loader and normalizer (Master §9, Plan 4 §7.2).

Ownership
---------
* Production taxonomy path: ``infrastructure/neo4j/skills_seed.yaml`` only.
* Tests inject a smaller fixture through the same parser/load path.
* No second normalizer, LLM-supplied aliases/relationships, or automatic
  related-skill edges for unknowns.

Seed format
-----------
JSON-compatible YAML: full-line ``#`` comments are stripped, then the body is
parsed with ``json.loads`` (stdlib only; no YAML package dependency).

ponytail: the ceiling is this small approved taxonomy file; the upgrade path is
a direct pinned YAML parser only when richer YAML syntax is actually required.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.core.settings import repo_root
from app.schemas.profile import CandidateSkill
from app.schemas.skills import SkillRef

PRODUCTION_SKILLS_SEED_RELATIVE: Final[str] = "infrastructure/neo4j/skills_seed.yaml"

# Separators collapsed during comparison / key derivation (punctuation + space).
_SEPARATOR_RE: Final[re.Pattern[str]] = re.compile(
    r"[\s\._\-/\\|,:;()\[\]{}'\"+*!?@&]+"
)


class SkillTaxonomyError(ValueError):
    """Raised when seed data is missing, malformed, or collides deterministically."""


@dataclass(frozen=True, slots=True)
class SeedSkill:
    """One approved taxonomy skill entry."""

    canonical_key: str
    display_name: str
    aliases: tuple[str, ...]
    category: str | None


@dataclass(frozen=True, slots=True)
class RelatedToEdge:
    """One approved seed ``RELATED_TO`` relationship (graph-ready projection)."""

    from_key: str
    to_key: str
    weight: float
    source: str


@dataclass(frozen=True, slots=True)
class SkillTaxonomy:
    """Validated, ordered taxonomy ready for normalization and graph seed load."""

    skills: tuple[SeedSkill, ...]
    relationships: tuple[RelatedToEdge, ...]
    # fingerprint (comparison form) -> canonical_key
    alias_index: Mapping[str, str]
    by_key: Mapping[str, SeedSkill]


def production_skills_seed_path() -> Path:
    """Absolute path of the sole production taxonomy file."""
    return repo_root() / PRODUCTION_SKILLS_SEED_RELATIVE


def _strip_full_line_comments(text: str) -> str:
    """Remove full-line ``#`` comments; preserve non-comment JSON/YAML body lines."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse_skills_seed_text(text: str) -> Any:
    """Parse JSON-compatible seed text (comments stripped) via stdlib JSON."""
    body = _strip_full_line_comments(text).strip()
    if not body:
        raise SkillTaxonomyError("skills seed is empty after removing comments")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SkillTaxonomyError(
            f"skills seed is not valid JSON-compatible YAML: {exc}"
        ) from exc


def unicode_normalize(value: str) -> str:
    """Step 1: Unicode normalize (NFKC)."""
    return unicodedata.normalize("NFKC", value)


def collapse_whitespace(value: str) -> str:
    """Step 2: trim and collapse internal whitespace to single spaces."""
    return " ".join(value.split())


def comparison_lowercase(value: str) -> str:
    """Step 3: casefold for stable canonical comparison."""
    return value.casefold()


def normalize_separators_to_spaces(value: str) -> str:
    """Step 4a: turn common punctuation/separators into spaces."""
    return _SEPARATOR_RE.sub(" ", value)


def comparison_fingerprint(raw: str) -> str:
    """Full comparison form: NFKC → whitespace → casefold → strip separators.

    Alphanumeric runs only (deterministic, separator-insensitive).
    """
    step = unicode_normalize(raw)
    step = collapse_whitespace(step)
    step = comparison_lowercase(step)
    step = normalize_separators_to_spaces(step)
    step = collapse_whitespace(step)
    # Drop remaining non-alnum so ``react.js`` / ``react-js`` / ``React JS`` match.
    return "".join(ch for ch in step if ch.isalnum())


def derive_unknown_canonical_key(raw: str) -> str:
    """Step 6: deterministic key for unresolved skills (underscore-joined tokens)."""
    step = unicode_normalize(raw)
    step = collapse_whitespace(step)
    step = comparison_lowercase(step)
    step = normalize_separators_to_spaces(step)
    step = collapse_whitespace(step)
    tokens = [tok for tok in step.split(" ") if tok]
    # Keep only alnum characters inside each token for a stable graph key.
    cleaned = ["".join(ch for ch in tok if ch.isalnum()) for tok in tokens]
    cleaned = [tok for tok in cleaned if tok]
    if not cleaned:
        raise SkillTaxonomyError(
            f"cannot derive canonical_key from empty/punctuation-only input: {raw!r}"
        )
    return "_".join(cleaned)


def display_name_from_raw(raw: str) -> str:
    """Stable display label for an unknown skill (NFKC + collapsed whitespace)."""
    cleaned = collapse_whitespace(unicode_normalize(raw))
    if not cleaned:
        raise SkillTaxonomyError(
            f"skill display name is empty after normalize: {raw!r}"
        )
    return cleaned


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SkillTaxonomyError(
            f"{label} must be an object, got {type(value).__name__}"
        )
    return value


def _require_list(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SkillTaxonomyError(f"{label} must be a list, got {type(value).__name__}")
    return value


def _parse_optional_category(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillTaxonomyError("skill category must be a string or null")
    category = collapse_whitespace(unicode_normalize(value))
    return category or None


def _parse_weight(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SkillTaxonomyError(f"relationship weight must be a number, got {value!r}")
    weight = float(value)
    if not (0.0 < weight <= 1.0):
        raise SkillTaxonomyError(
            f"relationship weight must be in (0, 1], got {weight!r}"
        )
    return weight


def load_skill_taxonomy(data: Any) -> SkillTaxonomy:
    """Validate seed payload: collisions, endpoints, weights, stable ordering."""
    root = _require_mapping(data, "skills seed root")
    skills_raw = _require_list(root.get("skills"), "skills")
    rels_raw = _require_list(root.get("relationships", []), "relationships")
    unexpected = set(root.keys()) - {"skills", "relationships"}
    if unexpected:
        raise SkillTaxonomyError(
            f"skills seed has unexpected top-level keys: {sorted(unexpected)}"
        )

    by_key: dict[str, SeedSkill] = {}
    alias_index: dict[str, str] = {}

    for index, entry in enumerate(skills_raw):
        item = _require_mapping(entry, f"skills[{index}]")
        unexpected_skill = set(item.keys()) - {
            "canonical_key",
            "display_name",
            "aliases",
            "category",
        }
        if unexpected_skill:
            raise SkillTaxonomyError(
                f"skills[{index}] unexpected keys: {sorted(unexpected_skill)}"
            )

        canonical_key = item.get("canonical_key")
        display_name = item.get("display_name")
        aliases_value = item.get("aliases", [])
        if not isinstance(canonical_key, str) or not canonical_key.strip():
            raise SkillTaxonomyError(
                f"skills[{index}].canonical_key must be a non-empty string"
            )
        if not isinstance(display_name, str) or not display_name.strip():
            raise SkillTaxonomyError(
                f"skills[{index}].display_name must be a non-empty string"
            )
        aliases_seq = _require_list(aliases_value, f"skills[{index}].aliases")

        key = collapse_whitespace(unicode_normalize(canonical_key))
        # Canonical keys are graph identities: lowercase, no spaces.
        if " " in key or key != key.casefold():
            raise SkillTaxonomyError(
                f"skills[{index}].canonical_key must be lowercase "
                f"without spaces: {canonical_key!r}"
            )
        if key in by_key:
            raise SkillTaxonomyError(f"duplicate canonical_key: {key!r}")

        display = collapse_whitespace(unicode_normalize(display_name))
        aliases: list[str] = []
        for a_i, alias in enumerate(aliases_seq):
            if not isinstance(alias, str) or not alias.strip():
                raise SkillTaxonomyError(
                    f"skills[{index}].aliases[{a_i}] must be a non-empty string"
                )
            alias_clean = collapse_whitespace(unicode_normalize(alias))
            aliases.append(alias_clean)

        category = _parse_optional_category(item.get("category"))
        seed = SeedSkill(
            canonical_key=key,
            display_name=display,
            aliases=tuple(aliases),
            category=category,
        )
        by_key[key] = seed

        # Index canonical key fingerprint and each alias fingerprint.
        labels: list[tuple[str, str]] = [
            ("canonical_key", key),
            ("canonical_key", display),
        ]
        labels.extend(("alias", a) for a in aliases)
        for kind, label in labels:
            fp = comparison_fingerprint(label)
            if not fp:
                raise SkillTaxonomyError(
                    f"skills[{index}] {kind} {label!r} has empty comparison fingerprint"
                )
            existing = alias_index.get(fp)
            if existing is not None and existing != key:
                raise SkillTaxonomyError(
                    f"colliding {kind} {label!r} (fingerprint {fp!r}): "
                    f"maps to both {existing!r} and {key!r}"
                )
            alias_index[fp] = key

    relationships: list[RelatedToEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for index, entry in enumerate(rels_raw):
        item = _require_mapping(entry, f"relationships[{index}]")
        unexpected_rel = set(item.keys()) - {"from", "to", "weight", "source"}
        if unexpected_rel:
            raise SkillTaxonomyError(
                f"relationships[{index}] unexpected keys: {sorted(unexpected_rel)}"
            )
        from_key = item.get("from")
        to_key = item.get("to")
        source = item.get("source", "seed")
        if not isinstance(from_key, str) or not from_key.strip():
            raise SkillTaxonomyError(
                f"relationships[{index}].from must be a non-empty string"
            )
        if not isinstance(to_key, str) or not to_key.strip():
            raise SkillTaxonomyError(
                f"relationships[{index}].to must be a non-empty string"
            )
        if not isinstance(source, str) or not source.strip():
            raise SkillTaxonomyError(
                f"relationships[{index}].source must be a non-empty string"
            )
        from_key = collapse_whitespace(unicode_normalize(from_key))
        to_key = collapse_whitespace(unicode_normalize(to_key))
        source = collapse_whitespace(unicode_normalize(source))
        if from_key not in by_key:
            raise SkillTaxonomyError(
                f"relationships[{index}].from {from_key!r} is not a seed skill"
            )
        if to_key not in by_key:
            raise SkillTaxonomyError(
                f"relationships[{index}].to {to_key!r} is not a seed skill"
            )
        if from_key == to_key:
            raise SkillTaxonomyError(
                f"relationships[{index}] self-loop is not allowed: {from_key!r}"
            )
        weight = _parse_weight(item.get("weight"))
        edge_id = (from_key, to_key, source)
        if edge_id in seen_edges:
            raise SkillTaxonomyError(
                f"duplicate relationship {from_key!r} -> {to_key!r} source={source!r}"
            )
        seen_edges.add(edge_id)
        relationships.append(
            RelatedToEdge(
                from_key=from_key,
                to_key=to_key,
                weight=weight,
                source=source,
            )
        )

    ordered_skills = tuple(by_key[k] for k in sorted(by_key.keys()))
    ordered_rels = tuple(
        sorted(relationships, key=lambda e: (e.from_key, e.to_key, e.source))
    )
    return SkillTaxonomy(
        skills=ordered_skills,
        relationships=ordered_rels,
        alias_index=dict(alias_index),
        by_key=dict(by_key),
    )


def load_skill_taxonomy_from_path(path: Path | str) -> SkillTaxonomy:
    """Load and validate a seed file from disk."""
    seed_path = Path(path)
    if not seed_path.is_file():
        raise SkillTaxonomyError(f"skills seed file not found: {seed_path}")
    text = seed_path.read_text(encoding="utf-8")
    return load_skill_taxonomy(parse_skills_seed_text(text))


def load_production_skill_taxonomy() -> SkillTaxonomy:
    """Load the sole production taxonomy under infrastructure/neo4j/."""
    return load_skill_taxonomy_from_path(production_skills_seed_path())


class SkillNormalizer:
    """Deterministic skill identity normalizer backed by one approved taxonomy."""

    def __init__(self, taxonomy: SkillTaxonomy) -> None:
        self._taxonomy = taxonomy

    @classmethod
    def from_path(cls, path: Path | str) -> SkillNormalizer:
        """Build a normalizer from any seed path (tests inject fixtures here)."""
        return cls(load_skill_taxonomy_from_path(path))

    @classmethod
    def production(cls) -> SkillNormalizer:
        """Build a normalizer from the production taxonomy path only."""
        return cls(load_production_skill_taxonomy())

    @property
    def taxonomy(self) -> SkillTaxonomy:
        return self._taxonomy

    def normalize_name(self, raw_name: str) -> SkillRef:
        """Normalize a free-text skill name to a stable ``SkillRef``.

        Known inputs resolve to the seed entry (display, aliases, category).
        Unknown inputs get a deterministic ``canonical_key``, empty aliases,
        ``category=None``, and never receive invented relationships.
        """
        if not isinstance(raw_name, str):
            raise SkillTaxonomyError(
                f"skill name must be a string, got {type(raw_name).__name__}"
            )
        fingerprint = comparison_fingerprint(raw_name)
        if not fingerprint:
            raise SkillTaxonomyError(
                f"skill name is empty after normalization: {raw_name!r}"
            )

        known_key = self._taxonomy.alias_index.get(fingerprint)
        if known_key is not None:
            seed = self._taxonomy.by_key[known_key]
            return SkillRef(
                canonical_key=seed.canonical_key,
                display_name=seed.display_name,
                aliases=list(seed.aliases),
                category=seed.category,
            )

        return SkillRef(
            canonical_key=derive_unknown_canonical_key(raw_name),
            display_name=display_name_from_raw(raw_name),
            aliases=[],
            category=None,
        )

    def normalize_candidate_skill(self, skill: CandidateSkill) -> CandidateSkill:
        """Re-normalize skill identity while preserving correction/exclusion fields.

        ``confidence``, ``proficiency``, ``years``, ``source``, ``excluded``, and
        ``evidence`` are copied unchanged from the input assertion. Lookup prefers
        ``display_name`` when non-empty, else ``canonical_key``.
        """
        raw_for_lookup = skill.skill.display_name.strip() or skill.skill.canonical_key
        normalized = self.normalize_name(raw_for_lookup)
        return CandidateSkill(
            skill=normalized,
            confidence=skill.confidence,
            proficiency=skill.proficiency,
            years=skill.years,
            source=skill.source,
            excluded=skill.excluded,
            evidence=list(skill.evidence),
        )

    def normalize_names(self, names: Iterable[str]) -> list[SkillRef]:
        """Normalize many names; repeats of equivalent inputs yield equal SkillRefs."""
        return [self.normalize_name(name) for name in names]

    def approved_relationships(self) -> tuple[RelatedToEdge, ...]:
        """Return only manually approved seed ``RELATED_TO`` edges (ordered)."""
        return self._taxonomy.relationships

    def relationships_for(self, canonical_key: str) -> tuple[RelatedToEdge, ...]:
        """Seed edges whose ``from_key`` equals ``canonical_key`` (empty if unknown)."""
        return tuple(
            edge
            for edge in self._taxonomy.relationships
            if edge.from_key == canonical_key
        )

    def is_seed_skill(self, canonical_key: str) -> bool:
        return canonical_key in self._taxonomy.by_key

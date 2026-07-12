"""Application service layer (storage, domain orchestration helpers)."""

from app.services.skill_normalization import (
    DEFAULT_SKILLS_SEED_PATH,
    SeedSkillEntry,
    SkillSeedCatalog,
    SkillSeedError,
    load_skills_seed,
    normalize_candidate_skills,
    normalize_skill_match_key,
    provisional_canonical_key,
)

# profile_context is imported from ``app.services.profile_context`` directly by
# chat assembly / tools to avoid package-level import cycles through
# schemas.chat → chat_context.

__all__ = [
    "DEFAULT_SKILLS_SEED_PATH",
    "SeedSkillEntry",
    "SkillSeedCatalog",
    "SkillSeedError",
    "load_skills_seed",
    "normalize_candidate_skills",
    "normalize_skill_match_key",
    "provisional_canonical_key",
]

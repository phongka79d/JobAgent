"""Application service layer (storage, domain orchestration helpers)."""

from app.services.pdf_text import (
    DEFAULT_MAX_PDF_PAGES,
    PdfTextError,
    PdfTextErrorCode,
    PdfTextResult,
    extract_pdf_text,
    usable_character_count,
)
from app.services.pii_redaction import (
    PiiRedactionError,
    PiiRedactionErrorCode,
    RedactionResult,
    assert_no_contact_sentinels,
    redact_pii,
)
from app.services.profile_extraction import (
    ProfileExtractionError,
    ProfileExtractionErrorCode,
    build_cv_extraction_messages,
    build_profile_draft,
)
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
    "DEFAULT_MAX_PDF_PAGES",
    "DEFAULT_SKILLS_SEED_PATH",
    "PdfTextError",
    "PdfTextErrorCode",
    "PdfTextResult",
    "PiiRedactionError",
    "PiiRedactionErrorCode",
    "ProfileExtractionError",
    "ProfileExtractionErrorCode",
    "RedactionResult",
    "SeedSkillEntry",
    "SkillSeedCatalog",
    "SkillSeedError",
    "assert_no_contact_sentinels",
    "build_cv_extraction_messages",
    "build_profile_draft",
    "extract_pdf_text",
    "load_skills_seed",
    "normalize_candidate_skills",
    "normalize_skill_match_key",
    "provisional_canonical_key",
    "redact_pii",
    "usable_character_count",
]

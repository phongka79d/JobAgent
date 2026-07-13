"""Shared skill identity contract (Master §7.1).

``SkillRef`` carries normalized skill identity only. The deterministic
normalizer (later Plan 4 work) populates aliases and category from
``skills_seed.yaml``; an unresolved skill has an empty alias list and may have
no category. The LLM must not invent aliases or relationships.

Later CV and JD skill wrappers (``CandidateSkill``, ``JobSkill``) compose this
type; they must not redefine a parallel skill-identity model.
"""

from __future__ import annotations

from typing import Any

from app.schemas.common import StrictModelConfig
from pydantic import BaseModel


class SkillRef(BaseModel):
    """Normalized skill identity shared by profile and job contracts."""

    model_config = StrictModelConfig

    canonical_key: str
    display_name: str
    aliases: list[str]
    category: str | None


def parse_skill_ref(payload: Any) -> SkillRef:
    """Parse and validate a ``SkillRef`` from arbitrary JSON-like input."""
    return SkillRef.model_validate(payload)

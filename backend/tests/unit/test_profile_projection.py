from app.db.models.profiles import PROFILE_SKILL_TAG_LIMIT
from app.schemas.profile import parse_candidate_profile
from app.services.profile_projection import project_display_name, project_skill_tags


def _profile(full_name: str | None = None):
    return parse_candidate_profile(
        {
            "full_name": full_name,
            "location": None,
            "summary": "Backend engineer",
            "current_title": "Engineer",
            "total_experience_years": 4,
            "skills": [
                {
                    "skill": {
                        "canonical_key": "python",
                        "display_name": "Python",
                        "aliases": [],
                        "category": "language",
                    },
                    "confidence": 0.9,
                    "proficiency": "advanced",
                    "years": 4,
                    "source": "cv",
                    "excluded": False,
                    "evidence": ["Python"],
                }
            ],
            "experiences": [],
            "education": [],
            "languages": [],
            "extraction_confidence": 0.9,
        }
    )


def test_profile_projection_prefers_source_grounded_name() -> None:
    assert project_display_name(_profile(" Ada Lovelace "), "resume.pdf") == (
        "Ada Lovelace"
    )


def test_profile_projection_falls_back_to_sanitized_filename() -> None:
    assert project_display_name(_profile(), "../Ada CV.pdf") == "Ada CV.pdf"


def test_profile_projection_builds_safe_skill_tags() -> None:
    tags, count = project_skill_tags(_profile())
    assert count == 1
    assert tags[0].model_dump() == {"key": "python", "label": "Python"}


def test_profile_projection_bounds_tags_but_counts_all_non_excluded_skills() -> None:
    payload = _profile().model_dump(mode="json")
    payload["skills"] = [
        {
            **payload["skills"][0],
            "skill": {
                **payload["skills"][0]["skill"],
                "canonical_key": f"skill-{index}",
                "display_name": f"Skill {index}",
            },
            "excluded": index == PROFILE_SKILL_TAG_LIMIT + 1,
        }
        for index in range(PROFILE_SKILL_TAG_LIMIT + 2)
    ]

    tags, count = project_skill_tags(parse_candidate_profile(payload))

    assert len(tags) == PROFILE_SKILL_TAG_LIMIT
    assert count == PROFILE_SKILL_TAG_LIMIT + 1

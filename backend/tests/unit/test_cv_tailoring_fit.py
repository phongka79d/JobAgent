from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredCVContent,
    TailoredHeaderSnapshot,
    TailoredItem,
    TailoredSection,
)
from app.schemas.jobs import JobPostExtraction, JobSkill
from app.schemas.skills import SkillRef
from app.services.cv_tailoring_fit import fit_warning_for_content_change


def _skill(label: str) -> JobSkill:
    return JobSkill(
        skill=SkillRef(
            canonical_key=label.casefold().replace(" ", "_"),
            display_name=label,
            aliases=[],
            category=None,
        ),
        confidence=1.0,
        evidence=[label],
    )


def _job() -> JobPostExtraction:
    return JobPostExtraction(
        title="Data Analyst",
        company="Synthetic Co",
        summary="Analyze data platforms",
        responsibilities=["Build dashboards"],
        required_skills=[_skill("Python"), _skill("SQL")],
        preferred_skills=[_skill("Tableau")],
        seniority="senior",
        min_experience_years=None,
        max_experience_years=None,
        location=None,
        work_mode="remote",
        extraction_confidence=1.0,
    )


def _content(text: str) -> TailoredCVContent:
    return TailoredCVContent(
        header=TailoredHeaderSnapshot(
            full_name="Synthetic Candidate",
            location=None,
            phone=None,
            email=None,
            github_url=None,
        ),
        sections=[
            TailoredSection(
                id="summary",
                ordinal=0,
                heading="Summary",
                kind="summary",
                items=[
                    TailoredItem(
                        id="summary:item",
                        source_entry_id="summary:source",
                        title=None,
                        subtitle=None,
                        date_text=None,
                        location=None,
                        body=SourceBoundText(text=text, source_fact_ids=["sf_1"]),
                        bullets=[],
                        attributes=[],
                    )
                ],
            )
        ],
    )


def test_fit_warning_detects_required_jd_skill_regression() -> None:
    warning = fit_warning_for_content_change(
        content=_content("Python analyst with dashboard delivery."),
        parent=_content("Python and SQL analyst with dashboard delivery."),
        job_context=_job(),
    )

    assert warning is not None
    assert "fewer required JD skills" in warning
    assert "SQL" in warning


def test_fit_warning_is_empty_when_coverage_is_preserved() -> None:
    assert (
        fit_warning_for_content_change(
            content=_content("Python and SQL analyst."),
            parent=_content("Python analyst."),
            job_context=_job(),
        )
        is None
    )

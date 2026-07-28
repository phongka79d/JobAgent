from datetime import UTC, datetime

from app.services.job_display import derive_saved_job_display_label

NOW = datetime(2026, 7, 28, tzinfo=UTC)


def test_saved_job_label_prefers_title_and_company() -> None:
    assert derive_saved_job_display_label(
        title="Backend Engineer", company="Acme", summary="ignored", saved_at=NOW
    ) == "Backend Engineer · Acme"


def test_saved_job_label_uses_first_summary_sentence_then_date() -> None:
    assert derive_saved_job_display_label(
        title=None,
        company=None,
        summary="Build APIs. Second sentence.",
        saved_at=NOW,
    ) == "Build APIs"
    assert derive_saved_job_display_label(
        title=None, company=None, summary="   ", saved_at=NOW
    ) == "Untitled saved job · 2026-07-28"


def test_saved_job_label_normalizes_and_bounds_metadata_and_summary() -> None:
    assert derive_saved_job_display_label(
        title="  Ｂackend\tEngineer ",
        company=" Acme  ",
        summary=None,
        saved_at=NOW,
    ) == "Backend Engineer · Acme"
    assert derive_saved_job_display_label(
        title=None,
        company="  Acme\n",
        summary=None,
        saved_at=NOW,
    ) == "Acme"
    assert len(
        derive_saved_job_display_label(
            title="T" * 100,
            company="C" * 100,
            summary=None,
            saved_at=NOW,
        )
    ) == 140
    assert len(
        derive_saved_job_display_label(
            title=None,
            company=None,
            summary=f"{'A' * 130}. Second sentence.",
            saved_at=NOW,
        )
    ) == 120

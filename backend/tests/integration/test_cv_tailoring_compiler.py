"""Real pdflatex evidence when the developer host provides TeX Live."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.core.ids import new_uuid
from app.schemas.cv_tailoring import (
    SourceBoundText,
    TailoredCVContent,
    TailoredHeaderSnapshot,
    TailoredItem,
    TailoredSection,
)
from app.services.cv_tailoring_compiler import compile_latex_cv
from app.services.cv_tailoring_renderer import render_latex_cv
from app.storage.cv_tailoring import TailoringArtifactStorage
from pypdf import PdfReader


@dataclass
class RealCompilerSettings:
    CV_TAILOR_MAX_TEX_CHARS: int = 100_000
    CV_TAILOR_COMPILE_TIMEOUT_SECONDS: int = 15
    CV_TAILOR_MAX_PDF_MB: int = 5


@pytest.mark.asyncio
async def test_real_fixed_bilingual_template_compiles_when_pdflatex_exists(
    tmp_path: Path,
) -> None:
    if shutil.which("pdflatex") is None:
        pytest.skip("pdflatex is not installed on this non-container host")
    # The fixed bilingual template requires these TeX Live inputs; skip only
    # when a developer host's partial installation cannot provide them.
    required_inputs = ("vietnamese.ldf", "t5enc.def", "enumitem.sty", "titlesec.sty")
    missing_inputs = [
        tex_input
        for tex_input in required_inputs
        if not subprocess.run(
            ["kpsewhich", tex_input], capture_output=True, text=True, check=False
        ).stdout.strip()
    ]
    if missing_inputs:
        pytest.skip(
            "fixed bilingual template requires missing TeX inputs: "
            + ", ".join(missing_inputs)
        )

    def item(item_id: str, body: str, title: str | None = None) -> TailoredItem:
        return TailoredItem(
            id=item_id,
            source_entry_id=item_id,
            title=(
                SourceBoundText(text=title, source_fact_ids=["sf_test"])
                if title
                else None
            ),
            body=SourceBoundText(text=body, source_fact_ids=["sf_test"]),
            bullets=[],
            attributes=[],
        )

    content = TailoredCVContent(
        header=TailoredHeaderSnapshot(full_name="Ứng viên Synthetic"),
        sections=[
            TailoredSection(
                id="summary",
                ordinal=0,
                heading="SUMMARY",
                kind="summary",
                items=[item("summary-1", "Synthetic summary")],
            ),
            TailoredSection(
                id="education",
                ordinal=1,
                heading="EDUCATION",
                kind="education",
                items=[item("education-1", "Synthetic University")],
            ),
            TailoredSection(
                id="skills",
                ordinal=2,
                heading="TECHNICAL SKILLS",
                kind="skills",
                items=[item("skills-1", "Python", "technical skills")],
            ),
            TailoredSection(
                id="projects",
                ordinal=3,
                heading="PROJECTS",
                kind="projects",
                items=[item("projects-1", "Built parser", "Resume parser")],
            ),
        ],
    )
    staging = TailoringArtifactStorage(tmp_path).create_staging_dir(
        version_id=new_uuid()
    )
    result = await compile_latex_cv(
        render_latex_cv(content),
        staging_dir=staging,
        settings=RealCompilerSettings(),
    )
    assert result.page_count > 0
    assert result.pdf_path.stat().st_size > 0
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(result.pdf_path).pages
    )
    for heading in ("SUMMARY", "EDUCATION", "TECHNICAL SKILLS", "PROJECTS"):
        assert pdf_text.count(heading) == 1
    assert pdf_text.count("Resume parser") == 1
    assert not (staging / "resume.log").exists()
    assert not (staging / "resume.aux").exists()

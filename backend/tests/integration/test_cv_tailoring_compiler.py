"""Real pdflatex evidence when the developer host provides TeX Live."""

from __future__ import annotations

import shutil
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
    text = SourceBoundText(text="Dịch vụ công cộng", source_fact_ids=["sf_test"])
    content = TailoredCVContent(
        header=TailoredHeaderSnapshot(full_name="Ứng viên Synthetic"),
        sections=[
            TailoredSection(
                id="summary",
                ordinal=0,
                heading="Tóm tắt",
                kind="summary",
                items=[
                    TailoredItem(
                        id="summary-1",
                        source_entry_id="summary-1",
                        body=text,
                        bullets=[],
                        attributes=[],
                    )
                ],
            )
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
    assert not (staging / "resume.log").exists()
    assert not (staging / "resume.aux").exists()

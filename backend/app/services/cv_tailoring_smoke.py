"""No-network build/runtime smoke for the real fixed LaTeX compiler path."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

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


@dataclass(frozen=True, slots=True)
class _SmokeCompilerSettings:
    CV_TAILOR_MAX_TEX_CHARS: int = 100_000
    CV_TAILOR_COMPILE_TIMEOUT_SECONDS: int = 15
    CV_TAILOR_MAX_PDF_MB: int = 5


def _synthetic_content() -> TailoredCVContent:
    body = SourceBoundText(
        text="Synthetic public service — Dịch vụ công cộng",
        source_fact_ids=["sf_smoke"],
    )
    return TailoredCVContent(
        header=TailoredHeaderSnapshot(full_name="Synthetic Candidate"),
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
                        body=body,
                        bullets=[],
                        attributes=[],
                    )
                ],
            )
        ],
    )


async def _run_smoke(root: Path) -> None:
    staging = TailoringArtifactStorage(root).create_staging_dir(
        version_id=new_uuid()
    )
    result = await compile_latex_cv(
        render_latex_cv(_synthetic_content()),
        staging_dir=staging,
        settings=_SmokeCompilerSettings(),
    )
    if result.page_count <= 0 or result.pdf_path.stat().st_size <= 0:
        raise RuntimeError("tailored CV smoke produced no PDF pages")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cv-tailoring-smoke-") as directory:
        asyncio.run(_run_smoke(Path(directory)))


if __name__ == "__main__":
    main()

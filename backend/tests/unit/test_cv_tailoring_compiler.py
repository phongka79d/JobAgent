"""Bounded argv-only LaTeX compiler adapter tests using fake processes."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from app.core.ids import new_uuid
from app.services.cv_tailoring_compiler import (
    TailoringCompileError,
    compile_latex_cv,
)
from app.storage.cv_tailoring import TailoringArtifactStorage
from pypdf import PdfWriter


@dataclass
class CompilerSettings:
    CV_TAILOR_MAX_TEX_CHARS: int = 100_000
    CV_TAILOR_COMPILE_TIMEOUT_SECONDS: float = 1
    CV_TAILOR_MAX_PDF_MB: int = 5


class FakeProcess:
    def __init__(
        self,
        *,
        returncode: int = 0,
        wait_forever: bool = False,
        on_wait: Any = None,
    ) -> None:
        self.returncode: int | None = None
        self._final_returncode = returncode
        self._wait_forever = wait_forever
        self._on_wait = on_wait
        self.killed = False
        self.wait_calls = 0

    async def wait(self) -> int:
        self.wait_calls += 1
        if self._wait_forever and not self.killed:
            await asyncio.Event().wait()
        if self._on_wait is not None:
            self._on_wait()
        self.returncode = -9 if self.killed else self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class RecordingFactory:
    def __init__(
        self,
        staging: Path,
        *,
        pages: int = 1,
        returncodes: tuple[int, ...] = (0, 0),
        create_pdf: bool = True,
        wait_forever: bool = False,
    ) -> None:
        self.staging = staging
        self.pages = pages
        self.returncodes = returncodes
        self.create_pdf = create_pdf
        self.wait_forever = wait_forever
        self.calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        self.processes: list[FakeProcess] = []

    async def __call__(self, *argv: str, **kwargs: Any) -> FakeProcess:
        call_index = len(self.calls)
        self.calls.append((argv, kwargs))

        def finish() -> None:
            (self.staging / "resume.aux").write_text("aux", encoding="utf-8")
            (self.staging / "resume.log").write_text("private log", encoding="utf-8")
            if call_index == 1 and self.create_pdf:
                writer = PdfWriter()
                for _ in range(self.pages):
                    writer.add_blank_page(width=100, height=100)
                with (self.staging / "resume.pdf").open("wb") as handle:
                    writer.write(handle)

        process = FakeProcess(
            returncode=self.returncodes[call_index],
            wait_forever=self.wait_forever,
            on_wait=finish,
        )
        self.processes.append(process)
        return process


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    return TailoringArtifactStorage(tmp_path).create_staging_dir(
        version_id=new_uuid()
    )


@pytest.mark.asyncio
async def test_compiler_runs_exact_safe_argv_twice_and_returns_hashes(
    staging: Path,
) -> None:
    factory = RecordingFactory(staging)
    source = "synthetic bilingual text: Tiếng Việt"
    result = await compile_latex_cv(
        source,
        staging_dir=staging,
        settings=CompilerSettings(),
        process_factory=factory,
    )
    expected_argv = (
        "pdflatex",
        "-no-shell-escape",
        "-halt-on-error",
        "-interaction=nonstopmode",
        f"-output-directory={staging}",
        "resume.tex",
    )
    assert len(factory.calls) == 2
    for argv, kwargs in factory.calls:
        assert argv == expected_argv
        assert kwargs["cwd"] == staging
        assert kwargs["stdin"] == asyncio.subprocess.DEVNULL
        assert kwargs["stdout"] == asyncio.subprocess.DEVNULL
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
        assert "shell" not in kwargs
    assert result.page_count == 1
    assert result.page_warning is None
    assert result.tex_path.name == "resume.tex"
    assert result.pdf_path.name == "resume.pdf"
    assert result.tex_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert result.pdf_sha256 == hashlib.sha256(result.pdf_path.read_bytes()).hexdigest()
    assert {path.name for path in staging.iterdir()} == {"resume.tex", "resume.pdf"}


@pytest.mark.asyncio
async def test_over_two_pages_returns_bounded_warning(staging: Path) -> None:
    result = await compile_latex_cv(
        "synthetic",
        staging_dir=staging,
        settings=CompilerSettings(),
        process_factory=RecordingFactory(staging, pages=3),
    )
    assert result.page_count == 3
    assert result.page_warning == "CV is 3 pages; review length"


@pytest.mark.asyncio
@pytest.mark.parametrize("pages", [0])
async def test_zero_page_pdf_is_rejected_and_staging_is_cleaned(
    staging: Path, pages: int
) -> None:
    with pytest.raises(TailoringCompileError) as captured:
        await compile_latex_cv(
            "synthetic",
            staging_dir=staging,
            settings=CompilerSettings(),
            process_factory=RecordingFactory(staging, pages=pages),
        )
    assert captured.value.code == "TAILORING_COMPILE_FAILED"
    assert list(staging.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("factory_kwargs", "timeout"),
    [
        ({"returncodes": (1,)}, 1),
        ({"returncodes": (0, 2)}, 1),
        ({"create_pdf": False}, 1),
        ({"wait_forever": True}, 0.01),
    ],
)
async def test_process_timeout_status_and_missing_pdf_are_safe_failures(
    staging: Path, factory_kwargs: dict[str, Any], timeout: float
) -> None:
    factory = RecordingFactory(staging, **factory_kwargs)
    with pytest.raises(TailoringCompileError) as captured:
        await compile_latex_cv(
            "synthetic",
            staging_dir=staging,
            settings=CompilerSettings(CV_TAILOR_COMPILE_TIMEOUT_SECONDS=timeout),
            process_factory=factory,
        )
    assert captured.value.code == "TAILORING_COMPILE_FAILED"
    assert "synthetic" not in str(captured.value)
    assert list(staging.iterdir()) == []
    if factory_kwargs.get("wait_forever"):
        assert factory.processes[0].killed is True
        assert factory.processes[0].wait_calls == 2


@pytest.mark.asyncio
async def test_tex_and_pdf_size_bounds_fail_before_return(staging: Path) -> None:
    with pytest.raises(TailoringCompileError):
        await compile_latex_cv(
            "12345",
            staging_dir=staging,
            settings=CompilerSettings(CV_TAILOR_MAX_TEX_CHARS=4),
            process_factory=RecordingFactory(staging),
        )
    assert list(staging.iterdir()) == []

    factory = RecordingFactory(staging)

    def oversized_pdf() -> None:
        (staging / "resume.pdf").write_bytes(b"x" * 1_100_000)

    async def oversized_factory(*argv: str, **kwargs: Any) -> FakeProcess:
        index = len(factory.calls)
        factory.calls.append((argv, kwargs))
        process = FakeProcess(on_wait=oversized_pdf if index == 1 else None)
        factory.processes.append(process)
        return process

    with pytest.raises(TailoringCompileError):
        await compile_latex_cv(
            "synthetic",
            staging_dir=staging,
            settings=CompilerSettings(CV_TAILOR_MAX_PDF_MB=1),
            process_factory=oversized_factory,
        )
    assert list(staging.iterdir()) == []


@pytest.mark.asyncio
async def test_rejects_non_owned_staging_shape_and_pdf_symlink(
    tmp_path: Path, staging: Path
) -> None:
    bad = tmp_path / "not-staging"
    bad.mkdir()
    with pytest.raises(TailoringCompileError):
        await compile_latex_cv(
            "synthetic",
            staging_dir=bad,
            settings=CompilerSettings(),
            process_factory=RecordingFactory(bad),
        )

    outside_pdf = tmp_path / "outside.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with outside_pdf.open("wb") as handle:
        writer.write(handle)

    class SymlinkFactory(RecordingFactory):
        async def __call__(self, *argv: str, **kwargs: Any) -> FakeProcess:
            index = len(self.calls)
            self.calls.append((argv, kwargs))

            def finish() -> None:
                if index == 1:
                    try:
                        (staging / "resume.pdf").symlink_to(outside_pdf)
                    except (OSError, NotImplementedError):
                        pytest.skip("symlinks unavailable")

            process = FakeProcess(on_wait=finish)
            self.processes.append(process)
            return process

    with pytest.raises(TailoringCompileError):
        await compile_latex_cv(
            "synthetic",
            staging_dir=staging,
            settings=CompilerSettings(),
            process_factory=SymlinkFactory(staging),
        )


@pytest.mark.asyncio
async def test_owned_staging_with_unexpected_input_is_rejected_and_cleaned(
    staging: Path,
) -> None:
    (staging / "client-input.png").write_bytes(b"untrusted")
    factory = RecordingFactory(staging)
    with pytest.raises(TailoringCompileError):
        await compile_latex_cv(
            "synthetic",
            staging_dir=staging,
            settings=CompilerSettings(),
            process_factory=factory,
        )
    assert factory.calls == []
    assert list(staging.iterdir()) == []


def test_compiler_source_has_no_shell_or_persisted_process_output() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "cv_tailoring_compiler.py"
    ).read_text(encoding="utf-8")
    assert "create_subprocess_shell" not in source
    assert "shell=True" not in source
    assert "stdout=asyncio.subprocess.PIPE" not in source
    assert "stderr=asyncio.subprocess.PIPE" not in source

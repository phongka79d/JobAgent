"""Bounded argv-only pdflatex adapter for fixed tailored-CV source."""

from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pypdf import PdfReader

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SAFE_ERROR_MESSAGE = "Tailored CV compilation failed"


class TailoringCompilerSettings(Protocol):
    @property
    def CV_TAILOR_MAX_TEX_CHARS(self) -> int: ...

    @property
    def CV_TAILOR_COMPILE_TIMEOUT_SECONDS(self) -> int: ...

    @property
    def CV_TAILOR_MAX_PDF_MB(self) -> int: ...


class ProcessLike(Protocol):
    returncode: int | None

    async def wait(self) -> int: ...

    def kill(self) -> None: ...


class ProcessFactory(Protocol):
    def __call__(
        self,
        *args: str,
        cwd: Path,
        stdin: int,
        stdout: int,
        stderr: int,
    ) -> Awaitable[ProcessLike]: ...


@dataclass(frozen=True, slots=True)
class TailoringCompileResult:
    tex_path: Path
    pdf_path: Path
    tex_sha256: str
    pdf_sha256: str
    page_count: int
    page_warning: str | None


class TailoringCompileError(Exception):
    code = "TAILORING_COMPILE_FAILED"

    def __init__(self) -> None:
        super().__init__(_SAFE_ERROR_MESSAGE)


_DEFAULT_PROCESS_FACTORY = cast(ProcessFactory, asyncio.create_subprocess_exec)


def _validated_staging_dir(staging_dir: Path) -> Path:
    if not isinstance(staging_dir, Path):
        raise TailoringCompileError
    if (
        not staging_dir.is_absolute()
        or staging_dir.is_symlink()
        or staging_dir.parent.name != ".staging"
        or not _UUID_V4_RE.fullmatch(staging_dir.name)
    ):
        raise TailoringCompileError
    resolved = staging_dir.resolve()
    if resolved != staging_dir or not resolved.is_dir():
        raise TailoringCompileError
    return resolved


def _cleanup_staging(staging_dir: Path, *, keep: frozenset[str]) -> None:
    try:
        children = list(staging_dir.iterdir())
    except OSError:
        return
    for child in children:
        if child.name in keep and child.is_file() and not child.is_symlink():
            continue
        try:
            if child.is_symlink() or child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            pass


async def _run_pdflatex(
    *,
    staging_dir: Path,
    settings: TailoringCompilerSettings,
    process_factory: ProcessFactory,
) -> None:
    argv = (
        "pdflatex",
        "-no-shell-escape",
        "-halt-on-error",
        "-interaction=nonstopmode",
        f"-output-directory={staging_dir}",
        "resume.tex",
    )
    process = await process_factory(
        *argv,
        cwd=staging_dir,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        returncode = await asyncio.wait_for(
            process.wait(),
            timeout=settings.CV_TAILOR_COMPILE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        try:
            process.kill()
        except OSError:
            pass
        try:
            await process.wait()
        except Exception:
            pass
        raise TailoringCompileError from None
    if returncode != 0 or process.returncode != 0:
        raise TailoringCompileError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def compile_latex_cv(
    tex_source: str,
    *,
    staging_dir: Path,
    settings: TailoringCompilerSettings,
    process_factory: ProcessFactory = _DEFAULT_PROCESS_FACTORY,
) -> TailoringCompileResult:
    validated: Path | None = None
    try:
        validated = _validated_staging_dir(staging_dir)
        if any(validated.iterdir()):
            raise TailoringCompileError
        if (
            not isinstance(tex_source, str)
            or not tex_source
            or len(tex_source) > settings.CV_TAILOR_MAX_TEX_CHARS
        ):
            raise TailoringCompileError
        tex_path = validated / "resume.tex"
        pdf_path = validated / "resume.pdf"
        tex_path.write_text(tex_source, encoding="utf-8", newline="\n")
        for _ in range(2):
            await _run_pdflatex(
                staging_dir=validated,
                settings=settings,
                process_factory=process_factory,
            )
        if (
            pdf_path.is_symlink()
            or not pdf_path.is_file()
            or pdf_path.resolve().parent != validated
        ):
            raise TailoringCompileError
        max_pdf_bytes = settings.CV_TAILOR_MAX_PDF_MB * 1024 * 1024
        if pdf_path.stat().st_size <= 0 or pdf_path.stat().st_size > max_pdf_bytes:
            raise TailoringCompileError
        page_count = len(PdfReader(pdf_path).pages)
        if page_count <= 0:
            raise TailoringCompileError
        result = TailoringCompileResult(
            tex_path=tex_path,
            pdf_path=pdf_path,
            tex_sha256=_sha256(tex_path),
            pdf_sha256=_sha256(pdf_path),
            page_count=page_count,
            page_warning=(
                f"CV is {page_count} pages; review length"
                if page_count > 2
                else None
            ),
        )
        _cleanup_staging(
            validated,
            keep=frozenset({"resume.tex", "resume.pdf"}),
        )
        return result
    except TailoringCompileError:
        if validated is not None:
            _cleanup_staging(validated, keep=frozenset())
        raise
    except Exception:
        if validated is not None:
            _cleanup_staging(validated, keep=frozenset())
        raise TailoringCompileError from None


__all__ = [
    "ProcessFactory",
    "ProcessLike",
    "TailoringCompileError",
    "TailoringCompileResult",
    "TailoringCompilerSettings",
    "compile_latex_cv",
]

"""Deterministic Plan 1 ShopAIKey / pypdf diagnostic failure coverage (Plan 13).

Fake transport/payload/aggregate tests only. No live provider calls, OCR, or
new fixtures. Asserts exact failure codes, capabilities, non-zero exits,
terminal FAIL markers, and secret/header redaction.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "infrastructure" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import verify_pdf_extraction as pdf_diag  # noqa: E402
from shopaikey_diag import chat_checks, common, embeddings, runner  # noqa: E402

SECRET = "test-secret-never-print"
SETTINGS = common.Settings(
    base_url="https://provider.invalid/v1",
    api_key=SECRET,
    llm_model=common.LOCKED_CHAT_MODEL,
    embedding_model=common.LOCKED_EMBED_MODEL,
    embedding_dimensions=common.LOCKED_DIMENSIONS,
)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx.Response(status, request=request, text="synthetic failure")
    return httpx.HTTPStatusError(
        "synthetic status", request=request, response=response
    )


def _assert_terminal_failure(
    error: common.DiagnosticError,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        common.emit_failure(
            code=error.code,
            capability=error.capability,
            detail=error.detail,
            secret=SECRET,
        )
        != 0
    )
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert f"ERROR={error.code}:" in captured.err
    assert "SHOPAIKEY_COMPATIBILITY=FAIL" in captured.out
    assert SECRET not in combined
    assert "Authorization" not in combined
    assert "Bearer " not in combined


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
        (_status_error(429), "RATE_LIMIT"),
        (ValueError("not-json"), "MALFORMED_RESPONSE"),
    ],
)
def test_diagnostic_normalizes_transport_failures(
    error: Exception,
    expected_code: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mapped = common.classify_http_error(error, "basic_chat", SECRET)
    assert mapped.code == expected_code
    assert mapped.capability == "basic_chat"
    _assert_terminal_failure(mapped, capsys)


def test_diagnostic_rejects_malformed_nonstream_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, request=request, text="{not-json")
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(common.DiagnosticError) as caught:
            common.request_json(
                client,
                "POST",
                f"{SETTINGS.base_url}/chat/completions",
                secret=SECRET,
                capability="basic_chat",
            )
    assert caught.value.code == common.CODE_MALFORMED
    assert caught.value.capability == "basic_chat"
    _assert_terminal_failure(caught.value, capsys)


def test_diagnostic_rejects_missing_chat_and_embedding_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(chat_checks, "request_json", lambda *_a, **_k: {"data": []})
    with pytest.raises(common.DiagnosticError) as caught:
        chat_checks.check_model_discovery(object(), SETTINGS)  # type: ignore[arg-type]
    assert caught.value.code == common.CODE_MODEL_ABSENCE
    assert caught.value.capability == "model_discovery"
    assert common.LOCKED_CHAT_MODEL in caught.value.detail
    assert common.LOCKED_EMBED_MODEL in caught.value.detail
    _assert_terminal_failure(caught.value, capsys)


@pytest.mark.parametrize(
    ("data", "expected_count", "expected_code"),
    [
        ([{"index": 0, "embedding": [0.0] * 1535}], 1, "DIMENSION_MISMATCH"),
        (
            [
                {"index": 1, "embedding": [0.0] * 1536},
                {"index": 0, "embedding": [1.0] * 1536},
            ],
            2,
            "ORDERING_MISMATCH",
        ),
        (
            [
                {"index": 0, "embedding": [0.0] * 1536},
                {"index": 0, "embedding": [1.0] * 1536},
            ],
            2,
            "ORDERING_MISMATCH",
        ),
    ],
)
def test_diagnostic_rejects_dimension_and_index_order(
    data: list[dict[str, object]],
    expected_count: int,
    expected_code: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(common.DiagnosticError) as caught:
        embeddings._validate_data(
            data,
            expected_count=expected_count,
            capability="scalar_batch_embeddings",
        )
    assert caught.value.code == expected_code
    assert caught.value.capability == "scalar_batch_embeddings"
    _assert_terminal_failure(caught.value, capsys)


def test_runner_rejects_unlocked_missing_chat_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = common.Settings(
        base_url=SETTINGS.base_url,
        api_key=SECRET,
        llm_model="missing-chat-model",
        embedding_model=SETTINGS.embedding_model,
        embedding_dimensions=SETTINGS.embedding_dimensions,
    )
    monkeypatch.setattr(runner, "load_settings", lambda **_kwargs: bad)

    assert runner.main() == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "ERROR=MODEL_ABSENCE:" in captured.err
    assert "failed_capability=config" in captured.out
    assert "SHOPAIKEY_COMPATIBILITY=FAIL" in captured.out
    assert SECRET not in combined
    assert "Authorization" not in combined
    assert "Bearer " not in combined


def _digital_row(path: Path, success: bool) -> dict[str, object]:
    return {
        "name": path.name,
        "kind": "digital",
        "pages": 1,
        "normal_non_ws": 400 if success else 0,
        "layout_non_ws": 400 if success else 0,
        "normal_norm_len": 400 if success else 0,
        "layout_norm_len": 400 if success else 0,
        "normal_ok": success,
        "layout_ok": success,
        "success": success,
        "status": "PASS" if success else "FAIL",
    }


def _digital_evaluator(pass_count: int):
    passing = set(pdf_diag.DIGITAL_FIXTURES[:pass_count])
    return lambda path: _digital_row(path, path.name in passing)


def _image_row(path: Path, *, accepted: bool) -> dict[str, object]:
    return {
        "name": path.name,
        "kind": "image_only",
        "pages": 1,
        "normal_non_ws": 400 if accepted else 0,
        "layout_non_ws": 0,
        "normal_norm_len": 400 if accepted else 0,
        "layout_norm_len": 0,
        "normal_ok": accepted,
        "layout_ok": False,
        "accepted": accepted,
        "status": "UNEXPECTED_TEXT" if accepted else pdf_diag.NO_EXTRACTABLE_TEXT,
    }


def test_pdf_gate_fails_below_four_digital_passes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(pdf_diag, "evaluate_digital", _digital_evaluator(3))
    monkeypatch.setattr(
        pdf_diag,
        "evaluate_image_only",
        lambda path: _image_row(path, accepted=False),
    )
    assert pdf_diag.main() == 1
    output = capsys.readouterr()
    assert "digital_below_threshold:3/5" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out


def test_pdf_gate_fails_when_image_only_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(pdf_diag, "evaluate_digital", _digital_evaluator(5))
    monkeypatch.setattr(
        pdf_diag,
        "evaluate_image_only",
        lambda path: _image_row(path, accepted=True),
    )
    assert pdf_diag.main() == 1
    output = capsys.readouterr()
    assert "image_only_not_rejected:UNEXPECTED_TEXT" in output.err
    assert "PYPDF_COMPATIBILITY=FAIL" in output.out


def test_pdf_diagnostic_introduces_no_ocr_dependency() -> None:
    tree = ast.parse(
        (REPO_ROOT / "infrastructure/scripts/verify_pdf_extraction.py").read_text(
            encoding="utf-8"
        )
    )
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(
                alias.name.split(".", 1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(
        {"pytesseract", "ocrmypdf", "easyocr", "pdf2image"}
    )

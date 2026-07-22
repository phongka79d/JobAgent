#!/usr/bin/env python3
"""Finite live-provider diagnostic for profession-neutral CV/JD skills.

The command reads repository-authored synthetic cases, invokes only the
production guarded CV/JD skill extractors, and prints case IDs plus bounded
status/count/code fields. It never opens application stores, embeds, evaluates,
or reads/writes Neo4j.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

APPROVED_CASE_IDS: Final[tuple[str, ...]] = (
    "cv_software",
    "cv_marketing",
    "cv_healthcare_bilingual",
    "jd_sales_operations",
    "jd_finance",
    "jd_unknown_punctuation",
)


def _safe_print(message: str, *, stream: Any = sys.stdout) -> None:
    print(message, file=stream)


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("fixture_shape")
    cases = payload["cases"]
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("fixture_case_shape")
    ids = [case.get("id") for case in cases]
    if ids != list(APPROVED_CASE_IDS):
        raise ValueError("fixture_case_ids")
    return cases


def _expected_keys(case: dict[str, Any], normalizer: Any) -> set[str]:
    names = case.get("expected_skill_names")
    if not isinstance(names, list) or not names:
        raise ValueError("fixture_expected_skills")
    keys: set[str] = set()
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("fixture_expected_skill_name")
        keys.add(normalizer.normalize_name(name).canonical_key)
    return keys


def _actual_keys(outcome: Any, *, kind: str) -> list[str]:
    if kind == "cv":
        rows = outcome.skills
    elif kind == "jd":
        extraction = outcome.extraction
        rows = [*extraction.required_skills, *extraction.preferred_skills]
    else:
        raise ValueError("fixture_kind")
    return [row.skill.canonical_key for row in rows]


def _run_case(
    case: dict[str, Any],
    *,
    cv_invoker: Any,
    jd_invoker: Any,
    normalizer: Any,
    parse_document: Any,
    extract_cv: Any,
    extract_jd: Any,
) -> tuple[str, int, str]:
    """Return only ``(status, skill_count, safe_code)`` for one case."""
    try:
        case_id = case.get("id")
        if case_id not in APPROVED_CASE_IDS:
            return "FAIL", 0, "CASE_NOT_APPROVED"
        kind = case.get("kind")
        expected = _expected_keys(case, normalizer)
        if kind == "cv":
            raw_document = case.get("document")
            if not isinstance(raw_document, dict):
                return "FAIL", 0, "FIXTURE_SOURCE"
            document = parse_document(raw_document)
            outcome = extract_cv(
                document,
                invoker=cv_invoker,
                normalizer=normalizer,
            )
        elif kind == "jd":
            raw_jd = case.get("raw_jd")
            if not isinstance(raw_jd, str) or not raw_jd.strip():
                return "FAIL", 0, "FIXTURE_SOURCE"
            outcome = extract_jd(
                raw_jd,
                invoker=jd_invoker,
                normalizer=normalizer,
            )
        else:
            return "FAIL", 0, "FIXTURE_KIND"
        actual = _actual_keys(outcome, kind=kind)
    except (KeyError, TypeError, ValueError):
        return "FAIL", 0, "FIXTURE_OR_OUTPUT"
    except Exception:
        # Exception text can contain provider or synthetic source bodies.
        return "FAIL", 0, "PROVIDER_OR_RUNTIME"

    count = len(actual)
    if len(set(actual)) != count:
        return "FAIL", count, "DUPLICATE_SKILL"
    if not expected.issubset(set(actual)):
        return "FAIL", count, "EXPECTED_SKILL_MISSING"
    return "PASS", count, "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the finite synthetic cross-profession CV/JD skill diagnostic; "
            "output contains safe IDs, statuses, counts, and codes only."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        required=True,
        help="Path to the repository-authored skill_extraction_golden.json",
    )
    args = parser.parse_args(argv)

    logging.disable(logging.WARNING)
    try:
        cases = _load_cases(args.cases)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
        _safe_print("ERROR=FIXTURE_UNREADABLE", stream=sys.stderr)
        return 2

    try:
        from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL
        from app.core.settings import get_settings
        from app.schemas.cv_document import CVDocument
        from app.services.cv_document_extraction import (
            ShopAIKeyStructuredCVDocumentInvoker,
        )
        from app.services.cv_skill_projection import (
            extract_candidate_skills_from_document,
        )
        from app.services.jd_extraction import (
            ShopAIKeyStructuredJdInvoker,
            extract_job_post_from_text,
        )
        from app.services.skill_normalization import SkillNormalizer
    except ImportError:
        _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
        _safe_print("ERROR=IMPORT_BACKEND", stream=sys.stderr)
        return 2

    try:
        settings = get_settings()
        if settings.LLM_MODEL != LOCKED_CHAT_MODEL:
            _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
            _safe_print("ERROR=MODEL_LOCK", stream=sys.stderr)
            return 2
        if not settings.SHOPAIKEY_API_KEY.get_secret_value().strip():
            _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
            _safe_print("ERROR=MISSING_KEY", stream=sys.stderr)
            return 2
        cv_invoker = ShopAIKeyStructuredCVDocumentInvoker()
        jd_invoker = ShopAIKeyStructuredJdInvoker()
        normalizer = SkillNormalizer.production()
    except Exception:
        _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
        _safe_print("ERROR=PROVIDER_INIT", stream=sys.stderr)
        return 2

    _safe_print("case_id | status | skill_count | code")
    _safe_print("--- | --- | --- | ---")
    failures = 0
    for case in cases:
        status, count, code = _run_case(
            case,
            cv_invoker=cv_invoker,
            jd_invoker=jd_invoker,
            normalizer=normalizer,
            parse_document=CVDocument.model_validate,
            extract_cv=extract_candidate_skills_from_document,
            extract_jd=extract_job_post_from_text,
        )
        if status != "PASS":
            failures += 1
        _safe_print(f"{case['id']} | {status} | {count} | {code}")

    if failures:
        _safe_print(f"failed_cases={failures}")
        _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=FAIL")
        return 1
    _safe_print("CROSS_PROFESSION_SKILL_DIAGNOSTIC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

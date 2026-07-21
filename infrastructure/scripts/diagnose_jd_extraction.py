#!/usr/bin/env python3
"""Bounded synthetic live-provider diagnostic for guarded JD extraction.

Explicit finite command over the approved live subset of
``backend/tests/fixtures/jd_extraction_golden.json``. Uses the configured locked
ShopAIKey provider and the production guarded extractor only.

Never persists, embeds, writes graph state, evaluates, or opens a runtime store.
Prints only case ID and safe pass/fail codes — never source text, evidence,
prompt, provider payload, secrets, or raw exception content.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

# Ensure the installable backend package is importable when run from a checkout.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Finite approved live subset: synthetic cases whose golden extraction is valid
# (empty expected_issues). Guard-negative fixtures are deterministic-only.
APPROVED_LIVE_CASE_IDS: Final[tuple[str, ...]] = (
    "en_sectioned_atomic",
    "vi_one_line_nfkc",
    "en_contact_only",
)

# Scorable live cases must retain usable signal; contact-only must be unscorable.
_SCORABLE_LIVE_CASE_IDS: Final[frozenset[str]] = frozenset(
    {
        "en_sectioned_atomic",
        "vi_one_line_nfkc",
    }
)
_UNSCORABLE_LIVE_CASE_IDS: Final[frozenset[str]] = frozenset({"en_contact_only"})


def _safe_print(message: str, *, stream: Any = sys.stdout) -> None:
    print(message, file=stream)


def _load_cases(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("fixture_shape")
    by_id: dict[str, dict[str, Any]] = {}
    for item in payload["cases"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("fixture_case_shape")
        by_id[item["id"]] = item
    return by_id


def _metadata_invariant_ok(
    *,
    expected: dict[str, Any],
    actual_title: str | None,
    actual_company: str | None,
    actual_location: str | None,
    source_norm: str,
    normalize: Any,
) -> bool:
    """Metadata invariant for live output.

    - Live non-null title/company/location must be source-grounded.
    - Fields the fixture treats as absent (null) must stay null (no invention).
    - When the fixture supplies a value and live also supplies one, the guard
      forms must match. Omission of an expected field is allowed so the
      diagnostic is not a brittle model benchmark.
    """
    pairs = (
        (expected.get("title"), actual_title),
        (expected.get("company"), actual_company),
        (expected.get("location"), actual_location),
    )
    for want, got in pairs:
        if got is None:
            continue
        if normalize(str(got)) not in source_norm:
            return False
        if want is None:
            # Fixture expects absence; inventing metadata fails.
            return False
        if normalize(str(want)) != normalize(str(got)):
            return False
    return True


def _skill_keys(skills: list[Any]) -> list[str]:
    return [skill.skill.canonical_key for skill in skills]


def _expected_skill_keys(
    rows: Any,
    normalizer: Any,
) -> set[str]:
    keys: set[str] = set()
    if not isinstance(rows, list):
        return keys
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        name = row["name"].strip()
        if not name:
            continue
        try:
            keys.add(normalizer.normalize_name(name).canonical_key)
        except ValueError:
            continue
    return keys


def _check_invariants(
    *,
    case_id: str,
    case: dict[str, Any],
    extraction: Any,
    quality: str,
    normalize: Any,
    normalizer: Any,
) -> str | None:
    """Return a safe failure code, or None when all invariants pass."""
    expected = case.get("extraction")
    if not isinstance(expected, dict):
        return "FIXTURE_EXTRACTION"

    raw_jd = case.get("raw_jd")
    if not isinstance(raw_jd, str):
        return "FIXTURE_SOURCE"

    source_norm = normalize(raw_jd)

    # Metadata: grounded live values; no invention when fixture expects null.
    if not _metadata_invariant_ok(
        expected=expected,
        actual_title=extraction.title,
        actual_company=extraction.company,
        actual_location=extraction.location,
        source_norm=source_norm,
        normalize=normalize,
    ):
        return "METADATA"

    # Grounding: responsibilities and skill evidence must be source-contained.
    for responsibility in extraction.responsibilities:
        if responsibility and normalize(responsibility) not in source_norm:
            return "GROUNDING"
    for skill in (*extraction.required_skills, *extraction.preferred_skills):
        for snippet in skill.evidence:
            if snippet and normalize(snippet) not in source_norm:
                return "GROUNDING"

    # Group: canonical keys unique within and across required/preferred.
    required_keys = _skill_keys(extraction.required_skills)
    preferred_keys = _skill_keys(extraction.preferred_skills)
    if len(required_keys) != len(set(required_keys)):
        return "GROUP"
    if len(preferred_keys) != len(set(preferred_keys)):
        return "GROUP"
    if set(required_keys) & set(preferred_keys):
        return "GROUP"

    # Atomicity: fixture expected skill identities must appear in the live group.
    if not _expected_skill_keys(
        expected.get("required_skills"),
        normalizer,
    ).issubset(set(required_keys)):
        return "ATOMICITY"
    if not _expected_skill_keys(
        expected.get("preferred_skills"),
        normalizer,
    ).issubset(set(preferred_keys)):
        return "ATOMICITY"

    # Quality branch:
    # - contact-only must classify as unscorable (no invented role signal).
    # - scorable synthetic JDs must retain usable signal (responsibility or
    #   evidenced skill). Summary is model-authored free text and is not
    #   source-grounded; blank summary alone may yield classifier "unscorable"
    #   even when grounded skills exist, so the live gate is usable signal plus
    #   contact-only branch correctness rather than a brittle full|partial enum
    #   match (not a model benchmark).
    if case_id in _UNSCORABLE_LIVE_CASE_IDS:
        if quality != "unscorable":
            return "QUALITY"
        if extraction.required_skills or extraction.preferred_skills:
            return "QUALITY"
        if any((item or "").strip() for item in extraction.responsibilities):
            return "QUALITY"
    elif case_id in _SCORABLE_LIVE_CASE_IDS:
        has_responsibility = any(
            (item or "").strip() for item in extraction.responsibilities
        )
        has_evidenced_skill = any(
            (snippet or "").strip()
            for skill in (
                *extraction.required_skills,
                *extraction.preferred_skills,
            )
            for snippet in skill.evidence
        )
        if not (has_responsibility or has_evidenced_skill):
            return "QUALITY"
    else:
        return "LIVE_SCOPE"

    return None


def _run_case(
    *,
    case_id: str,
    case: dict[str, Any],
    invoker: Any,
    normalizer: Any,
    extract_fn: Any,
    classify_fn: Any,
    normalize: Any,
    extraction_error_type: type[BaseException],
) -> tuple[str, str]:
    """Return (status, safe_detail) for one live case. Never echoes payloads."""
    raw_jd = case.get("raw_jd")
    if not isinstance(raw_jd, str) or not raw_jd.strip():
        return "FAIL", "FIXTURE_SOURCE"

    try:
        outcome = extract_fn(
            raw_jd,
            invoker=invoker,
            normalizer=normalizer,
        )
    except extraction_error_type as exc:
        code = getattr(exc, "code", None)
        if isinstance(code, str) and code:
            return "FAIL", code
        return "FAIL", "EXTRACTION"
    except Exception:
        # Never print exception text (may contain provider/body fragments).
        return "FAIL", "PROVIDER_OR_RUNTIME"

    extraction = outcome.extraction
    quality = classify_fn(extraction)
    failure = _check_invariants(
        case_id=case_id,
        case=case,
        extraction=extraction,
        quality=quality,
        normalize=normalize,
        normalizer=normalizer,
    )
    if failure is not None:
        return "FAIL", failure
    return "PASS", "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Finite synthetic live-provider diagnostic for guarded JD extraction. "
            "Requires configured ShopAIKey credentials; prints only case IDs and "
            "safe status codes."
        )
    )
    parser.add_argument(
        "--cases",
        type=Path,
        required=True,
        help="Path to jd_extraction_golden.json (synthetic fixture only)",
    )
    args = parser.parse_args(argv)

    # Suppress application debug logs that might name internal paths.
    logging.disable(logging.WARNING)

    cases_path = args.cases
    if not cases_path.is_file():
        _safe_print("ERROR=missing_fixture", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    try:
        from app.adapters.shopaikey_chat import LOCKED_CHAT_MODEL
        from app.core.settings import get_settings
        from app.services.jd_extraction import (
            JdExtractionError,
            ShopAIKeyStructuredJdInvoker,
            extract_job_post_from_text,
        )
        from app.services.jd_extraction_guard import normalize_guard_text
        from app.services.jd_quality import classify_jd_quality
        from app.services.skill_normalization import SkillNormalizer
    except ImportError:
        _safe_print("ERROR=import_backend", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    try:
        settings = get_settings()
    except Exception:
        _safe_print("ERROR=MISSING_OR_INVALID_SETTINGS", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    api_key = settings.SHOPAIKEY_API_KEY.get_secret_value().strip()
    if not api_key:
        _safe_print("MISSING_VARIABLE=SHOPAIKEY_API_KEY", stream=sys.stderr)
        _safe_print("ERROR=MISSING_KEY", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    if settings.LLM_MODEL != LOCKED_CHAT_MODEL:
        _safe_print(
            f"ERROR=MODEL_LOCK:llm={settings.LLM_MODEL}",
            stream=sys.stderr,
        )
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    try:
        all_cases = _load_cases(cases_path)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        _safe_print("ERROR=fixture_unreadable", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    missing = [
        case_id
        for case_id in APPROVED_LIVE_CASE_IDS
        if case_id not in all_cases
    ]
    if missing:
        _safe_print(
            f"ERROR=missing_live_cases:{len(missing)}",
            stream=sys.stderr,
        )
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    try:
        invoker = ShopAIKeyStructuredJdInvoker()
        normalizer = SkillNormalizer.production()
    except Exception:
        _safe_print("ERROR=provider_client_init", stream=sys.stderr)
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 2

    _safe_print(f"locked_llm_model={LOCKED_CHAT_MODEL}")
    _safe_print(f"live_case_count={len(APPROVED_LIVE_CASE_IDS)}")
    _safe_print("case_id | status | detail")
    _safe_print("--- | --- | ---")

    failures = 0
    for case_id in APPROVED_LIVE_CASE_IDS:
        status, detail = _run_case(
            case_id=case_id,
            case=all_cases[case_id],
            invoker=invoker,
            normalizer=normalizer,
            extract_fn=extract_job_post_from_text,
            classify_fn=classify_jd_quality,
            normalize=normalize_guard_text,
            extraction_error_type=JdExtractionError,
        )
        if status != "PASS":
            failures += 1
        _safe_print(f"{case_id} | {status} | {detail}")

    if failures:
        _safe_print(f"failed_cases={failures}")
        _safe_print("JD_EXTRACTION_DIAGNOSTIC=FAIL")
        return 1

    _safe_print("JD_EXTRACTION_DIAGNOSTIC=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

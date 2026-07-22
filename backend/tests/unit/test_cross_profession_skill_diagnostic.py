from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "infrastructure" / "scripts" / "diagnose_cross_profession_skills.py"
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "skill_extraction_golden.json"

EXPECTED_CASE_IDS = (
    "cv_software",
    "cv_marketing",
    "cv_healthcare_bilingual",
    "jd_sales_operations",
    "jd_finance",
    "jd_unknown_punctuation",
)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cross_profession_diag", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_uses_one_finite_cross_profession_synthetic_corpus() -> None:
    module = _module()
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert module.APPROVED_CASE_IDS == EXPECTED_CASE_IDS
    assert [case["id"] for case in payload["cases"]] == list(EXPECTED_CASE_IDS)
    assert {case["kind"] for case in payload["cases"]} == {"cv", "jd"}
    assert all(case["expected_skill_names"] for case in payload["cases"])
    serialized = json.dumps(payload, ensure_ascii=False).casefold()
    assert "api_key" not in serialized
    assert "provider_payload" not in serialized
    assert payload["provenance"] == "repository-authored synthetic"


class _CandidateOutcome:
    def __init__(self, labels: list[str]) -> None:
        self.skills = [
            type(
                "CandidateSkillFact",
                (),
                {
                    "skill": type(
                        "SkillRefFact",
                        (),
                        {"canonical_key": label.casefold().replace(" ", "_")},
                    )()
                },
            )()
            for label in labels
        ]


class _JobOutcome:
    def __init__(self, labels: list[str]) -> None:
        rows = [
            type(
                "JobSkillFact",
                (),
                {
                    "skill": type(
                        "SkillRefFact",
                        (),
                        {"canonical_key": label.casefold().replace(" ", "_")},
                    )()
                },
            )()
            for label in labels
        ]
        self.extraction = type(
            "JobExtractionFact",
            (),
            {"required_skills": rows, "preferred_skills": []},
        )()


class _Normalizer:
    def normalize_name(self, label: str) -> Any:
        return type(
            "SkillRefFact",
            (),
            {"canonical_key": label.casefold().replace(" ", "_")},
        )()


def test_case_runner_reports_only_safe_status_count_and_code() -> None:
    module = _module()
    normalizer = _Normalizer()
    cv_case = {
        "id": "cv_marketing",
        "kind": "cv",
        "document": {"synthetic": True},
        "expected_skill_names": ["Audience Research"],
    }
    jd_case = {
        "id": "jd_finance",
        "kind": "jd",
        "raw_jd": "private synthetic source",
        "expected_skill_names": ["Variance Analysis"],
    }

    cv_result = module._run_case(
        cv_case,
        cv_invoker=object(),
        jd_invoker=object(),
        normalizer=normalizer,
        parse_document=lambda raw: raw,
        extract_cv=lambda document, **kwargs: _CandidateOutcome(
            ["Audience Research"]
        ),
        extract_jd=lambda raw, **kwargs: None,
    )
    jd_result = module._run_case(
        jd_case,
        cv_invoker=object(),
        jd_invoker=object(),
        normalizer=normalizer,
        parse_document=lambda raw: raw,
        extract_cv=lambda document, **kwargs: None,
        extract_jd=lambda raw, **kwargs: _JobOutcome(["Variance Analysis"]),
    )

    assert cv_result == ("PASS", 1, "ok")
    assert jd_result == ("PASS", 1, "ok")
    assert "private synthetic source" not in repr(jd_result)


def test_case_runner_redacts_provider_and_source_failures() -> None:
    module = _module()

    def fail(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise RuntimeError("secret source and provider body")

    result = module._run_case(
        {
            "id": "cv_software",
            "kind": "cv",
            "document": {"secret": "source"},
            "expected_skill_names": ["Python"],
        },
        cv_invoker=object(),
        jd_invoker=object(),
        normalizer=_Normalizer(),
        parse_document=lambda raw: raw,
        extract_cv=fail,
        extract_jd=fail,
    )

    assert result == ("FAIL", 0, "PROVIDER_OR_RUNTIME")
    assert "secret" not in repr(result)


def test_diagnostic_has_no_store_graph_embedding_or_evaluation_imports() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imports = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    forbidden = (
        "app.db",
        "app.graph",
        "app.repositories",
        "app.services.embedding",
        "app.services.job_evaluation",
    )
    assert not any(
        imported.startswith(prefix)
        for imported in imports
        for prefix in forbidden
    )

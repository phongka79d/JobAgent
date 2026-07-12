"""Extraction prediction parse and aggregate scoring (Plan 6 / 05B)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from evaluation.dataset_contracts import (
    PROTOCOL_ID,
    SCHEMA_VERSION,
    ExtractionDataset,
    assert_no_forbidden_fields,
    content_digest,
)
from evaluation.metrics import (
    EXTRACTION_TIMEOUT_SECONDS_MAX,
    LOCATION_ACCURACY_MIN,
    SENIORITY_MACRO_F1_MIN,
    SKILL_ENTITY_F1_MIN,
    WORK_MODE_MACRO_F1_MIN,
    MetricGate,
    all_gates_pass,
    field_accuracy,
    gates_as_mapping,
    macro_f1,
    mean_entity_set_f1,
    threshold_gate,
    threshold_gate_max,
)

RUNNER_ID: Final[str] = "plan6_extraction_runner_v1"
PREDICTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"ok", "timeout", "invalid", "missing"}
)

class ExtractionRunnerError(ValueError):
    """Raised when extraction evaluation inputs are invalid."""

@dataclass(frozen=True, slots=True)
class ExtractionPrediction:
    entity_id: str
    required_skills: tuple[str, ...]
    preferred_skills: tuple[str, ...]
    seniority: str
    work_mode: str
    location: str
    duration_seconds: float
    status: str

@dataclass(frozen=True, slots=True)
class ExtractionEvalResult:
    protocol_id: str
    runner_id: str
    item_count: int
    gold_digest: str
    prediction_digest: str
    metrics: dict[str, float]
    gates: tuple[MetricGate, ...]
    overall: Literal["PASS", "FAIL"]
    missing_prediction_count: int
    invalid_prediction_count: int
    timeout_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "data_class": "safe_aggregate",
            "protocol_id": self.protocol_id,
            "runner_id": self.runner_id,
            "item_count": self.item_count,
            "gold_digest": self.gold_digest,
            "prediction_digest": self.prediction_digest,
            "metrics": self.metrics,
            "gates": gates_as_mapping(self.gates),
            "overall": self.overall,
            "missing_prediction_count": self.missing_prediction_count,
            "invalid_prediction_count": self.invalid_prediction_count,
            "timeout_count": self.timeout_count,
        }

def _as_str_list(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ExtractionRunnerError(f"{field} must be a list of strings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ExtractionRunnerError(f"{field} items must be strings")
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out

def _finite_nonneg(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ExtractionRunnerError(f"{field} must be a number")
    number = float(value)
    if number < 0.0 or number != number or number in (float("inf"), float("-inf")):
        raise ExtractionRunnerError(f"{field} must be finite and >= 0")
    return number

def parse_extraction_predictions(
    payload: Mapping[str, Any],
) -> dict[str, ExtractionPrediction]:
    assert_no_forbidden_fields(payload)
    raw_items = payload.get("predictions")
    if not isinstance(raw_items, list):
        raise ExtractionRunnerError("predictions must be a list")
    parsed: dict[str, ExtractionPrediction] = {}
    for index, entry in enumerate(raw_items):
        if not isinstance(entry, Mapping):
            raise ExtractionRunnerError(f"predictions[{index}] must be an object")
        assert_no_forbidden_fields(entry, path=f"$.predictions[{index}]")
        entity_id = entry.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ExtractionRunnerError(f"predictions[{index}].entity_id required")
        entity_key = entity_id.strip()
        if entity_key in parsed:
            raise ExtractionRunnerError(f"duplicate prediction entity_id {entity_key!r}")
        status_raw = entry.get("status", "ok")
        if not isinstance(status_raw, str) or status_raw not in PREDICTION_STATUSES:
            raise ExtractionRunnerError(
                f"predictions[{index}].status must be one of "
                + ", ".join(sorted(PREDICTION_STATUSES))
            )
        seniority = entry.get("seniority", "")
        work_mode = entry.get("work_mode", "")
        location = entry.get("location", "")
        if not all(isinstance(v, str) for v in (seniority, work_mode, location)):
            raise ExtractionRunnerError(
                f"predictions[{index}] seniority/work_mode/location must be strings"
            )
        parsed[entity_key] = ExtractionPrediction(
            entity_id=entity_key,
            required_skills=tuple(
                _as_str_list(entry.get("required_skills"), field="required_skills")
            ),
            preferred_skills=tuple(
                _as_str_list(entry.get("preferred_skills"), field="preferred_skills")
            ),
            seniority=seniority.strip(),
            work_mode=work_mode.strip(),
            location=location.strip(),
            duration_seconds=_finite_nonneg(
                entry.get("duration_seconds", 0.0),
                field=f"predictions[{index}].duration_seconds",
            ),
            status=status_raw,
        )
    return parsed

def _empty_prediction(entity_id: str, *, status: str) -> ExtractionPrediction:
    duration = (
        EXTRACTION_TIMEOUT_SECONDS_MAX + 1.0 if status == "timeout" else 0.0
    )
    return ExtractionPrediction(
        entity_id=entity_id,
        required_skills=(),
        preferred_skills=(),
        seniority="",
        work_mode="",
        location="",
        duration_seconds=duration,
        status=status,
    )

def _coerce_prediction(
    entity_id: str,
    pred: ExtractionPrediction | None,
) -> tuple[ExtractionPrediction, str]:
    if pred is None or pred.status == "missing":
        return _empty_prediction(entity_id, status="missing"), "missing"
    if pred.status == "invalid":
        return _empty_prediction(entity_id, status="invalid"), "invalid"
    if pred.status == "timeout":
        duration = pred.duration_seconds
        if duration <= EXTRACTION_TIMEOUT_SECONDS_MAX:
            duration = EXTRACTION_TIMEOUT_SECONDS_MAX + 1.0
        return (
            ExtractionPrediction(
                entity_id=entity_id,
                required_skills=(),
                preferred_skills=(),
                seniority="",
                work_mode="",
                location="",
                duration_seconds=duration,
                status="timeout",
            ),
            "timeout",
        )
    return pred, "ok"

def evaluate_extraction(
    gold: ExtractionDataset,
    predictions: Mapping[str, ExtractionPrediction],
) -> ExtractionEvalResult:
    """Score all gold items; missing/invalid predictions fail closed."""
    required_pairs: list[tuple[Sequence[str], Sequence[str]]] = []
    preferred_pairs: list[tuple[Sequence[str], Sequence[str]]] = []
    gold_seniority: list[str] = []
    pred_seniority: list[str] = []
    gold_work_mode: list[str] = []
    pred_work_mode: list[str] = []
    gold_location: list[str] = []
    pred_location: list[str] = []
    durations: list[float] = []
    missing = invalid = timeouts = 0
    for item in gold.items:
        pred, kind = _coerce_prediction(item.entity_id, predictions.get(item.entity_id))
        if kind == "missing":
            missing += 1
        elif kind == "invalid":
            invalid += 1
        elif kind == "timeout":
            timeouts += 1
        required_pairs.append((item.required_skills, list(pred.required_skills)))
        preferred_pairs.append((item.preferred_skills, list(pred.preferred_skills)))
        gold_seniority.append(item.seniority)
        pred_seniority.append(pred.seniority)
        gold_work_mode.append(item.work_mode)
        pred_work_mode.append(pred.work_mode)
        gold_location.append(item.location)
        pred_location.append(pred.location)
        durations.append(pred.duration_seconds)
    required_f1 = mean_entity_set_f1(required_pairs)
    preferred_f1 = mean_entity_set_f1(preferred_pairs)
    skill_f1 = (required_f1 + preferred_f1) / 2.0
    seniority_f1 = macro_f1(gold_seniority, pred_seniority)
    work_mode_f1 = macro_f1(gold_work_mode, pred_work_mode)
    location_acc = field_accuracy(gold_location, pred_location)
    max_duration = max(durations) if durations else 0.0
    gates = (
        threshold_gate(name="skill_entity_f1", value=round(skill_f1, 6), minimum=SKILL_ENTITY_F1_MIN),
        threshold_gate(name="seniority_macro_f1", value=round(seniority_f1, 6), minimum=SENIORITY_MACRO_F1_MIN),
        threshold_gate(name="work_mode_macro_f1", value=round(work_mode_f1, 6), minimum=WORK_MODE_MACRO_F1_MIN),
        threshold_gate(name="location_accuracy", value=round(location_acc, 6), minimum=LOCATION_ACCURACY_MIN),
        threshold_gate_max(
            name="extraction_timeout_seconds",
            value=round(max_duration, 6),
            maximum=EXTRACTION_TIMEOUT_SECONDS_MAX,
        ),
    )
    metrics = {
        "required_skill_entity_f1": round(required_f1, 6),
        "preferred_skill_entity_f1": round(preferred_f1, 6),
        "skill_entity_f1": round(skill_f1, 6),
        "seniority_macro_f1": round(seniority_f1, 6),
        "work_mode_macro_f1": round(work_mode_f1, 6),
        "location_accuracy": round(location_acc, 6),
        "extraction_timeout_seconds_max": round(max_duration, 6),
    }
    gold_digest = content_digest([item.model_dump(mode="json") for item in gold.items])
    pred_digest = content_digest(
        {
            key: {
                "entity_id": pred.entity_id,
                "required_skills": list(pred.required_skills),
                "preferred_skills": list(pred.preferred_skills),
                "seniority": pred.seniority,
                "work_mode": pred.work_mode,
                "location": pred.location,
                "duration_seconds": pred.duration_seconds,
                "status": pred.status,
            }
            for key, pred in sorted(predictions.items())
        }
    )
    overall: Literal["PASS", "FAIL"] = "PASS" if all_gates_pass(gates) else "FAIL"
    return ExtractionEvalResult(
        protocol_id=PROTOCOL_ID,
        runner_id=RUNNER_ID,
        item_count=len(gold.items),
        gold_digest=gold_digest,
        prediction_digest=pred_digest,
        metrics=metrics,
        gates=gates,
        overall=overall,
        missing_prediction_count=missing,
        invalid_prediction_count=invalid,
        timeout_count=timeouts,
    )

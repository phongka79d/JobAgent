"""Parse ranking feature envelopes into RankingItem rows (Plan 6 / 05C)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from evaluation.ranking_types import RankingItem, RankingRunnerError

__all__ = ["parse_ranking_items"]


def parse_ranking_items(payload: Mapping[str, Any]) -> tuple[RankingItem, ...]:
    """Parse ranking feature+label rows (aggregate-safe IDs only)."""
    from evaluation.dataset_privacy import assert_no_forbidden_fields

    assert_no_forbidden_fields(payload)
    items_raw = payload.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise RankingRunnerError("ranking input requires non-empty items list")
    out: list[RankingItem] = []
    seen: set[str] = set()
    for index, raw in enumerate(items_raw):
        if not isinstance(raw, Mapping):
            raise RankingRunnerError(f"items[{index}] must be an object")
        entity_id = str(raw.get("entity_id", "")).strip()
        if not entity_id:
            raise RankingRunnerError(f"items[{index}] missing entity_id")
        if entity_id in seen:
            raise RankingRunnerError(f"duplicate entity_id: {entity_id}")
        seen.add(entity_id)
        relevance = raw.get("relevance")
        if not isinstance(relevance, int) or isinstance(relevance, bool):
            raise RankingRunnerError(f"{entity_id}: relevance must be int 0-3")
        if relevance < 0 or relevance > 3:
            raise RankingRunnerError(f"{entity_id}: relevance must be int 0-3")
        components = raw.get("components")
        if not isinstance(components, Mapping):
            raise RankingRunnerError(f"{entity_id}: components object required")
        out.append(
            RankingItem(
                entity_id=entity_id,
                relevance=relevance,
                semantic_similarity=_req_unit(
                    components, "semantic_similarity", entity_id=entity_id
                ),
                skill_score_exact=_req_unit(
                    components, "skill_score_exact", entity_id=entity_id
                ),
                skill_score_graph=_req_unit(
                    components, "skill_score_graph", entity_id=entity_id
                ),
                seniority_score=_opt_unit(
                    components, "seniority_score", entity_id=entity_id
                ),
                experience_score=_opt_unit(
                    components, "experience_score", entity_id=entity_id
                ),
                location_score=_opt_unit(
                    components, "location_score", entity_id=entity_id
                ),
                work_mode_score=_opt_unit(
                    components, "work_mode_score", entity_id=entity_id
                ),
                match_latency_seconds=_opt_nonneg(
                    raw, "match_latency_seconds", default=0.0, entity_id=entity_id
                ),
            )
        )
    return tuple(out)


def _req_unit(components: Mapping[str, Any], key: str, *, entity_id: str) -> float:
    if key not in components:
        raise RankingRunnerError(f"{entity_id}: missing components.{key}")
    value = components[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RankingRunnerError(f"{entity_id}: components.{key} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise RankingRunnerError(f"{entity_id}: components.{key} must be in [0,1]")
    return number


def _opt_unit(
    components: Mapping[str, Any], key: str, *, entity_id: str
) -> float | None:
    if key not in components or components[key] is None:
        return None
    return _req_unit(components, key, entity_id=entity_id)


def _opt_nonneg(
    raw: Mapping[str, Any],
    key: str,
    *,
    default: float,
    entity_id: str,
) -> float:
    if key not in raw or raw[key] is None:
        return default
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RankingRunnerError(f"{entity_id}: {key} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise RankingRunnerError(f"{entity_id}: {key} must be finite and non-negative")
    return number

"""Entity-set and label classification metric primitives (shared evaluation)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from app.services.skill_normalization import normalize_skill_match_key

__all__ = [
    "entity_set_f1",
    "field_accuracy",
    "macro_f1",
    "mean_entity_set_f1",
    "normalize_entity_token",
    "normalize_entity_token_set",
]


def normalize_entity_token(value: str) -> str:
    """Deterministic entity comparison form (production skill match key)."""
    cleaned = " ".join(str(value).strip().split())
    if not cleaned:
        return ""
    return normalize_skill_match_key(cleaned)


def normalize_entity_token_set(values: Iterable[str]) -> frozenset[str]:
    out: set[str] = set()
    for raw in values:
        token = normalize_entity_token(raw)
        if token:
            out.add(token)
    return frozenset(out)


def entity_set_f1(gold: Iterable[str], predicted: Iterable[str]) -> float:
    """Set F1 for one multi-label entity field (skills).

    Empty gold and empty predicted yield 1.0. Empty gold with non-empty
    predicted (or the reverse) yields 0.0.
    """
    gold_set = normalize_entity_token_set(gold)
    pred_set = normalize_entity_token_set(predicted)
    if not gold_set and not pred_set:
        return 1.0
    if not gold_set or not pred_set:
        return 0.0
    intersection = len(gold_set & pred_set)
    precision = intersection / len(pred_set)
    recall = intersection / len(gold_set)
    if precision + recall <= 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def mean_entity_set_f1(
    pairs: Sequence[tuple[Sequence[str], Sequence[str]]],
) -> float:
    """Macro-average set F1 over item pairs ``(gold, predicted)``."""
    if not pairs:
        return 0.0
    total = sum(entity_set_f1(gold, pred) for gold, pred in pairs)
    return total / len(pairs)


def field_accuracy(
    gold_labels: Sequence[str],
    predicted_labels: Sequence[str],
) -> float:
    """Exact token-normalized accuracy; length mismatch fails closed at 0.0."""
    if not gold_labels:
        return 0.0
    if len(gold_labels) != len(predicted_labels):
        return 0.0
    correct = 0
    for gold, pred in zip(gold_labels, predicted_labels, strict=True):
        if normalize_entity_token(gold) == normalize_entity_token(pred):
            if normalize_entity_token(gold):
                correct += 1
            elif not normalize_entity_token(pred):
                correct += 1
    return correct / len(gold_labels)


def macro_f1(
    gold_labels: Sequence[str],
    predicted_labels: Sequence[str],
) -> float:
    """Unweighted mean of per-class F1 over the gold∪pred label universe."""
    if not gold_labels:
        return 0.0
    if len(gold_labels) != len(predicted_labels):
        return 0.0
    gold_norm = [normalize_entity_token(label) or "__empty__" for label in gold_labels]
    pred_norm = [
        normalize_entity_token(label) or "__empty__" for label in predicted_labels
    ]
    labels = sorted(set(gold_norm) | set(pred_norm))
    if not labels:
        return 0.0
    gold_counts = Counter(gold_norm)
    pred_counts = Counter(pred_norm)
    pair_counts = Counter(zip(gold_norm, pred_norm, strict=True))
    scores: list[float] = []
    for label in labels:
        tp = pair_counts[(label, label)]
        fp = pred_counts[label] - tp
        fn = gold_counts[label] - tp
        if tp == 0 and fp == 0 and fn == 0:
            scores.append(1.0)
            continue
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        if precision + recall <= 0.0:
            scores.append(0.0)
        else:
            scores.append((2.0 * precision * recall) / (precision + recall))
    return sum(scores) / len(scores)

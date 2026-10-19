"""Human overrides, explicit weight sensitivity and finite-objective Pareto sets."""

from copy import deepcopy
from math import isfinite


def _score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 4:
        raise ValueError("scores must be finite numbers on the documented 0–4 ordinal rubric")
    return float(value)


def apply_human_ratings(report, ratings):
    """Return a new report; human judgments override estimates without erasing them.

    Each rating requires metric_id, score, evaluator and rationale. Optional
    version must match the report; cross-version ratings are rejected as stale.
    This records a judgment, not evidence of population-level calibration.
    """
    result = deepcopy(report)
    history = result.setdefault("calibration", {}).setdefault("human_rating_history", [])
    for rating in ratings:
        metric = rating["metric_id"]
        if metric not in result["dimensions"]:
            raise ValueError(f"unknown benchmark dimension {metric}")
        if not rating.get("evaluator") or not rating.get("rationale"):
            raise ValueError("human ratings require evaluator and rationale")
        record = result["dimensions"][metric]
        if rating.get("version", record["version"]) != record["version"]:
            raise ValueError("human rating is stale for this story version")
        score = _score(rating["score"])
        record["human_score"] = score
        record["effective_score"] = score
        record["effective_score_source"] = "human_override"
        history.append({**deepcopy(rating), "score": score, "version": record["version"]})
    result["quality_vector"] = {metric: entry.get("human_score") if entry.get("human_score") is not None else entry.get("model_score") for metric, entry in result["dimensions"].items()}
    result["calibration"]["status"] = "HUMAN_ANNOTATED_UNCALIBRATED" if history else "UNCALIBRATED"
    result["calibration"]["human_overrides_model"] = True
    return result


def aggregate(scores, weights):
    """Optional preference aggregate over explicitly rated objectives only.

    Missing/unrated weighted objectives raise instead of being silently imputed.
    The result is a preference calculation on ordinal labels, not art quality.
    """
    if not weights:
        raise ValueError("provide explicit objective weights")
    for key, weight in weights.items():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not isfinite(weight) or weight < 0:
            raise ValueError("weights must be finite nonnegative numbers")
        if weight > 0:
            _score(scores.get(key))
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("at least one objective needs positive weight")
    return sum(float(scores[key]) * weight for key, weight in weights.items() if weight > 0) / total


def weight_sensitivity(vectors, weights, relative_change=0.25):
    """Compare candidate rankings after one-at-a-time ±weight perturbations."""
    if not isfinite(relative_change) or not 0 < relative_change < 1:
        raise ValueError("relative_change must lie between zero and one")
    def comparison(selected_weights):
        values = {candidate: aggregate(scores, selected_weights) for candidate, scores in vectors.items()}
        return {"aggregates": values, "ranking": sorted(values, key=lambda candidate: (-values[candidate], candidate))}
    baseline = comparison(weights)
    trials = []
    for objective in sorted(weights):
        for multiplier in (1 - relative_change, 1 + relative_change):
            changed = dict(weights)
            changed[objective] *= multiplier
            trial = comparison(changed)
            trials.append({"objective": objective, "multiplier": multiplier, "weights": changed, **trial, "ranking_changed": trial["ranking"] != baseline["ranking"]})
    return {"baseline": baseline, "perturbations": trials, "limitations": "Local preference sensitivity only; ordinal aggregation and weight choices are not universal artistic measurements."}


def pareto_front(vectors, maximize=True):
    """Return nondominated candidates, requiring the same complete objective set."""
    if not vectors:
        return []
    objectives = set(next(iter(vectors.values())))
    if not objectives:
        raise ValueError("Pareto comparison requires at least one rated objective")
    for vector in vectors.values():
        if set(vector) != objectives:
            raise ValueError("Pareto vectors must use identical objectives")
        for value in vector.values():
            _score(value)
    direction = 1 if maximize else -1
    def dominates(a, b):
        differences = [direction * (a[key] - b[key]) for key in objectives]
        return all(value >= 0 for value in differences) and any(value > 0 for value in differences)
    return sorted(candidate for candidate, vector in vectors.items() if not any(other != candidate and dominates(other_vector, vector) for other, other_vector in vectors.items()))

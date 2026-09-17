#!/usr/bin/env python3
"""Label-gated AIS predictive validation.

This module deliberately has no fixture fallback. It accepts a CSV exported from
an outcome system, rejects leakage (an outcome must occur after its AIS window),
uses chronological splits, and writes machine-readable plus Markdown results.
It is intentionally dependency-free so the same gate can run in CI, a notebook,
or an incident-review environment without silently changing metric semantics.

Required columns:
  agent_id, window_start, window_end, outcome_time, label, ais

Optional columns enable subgroup and baseline analysis:
  verification_tier, activity_volume, provider, task_domain,
  grounding_available, violation_ratio, recent_incident_count, event_count,
  risk_probability

`label=1` means the pre-declared adverse outcome occurred after the score
window. The script does not decide what that outcome means; the report records
the dataset's declared label definition supplied by the operator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REQUIRED = ("agent_id", "window_start", "window_end", "outcome_time", "label", "ais")
SUBGROUPS = ("verification_tier", "provider", "task_domain", "grounding_available")
COMPONENTS = ("entropy_score", "grounding_score", "sacrifice_score", "compliance_score")
WEIGHTS = (0.30, 0.30, 0.20, 0.20)


def parse_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def finite_float(value: str, field: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in REQUIRED if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")
        rows = []
        for line, raw in enumerate(reader, start=2):
            try:
                window_start = parse_time(raw["window_start"])
                window_end = parse_time(raw["window_end"])
                outcome_time = parse_time(raw["outcome_time"])
                if window_end <= window_start:
                    raise ValueError("window_end must be after window_start")
                if outcome_time <= window_end:
                    raise ValueError("outcome_time must be strictly after window_end (leakage)")
                label = int(raw["label"])
                if label not in (0, 1):
                    raise ValueError("label must be 0 or 1")
                ais = finite_float(raw["ais"], "ais")
                if not 0.0 <= ais <= 1000.0:
                    raise ValueError("ais must be in [0, 1000]")
                row = dict(raw)
                row.update(window_start=window_start, window_end=window_end,
                           outcome_time=outcome_time, label=label, ais=ais)
                rows.append(row)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"line {line}: {exc}") from exc
    if not rows:
        raise ValueError("input contains no rows")
    return sorted(rows, key=lambda row: row["window_end"])


def confusion(rows: Iterable[dict], score_key: str = "ais", threshold: float = 300.0) -> dict:
    values = list(rows)
    predicted = [(float(row[score_key]) <= threshold) for row in values]
    tp = sum(p and row["label"] == 1 for p, row in zip(predicted, values))
    fp = sum(p and row["label"] == 0 for p, row in zip(predicted, values))
    tn = sum(not p and row["label"] == 0 for p, row in zip(predicted, values))
    fn = sum(not p and row["label"] == 1 for p, row in zip(predicted, values))
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None}


def auc(rows: Iterable[dict], value_key: str = "ais", lower_is_risk: bool = True) -> float | None:
    values = [(float(row[value_key]), row["label"]) for row in rows]
    positives = [value for value, label in values if label == 1]
    negatives = [value for value, label in values if label == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if lower_is_risk:
                wins += 1.0 if positive < negative else 0.5 if positive == negative else 0.0
            else:
                wins += 1.0 if positive > negative else 0.5 if positive == negative else 0.0
    return wins / (len(positives) * len(negatives))


def auprc(rows: Iterable[dict], value_key: str = "ais", lower_is_risk: bool = True) -> float | None:
    values = [(float(row[value_key]), row["label"]) for row in rows]
    positives = sum(label for _, label in values)
    if positives == 0 or positives == len(values):
        return None
    values.sort(key=lambda pair: pair[0], reverse=not lower_is_risk)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    for _, label in values:
        if label:
            tp += 1
        else:
            fp += 1
        recall = tp / positives
        precision = tp / (tp + fp)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def recall_at_fpr(rows: list[dict], target_fpr: float = 0.05) -> float | None:
    candidates = sorted({float(row["ais"]) for row in rows})
    best = None
    for threshold in candidates:
        stats = confusion(rows, threshold=threshold)
        if stats["fpr"] is not None and stats["fpr"] <= target_fpr and stats["recall"] is not None:
            best = max(best or 0.0, stats["recall"])
    return best


def bootstrap(rows: list[dict], metric, repetitions: int, seed: int) -> dict:
    if len(rows) < 2 or repetitions <= 0:
        return {"estimate": metric(rows), "lower": None, "upper": None, "repetitions": 0}
    rng = random.Random(seed)
    samples = []
    for _ in range(repetitions):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        value = metric(sample)
        if value is not None and math.isfinite(value):
            samples.append(value)
    if not samples:
        return {"estimate": metric(rows), "lower": None, "upper": None, "repetitions": 0}
    samples.sort()
    return {"estimate": metric(rows),
            "lower": samples[max(0, int(0.025 * len(samples)) - 1)],
            "upper": samples[min(len(samples) - 1, int(0.975 * len(samples)))],
            "repetitions": len(samples)}


def evaluate(rows: list[dict], bootstrap_repetitions: int, seed: int) -> dict:
    labels = [row["label"] for row in rows]
    metrics = {
        "n": len(rows),
        "positive": sum(labels),
        "negative": len(rows) - sum(labels),
        "incident_rate": sum(labels) / len(rows),
        "auroc": bootstrap(rows, auc, bootstrap_repetitions, seed),
        "auprc": bootstrap(rows, auprc, bootstrap_repetitions, seed + 1),
        "recall_at_5pct_fpr": recall_at_fpr(rows),
        "alert_at_ais_300": confusion(rows, threshold=300.0),
        "alert_at_ais_600": confusion(rows, threshold=600.0),
    }
    baselines = {}
    for field, lower_is_risk in (("event_count", False), ("violation_ratio", False),
                                 ("recent_incident_count", False), ("activity_volume", False)):
        if all(row.get(field, "").strip() for row in rows):
            for row in rows:
                row[f"__{field}"] = finite_float(row[field], field)
            baselines[field] = {"auroc": auc(rows, f"__{field}", lower_is_risk=lower_is_risk),
                                "auprc": auprc(rows, f"__{field}", lower_is_risk=lower_is_risk)}
    metrics["baselines"] = baselines
    if all(row.get(field, "").strip() for row in rows for field in COMPONENTS):
        metrics["aggregation_ablations"] = aggregation_ablations(rows)
    else:
        metrics["aggregation_ablations"] = {"status": "not_estimable", "reason": "component score columns were not supplied"}
    if all(row.get("risk_probability", "").strip() for row in rows):
        probabilities = [min(1.0, max(0.0, finite_float(row["risk_probability"], "risk_probability"))) for row in rows]
        metrics["risk_probability_brier"] = sum((p - y) ** 2 for p, y in zip(probabilities, labels)) / len(rows)
        bins = defaultdict(list)
        for p, y in zip(probabilities, labels):
            bins[min(9, int(p * 10))].append(y)
        metrics["risk_probability_reliability"] = [
            {"bin": index, "n": len(values), "mean_predicted": (index + 0.5) / 10,
             "observed_rate": sum(values) / len(values)}
            for index, values in sorted(bins.items())
        ]
    else:
        metrics["calibration"] = {"status": "not_estimable", "reason": "AIS is not a probability; supply risk_probability from a declared calibrated model to evaluate calibration"}
    return metrics


def aggregation_ablations(rows: list[dict]) -> dict:
    """Compare the declared geometric profile with arithmetic and leave-one-axis-out variants."""
    values = [[finite_float(row[field], field) for field in COMPONENTS] for row in rows]

    def aggregate(vector: list[float], weights: list[float], arithmetic: bool) -> float:
        normalized = [min(1000.0, max(0.0, value)) / 1000.0 for value in vector]
        if arithmetic:
            return sum(weight * value for weight, value in zip(weights, normalized)) * 1000.0
        if any(value == 0.0 for value in normalized):
            return 0.0
        return math.exp(sum(weight * math.log(value) for weight, value in zip(weights, normalized))) * 1000.0

    output = {}
    for name, arithmetic, omitted in (("geometric", False, None), ("arithmetic", True, None),
                                      ("without_entropy", False, 0), ("without_grounding", False, 1),
                                      ("without_sacrifice", False, 2), ("without_compliance", False, 3)):
        scores = []
        for vector in values:
            if omitted is None:
                scores.append(aggregate(vector, list(WEIGHTS), arithmetic))
            else:
                kept = [index for index in range(4) if index != omitted]
                scores.append(aggregate([vector[index] for index in kept], [WEIGHTS[index] for index in kept], arithmetic))
        temp = [dict(row, __aggregate_score=score) for row, score in zip(rows, scores)]
        output[name] = {"auroc": auc(temp, "__aggregate_score"), "auprc": auprc(temp, "__aggregate_score")}
    return output


def gaming_diagnostics(rows: list[dict]) -> dict:
    """Report volume sensitivity without treating correlation as causal evidence."""
    values = []
    for row in rows:
        raw_volume = row.get("activity_volume") or row.get("event_count")
        if raw_volume and raw_volume.strip():
            volume = finite_float(raw_volume, "activity_volume/event_count")
            values.append((math.log1p(max(0.0, volume)), row["ais"]))
    if len(values) < 2:
        return {"status": "not_estimable", "reason": "activity_volume or event_count is unavailable"}
    x_bar = statistics.mean(x for x, _ in values)
    y_bar = statistics.mean(y for _, y in values)
    covariance = sum((x - x_bar) * (y - y_bar) for x, y in values)
    denominator = math.sqrt(sum((x - x_bar) ** 2 for x, _ in values) * sum((y - y_bar) ** 2 for _, y in values))
    by_agent = defaultdict(list)
    for row in rows:
        by_agent[row["agent_id"]].append(row["ais"])
    volatility = [statistics.pstdev(scores) for scores in by_agent.values() if len(scores) > 1]
    return {"status": "observed_diagnostics", "n": len(values),
            "pearson_log_volume_vs_ais": covariance / denominator if denominator else None,
            "agent_score_volatility_mean": statistics.mean(volatility) if volatility else None,
            "agent_score_volatility_n": len(volatility),
            "interpretation": "diagnostic association only; not proof of farming or causation"}


def split(rows: list[dict]) -> dict[str, list[dict]]:
    n = len(rows)
    train_end = max(1, int(n * 0.6))
    validation_end = max(train_end + 1, int(n * 0.8)) if n > 2 else n
    return {"train": rows[:train_end], "validation": rows[train_end:validation_end], "test": rows[validation_end:]}


def subgroup_metrics(rows: list[dict]) -> dict:
    output = {}
    for field in SUBGROUPS:
        groups = defaultdict(list)
        for row in rows:
            if row.get(field, "").strip():
                groups[row[field]].append(row)
        output[field] = {
            value: {"n": len(group), "incident_rate": sum(r["label"] for r in group) / len(group),
                    "auroc": auc(group), "auprc": auprc(group)}
            for value, group in sorted(groups.items())
        }
    return output


def render_markdown(result: dict) -> str:
    lines = ["# AIS predictive validation run", "", f"Status: **{result['status']}**", "",
             f"Rows accepted: `{result.get('rows', 0)}`", f"Input: `{result.get('input', '')}`", ""]
    if result["status"] != "evaluated":
        lines += [result.get("reason", "No evaluation was performed."), ""]
        return "\n".join(lines)
    lines += ["## Leakage and cohort controls", "",
              "Rows were required to have `outcome_time > window_end`; splits are chronological (60/20/20).",
              "AIS is evaluated as a ranking signal where lower AIS indicates higher observed risk.", "",
              "## Metrics", "", "```json", json.dumps(result["splits"], indent=2, default=str), "```", "",
              "## Subgroups", "", "```json", json.dumps(result["subgroups"], indent=2, default=str), "```", "",
              "## Baselines, ablations, and gaming diagnostics", "", "```json",
              json.dumps({"baselines": {name: cohort.get("baselines", {}) for name, cohort in result["splits"].items()},
                          "aggregation_ablations": {name: cohort.get("aggregation_ablations", {}) for name, cohort in result["splits"].items()},
                          "gaming_diagnostics": result["gaming_diagnostics"]}, indent=2, default=str), "```", "",
              "Calibration is not inferred from AIS. A calibrated probability column is required before probability claims are made.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="CSV with declared post-window outcome labels")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260916)
    args = parser.parse_args()
    try:
        rows = load_rows(args.input)
        if len(rows) < 30 or len({row["label"] for row in rows}) < 2:
            result = {"status": "insufficient_data", "input": str(args.input), "rows": len(rows),
                      "reason": "At least 30 rows containing both outcome classes are required before predictive metrics are reported."}
        else:
            cohorts = split(rows)
            result = {"status": "evaluated", "input": str(args.input), "rows": len(rows),
                      "splits": {name: evaluate(cohort, args.bootstrap, args.seed + index * 100)
                                 for index, (name, cohort) in enumerate(cohorts.items())},
                      "subgroups": subgroup_metrics(rows),
                      "gaming_diagnostics": gaming_diagnostics(rows),
                      "provenance": {"synthetic": False, "label_source": "operator-supplied CSV",
                                     "leakage_rule": "outcome_time strictly after window_end",
                                     "split": "chronological 60/20/20", "lower_ais_means_higher_risk": True}}
    except (OSError, ValueError) as exc:
        result = {"status": "rejected", "input": str(args.input), "reason": str(exc)}
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(result), encoding="utf-8")
        return 2
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "rows": result.get("rows", 0), "output_json": str(args.output_json), "output_md": str(args.output_md)}))
    return 0 if result["status"] in {"evaluated", "insufficient_data"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

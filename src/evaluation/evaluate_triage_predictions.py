#!/usr/bin/env python
"""Evaluate triage predictions against reference structured labels.

The script is dependency-free and expects JSONL records. By default it looks for:
- reference label in: reference, gold, gold_label_json, majority_label
- prediction label in: prediction, predicted_label, student_prediction, model_output

Both reference and prediction should be JSON objects containing at least risk_tier.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import Counter
from typing import Any


TIERS = [0, 1, 2, 3]


def parse_obj(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def pick_label(record: dict[str, Any], explicit: str | None, defaults: list[str]) -> dict[str, Any] | None:
    fields = [explicit] if explicit else defaults
    for field in fields:
        if not field:
            continue
        value = record.get(field)
        parsed = parse_obj(value)
        if parsed is not None:
            return parsed
    return None


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def quadratic_weighted_kappa(confusion: list[list[int]]) -> float:
    n = sum(sum(row) for row in confusion)
    if n == 0:
        return 0.0
    hist_true = [sum(confusion[i][j] for j in TIERS) for i in TIERS]
    hist_pred = [sum(confusion[i][j] for i in TIERS) for j in TIERS]
    weighted_observed = 0.0
    weighted_expected = 0.0
    max_dist = (len(TIERS) - 1) ** 2
    for i in TIERS:
        for j in TIERS:
            weight = ((i - j) ** 2) / max_dist
            weighted_observed += weight * confusion[i][j]
            weighted_expected += weight * (hist_true[i] * hist_pred[j] / n)
    if weighted_expected == 0:
        return 1.0 if weighted_observed == 0 else 0.0
    return 1.0 - (weighted_observed / weighted_expected)


def evidence_f1(reference: dict[str, Any], prediction: dict[str, Any]) -> tuple[float, float, float]:
    ref = set(str(x).strip() for x in reference.get("evidence_spans", []) if str(x).strip())
    pred = set(str(x).strip() for x in prediction.get("evidence_spans", []) if str(x).strip())
    if not ref and not pred:
        return 1.0, 1.0, 1.0
    if not ref or not pred:
        return 0.0, 0.0, 0.0
    tp = len(ref & pred)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(ref) if ref else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-errors", default="")
    parser.add_argument("--reference-field", default="")
    parser.add_argument("--prediction-field", default="")
    args = parser.parse_args()

    reference_defaults = ["reference", "gold", "gold_label_json", "majority_label"]
    prediction_defaults = ["prediction", "predicted_label", "student_prediction", "model_output"]

    confusion = [[0 for _ in TIERS] for _ in TIERS]
    invalid_reference = 0
    invalid_prediction = 0
    total = 0
    usable = 0
    abs_errors: list[int] = []
    squared_errors: list[int] = []
    evidence_scores: list[tuple[float, float, float]] = []
    error_rows: list[dict[str, Any]] = []
    risk_pair_counts: Counter[str] = Counter()

    with pathlib.Path(args.input).open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            total += 1
            record = json.loads(line)
            reference = pick_label(record, args.reference_field or None, reference_defaults)
            prediction = pick_label(record, args.prediction_field or None, prediction_defaults)
            if reference is None or reference.get("risk_tier") not in TIERS:
                invalid_reference += 1
                continue
            if prediction is None or prediction.get("risk_tier") not in TIERS:
                invalid_prediction += 1
                error_rows.append({"id": record.get("id", ""), "line": line_number, "error": "invalid_prediction"})
                continue
            true = int(reference["risk_tier"])
            pred = int(prediction["risk_tier"])
            confusion[true][pred] += 1
            usable += 1
            abs_errors.append(abs(pred - true))
            squared_errors.append((pred - true) ** 2)
            evidence_scores.append(evidence_f1(reference, prediction))
            risk_pair_counts[f"{true}->{pred}"] += 1
            if true != pred or (true >= 2 and pred <= 1):
                error_rows.append(
                    {
                        "id": record.get("id", ""),
                        "line": line_number,
                        "true_tier": true,
                        "pred_tier": pred,
                        "severity_distance": abs(pred - true),
                        "under_triage": true >= 2 and pred <= 1,
                    }
                )

    per_tier: dict[str, dict[str, float | int]] = {}
    macro_f1_values: list[float] = []
    weighted_f1_sum = 0.0
    support_sum = 0
    for tier in TIERS:
        tp = confusion[tier][tier]
        fp = sum(confusion[i][tier] for i in TIERS if i != tier)
        fn = sum(confusion[tier][j] for j in TIERS if j != tier)
        support = sum(confusion[tier])
        precision, recall, f1 = prf(tp, fp, fn)
        per_tier[str(tier)] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        macro_f1_values.append(f1)
        weighted_f1_sum += f1 * support
        support_sum += support

    correct = sum(confusion[i][i] for i in TIERS)
    under_triage_count = sum(confusion[t][p] for t in [2, 3] for p in [0, 1])
    severe_under_triage_count = sum(confusion[3][p] for p in [0, 1])
    over_triage_count = sum(confusion[t][p] for t in [0, 1] for p in [2, 3])
    high_risk_support = sum(confusion[3])
    high_risk_recall = confusion[3][3] / high_risk_support if high_risk_support else 0.0
    tier2plus_support = sum(sum(confusion[t]) for t in [2, 3])
    tier2plus_recall = (
        sum(confusion[t][p] for t in [2, 3] for p in [2, 3]) / tier2plus_support
        if tier2plus_support
        else 0.0
    )

    ev_p = sum(x[0] for x in evidence_scores) / len(evidence_scores) if evidence_scores else 0.0
    ev_r = sum(x[1] for x in evidence_scores) / len(evidence_scores) if evidence_scores else 0.0
    ev_f1 = sum(x[2] for x in evidence_scores) / len(evidence_scores) if evidence_scores else 0.0

    metrics = {
        "total_records": total,
        "usable_records": usable,
        "invalid_reference": invalid_reference,
        "invalid_prediction": invalid_prediction,
        "accuracy": correct / usable if usable else 0.0,
        "macro_f1": sum(macro_f1_values) / len(macro_f1_values) if macro_f1_values else 0.0,
        "weighted_f1": weighted_f1_sum / support_sum if support_sum else 0.0,
        "per_tier": per_tier,
        "confusion_matrix_rows_true_cols_pred": confusion,
        "quadratic_weighted_kappa": quadratic_weighted_kappa(confusion),
        "tier3_recall": high_risk_recall,
        "tier2plus_recall": tier2plus_recall,
        "under_triage_count": under_triage_count,
        "under_triage_rate_among_tier2plus": under_triage_count / tier2plus_support if tier2plus_support else 0.0,
        "severe_under_triage_count_tier3_to_0_or_1": severe_under_triage_count,
        "over_triage_count_tier0or1_to_2or3": over_triage_count,
        "mean_abs_severity_error": sum(abs_errors) / len(abs_errors) if abs_errors else 0.0,
        "mean_squared_severity_error": sum(squared_errors) / len(squared_errors) if squared_errors else 0.0,
        "evidence_span_exact_set_precision": ev_p,
        "evidence_span_exact_set_recall": ev_r,
        "evidence_span_exact_set_f1": ev_f1,
        "risk_pair_counts": dict(risk_pair_counts),
    }

    output_json = pathlib.Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    if args.output_errors:
        output_errors = pathlib.Path(args.output_errors)
        output_errors.parent.mkdir(parents=True, exist_ok=True)
        with output_errors.open("w", encoding="utf-8", newline="") as f:
            fieldnames = ["id", "line", "error", "true_tier", "pred_tier", "severity_distance", "under_triage"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in error_rows:
                writer.writerow(row)

    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

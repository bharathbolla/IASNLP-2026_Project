#!/usr/bin/env python
"""Apply deterministic quality gates after teacher judging.

Input is the output of judge_aux_labels.py. The script separates records into:
- accepted_auto.jsonl
- human_audit_queue.jsonl
- rejected.jsonl
- quality_gate_summary.json

High-risk or escalation-required examples are routed to human audit by default,
even when the judge score is good.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter
from typing import Any


def exact_spans(label: dict[str, Any], text: str) -> bool:
    spans = label.get("evidence_spans")
    if not isinstance(spans, list) or not spans:
        return False
    return all(isinstance(span, str) and span and span in text for span in spans)


def gate_record(record: dict[str, Any], min_score: int, audit_score: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    label = record.get("majority_label")
    judge = record.get("judge") or {}
    text = record.get("text", "")

    if not isinstance(label, dict):
        return "reject", ["missing_majority_label"]

    if label.get("risk_tier") not in [0, 1, 2, 3]:
        return "reject", ["bad_risk_tier"]

    if not exact_spans(label, text):
        return "reject", ["evidence_spans_not_exact_or_empty"]

    score = judge.get("score")
    if not isinstance(score, int):
        return "audit", ["missing_judge_score"]

    if score < min_score:
        return "reject", [f"judge_score_below_{min_score}"]

    if not judge.get("evidence_exact", False):
        return "reject", ["judge_evidence_not_exact"]

    if not judge.get("label_supported", False):
        return "reject", ["judge_label_not_supported"]

    if judge.get("hallucination_risk") == "high":
        return "reject", ["high_hallucination_risk"]

    risk_tier = label.get("risk_tier")
    majority_meta = record.get("majority_meta") or {}
    agreement = majority_meta.get("agreement", 1.0)

    if risk_tier == 3:
        reasons.append("tier3_requires_human_audit")
    if label.get("escalation_required"):
        reasons.append("escalation_requires_human_audit")
    if judge.get("requires_human_audit"):
        reasons.append("judge_requires_human_audit")
    if score < audit_score:
        reasons.append(f"judge_score_below_{audit_score}")
    if isinstance(agreement, (int, float)) and agreement < 1.0:
        reasons.append("teacher_runs_disagreed")

    disagreement_tier = judge.get("disagreement_risk_tier")
    if disagreement_tier in [0, 1, 2, 3] and abs(disagreement_tier - risk_tier) > 1:
        reasons.append("judge_disagreement_gt_1_tier")

    if reasons:
        return "audit", reasons
    return "accept", ["passed_all_gates"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-score", type=int, default=7)
    parser.add_argument("--audit-score", type=int, default=8)
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "accept": output_dir / "accepted_auto.jsonl",
        "audit": output_dir / "human_audit_queue.jsonl",
        "reject": output_dir / "rejected.jsonl",
    }

    counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()

    handles = {key: path.open("w", encoding="utf-8") for key, path in paths.items()}
    try:
        with pathlib.Path(args.input).open("r", encoding="utf-8") as src:
            for line in src:
                if not line.strip():
                    continue
                record = json.loads(line)
                decision, reasons = gate_record(record, args.min_score, args.audit_score)
                record["quality_gate_decision"] = decision
                record["quality_gate_reasons"] = reasons
                counts[decision] += 1
                for reason in reasons:
                    reason_counts[reason] += 1
                label = record.get("majority_label") or {}
                tier_counts[str(label.get("risk_tier", "missing"))] += 1
                handles[decision].write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        for handle in handles.values():
            handle.close()

    summary = {
        "input": args.input,
        "output_dir": str(output_dir),
        "min_score": args.min_score,
        "audit_score": args.audit_score,
        "counts": dict(counts),
        "reason_counts": dict(reason_counts),
        "tier_counts_before_gate": dict(tier_counts),
        "files": {key: str(path) for key, path in paths.items()},
    }
    (output_dir / "quality_gate_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

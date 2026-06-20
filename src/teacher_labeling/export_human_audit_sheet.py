#!/usr/bin/env python
"""Export a human-audit CSV from quality-gated records."""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
from typing import Any


def join_list(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return "" if value is None else str(value)


def excerpt(text: str, max_chars: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half].rstrip() + " ... [middle omitted] ... " + text[-half:].lstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-text-chars", type=int, default=2000)
    args = parser.parse_args()

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id",
        "split",
        "source",
        "gold_label",
        "text_excerpt",
        "teacher_risk_tier",
        "teacher_confidence",
        "evidence_spans",
        "risk_factors",
        "protective_factors",
        "recommended_next_step",
        "escalation_required",
        "judge_score",
        "judge_reasons",
        "quality_gate_reasons",
        "human_decision",
        "corrected_risk_tier",
        "corrected_evidence_spans",
        "corrected_notes",
    ]

    with pathlib.Path(args.input).open("r", encoding="utf-8") as src, output.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for line in src:
            if not line.strip():
                continue
            record = json.loads(line)
            label = record.get("majority_label") or {}
            judge = record.get("judge") or {}
            source_row = record.get("source_row") or {}
            writer.writerow(
                {
                    "id": record.get("id", ""),
                    "split": record.get("split", ""),
                    "source": source_row.get("source", ""),
                    "gold_label": record.get("gold_label", ""),
                    "text_excerpt": excerpt(record.get("text", ""), args.max_text_chars),
                    "teacher_risk_tier": label.get("risk_tier", ""),
                    "teacher_confidence": label.get("confidence", ""),
                    "evidence_spans": join_list(label.get("evidence_spans")),
                    "risk_factors": join_list(label.get("risk_factors")),
                    "protective_factors": join_list(label.get("protective_factors")),
                    "recommended_next_step": label.get("recommended_next_step", ""),
                    "escalation_required": label.get("escalation_required", ""),
                    "judge_score": judge.get("score", ""),
                    "judge_reasons": join_list(judge.get("reasons")),
                    "quality_gate_reasons": join_list(record.get("quality_gate_reasons")),
                    "human_decision": "",
                    "corrected_risk_tier": "",
                    "corrected_evidence_spans": "",
                    "corrected_notes": "",
                }
            )
    print(f"wrote={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

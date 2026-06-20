#!/usr/bin/env python
"""Build student SFT JSONL from judged auxiliary-label records."""

from __future__ import annotations

import argparse
import json
import pathlib


SYSTEM = (
    "You are a research-only crisis triage assistant. "
    "Return valid JSON with risk tier, evidence spans, grounded factors, "
    "a concise rationale, a plain-language summary, and escalation fields. "
    "Do not diagnose or provide therapy instructions."
)


def build_user(text: str) -> str:
    return "Analyze the following text using the triage rubric and return the structured JSON.\n\n<TEXT>\n" + text + "\n</TEXT>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--include-human-audit", action="store_true")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    skipped = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("accepted_for_training"):
                skipped += 1
                continue
            if record.get("requires_human_audit") and not args.include_human_audit:
                skipped += 1
                continue
            label = record["majority_label"]
            item = {
                "id": record.get("id"),
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": build_user(record["text"])},
                    {"role": "assistant", "content": json.dumps(label, ensure_ascii=False)},
                ],
                "metadata": {
                    "gold_label": record.get("gold_label", ""),
                    "judge_score": (record.get("judge") or {}).get("score"),
                    "teacher_model": record.get("model"),
                },
            }
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
            kept += 1
    print(f"kept={kept} skipped={skipped} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

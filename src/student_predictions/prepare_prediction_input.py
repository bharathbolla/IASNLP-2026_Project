#!/usr/bin/env python
"""Prepare clean/dev/test examples for student-model prediction.

This script is separate from teacher label generation. It creates JSONL records
that the fine-tuned student model will run on.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import pathlib
from typing import Any


def normalize_text(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return "\n\n".join(str(x).strip() for x in parsed if str(x).strip())
        except (SyntaxError, ValueError):
            pass
    return value


def maybe_json(value: str) -> Any:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--text-column", default="text")
    parser.add_argument("--reference-column", default="")
    parser.add_argument("--gold-column", default="")
    parser.add_argument("--split-column", default="")
    parser.add_argument("--allowed-splits", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    allowed_splits = set(s.strip() for s in args.allowed_splits.split(",") if s.strip())
    output = pathlib.Path(args.output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with pathlib.Path(args.input_csv).open("r", encoding="utf-8-sig", newline="") as src, output.open("w", encoding="utf-8") as out:
        reader = csv.DictReader(src)
        for row_index, row in enumerate(reader):
            split = row.get(args.split_column, "") if args.split_column else ""
            if allowed_splits and split not in allowed_splits:
                continue
            text = normalize_text(row.get(args.text_column, ""))
            if not text:
                continue
            record: dict[str, Any] = {
                "id": row.get(args.id_column) or f"row-{row_index}",
                "text": text,
                "split": split,
                "source": args.source or row.get("source", ""),
                "gold_label": row.get(args.gold_column, "") if args.gold_column else "",
            }
            if args.reference_column:
                ref = maybe_json(row.get(args.reference_column, ""))
                if isinstance(ref, dict):
                    record["reference"] = ref
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
            if args.limit and count >= args.limit:
                break

    print(f"wrote={count} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

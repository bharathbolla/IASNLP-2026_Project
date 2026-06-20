#!/usr/bin/env python
"""Prepare eRisk26 Task 2 JSON histories for teacher-label generation.

Input:
- all_combined/*.json user-history files
- shuffled_ground_truth_labels.txt

Output:
- CSV with one row per subject:
  subject_id,gold_label,source,text,...

The generated text is a compact chronological dossier of the target subject's
own submissions/comments. It is meant for teacher-generated auxiliary labels,
not for final gold triage evaluation.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
from typing import Any


def load_labels(path: pathlib.Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                labels[parts[0]] = parts[1]
    return labels


def add_fragment(fragments: list[str], kind: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        fragments.append(f"[{kind}] {text}")


def collect_subject_text(data: list[dict[str, Any]], subject_id: str, include_context: bool) -> tuple[str, int]:
    fragments: list[str] = []
    for item in data:
        submission = item.get("submission") or {}
        is_target_submission = bool(submission.get("target")) or submission.get("user_id") == subject_id
        if is_target_submission:
            add_fragment(fragments, "submission title", submission.get("title"))
            add_fragment(fragments, "submission body", submission.get("body"))

        for comment in item.get("comments") or []:
            is_target_comment = bool(comment.get("target")) or comment.get("user_id") == subject_id
            if is_target_comment or include_context:
                prefix = "target comment" if is_target_comment else "context comment"
                add_fragment(fragments, prefix, comment.get("body"))

        for comment in submission.get("comments") or []:
            is_target_comment = bool(comment.get("target")) or comment.get("user_id") == subject_id
            if is_target_comment or include_context:
                prefix = "target comment" if is_target_comment else "context comment"
                add_fragment(fragments, prefix, comment.get("body"))

    return "\n\n".join(fragments), len(fragments)


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    half = max_chars // 2
    head = text[:half].rstrip()
    tail = text[-half:].lstrip()
    marker = "\n\n[... middle omitted for length; beginning and end retained ...]\n\n"
    return head + marker + tail, True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-dir", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--include-context-comments", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    json_dir = pathlib.Path(args.json_dir)
    labels = load_labels(pathlib.Path(args.labels))
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "subject_id",
        "gold_label",
        "source",
        "text",
        "source_file",
        "writings_included",
        "chars_before_truncation",
        "truncated",
    ]

    files = sorted(json_dir.glob("*.json"))
    if args.limit:
        files = files[: args.limit]

    written = 0
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for path in files:
            subject_id = path.stem
            if subject_id not in labels:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            text, writings = collect_subject_text(data, subject_id, args.include_context_comments)
            original_len = len(text)
            text, truncated = truncate_text(text, args.max_chars)
            if not text.strip():
                continue
            writer.writerow(
                {
                    "subject_id": subject_id,
                    "gold_label": labels[subject_id],
                    "source": "eRisk26-task2-contextualized-depression",
                    "text": text,
                    "source_file": path.name,
                    "writings_included": writings,
                    "chars_before_truncation": original_len,
                    "truncated": str(truncated),
                }
            )
            written += 1
    print(f"wrote={written} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

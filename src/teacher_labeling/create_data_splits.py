#!/usr/bin/env python
"""Create train/dev/test CSV splits before teacher label generation.

This script keeps all rows from the same user/group in the same split and
stratifies by the gold label where possible. It is intentionally dependency-free
so it can run before the ML environment is set up.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random
from collections import defaultdict
from typing import Any


def read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path: pathlib.Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ratio_to_counts(n: int, train_ratio: float, dev_ratio: float) -> tuple[int, int, int]:
    train_n = round(n * train_ratio)
    dev_n = round(n * dev_ratio)
    if train_n + dev_n > n:
        dev_n = max(0, n - train_n)
    test_n = n - train_n - dev_n
    return train_n, dev_n, test_n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--id-column", default="User")
    parser.add_argument("--group-column", default="User")
    parser.add_argument("--label-column", default="Label")
    parser.add_argument("--text-column", default="Post")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--dev-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split-column", default="split")
    parser.add_argument("--manifest", default="split_manifest.json")
    args = parser.parse_args()

    rows = read_rows(pathlib.Path(args.input))
    if not rows:
        raise SystemExit("No rows found in input CSV")

    fieldnames = list(rows[0].keys())
    if args.split_column not in fieldnames:
        fieldnames.append(args.split_column)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        group_id = row.get(args.group_column) or row.get(args.id_column) or f"row-{len(grouped)}"
        grouped[group_id].append(row)

    label_to_groups: dict[str, list[str]] = defaultdict(list)
    for group_id, group_rows in grouped.items():
        labels = [r.get(args.label_column, "") for r in group_rows]
        label = max(set(labels), key=labels.count) if labels else ""
        label_to_groups[label].append(group_id)

    rng = random.Random(args.seed)
    split_for_group: dict[str, str] = {}
    manifest: dict[str, Any] = {
        "input": args.input,
        "seed": args.seed,
        "train_ratio": args.train_ratio,
        "dev_ratio": args.dev_ratio,
        "test_ratio": round(1.0 - args.train_ratio - args.dev_ratio, 6),
        "group_column": args.group_column,
        "label_column": args.label_column,
        "counts": {"train": 0, "dev": 0, "test": 0},
        "label_counts": {},
        "note": "The test split is a locked evaluation candidate. For gold results, manually review/relabel it with the project rubric and evidence spans before use.",
    }

    for label, group_ids in sorted(label_to_groups.items()):
        ids = list(group_ids)
        rng.shuffle(ids)
        train_n, dev_n, _test_n = ratio_to_counts(len(ids), args.train_ratio, args.dev_ratio)
        for group_id in ids[:train_n]:
            split_for_group[group_id] = "train"
        for group_id in ids[train_n : train_n + dev_n]:
            split_for_group[group_id] = "dev"
        for group_id in ids[train_n + dev_n :]:
            split_for_group[group_id] = "test"

    split_rows: dict[str, list[dict[str, str]]] = {"train": [], "dev": [], "test": []}
    for group_id, group_rows in grouped.items():
        split = split_for_group[group_id]
        for row in group_rows:
            row = dict(row)
            row[args.split_column] = split
            split_rows[split].append(row)

    output_dir = pathlib.Path(args.output_dir)
    for split, split_data in split_rows.items():
        write_rows(output_dir / f"{split}.csv", split_data, fieldnames)
        manifest["counts"][split] = len(split_data)

    for split, split_data in split_rows.items():
        counts: dict[str, int] = defaultdict(int)
        for row in split_data:
            counts[row.get(args.label_column, "")] += 1
        manifest["label_counts"][split] = dict(sorted(counts.items()))

    all_path = output_dir / "all_with_splits.csv"
    all_rows = split_rows["train"] + split_rows["dev"] + split_rows["test"]
    write_rows(all_path, all_rows, fieldnames)

    manifest_path = output_dir / args.manifest
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

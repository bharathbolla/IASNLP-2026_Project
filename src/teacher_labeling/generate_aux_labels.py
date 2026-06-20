#!/usr/bin/env python
"""Generate structured auxiliary labels with an OpenAI-compatible chat API.

The script supports OpenRouter and local vLLM/SGLang servers by changing
--base-url and --api-key-env. It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_post(value: str) -> str:
    """Handle ordinary text and C-SSRS stringified list-of-posts cells."""
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return "\n\n".join(str(item).strip() for item in parsed if str(item).strip())
        except (SyntaxError, ValueError):
            pass
    return value


def iter_csv_rows(
    path: pathlib.Path,
    id_column: str,
    text_column: str,
    gold_column: str | None,
    split_column: str | None,
    allowed_splits: set[str] | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            split = row.get(split_column, "") if split_column else ""
            if allowed_splits is not None and split not in allowed_splits:
                continue
            text = normalize_post(row.get(text_column, ""))
            if not text:
                continue
            item = {
                "id": row.get(id_column) or f"row-{len(rows)}",
                "text": text,
                "gold_label": row.get(gold_column, "") if gold_column else "",
                "split": split,
                "source_row": row,
            }
            rows.append(item)
            if limit and len(rows) >= limit:
                break
    return rows


def extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


def exact_span_in_text(span: str, text: str) -> bool:
    return bool(span) and span in text


def validate_aux_label(label: dict[str, Any], text: str) -> list[str]:
    errors: list[str] = []
    required = [
        "risk_tier",
        "confidence",
        "evidence_spans",
        "risk_factors",
        "protective_factors",
        "cssrs_axes",
        "clinical_rationale",
        "plain_language_summary",
        "recommended_next_step",
        "escalation_required",
        "uncertainty_flags",
    ]
    for key in required:
        if key not in label:
            errors.append(f"missing:{key}")
    if errors:
        return errors
    if label["risk_tier"] not in [0, 1, 2, 3]:
        errors.append("bad:risk_tier")
    if not isinstance(label["confidence"], (int, float)) or not 0 <= label["confidence"] <= 1:
        errors.append("bad:confidence")
    if not isinstance(label["evidence_spans"], list) or not label["evidence_spans"]:
        errors.append("bad:evidence_spans_empty")
    else:
        for span in label["evidence_spans"]:
            if not isinstance(span, str) or not exact_span_in_text(span, text):
                errors.append(f"bad:evidence_not_exact:{span[:60]}")
    if not isinstance(label["escalation_required"], bool):
        errors.append("bad:escalation_required")
    if label["recommended_next_step"] not in [
        "Supportive",
        "Professional support",
        "Urgent support",
        "Emergency escalation",
        "Human review",
    ]:
        errors.append("bad:recommended_next_step")
    return errors


def build_user_prompt(item: dict[str, Any]) -> str:
    gold = item.get("gold_label") or "unknown"
    return (
        "Create a structured crisis-triage rationale JSON for the input below.\n\n"
        f"Original dataset label, if any: {gold}\n"
        "Treat the original label as context, not as guaranteed truth.\n\n"
        "Input text:\n"
        "<TEXT>\n"
        f"{item['text']}\n"
        "</TEXT>"
    )


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    schema: dict[str, Any] | None,
    max_retries: int,
    timeout: int,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": schema,
        }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            sleep_s = min(30, 2**attempt)
            time.sleep(sleep_s)
    raise RuntimeError(f"chat completion failed after retries: {last_error}")


def choose_majority(runs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    valid = [r for r in runs if not r.get("validation_errors") and isinstance(r.get("label"), dict)]
    if not valid:
        return None, {"valid_runs": 0, "majority_tier": None, "agreement": 0.0}
    tiers = [r["label"]["risk_tier"] for r in valid]
    majority_tier = max(set(tiers), key=tiers.count)
    candidates = [r for r in valid if r["label"]["risk_tier"] == majority_tier]
    candidates.sort(key=lambda r: r["label"].get("confidence", 0), reverse=True)
    agreement = tiers.count(majority_tier) / len(tiers)
    meta = {
        "valid_runs": len(valid),
        "majority_tier": majority_tier,
        "agreement": agreement,
        "tier_votes": {str(t): tiers.count(t) for t in sorted(set(tiers))},
    }
    return candidates[0]["label"], meta


def already_done_ids(output_path: pathlib.Path) -> set[str]:
    if not output_path.exists():
        return set()
    done: set[str] = set()
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                done.add(json.loads(line)["id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--text-column", default="text")
    parser.add_argument("--gold-column", default="")
    parser.add_argument("--split-column", default="")
    parser.add_argument(
        "--allowed-splits",
        default="",
        help="Comma-separated split names allowed for generation, e.g. train,dev. Use with --split-column.",
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--schema", default=str(ROOT / "schema.json"))
    parser.add_argument("--system-prompt", default=str(ROOT / "prompts" / "primary_teacher_system.md"))
    parser.add_argument("--no-schema-response", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key env var: {args.api_key_env}", file=sys.stderr)
        return 2

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = None if args.no_schema_response else load_json(pathlib.Path(args.schema))
    system_prompt = read_text(pathlib.Path(args.system_prompt))

    done = already_done_ids(output_path) if args.resume else set()
    rows = iter_csv_rows(
        input_path,
        args.id_column,
        args.text_column,
        args.gold_column or None,
        args.split_column or None,
        set(s.strip() for s in args.allowed_splits.split(",") if s.strip()) if args.allowed_splits else None,
        args.limit or None,
    )

    with output_path.open("a" if args.resume else "w", encoding="utf-8") as out:
        for index, item in enumerate(rows, start=1):
            if item["id"] in done:
                continue
            runs: list[dict[str, Any]] = []
            for run_index in range(args.runs):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": build_user_prompt(item)},
                ]
                run_record: dict[str, Any] = {"run_index": run_index}
                try:
                    content = chat_completion(
                        base_url=args.base_url,
                        api_key=api_key,
                        model=args.model,
                        messages=messages,
                        temperature=args.temperature,
                        schema=schema,
                        max_retries=args.max_retries,
                        timeout=args.timeout,
                    )
                    label = extract_json(content)
                    errors = validate_aux_label(label, item["text"])
                    run_record.update(
                        {
                            "raw_content": content,
                            "label": label,
                            "validation_errors": errors,
                        }
                    )
                except Exception as exc:  # keep pipeline resumable
                    run_record.update({"error": str(exc), "validation_errors": ["exception"]})
                runs.append(run_record)

            majority, majority_meta = choose_majority(runs)
            record = {
                "id": item["id"],
                "gold_label": item.get("gold_label", ""),
                "split": item.get("split", ""),
                "text": item["text"],
                "model": args.model,
                "base_url": args.base_url,
                "runs": runs,
                "majority_label": majority,
                "majority_meta": majority_meta,
                "requires_human_audit": bool(
                    majority
                    and (
                        majority.get("risk_tier") == 3
                        or majority.get("escalation_required")
                        or majority_meta.get("agreement", 0) < 1.0
                    )
                ),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{index}/{len(rows)}] wrote {item['id']} tier={majority_meta.get('majority_tier')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

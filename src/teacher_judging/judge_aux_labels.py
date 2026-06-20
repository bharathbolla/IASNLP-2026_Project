#!/usr/bin/env python
"""Judge generated auxiliary labels with a second OpenAI-compatible model."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent


JUDGE_SCHEMA = {
    "name": "triage_auxiliary_judgment",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_valid",
            "evidence_exact",
            "label_supported",
            "rationale_supported",
            "hallucination_risk",
            "disagreement_risk_tier",
            "score",
            "reasons",
            "requires_human_audit",
        ],
        "properties": {
            "schema_valid": {"type": "boolean"},
            "evidence_exact": {"type": "boolean"},
            "label_supported": {"type": "boolean"},
            "rationale_supported": {"type": "boolean"},
            "hallucination_risk": {"type": "string", "enum": ["low", "medium", "high"]},
            "disagreement_risk_tier": {"type": "integer", "enum": [0, 1, 2, 3]},
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "requires_human_audit": {"type": "boolean"},
        },
    },
}


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


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


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: int,
    max_retries: int,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": JUDGE_SCHEMA,
        },
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
            time.sleep(min(30, 2**attempt))
    raise RuntimeError(f"judge completion failed after retries: {last_error}")


def build_judge_prompt(record: dict[str, Any]) -> str:
    return (
        "Evaluate this candidate auxiliary label.\n\n"
        "Input text:\n"
        "<TEXT>\n"
        f"{record['text']}\n"
        "</TEXT>\n\n"
        "Candidate JSON:\n"
        "<JSON>\n"
        f"{json.dumps(record.get('majority_label'), ensure_ascii=False, indent=2)}\n"
        "</JSON>"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--system-prompt", default=str(ROOT / "prompts" / "judge_system.md"))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key env var: {args.api_key_env}", file=sys.stderr)
        return 2

    system_prompt = read_text(pathlib.Path(args.system_prompt))
    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for index, line in enumerate(src, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not record.get("majority_label"):
                record["judge"] = {"score": 0, "requires_human_audit": True, "reasons": ["no majority label"]}
            else:
                try:
                    content = chat_completion(
                        base_url=args.base_url,
                        api_key=api_key,
                        model=args.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": build_judge_prompt(record)},
                        ],
                        temperature=args.temperature,
                        timeout=args.timeout,
                        max_retries=args.max_retries,
                    )
                    record["judge"] = extract_json(content)
                except Exception as exc:
                    record["judge"] = {
                        "score": 0,
                        "requires_human_audit": True,
                        "reasons": [f"judge_exception:{exc}"],
                    }
            label = record.get("majority_label") or {}
            judge = record.get("judge") or {}
            record["accepted_for_training"] = bool(
                label
                and judge.get("score", 0) >= 7
                and judge.get("evidence_exact", False)
                and judge.get("label_supported", False)
                and judge.get("hallucination_risk") in ["low", "medium"]
            )
            record["requires_human_audit"] = bool(
                record.get("requires_human_audit")
                or judge.get("requires_human_audit")
                or judge.get("score", 0) < 8
            )
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{index}] judged {record.get('id')} score={judge.get('score')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

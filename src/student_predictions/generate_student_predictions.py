#!/usr/bin/env python
"""Run a fine-tuned student model through an OpenAI-compatible chat endpoint.

This script is intentionally separate from teacher label generation. It should
be used only after a student model has been trained.
"""

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


ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "teacher_labeling" / "schema.json"


SYSTEM_PROMPT = (
    "You are a research-only crisis triage assistant. "
    "Return only valid JSON matching the triage schema. "
    "Use exact evidence spans copied from the input text. "
    "Do not diagnose, prescribe medication, or provide therapy instructions."
)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(content[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("model output did not contain a JSON object")


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None,
    temperature: float,
    timeout: int,
    max_retries: int,
) -> str:
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
    url = base_url.rstrip("/") + "/chat/completions"
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
    raise RuntimeError(f"student prediction failed after retries: {last_error}")


def build_messages(text: str) -> list[dict[str, str]]:
    user = "Analyze the following text and return the structured triage JSON.\n\n<TEXT>\n" + text + "\n</TEXT>"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--api-key-env", default="LOCAL_LLM_API_KEY")
    parser.add_argument("--schema", default=str(SCHEMA_PATH))
    parser.add_argument("--no-schema-response", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key env var: {args.api_key_env}", file=sys.stderr)
        return 2

    schema = None if args.no_schema_response else load_json(pathlib.Path(args.schema))
    output = pathlib.Path(args.output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with pathlib.Path(args.input_jsonl).open("r", encoding="utf-8") as src, output.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            record = json.loads(line)
            if args.limit and count >= args.limit:
                break
            result = dict(record)
            try:
                content = chat_completion(
                    base_url=args.base_url,
                    api_key=api_key,
                    model=args.model,
                    messages=build_messages(record["text"]),
                    schema=schema,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    max_retries=args.max_retries,
                )
                result["raw_student_output"] = content
                result["prediction"] = extract_json(content)
                result["prediction_parse_error"] = ""
            except Exception as exc:
                result["raw_student_output"] = ""
                result["prediction"] = None
                result["prediction_parse_error"] = str(exc)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            count += 1
            print(f"[{count}] wrote prediction for {record.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

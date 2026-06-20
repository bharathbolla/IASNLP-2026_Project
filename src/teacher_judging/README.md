# Teacher Label Judging Pipeline

This pipeline is part of label generation. It is not the student-model evaluation pipeline.

Use it after `src/teacher_labeling/generate_aux_labels.py` creates raw teacher outputs.

## Step 1. Judge Teacher Candidates

```powershell
python src/teacher_judging/judge_aux_labels.py `
  --input data/synthetic_aux/raw_primary_runs.jsonl `
  --output data/synthetic_aux/judged_candidates.jsonl `
  --model "anthropic/claude-sonnet-4" `
  --base-url "https://openrouter.ai/api/v1" `
  --api-key-env OPENROUTER_API_KEY
```

## Step 2. Apply Quality Gates

```powershell
python src/teacher_judging/apply_quality_gates.py `
  --input data/synthetic_aux/judged_candidates.jsonl `
  --output-dir data/synthetic_aux/gated `
  --min-score 7 `
  --audit-score 8
```

## Step 3. Export Human Audit Sheet

```powershell
python src/teacher_judging/export_human_audit_sheet.py `
  --input data/synthetic_aux/gated/human_audit_queue.jsonl `
  --output data/synthetic_aux/gated/human_audit_sheet.csv
```

## Outputs

```text
data/synthetic_aux/gated/
  accepted_auto.jsonl
  human_audit_queue.jsonl
  human_audit_sheet.csv
  rejected.jsonl
  quality_gate_summary.json
```

## Boundary

This folder judges teacher-generated auxiliary labels.

Student prediction generation and final student-model metrics live in:

```text
src/student_predictions/
src/evaluation/
```

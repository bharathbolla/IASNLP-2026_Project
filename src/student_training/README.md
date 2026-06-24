# Student Model Training (LoRA SFT)

This pipeline is the missing link between teacher-label generation and student
prediction. It is separate from:

- teacher auxiliary-label generation (`src/teacher_labeling/`)
- teacher-label judging (`src/teacher_judging/`)
- student prediction generation (`src/student_predictions/`)
- student metric evaluation (`src/evaluation/`)

## Purpose

Fine-tune a small "student" model (Qwen2.5-1.5B-Instruct, LoRA) on the
chat-format training data produced by
`src/teacher_labeling/build_student_sft_jsonl.py`, so it can later be served
behind an OpenAI-compatible endpoint and consumed unchanged by
`src/student_predictions/generate_student_predictions.py`.

## Where this sits in the pipeline

```
src/teacher_labeling/build_student_sft_jsonl.py
        |
        v
data/synthetic_aux/student_sft_train.jsonl
        |
        v
notebooks/train_student_qwen_lora.ipynb   <-- this stage
        |
        v
LoRA adapter  --serve with vLLM-->  OpenAI-compatible /v1/chat/completions
        |
        v
src/student_predictions/generate_student_predictions.py
        |
        v
src/evaluation/evaluate_triage_predictions.py
```

## Why no separate CoT-rationalization stage

`student_sft_train.jsonl` already contains finished `messages` triples (system
prompt, user post, assistant target). The assistant target is the full
`triage_auxiliary_label` JSON object from `src/teacher_labeling/schema.json`,
which already includes a `clinical_rationale` field written by the teacher
during labeling/judging. There is no need to re-derive a chain-of-thought —
the notebook trains directly on the already-judged, already-gated teacher
output.

## Run it

1. Run the full teacher pipeline (`docs/teacher_label_generation_and_judging_pipeline.md`)
   through `build_student_sft_jsonl.py` to produce `student_sft_train.jsonl`.
2. Open `notebooks/train_student_qwen_lora.ipynb` on Kaggle or Colab (GPU, e.g. T4).
3. Attach `student_sft_train.jsonl` as an input dataset.
4. Run all cells. The notebook trains, sanity-checks the adapter's JSON output
   against the required schema keys, and prints serving instructions.
5. Serve the adapter (vLLM `--enable-lora`) and point
   `src/student_predictions/generate_student_predictions.py --base-url` at it.

## Boundary summary

This pipeline produces:

```text
a LoRA adapter for the student model
```

It does not produce:

```text
teacher labels
judged labels
student prediction JSONL
metric reports
```

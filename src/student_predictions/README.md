# Student Model Prediction Pipeline

This pipeline is separate from teacher label generation.

Use it only after a small/student model has been trained.

## Purpose

Input:

- dev/test examples
- optional human-reviewed reference labels

Output:

- student model predictions

## Step 1. Prepare Prediction Inputs

```powershell
python src/student_predictions/prepare_prediction_input.py `
  --input-csv data/processed/cssrs_splits/test.csv `
  --output-jsonl data/student_predictions/test_inputs.jsonl `
  --id-column User `
  --text-column Post `
  --gold-column Label `
  --split-column split `
  --allowed-splits test `
  --source cssrs
```

If you have human-reviewed structured gold labels in a CSV column, pass it with:

```powershell
--reference-column reference_json
```

## Step 2. Run The Fine-Tuned Student Model

Example with a local vLLM server:

```powershell
$env:LOCAL_LLM_API_KEY="dummy"

python src/student_predictions/generate_student_predictions.py `
  --input-jsonl data/student_predictions/test_inputs.jsonl `
  --output-jsonl data/student_predictions/test_predictions.jsonl `
  --model "local-student-triage-model" `
  --base-url "http://localhost:8000/v1" `
  --api-key-env LOCAL_LLM_API_KEY
```

## Step 3. Evaluate Elsewhere

After predictions are created, evaluate them with the separate metric code in:

```text
src/evaluation/
```

## Important Boundary

Do not use teacher-generated labels as final test truth.

Use:

- dev set for tuning
- locked human-reviewed test set for final claims
- noisy/hard-negative test views for robustness claims

This folder does not generate auxiliary labels and does not compute final metrics. It only prepares inputs and runs the trained student model.

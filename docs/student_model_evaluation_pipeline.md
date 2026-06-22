# Student Model Evaluation Pipeline

## Purpose

This pipeline computes metrics for student-model predictions.

It is separate from:

- teacher auxiliary-label generation
- teacher-label judging
- student prediction generation

Use it after `src/student_predictions/` has produced prediction JSONL.

## Boundary Figure

![Evaluation metrics](../figures/evaluation_metrics_map.svg)

## Inputs

The evaluation script expects JSONL records with:

- a reference structured label
- a student prediction structured label

Preferred evaluation inputs:

- dev predictions for model selection and threshold tuning
- locked human-reviewed test predictions for final claims
- noisy or hard-negative prediction views for robustness claims

Do not use teacher-generated labels as the only final test truth.

## Stage 1. Evaluate Student Predictions

Run:

```powershell
python src/evaluation/evaluate_triage_predictions.py `
  --input data/student_predictions/test_predictions.jsonl `
  --output-json data/student_predictions/metrics.json `
  --output-errors data/student_predictions/error_log.csv `
  --reference-field reference `
  --prediction-field prediction
```

## Metrics

The script computes:

- accuracy
- macro-F1
- weighted-F1
- per-tier precision, recall, and F1
- confusion matrix
- quadratic weighted kappa
- tier-3 recall
- tier-2-or-higher recall
- under-triage count and rate
- severe under-triage count
- over-triage count
- mean severity error
- evidence-span exact-set precision, recall, and F1

## Dev vs Test Usage

Use dev to:

- choose the best checkpoint
- tune thresholds
- compare model variants
- debug evidence-span failures

Use test only for final reporting.

The locked test set should be human-reviewed.

## Robustness Views

For noise and hard-negative experiments, run the same evaluation script on:

```text
clean test predictions
noisy test-view predictions
hard-negative test predictions
```

Keep the reference labels fixed for noisy copies of the same test examples.

## Boundary Summary

This pipeline produces:

```text
metrics JSON
error log CSV
```

It does not produce:

```text
teacher labels
teacher judge scores
student prediction JSONL
training labels
```

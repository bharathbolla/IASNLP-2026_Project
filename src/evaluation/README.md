# Student Model Evaluation Metrics

This folder contains metric scripts for scoring student-model predictions against held-out reference labels.

It does not generate auxiliary labels, judge teacher outputs, or run student inference. Those steps are kept separate:

- `src/teacher_labeling/`: generate candidate auxiliary labels and build training files.
- `src/teacher_judging/`: judge and quality-filter teacher-generated labels.
- `src/student_predictions/`: run the trained student model on dev/test inputs.

## Main Script

`evaluate_triage_predictions.py`

Input: JSONL records with a reference JSON and prediction JSON.

Default reference fields checked:

- `reference`
- `gold`
- `gold_label_json`
- `majority_label`

Default prediction fields checked:

- `prediction`
- `predicted_label`
- `student_prediction`
- `model_output`

## Metrics

The script computes:

- accuracy
- macro-F1
- weighted-F1
- per-tier precision/recall/F1
- confusion matrix
- quadratic weighted kappa
- tier-3 recall
- tier-2-or-higher recall
- under-triage count/rate
- severe under-triage count
- over-triage count
- mean severity error
- evidence-span exact-set precision/recall/F1

## Example

```powershell
python src/evaluation/evaluate_triage_predictions.py `
  --input data/eval/student_predictions.jsonl `
  --output-json data/eval/metrics.json `
  --output-errors data/eval/error_log.csv `
  --reference-field reference `
  --prediction-field prediction
```

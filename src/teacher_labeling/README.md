# Teacher Labeling Pipeline

This folder contains dependency-light scripts for generating structured auxiliary labels.

## Files

- `schema.json`: JSON schema for the generated auxiliary label.
- `prompts/primary_teacher_system.md`: primary generation prompt.
- `generate_aux_labels.py`: calls a primary teacher model 1-3 times per row and stores majority labels.
- `build_student_sft_jsonl.py`: converts accepted labels into chat-format SFT JSONL.
- `prepare_erisk26_task2.py` / `.ps1`: converts eRisk26 Task 2 subject histories into CSV records.

Judging generated teacher labels is handled separately in:

```text
src/teacher_judging/
```

Student model prediction and evaluation is handled separately in:

```text
src/student_predictions/
src/evaluation/
```

## API Compatibility

The scripts call `/chat/completions` on an OpenAI-compatible endpoint.

Works with:

- OpenRouter: `https://openrouter.ai/api/v1`
- local vLLM: `http://localhost:8000/v1`
- local SGLang: `http://localhost:30000/v1`

## Minimal Smoke Test

```powershell
$env:OPENROUTER_API_KEY="sk-or-..."

python src/teacher_labeling/create_data_splits.py `
  --input datasets/cssrs/500_anonymized_Reddit_users_posts_labels.csv `
  --output-dir data/processed/cssrs_splits `
  --id-column User `
  --group-column User `
  --label-column Label `
  --text-column Post `
  --seed 42

python src/teacher_labeling/generate_aux_labels.py `
  --input data/processed/cssrs_splits/all_with_splits.csv `
  --output data/synthetic_aux/raw_primary_runs.jsonl `
  --id-column User `
  --text-column Post `
  --gold-column Label `
  --split-column split `
  --allowed-splits train,dev `
  --model "google/gemini-2.5-pro" `
  --base-url "https://openrouter.ai/api/v1" `
  --api-key-env OPENROUTER_API_KEY `
  --runs 3 `
  --limit 20
```

Run a 20-row smoke test first. Do not launch the full dataset until the invalid JSON rate, exact-evidence rate, and tier distribution look reasonable.

## eRisk26 Task 2

Prepare one row per subject:

```powershell
powershell -ExecutionPolicy Bypass -File src/teacher_labeling/prepare_erisk26_task2.ps1 `
  -JsonDir datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/all_combined `
  -Labels datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/shuffled_ground_truth_labels.txt `
  -Output data/processed/erisk26_task2/erisk26_task2_subjects.csv `
  -MaxChars 12000
```

Then split and generate labels:

```powershell
python src/teacher_labeling/create_data_splits.py `
  --input data/processed/erisk26_task2/erisk26_task2_subjects.csv `
  --output-dir data/processed/erisk26_task2/splits `
  --id-column subject_id `
  --group-column subject_id `
  --label-column gold_label `
  --text-column text `
  --seed 42

python src/teacher_labeling/generate_aux_labels.py `
  --input data/processed/erisk26_task2/splits/all_with_splits.csv `
  --output data/synthetic_aux/erisk26_task2_raw_primary_runs.jsonl `
  --id-column subject_id `
  --text-column text `
  --gold-column gold_label `
  --split-column split `
  --allowed-splits train,dev `
  --model "google/gemini-2.5-pro" `
  --base-url "https://openrouter.ai/api/v1" `
  --api-key-env OPENROUTER_API_KEY `
  --runs 3
```

Use eRisk26 Task 2 as auxiliary depression-context data. Its labels are not suicide/crisis triage labels.

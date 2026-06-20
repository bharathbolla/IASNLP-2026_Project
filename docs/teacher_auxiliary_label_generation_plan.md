# Teacher-Generated Auxiliary Label Plan

## 1. Goal

Create a high-quality synthetic structured-rationale dataset for crisis-risk triage.

Each input post should become one JSON training record:

```json
{
  "risk_tier": 0,
  "confidence": 0.0,
  "evidence_spans": [],
  "risk_factors": [],
  "protective_factors": [],
  "cssrs_axes": {
    "ideation": "",
    "behavior": "",
    "intensity": "",
    "lethality": "",
    "precipitants": ""
  },
  "clinical_rationale": "",
  "plain_language_summary": "",
  "recommended_next_step": "",
  "escalation_required": false,
  "uncertainty_flags": []
}
```

This is the source for auxiliary training. The student model is not trained only to predict the risk tier; it is also trained to cite evidence, identify risk/protective factors, produce a short rationale, write a plain-language summary, and flag escalation.

Important language choice: call this **structured rationale data** or **structured CoT-style supervision**, not long hidden chain-of-thought. The output should be short, auditable, and grounded in exact text spans.

## 2. Recommended Teacher Model Setup

Use a 3-role teacher system:

![Teacher review system](../figures/easy_teacher_review_system.svg)

| Role | Purpose | Recommended model | Backup |
|---|---|---|---|
| Primary teacher | Generate structured labels | MedGemma 27B text IT locally, Gemini/GPT/Claude via approved API, or another strong medical/general model | MedGemma 4B or a strong 70B local general model |
| Disagreement teacher | Independently re-label risk tier and safety flags | Different model family from primary teacher | Same model with a different prompt only if no alternative |
| Rubric judge | Score evidence support, hallucination risk, schema quality | Strong structured-output model | Human-only judge for small data |

Minimum viable sprint:

- Primary teacher: 1 model, 3 stochastic runs per post.
- Judge: 1 separate model or same model with a judge prompt.
- Human audit: all tier-3/high-risk cases, all disagreements, all low judge scores.

Preferred:

- Primary teacher: MedGemma 27B local or a strong API model.
- Disagreement teacher: different provider/model.
- Judge: strongest JSON-capable model available.

Do not use teacher labels as final ground truth. They are noisy training supervision. Final reported results should use a human-labeled locked test set.

## 3. Hugging Face, OpenRouter, and MedGemma

### Hugging Face

Use Hugging Face when you want local control:

- Download/open-weight models.
- Run them using `transformers`, `vLLM`, or `SGLang`.
- Best for sensitive mental-health text if the data policy does not allow API calls.

For this project, local Hugging Face serving should expose an OpenAI-compatible endpoint through vLLM or SGLang. Then the provided scripts can call it exactly like an API.

### OpenRouter

Use OpenRouter only if your data policy allows sending de-identified text to an external service.

Pros:

- One API for many teacher models.
- Supports structured-output requests for compatible models.
- Easy model swapping.

Cons:

- Sensitive text leaves your machine.
- Provider logging and data handling must be checked before use.
- Model availability and pricing can change.

### MedGemma 27B

MedGemma 27B is a good candidate for the primary teacher because the task is medical/clinical text comprehension. Google describes MedGemma as open models for medical text and image comprehension, with 27B generally best for text reasoning use cases, while still requiring validation for the specific use case.

Practical caveats:

- The Hugging Face model requires accepting Google Health AI terms before download.
- MedGemma is not clinical-grade by default.
- Use it as a label generator and extractor, not as a clinical authority.
- Validate heavily with human audit and a locked test set.

## 4. Data Policy Gate

Before generation, choose one path:

| Path | Condition | Teacher location |
|---|---|---|
| A. External API allowed | License/ethics allow de-identified text to leave your machine | OpenRouter or direct vendor API |
| B. Local only | External API is forbidden or unclear | Hugging Face model served by vLLM/SGLang |
| C. Synthetic-only fallback | Real posts cannot be used | Teacher generates synthetic cases from rubric seeds |

For C-SSRS Reddit, confirm that your use of API inference is allowed under your institution's policy. Even public/anonymized mental-health text can be sensitive.

## 5. Pipeline Overview

![Auxiliary label pipeline](../figures/easy_aux_label_pipeline.svg)

1. Prepare input CSV/JSONL.
2. De-identify and quality-filter text.
3. Create user-level train/dev/test splits.
4. Lock the test split before prompt tuning or teacher generation.
5. Generate teacher labels only for train/dev examples.
6. Generate 3 primary teacher outputs per allowed post.
7. Validate schema and exact evidence spans.
8. Majority-vote risk tier.
9. Send accepted candidate to disagreement teacher.
10. Send candidate to rubric judge.
11. Route high-risk, disagreement, and low-score examples to human audit.
12. Save accepted examples as `accepted_aux_labels.jsonl`.
13. Build student training JSONL from accepted examples.
14. Evaluate only on the locked human-reviewed test set.

## 5.1 Split Policy

The test set must be kept separate before teacher generation begins.

Recommended split:

| Split | Percentage | Use |
|---|---:|---|
| Train | 70% | Teacher-generated auxiliary labels and student training |
| Dev | 15% | Prompt debugging, threshold selection, early stopping |
| Test | 15% | Locked human-labeled evaluation only |

Rules:

- Split by user/group, not by individual post, to avoid leakage.
- Stratify by original label when possible.
- Do not send locked test examples through the teacher-generation pipeline for training labels.
- If the public dataset labels are coarse, manually relabel the test split with the project 4-tier rubric and evidence spans before final evaluation.
- Teacher labels may be used on train/dev, but final claims must come from the locked human-reviewed test split.

## 6. Input Format

Recommended CSV columns:

```csv
id,user_id,source,text,gold_label,split
```

For the downloaded C-SSRS file:

```csv
User,Post,Label
```

The pipeline code supports choosing the ID, text, and label columns. It also attempts to parse the C-SSRS `Post` column, which contains a stringified Python list of posts.

For eRisk26 Task 2, the raw data is not CSV. It is one JSON file per subject plus a label file. Convert it first:

```powershell
powershell -ExecutionPolicy Bypass -File src/teacher_labeling/prepare_erisk26_task2.ps1 `
  -JsonDir datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/all_combined `
  -Labels datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/shuffled_ground_truth_labels.txt `
  -Output data/processed/erisk26_task2/erisk26_task2_subjects.csv `
  -MaxChars 12000
```

This creates one row per subject:

```csv
subject_id,gold_label,source,text,source_file,writings_included,chars_before_truncation,truncated
```

Use `gold_label` only as depression/control context:

- `0` = control
- `1` = depression-risk positive

Do not treat eRisk26 Task 2 labels as suicide/crisis triage labels.

## 7. Label Mapping

For C-SSRS labels:

| C-SSRS label | Suggested risk_tier | Meaning |
|---|---:|---|
| Supportive | 0 | no acute crisis in the authored text; may be support given to others |
| Ideation | 1 or 2 | depends on passive vs active ideation |
| Behavior | 2 | self-harm/suicidal behavior without clear imminent attempt |
| Attempt | 3 | attempt or high/imminent risk |

Do not force this mapping blindly. The teacher should use the actual text and the 4-tier rubric. The original label can be passed as context, not final truth.

For eRisk26 Task 2:

| eRisk label | Meaning | Use in this project |
|---|---|---|
| 0 | control | background/domain contrast |
| 1 | depression-risk positive | depression-context auxiliary signal |

These labels are useful for mental-health/domain adaptation and teacher-generated depression evidence, but they are not enough for acute suicide triage.

## 8. Teacher Generation Prompt Rules

Primary teacher must:

- Return only valid JSON matching schema.
- Copy `evidence_spans` exactly from input text.
- Use observed evidence only.
- Avoid diagnosis, medication advice, therapy instructions, or moral judgment.
- Keep `clinical_rationale` to 2-4 sentences.
- Keep `plain_language_summary` understandable for a non-clinician.
- Use uncertainty flags instead of guessing.

## 9. Quality Gates

![Quality gate decision tree](../figures/easy_quality_gate_decision.svg)

Reject or regenerate if:

- JSON is malformed.
- Required field is missing.
- `risk_tier` is outside 0-3.
- `confidence` is outside 0-1.
- `evidence_spans` is empty.
- Any evidence span is not an exact substring of the input text.
- The output invents facts, diagnoses, medication instructions, or therapy instructions.
- Rationale contradicts risk tier.

Route to human audit if:

- risk tier is 3.
- escalation is required.
- primary runs disagree.
- disagreement teacher differs by more than 1 tier.
- judge score is below 7/10.
- text includes sarcasm, cultural idiom, metaphor, or unclear intent.

## 10. GPU Recommendation

### If using OpenRouter/API

No local GPU is needed for teacher generation. A CPU machine is enough.

Use local GPU later for student fine-tuning:

- 24 GB GPU: Qwen/Phi 1.5B-4B QLoRA.
- 48 GB GPU: comfortable 3B-7B QLoRA.
- 80 GB GPU: optional, useful for faster ablations.

### If serving MedGemma 27B locally

Recommended:

- A100 80 GB, H100 80 GB, or similar for low-friction FP16/BF16 serving.
- 48 GB may work with quantization depending on serving stack, context length, and batch size.
- 24 GB is not recommended for MedGemma 27B teacher serving.

For a 10-day sprint, the cleanest setup is:

- Teacher generation: external API if policy allows, or MedGemma 27B on A100 80 GB.
- Student training: 48 GB L40S/A6000/A40 or A100 if already available.

## 11. Generation Scale

For each post:

- 3 primary generations.
- 1 disagreement check for accepted majority output.
- 1 judge call for accepted majority output.

For 3,000 posts:

- Primary calls: 9,000
- Disagreement calls: up to 3,000
- Judge calls: up to 3,000
- Human audit: all tier-3 + disagreements + random 10% sample

To save cost/time:

- Run 200 posts first.
- Measure pass rate, tier distribution, invalid JSON rate, and hallucination rate.
- Freeze prompt v2.
- Then run the full batch.

## 12. Output Files

Recommended output layout:

```text
data/
  processed/
    input_posts.csv
  synthetic_aux/
    raw_primary_runs.jsonl
    majority_candidates.jsonl
    judged_candidates.jsonl
    accepted_aux_labels.jsonl
    rejected_aux_labels.jsonl
    human_audit_queue.jsonl
    student_sft_train.jsonl
```

## 13. Student Training Use

For plain SFT, train the model to emit the full accepted JSON.

For auxiliary loss, split the JSON into components:

- label loss: `risk_tier`
- span loss: `evidence_spans`
- factor loss: `risk_factors`, `protective_factors`
- rationale loss: `clinical_rationale`
- summary loss: `plain_language_summary`
- calibration loss: `confidence`
- escalation loss: `escalation_required`

Mask losses for fields that are missing or human-rejected.

## 14. Commands

OpenRouter example:

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
  --limit 200
```

eRisk26 Task 2 preparation and generation example:

```powershell
powershell -ExecutionPolicy Bypass -File src/teacher_labeling/prepare_erisk26_task2.ps1 `
  -JsonDir datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/all_combined `
  -Labels datasets/eRisk26-datasets/task2-contextualized-depression/eRisk26-task2-trainingdata/final-eriskt2-dataset-with-ground-truth/shuffled_ground_truth_labels.txt `
  -Output data/processed/erisk26_task2/erisk26_task2_subjects.csv `
  -MaxChars 12000

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

Recommended eRisk26 Task 2 use:

- Generate structured auxiliary labels for train/dev only.
- Use the generated records as auxiliary/background data.
- Keep final crisis-triage claims tied to C-SSRS/CLPsych/manual gold data.

Local MedGemma via vLLM/SGLang example:

```powershell
$env:LOCAL_LLM_API_KEY="dummy"
python src/teacher_labeling/generate_aux_labels.py `
  --input data/processed/cssrs_splits/all_with_splits.csv `
  --output data/synthetic_aux/raw_primary_runs.jsonl `
  --id-column User `
  --text-column Post `
  --gold-column Label `
  --split-column split `
  --allowed-splits train,dev `
  --model "google/medgemma-27b-text-it" `
  --base-url "http://localhost:8000/v1" `
  --api-key-env LOCAL_LLM_API_KEY `
  --runs 3 `
  --limit 200
```

Judge candidates:

```powershell
python src/teacher_labeling/judge_aux_labels.py `
  --input data/synthetic_aux/raw_primary_runs.jsonl `
  --output data/synthetic_aux/judged_candidates.jsonl `
  --model "anthropic/claude-sonnet-4" `
  --base-url "https://openrouter.ai/api/v1" `
  --api-key-env OPENROUTER_API_KEY
```

Build student SFT data:

```powershell
python src/teacher_labeling/build_student_sft_jsonl.py `
  --input data/synthetic_aux/judged_candidates.jsonl `
  --output data/synthetic_aux/student_sft_train.jsonl
```

## 15. Sources Checked

- Google MedGemma documentation: https://developers.google.com/health-ai-developer-foundations/medgemma
- MedGemma 27B Hugging Face model card: https://huggingface.co/google/medgemma-27b-text-it
- OpenRouter structured outputs: https://openrouter.ai/docs/features/structured-outputs
- OpenRouter quickstart: https://openrouter.ai/docs/quickstart

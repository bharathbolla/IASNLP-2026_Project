# Auxiliary Label Generation Plan

## Plain-English Summary

The project needs training data where each mental-health post has more than a risk label. The student model should learn to predict the crisis risk tier and also explain that decision using exact evidence from the post.

These extra fields are called **auxiliary labels**:

- risk tier
- confidence
- evidence spans copied from the post
- risk factors
- protective factors
- short clinical rationale
- plain-language summary
- recommended next step
- escalation flag
- uncertainty flags

Because most public datasets only provide coarse labels, we use a strong teacher model to generate the missing fields. Then we check the teacher output carefully before using it for student training.

The pipeline can now use both:

- C-SSRS Reddit: better aligned with suicide-risk labels
- eRisk26 Task 2: useful depression-context/user-history data, but not a direct suicide-triage gold set

## The Core Idea

Do not train the student model only like this:

```text
Post -> risk_tier
```

Train it like this:

```text
Post -> risk_tier + evidence + factors + rationale + summary + next_step
```

This makes the student model more auditable. If it predicts high risk, it must also show which words in the post support that decision.

## Figure 1. End-to-End Pipeline

![Auxiliary label pipeline](../figures/easy_aux_label_pipeline.svg)

## Recommended Teacher Setup

Use a small panel of teachers, not just one model.

| Role | What it does | Recommended choice |
|---|---|---|
| Primary teacher | Generates the full auxiliary JSON | MedGemma 27B locally, or a strong API model if allowed |
| Disagreement teacher | Independently checks the risk tier | A different model family from the primary teacher |
| Rubric judge | Scores whether the output is grounded and safe | Strong structured-output model |
| Human auditor | Reviews risky or uncertain cases | Lead + annotator |

Minimum setup:

- One primary teacher model
- Three generations per post
- One judge model
- Human review for high-risk, disagreement, and low-score cases

Preferred setup:

- Primary teacher: MedGemma 27B or strongest approved API model
- Disagreement teacher: different model family
- Judge: strongest JSON-capable model available
- Human audit: all high/imminent-risk examples

## Train, Dev, and Golden Test Split

Before using any teacher model, split the dataset.

Recommended split:

| Split | Use |
|---|---|
| Train | Generate auxiliary labels and train the student model |
| Dev | Tune prompts, thresholds, and early stopping |
| Golden test | Keep locked for final evaluation only |

The golden test set should not be used to generate training labels. It should be manually reviewed or relabeled with the project rubric, including risk tier and evidence spans.

This matters because teacher labels are noisy. If the same teacher-generated labels are used for both training and final testing, the evaluation will look better than it really is.

For eRisk26 Task 2, keep in mind that its label is binary depression/control. It is useful for auxiliary training and background mental-health language, but final triage claims should still come from a suicide/crisis-specific locked test set.

## Using eRisk26 Task 2

eRisk26 Task 2 stores one JSON history per subject. Before teacher generation, convert those files into one CSV row per subject.

Recommended use:

- Treat each subject history as depression-context data.
- Pass the original `gold_label` as context only.
- Ask the teacher to generate structured risk/evidence labels from the actual text.
- Do not treat depression-positive as automatically suicidal or high risk.

Best role in this project:

- auxiliary/background data for mental-health language
- extra examples for teacher-generated evidence and factor extraction
- not the final gold evaluation set

## Figure 2. Teacher Review System

![Teacher review system](../figures/easy_teacher_review_system.svg)

## What the Teacher Produces

Example input:

```text
I have a bottle of pills and I am going to take them tonight. My sister is in the next room but I do not want to tell her.
```

Example accepted output:

```json
{
  "risk_tier": 3,
  "confidence": 0.94,
  "evidence_spans": [
    "I have a bottle of pills",
    "I am going to take them tonight"
  ],
  "risk_factors": [
    "access to means",
    "time-bound intent"
  ],
  "protective_factors": [
    "My sister is in the next room"
  ],
  "clinical_rationale": "The post describes access to pills and a time-bound intent to take them tonight. A nearby sister is a protective factor, but the immediate danger remains high.",
  "plain_language_summary": "This message suggests urgent danger because the person has pills and says they may take them tonight.",
  "recommended_next_step": "Emergency escalation",
  "escalation_required": true,
  "uncertainty_flags": []
}
```

## Quality Gates

Teacher outputs are not accepted automatically.

Reject or regenerate if:

- JSON is invalid
- evidence spans are missing
- evidence spans are not exact text from the post
- the model invents facts
- the model gives diagnosis, therapy instructions, or medication advice
- the rationale does not match the risk tier

Send to human review if:

- risk tier is 3
- escalation is required
- teacher models disagree
- judge score is below 8/10
- sarcasm, metaphor, cultural idiom, or unclear intent is present

## Figure 3. Accept, Regenerate, or Human Review

![Quality gate decision tree](../figures/easy_quality_gate_decision.svg)

## GPU and Platform Choice

### If API Use Is Allowed

Use OpenRouter or a direct model API for teacher generation. You do not need a GPU for generating auxiliary labels.

Then use a GPU only for student model training:

- Colab T4: useful for debugging and very small 1B-1.5B experiments
- RunPod 24 GB: okay for Qwen2.5-1.5B or small Phi/Qwen models
- RunPod 48 GB: recommended for the real sprint
- A100 80 GB: best if available, especially for ablations

### If Data Must Stay Local

Use Hugging Face plus a local serving stack such as vLLM or SGLang.

For MedGemma 27B teacher generation:

- Colab T4 is not enough
- 24 GB GPU is not recommended
- 48 GB may work only with quantization and low batch size
- A100 80 GB is the clean choice

For the student model:

- 24 GB is enough for 1.5B-3B QLoRA
- 48 GB is the best practical choice
- 80 GB is comfortable but not mandatory

## Recommended Practical Path

If your data policy allows external API use:

1. Generate teacher labels with OpenRouter or a direct approved API.
2. Use structured JSON schema output.
3. Judge and filter outputs.
4. Train the student model on RunPod 48 GB.

If your data policy does not allow external API use:

1. Serve MedGemma 27B locally on A100 80 GB.
2. Generate labels locally.
3. Use a local or separately approved judge.
4. Train the student model on the same A100 or a 48 GB GPU.

## Output Files To Create

```text
data/synthetic_aux/
  raw_primary_runs.jsonl
  majority_candidates.jsonl
  judged_candidates.jsonl
  accepted_aux_labels.jsonl
  rejected_aux_labels.jsonl
  human_audit_queue.jsonl
  student_sft_train.jsonl
```

## Final Training Use

The accepted JSON becomes student training data.

The student can be trained in two ways:

1. **Simple SFT:** train it to emit the full JSON.
2. **Auxiliary loss training:** compute separate losses for risk tier, evidence spans, factors, rationale, summary, confidence, and escalation.

For a 10-day sprint, start with simple SFT first. Add explicit auxiliary losses only after the full JSON-output baseline works.

## Key Safety Principle

Teacher-generated auxiliary labels are **training supervision**, not clinical truth.

Final claims must be based on:

- a human-labeled locked test set
- high-risk miss review
- unsupported-claim analysis
- evidence-span grounding checks
- clear limitations that the system is research-only

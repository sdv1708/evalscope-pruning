# AA-LCR (Reference Pruned)


## Overview

Native AA-LCR historical-reference selection. The defended default retains the full
100-question reference population: no smaller tested candidate passed every fidelity gate.

## Task Description

- **Task Type**: Long-context question answering
- **Input**: Original multi-document context and question
- **Output**: Free-form answer evaluated against the reference
- **Domain**: Long-context reasoning

## Key Features

- length_difficulty_stratified crosses token-length thirds with historical pass counts
- metadata_stratified crosses length with document-URL-count thirds
- prune_ratio is a retained fraction in (0, 1], rounded up; default 1.0
- Question fingerprints and validated benchmark metadata bind the frozen population
- Target reference grades are excluded before selection; repeats follow selection
- Hugging Face source is pinned to historical v1.0, not the revised v1.1 answers/judge

## Evaluation Notes

- Inherits AA-LCR prompting and contract-based binary LLM judging; requires a judge
- Reports raw subset accuracy and a separate population-weighted mean
- Judge randomness is unmeasured: sampling intervals do not include judge error
- Full retention removes sampling error only; repeats generate new answers, not repeat judging
- Missing/invalid judge verdicts exclude the sample and fail the population estimate closed
- Smaller ratios are research settings, without a new-model or GO/NO GO guarantee
- Requires reference_path and dataset_hub=huggingface for pinned remote data;
  text_dir may name a local extracted corpus
- Context uses data_source_filenames order and fails on missing/empty files
- Generic Usage templates below require reference_path and removal of limit;
  control retained size through prune_ratio. Credential-free synthetic smoke:

```bash
python examples/aa_lcr_pruned/smoke.py
```

See AA_LCR_PRUNED.md for live configuration, historical replay and judge limitations.


## Properties

| Property | Value |
|----------|-------|
| **Benchmark Name** | `aa_lcr_pruned` |
| **Dataset ID** | [evalscope/AA-LCR](https://modelscope.cn/datasets/evalscope/AA-LCR/summary) |
| **Paper** | N/A |
| **Tags** | `Knowledge`, `LongContext`, `Reasoning` |
| **Metrics** | `accuracy` |
| **Default Shots** | 0-shot |
| **Evaluation Split** | `test` |


## Data Statistics

*Statistics not available.*

## Sample Example

*Sample example not available.*

## Prompt Template

**Prompt Template:**
```text

BEGIN INPUT DOCUMENTS

{documents_text}

END INPUT DOCUMENTS

Answer the following question using the input documents provided above.

START QUESTION

{question}

END QUESTION

```

## Extra Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_dir` | `str | null` | `None` | Local directory containing extracted AA-LCR text files; if null will auto-download & extract. |
| `pruning_strategy` | `str` | `length_difficulty_stratified` | AA-LCR historical strata; baselines rejected. |
| `prune_ratio` | `float` | `1.0` | Retained fraction; 1.0 is the defended fallback. |
| `reference_path` | `str` | `` | Local frozen AA-LCR panel JSON. |
| `excluded_reference_models` | `list[str]` | `[]` | Additional holdout model names. |

## Usage

### Using CLI

```bash
evalscope eval \
    --model YOUR_MODEL \
    --api-url OPENAI_API_COMPAT_URL \
    --api-key EMPTY_TOKEN \
    --datasets aa_lcr_pruned \
    --judge '{"strategy":"llm","models":[{"model_id":"YOUR_JUDGE_MODEL"}]}' \
    --limit 10  # Remove this line for formal evaluation
```

### Using Python

```python
from evalscope import run_task
from evalscope.config import TaskConfig

task_cfg = TaskConfig(
    model='YOUR_MODEL',
    api_url='OPENAI_API_COMPAT_URL',
    api_key='EMPTY_TOKEN',
    datasets=['aa_lcr_pruned'],
    judge={'strategy': 'llm', 'models': [{'model_id': 'YOUR_JUDGE_MODEL'}]},
    dataset_args={
        'aa_lcr_pruned': {
            # extra_params: {}  # uses default extra parameters
        }
    },
    limit=10,  # Remove this line for formal evaluation
)

run_task(task_cfg=task_cfg)
```

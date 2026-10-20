# Pruning Smoke (Synthetic)


## Overview

A six-question synthetic benchmark that exercises native subset selection inside
EvalScope. This is an integration smoke path, not LiveCodeBench or AA-LCR.

## Task Description

- **Task Type**: Synthetic question answering
- **Input**: A short question with stable identity and a metadata stratum
- **Output**: A short text answer
- **Domain**: Framework integration testing

## Key Features

- Bundled local fixture: two questions in each of easy, medium and hard groups
- Deterministic hash priorities select one question per group by default
- Selection uses metadata and identity, never target-model scores

## Evaluation Notes

- Exact-match scoring and ordinary subset-mean aggregation
- Runs through the normal evaluator, including mock_llm, with no API key
- Selection precedes limit and repeats; a debugging limit may remove coverage
- Fixed per-stratum allocation is a smoke policy, not a validated pruning strategy
- Scores are synthetic subset scores, not estimates of a full benchmark


## Properties

| Property | Value |
|----------|-------|
| **Benchmark Name** | `pruning_smoke` |
| **Dataset ID** | `pruning_smoke` |
| **Paper** | N/A |
| **Tags** | `Custom`, `QA` |
| **Metrics** | `exact_match` |
| **Default Shots** | 0-shot |
| **Evaluation Split** | `test` |


## Data Statistics

| Metric | Value |
|--------|-------|
| Total Samples | 3 |
| Prompt Length (Mean) | 24.67 chars |
| Prompt Length (Min/Max) | 14 / 42 chars |

## Sample Example

**Subset**: `smoke`

```json
{
  "input": [
    {
      "id": "52356e3e",
      "content": "What is 1 + 1?"
    }
  ],
  "target": "2",
  "id": 0,
  "group_id": 0,
  "metadata": {
    "record_id": "easy-1",
    "stratum": "easy"
  }
}
```

## Prompt Template

**Prompt Template:**
```text
{question}
```

## Extra Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `keep_per_stratum` | `int` | `1` | Positive number retained per synthetic metadata group; not a production policy. |

## Usage

### Using CLI

```bash
evalscope eval \
    --model YOUR_MODEL \
    --api-url OPENAI_API_COMPAT_URL \
    --api-key EMPTY_TOKEN \
    --datasets pruning_smoke \
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
    datasets=['pruning_smoke'],
    dataset_args={
        'pruning_smoke': {
            # extra_params: {}  # uses default extra parameters
        }
    },
    limit=10,  # Remove this line for formal evaluation
)

run_task(task_cfg=task_cfg)
```

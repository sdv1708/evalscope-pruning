# LiveCodeBench (Reference Pruned)


## Overview

Historical reference-stratified LiveCodeBench selection inside the native evaluation
pipeline. Full retention is the default: the reference analysis did not validate a
smaller operating point under its conservative decision policy.

## Task Description

- **Task Type**: Competitive programming / code generation
- **Input**: Original LiveCodeBench problem and starter code
- **Output**: Python solution using the standard LiveCodeBench format
- **Domain**: Coding capability screening

## Key Features

- Configurable difficulty_stratified or response_stratified historical selection
- prune_ratio is a retained fraction in (0, 1], rounded up
- Frozen question fingerprints bind analysis indices to source problems
- Evaluated model grades are excluded; selection precedes inference and repeats

## Evaluation Notes

- Inherits the LiveCodeBench prompt, date filter, extraction and code execution grader
- Requires a local reference_path panel; benchmark downloads use standard loaders
- Standard subset pass@k remains available alongside population-weighted accuracy
- Use sandbox execution for generated code as in the full benchmark
- Smaller ratios are experimental; no new GO/NO GO guarantee is certified


## Properties

| Property | Value |
|----------|-------|
| **Benchmark Name** | `live_code_bench_pruned` |
| **Dataset ID** | [evalscope/livecodebench_code_generation_lite_parquet](https://modelscope.cn/datasets/evalscope/livecodebench_code_generation_lite_parquet/summary) |
| **Paper** | N/A |
| **Tags** | `Coding` |
| **Metrics** | `accuracy` |
| **Default Shots** | 0-shot |
| **Evaluation Split** | `test` |
| **Aggregation** | `mean_and_pass_at_k` |


## Data Statistics

*Statistics not available.*

## Sample Example

*Sample example not available.*

## Prompt Template

**System Prompt:**
```text
You are an expert Python programmer. You will be given a question (problem specification) and will generate a correct Python program that matches the specification and passes all tests. You will NOT return anything except for the program.
```

**Prompt Template:**
```text
### Question:
{question_content}

{format_prompt} ### Answer: (use the provided format with backticks)


```

## Extra Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_date` | `str | null` | `None` | Filter problems starting from this date (YYYY-MM-DD). Null keeps all. |
| `end_date` | `str | null` | `None` | Filter problems up to this date (YYYY-MM-DD). Null keeps all. |
| `debug` | `bool` | `False` | Enable verbose debug logging and bypass certain safety checks. |
| `pruning_strategy` | `str` | `difficulty_stratified` | Historical stratification policy; comparison baselines are rejected. |
| `prune_ratio` | `float` | `1.0` | Fraction retained in (0, 1]; 1.0 is the defended fallback. |
| `reference_path` | `str` | `` | Local frozen reference panel JSON, schema version 1. |
| `excluded_reference_models` | `list[str]` | `[]` | Additional reference model names to exclude (for pair holdouts). |

## Sandbox Configuration

This benchmark requires a sandbox environment for code execution.

```json
{
  "image": "python:3.11-slim",
  "tools_config": {
    "shell_executor": {},
    "python_executor": {}
  }
}
```

## Usage

### Using CLI

```bash
evalscope eval \
    --model YOUR_MODEL \
    --api-url OPENAI_API_COMPAT_URL \
    --api-key EMPTY_TOKEN \
    --datasets live_code_bench_pruned \
    --sandbox '{"enabled": true}' \
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
    datasets=['live_code_bench_pruned'],
    sandbox={'enabled': True},
    dataset_args={
        'live_code_bench_pruned': {
            # extra_params: {}  # uses default extra parameters
        }
    },
    limit=10,  # Remove this line for formal evaluation
)

run_task(task_cfg=task_cfg)
```

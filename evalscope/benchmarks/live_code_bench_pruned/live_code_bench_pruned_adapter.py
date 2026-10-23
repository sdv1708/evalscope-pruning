"""Prune before inference while inheriting LiveCodeBench prompting and grading."""

import hashlib
import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from evalscope.api.dataset import DataLoader, Dataset, DatasetDict, MemoryDataset, Sample
from evalscope.api.dataset.loader import repeat_samples
from evalscope.api.metric import AggScore, SampleScore
from evalscope.api.metric.semantics import MetricSelector
from evalscope.api.registry import BENCHMARK_REGISTRY, register_benchmark
from evalscope.benchmarks._reference_pruning.adapter import ReferencePruningAdapter
from evalscope.benchmarks._reference_pruning.selection import (
    PruningConfig,
    ReferencePanel,
    SelectedTask,
    load_reference_panel,
    question_fingerprint,
    select_tasks,
)
from evalscope.benchmarks.live_code_bench.live_code_bench_adapter import LiveCodeBenchAdapter

DESCRIPTION = """
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
- **Configuration required:** the generic Usage templates generated below are not
  runnable unchanged for this benchmark. Supply `extra_params.reference_path` and
  remove `--limit` / `limit=10`; use `prune_ratio` to control the retained size.
  For a runnable offline example, from the repository root run:

```python
from evalscope import run_task
run_task('examples/live_code_bench_pruned/task.json')
```

See `LIVE_CODE_BENCH_PRUNED.md` for the full reference-panel schema and live command.
"""

_BASE = BENCHMARK_REGISTRY['live_code_bench']
_EXTRA = {
    'pruning_strategy': {
        'type': 'str',
        'description': 'Historical stratification policy; comparison baselines are rejected.',
        'value': 'difficulty_stratified',
    },
    'prune_ratio': {
        'type': 'float',
        'description': 'Fraction retained in (0, 1]; 1.0 is the defended fallback.',
        'value': 1.0,
    },
    'reference_path': {
        'type': 'str',
        'description': 'Local frozen reference panel JSON, schema version 1.',
        'value': '',
    },
    'excluded_reference_models': {
        'type': 'list[str]',
        'description': 'Additional reference model names to exclude (for pair holdouts).',
        'value': [],
    },
}


@register_benchmark(
    replace(
        _BASE,
        name='live_code_bench_pruned',
        pretty_name='LiveCodeBench (Reference Pruned)',
        subset_list=['release_v5'],
        description=DESCRIPTION,
        evaluation_version='v1.0',
        hf_dataset_revision='e70df9620dd54c12afac5e2881355de6f9ece2e9',
        extra_params={**_BASE.extra_params, **_EXTRA},
        primary_metric=MetricSelector(name='accuracy', aggregation='weighted_mean', dimensions={'scope': 'population'}),
    )
)
class LiveCodeBenchPrunedAdapter(ReferencePruningAdapter, LiveCodeBenchAdapter):
    """Keep standard benchmark semantics and validate pruning at configuration time."""

    pruning_config: PruningConfig

    aggregate_empty_scores = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pruning_config = PruningConfig.model_validate({key: (self.extra_params or {})[key] for key in _EXTRA})
        self.save_metadata = True
        if self._task_config is not None and (self.seed is None or isinstance(self.seed, bool)):
            raise ValueError('Pruning requires an integer seed for reproducible selection.')
        if self._task_config is not None and self.limit is not None:
            raise ValueError(
                'live_code_bench_pruned does not support limit; use prune_ratio to preserve population weights.'
            )

    def load_from_disk(self, use_local_loader: bool = True) -> Tuple[DatasetDict, Optional[DatasetDict]]:
        """Support ordinary local JSONL/CSV/parquet mirrors through the native loader."""
        return super().load_from_disk(use_local_loader=use_local_loader)

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        """Preserve original conversion and add a content-based question identity."""
        fingerprint = question_fingerprint(record['question_content'])
        sample = super().record_to_sample(record)
        sample.metadata['question_sha256'] = fingerprint
        return sample

    def selection_design(self) -> Tuple[ReferencePanel[Any], List[SelectedTask], List[str]]:
        """Use LiveCodeBench historical difficulty or response-pattern strata."""
        panel = load_reference_panel(self.pruning_config.reference_path)
        excluded = self.excluded_models()
        assert isinstance(self.seed, int)
        selected = select_tasks(panel, self.pruning_config, seed=self.seed, excluded_models=excluded)
        references = sorted(set(panel.tasks[0].scores) - excluded - set(self.pruning_config.excluded_reference_models))
        return panel, selected, references

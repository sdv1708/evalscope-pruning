"""A small, native pruning smoke path; not a production benchmark estimator."""

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field

from evalscope.api.benchmark import BenchmarkMeta, DefaultDataAdapter
from evalscope.api.dataset import DataLoader, Dataset, DatasetDict, MemoryDataset, Sample
from evalscope.api.dataset.dataset import resolve_dataset_limit
from evalscope.api.dataset.loader import repeat_samples
from evalscope.api.registry import register_benchmark
from evalscope.constants import Tags


class SmokeRecord(BaseModel):
    """Synthetic question identity and metadata, independent of model outcomes."""

    model_config = ConfigDict(strict=True)

    record_id: str = Field(min_length=1)
    stratum: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class SmokeSelectionConfig(BaseModel):
    """Typed, validated allocation for the synthetic selection policy."""

    keep_per_stratum: int = Field(default=1, gt=0, strict=True)


@register_benchmark(
    BenchmarkMeta(
        name='pruning_smoke',
        pretty_name='Pruning Smoke (Synthetic)',
        dataset_id='pruning_smoke',
        subset_list=['smoke'],
        eval_split='test',
        metric_list=['exact_match'],
        aggregation='mean',
        prompt_template='{question}',
        tags=[Tags.QA, Tags.CUSTOM],
        evaluation_version='v1.0',
        extra_params={
            'keep_per_stratum': {
                'type': 'int',
                'description': 'Positive number retained per synthetic metadata group; not a production policy.',
                'value': 1,
            },
        },
        description="""
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
""",
    )
)
class PruningSmokeAdapter(DefaultDataAdapter):
    """Select metadata groups at the benchmark's population-aware loading seam."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.selection_config = SmokeSelectionConfig.model_validate(self.extra_params or {})

    @property
    def dataset_id(self) -> str:
        """Resolve the bundled fixture without publishing a machine-specific path."""
        if self.benchmark_meta.dataset_id == 'pruning_smoke':
            return str(Path(__file__).parent / 'data')
        return super().dataset_id

    def load_from_disk(self, use_local_loader: bool = True) -> Tuple[DatasetDict, Optional[DatasetDict]]:
        """Read bundled or user-supplied local data through the standard loader."""
        return super().load_from_disk(use_local_loader=use_local_loader)

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        """Preserve source identity separately from framework execution IDs."""
        item = SmokeRecord.model_validate(record)
        return Sample(
            input=item.question,
            target=item.answer,
            metadata={'record_id': item.record_id, 'stratum': item.stratum},
        )

    def load_subset(self, subset: str, data_loader: Type[DataLoader]) -> Dataset:
        """Select from the complete eligible pool before debug limits and repeats."""
        if self._task_config is None:
            raise ValueError('Loading pruning_smoke requires a TaskConfig.')
        population_config = self._task_config.model_copy(update={'limit': None, 'repeats': 1})
        with (
            self._temporary_attribute('_task_config', population_config),
            self._temporary_attribute('shuffle', False),
        ):
            population = super().load_subset(subset, data_loader)

        groups: Dict[str, List[Sample]] = defaultdict(list)
        seen = set()
        for sample in population:
            record_id = sample.metadata['record_id']
            if record_id in seen:
                raise ValueError(f'Duplicate record_id {record_id!r} in subset {subset!r}.')
            seen.add(record_id)
            groups[sample.metadata['stratum']].append(sample)
        selected: List[Sample] = []
        for stratum in sorted(groups):
            candidates = sorted(
                groups[stratum],
                key=lambda sample: hashlib.sha256(
                    f'{self.seed}\x00{stratum}\x00{sample.metadata["record_id"]}'.encode('utf-8')
                ).digest(),
            )
            selected.extend(candidates[: self.selection_config.keep_per_stratum])

        result = MemoryDataset(selected, name=population.name, location=population.location)
        if self.shuffle:
            result.shuffle(seed=self.seed)
        count = resolve_dataset_limit(self.limit, len(result))
        samples = list(result) if count is None else list(result)[:count]
        result = MemoryDataset(
            repeat_samples(samples, self.repeats),
            name=population.name,
            location=population.location,
            shuffled=self.shuffle,
        )
        result.reindex(group_size=self.repeats)
        return result

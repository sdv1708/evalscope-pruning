"""Reproduce the validated length/document and length/difficulty AA-LCR designs."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from typing import Dict, List, Literal

from pydantic import Field, field_validator

from evalscope.benchmarks._reference_pruning.selection import (
    ReferencePanel,
    ReferenceTask,
    SelectedTask,
    SelectionConfig,
    allocate_tasks,
)


class AALCRConfig(SelectionConfig):
    """Keep the issue #17 full-reference fallback as the default."""

    pruning_strategy: Literal['metadata_stratified', 'length_difficulty_stratified'] = 'length_difficulty_stratified'


class AALCRTask(ReferenceTask):
    """Benchmark metadata, never a target model's usage or generated answer."""

    input_tokens: int = Field(gt=0)
    source_urls: List[str] = Field(min_length=1)

    @field_validator('source_urls')
    @classmethod
    def validate_sources(cls, value: List[str]) -> List[str]:
        """Require the canonical document-URL set used by the analysis."""
        if any(not url.strip() or url != url.strip() for url in value) or len(set(value)) != len(value):
            raise ValueError('source_urls must be unique, nonempty, trimmed strings.')
        return sorted(value)


class AALCRPanel(ReferencePanel[AALCRTask]):
    """A frozen, fingerprint-bound AA-LCR reference population."""


def _bands(values: Dict[int, int]) -> Dict[int, int]:
    ordered = sorted(values.values())
    return {
        index: min(2, 3 * (bisect_left(ordered, value) + bisect_right(ordered, value)) // (2 * len(ordered)))
        for index, value in values.items()
    }


def select_long_context(
    panel: AALCRPanel, config: AALCRConfig, *, seed: int, references: List[str]
) -> List[SelectedTask]:
    """Cover empirical length thirds crossed with document bands or reference passes."""
    if not references:
        raise ValueError('Selection needs at least one reference model after excluding the evaluated model.')
    lengths = _bands({task.index: task.input_tokens for task in panel.tasks})
    documents = _bands({task.index: len(task.source_urls) for task in panel.tasks})
    groups: Dict[str, List[AALCRTask]] = defaultdict(list)
    for task in panel.tasks:
        second = (
            f'documents:{documents[task.index]}'
            if config.pruning_strategy == 'metadata_stratified'
            else f'passes:{sum(task.scores[model] for model in references)}'
        )
        groups[f'length:{lengths[task.index]}|{second}'].append(task)
    return allocate_tasks(groups, ratio=config.prune_ratio, seed=seed)

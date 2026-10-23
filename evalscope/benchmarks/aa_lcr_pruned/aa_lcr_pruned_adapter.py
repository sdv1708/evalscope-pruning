"""AA-LCR selection in the native loader with inherited contract-based judging."""

import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from evalscope.api.dataset import DatasetDict, Sample
from evalscope.api.metric import AggScore, SampleScore
from evalscope.api.metric.semantics import MetricSelector
from evalscope.api.registry import BENCHMARK_REGISTRY, register_benchmark
from evalscope.benchmarks._reference_pruning.adapter import ReferencePruningAdapter
from evalscope.benchmarks._reference_pruning.selection import (
    ReferencePanel,
    SelectedTask,
    question_fingerprint,
    read_reference_json,
)
from evalscope.benchmarks.aa_lcr.aa_lcr_adapter import AALCRAdapter
from evalscope.constants import HubType

from .selection import AALCRConfig, AALCRPanel, select_long_context

DESCRIPTION = """
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
"""

_BASE = BENCHMARK_REGISTRY['aa_lcr']
_EXTRA = {
    'pruning_strategy': {
        'type': 'str',
        'description': 'AA-LCR historical strata; baselines rejected.',
        'value': 'length_difficulty_stratified',
    },
    'prune_ratio': {'type': 'float', 'description': 'Retained fraction; 1.0 is the defended fallback.', 'value': 1.0},
    'reference_path': {'type': 'str', 'description': 'Local frozen AA-LCR panel JSON.', 'value': ''},
    'excluded_reference_models': {'type': 'list[str]', 'description': 'Additional holdout model names.', 'value': []},
}


@register_benchmark(
    replace(
        _BASE,
        name='aa_lcr_pruned',
        pretty_name='AA-LCR (Reference Pruned)',
        description=DESCRIPTION,
        evaluation_version='v1.0',
        hf_dataset_revision='bdae010bbce259820c0e34c1d7cce210d966fb75',
        extra_params={**_BASE.extra_params, **_EXTRA},
        primary_metric=MetricSelector(name='accuracy', aggregation='weighted_mean', dimensions={'scope': 'population'}),
    )
)
class AALCRPrunedAdapter(ReferencePruningAdapter, AALCRAdapter):
    """Preserve native judging while pruning before inference, limits and repeats."""

    pruning_config: AALCRConfig

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pruning_config = AALCRConfig.model_validate({key: (self.extra_params or {})[key] for key in _EXTRA})
        self.save_metadata = True
        if self._task_config is not None and (self.seed is None or isinstance(self.seed, bool)):
            raise ValueError('Pruning requires an integer seed for reproducible selection.')
        if self._task_config is not None and self.limit is not None:
            raise ValueError('aa_lcr_pruned does not support limit; use prune_ratio to preserve population weights.')
        if (
            self._task_config is not None
            and not self._benchmark_meta.dataset_source.is_local
            and self.dataset_hub != HubType.HUGGINGFACE
        ):
            raise ValueError('aa_lcr_pruned requires dataset_hub=huggingface for the pinned source, or local_path.')

    def load_from_disk(self, use_local_loader: bool = True) -> Tuple[DatasetDict, Optional[DatasetDict]]:
        """Use the native local JSONL/CSV/parquet loader for benchmark mirrors."""
        return super().load_from_disk(use_local_loader=use_local_loader)

    def _get_context(self, record: Dict[str, Any]) -> str:
        folder = Path(self.text_dir) / record['document_category'] / record['document_set_id']
        filenames = record.get('data_source_filenames')
        if not isinstance(filenames, str) or not filenames.strip():
            raise ValueError('AA-LCR requires ordered data_source_filenames.')
        documents = []
        for filename in filenames.split(';'):
            path = folder / filename.strip()
            if not path.is_file():
                # The pinned ZIP omits its UTF-8 flag for four non-ASCII names.
                # One is also decomposed Unicode. Resolve only these exact encodings.
                decomposed = unicodedata.normalize('NFD', filename.strip())
                aliases = {
                    folder / decomposed,
                    folder / filename.strip().encode('utf-8').decode('cp437'),
                    folder / decomposed.encode('utf-8').decode('cp437'),
                }
                matches = [alias for alias in aliases if alias.is_file()]
                if len(matches) > 1:
                    raise ValueError(f'AA-LCR document filename is ambiguous: {filename}')
                if matches:
                    path = matches[0]
            if not path.resolve().is_relative_to(Path(self.text_dir).resolve()):
                raise ValueError('AA-LCR document path escapes text_dir.')
            content = path.read_text(encoding='utf-8').strip()
            if not content:
                raise ValueError(f'AA-LCR document is empty: {path}')
            documents.append(content)
        return '\n\n'.join(f'BEGIN DOCUMENT {i + 1}:\n{doc}\nEND DOCUMENT {i + 1}' for i, doc in enumerate(documents))

    def record_to_sample(self, record: Dict[str, Any]) -> Sample:
        """Add stable identity without using row order or target outputs."""
        tokens = record.get('input_tokens')
        if isinstance(tokens, str) and tokens.isascii() and tokens.isdecimal():
            record = {**record, 'input_tokens': int(tokens)}
        sample = super().record_to_sample(record)
        sample.metadata['question_sha256'] = question_fingerprint(record['question'])
        return sample

    def selection_design(self) -> Tuple[ReferencePanel[Any], List[SelectedTask], List[str]]:
        """Validate benchmark signals and exclude target grades before forming strata."""
        panel = AALCRPanel.model_validate(read_reference_json(self.pruning_config.reference_path))
        excluded = self.excluded_models() | set(self.pruning_config.excluded_reference_models)
        references = sorted(set(panel.tasks[0].scores) - excluded)
        assert isinstance(self.seed, int)
        selected = select_long_context(panel, self.pruning_config, seed=self.seed, references=references)
        self._panel_metadata = {task.question_sha256: task for task in panel.tasks}
        return panel, selected, references

    def validate_population_sample(self, sample: Sample) -> None:
        """Reject source metadata drift even when question fingerprints still match."""
        task = self._panel_metadata[sample.metadata['question_sha256']]
        urls = sample.metadata.get('data_source_urls')
        tokens = sample.metadata.get('input_tokens')
        if (
            type(tokens) is not int
            or tokens != task.input_tokens
            or not isinstance(urls, str)
            or sorted({url.strip() for url in urls.split(';') if url.strip()}) != task.source_urls
        ):
            raise ValueError(f'AA-LCR benchmark metadata mismatch at reference index {task.index}.')

    def aggregate_scores(self, sample_scores: List[SampleScore]) -> List[AggScore]:
        """Keep judge uncertainty visible next to the reported population estimate."""
        aggregates = super().aggregate_scores(sample_scores)
        for score in aggregates:
            if score.aggregation == 'weighted_mean':
                score.metadata = {
                    **(score.metadata or {}),
                    'judge_noise': 'Unmeasured; sampling uncertainty excludes judge error.',
                    'full_retention_removes_judge_error': False,
                    'source_version': 'AA-LCR v1.0; see configured source revision/local mirror.',
                }
        return aggregates

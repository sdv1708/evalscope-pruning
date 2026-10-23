"""Select a frozen population before repeats; report complete design-weighted grades."""

import hashlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from evalscope.api.benchmark import DefaultDataAdapter
from evalscope.api.dataset import DataLoader, Dataset, MemoryDataset, Sample
from evalscope.api.dataset.loader import repeat_samples
from evalscope.api.metric import AggScore, SampleScore

from .selection import ReferencePanel, SelectedTask, SelectionConfig


class ReferencePruningAdapter(DefaultDataAdapter):
    """Share population matching and weighting without changing benchmark grading."""

    aggregate_empty_scores = True
    pruning_config: SelectionConfig

    def selection_design(self) -> Tuple[ReferencePanel[Any], List[SelectedTask], List[str]]:
        """Return the validated panel, selection and non-target reference names."""
        raise NotImplementedError

    def excluded_models(self) -> set[str]:
        """Exclude underlying target identities as well as the display identity."""
        if self._task_config is None:
            raise ValueError('Reference pruning requires a TaskConfig.')
        model = self._task_config.model
        names = [model, getattr(model, 'name', None), getattr(model, 'model_name', None), self._task_config.model_id]
        return {name for name in names if isinstance(name, str) and name}

    def validate_population_sample(self, sample: Sample) -> None:
        """Allow benchmark-specific validation before matching the population."""

    def load_subset(self, subset: str, data_loader: Type[DataLoader]) -> Dataset:
        """Match the frozen population, select, then apply framework shuffle and repeats."""
        if self._task_config is None:
            raise ValueError('Loading a reference pruner requires a TaskConfig.')
        panel, selected, reference_models = self.selection_design()
        population_config = self._task_config.model_copy(update={'repeats': 1})
        with (
            self._temporary_attribute('_task_config', population_config),
            self._temporary_attribute('shuffle', False),
        ):
            population = super().load_subset(subset, data_loader)
        wanted = {task.question_sha256 for task in panel.tasks}
        matched: Dict[str, Sample] = {}
        for sample in population:
            fingerprint = sample.metadata['question_sha256']
            if fingerprint not in wanted:
                continue
            if fingerprint in matched:
                raise ValueError(f'Duplicate source question fingerprint in subset {subset!r}: {fingerprint}.')
            self.validate_population_sample(sample)
            matched[fingerprint] = sample
        if missing := wanted - matched.keys():
            raise ValueError(
                f'Reference population mismatch: {len(missing)} questions missing from subset {subset!r}. '
                'Check source version and date filters; row positions cannot substitute for identity.'
            )
        panel_sha256 = hashlib.sha256(Path(self.pruning_config.reference_path).read_bytes()).hexdigest()
        samples = []
        for task in selected:
            sample = matched[task.question_sha256]
            sample.metadata['pruning'] = {
                **task.model_dump(),
                'strategy': self.pruning_config.pruning_strategy,
                'keep_ratio': self.pruning_config.prune_ratio,
                'seed': self.seed,
                'population_size': len(panel.tasks),
                'selected_size': len(selected),
                'reference_models': reference_models,
                'reference_panel_sha256': panel_sha256,
            }
            samples.append(sample)
        result = MemoryDataset(samples, name=population.name, location=population.location)
        if self.shuffle:
            result.shuffle(seed=self.seed)
        result = MemoryDataset(
            repeat_samples(list(result), self.repeats),
            name=population.name,
            location=population.location,
            shuffled=self.shuffle,
        )
        result.reindex(group_size=self.repeats)
        return result

    def aggregate_scores(self, sample_scores: List[SampleScore]) -> List[AggScore]:
        """Retain upstream subset metrics and add the design-weighted population mean.

        Each question contributes its weight times its mean across repeated attempts.
        Incomplete or unscored attempts fail closed instead of renormalizing a biased
        surviving subset. This estimate has no customer-decision certification.
        """
        if not sample_scores:
            raise ValueError('Incomplete pruning scores: no graded questions.')
        sample_ids = [score.sample_id for score in sample_scores]
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError('Incomplete pruning scores: duplicate execution sample IDs.')
        groups: Dict[int, List[SampleScore]] = defaultdict(list)
        traces: Dict[int, SelectedTask] = {}
        context: Optional[Dict[str, Any]] = None
        context_keys = (
            'selected_size',
            'population_size',
            'strategy',
            'keep_ratio',
            'seed',
            'reference_models',
            'reference_panel_sha256',
        )
        for score in sample_scores:
            raw = (score.sample_metadata or {}).get('pruning')
            if not isinstance(raw, dict):
                raise ValueError('Incomplete pruning scores: missing selection metadata.')
            trace = SelectedTask.model_validate(raw)
            current = {key: raw[key] for key in context_keys}
            if context is None:
                context = current
            if context != current or (trace.index in traces and traces[trace.index] != trace):
                raise ValueError('Inconsistent pruning score provenance.')
            if not score.score.status.is_usable or score.score.value.get('acc') not in (0, 1):
                raise ValueError('Incomplete pruning scores: every planned attempt needs a binary acc grade.')
            traces[trace.index] = trace
            groups[trace.index].append(score)
        assert context is not None
        if len(groups) != context['selected_size'] or any(
            len(attempts) != self.repeats for attempts in groups.values()
        ):
            raise ValueError('Incomplete pruning scores: missing questions or repeated attempts.')
        for attempts in groups.values():
            positions = [score.generation_index for score in attempts]
            if any(position is not None for position in positions) and set(positions) != set(range(self.repeats)):
                raise ValueError('Incomplete pruning scores: missing or duplicated attempt positions.')
        if not math.isclose(math.fsum(trace.weight for trace in traces.values()), 1.0, abs_tol=1e-12):
            raise ValueError('Incomplete pruning scores: population weights must sum to one.')
        estimate = math.fsum(
            traces[index].weight * math.fsum(float(score.score.value['acc']) for score in attempts) / len(attempts)
            for index, attempts in groups.items()
        )
        aggregates = super().aggregate_scores(sample_scores)
        aggregates.append(
            AggScore(
                score=estimate,
                metric_name='accuracy',
                aggregation='weighted_mean',
                dimensions={'scope': 'population'},
                num=len(groups),
                ids=[score.sample_id for score in sample_scores if score.sample_id is not None],
                metadata={**context, 'selected_indices': sorted(groups), 'decision_certified': False},
            )
        )
        return aggregates

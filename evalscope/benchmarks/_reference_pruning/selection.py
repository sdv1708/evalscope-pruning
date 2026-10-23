"""Frozen historical selection design, independent of evaluated model outcomes."""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Generic, List, Literal, Set, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self


class SelectionConfig(BaseModel):
    """A ratio is the fraction retained; full retention is the supported default."""

    model_config = ConfigDict(strict=True, extra='forbid')

    pruning_strategy: str
    prune_ratio: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    reference_path: str = ''
    excluded_reference_models: List[str] = Field(default_factory=list)

    @field_validator('prune_ratio', mode='before')
    @classmethod
    def validate_ratio(cls, value: Any) -> Any:
        """Do not interpret a boolean or numeric string as a retained fraction."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('prune_ratio must be a finite number in (0, 1].')
        return value


class PruningConfig(SelectionConfig):
    """LiveCodeBench reference-stratification configuration."""

    pruning_strategy: Literal['difficulty_stratified', 'response_stratified'] = 'difficulty_stratified'


def question_fingerprint(question: str) -> str:
    """Bind historical identity to question content, never the current row position."""
    normalized = question.replace('\r\n', '\n').replace('\r', '\n').strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


class ReferenceTask(BaseModel):
    """One original analysis index bound to a question and historical binary grades."""

    model_config = ConfigDict(strict=True, extra='forbid')

    index: int = Field(ge=0)
    question_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    scores: Dict[str, int] = Field(min_length=1)

    @field_validator('scores')
    @classmethod
    def validate_scores(cls, scores: Dict[str, int]) -> Dict[str, int]:
        """Reject grades outside the frozen binary reference design."""
        if any(not name.strip() or value not in (0, 1) for name, value in scores.items()):
            raise ValueError('Reference scores require nonempty model names and binary grades.')
        return scores


Task = TypeVar('Task', bound=ReferenceTask)


class ReferencePanel(BaseModel, Generic[Task]):
    """A complete, unique reference population with optional provenance."""

    model_config = ConfigDict(strict=True, extra='forbid')

    schema_version: Literal[1]
    tasks: List[Task] = Field(min_length=1)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_population(self) -> Self:
        """Every model must describe the same unambiguous set of questions."""
        if len({task.index for task in self.tasks}) != len(self.tasks):
            raise ValueError('Duplicate reference index.')
        if len({task.question_sha256 for task in self.tasks}) != len(self.tasks):
            raise ValueError('Duplicate reference question fingerprint.')
        models = set(self.tasks[0].scores)
        if any(set(task.scores) != models for task in self.tasks):
            raise ValueError('Reference model identities differ across tasks.')
        return self


def _unique_object(pairs: List[tuple]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key {key!r} in reference panel.')
        result[key] = value
    return result


def load_reference_panel(path: str) -> ReferencePanel[ReferenceTask]:
    """Read a local panel without downloads or model calls."""
    return ReferencePanel[ReferenceTask].model_validate(read_reference_json(path))


def read_reference_json(path: str) -> Any:
    """Read local reference JSON and reject duplicate keys."""
    if not path:
        raise ValueError('reference_path is required; supply a frozen historical reference panel.')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)


class SelectedTask(BaseModel):
    """Population contribution of one retained original question."""

    model_config = ConfigDict(strict=True)

    index: int = Field(ge=0)
    question_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    weight: float = Field(gt=0, le=1, allow_inf_nan=False)
    stratum: str = Field(min_length=1)
    population_count: int = Field(gt=0)
    selected_count: int = Field(gt=0)


def select_tasks(
    panel: ReferencePanel[ReferenceTask], config: PruningConfig, *, seed: int, excluded_models: Set[str]
) -> List[SelectedTask]:
    """Reproduce the analysis v1 allocation and SHA-256 priorities exactly.

    Each occupied stratum receives one slot. Remaining slots go to the largest
    proportional deficit, with lexical ties. Target grades are excluded before
    defining strata. No fallback to a forbidden comparison baseline is allowed.
    """
    models = sorted(set(panel.tasks[0].scores) - excluded_models - set(config.excluded_reference_models))
    if not models:
        raise ValueError('Selection needs at least one reference model after excluding the evaluated model.')
    groups: Dict[str, List[ReferenceTask]] = defaultdict(list)
    for task in panel.tasks:
        pattern = [task.scores[model] for model in models]
        key = (
            f'passes:{sum(pattern)}/{len(models)}'
            if config.pruning_strategy == 'difficulty_stratified'
            else 'pattern:' + ''.join(map(str, pattern))
        )
        groups[key].append(task)
    return allocate_tasks(groups, ratio=config.prune_ratio, seed=seed)


def allocate_tasks(groups: Dict[str, List[Task]], *, ratio: float, seed: int) -> List[SelectedTask]:
    """Cover every occupied stratum using the original proportional/hash design."""
    total = sum(len(members) for members in groups.values())
    budget = math.ceil(total * ratio)
    if budget < len(groups):
        raise ValueError(f'Budget {budget} cannot cover {len(groups)} occupied strata.')
    allocation = dict.fromkeys(sorted(groups), 1)
    for _ in range(budget - len(groups)):
        key = min(
            (key for key in allocation if allocation[key] < len(groups[key])),
            key=lambda key: (-(budget * len(groups[key]) - allocation[key] * total), key),
        )
        allocation[key] += 1
    selected: List[SelectedTask] = []
    for key, count in allocation.items():
        members = sorted(
            groups[key],
            key=lambda task: (
                hashlib.sha256(f'lcb-pruning-v1:{seed}:{task.index}'.encode('ascii')).digest(),
                task.index,
            ),
        )[:count]
        selected.extend(
            SelectedTask(
                index=task.index,
                question_sha256=task.question_sha256,
                weight=len(groups[key]) / (total * count),
                stratum=key,
                population_count=len(groups[key]),
                selected_count=count,
            )
            for task in members
        )
    return sorted(selected, key=lambda task: task.index)

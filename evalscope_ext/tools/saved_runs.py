"""Read Native Part A evidence and validate completeness before comparing it."""

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

BENCHMARKS = {
    'live_code_bench': 'live_code_bench',
    'live_code_bench_pruned': 'live_code_bench',
    'aa_lcr': 'aa_lcr',
    'aa_lcr_pruned': 'aa_lcr',
}
PRUNING_KEYS = {'pruning_strategy', 'prune_ratio', 'reference_path', 'excluded_reference_models', 'text_dir'}


class Question(BaseModel):
    """One stable evaluated input, with attempts averaged before population weighting."""

    mean: float
    weight: float
    trace: Optional[dict[str, Any]] = None


class SavedRun(BaseModel):
    """Validated model/benchmark/subset evidence from one run root."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    model: str
    benchmark: str
    subset: str
    questions: dict[str, Question]
    attempts: int
    population_size: int
    settings: dict[str, Any]
    sources: list[Path]
    legacy_full: bool = False

    @property
    def samples(self) -> int:
        """Count unique questions, never repeated generations."""
        return len(self.questions)

    @property
    def raw_mean(self) -> float:
        """Return the unweighted question mean."""
        return math.fsum(q.mean for q in self.questions.values()) / self.samples

    @property
    def score(self) -> float:
        """Return the design-weighted population estimate."""
        return math.fsum(q.mean * q.weight for q in self.questions.values())


class Trace(BaseModel):
    """Strict numeric constraints for persisted selection metadata."""

    model_config = ConfigDict(strict=True)
    index: int = Field(ge=0)
    question_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    weight: float = Field(gt=0, le=1, allow_inf_nan=False)
    stratum: str = Field(min_length=1)
    population_count: int = Field(gt=0)
    selected_count: int = Field(gt=0)
    population_size: int = Field(gt=0)
    selected_size: int = Field(gt=0)
    keep_ratio: float = Field(gt=0, le=1, allow_inf_nan=False)
    strategy: str = Field(min_length=1)
    seed: int
    reference_models: list[str] = Field(min_length=1)
    reference_panel_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key {key!r}.')
        result[key] = value
    return result


def _json(text: str, path: Path) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_object)
    except ValueError as error:
        raise ValueError(f'{path}: invalid JSON: {error}') from error


def _count(value: Any, context: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f'{context}: expected a positive integer count.')
    return value


def _score(value: Any, context: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f'{context}: expected a finite accuracy in [0,1].')
    return float(value)


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items() if key not in {'api_key', 'api-key', 'authorization'}}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _settings(config: dict[str, Any], name: str) -> dict[str, Any]:
    if config.get('limit') is not None:
        raise ValueError('Limited runs are incompatible: remove limit and control size with prune_ratio.')
    try:
        spec = dict(config['resolved_benchmarks'][name])
        version = config['evaluation_identity']['benchmarks'][name]['evaluation_version']
    except (KeyError, TypeError) as error:
        raise ValueError(
            'Missing resolved_benchmarks/evaluation_identity in configs/task_config.yaml; '
            'regenerate runs with the pinned Native framework.'
        ) from error
    for field in ('name', 'primary_metric', 'shuffle'):
        spec.pop(field, None)
    spec['extra_params'] = {
        key: value for key, value in spec.get('extra_params', {}).items() if key not in PRUNING_KEYS
    }
    fields = (
        'model',
        'eval_type',
        'model_args',
        'generation_config',
        'judge',
        'repeats',
        'chat_template',
        'sandbox',
        'use_sandbox',
        'model_task',
        'evalscope_version',
    )
    result = {key: _scrub(config.get(key)) for key in fields}
    result.update(resolved_benchmark=spec, evaluation_version=version)
    return result


def _input_key(row: dict[str, Any], path: Path) -> str:
    messages = []
    for message in row['messages']:
        if message['role'] == 'assistant' and message.get('source') == 'generate':
            break
        # Native zero-shot Part A has a single user input; assistant generations are excluded.
        if message['role'] in ('system', 'user'):
            messages.append({'role': message['role'], 'content': message['content']})
    if not messages or not any(m['role'] == 'user' for m in messages):
        raise ValueError(f'{path}: missing input messages; prompt identity is required.')
    grading_cases = (row['sample_score'].get('sample_metadata') or {}).get('evaluation_sample')
    encoded = json.dumps(
        [messages, row.get('target'), grading_cases], sort_keys=True, ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _questions(path: Path, repeats: int, pruned: bool) -> tuple[dict[str, Question], int, int]:
    groups: dict[str, list[tuple[float, Any, Any]]] = defaultdict(list)
    ids: set[int] = set()
    with path.open(encoding='utf-8-sig') as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            context = f'{path}:{line_number}'
            row = _json(line, path)
            try:
                sample = row['sample_score']
                identifier = row['index']
                if type(identifier) is not int or identifier in ids or sample['sample_id'] != identifier:
                    raise ValueError(f'{context}: duplicate or mismatched execution sample ID.')
                ids.add(identifier)
                grade = sample['score']
                if grade.get('status', 'success') != 'success' or (grade.get('metadata') or {}).get('error'):
                    raise ValueError(f'{context}: failed or degraded score; regenerate complete successful reviews.')
                value = grade['value']['acc']
                if not isinstance(value, (int, float, bool)) or value not in (0, 1):
                    raise ValueError(f'{context}: requires a usable binary acc grade.')
                raw = (sample.get('sample_metadata') or {}).get('pruning')
                trace = Trace.model_validate(raw).model_dump() if raw is not None else None
                if pruned and trace is None:
                    raise ValueError(f'{context}: missing pruning metadata; use the native reference adapter.')
                groups[_input_key(row, path)].append((float(value), sample.get('generation_index'), trace))
            except (KeyError, TypeError) as error:
                raise ValueError(
                    f'{context}: missing or invalid review field {error}; preserve Native reviews.'
                ) from error
    if not groups:
        raise ValueError(f'{path}: empty review file.')
    questions = {}
    for key, attempts in groups.items():
        positions = [a[1] for a in attempts]
        if (
            len(attempts) != repeats
            or any(type(p) is not int for p in positions)
            or set(positions) != set(range(repeats))
        ):
            raise ValueError(
                f'{path}: incomplete or duplicate repeated attempts; expected generation_index 0..{repeats - 1}.'
            )
        trace = attempts[0][2]
        if any(a[2] != trace for a in attempts):
            raise ValueError(f'{path}: inconsistent pruning metadata across attempts.')
        questions[key] = Question(
            mean=math.fsum(a[0] for a in attempts) / repeats,
            weight=trace['weight'] if trace else 1 / len(groups),
            trace=trace,
        )
    population = _validate_design(questions, path) if pruned else len(questions)
    return questions, len(ids), population


def _validate_design(questions: dict[str, Question], path: Path) -> int:
    traces = [q.trace for q in questions.values()]
    if any(t is None for t in traces):
        raise ValueError(f'{path}: missing pruning metadata.')
    first = traces[0]
    assert first is not None
    context_fields = (
        'population_size',
        'selected_size',
        'keep_ratio',
        'seed',
        'strategy',
        'reference_models',
        'reference_panel_sha256',
    )
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    indices = set()
    fingerprints = set()
    for trace in traces:
        assert trace is not None
        if any(trace[field] != first[field] for field in context_fields):
            raise ValueError(f'{path}: inconsistent selection provenance.')
        if trace['index'] in indices or trace['question_sha256'] in fingerprints:
            raise ValueError(f'{path}: duplicate original question identity.')
        indices.add(trace['index'])
        fingerprints.add(trace['question_sha256'])
        strata[trace['stratum']].append(trace)
    population = first['population_size']
    if len(questions) != first['selected_size'] or len(questions) != math.ceil(population * first['keep_ratio']):
        raise ValueError(f'{path}: missing selected questions or inconsistent retained ratio.')
    if sum(group[0]['population_count'] for group in strata.values()) != population:
        raise ValueError(f'{path}: missing population strata.')
    for group in strata.values():
        count = len(group)
        original = group[0]['population_count']
        for trace in group:
            expected = original / (population * count)
            if (
                trace['selected_count'] != count
                or trace['population_count'] != original
                or original < count
                or not math.isclose(trace['weight'], expected, rel_tol=0, abs_tol=1e-12)
            ):
                raise ValueError(f'{path}: invalid stratum counts or population weights.')
    if not math.isclose(math.fsum(q.weight for q in questions.values()), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError(f'{path}: population weights must sum to one.')
    return int(population)


def _rounded_metric_score(metric: dict[str, Any]) -> float:
    """Mirror Native report rounding at subset, category and metric boundaries."""
    categories = []
    for category in metric['categories']:
        subsets = [subset for subset in category['subsets'] if not subset.get('is_aggregate', False)]
        count = sum(subset['num'] for subset in subsets)
        if count:
            score = round(sum(subset['score'] * subset['num'] for subset in subsets) / count, 4)
            categories.append((score, count))
    return round(sum(score * count for score, count in categories) / sum(count for _, count in categories), 4)


def load_runs(root: Path) -> dict[tuple[str, str, str], SavedRun]:
    """Read one exact run root, rejecting ambiguity and mismatched report/review evidence."""
    root = root.resolve()
    report_paths = sorted((root / 'reports').glob('*/*.json'))
    if not report_paths:
        raise ValueError(
            f'{root}: no reports/<model>/<benchmark>.json. Pass the exact run root, '
            'not reports/, reviews/, or a timestamp parent.'
        )
    config_path = root / 'configs' / 'task_config.yaml'
    try:
        config = yaml.safe_load(config_path.read_text(encoding='utf-8-sig'))
    except yaml.YAMLError as error:
        raise ValueError(f'{config_path}: invalid YAML configuration.') from error
    if not isinstance(config, dict):
        raise ValueError(f'{config_path}: expected a Native configuration object.')
    repeats = _count(config.get('repeats'), f'{config_path}: repeats')
    runs = {}
    for path in report_paths:
        payload = _json(path.read_text(encoding='utf-8-sig'), path)
        if not isinstance(payload, dict) or payload.get('schema_version') != 2:
            raise ValueError(f'{path}: expected Native report schema_version=2; regenerate with pinned framework.')
        name = payload['dataset_name']
        model = payload['model_name']
        if name not in BENCHMARKS:
            raise ValueError(f'{path}: unsupported benchmark {name!r}; expected Part A coding or AA-LCR.')
        if path.stem != name or path.parent.name != model or config.get('model_id') != model:
            raise ValueError(f'{path}: mismatched report path, model_id or dataset identity.')
        execution = payload.get('execution_summary')
        if (
            not isinstance(execution, dict)
            or execution.get('incomplete') is not False
            or execution.get('errored') != 0
            or execution.get('requested') != execution.get('succeeded')
        ):
            raise ValueError(f'{path}: missing or incomplete execution_summary; finish the run before comparison.')
        pruned = name.endswith('_pruned')
        metrics = [
            m
            for m in payload['metrics']
            if m['identity']
            == {
                'name': 'accuracy',
                'aggregation': 'weighted_mean' if pruned else ('pass_at_k' if name == 'live_code_bench' else 'mean'),
                'dimensions': {'scope': 'population'} if pruned else ({'k': 1} if name == 'live_code_bench' else {}),
            }
        ]
        if len(metrics) != 1:
            raise ValueError(f'{path}: expected exactly one compatible accuracy metric, including population weights.')
        metric = metrics[0]
        subsets = [s for c in metric['categories'] for s in c['subsets'] if not s.get('is_aggregate', False)]
        if not subsets or len({s['name'] for s in subsets}) != len(subsets):
            raise ValueError(f'{path}: missing or duplicate scored subsets.')
        total_attempts = 0
        total_metric_count = 0
        for subset in subsets:
            subset_name = subset['name']
            if not isinstance(subset_name, str) or '/' in subset_name or '\\' in subset_name or '..' in subset_name:
                raise ValueError(f'{path}: invalid subset name.')
            review_path = root / 'reviews' / model / f'{name}_{subset_name}.jsonl'
            questions, attempts, population = _questions(review_path, repeats, pruned)
            run = SavedRun(
                model=model,
                benchmark=BENCHMARKS[name],
                subset=subset_name,
                questions=questions,
                attempts=attempts,
                population_size=population,
                settings=_settings(config, name),
                sources=[path, review_path, config_path],
                legacy_full=not pruned,
            )
            # Native Mean counts attempts; the reference weighted mean and LCB pass@1 count questions.
            metric_count = attempts if name == 'aa_lcr' else run.samples
            if _count(subset['num'], str(path)) != metric_count:
                raise ValueError(f'{path}: report/review sample counts differ for {subset_name}.')
            if abs(_score(subset['score'], str(path)) - run.score) > 0.000051:
                raise ValueError(f'{path}: report/review weighted score mismatch for {subset_name}.')
            key = (model, run.benchmark, subset_name)
            if key in runs:
                raise ValueError(f'{root}: duplicate model/benchmark/subset reports.')
            runs[key] = run
            total_attempts += attempts
            total_metric_count += metric_count
        if (
            _count(metric['num'], str(path)) != total_metric_count
            or abs(_score(metric['score'], str(path)) - _rounded_metric_score(metric)) > 1e-12
        ):
            raise ValueError(f'{path}: aggregate metric disagrees with subset evidence.')
        if execution['requested'] != total_attempts:
            raise ValueError(f'{path}: execution_summary/review attempt counts differ.')
    return runs

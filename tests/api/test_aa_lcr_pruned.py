"""AA-LCR pruning contracts through the public registry, loader and judge."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalscope.api.evaluator import TaskState
from evalscope.api.metric import SampleScore, Score
from evalscope.api.model import ModelOutput
from evalscope.api.registry import get_benchmark
from evalscope.config import TaskConfig
from evalscope.constants import ScoreStatus
from evalscope.metrics.judge.llm_judge import DEFAULT_PROMPT_TEMPLATE, LLMJudge
from evalscope.models.mockllm import MockLLM


def population(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Twelve questions, three independently known metadata strata of 2, 2, 8."""
    texts = tmp_path / 'texts' / 'fixture' / 'set'
    texts.mkdir(parents=True)
    (texts / 'b.txt').write_text('Second document.', encoding='utf-8')
    (texts / 'a.txt').write_text('First document.', encoding='utf-8')
    rows, tasks = [], []
    for index in range(12):
        question = f'Question {index}?'
        tokens = 100 if index < 4 else 1000
        urls = ['a'] if index < 2 else ['a', 'b']
        rows.append({
            'question': question, 'answer': 'Answer', 'document_category': 'fixture',
            'document_set_id': 'set', 'data_source_filenames': 'a.txt;b.txt',
            'data_source_urls': ';'.join(urls), 'input_tokens': tokens,
        })
        tasks.append({
            'index': index, 'question_sha256': hashlib.sha256(question.encode()).hexdigest(),
            'scores': {'reference-a': 0, 'reference-b': int(index >= 4)},
            'input_tokens': tokens, 'source_urls': urls,
        })
    source, panel = tmp_path / 'questions.jsonl', tmp_path / 'references.json'
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    panel.write_text(json.dumps({'schema_version': 1, 'tasks': tasks}), encoding='utf-8')
    return source, panel, texts.parent.parent


def configuration(source: Path, panel: Path, texts: Path, **extra: object) -> TaskConfig:
    """Exercise the native dataset_args contract."""
    return TaskConfig(
        model='unseen', datasets=['aa_lcr_pruned'], seed=42,
        dataset_args={'aa_lcr_pruned': {
            'local_path': str(source), 'subset_list': ['fixture'],
            'extra_params': {'reference_path': str(panel), 'text_dir': str(texts), **extra},
        }},
    )


def test_registered_selection_preserves_prompt_and_corrects_population_weights(tmp_path: Path) -> None:
    source, panel, texts = population(tmp_path)
    adapter = get_benchmark('aa_lcr_pruned', configuration(
        source, panel, texts, pruning_strategy='metadata_stratified', prune_ratio=0.25,
    ))
    samples = list(adapter.load_dataset()['fixture'])
    assert len(samples) == 3
    assert sorted(s.metadata['pruning']['population_count'] for s in samples) == [2, 2, 8]
    assert sorted(s.metadata['pruning']['weight'] for s in samples) == pytest.approx([1/6, 1/6, 2/3])
    assert all(s.target == 'Answer' for s in samples)
    assert str(samples[0].input).index('First document.') < str(samples[0].input).index('Second document.')
    assert 'BEGIN INPUT DOCUMENTS' in str(samples[0].input)


def test_default_is_full_retention_and_remote_source_requires_pinned_hub(tmp_path: Path) -> None:
    source, panel, texts = population(tmp_path)
    config = configuration(source, panel, texts)
    samples = list(get_benchmark('aa_lcr_pruned', config).load_dataset()['fixture'])
    assert [s.metadata['pruning']['index'] for s in samples] == list(range(12))
    assert all(s.metadata['pruning']['keep_ratio'] == 1.0 for s in samples)
    del config.dataset_args['aa_lcr_pruned']['local_path']
    with pytest.raises(ValueError, match='dataset_hub=huggingface'):
        get_benchmark('aa_lcr_pruned', config)
    config.dataset_hub = 'huggingface'
    adapter = get_benchmark('aa_lcr_pruned', config)
    assert adapter.dataset_revision == 'bdae010bbce259820c0e34c1d7cce210d966fb75'
    assert adapter.dataset_id == 'ArtificialAnalysis/AA-LCR'


@pytest.mark.parametrize('ratio', [0, -0.1, 1.01, True, '0.5', None, float('nan'), float('inf')])
def test_invalid_ratio_fails_before_loading(tmp_path: Path, ratio: object) -> None:
    source, panel, texts = population(tmp_path)
    with pytest.raises(ValueError, match='prune_ratio'):
        get_benchmark('aa_lcr_pruned', configuration(source, panel, texts, prune_ratio=ratio))


@pytest.mark.parametrize('strategy', ['uniform_random', 'easiest_only', 'hardest_only', 'unknown'])
def test_forbidden_strategies_fail_before_loading(tmp_path: Path, strategy: str) -> None:
    source, panel, texts = population(tmp_path)
    with pytest.raises(ValueError, match='pruning_strategy'):
        get_benchmark('aa_lcr_pruned', configuration(source, panel, texts, pruning_strategy=strategy))


def test_weighted_estimate_differs_from_subset_mean_and_fails_on_incomplete_grades(tmp_path: Path) -> None:
    source, panel, texts = population(tmp_path)
    config = configuration(source, panel, texts, pruning_strategy='metadata_stratified', prune_ratio=0.25)
    config.repeats = 2
    adapter = get_benchmark('aa_lcr_pruned', config)
    samples = list(adapter.load_dataset()['fixture'])
    scores = [SampleScore(
        sample_id=s.id, group_id=s.group_id, generation_index=i % 2, sample_metadata=s.metadata,
        score=Score(value={'acc': int(s.metadata['pruning']['population_count'] == 8)}),
    ) for i, s in enumerate(samples)]
    aggregates = adapter.aggregate_scores(scores)
    assert next(s.score for s in aggregates if s.aggregation == 'mean') == pytest.approx(1/3)
    estimate = next(s for s in aggregates if s.aggregation == 'weighted_mean')
    assert estimate.score == pytest.approx(2/3)
    assert estimate.num == 3
    assert estimate.metadata is not None
    assert estimate.metadata['decision_certified'] is False
    for incomplete in ([], scores[:-1], [scores[0], *scores]):
        with pytest.raises(ValueError, match='Incomplete'):
            adapter.aggregate_scores(incomplete)
    scores[0].score = Score(value={}, status=ScoreStatus.EXCLUDED)
    with pytest.raises(ValueError, match='binary acc'):
        adapter.aggregate_scores(scores)


@pytest.mark.parametrize('model_object', [False, True])
def test_target_exclusion_is_order_independent_and_precedes_repeats(tmp_path: Path, model_object: bool) -> None:
    source, panel, texts = population(tmp_path)
    config = configuration(source, panel, texts, prune_ratio=0.5)
    config.model = MockLLM(model_name='reference-a') if model_object else 'reference-a'
    config.model_id = 'custom-display'
    config.repeats = 2
    first = list(get_benchmark('aa_lcr_pruned', config).load_dataset()['fixture'])
    value = json.loads(panel.read_text(encoding='utf-8'))
    for task in value['tasks']:
        task['scores']['reference-a'] = 1
    value['tasks'].reverse()
    panel.write_text(json.dumps(value), encoding='utf-8')
    source.write_text('\n'.join(reversed(source.read_text(encoding='utf-8').splitlines()))+'\n', encoding='utf-8')
    second = list(get_benchmark('aa_lcr_pruned', config).load_dataset()['fixture'])
    assert [s.metadata['pruning']['index'] for s in first] == [s.metadata['pruning']['index'] for s in second]
    assert len(second) == 12
    assert [s.group_id for s in second] == [i//2 for i in range(12)]
    assert all(s.metadata['pruning']['reference_models'] == ['reference-b'] for s in second)


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'tokens', 'urls', 'documents', 'panel', 'budget', 'limit', 'seed', 'excluded'])
def test_invalid_source_or_configuration_fails_before_inference(tmp_path: Path, case: str) -> None:
    source, panel, texts = population(tmp_path)
    config = configuration(source, panel, texts)
    rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]
    if case == 'missing':
        rows.pop()
    elif case == 'duplicate':
        rows.append(rows[0])
    elif case == 'tokens':
        rows[0]['input_tokens'] += 1
    elif case == 'urls':
        rows[0]['data_source_urls'] = 'changed'
    elif case == 'documents':
        (texts/'fixture/set/a.txt').unlink()
    elif case == 'panel':
        panel.write_text('{"tasks": [], "tasks": []}', encoding='utf-8')
    elif case == 'budget':
        config.dataset_args['aa_lcr_pruned']['extra_params']['prune_ratio'] = 0.01
    elif case == 'limit':
        config.limit = 2
    elif case == 'seed':
        config.seed = None
    elif case == 'excluded':
        config.dataset_args['aa_lcr_pruned']['extra_params']['excluded_reference_models'] = ['reference-a', 'reference-b']
    source.write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf-8')
    with pytest.raises((ValueError, FileNotFoundError)):
        get_benchmark('aa_lcr_pruned', config).load_dataset()


@pytest.mark.parametrize('reply, expected', [('{"verdict":"CORRECT"}', 1), ('{"verdict":"INCORRECT"}', 0), ('prose', None), ('[ERROR] transport', None)])
def test_inherited_judge_contract_scores_or_excludes(tmp_path: Path, reply: str, expected: int | None) -> None:
    source, panel, texts = population(tmp_path)
    config = configuration(source, panel, texts)
    config.judge.strategy = 'llm'
    adapter = get_benchmark('aa_lcr_pruned', config)

    class Judge(LLMJudge):
        judge_id = model_id = 'scripted'

        def __init__(self) -> None:
            self.score_type = 'pattern'
            self.score_mapping = {'CORRECT': 1.0, 'INCORRECT': 0.0}
            self.prompt_template = DEFAULT_PROMPT_TEMPLATE
            self.system_prompt = None

        def generate(self, messages: object) -> ModelOutput:
            return ModelOutput.from_content('scripted', reply)

    adapter.llm_judge = Judge()
    sample = list(adapter.load_dataset()['fixture'])[0]
    state = TaskState(model='unseen', sample=sample, output=ModelOutput.from_content('unseen', 'Answer'), completed=True)
    result = adapter.calculate_metrics(state)
    if expected is None:
        assert result.score.status is ScoreStatus.EXCLUDED
        assert result.score.value == {}
    else:
        assert result.score.value == {'acc': expected}


def test_cli_smoke_has_native_reports_and_population_provenance(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root/'examples/aa_lcr_pruned/smoke.py'), '--work-dir', str(tmp_path/'run')],
        cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
    )
    assert result.returncode == 0, result.stdout[-3000:]+result.stderr[-3000:]
    report = json.loads((tmp_path/'run/reports/unseen/aa_lcr_pruned.json').read_text(encoding='utf-8'))
    metric = next(m for m in report['metrics'] if m['identity']['aggregation'] == 'weighted_mean')
    assert metric['score'] == 1.0
    assert metric['num'] == 3
    assert (tmp_path/'run/reports/report.html').is_file()
    review = next((tmp_path/'run/reviews').rglob('*.jsonl'))
    rows = [json.loads(line) for line in review.read_text(encoding='utf-8').splitlines()]
    assert len(rows) == 3
    assert all('pruning' in row['sample_score']['sample_metadata'] for row in rows)

"""Test native coding pruning through registry, loading, scoring and CLI seams."""

import hashlib
import json
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from evalscope.api.evaluator import TaskState
from evalscope.api.metric import SampleScore, Score
from evalscope.api.model import ModelOutput
from evalscope.api.registry import get_benchmark
from evalscope.config import TaskConfig
from evalscope.models.mockllm import MockLLM


def population(tmp_path: Path) -> tuple[Path, Path]:
    """Create six real-format LCB records and a historical two-model panel."""
    rows = []
    tasks = []
    patterns = [(0, 0), (0, 0), (0, 1), (1, 0), (1, 1), (1, 1)]
    for index, (left, right) in enumerate(patterns):
        question = f'Print {index}.'
        rows.append({
            'question_content': question, 'starter_code': '',
            'public_test_cases': json.dumps([{'input': '', 'output': str(index), 'testtype': 'stdin'}]),
            'private_test_cases': '[]', 'metadata': '{}',
            'contest_date': '2024-09-01T00:00:00',
        })
        tasks.append({
            'index': index, 'question_sha256': hashlib.sha256(question.encode()).hexdigest(),
            'scores': {'reference-a': left, 'reference-b': right},
        })
    source = tmp_path / 'questions.jsonl'
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    panel = tmp_path / 'references.json'
    panel.write_text(json.dumps({'schema_version': 1, 'tasks': tasks}), encoding='utf-8')
    return source, panel


def configuration(source: Path, panel: Path, **extra: object) -> TaskConfig:
    """Use the documented native dataset-args contract."""
    return TaskConfig(
        model='unseen-model', datasets=['live_code_bench_pruned'], seed=42,
        dataset_args={'live_code_bench_pruned': {
            'local_path': str(source), 'subset_list': ['fixture'],
            'extra_params': {'reference_path': str(panel), **extra},
        }},
    )


def test_registered_pruner_matches_analysis_selection_and_preserves_coding_prompts(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    adapter = get_benchmark('live_code_bench_pruned', configuration(source, panel, prune_ratio=0.5))
    samples = list(adapter.load_dataset()['fixture'])
    # Independently frozen from benchmark_reference.select_samples, seed 42.
    assert [sample.metadata['pruning']['index'] for sample in samples] == [1, 2, 5]
    assert [sample.metadata['pruning']['weight'] for sample in samples] == pytest.approx([1 / 3] * 3)
    assert all('evaluation_sample' in sample.metadata for sample in samples)
    assert all(len(sample.input) == 2 for sample in samples)
    assert '### Question:' in str(samples[0].input[1])


@pytest.mark.parametrize('ratio', [0, -0.1, 1.01, True, '0.5', None, float('nan'), float('inf')])
def test_invalid_ratios_fail_at_registry_boundary(tmp_path: Path, ratio: object) -> None:
    source, panel = population(tmp_path)
    with pytest.raises(ValueError, match='prune_ratio'):
        get_benchmark('live_code_bench_pruned', configuration(source, panel, prune_ratio=ratio))


def test_population_estimate_corrects_unequal_stratum_allocation(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    adapter = get_benchmark('live_code_bench_pruned', configuration(source, panel, prune_ratio=2 / 3))
    samples = list(adapter.load_dataset()['fixture'])
    scores = [SampleScore(
        sample_id=sample.id, group_id=sample.group_id, sample_metadata=sample.metadata,
        score=Score(value={'acc': int(sample.metadata['pruning']['stratum'] == 'passes:0/2')}),
    ) for sample in samples]
    aggregates = adapter.aggregate_scores(scores)
    subset_mean = next(score for score in aggregates if score.aggregation == 'mean')
    estimate = next(score for score in aggregates if score.aggregation == 'weighted_mean')
    assert subset_mean.score == 0.5
    assert estimate.score == pytest.approx(1 / 3)
    assert estimate.metric_name == 'accuracy'
    assert estimate.dimensions == {'scope': 'population'}
    with pytest.raises(ValueError, match='Incomplete'):
        adapter.aggregate_scores(scores[:-1])


@pytest.mark.parametrize('strategy', ['uniform_random', 'easiest_only', 'hardest_only', 'unknown'])
def test_comparison_baselines_cannot_become_production_policies(tmp_path: Path, strategy: str) -> None:
    source, panel = population(tmp_path)
    with pytest.raises(ValueError, match='pruning_strategy'):
        get_benchmark('live_code_bench_pruned', configuration(source, panel, pruning_strategy=strategy))


def test_order_invariance_repeats_and_target_exclusion(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    config = configuration(source, panel, prune_ratio=0.5)
    config.model = 'reference-a'
    config.repeats = 2
    first = get_benchmark('live_code_bench_pruned', config).load_dataset()['fixture']
    rows = source.read_text(encoding='utf-8').splitlines()
    source.write_text('\n'.join(reversed(rows)) + '\n', encoding='utf-8')
    manifest = json.loads(panel.read_text(encoding='utf-8'))
    for task in manifest['tasks']:
        task['scores']['reference-a'] = 1 - task['scores']['reference-a']
    manifest['tasks'].reverse()
    panel.write_text(json.dumps(manifest), encoding='utf-8')
    second = get_benchmark('live_code_bench_pruned', config).load_dataset()['fixture']
    assert [s.metadata['pruning']['index'] for s in first] == [s.metadata['pruning']['index'] for s in second]
    assert len(first) == 6
    assert [s.id for s in first] == list(range(6))
    assert [s.group_id for s in first] == [0, 0, 1, 1, 2, 2]
    assert all(s.metadata['pruning']['reference_models'] == ['reference-b'] for s in second)
    assert list(second)[0] is not list(second)[1]
    assert config.repeats == 2


def test_model_api_objects_exclude_underlying_target_with_a_custom_display_name(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    config = configuration(source, panel, prune_ratio=0.5)
    config.model = MockLLM(model_name='reference-a')
    config.model_id = 'custom-display'
    samples = get_benchmark('live_code_bench_pruned', config).load_dataset()['fixture']
    assert all(sample.metadata['pruning']['reference_models'] == ['reference-b'] for sample in samples)


@pytest.mark.parametrize('case', ['duplicate_index', 'duplicate_hash', 'score', 'model', 'duplicate_key'])
def test_invalid_reference_panels_fail_before_inference(tmp_path: Path, case: str) -> None:
    source, panel = population(tmp_path)
    value = json.loads(panel.read_text(encoding='utf-8'))
    if case == 'duplicate_index':
        value['tasks'][1]['index'] = value['tasks'][0]['index']
    elif case == 'duplicate_hash':
        value['tasks'][1]['question_sha256'] = value['tasks'][0]['question_sha256']
    elif case == 'score':
        value['tasks'][0]['scores']['reference-a'] = 0.5
    elif case == 'model':
        value['tasks'][0]['scores'].pop('reference-a')
    text = json.dumps(value) if case != 'duplicate_key' else '{"tasks": [], "tasks": []}'
    panel.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError):
        get_benchmark('live_code_bench_pruned', configuration(source, panel)).load_dataset()


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'date', 'undersized', 'no_references', 'limit'])
def test_unusable_populations_fail_explicitly(tmp_path: Path, case: str) -> None:
    source, panel = population(tmp_path)
    rows = source.read_text(encoding='utf-8').splitlines()
    extra: dict[str, object] = {}
    if case == 'missing':
        rows.pop()
    elif case == 'duplicate':
        rows.append(rows[0])
    elif case == 'date':
        extra['start_date'] = '2025-01-01'
    elif case == 'undersized':
        extra['prune_ratio'] = 0.1
    elif case == 'no_references':
        extra['excluded_reference_models'] = ['reference-a', 'reference-b']
    source.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    config = configuration(source, panel, **extra)
    if case == 'limit':
        config.limit = 1
    with pytest.raises(ValueError):
        get_benchmark('live_code_bench_pruned', config).load_dataset()


def test_full_retention_and_response_policy_are_available(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    full = get_benchmark('live_code_bench_pruned', configuration(source, panel)).load_dataset()['fixture']
    assert [s.metadata['pruning']['index'] for s in full] == list(range(6))
    config = configuration(source, panel, prune_ratio=2 / 3, pruning_strategy='response_stratified')
    samples = get_benchmark('live_code_bench_pruned', config).load_dataset()['fixture']
    assert {s.metadata['pruning']['stratum'] for s in samples} == {'pattern:00', 'pattern:01', 'pattern:10', 'pattern:11'}


def test_cli_writes_native_coding_reports_and_selection_provenance(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    config = configuration(source, panel, prune_ratio=0.5)
    args = json.dumps(config.dataset_args)
    result = subprocess.run(
        [sys.executable, '-m', 'evalscope.cli.cli', 'eval', '--model', 'unseen-model',
         '--eval-type', 'mock_llm', '--datasets', 'live_code_bench_pruned',
         '--dataset-args', args, '--work-dir', str(tmp_path / 'run'), '--no-timestamp'],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    report = json.loads((tmp_path / 'run/reports/unseen-model/live_code_bench_pruned.json').read_text(encoding='utf-8'))
    assert report['dataset_name'] == 'live_code_bench_pruned'
    assert any(metric['identity']['aggregation'] == 'weighted_mean' for metric in report['metrics'])
    for kind in ('predictions', 'reviews'):
        paths = list((tmp_path / 'run' / kind).rglob('*.jsonl'))
        rows = [json.loads(line) for line in paths[0].read_text(encoding='utf-8').splitlines()]
        assert len(rows) == 3
        assert all('pruning' in (row.get('metadata') or row.get('sample_score', {}).get('sample_metadata', {})) for row in rows)
    assert (tmp_path / 'run/reports/report.html').is_file()


def test_inherited_coding_grader_executes_and_scores_correct_and_wrong_solutions(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    adapter = get_benchmark('live_code_bench_pruned', configuration(source, panel))
    sample = list(adapter.load_dataset()['fixture'])[0]
    for code, expected in [('print(0)', 1), ('print(999)', 0)]:
        state = TaskState(model='unseen-model', sample=sample,
                          output=ModelOutput.from_content('unseen-model', f'```python\n{code}\n```'),
                          completed=True)
        score = adapter.calculate_metrics(state)
        assert score.score.value['acc'] == expected, score.score.model_dump()
        assert score.sample_metadata is not None
        assert score.sample_metadata['pruning']['index'] == 0


def test_repeated_attempts_have_one_question_weight_and_unavailable_grades_fail(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    config = configuration(source, panel, prune_ratio=0.5)
    config.repeats = 2
    adapter = get_benchmark('live_code_bench_pruned', config)
    samples = list(adapter.load_dataset()['fixture'])
    scores = [SampleScore(
        sample_id=sample.id, group_id=sample.group_id, generation_index=index % 2,
        sample_metadata=sample.metadata, score=Score(value={'acc': index % 2}),
    ) for index, sample in enumerate(samples)]
    estimate = next(s for s in adapter.aggregate_scores(scores) if s.aggregation == 'weighted_mean')
    assert estimate.score == 0.5
    assert estimate.num == 3
    scores[0].score.value = {}
    with pytest.raises(ValueError, match='Incomplete'):
        adapter.aggregate_scores(scores)


def test_openai_compatible_transport_and_real_grading_work_without_external_api_keys(tmp_path: Path) -> None:
    source, panel = population(tmp_path)
    requests: list[dict] = []

    class FixtureEndpoint(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(payload)
            prompt = payload['messages'][-1]['content']
            match = re.search(r'Print (\d+)\.', prompt)
            assert match is not None
            number = match.group(1)
            response = {'id': 'offline-fixture', 'object': 'chat.completion', 'created': 0,
                        'model': 'unseen-model', 'choices': [{'index': 0, 'finish_reason': 'stop',
                            'message': {'role': 'assistant', 'content': f'```python\nprint({number})\n```'}}],
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureEndpoint)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = configuration(source, panel, prune_ratio=0.5)
        result = subprocess.run(
            [sys.executable, '-m', 'evalscope.cli.cli', 'eval', '--model', 'unseen-model',
             '--eval-type', 'openai_api', '--api-url', f'http://127.0.0.1:{server.server_port}/v1',
             '--api-key', 'offline-fixture-only', '--datasets', 'live_code_bench_pruned',
             '--dataset-args', json.dumps(config.dataset_args), '--eval-batch-size', '1',
             '--work-dir', str(tmp_path / 'http-run'), '--no-timestamp'],
            cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    assert len(requests) == 3
    assert all(payload['messages'][0]['role'] == 'system' for payload in requests)
    report_path = tmp_path / 'http-run/reports/unseen-model/live_code_bench_pruned.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    estimate = next(m for m in report['metrics'] if m['identity']['aggregation'] == 'weighted_mean')
    assert estimate['score'] == 1.0
    assert estimate['num'] == 3

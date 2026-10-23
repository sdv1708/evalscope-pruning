"""Behavioral tests of the documented comparison module command."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


def write_run(root: Path, grades: list[int], *, selected: list[int] | None = None) -> Path:
    """Write a small Native-shaped run with independently known expected scores."""
    indices = list(range(len(grades))) if selected is None else selected
    name = 'live_code_bench_pruned'
    (root / 'configs').mkdir(parents=True)
    spec = {'name': name, 'dataset_id': 'fixture', 'subset_list': ['test'], 'extra_params': {}}
    config = {
        'model': 'candidate', 'model_id': 'candidate', 'eval_type': 'mock_llm', 'repeats': 1,
        'generation_config': {}, 'judge': {'strategy': 'rule'}, 'limit': None,
        'resolved_benchmarks': {name: spec},
        'evaluation_identity': {'schema_version': 1, 'benchmarks': {
            name: {'evaluation_version': 'v1.0', 'fingerprint': 'fixture'},
        }},
    }
    (root / 'configs' / 'task_config.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    rows = []
    for execution, index in enumerate(indices):
        trace = {
            'index': index, 'question_sha256': hashlib.sha256(f'q{index}'.encode()).hexdigest(),
            'weight': 1 / len(indices), 'stratum': 'all', 'population_count': len(grades),
            'selected_count': len(indices), 'strategy': 'difficulty_stratified',
            'keep_ratio': len(indices) / len(grades), 'seed': 42,
            'population_size': len(grades), 'selected_size': len(indices),
            'reference_models': ['reference'], 'reference_panel_sha256': 'a' * 64,
        }
        rows.append({
            'index': execution, 'messages': [{'role': 'user', 'content': f'q{index}'}], 'target': None,
            'sample_score': {'sample_id': execution, 'group_id': execution, 'generation_index': 0,
                             'score': {'value': {'acc': grades[index]}, 'status': 'success'},
                             'sample_metadata': {'pruning': trace}},
        })
    reviews = root / 'reviews' / 'candidate'
    reviews.mkdir(parents=True)
    (reviews / f'{name}_test.jsonl').write_text('\n'.join(map(json.dumps, rows)) + '\n', encoding='utf-8')
    score = sum(grades[index] for index in indices) / len(indices)
    identity = {'name': 'accuracy', 'aggregation': 'weighted_mean', 'dimensions': {'scope': 'population'}}
    report = {
        'schema_version': 2, 'dataset_name': name, 'model_name': 'candidate',
        'metrics': [{'identity': identity, 'num': len(indices), 'score': round(score, 4),
                     'categories': [{'name': ['default'], 'subsets': [
                         {'name': 'test', 'num': len(indices), 'score': round(score, 4)},
                     ]}]}],
        'execution_summary': {'requested': len(indices), 'succeeded': len(indices), 'errored': 0,
                              'incomplete': False},
    }
    reports = root / 'reports' / 'candidate'
    reports.mkdir(parents=True)
    (reports / f'{name}.json').write_text(json.dumps(report), encoding='utf-8')
    return root


def invoke(full: Path, pruned: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """Exercise the installed module boundary in a separate Python process."""
    return subprocess.run(
        [sys.executable, '-m', 'evalscope_ext.tools.compare_runs', '--full', str(full),
         '--pruned', str(pruned), *extra], capture_output=True, text=True, timeout=30,
    )


def test_reports_counts_weighted_difference_and_conservative_decision(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0, 1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0, 1, 0], selected=[0, 2])
    result = invoke(full, pruned, '--threshold', '0.6')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    comparison = report['comparisons'][0]
    assert comparison['full_samples'] == 4
    assert comparison['pruned_samples'] == 2
    assert comparison['full_score'] == 0.5
    assert comparison['pruned_score'] == 1.0
    assert comparison['difference_pp'] == 50.0
    assert comparison['decision']['full'] == 'NO GO'
    assert comparison['decision']['pruned'] == 'inconclusive'
    assert comparison['finite_pool_bounds'] == [0.5, 1.0]
    assert report['warnings']


def test_full_retention_is_exact_and_threshold_equality_is_go(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0])
    result = invoke(full, pruned, '--threshold', '0.5')
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)['comparisons'][0]
    assert row['difference_pp'] == 0
    assert row['finite_pool_bounds'] == [0.5, 0.5]
    assert row['decision']['pruned'] == 'GO'


def test_missing_run_has_actionable_diagnostic(tmp_path: Path) -> None:
    result = invoke(tmp_path / 'absent', tmp_path / 'also-absent')
    assert result.returncode == 2
    assert 'reports' in result.stderr and 'Traceback' not in result.stderr


def test_incompatible_generation_settings_fail(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0])
    path = pruned / 'configs' / 'task_config.yaml'
    config = yaml.safe_load(path.read_text())
    config['generation_config'] = {'temperature': 0.8}
    path.write_text(yaml.safe_dump(config), encoding='utf-8')
    result = invoke(full, pruned)
    assert result.returncode == 2
    assert 'generation_config' in result.stderr


def test_weights_correct_unequal_strata_instead_of_using_subset_mean(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [0, 0, 1, 1, 1, 1, 1, 1])
    pruned = write_run(tmp_path / 'pruned', [0, 0, 1, 1, 1, 1, 1, 1], selected=[0, 2])
    for root in (full, pruned):
        path = root / 'reviews/candidate/live_code_bench_pruned_test.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            trace = row['sample_score']['sample_metadata']['pruning']
            small = trace['index'] < 2
            trace['stratum'] = 'small' if small else 'large'
            trace['population_count'] = 2 if small else 6
            trace['selected_count'] = (2 if small else 6) if root == full else 1
            trace['weight'] = 1 / 8 if root == full else (0.25 if small else 0.75)
        path.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
        report_path = root / 'reports/candidate/live_code_bench_pruned.json'
        report = json.loads(report_path.read_text())
        report['metrics'][0]['score'] = 0.75
        report['metrics'][0]['categories'][0]['subsets'][0]['score'] = 0.75
        report_path.write_text(json.dumps(report), encoding='utf-8')
    result = invoke(full, pruned)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)['comparisons'][0]
    assert row['raw_pruned_mean'] == 0.5
    assert row['pruned_score'] == row['full_score'] == 0.75
    assert row['difference_pp'] == 0


@pytest.mark.parametrize('damage,diagnostic', [
    ('missing_reviews', 'jsonl'), ('mismatched_model', 'model'),
    ('mismatched_input', 'not found'), ('partial_full', 'complete population'),
    ('invalid_weight', 'weights'), ('missing_question', 'selected questions'),
    ('failed_grade', 'failed'), ('bad_json', 'invalid JSON'),
    ('duplicate_json_key', 'Duplicate JSON key'), ('bad_report_score', 'score mismatch'),
    ('incomplete_execution', 'execution_summary'), ('duplicate_attempt', 'duplicate'),
    ('wrong_revision', 'resolved_benchmark'), ('wrong_judge', 'judge'),
    ('wrong_panel', 'reference_panel_sha256'), ('wrong_stratum', 'strata'),
])
def test_invalid_evidence_fails_before_publishing(tmp_path: Path, damage: str, diagnostic: str) -> None:
    full = write_run(tmp_path / 'full', [1, 0, 1, 0], selected=[0, 1] if damage == 'partial_full' else None)
    pruned = write_run(tmp_path / 'pruned', [1, 0, 1, 0], selected=[0, 1])
    review = pruned / 'reviews/candidate/live_code_bench_pruned_test.jsonl'
    report_path = pruned / 'reports/candidate/live_code_bench_pruned.json'
    config_path = pruned / 'configs/task_config.yaml'
    rows = [json.loads(line) for line in review.read_text().splitlines()]
    if damage == 'missing_reviews':
        review.unlink()
    elif damage == 'mismatched_model':
        report = json.loads(report_path.read_text())
        report['model_name'] = 'other'
        report_path.write_text(json.dumps(report), encoding='utf-8')
    elif damage == 'mismatched_input':
        rows[0]['messages'][0]['content'] = 'wrong source question'
    elif damage == 'invalid_weight':
        rows[0]['sample_score']['sample_metadata']['pruning']['weight'] = 0.25
    elif damage == 'missing_question':
        rows.pop()
    elif damage == 'failed_grade':
        rows[0]['sample_score']['score']['status'] = 'parse_error'
    elif damage == 'bad_json':
        review.write_text('{broken', encoding='utf-8')
    elif damage == 'duplicate_json_key':
        review.write_text('{"index": 0, "index": 1}', encoding='utf-8')
    elif damage == 'bad_report_score':
        report = json.loads(report_path.read_text())
        report['metrics'][0]['categories'][0]['subsets'][0]['score'] = 0.9
        report_path.write_text(json.dumps(report), encoding='utf-8')
    elif damage == 'incomplete_execution':
        report = json.loads(report_path.read_text())
        report['execution_summary']['incomplete'] = True
        report_path.write_text(json.dumps(report), encoding='utf-8')
    elif damage == 'duplicate_attempt':
        rows.append(rows[0])
    elif damage in ('wrong_revision', 'wrong_judge'):
        config = yaml.safe_load(config_path.read_text())
        if damage == 'wrong_revision':
            config['resolved_benchmarks']['live_code_bench_pruned']['dataset_revision'] = 'other'
        else:
            config['judge'] = {'strategy': 'llm', 'models': [{'model_id': 'different-judge'}]}
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
    elif damage == 'wrong_panel':
        for row in rows:
            row['sample_score']['sample_metadata']['pruning']['reference_panel_sha256'] = 'b' * 64
    elif damage == 'wrong_stratum':
        for row in rows:
            row['sample_score']['sample_metadata']['pruning']['population_count'] = 3
    if damage in {'mismatched_input', 'invalid_weight', 'missing_question', 'failed_grade',
                  'duplicate_attempt', 'wrong_panel', 'wrong_stratum'}:
        review.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
    result = invoke(full, pruned)
    assert result.returncode == 2, result.stdout
    assert diagnostic in result.stderr
    assert not result.stdout
    assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('threshold', ['nan', 'inf', '-0.1', '1.1'])
def test_invalid_threshold_is_rejected(tmp_path: Path, threshold: str) -> None:
    result = invoke(tmp_path / 'full', tmp_path / 'pruned', '--threshold', threshold)
    assert result.returncode == 2
    assert 'threshold' in result.stderr


def test_repeated_attempts_do_not_inflate_unique_question_count(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0])
    for root in (full, pruned):
        config_path = root / 'configs/task_config.yaml'
        config = yaml.safe_load(config_path.read_text())
        config['repeats'] = 2
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
        review = root / 'reviews/candidate/live_code_bench_pruned_test.jsonl'
        rows = [json.loads(line) for line in review.read_text().splitlines()]
        repeated: list[dict[str, Any]] = []
        for row in rows:
            for position in (0, 1):
                attempt = json.loads(json.dumps(row))
                attempt['index'] = len(repeated)
                attempt['sample_score']['sample_id'] = len(repeated)
                attempt['sample_score']['generation_index'] = position
                repeated.append(attempt)
        review.write_text('\n'.join(map(json.dumps, repeated)), encoding='utf-8')
        report_path = root / 'reports/candidate/live_code_bench_pruned.json'
        report = json.loads(report_path.read_text())
        report['execution_summary'].update(requested=4, succeeded=4)
        report_path.write_text(json.dumps(report), encoding='utf-8')
    result = invoke(full, pruned)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)['comparisons'][0]
    assert row['full_samples'] == row['pruned_samples'] == 2
    assert row['full_attempts'] == row['pruned_attempts'] == 4


def test_ordering_uses_multiple_run_roots_and_preserves_ties(tmp_path: Path) -> None:
    full_a = write_run(tmp_path / 'full-a', [1, 0])
    pruned_a = write_run(tmp_path / 'pruned-a', [1, 0])
    full_b = write_run(tmp_path / 'full-b', [1, 1])
    pruned_b = write_run(tmp_path / 'pruned-b', [1, 0])
    for root in (full_b, pruned_b):
        config_path = root / 'configs/task_config.yaml'
        config = yaml.safe_load(config_path.read_text())
        config.update(model='second', model_id='second')
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
        for folder in ('reports', 'reviews'):
            (root / folder / 'candidate').rename(root / folder / 'second')
        report_path = root / 'reports/second/live_code_bench_pruned.json'
        report = json.loads(report_path.read_text())
        report['model_name'] = 'second'
        report_path.write_text(json.dumps(report), encoding='utf-8')
    result = invoke(full_a, pruned_a, '--full', str(full_a), str(full_b),
                    '--pruned', str(pruned_a), str(pruned_b))
    assert result.returncode == 0, result.stderr
    pair = json.loads(result.stdout)['ordering'][0]
    assert pair['full_difference_pp'] == -50
    assert pair['pruned_difference_pp'] == 0
    assert pair['ordering_preserved'] is False


def test_unpruned_full_adapter_matches_by_input_not_row_position(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0, 1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0, 1, 0], selected=[1, 3])
    old_name = 'live_code_bench_pruned'
    name = 'live_code_bench'
    config_path = full / 'configs/task_config.yaml'
    config = yaml.safe_load(config_path.read_text())
    config['resolved_benchmarks'][name] = config['resolved_benchmarks'].pop(old_name)
    config['resolved_benchmarks'][name]['name'] = name
    config['evaluation_identity']['benchmarks'][name] = config['evaluation_identity']['benchmarks'].pop(old_name)
    config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
    review = full / f'reviews/candidate/{old_name}_test.jsonl'
    rows = [json.loads(line) for line in review.read_text().splitlines()]
    for row in rows:
        row['sample_score']['sample_metadata'] = {}
    review.unlink()
    review.with_name(f'{name}_test.jsonl').write_text('\n'.join(map(json.dumps, reversed(rows))), encoding='utf-8')
    report_path = full / f'reports/candidate/{old_name}.json'
    report = json.loads(report_path.read_text())
    report['dataset_name'] = name
    report['metrics'][0]['identity'] = {'name': 'accuracy', 'aggregation': 'pass_at_k', 'dimensions': {'k': 1}}
    report_path.unlink()
    report_path.with_name(f'{name}.json').write_text(json.dumps(report), encoding='utf-8')
    result = invoke(full, pruned)
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output['comparisons'][0]['difference_pp'] == -50
    assert any('population identity cannot be proven' in warning for warning in output['warnings'])


def test_null_score_metadata_is_valid_and_aa_lcr_warns_about_judge_noise(tmp_path: Path) -> None:
    full = write_run(tmp_path / 'full', [1, 0])
    pruned = write_run(tmp_path / 'pruned', [1, 0])
    for root in (full, pruned):
        for path in list(root.rglob('*')):
            if path.suffix not in ('.yaml', '.json', '.jsonl'):
                continue
            content = path.read_text().replace('live_code_bench_pruned', 'aa_lcr_pruned')
            if path.suffix == '.jsonl':
                rows = [json.loads(line) for line in content.splitlines()]
                for row in rows:
                    row['sample_score']['score']['metadata'] = None
                content = '\n'.join(map(json.dumps, rows))
            path.write_text(content, encoding='utf-8')
            if 'live_code_bench_pruned' in path.name:
                path.rename(path.with_name(path.name.replace('live_code_bench_pruned', 'aa_lcr_pruned')))
    result = invoke(full, pruned)
    assert result.returncode == 0, result.stderr
    assert any('judge noise' in warning for warning in json.loads(result.stdout)['warnings'])

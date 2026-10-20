"""Exercise pruning through EvalScope's public registry and dataset pipeline."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evalscope.api.registry import get_benchmark
from evalscope.config import TaskConfig


def write_population(path: Path, rows: list[dict[str, str]]) -> None:
    """Write synthetic input through the same JSONL format used by the CLI."""
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def fixture_rows() -> list[dict[str, str]]:
    """Read the bundled input through its registered public dataset location."""
    source = Path(get_benchmark('pruning_smoke').dataset_id) / 'smoke_test.jsonl'
    return [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]


def test_registered_smoke_dataset_retains_every_stratum() -> None:
    adapter = get_benchmark('pruning_smoke', TaskConfig(datasets=['pruning_smoke']))
    dataset = adapter.load_dataset()['smoke']

    assert len(dataset) == 3
    assert {sample.metadata['stratum'] for sample in dataset} == {'easy', 'medium', 'hard'}
    assert len({sample.metadata['record_id'] for sample in dataset}) == 3


@pytest.mark.parametrize('keep', [0, -1, True, 1.5, '1', None])
def test_invalid_allocation_is_rejected_during_configuration(keep: object) -> None:
    config = TaskConfig(
        datasets=['pruning_smoke'],
        dataset_args={'pruning_smoke': {'extra_params': {'keep_per_stratum': keep}}},
    )
    with pytest.raises(ValueError, match='keep_per_stratum'):
        get_benchmark('pruning_smoke', config)


def test_duplicate_question_ids_fail_instead_of_silently_resampling(tmp_path: Path) -> None:
    rows = fixture_rows()
    rows[1]['record_id'] = rows[0]['record_id']
    source = tmp_path / 'duplicate.jsonl'
    write_population(source, rows)
    config = TaskConfig(
        datasets=['pruning_smoke'],
        dataset_args={'pruning_smoke': {'local_path': str(source)}},
    )
    with pytest.raises(ValueError, match='Duplicate.*easy-1'):
        get_benchmark('pruning_smoke', config).load_dataset()


def test_reordering_input_does_not_change_selected_original_questions(tmp_path: Path) -> None:
    config = TaskConfig(datasets=['pruning_smoke'], seed=42)
    expected = get_benchmark('pruning_smoke', config).load_dataset()['smoke']
    source = tmp_path / 'reversed.jsonl'
    write_population(source, fixture_rows()[::-1])
    reordered = TaskConfig(
        datasets=['pruning_smoke'], seed=42,
        dataset_args={'pruning_smoke': {'local_path': str(source)}},
    )
    actual = get_benchmark('pruning_smoke', reordered).load_dataset()['smoke']

    assert [s.metadata['record_id'] for s in actual] == [s.metadata['record_id'] for s in expected]


@pytest.mark.parametrize(('limit', 'count'), [(None, 6), (1, 2), (0.5, 2), (0, 6)])
def test_limits_apply_after_selection_and_before_repeated_attempts(limit: int | float | None, count: int) -> None:
    config = TaskConfig(datasets=['pruning_smoke'], limit=limit, repeats=2)
    configured_limit = config.limit  # Upstream normalizes 0 to unlimited (None).
    adapter = get_benchmark('pruning_smoke', config)
    dataset = adapter.load_dataset()['smoke']

    assert len(dataset) == count
    assert [s.id for s in dataset] == list(range(count))
    assert [s.group_id for s in dataset] == [0, 0, 1, 1, 2, 2][:count]
    assert config.limit == configured_limit
    assert config.repeats == 2
    samples = list(dataset)
    for first, second in zip(samples[::2], samples[1::2]):
        assert first.metadata['record_id'] == second.metadata['record_id']
        assert first is not second


def test_increasing_allocation_can_retain_the_complete_toy_population() -> None:
    config = TaskConfig(
        datasets=['pruning_smoke'],
        dataset_args={'pruning_smoke': {'extra_params': {'keep_per_stratum': 2}}},
    )
    dataset = get_benchmark('pruning_smoke', config).load_dataset()['smoke']
    assert len(dataset) == 6
    assert {s.metadata['record_id'] for s in dataset} == {
        'easy-1', 'easy-2', 'medium-1', 'medium-2', 'hard-1', 'hard-2',
    }


def test_bad_metadata_fails_instead_of_being_dropped_from_the_population(tmp_path: Path) -> None:
    rows = fixture_rows()
    rows[0]['stratum'] = ''
    source = tmp_path / 'malformed.jsonl'
    write_population(source, rows)
    config = TaskConfig(
        datasets=['pruning_smoke'],
        dataset_args={'pruning_smoke': {'local_path': str(source)}},
    )
    with pytest.raises(ValueError, match='stratum'):
        get_benchmark('pruning_smoke', config).load_dataset()


def test_cli_discovers_benchmark_and_writes_standard_evaluation_artifacts(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, '-m', 'evalscope.cli.cli', 'eval',
         '--model', 'pruning-smoke-mock', '--eval-type', 'mock_llm',
         '--datasets', 'pruning_smoke', '--work-dir', str(tmp_path), '--no-timestamp'],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    report_path = tmp_path / 'reports' / 'pruning-smoke-mock' / 'pruning_smoke.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['dataset_name'] == 'pruning_smoke'
    assert report['metrics'][0]['num'] == 3
    assert report['metrics'][0]['score'] == 0.0
    assert (tmp_path / 'reports' / 'report.html').is_file()
    for kind in ('predictions', 'reviews'):
        files = list((tmp_path / kind).rglob('*.jsonl'))
        assert len(files) == 1
        assert len(files[0].read_text(encoding='utf-8').splitlines()) == 3

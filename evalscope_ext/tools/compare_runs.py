"""Compare full and pruned Native Part A runs without inference or judge calls."""

import argparse
import json
import math
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

from evalscope_ext.tools.saved_runs import SavedRun, load_runs


def _decision(lower: float, upper: float, threshold: float) -> str:
    if lower >= threshold:
        return 'GO'
    if upper < threshold:
        return 'NO GO'
    return 'inconclusive'


def _compatible(full: SavedRun, pruned: SavedRun) -> None:
    if full.settings != pruned.settings:
        fields = sorted(
            key
            for key in full.settings.keys() | pruned.settings.keys()
            if full.settings.get(key) != pruned.settings.get(key)
        )
        raise ValueError(
            f'Incompatible runs for {full.model}/{full.benchmark}: settings differ: {fields}. '
            'Regenerate both runs with the same model, generation, judge and source settings.'
        )
    if full.population_size != full.samples or pruned.population_size != full.samples:
        raise ValueError(
            'Population mismatch: --full must contain the complete population; '
            'use the same reference panel at prune_ratio=1.0 and remove limit.'
        )
    for key, question in pruned.questions.items():
        if key not in full.questions:
            raise ValueError(
                'Pruned question/input/target not found in full run. Check source revision, '
                'document order, prompt and subset; execution row indices are not identities.'
            )
        original = full.questions[key]
        if original.trace is not None and question.trace is not None:
            for field in (
                'index',
                'question_sha256',
                'stratum',
                'population_count',
                'reference_panel_sha256',
                'strategy',
                'reference_models',
            ):
                if original.trace[field] != question.trace[field]:
                    raise ValueError(f'Incompatible pruning provenance: {field}. Use the same panel and strategy.')


def compare(full: SavedRun, pruned: SavedRun, threshold: Optional[float]) -> dict[str, Any]:
    """Return observed fidelity and deterministic bounds on the fixed recorded pool."""
    _compatible(full, pruned)
    # Unobserved question means may be anywhere in [0,1]; no randomness assumption.
    lower = math.fsum(q.mean for q in pruned.questions.values()) / full.samples
    upper = min(1.0, lower + (full.samples - pruned.samples) / full.samples)
    decision = None
    if threshold is not None:
        full_decision = _decision(full.score, full.score, threshold)
        pruned_decision = _decision(lower, upper, threshold)
        decision = {
            'threshold': threshold,
            'full': full_decision,
            'pruned': pruned_decision,
            'observed_pruned_point': _decision(pruned.score, pruned.score, threshold),
            'agreement': full_decision == pruned_decision,
            'decision_certified': False,
        }
    return {
        'model': full.model,
        'benchmark': full.benchmark,
        'subset': full.subset,
        'full_samples': full.samples,
        'pruned_samples': pruned.samples,
        'full_attempts': full.attempts,
        'pruned_attempts': pruned.attempts,
        'retained_fraction': pruned.samples / full.samples,
        'full_score': full.score,
        'pruned_score': pruned.score,
        'raw_pruned_mean': pruned.raw_mean,
        'difference_pp': 100 * (pruned.score - full.score),
        'absolute_error_pp': 100 * abs(pruned.score - full.score),
        'finite_pool_bounds': [lower, upper],
        'paired_question_mae': math.fsum(abs(q.mean - full.questions[key].mean) for key, q in pruned.questions.items())
        / pruned.samples,
        'decision': decision,
    }


def _ordering(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for left, right in combinations(rows, 2):
        if (left['benchmark'], left['subset']) != (right['benchmark'], right['subset']):
            continue
        full_delta = left['full_score'] - right['full_score']
        pruned_delta = left['pruned_score'] - right['pruned_score']
        sign_full = 0 if abs(full_delta) <= 1e-12 else (1 if full_delta > 0 else -1)
        sign_pruned = 0 if abs(pruned_delta) <= 1e-12 else (1 if pruned_delta > 0 else -1)
        result.append(
            {
                'benchmark': left['benchmark'],
                'subset': left['subset'],
                'left_model': left['model'],
                'right_model': right['model'],
                'full_difference_pp': full_delta * 100,
                'pruned_difference_pp': pruned_delta * 100,
                'ordering_preserved': sign_full == sign_pruned,
                'ties_count_as_distinct': True,
            }
        )
    return result


def main() -> int:
    """Write one JSON document to stdout, or an actionable error to stderr (exit 2)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', required=True, type=Path, nargs='+', help='One or more exact full run roots.')
    parser.add_argument('--pruned', required=True, type=Path, nargs='+', help='One or more exact pruned run roots.')
    parser.add_argument('--threshold', type=float, help='Illustrative minimum accuracy in [0,1], inclusive.')
    args = parser.parse_args()
    try:
        if args.threshold is not None and (not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1):
            raise ValueError('--threshold must be finite and in [0,1].')
        full = _load_many(args.full)
        pruned = _load_many(args.pruned)
        if full.keys() != pruned.keys():
            raise ValueError(
                'Mismatched model/benchmark/subset keys. Supply matching complete run directories; '
                f'full-only={sorted(full.keys() - pruned.keys())}, '
                f'pruned-only={sorted(pruned.keys() - full.keys())}.'
            )
        rows = [compare(full[key], pruned[key], args.threshold) for key in sorted(full)]
        warnings = [
            'Observed saved-run fidelity is retrospective; it does not validate transfer to an unseen model.',
            'Bounds cover only unobserved grades in this fixed pool, not generation or judge randomness, '
            'future tasks, or a production GO guarantee.',
        ]
        if any(row['retained_fraction'] == 1 for row in rows):
            warnings.append('Full retention: no sample-count saving is demonstrated.')
        if any(row['benchmark'] == 'aa_lcr' for row in rows):
            warnings.append(
                'AA-LCR judge noise is unidentifiable from one saved verdict per answer; '
                'a census does not remove judge uncertainty.'
            )
        if any(row['paired_question_mae'] > 0 for row in rows):
            warnings.append(
                'Overlapping question grades changed between runs. Bounds describe possible '
                'completions of the pruned run, not the independently generated full-run grades.'
            )
        ordering = _ordering(rows)
        if not ordering:
            warnings.append('Ordering unavailable: provide at least two matching models per benchmark/subset.')
        if args.threshold is None:
            warnings.append('No threshold supplied: customer GO/NO GO evidence is unavailable.')
        if any(run.legacy_full for run in full.values()):
            warnings.append(
                'Unpruned adapter input matched by prompt and target. The complete historical '
                'population identity cannot be proven without full-run pruning traces; '
                'prefer the reference adapter at prune_ratio=1.0.'
            )
        output = {
            'schema_version': 1,
            'comparisons': rows,
            'ordering': ordering,
            'warnings': warnings,
            'sources': {
                'full': [str(path) for path in sorted({p for r in full.values() for p in r.sources})],
                'pruned': [str(path) for path in sorted({p for r in pruned.values() for p in r.sources})],
            },
        }
        print(json.dumps(output, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print(f'compare_runs: {error}', file=sys.stderr)
        return 2
    return 0


def _load_many(roots: list[Path]) -> dict[tuple[str, str, str], SavedRun]:
    runs: dict[tuple[str, str, str], SavedRun] = {}
    for root in roots:
        incoming = load_runs(root)
        if runs.keys() & incoming.keys():
            raise ValueError(f'{root}: duplicate model/benchmark/subset across supplied run roots.')
        runs.update(incoming)
    return runs


if __name__ == '__main__':
    raise SystemExit(main())

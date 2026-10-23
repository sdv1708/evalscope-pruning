# Comparing full and pruned Native runs (issue #21)

From this fork, developed against upstream
`66f0945d145ce6c30de40253cd78144003c6f1fe`, run:

```powershell
.venv/Scripts/python.exe -m evalscope_ext.tools.compare_runs --full results_full --pruned results_pruned --threshold 0.7
```

The module is packaged with EvalScope (`evalscope*` package discovery includes
`evalscope_ext`). It reads files only: no inference, judge, downloads or credentials.
Python 3.10+ is supported; verification used 3.12.8. `--threshold` is optional,
finite and within [0,1]. It is a caller's minimum acceptable accuracy, never an
inferred customer requirement. Equality meets the threshold.

## Reproduce the complete workflow without credentials

Install this fork with `python -m pip install -e .`. From its root:

```powershell
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/comparison-smoke
python -m evalscope_ext.tools.compare_runs --full outputs/comparison-smoke/full --pruned outputs/comparison-smoke/pruned --threshold 0.8 > comparison.json
```

The first command starts a loopback-only OpenAI-compatible model/judge fixture,
runs the real EvalScope CLI twice and then invokes the comparison module. The
full run retains all 12 synthetic questions; the pruned run retains 3. Both score
1.0, their difference is 0 percentage points, and the pruned completion bounds are
[0.25,1.0]. At an 80% threshold the full recorded run says GO and the subset is
inconclusive. This proves the workflow, not any model's quality or safe compression.

## Real coding evaluation contract

Use the source, reference panel and sandbox setup in
[LIVE_CODE_BENCH_PRUNED.md](LIVE_CODE_BENCH_PRUNED.md). Set `EVAL_MODEL`,
`EVAL_API_URL`, `EVAL_API_KEY` and `LCB_REFERENCE_PANEL` first. Fresh evaluation
incurs endpoint/grading costs; it was not performed for this ticket.

```powershell
$datasetArgs = @{live_code_bench_pruned = @{subset_list = @('release_v5'); extra_params = @{pruning_strategy = 'difficulty_stratified'; prune_ratio = 1.0; reference_path = $env:LCB_REFERENCE_PANEL}}} | ConvertTo-Json -Depth 5 -Compress
python -m evalscope.cli.cli eval --model $env:EVAL_MODEL --eval-type openai_api --api-url $env:EVAL_API_URL --api-key $env:EVAL_API_KEY --datasets live_code_bench_pruned --dataset-hub huggingface --dataset-args $datasetArgs --sandbox '{"enabled":true}' --seed 42 --no-timestamp --work-dir results_full
$datasetArgs = @{live_code_bench_pruned = @{subset_list = @('release_v5'); extra_params = @{pruning_strategy = 'difficulty_stratified'; prune_ratio = 0.5; reference_path = $env:LCB_REFERENCE_PANEL}}} | ConvertTo-Json -Depth 5 -Compress
python -m evalscope.cli.cli eval --model $env:EVAL_MODEL --eval-type openai_api --api-url $env:EVAL_API_URL --api-key $env:EVAL_API_KEY --datasets live_code_bench_pruned --dataset-hub huggingface --dataset-args $datasetArgs --sandbox '{"enabled":true}' --seed 42 --no-timestamp --work-dir results_pruned
python -m evalscope_ext.tools.compare_runs --full results_full --pruned results_pruned --threshold 0.7
```

Use fresh output directories. The second ratio is experimental. The defended
production fallback remains 1.0 for both Part A benchmarks. At 1.0 there is no
sample saving. The full and pruned runs deliberately use the same reference adapter:
at 1.0 it evaluates the entire frozen population, preserves identity, and (for
AA-LCR) preserves document order. See [AA_LCR_PRUNED.md](AA_LCR_PRUNED.md) for
the equivalent judge configuration and pinned real AA-LCR source setup.

The task brief's `--output` is conceptual syntax; this pinned framework's actual
flag is `--work-dir`. Its dataset arguments must be nested by benchmark name
and pruning settings belong under `extra_params`. `--no-timestamp` makes these
exact directory arguments reproducible. Without it, pass the actual timestamped
run directory, never its parent. The original `live_code_bench` and `aa_lcr` full
adapters are accepted only when source, prompt, target, settings and count match;
their missing population traces trigger an explicit provenance warning. A default
880-question coding source cannot replace the 315-question historical population.

## Evidence contract

Each exact run root must contain `configs/task_config.yaml`,
`reports/<model>/<benchmark>.json` and
`reviews/<model>/<benchmark>_<subset>.jsonl`. Reports must use Native schema 2,
with generated resolved benchmark settings, evaluation version and a complete
execution summary. Historical challenge `Evals/` files alone are not Native runs.

Supported benchmarks are `live_code_bench[_pruned]` and `aa_lcr[_pruned]`.
The pruned side requires native pruning traces. The full side must contain
the entire matching population with no `limit`. Other benchmark reports in the
same root are rejected. Use separate roots rather than mixing unrelated results.

The loader checks report/review counts and scores, unique execution IDs, complete
repetition positions, binary successful grades, selection identity, covered strata,
population sizes, retained counts, ratio and weights. Failed/degraded grades are
rejected rather than converted to zero. Each retained question must have identical
input messages, target and coding grading test cases in the full run; generated answers and ephemeral message
IDs do not define input identity. Original panel identity and stratum metadata must
also match when both sides carry traces. Missing evidence cannot be silently dropped.

Model, generation, judge, source revision, prompt, filtering, evaluation version,
sandbox and repeat settings must match within a pair. Selection ratio, local panel
path, document directory, declared primary metric and shuffle may differ; input
content and panel hashes still have to match. Secrets are excluded from settings
comparison and are never emitted. Fingerprints intentionally differ with pruning;
requiring identical complete cache fingerprints would reject valid comparisons.

JSON is written to stdout only after all pairs validate; warnings live in that
JSON. Errors go to stderr with exit 2 and no partial JSON. Exit 0 means the
comparison completed, not that the customer received GO. Source file paths are
included for audit. `> comparison.json` is ordinary shell redirection.

## Scores, bounds and ordering

For stratum h, population size `N_h`, retained size `n_h`, total population N:
each retained question has weight `N_h/(N*n_h)`. Average its repeated binary
attempts first, then sum `weight * question_mean`. This is mean-attempt accuracy,
not pass@k for k>1. The command recomputes scores from reviews at full precision
and reconciles the framework's four-decimal subset/category/metric rounding in saved reports.

Output includes unique sample and attempt counts, retained fraction, full and
weighted pruned scores, raw subset mean, signed/absolute difference in percentage
points, paired question MAE, optional threshold evidence and warnings. Scores use
the [0,1] scale: 0.75 means 75%; a move from 0.70 to 0.75 is +5 percentage points.

No confidence level or probability sampling assumption is invented. If selected
question means sum to S and n of N questions are observed, deterministic completion
bounds are `[S/N, (S+N-n)/N]`. They assign each unobserved question any mean in
[0,1]. These deliberately conservative bounds are separate from the design-weighted
point estimate. If overlapping grades differ across independent runs, the bounds
describe possible completions of the pruned run, not the recorded full run.

GO requires the entire bound at/above the threshold; NO GO requires the entire
bound below it; otherwise the result is inconclusive. The point-only decision
is also shown but is not certified. Even a census is conditional on recorded
grades: it does not measure future-task transfer, generation variation or AA-LCR
judge error. `decision_certified` remains false.

To inspect ordering, provide one exact run per model:

```powershell
python -m evalscope_ext.tools.compare_runs --full full_model_a full_model_b --pruned pruned_model_a pruned_model_b
```

Keys must match exactly across sides. Duplicate keys fail. Across models, full
input populations and generation/judge/scoring protocols must match before ranking.
Pairwise model order
is reported separately within each benchmark/subset, with ties distinct from
strict order (absolute tie tolerance 1e-12). One model cannot establish ordering.
Ordering is retrospective and may use model-specific selections; it does not
replace independent model-pair holdout experiments from issues #15–#17.

## Research and checks

Sources checked before implementation: the pinned `CacheManager`/`ReviewResult`,
`SampleScore`, `Report`, evaluation-identity serialization and shared native
pruning aggregation; the actual `eval --help`; and official
[saved-run structure](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html)
and [judge/parameter semantics](https://evalscope.readthedocs.io/en/v1.14.0/get_started/parameters.html).
The pinned local code is the source of truth when rolling documentation differs.

Run `python -m pytest tests/tools/test_compare_runs.py` for the public command
regressions, and see [VALIDATION_ISSUE_21.md](VALIDATION_ISSUE_21.md) for measured
integration, quality and packaging checks.

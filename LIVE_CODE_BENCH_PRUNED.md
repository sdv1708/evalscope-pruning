# Native LiveCodeBench pruning — issue #19

`live_code_bench_pruned` runs historical stratified selection inside EvalScope
before inference. It inherits `LiveCodeBenchAdapter`: original prompts, starter
code, date filtering, code extraction, local/sandbox grading, repeated attempts,
caching and ordinary reports remain in use.

Upstream base: **`66f0945d145ce6c30de40253cd78144003c6f1fe`**. This branch
includes the issue #18 baseline `152d811484e0c3ad3d9329af9befb73e961d8872` on top
of private main. The public Hugging Face dataset is pinned to
`e70df9620dd54c12afac5e2881355de6f9ece2e9` in benchmark metadata.

## Install and run offline

Use the Python 3.12 environment in [PRUNING_BASELINE.md](PRUNING_BASELINE.md).
The adapter needs no additional runtime dependency. From this repository root:

```powershell
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info live_code_bench_pruned
.venv/Scripts/python.exe -c "from evalscope import run_task; run_task('examples/live_code_bench_pruned/task.json')"
.venv/Scripts/python.exe -m pytest tests/api/test_live_code_bench_pruned.py --basetemp=.pytest-tmp/coding
```

The example has six synthetic coding questions, a two-model historical panel and
a mock model. It selects three questions, uses LiveCodeBench grading, and writes
predictions, reviews, JSON and HTML reports. Zero accuracy is expected from the
mock model's fixed non-code answer. This tests integration, not model quality.

Python's local multiprocessing workers must be allowed to start. In a restricted
Windows process sandbox even a correct fixed `print(0)` program can receive an
upstream grader failure. Run the correct/wrong-program regression with worker
creation enabled. Use the upstream code sandbox for generated model programs.

## Dataset arguments

Use EvalScope's actual per-dataset configuration structure:

```json
{
  "live_code_bench_pruned": {
    "subset_list": ["release_v5"],
    "extra_params": {
      "pruning_strategy": "difficulty_stratified",
      "prune_ratio": 1.0,
      "reference_path": "path/to/lcb-reference-panel.json",
      "excluded_reference_models": []
    }
  }
}
```

| Parameter | Meaning |
| --- | --- |
| `pruning_strategy` | `difficulty_stratified` (default) or `response_stratified` |
| `prune_ratio` | Fraction **retained** in `(0, 1]`; count is `ceil(N * ratio)` |
| `reference_path` | Required at load time: local frozen historical panel JSON |
| `excluded_reference_models` | Additional historical names to exclude, e.g. the second member of a pair holdout |
| Task `seed` | Integer for reproducible hash priorities |
| `local_path` | Optional JSONL/CSV/TSV/parquet mirror with original raw LCB fields |
| Inherited `start_date`, `end_date`, `debug` | Ordinary LiveCodeBench options in `extra_params` |

The task's actual model name and display model ID are automatically excluded when
present in the panel. For an alias also put its canonical historical name in
`excluded_reference_models`. At least one reference must remain. A fourth model
requires no target grades for selection. Forbidden comparison-only names
`uniform_random`, `easiest_only` and `hardest_only` are rejected.

Flat top-level pruning arguments are not the native dataset-args format.
`--limit` is rejected because truncation invalidates the population weights.
Shuffle changes execution order only; repeats duplicate selected questions later.

## Frozen identity and exact selection

Panel schema version 1 contains `tasks`, each with a nonnegative analysis `index`,
a 64-character lowercase `question_sha256`, and `scores` mapping historical model
names to binary integer grades. Optional `provenance` records source information.
See `examples/live_code_bench_pruned/data/references.json` for a complete example.

Fingerprint UTF-8 `question_content` after normalizing CRLF/CR to LF and stripping
outer whitespace. Current file row positions and fresh execution IDs never replace
the original analysis index. Duplicate indices/fingerprints, unequal model sets,
non-binary scores and duplicate JSON keys fail.

The standard loader converts and date-filters the complete source subset. All
panel fingerprints must match uniquely before selection. Extra source questions
outside the panel are not evaluated. Missing questions, ambiguous matches or a
budget too small to cover every occupied stratum fail before inference. Each
configured source subset must contain the complete panel.

`difficulty_stratified` groups by historical pass count. `response_stratified`
groups by the complete pass/fail pattern in sorted reference-model order. One slot
covers each group; remaining slots go to the largest proportional deficit, with
lexical ties. Inside each group the lowest SHA-256 priorities of
`lcb-pruning-v1:{seed}:{index}` win. This exactly reproduces the independent
analysis design. Target references are excluded before groups are constructed.

Challenge data stays in the private challenge repository at
`task2/data/lcb-reference-panel.json`; this generic EvalScope repository includes
only synthetic fixtures. The exporter recovers 315 questions from saved GPT-OSS
Harmony prompt tokens, joins grades by index, and records six source-file hashes.
The supplied shared index remains the cross-model identity assumption because
original problem IDs were absent. All 315 fingerprints were independently matched
uniquely in the pinned public **880-question** `release_v5` corpus using projected
question/identity columns. The frozen 315 tasks are not the whole 880-task release.

## Weights and reports

For stratum population `N_h`, retained count `n_h`, and total population `N`, each
selected question contributes weight `N_h / (N * n_h)`. The primary metric is
`accuracy / weighted_mean / {scope: population}`: each question's weight times
its mean binary grade across repeated attempts, summed over questions. `num`
counts unique selected questions. It estimates average-attempt accuracy, not
population pass@k for k > 1. Ordinary unweighted subset mean and pass@k remain
separate report entries.

Incomplete questions/attempts, absent grades, invalid/inconsistent provenance,
duplicate execution IDs and invalid total weight fail the aggregate. The adapter
never silently renormalizes weights over surviving questions. Prediction/review
metadata records original index/fingerprint, stratum, weight, group counts,
population/selected sizes, strategy, ratio, seed, references and panel-file SHA-256.

## Live endpoint run

Use the original benchmark questions **and their test cases**, or let the standard
loader download the pinned source. Supplied challenge `Evals/` files contain
outputs/grades, not hidden tests for fresh grading. The parity audit's empty-test
loader fixtures must never be used for a live evaluation.

Set `EVAL_MODEL`, `EVAL_API_URL`, `EVAL_API_KEY` and `LCB_REFERENCE_PANEL` in the
environment. Install the upstream sandbox extra and configure Docker using the
[sandbox guide](https://evalscope.readthedocs.io/en/latest/user_guides/sandbox.html).
From this repository root:

```powershell
$datasetArgs = @{live_code_bench_pruned = @{subset_list = @('release_v5'); extra_params = @{pruning_strategy = 'difficulty_stratified'; prune_ratio = 1.0; reference_path = $env:LCB_REFERENCE_PANEL}}} | ConvertTo-Json -Depth 5 -Compress
.venv/Scripts/python.exe -m evalscope.cli.cli eval --model $env:EVAL_MODEL --eval-type openai_api --api-url $env:EVAL_API_URL --api-key $env:EVAL_API_KEY --datasets live_code_bench_pruned --dataset-hub huggingface --dataset-args $datasetArgs --sandbox '{"enabled":true}' --work-dir outputs/lcb-full-reference
```

Change the ratio to `0.5` and the output directory for an experimental 158-question
run. The **1.0 default** is issue #17's defended fallback: 315 question-level
generation requests at repeats=1, excluding transport retries. No compression
savings are claimed there. Smaller ratios remain experimental; CLI availability
does not certify a customer GO/NO GO decision. No model key or paid inference was
used for this ticket. Fresh endpoint/sandbox behavior remains to be measured live.

Saved-run comparison belongs to issue #21. Compare the same frozen population
and generation/grading settings: a default full `live_code_bench` run over 880
rows is not the recorded 315-row reference.

## Verification pointers

- `evalscope/benchmarks/live_code_bench_pruned/`: typed panel, selector and adapter
- `tests/api/test_live_code_bench_pruned.py`: registry, loader, grading and actual CLI tests
- `examples/live_code_bench_pruned/`: runnable offline task
- Challenge `task2/tools/export_lcb_panel.py`: reproducible panel export
- Challenge `task2/tools/audit_evalscope_lcb.py`: 1,200 native-loader parity cases and historical grade replay
- Challenge `task2/tools/verify_lcb_source.py`: optional public-source identity verification

Discovery index and docs are generated with the upstream CLI. Metadata-only
generation avoids hidden-test downloads for documentation. The Chinese page uses
the generator's English fallback; no translation credential was used. See
[VALIDATION_ISSUE_19.md](VALIDATION_ISSUE_19.md) for measured checks.

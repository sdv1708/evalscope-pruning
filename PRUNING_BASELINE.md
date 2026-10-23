# Private pruning development baseline — issue #18

Upstream: https://github.com/modelscope/evalscope

**Exact upstream base: `66f0945d145ce6c30de40253cd78144003c6f1fe`.**

Private development repository: https://github.com/sdv1708/evalscope-pruning

Branch: `feature/issue-18-evalscope-baseline`.

This is a derived development repository, not a GitHub fork-network fork.
The public upstream's Git history, Apache-2.0 LICENSE and source attribution
are retained. A separate private repository keeps development private. Never
push challenge artifacts or data to the public upstream. The synthetic six-row
fixture in this repository contains no challenge benchmark content.

## Scope

Issue #18 establishes the extension environment and a minimal native smoke path.
`pruning_smoke` is synthetic QA, with one retained question per metadata stratum
by default. It tests integration, not statistical performance. It is not
`live_code_bench_pruned` or AA-LCR, and its exact-match scores are not scores for
those benchmarks. Their production adapters and comparison workflow belong to
issues #19–#21 in the challenge repository.

## Install and run

From this repository's root, with Python 3.12 and uv:

```powershell
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements/pruning-baseline.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info pruning_smoke
.venv/Scripts/python.exe -m evalscope.cli.cli eval --model pruning-smoke-mock --eval-type mock_llm --datasets pruning_smoke --work-dir outputs/pruning-smoke
```

The dependency snapshot records the Python 3.12 Windows environment used for
verification; it does not change upstream's general dependency policy. On another
platform, start with `uv pip install -e . pytest ruff mypy import-linter` and
revalidate. Initial installation requires internet. The synthetic benchmark and
mock model require no model download, GPU, API credentials or paid inference.

On POSIX systems use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.
Commands assume the repository root, because the example config is a relative
file path. The bundled dataset path resolves relative to the adapter module.
Ordinary reports, predictions, reviews and configurations are written beneath
`outputs/pruning-smoke/` in a timestamped directory. Mock scores only test wiring.

The JSON example uses the normal `TaskConfig` schema and can also be run with:

```powershell
.venv/Scripts/python.exe -c "from evalscope import run_task; run_task('examples/pruning_smoke/task.json')"
```

To keep both questions in each
toy group, change `dataset_args.pruning_smoke.extra_params.keep_per_stratum` to
`2`. The default `1` retains three of six questions. Values must be positive
integers; invalid configuration fails before loading data. `--limit` applies
after selection and can remove stratum coverage: reserve it for debugging.

## Selected seam

Extend `DefaultDataAdapter` and override `load_subset(subset, data_loader)`.
Reuse the supplied loader to read/convert/filter the complete eligible pool
with limit/repeats/shuffle temporarily disabled, select original question IDs,
then reuse framework limit resolution, repeat helpers and reindexing. Prompt
processing, inference, scoring, cache handling and reports remain downstream.

The smoke selects the lowest SHA-256 priority within each metadata stratum,
using the framework seed and stable question ID. It rejects duplicate source
IDs rather than silently selecting the same question twice. Its fixed allocation
is demonstration behavior, not the analysis package's candidate policy. An
unweighted subset mean on unbalanced strata is not a full-population estimate.

The future coding adapter should inherit LiveCodeBench's prompt conversion,
date rules and sandbox grader; the AA-LCR adapter should retain its judge
contract. Do not substitute this synthetic QA grading for either benchmark.

Source pointers at the pin:

- `evalscope/api/registry.py`: registration decorator and configuration resolution.
- `evalscope/benchmarks/__init__.py`: adapter discovery and generated lazy index.
- `evalscope/api/benchmark/adapters/default_data_adapter.py`: loading and full pipeline.
- `evalscope/api/dataset/loader.py`: loaders, filtering, limits and repeats.
- `evalscope/api/dataset/dataset.py`: stable execution grouping and limit resolution.
- `evalscope/benchmarks/live_code_bench/live_code_bench_adapter.py`: coding behavior.

Alternatives: `record_to_sample` is too narrow for population allocation;
`sample_filter` alone lacks a whole-pool view and is called after loader limits
and repeats at this pin; `--limit` is a debugging prefix, not pruning; replacing
`load()` or the evaluator duplicates too much framework code; adding a global
core API before validating adapters is premature. An external file-selection
script alone would not meet the integration requirement.

## Verification

Create the parent of pytest's temporary directory on Windows:

```powershell
New-Item -ItemType Directory -Path .pytest-tmp -Force
.venv/Scripts/python.exe -m pytest tests/api/test_pruning_smoke.py --basetemp=.pytest-tmp/smoke
.venv/Scripts/python.exe -m pytest tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py --basetemp=.pytest-tmp/contracts
.venv/Scripts/python.exe -m ruff check evalscope/benchmarks/pruning_smoke tests/api/test_pruning_smoke.py
.venv/Scripts/python.exe -m ruff format --check evalscope/benchmarks/pruning_smoke
.venv/Scripts/lint-imports.exe
```

Run type checking on the new module and test with imported upstream modules
excluded from analysis, since upstream has no repository-wide mypy contract:

```powershell
.venv/Scripts/python.exe -m mypy --follow-imports=silent --ignore-missing-imports --check-untyped-defs evalscope/benchmarks/pruning_smoke tests/api/test_pruning_smoke.py
```

Public test seams are the registry/configuration, `load_dataset()` and actual
CLI-generated reports, as specified in the parent challenge PRD. Tests do not
replace loaders/evaluator internals. The model boundary uses upstream `mock_llm`.
Check `VALIDATION_ISSUE_18.md` for measured results and platform limitations.

## Generated discovery and documentation

After adding or renaming an adapter, regenerate the index, never edit it:

```powershell
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info --update-index
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info pruning_smoke --update --compute-stats --force --workers 1
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info --generate-docs
```

These are the Python equivalents of the upstream Make targets on Windows.
Generated metadata/stats describe the default selected three-row smoke dataset.
Upstream's separate translation step requires an LLM credential. The baseline
uses the generator's supported English fallback for Chinese docs; it makes no
translation API request.

For upstream updates, add the provenance remote if needed, fetch it, review the
adapter API and loader behavior, then rerun contracts before changing the pin:

```powershell
git remote add upstream https://github.com/modelscope/evalscope.git
git fetch upstream
git show 66f0945d145ce6c30de40253cd78144003c6f1fe:LICENSE
```

`git clone` does not copy local remote definitions; the private repository's
`origin` is not a substitute for the documented public `upstream`.

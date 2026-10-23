# Issue #21 validation

Private fork main was pulled to `9698587429f23a28daed3f341ca8b97aa5b1d28b`
before creating `feature/issue-21-compare-runs`. The inherited upstream pin is
`66f0945d145ce6c30de40253cd78144003c6f1fe`. Python 3.12.8, Windows.

| Check | Result |
| --- | --- |
| Public comparison CLI tests | **34 passed** |
| Complete relevant native regression suite and required upstream CI smoke | **242 passed**, 189 upstream warnings |
| Submission Task 2 suite | **129 passed** |
| Feature Mypy | Passed, 6 source/test/example files |
| Feature Ruff and formatting | Passed |
| Architecture contracts | **5 kept, 0 broken** |
| Pre-commit hooks on changed files | Passed |
| Built wheel includes all four extension modules | Verified against exact source bytes |
| Comparison executed from extracted wheel outside source checkout | Passed |
| Complete upstream pytest attempt | **27 collection errors**, 12 skipped; optional dependencies unavailable |
| Repository-wide `make lint` | Existing Windows symlink-placeholder EOF hook failure; unrelated edit removed |

The public command test boundary was explicitly confirmed by the user. Initial
execution failed because the module did not exist. Tests cover census and smaller
runs, unequal weights, separate question/attempt counts, threshold equality,
invalid thresholds, incomplete/malformed evidence, missing reports/reviews,
source/judge/generation mismatch, changed grading cases, independently reindexed
questions, original full adapters, AA-LCR warnings, model ordering and ties,
cross-model population/protocol incompatibility, and Native multi-level rounding.

Independent parallel standards/spec review found four compatibility gaps; all
were repaired and the spec reviewer independently passed seven targeted public
CLI regressions. No hard standards violation remains. One optional suggestion
to retain the validated Trace model rather than its dumped dictionary is recorded
as a maintenance tradeoff in the submission review report.

## Reproduce the final native suite

```powershell
.venv/Scripts/python.exe -m pytest tests/tools/test_compare_runs.py tests/api/test_aa_lcr_pruned.py tests/api/test_live_code_bench_pruned.py tests/api/test_pruning_smoke.py tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py tests/api/test_benchmark_meta.py tests/benchmark/test_live_code_bench_prompt.py tests/benchmark/test_live_code_bench_sandbox_stdio.py tests/api/judge/test_migrated_adapters.py tests/api/judge/test_gates.py tests/cli/test_all.py::TestRun::test_ci_lite --basetemp=.pytest-tmp/issue21-final -q
.venv/Scripts/python.exe -m mypy --follow-imports=silent --ignore-missing-imports evalscope_ext tests/tools/test_compare_runs.py examples/aa_lcr_pruned/smoke.py
.venv/Scripts/python.exe -m ruff check evalscope_ext tests/tools/test_compare_runs.py
.venv/Scripts/python.exe -m ruff format --check evalscope_ext
.venv/Scripts/lint-imports.exe
```

Loopback fixtures and inherited sandbox/worker tests require ordinary local
socket/process creation. The restricted process sandbox blocked loopback HTTP;
the same native smoke passed with those local operations permitted. No paid
benchmark inference or judge endpoint was used. CI-lite uses its mock model and
cached public test data.

The whole upstream suite was attempted, but collection requires optional
`anthropic`, `emoji`, `flask`, `langdetect`, `torch` and `uvicorn` dependencies.
It does not pass wholesale in this environment; the 242 passing tests are the
explicit relevant suite above. No unrelated heavy backends were installed to
inflate the validation claim. Repository-wide hooks again tried to add a newline
to `.github/copilot-instructions.md`, a symlink materialized as a Windows
placeholder. That unrelated modification was restored; applicable feature hooks
passed. No upstream lint ignore or architecture exemption was added.

## Measured Native CLI workflow

```powershell
.venv/Scripts/python.exe examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/issue21-native-verified
.venv/Scripts/python.exe -m evalscope_ext.tools.compare_runs --full outputs/issue21-native-verified/full --pruned outputs/issue21-native-verified/pruned --threshold 0.8
```

The first command invokes the real evaluator twice with a local synthetic
OpenAI-compatible model and judge. Full and pruned results contain 12 and 3
unique questions/attempts. Both weighted scores are 1.0; the signed difference
is 0 percentage points; paired question MAE is 0. Bounds [0.25,1.0] make the
subset inconclusive at 80%, while the full recorded score is GO. The comparator
warns about AA-LCR judge uncertainty and unavailable single-model ordering.
The final reviewed comparator was rerun on these saved Native results.

This is transport, serialization, validation and comparison evidence only. A
fixture reduction of 75% is not a demonstrated production compression benefit.
The defended reference defaults remain full retention for both Part A benchmarks.

## Packaging

`python setup.py bdist_wheel --dist-dir outputs/issue21-final-package` built
`evalscope-0.0.0.dev0-py3-none-any.whl`. Existing `evalscope*` discovery includes
`evalscope_ext` without a new packaging rule. All four extension files in the
wheel matched the reviewed source bytes. They were extracted to a separate
directory; with PYTHONPATH removed, Python imported that extracted package and
successfully compared the real saved smoke runs. The challenge repository records
the wheel SHA-256 and results in `docs/data/task2-run-comparison-package.json`.

The complete real coding endpoint/sandbox command contract is documented in
`COMPARE_RUNS.md`; it was checked against actual CLI help but not run on a paid
model. Native report schema 2 and generated config identity are required. Old
challenge JSONL artifacts are not relabelled as fresh Native inference results.

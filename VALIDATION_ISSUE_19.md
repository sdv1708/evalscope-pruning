# Issue #19 verification

Environment: Windows, Python 3.12.8, native EvalScope upstream pin
`66f0945d145ce6c30de40253cd78144003c6f1fe`, plus pinned issue #18 baseline
`152d811484e0c3ad3d9329af9befb73e961d8872`.

Before implementation, the challenge Task 2 suite passed **129 tests** and the
relevant native loader/registry/smoke/LiveCodeBench contracts passed **75 tests**.
Windows sandbox temp directories were unusable, so pytest uses `.pytest-tmp/`.

| Final check | Result |
| --- | --- |
| Complete feature suite and relevant upstream contracts, including CI-lite | **122 passed**, including 31 feature tests |
| Challenge Task 2 full suite | **129 passed** |
| Independent registry/loader parity and historical replay | **1,200 cases passed** |
| Public source identity verification | **315/315 unique matches**, 880 source rows |
| Feature Ruff check/format and Mypy | Passed, 4 native source/test files |
| Challenge Ruff check/format and strict Mypy | Passed |
| Architecture import rules | **5 kept, 0 broken** |
| Upstream pre-commit hooks on all feature files | Passed (nonapplicable hooks skipped) |
| Upstream repository-wide pre-commit | All hooks pass except the existing Windows symlink-placeholder EOF issue |

The repository-wide EOF hook tries to append a newline to
`.github/copilot-instructions.md`, an upstream symlink to `../AGENTS.md` materialized
as a plain file on this Windows checkout. This is the same limitation recorded in
issue #18. That hook's incidental change was removed after inspecting the exact
one-line diff. No unrelated upstream change is included in this feature.

Final framework command (with local process/listener capability enabled, mock
models and cached public CI-lite data):

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:MODELSCOPE_OFFLINE = '1'
.venv/Scripts/python.exe -m pytest tests/api/test_live_code_bench_pruned.py tests/api/test_pruning_smoke.py tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py tests/api/test_benchmark_meta.py tests/benchmark/test_live_code_bench_prompt.py tests/benchmark/test_live_code_bench_sandbox_stdio.py tests/cli/test_all.py::TestRun::test_ci_lite --basetemp=.pytest-tmp/issue19-full -q
```

The entire upstream repository contains optional backends, real external services
and large model-dependent tests. No all-upstream-tests claim is made; the complete
relevant integration/contract suite and the required CI smoke passed.

The first native selection test failed because `live_code_bench_pruned` was absent.
Configuration, selection and weighted aggregation were added in successive slices.
The weighted-estimator test first failed because the population metric was absent.
It now distinguishes a raw subset mean of 0.5 from a population estimate of 1/3.

The feature suite exercises registry configuration; exact golden selections;
ratio/strategy/panel validation; source/panel order invariance; model exclusion;
population mismatch, duplicate questions and insufficient budgets; full retention;
repeats; weighted reporting; real generated-code grading; native CLI output and
selection provenance; and actual OpenAI-compatible transport on a loopback server.
The HTTP fixture sends three deterministic correct programs and obtains a primary
weighted score of 1.0. It uses no real provider or external API credential.

The challenge audit compares **1,200 native registry/loader selections** and their
historical score replays with independent analysis: two strategies, five ratios,
twenty seeds, three score holdouts and three independently excluded pairs.
Original IDs, strata, weights, allocations, excluded references and replayed
estimates match. Full retention reproduces 241/315, 198/315 and 195/315.
Audit loader fixtures contain reconstructed questions and empty tests; they are
never graded and do not establish fresh-model performance.

Public-source verification matched all **315** question fingerprints uniquely
inside the pinned **880**-question `release_v5` source. It projected parquet
question/identity columns over HTTP ranges and did not fetch large hidden-test
columns. Its dataset SHA is `e70df9620dd54c12afac5e2881355de6f9ece2e9`.

On Windows, the restricted process sandbox prevented Python's local grader
workers from starting. The explicit correct/wrong-program test passed with normal
worker creation enabled. Grading and loopback tests therefore require that local
process capability; no model credentials are needed.

Commands and interpretation are in [LIVE_CODE_BENCH_PRUNED.md](LIVE_CODE_BENCH_PRUNED.md).
Generated discovery, metadata and benchmark pages use upstream generators. The
Chinese page uses their English fallback, and full hidden-test dataset statistics
are not downloaded solely for documentation. No paid inference, live provider
benchmark, Docker sandbox run or fresh-model accuracy certification is claimed.

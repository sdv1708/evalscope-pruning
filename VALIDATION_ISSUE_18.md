# Issue #18 verification record

Tested on Windows, Python 3.12.8, against upstream base
`66f0945d145ce6c30de40253cd78144003c6f1fe`. Exact package versions are in
`requirements/pruning-baseline.txt`. The native synthetic benchmark uses no
challenge data or paid model endpoint.

| Check | Result |
| --- | --- |
| Unmodified upstream adapter / dataset-limit / registry contracts | 50 passed |
| Final adapter / dataset-limit / registry / benchmark-meta / smoke suite | 81 passed, including all 16 new smoke tests |
| Upstream `tests/cli/test_all.py::TestRun::test_ci_lite` | 1 passed, mock model; public IQuiz dataset downloaded |
| Ruff check and format on new code | Passed |
| Mypy on new module and test, following upstream imports silently | Passed, 3 source files |
| Upstream `lint-imports` | All 5 contracts kept, 0 broken |
| Pinned upstream pre-commit hooks on every feature file | Passed; YAML hook had no applicable files |
| Full upstream pre-commit invocation | Run; Windows line-ending fixes and a pre-existing symlink-placeholder EOF issue prevented a clean global pass |
| Native CLI and `run_task` JSON example | Both produced ordinary JSON and HTML reports with 3 graded questions |
| Wheel build and temporary target installation | Passed; imported installed package and loaded bundled fixture, selecting 3 questions |

The baseline contracts were run before the adapter was introduced. The first
smoke test failed because `pruning_smoke` was absent; configuration and duplicate-ID
tests also failed before their corresponding validation was added. Tests then
passed through registry/configuration and `load_dataset()`, without mocks for
internal framework components. The CLI test launches a fresh interpreter outside
the repository working directory, executes real framework evaluation with
`mock_llm`, and checks prediction/review counts plus both report formats.

The 16 tests cover registration and group coverage, six invalid allocation
settings, duplicate question IDs, invariance to row ordering, four limit/repeat
cases, full toy retention, malformed metadata and the CLI artifact contract.
At this upstream pin, `TaskConfig(limit=0)` means unlimited, so the integration
retains that upstream convention. Fractional limits resolve against the selected
population before repeats. Caller configuration is preserved.

Useful reproduction commands are in `PRUNING_BASELINE.md`. The final suite was:

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py tests/api/test_benchmark_meta.py tests/api/test_pruning_smoke.py --basetemp=.pytest-tmp/contracts -q
```

The standard CI smoke was:

```powershell
.venv/Scripts/python.exe -m pytest tests/cli/test_all.py::TestRun::test_ci_lite --basetemp=.pytest-tmp/ci-lite -q
```

The complete upstream suite includes live services, optional backends, large
model downloads and platform-specific integrations; no all-tests pass is claimed.
Relevant baseline tests and the required CI smoke passed. The challenge
repository's complete existing Task 2 suite separately passed all 129 tests,
plus its Ruff and strict Mypy checks.

On Windows, pytest's default sandbox temp location was unusable, so test
directories were placed under `.pytest-tmp/`. Git's initial CRLF checkout also
conflicted with upstream LF hooks. Hook-generated changes outside the feature
were excluded. The remaining repository-wide EOF issue is the Windows
materialization of `.github/copilot-instructions.md`, an upstream Git symlink to
`../AGENTS.md`. All feature hooks pass. No unrelated upstream source fix is
included in the branch.

Documentation metadata, statistics, lazy-discovery index and English/Chinese
pages were generated with the upstream CLI. Translation requires an LLM
credential; the supported English fallback is used for the Chinese page.
Generated statistics describe the selected three-question smoke population,
not the six-question input fixture or real benchmark populations.

Example observed report: model `pruning-smoke-mock`, dataset `pruning_smoke`,
metric `exact_match / mean`, sample count **3**, score **0.0**. The zero score is
expected because `mock_llm` returns fixed text instead of solving the questions.
This verifies execution and grading, not model quality, selection fidelity,
customer decisions or production cost savings.

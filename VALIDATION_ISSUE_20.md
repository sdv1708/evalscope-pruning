# Issue #20 validation

Base private main: `3e850321`. Upstream framework pin:
`66f0945d145ce6c30de40253cd78144003c6f1fe`. Windows, Python 3.12.8.

| Check | Result |
| --- | --- |
| Complete relevant native suite plus required upstream CI smoke | **207 passed**, including all **32 AA-LCR feature tests** |
| Complete submission Task 2 suite | **129 passed** |
| Independent native selection and historical replay | **1,200 cases passed** |
| Feature Ruff check and format | Passed |
| Feature Mypy, imports followed silently | Passed, **10 source/test/example files** |
| Architecture contracts | **5 kept, 0 broken** |
| Upstream pre-commit on feature files | Passed; YAML/requirements hooks nonapplicable |
| Repository-wide pre-commit | Existing Windows symlink-placeholder EOF issue; no unrelated fix retained |

The first expanded run had 204 passes and three existing ArenaHard judge tests
missing optional `scikit-learn`. Installed the dependency from that benchmark's
requirements (`uv pip install --python .venv/Scripts/python.exe scikit-learn`),
then the same full relevant command passed all 207 tests. Upstream syntax and
Pydantic warnings are unchanged.

```powershell
.venv/Scripts/python.exe -m pytest tests/api/test_aa_lcr_pruned.py tests/api/test_live_code_bench_pruned.py tests/api/test_pruning_smoke.py tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py tests/api/test_benchmark_meta.py tests/benchmark/test_live_code_bench_prompt.py tests/benchmark/test_live_code_bench_sandbox_stdio.py tests/api/judge/test_migrated_adapters.py tests/api/judge/test_gates.py tests/cli/test_all.py::TestRun::test_ci_lite --basetemp=.pytest-tmp/issue20-final -q
```

Loopback model/judge fixtures and the inherited coding grader require ordinary
local listener/worker creation, blocked by the restricted process sandbox.
No paid benchmark inference or judge API was used. CI-lite uses cached public
IQuiz data with its mock model. The full upstream repository's optional/live
backend suites were not run wholesale.

Public seams: benchmark registry/configuration, native loader, scoring and CLI.
The initial registry test failed before implementation. Feature tests verify
full-retention default, ratio/strategy rejection, metadata groups, unequal weights,
target exclusion for strings/model objects, row-order invariance, repeats,
population/source mismatch, missing context, malformed panels, insufficient
budgets, limit/seed/exclusion errors, inherited judge success/failure, actual
OpenAI-compatible model/judge transport, and native report/provenance output.

Independent audit: two candidates, five ratios, twenty seeds, three individual
and three pair exclusions. Native IDs, strata, group counts, weights and replayed
weighted scores match the earlier analysis. Full retention reproduces 48/100,
66/100 and 64/100. Tiny synthetic contexts are never inferred or judged there.

Source identity: 95 exact official question strings and five exact reversible
UTF-8-decoded-as-Mac-Roman matches. All token counts and URL sets agree with
historical v1.0. Official text and declared document order are used for fresh runs;
therefore the audit establishes fixed-grade replay, not exact historical prompts.

The registry index, metadata and English/Chinese pages were generated using
upstream commands. The required statistics pass was attempted; an unconfigured
reference panel/corpus cannot define the population. Its misleading zero-row cache
was discarded and metadata regenerated without statistics. Translation was
attempted and failed for missing `DASHSCOPE_API_KEY`; the Chinese page uses the
upstream English fallback. No translation credential is assumed.

Repository-wide hooks try to append an EOF newline to the upstream symlink
`.github/copilot-instructions.md`, materialized as a placeholder on Windows.
That incidental edit was inspected and removed, consistent with #18/#19.
Feature-file hooks pass. Generated files were normalized to LF; unrelated docs
are unchanged except the generated LLM discovery tables.

See [AA_LCR_PRUNED.md](AA_LCR_PRUNED.md) for live and offline commands, report
semantics, historical source limits and unmeasured judge noise. Smaller ratios
are experimental. No fresh-model accuracy, savings or deployment guarantee is claimed.

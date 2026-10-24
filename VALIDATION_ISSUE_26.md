# Issue #26 documentation verification

The issue branch starts from freshly pulled private-fork main
`800119ff6870ca958f5d8459970f5fe75bfac305`, with upstream base
`66f0945d145ce6c30de40253cd78144003c6f1fe`. The runtime tree matches the
previous validated implementation `5fd26289972f6d01b13ea95bb30481ebd103fa2d`.
Only `README.md`, `TASK2_README.md` and this record change for #26.

The reviewer entrypoint provides installation, registration, synthetic full/pruned
evaluation, comparison, relevant regression/type/lint commands, real-provider
runbook links, method, weighted interpretation and the written walkthrough.
No runtime behavior changes, new test seam or new paid model result is introduced.

The owner requested deferring the video into a separate ticket. Recording,
publishing and reviewer access are now tracked in open
[issue #49](https://github.com/sdv1708/ai-model-benchmark/issues/49). No recording/link
exists yet; the requirement remains active for submission and is separate from
issue #26's written deliverables.
This validation does not certify private reviewer access or submission-form
completion. Branch publication is tracked by the accompanying pull request.

## Isolated installation and native workflow

Created a new sibling clone, `issue-26-native-clean`, with
`git clone --no-local --no-hardlinks` from the committed local Git source.
The new clone's HEAD is the runtime pin above. Created a separate Python 3.12.8
virtual environment and installed all 143 pinned baseline packages, followed by
`uv pip install --python .venv/Scripts/python.exe --no-deps -e .` from that clone.
Imports resolve to the new checkout, with no shared site-packages. Package cache
reuse does not reuse the original virtual environment. This is an isolated local
clone check, not verification of a reviewer's remote/private repository access.

Both benchmark-info commands succeeded. From that clean clone:

```powershell
.venv/Scripts/python.exe examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/task2-demo
.venv/Scripts/python.exe -m evalscope_ext.tools.compare_runs --full outputs/task2-demo/full --pruned outputs/task2-demo/pruned --threshold 0.8
```

Both commands exited 0. The native CLI wrote actual configs/reports/reviews.
The saved comparison reports 12 full / 3 retained unique questions and attempts,
weighted scores 1.0 / 1.0, difference 0 pp, completion bounds [0.25, 1.0], full GO
and subset inconclusive at 0.8. `decision_certified=false`; ordering is unavailable
with one model. This is scripted synthetic integration evidence, not a measured
real-model compression or savings result. Ordinary local socket/process access
was enabled; no paid provider inference was needed.

## Clean-clone defects found and fixed in instructions

1. Default Windows CRLF checkout fails the framework's LF formatter on four
   unchanged extension files. The clone command now uses
   `git clone -c core.autocrlf=false ...`, preserving that repository-local setting
   for the pinned checkout. Re-checkout with LF made formatting pass. No runtime
   source, global Git setting or formatter exemption was changed.
2. Pytest does not create the parent of a nested explicit basetemp. The first
   attempt had 108 setup errors because `.pytest-tmp` did not exist. The recipe
   now creates that parent before running the suite.
3. Three inherited ArenaHard judge regressions require scikit-learn, absent from
   the baseline snapshot but present in the previous development environment.
   The final test recipe installs `scikit-learn==1.9.1` and `threadpoolctl==3.7.0`
   explicitly. Neither is needed for the pruning smoke itself. The first full
   attempt therefore had 3 failures, 131 passes and 108 setup errors; it is not
   described as a successful clean-clone run.
4. CI-lite reads `dotenv_values('.env')`, not the process key environment. The
   documented guard requires a fresh clone without `.env` to guarantee mock mode.
   The verification clone has no `.env`. No user secrets/configuration were edited.

## Final verification

| Check | Result |
| --- | --- |
| Native registration and synthetic CLI / saved comparison | Passed |
| Complete relevant suite including upstream CI-lite | **242 passed**, 189 upstream warnings, 128.15 seconds |
| Feature Mypy in isolated environment | Passed, 6 files |
| Comparator Ruff lint | Passed |
| Extension formatting after LF checkout | Passed, 4 files |
| Architecture import contracts | 5 kept, 0 broken |
| Pre-commit on changed documentation | Passed |
| Repository-wide `make lint` | Known Windows symlink-placeholder EOF failure, explained below |

`make lint` again attempted to add a newline to `.github/copilot-instructions.md`,
the upstream symlink materialized as a Windows placeholder. That unrelated
hook-generated change was restored. All applicable changed-file hooks pass.
The entire upstream test suite was not rerun or claimed to pass.
The selected suite and install instructions are in [TASK2_README.md](TASK2_README.md).

Native smoke/test logs and saved runs remain under the clean clone's ignored
`outputs/`. The challenge repository records the fresh comparison JSON, historical
replay, complete 152-test analysis suite, acceptance status and review evidence.
Both documentation branches are prepared for pull-request review. Merge and
final submission remain pending.

Independent parallel Standards and Spec reviewers checked both repositories.
Standards found zero actionable issues. Spec review repaired the shared production
helper path (`_reference_pruning`, not the separate `pruning_smoke`) and CI-lite's
key-source prerequisite. The Spec reviewer confirmed zero unresolved findings.

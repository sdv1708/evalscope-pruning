# Reproduce the native pruning workflow

This [EvalScope-derived repository](https://github.com/sdv1708/evalscope-pruning)
contains the actual pruners and saved-run comparator. It preserves upstream history
and licensing; it is a derived repository rather than a GitHub fork-network fork.

**Upstream base: `66f0945d145ce6c30de40253cd78144003c6f1fe`.**
**Tested runtime: `800119ff6870ca958f5d8459970f5fe75bfac305`.**
The historical analysis, reference panels, and MMMU proposal live in the
[main project repository](https://github.com/sdv1708/ai-model-benchmark).

The defended result is **full retention: 315 coding / 100 AA-LCR questions**.
Smaller tested selections failed at least one retrospective fidelity gate.
No smaller production compression or live cost saving is established.

## Install from a clean clone

Use Git, uv, Python 3.12, and PowerShell 7. Internet access for package
installation is a prerequisite. From a parent directory:

```powershell
git clone -c core.autocrlf=false https://github.com/sdv1708/evalscope-pruning.git
cd evalscope-pruning
git checkout 800119ff6870ca958f5d8459970f5fe75bfac305
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements/pruning-baseline.txt
uv pip install --python .venv/Scripts/python.exe --no-deps -e .
```

Stop if any command fails. The historical runtime checkout predates this guide;
keep this guide open while following it. The clone option preserves the LF source
endings required by the fork's formatter without changing global Git settings.
The snapshot was tested on Windows with
Python 3.12.8. On POSIX, use `.venv/bin/python` and revalidate dependencies as
described in [PRUNING_BASELINE.md](PRUNING_BASELINE.md). Direct interpreter paths
avoid requiring shell activation. Upstream's broader supported Python range does
not imply this exact dependency snapshot was tested on every version/platform.

## Check registration and run without credentials

Run from the fork root. Choose a fresh output directory each time; the example
below must not contain earlier cached results.

```powershell
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info live_code_bench_pruned
.venv/Scripts/python.exe -m evalscope.cli.cli benchmark-info aa_lcr_pruned
.venv/Scripts/python.exe examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/task2-demo
if ($LASTEXITCODE -ne 0) { throw 'Synthetic native evaluation failed' }
.venv/Scripts/python.exe -m evalscope_ext.tools.compare_runs --full outputs/task2-demo/full --pruned outputs/task2-demo/pruned --threshold 0.8
if ($LASTEXITCODE -ne 0) { throw 'Saved-run comparison failed' }
```

The smoke starts a loopback-only scripted candidate/judge, invokes the real
evaluator twice and compares saved results. It needs local socket/process access,
but no GPU, provider credentials or paid calls. Inspect these output fields:

| Field | Expected synthetic value |
| --- | --- |
| `full_samples`, `pruned_samples` | 12, 3 unique questions |
| `full_score`, `pruned_score` | 1.0, 1.0 |
| `difference_pp` | 0.0 percentage points |
| `finite_pool_bounds` | [0.25, 1.0] |
| `decision.full`, `decision.pruned` | GO, inconclusive |
| `decision.decision_certified` | false |

`ordering` is empty for one model. Exit 0 means the comparison succeeded, not
that the model got GO; invalid/incompatible evidence produces exit 2. Read the
bounds and warnings. Three passes among twelve questions leave nine unknown:
the complete score could be 3/12 or 12/12. An illustrative 80% requirement lies
inside that range. These are completion bounds, not 95% confidence intervals.
The fixture's 75% reduction proves wiring, not real-world compression quality.

## Relevant tests and quality checks

From the installed fork root:

```powershell
uv pip install --python .venv/Scripts/python.exe scikit-learn==1.9.1 threadpoolctl==3.7.0
New-Item -ItemType Directory -Path .pytest-tmp -Force > $null
if (Test-Path .env) { throw 'Run this suite in a clean clone without .env so CI-lite uses its mock model' }
.venv/Scripts/python.exe -m pytest tests/tools/test_compare_runs.py tests/api/test_aa_lcr_pruned.py tests/api/test_live_code_bench_pruned.py tests/api/test_pruning_smoke.py tests/api/test_default_data_adapter.py tests/api/test_dataset_dict_limit.py tests/api/test_benchmark_registry_contract.py tests/api/test_benchmark_meta.py tests/benchmark/test_live_code_bench_prompt.py tests/benchmark/test_live_code_bench_sandbox_stdio.py tests/api/judge/test_migrated_adapters.py tests/api/judge/test_gates.py tests/cli/test_all.py::TestRun::test_ci_lite --basetemp=.pytest-tmp/task2-review -q
.venv/Scripts/python.exe -m mypy --follow-imports=silent --ignore-missing-imports evalscope_ext tests/tools/test_compare_runs.py examples/aa_lcr_pruned/smoke.py
.venv/Scripts/python.exe -m ruff check evalscope_ext tests/tools/test_compare_runs.py
.venv/Scripts/python.exe -m ruff format --check evalscope_ext
.venv/Scripts/lint-imports.exe
```

The extra scikit-learn installation, with its pinned threadpoolctl dependency,
supports three inherited ArenaHard judge
regressions included in this suite; it is not needed by the pruning smoke itself.
Creating the temporary-directory parent is necessary in a new clone. The selected
suite covers both adapters, comparator, loader behavior, registration,
coding prompt/sandbox behavior, judge contracts and upstream CI-lite. CI-lite reads
its provider key from a local `.env` file, not the process environment. The guard
requires a clean clone without that file, so CI-lite uses its mock model; it may
download public test data on its first run. See
[prior validation](VALIDATION_ISSUE_21.md) and [issue #26 verification](VALIDATION_ISSUE_26.md)
for the exact scope and results. The complete upstream suite has optional backend
dependencies beyond this snapshot and is not claimed to pass wholesale.

## Real full, candidate and comparison commands

The complete coding contract is in [COMPARE_RUNS.md](COMPARE_RUNS.md#real-coding-evaluation-contract),
with original problem/test-case and Docker sandbox prerequisites in
[LIVE_CODE_BENCH_PRUNED.md](LIVE_CODE_BENCH_PRUNED.md).
[AA_LCR_PRUNED.md](AA_LCR_PRUNED.md) supplies historical source/document setup and
the explicit judge configuration. The main project's historical
[operational runbook](https://github.com/sdv1708/ai-model-benchmark/blob/7882d16/task2/ISSUE_25_GUIDE.md#7-real-endpoint-runbook)
has full paired coding and AA-LCR PowerShell templates, including comparison.
These are provider templates, not records of live inference performed here.

Key configuration contract:

| Setting | Meaning |
| --- | --- |
| `--datasets live_code_bench_pruned` | Coding adapter with original grading tests |
| `--datasets aa_lcr_pruned` | Long-document adapter with LLM judging |
| `dataset_args.<dataset>.extra_params.pruning_strategy` | `difficulty_stratified` / `length_difficulty_stratified` defended strategies |
| `extra_params.reference_path` | Absolute path to the matching main project `task2/data/*-reference-panel.json` |
| `extra_params.prune_ratio` | Fraction **retained**, rounded up; 1.0 is defended |
| `--work-dir FULL` / `--work-dir PRUNED` | Actual flag at this pin; the brief's `--output` is conceptual |
| `--no-timestamp` | Makes those exact saved run roots |
| `--seed 42` | Reproducible selection priority |

Use the same reference adapter at ratio 1.0 for the full run, then an explicitly
experimental smaller ratio for a research comparison. At ratio 1.0 both sides
retain the full frozen pool with no saving. A 0.5 coding ratio retains 158 of 315;
it does not evaluate half of the broader 880-question release. Do not use `--limit`.

Match model, population, source revision, prompt, generation, judge, sandbox and
repetitions. Explicitly exclude canonical reference model names if testing aliases
of historical models; the adapter cannot infer arbitrary aliases. The comparator
needs exact roots containing `configs/task_config.yaml`, `reports/` and `reviews/`.
Historical JSONL files from the main project alone are not native runs. Set provider secrets
in environment variables and keep them out of shared command/config evidence.

## Written walkthrough

1. **Problem and evidence:** We want fewer questions without changing a customer's
   score, model ordering or requirement decision. The tested grid retained 10%,
   20%, 30%, 50% and 100%. Only full retention passed every illustrative policy
   gate; it is the conservative fallback, not proof that every smaller method fails.
2. **Method:** Coding strata use remaining historical reference pass counts;
   AA-LCR crosses those with token-length thirds. Reserve coverage of occupied
   strata, allocate the remaining budget, then choose stable seeded hash priorities.
   Target model grades are excluded before selection. This uses reference evidence
   available before evaluating a new candidate. Holdout stress tests do not prove
   transfer to a fourth model.
3. **Integration:** Inspect `evalscope/benchmarks/live_code_bench_pruned/` and
   `evalscope/benchmarks/aa_lcr_pruned/`. Both inherit `ReferencePruningAdapter` in
   `evalscope/benchmarks/_reference_pruning/adapter.py`, with shared selection in
   the adjacent `selection.py`. The `DefaultDataAdapter.load_subset` seam
   selects the complete eligible population before repeats/inference. Existing
   prompt conversion, model calls, coding sandbox, judge contracts and reports
   remain in the framework. It is a native registered extension.
4. **Demonstration:** Run the credential-free commands above. Open the saved config,
   reviews and reports. Follow original question identities, strata and weights
   into `evalscope_ext/tools/compare_runs.py`. Show the 12/3 counts, zero observed
   difference and inconclusive subset decision together. They answer different questions.
5. **Weighting:** Each selected question in group h has weight `N_h/(N*n_h)`.
   A group mean represents its population share. This corrects unequal allocation;
   it does not make an unrepresentative model panel representative of future models.
6. **Limits:** Full retention removes unknown questions from the
   recorded pool, not generation variability or judge error. One saved verdict per
   answer cannot estimate judge variance.
7. **Multimodal roadmap:** Cover the full MMMU inventory, 11,550 across 30 subjects,
   rather than only the 660 supplied references. Pair original images with
   answer-preserving visual stresses, plus no-image, factual-text and visual-fact
   controls. This diagnoses visual-path sensitivity through an API. Only an
   encoder-only intervention could support encoder-specific causality. The existing
   image harness is offline/synthetic; the full probe remains a design proposal.

## Sources and next experiment

Implementation behavior is defined by the source at the runtime pin and linked
adapter/comparison guides. [Official EvalScope usage](https://evalscope.readthedocs.io/en/latest/get_started/basic_usage.html)
corroborates the evaluation workflow; rolling docs do not override pinned flags.
The [official pinned MMMU inventory](https://raw.githubusercontent.com/MMMU-Benchmark/MMMU/268471d0d488258990025331c7528359c324aa25/README.md)
supports 150 development + 900 validation + 10,500 test questions. The
[MMStar paper](https://arxiv.org/abs/2403.20330v2) motivates testing visual dependence.
Those sources do not validate this project's proposed probe sizes or accuracy.

With more resources, freeze customer requirements and selection before collecting
an untouched model, repeat generation and independently rejudge fixed answers,
audit failures with humans, and measure actual tokens, wall time and cost.
Validate customer tasks and serving performance before treating benchmark GO
as deployment approval.

## Project history

This guide started as the Task 2 reviewer guide of an AI model quality challenge.
Issue numbers refer to the [main project issue tracker](https://github.com/sdv1708/ai-model-benchmark/issues).
[Issue #49](https://github.com/sdv1708/ai-model-benchmark/issues/49) tracks a recorded video
of the walkthrough. No recording exists yet.
The `VALIDATION_ISSUE_*.md` files keep their original wording from that period.

# Native AA-LCR reference pruning

`aa_lcr_pruned` is registered inside EvalScope and inherits AA-LCR conversion,
prompt template, judge workflow and standard output pipeline. The selected
issue #17 configuration is `length_difficulty_stratified`, **prune_ratio=1.0**.
This is the conservative full-reference fallback: no smaller tested operating
point passed all fidelity gates. Lower ratios are configurable research settings.

## Run the offline smoke

From this repository root after installing `requirements/pruning-baseline.txt`
and the editable package:

```powershell
python examples/aa_lcr_pruned/smoke.py
evalscope benchmark-info aa_lcr_pruned
```

The smoke starts a loopback OpenAI-compatible endpoint for a synthetic model and
judge, then invokes the real `evalscope eval` CLI. It retains three of twelve tiny
questions, produces native predictions/reviews/JSON/HTML, and reports weighted
accuracy 1.0. This proves plumbing only. There are no real provider calls or keys.

## Evaluate a model on the pinned benchmark

The main project repository supplies `task2/data/aa-lcr-reference-panel.json`.
Set `AA_LCR_PANEL` to its absolute path, plus provider environment variables.
Use the same context-capable model settings and judge policy when comparing runs.

```python
import os
from evalscope import TaskConfig, run_task

run_task(TaskConfig(
    model=os.environ['MODEL'],
    eval_type='openai_api',
    api_url=os.environ['MODEL_API_URL'],
    api_key=os.environ['MODEL_API_KEY'],
    datasets=['aa_lcr_pruned'],
    dataset_hub='huggingface',
    seed=42,
    dataset_args={'aa_lcr_pruned': {'extra_params': {
        'reference_path': os.environ['AA_LCR_PANEL'],
        'pruning_strategy': 'length_difficulty_stratified',
        'prune_ratio': 1.0,
    }}},
    judge={'strategy': 'llm', 'models': [{
        'model_id': os.environ['JUDGE_MODEL'],
        'api_url': os.environ['JUDGE_API_URL'],
        'api_key': os.environ['JUDGE_API_KEY'],
        'eval_type': 'openai_api',
    }]},
    work_dir='outputs/aa-lcr-pruned',
))
```

The native CLI accepts the same `--datasets aa_lcr_pruned`, `--dataset-hub
huggingface`, `--dataset-args` and typed `--judge` JSON settings. Use `--seed 42`.
Do not pass `--limit`: it would invalidate coverage and population weights.
The adapter rejects it. `repeats` generates fresh candidate answers after selecting
questions; it does not repeat-judge a fixed answer.

Remote evaluation requires the Hugging Face hub, pinned to
`bdae010bbce259820c0e34c1d7cce210d966fb75` (historical AA-LCR v1.0).
Other remote hubs are rejected rather than silently switching source versions.
A native `local_path` CSV/JSONL/parquet mirror is supported, with `text_dir`
pointing at the extracted corpus. With no `text_dir`, the inherited AA-LCR loader
downloads the archive from the configured dataset/revision. Every matched question
must agree with the frozen token count and canonical source URL set.

The benchmark corpus is large; questions use roughly 72k–115k benchmark tokens.
Configure provider context/output limits explicitly. Token counts in the panel are
the benchmark's fixed metadata, not a target model's actual billed tokens.

## Frozen panel and identity

Schema version 1 contains `tasks` and optional `provenance`. Each task has:

```json
{
  "index": 0,
  "question_sha256": "<64 lowercase hexadecimal characters>",
  "scores": {"reference-a": 0, "reference-b": 1},
  "input_tokens": 94494,
  "source_urls": ["https://example.com/document.pdf"]
}
```

Indices, fingerprints and reference model sets must be unique/consistent. Scores
are strict binary integers; tokens are positive integers; URL sets are nonempty
and unique. Duplicate JSON keys are rejected. Missing/duplicate source questions,
metadata drift, missing documents and insufficient coverage budgets fail explicitly.
Unrelated source questions do not enter the reference population.

The main project's exporter verifies all 100 official question identities. Ninety-five
recorded question strings match exactly; five match the exact UTF-8-to-Mac-Roman
decoding error recorded in provenance. Runtime fingerprints use official text;
runtime matching never applies fuzzy text repair. This does not establish identical
historical prompts or document order. The new path follows `data_source_filenames`
order and fails for missing/empty documents; upstream's directory iteration could
depend on filesystem order. Fresh-run scores must not be described as exact replay.

AA-LCR v1.1 changes answers and grading instructions. Its scores are not directly
comparable with the historical evidence. This extension preserves the pinned
EvalScope AA-LCR judge contract rather than claiming parity with newer official
grading. Keep judge model, prompt, policy and source revision in comparisons.

The original ZIP also omits the UTF-8 filename flag for four non-ASCII names;
one additionally uses decomposed Unicode. For a missing exact declared filename,
the adapter resolves only the corresponding CP437/decomposed-Unicode names and
rejects ambiguity. It does not fuzzy-match filenames or modify document contents.
Local CSV decimal token fields are normalized before strict metadata comparison.
The real pinned CSV and archive have been loaded through the native mirror path:
all 100 contexts read successfully, without inference or judge calls.

## Selection and metrics

The target model name, underlying model name and display identity are excluded
from reference grades. `excluded_reference_models` supports additional holdouts.
Use it for aliases that differ from recorded reference names. At least one
reference model must remain. A future unseen model needs no grades to be selected.

`length_difficulty_stratified` crosses empirical token-length thirds with the
remaining reference pass count. `metadata_stratified` crosses length thirds with
canonical document-URL-count thirds. Equal values stay together using empirical
midranks. These are cost/context and historical difficulty proxies, not semantic
embeddings or guarantees of document-category coverage.

Retain `ceil(N * prune_ratio)` questions. Every occupied stratum gets one slot;
remaining slots follow largest proportional deficit with lexical ties. Within
strata, SHA-256 priorities of `lcb-pruning-v1:{seed}:{index}` reproduce the original
analysis exactly (the historical namespace also applies to AA-LCR). Final output
is sorted by original index before optional shuffle and repeat/index operations.
Random/easiest/hardest-only baselines cannot be configured as production policies.

Each selected item from stratum h has weight `N_h/(N*n_h)`. The population estimate
is `sum(weight_i * mean_attempt_grade_i)`. Ordinary subset accuracy is also retained.
Example: group sizes 2, 2, 8, one retained per group. Weights are 1/6, 1/6, 2/3.
Only the largest group's question passes: subset accuracy is 1/3, population
estimate is 2/3. Reporting only the subset mean would distort the design.

The weighted metric is identified as `accuracy`, aggregation `weighted_mean`,
dimension `scope=population`; `num` counts unique questions, not repeated attempts.
Selection metadata, panel hash and excluded reference list travel with reviews.
Missing/excluded/nonbinary grades or incomplete repetitions fail the population
estimate closed. They are never scored zero or dropped with renormalized weights.

Judge noise is **unmeasured**. One recorded grade per answer cannot identify judge
variance. Full retention removes sampling error, not judge error. Sampling intervals
from offline analysis are conditional on recorded labels. The 66%-versus-64% pair
can tie after two total adversarial grade-cell flips; three can reverse it. These
are sensitivity counts, not estimated error probabilities. The weighted report
persists this warning and `decision_certified=false` beside the metric.

## Research and verification

Primary sources read before implementation:

- [Official AA-LCR release](https://artificialanalysis.ai/articles/announcing-aa-lcr)
- [AA-LCR dataset card and historical revision](https://huggingface.co/datasets/ArtificialAnalysis/AA-LCR)
- [EvalScope AA-LCR documentation](https://evalscope.readthedocs.io/en/latest/benchmarks/aa_lcr.html)
- [EvalScope contribution guide](https://evalscope.readthedocs.io/en/latest/advanced_guides/add_benchmark.html)
- Pinned local loader, AA-LCR adapter, judge output contract and issue #19 integration

The challenge repository includes an independent 1,200-case native loader/replay
audit across two strategies, five ratios, twenty seeds and six holdout sets. It
checks original IDs, weights, strata, allocation counts, references and scores.
Its tiny document contents are loader fixtures and are never inferred or judged.
Full-retention historical replay recovers 48/100, 66/100 and 64/100. Neither this
audit nor the synthetic transport smoke is evidence of new-model accuracy.

Saved-run comparison is issue #21. No paid benchmark inference is needed for #20.

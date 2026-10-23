# How the harness works

HarnessLab makes the path from an execution failure to a configuration decision inspectable. It records tool events, attaches diagnoses to those events, compares paired runs, and stores configuration versions that can be restored. The bundled demonstration uses scripted repair outcomes and costs; it does not call a language model.

The broader research motivation and planned study are described in the [unpublished manuscript](manuscript.md). The [evaluation guide](evaluation.md) separates completed software checks from experiments that have not been run.

## Execution and verification

[`runner.py`](../harnesslab/runner.py) invokes an argument array without a shell. Each process record includes the command, working directory, return code, timeout flag, captured output, truncation flag, and elapsed time. On POSIX, a timeout terminates the process group; the Windows branch terminates the direct child process.

[`test_worker.py`](../harnesslab/test_worker.py) collects `unittest` cases in a separate process and writes a structured summary. Verification checks that summary together with the process outcome. An exit code of zero alone cannot establish a passing test run.

The eight bundled process fixtures cover these cases:

| Case | Expected status | Accepted as resolved? |
| --- | --- | --- |
| A collected, passing test | `passed` | Yes |
| A failed assertion | `failed` | No |
| No collected tests | `zero_tests` | No |
| Every collected test skipped | `skipped_only` | No |
| Execution limit exceeded | `timeout` | No |
| Import failure | `import_error` | No |
| Exit zero without a result file | `unverified_exit_zero` | No |
| Nonzero exit without a result file | `process_error` | No |

The implementation also rejects a suite with no verified success after subtracting skipped and expected-failure cases. Positive test counts establish that some tests executed; they do not prove that those tests cover the requested change.

This runner is intended for trusted fixtures and reviewed commands. It inherits the local environment and filesystem permissions, so live third-party repositories and model-generated code require a separate isolated execution environment. Output is truncated before it is saved to JSON, but the temporary files used during execution can still grow; disk quotas must be enforced outside this prototype.

## Run records and independent outcomes

[`analysis.py`](../harnesslab/analysis.py) normalizes each run using explicit identifiers and provenance fields:

| Group | Fields |
| --- | --- |
| Run identity | `run_id`, `task_id`, `family_id`, `seed`, `split` |
| Repository snapshot | `repository`, `base_commit`, `task_input_sha256` |
| Configuration | `config_id`, `config_sha256` |
| Model | `model_id`, `model_spec` with provider, version, and settings hash |
| Budget and claims | `budget_usd`, `cost_usd`, `claimed_complete` |
| Evidence | `events`, `evaluation`, `final_test_sha256`, `evaluation_protocol_sha256` |
| Input type | `synthetic` |

Unknown cost remains `null`. It is distinct from a measured cost of zero. Real run records require pinned model metadata; the synthetic demo supplies an explicitly labeled local-fixture model specification.

An imported trace must have no embedded success judgment. [`external.py`](../harnesslab/external.py) joins it to a separately supplied evaluation file. A passing evaluation must identify the same run and task, declare independence, report `resolved: true`, include positive non-skipped test counts, and match both the frozen test hash and the evaluator-protocol hash. The protocol hash identifies this prototype's record contract, not the official SWE-bench scoring protocol.

`independent: true` is an assertion by the exporter. Separate files and matching hashes do not themselves prove that an agent could not inspect or modify the evaluator. Isolation and evaluator provenance remain responsibilities of the live experiment.

## Diagnoses retain their evidence

The current diagnosis layer uses rules. It identifies observable symptoms such as timeout, import errors, zero test collection, skipped-only runs, nonzero command exits, repeated identical failed commands, and completion claims without passing independent evidence.

Each diagnosis contains a run identifier and one or more logical pointers such as:

```text
traces.jsonl#baseline-task05-seed0/events/0
```

This is an evidence address, not an automatically navigable browser anchor. Locate the record with that `run_id` in the JSONL file, then inspect the indicated event. An import error is evidence of an import failure; it does not establish whether the root cause is a missing dependency, a wrong working directory, or an incompatible repository snapshot.

## Candidates and configuration versions

The reference demonstration compares `baseline`, `short-guidance`, and `test-wrapper`. Their outcomes are deliberately scripted to exercise report and decision branches. The candidate instructions do not drive a model in this demonstration.

For a live study, each candidate should change one main mechanism and record the development families used to design it. A guidance candidate changes the instructions visible to the agent; a wrapper candidate changes the testing interface. Neither may replace the frozen task-success evaluator or carry an issue-specific answer into evaluation tasks.

[`storage.py`](../harnesslab/storage.py) stores configurations under content hashes and records activation history. Rollback restores the previous selected configuration while preserving the record of the attempted change. This is a local version-selection operation; it does not deploy software or authorize a production release.

## Paired comparison

Runs are paired by `task_id` and `seed`. A pair must agree on repository snapshot, issue family, split, model settings, budget, input hash, final tests, evaluation protocol, and synthetic status. Duplicate records, changed identities, mixed real and synthetic observations, budget violations, or leakage from candidate-design families invalidate the comparison.

Missing independent outcomes are tracked separately from observed failures. An incomplete pair does not enter effect estimation, and the decision requests more data. The report retains planned task and selected task/seed counts for the records that were imported. A task with no imported record cannot be discovered automatically; a live study must reconcile all expected runs against an external frozen manifest.

For task $i$, configuration $h$, and $R_i$ evaluated repetitions, the task mean is:

$$
p_i(h)=\frac{1}{R_i}\sum_{j=1}^{R_i} y_{ij}(h).
$$

Here $y_{ij}(h)$ is one for an independently verified resolution and zero for an independently evaluated unresolved task. A missing or invalid evaluation is outside this binary outcome and blocks promotion.

The comparison averages task differences, giving each task equal weight:

$$
\Delta=\frac{1}{N}\sum_{i=1}^{N}\left[p_i(h_{\mathrm{candidate}})-p_i(h_{\mathrm{baseline}})\right].
$$

The bootstrap resamples these task differences, preserving the repetitions within each task. Repeating a task twice does not create two independent tasks.

The implemented regression rate divides the number of tasks with decreased mean success by the number with positive baseline mean success. It is undefined when that denominator is zero. False-completion rates use completion claims as their denominator; repeated-failure incidence uses tasks.

## Decision policy

The default policy is a demonstration setting, not a general statistical recommendation:

| Criterion | Default |
| --- | --- |
| Paired tasks | At least 12 |
| Complete paired repetitions per task | At least 2 |
| Task-level regression rate | 0 |
| Candidate/baseline mean-cost ratio | At most 1.25 for a positive-cost baseline |
| Lower endpoint of the task-bootstrap interval for mean improvement | Greater than 0 |
| Bootstrap | 2,000 resamples; seed `20260918`; 95% percentile interval |

Invalid evidence or policy violations produce `reject`. Incomplete evidence, unknown costs, insufficient tasks or repetitions, or an interval that does not clear the improvement threshold produce `needs-more-data`. Complete evidence satisfying the frozen criteria can produce `promote`. Reports always set `production_release_authorized` to `false`; the synthetic records set `decision_applies_to` to `demo_only`.

The [reference comparisons](../results/reference_demo/comparison.json) and [task table](../results/reference_demo/task_comparison.csv) expose the arithmetic. Their success rates, deltas, and cost entries are fixture properties, so they provide no estimate of a language model's improvement.

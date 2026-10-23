# Evaluation and reproduction

The completed evaluation checks the reference software with controlled inputs. It includes 38 unit tests, eight local process cases, and 72 synthetic run records from 12 tasks, two repetitions, and three configurations. The demonstration performs real local subprocess checks but uses scripted repair outcomes and costs. No live language-model or SWE-bench task-resolution experiment has been executed.

## What has been checked

| Layer | Recorded result | Interpretation |
| --- | --- | --- |
| Unit suite | 38 passed; 0 failed | Local branch, boundary, and validation behavior |
| Process cases | 8 of 8 matched expected status | Pass, fail, zero collection, skips, timeout, import error, unverified zero exit, and process error |
| Synthetic replay | 12 tasks × 2 repetitions × 3 configurations = 72 records | Trace handling and paired-report arithmetic |
| Diagnoses | 102 from the synthetic traces | Evidence-pointer generation and rule behavior |
| Decision branches | Wrapper: `promote`; guidance: `needs-more-data`; separate regression fixture: `reject` | Demonstration-policy behavior on constructed inputs |
| Frozen tests and rollback | Verified in the local validation | Integrity and recovery behavior within the prototype |
| Model execution | None | No observed model-effect or business-impact result |

The source validation was recorded on macOS 14.6.1, arm64, with Python 3.13.1. A relocated copy was also checked with Python 3.12.14 and passed the 38 tests and demo. These observations do not establish portability to every supported Python release or operating system.

The [reference summary](../results/reference_demo/summary.json) records the demonstration scale and explicit absence of a model run. The other inspectable outputs are the [comparison JSON](../results/reference_demo/comparison.json), [task comparison CSV](../results/reference_demo/task_comparison.csv), and [process checks](../results/reference_demo/process_check_summary.json). Their numeric success and cost differences are specified by the fixture and must not be presented as measured coding-agent gains.

## Run the offline checks

Run all commands from the repository root. The implementation uses the Python standard library. Python 3.10 or later is recommended; the recorded source checks used the two versions above.

```bash
python3 -m unittest discover -s tests -v
python3 -m harnesslab demo --output results/demo
```

The demo output directory must be absent or empty. Use a new directory for a second run so that earlier outputs remain available. Expected summary:

```text
process_checks=8/8
synthetic_runs=72 tasks=12 repeats=2 configs=3
final_tests_unchanged=true main_llm_experiment_run=false
```

The last line printed by the command identifies the generated directory. It contains raw demonstration traces, test fixtures and evaluations, diagnosis records, configuration history, comparison reports, and a local `review.html` page. The saved public reference files provide a compact entry into the same demonstration; rerunning the demo creates the full local artifact set.

Recompute diagnoses and the wrapper comparison from a newly generated demo:

```bash
python3 -m harnesslab replay --traces results/demo/traces.jsonl --output results/replayed_diagnoses.json
python3 -m harnesslab compare --traces results/demo/traces.jsonl --freeze results/demo/test_freeze.json --output results/replayed_comparison.json
```

Check strict test semantics directly:

```bash
python3 -m harnesslab check-tests --tests results/demo/fixtures/passed --output results/check_passed.json
python3 -m harnesslab check-tests --tests results/demo/fixtures/zero_tests --output results/check_zero.json
```

The passing fixture returns exit code 0. The zero-test fixture prints `status=zero_tests resolved=false` and returns exit code 2. That rejection is the expected behavior even if the inner test process exited successfully.

## Interpret coverage before interpreting outcomes

The [methods guide](methods.md#paired-comparison) defines the task-level analysis. Read these counts together:

| Field | Meaning |
| --- | --- |
| `planned_task_count` | Distinct tasks present among the selected imported records |
| `selected_task_seed_count` | Distinct task/seed pairs represented in those records |
| `task_count` | Tasks with at least one complete, valid evaluated pair included in the task table |
| `paired_run_count` | Complete paired repetitions contributing to that table |

The gate still requires the registered minimum repetitions per task. A task represented by only one valid pair can appear in the table while the decision requests further data. An entirely absent task has no record from which the program can infer its existence; external reconciliation is required for a complete planned denominator.

Missing independent evaluation is kept distinct from an observed unresolved task. An earlier handling defect could interpret a missing candidate outcome as a failure and reject it as a regression. The corrected implementation excludes the incomplete pair from effect estimation, preserves coverage information, and returns `needs-more-data`; the unit suite checks this boundary.

## External-run interface

The adapter accepts a reviewed command as an argument array and imports a trace separately from its evaluation. The bundled example checks this interchange contract with a synthetic fixture:

```bash
python3 -m harnesslab run-command --config results/demo/external_example/command.json --freeze results/demo/test_freeze.json --output results/external_command.json
python3 -m harnesslab import-run --trace results/demo/external_example/trace.json --evaluation results/demo/external_example/evaluation.json --freeze results/demo/test_freeze.json --output results/imported
```

`run-command` does not evaluate task success. It reports `evaluated=false`; success must be supplied by the independent evaluator. The demo import remains synthetic. This check does not establish integration with a live agent or official benchmark harness.

For live traces, pin the model provider, model version, settings hash, repository commit, input identity, configuration, task split, budget, and repetition identifier. Preserve the runner's original output and make any mapping into HarnessLab's schema explicit. The `evaluation_protocol_sha256` field identifies HarnessLab's evaluation contract; official benchmark scores require an auditable conversion from the original evaluator report.

## Public metadata is not benchmark execution

The [source audit provenance](../results/metadata_audit/source_manifest.json) and [repository counts](../results/metadata_audit/summary.json) record inspection of 300 records from the SWE-bench Lite test split, including 114 Django and 17 pytest entries. It also exercised a 20-row Django download. These are metadata counts, not reconstructed environments or solved issues.

The importer writes only `instance_id`, `repo`, `base_commit`, `problem_statement`, `created_at`, and `version`. It excludes reference patches, test patches, answer-bearing hints, and reference-test lists from its saved agent-facing output. The dataset service's raw response may contain excluded fields in memory, so raw responses must not be passed to the acting agent.

To create a fresh metadata snapshot:

```bash
python3 -m harnesslab download-metadata --output results/public_metadata_new --limit 20
```

This command uses the network and records source information and a checksum in its generated output. Consult the [SWE-bench Lite dataset](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite) and retain applicable dataset and repository terms when using external artifacts.

## Live efficacy study: protocol only

The manuscript specifies the following study, which remains unexecuted:

1. Select a scoped failure family and reconstruct eligible historical tasks in an isolated evaluator. Record exclusions and failed reconstructions before outcome-based selection.
2. Group related issues into families, then assign development, validation, and final sets. Keep reference repairs and hidden tests outside the agent and candidate-design environment.
3. Pin the base agent, model settings, repository snapshot, dependencies, container image, and operating budget. Start each run in a fresh workspace and register repetition identifiers.
4. Use development evidence to design a concise guidance candidate and a testing-wrapper candidate. Compare each against the fixed baseline and manually prepared static guidance. Raw-log retrieval is an optional comparator.
5. Select on validation tasks. Freeze the candidate, evaluation policy, cost account, and final analysis before accessing the final holdout.
6. Evaluate the selected configuration on the untouched final tasks using independent task scoring. Include failed attempts and candidate-development overhead in the cost report.

For final comparison, the CLI requires `--split final` and `--final-ledger`. The ledger is created exclusively and consumed before the comparison completes, including on an inconclusive comparison or a later validation error. It is a conservative local one-use marker. It cannot prove that a holdout was never accessed elsewhere, and changing the ledger filename does not create a new holdout. Precheck completeness on validation data; after consumption, document any protocol deviation and use a newly established final batch.

No Django environment reconstruction, live mini-swe-agent run, real task-resolution score, model-driven candidate generation, model-cost measurement, or cross-repository transfer result is included in this release.

## Limits of the evidence

Frozen hashes detect changes to agreed files; they do not prove test adequacy or protect against an operator who can rewrite both the code and its history. Independent files do not prove evaluator isolation. Task-level bootstrap intervals summarize the selected sample and can be unreliable with small or strongly related task pools. Public historical tasks also raise possible model-training contamination concerns.

The appropriate conclusion from the current checks is that the prototype exercises its stated data and decision paths on controlled inputs. Whether the proposed interventions improve a coding agent remains an open empirical question.

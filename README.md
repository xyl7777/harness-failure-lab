# HarnessLab: Failure Analysis for Coding Agents

A Python reference implementation for inspecting coding-agent failures and comparing changes to the agent's execution harness under fixed evaluation rules.

An agent can claim success after collecting zero tests, repeat a command that cannot run, or improve on one task while regressing on another. HarnessLab connects these observations to recorded evidence, checks test execution independently of completion claims, and compares configuration versions before activating or rolling them back.

The current implementation includes an offline demonstration with scripted repair outcomes and real subprocess checks. It does not call a language model. The demonstrated success rates and costs are synthetic inputs used to exercise the analysis and decision logic; real SWE-bench agent experiments have not been run.

## What is implemented

- **Process verification:** separate statuses for passed, failed, zero tests, skipped-only, timeout, import error, unverified exit zero, and process error. Exit code zero alone does not establish success.
- **Evidence-linked diagnosis:** rule-based observations point to the run and event that produced them. Repeated failures and unsupported completion claims remain inspectable symptoms, without a causal root-cause claim.
- **Paired comparison:** baseline and candidate runs must match task, seed, model settings, budget, frozen test fingerprint, and evaluator protocol. Incomplete evidence produces `needs-more-data`.
- **Configuration history:** content-addressed configurations, activation records, and an explicit rollback operation.
- **External interfaces:** reviewed argument-array commands and separate trace/evaluation imports. Commands run without shell interpolation.

| Read next | Contents |
|---|---|
| [Methods](docs/methods.md) | Trace contract, evidence checks, comparison policy, and trust boundaries |
| [Evaluation](docs/evaluation.md) | Executed software checks, synthetic results, and the proposed real-task protocol |
| [Technical manuscript](docs/manuscript.md) | Research motivation, detailed protocol, limitations, and references |
| [Implementation](harnesslab/) | Standard-library Python modules |
| [Tests](tests/test_harnesslab.py) | Boundary cases for execution, evidence, comparison, and storage |

## Run the offline demonstration

Use Python 3.10 or newer from the repository root. No third-party packages or API keys are needed. The release was checked on macOS with Python 3.13.1; the original materials also report validation with Python 3.12.14.

```bash
python3 -m unittest discover -s tests -v
python3 -m harnesslab demo --output results/demo
```

The demo output directory must be absent or empty. Use a fresh directory for another run. Expected console output includes:

```text
process_checks=8/8
synthetic_runs=72 tasks=12 repeats=2 configs=3
final_tests_unchanged=true main_llm_experiment_run=false
```

Open the generated `results/demo/review.html` in a browser to inspect comparisons and evidence links. The generated directory also contains the full traces, independent test outputs, frozen tests, and version history. This repository retains a compact, path-free selection of [reference results](results/reference_demo/); generate a new demo for complete replayable artifacts.

```bash
python3 -m harnesslab replay --traces results/demo/traces.jsonl --output results/replayed_diagnoses.json
python3 -m harnesslab compare --traces results/demo/traces.jsonl --freeze results/demo/test_freeze.json --output results/replayed_comparison.json
python3 -m harnesslab check-tests --tests results/demo/fixtures/zero_tests --output results/check_zero.json
```

The final command intentionally exits with code 2 and reports `status=zero_tests resolved=false`.

## Reference results

The demo covers 12 constructed tasks, two repeats per task, and three configurations, for 72 synthetic runs. All eight subprocess scenarios are classified as expected. The existing test suite contains 38 tests. The release check reran the tests and demo and reproduced the stored comparison.

| Scripted configuration | Task-mean pass rate | False completion claims | Decision |
|---|---|---|---|
| Baseline | 41.7% | 14 / 24 | Reference |
| Short guidance | 58.3% | 10 / 24 | Needs more data |
| Test wrapper | 75.0% | 6 / 24 | Promote within demo only |

These values verify software behavior on arranged fixtures. The guidance text did not drive a model to produce the outcomes. Every comparison is marked `synthetic: true`, `decision_applies_to: demo_only`, and `production_release_authorized: false`. See [comparison.json](results/reference_demo/comparison.json) for denominators and task-level intervals, and [task_comparison.csv](results/reference_demo/task_comparison.csv) for the wrapper comparison.

## Public data and experiment scope

The metadata downloader projects six allowed fields from [SWE-bench Lite](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite): instance ID, repository, base commit, issue text, creation date, and version. It excludes patches, test patches, hints, and reference test lists from saved output. The upstream response can still contain excluded fields in memory before projection.

An earlier audit read all 300 test-set metadata records. This release retains [repository counts](results/metadata_audit/summary.json) and the [source manifest](results/metadata_audit/source_manifest.json), without redistributing issue text. Metadata inspection is separate from reconstructing or solving the tasks.

Real agent runs require isolated execution, an independently operated evaluator, reviewed adapters, pinned model and environment versions, and development/validation/final task separation. The subprocess runner inherits local permissions and is not a security sandbox. The supplied fixtures are trusted; arbitrary generated code needs a container or separate machine. A declared `independent` field and local hashes do not by themselves prove evaluator isolation.

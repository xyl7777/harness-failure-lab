# Failure-Driven Harness Improvement for Coding Agents

## A Reproducible Prototype and Evaluation Protocol

Unpublished technical manuscript, version 1.0. Independent prototype informed by publicly described developer-tool workflows, with no company affiliation claimed. The reference implementation and documentation were prepared with AI assistance. This document makes no individual authorship or contribution claim. The completed checks use synthetic records and local process fixtures; the live-model efficacy study remains unexecuted.

See the [repository overview](../README.md), [implementation guide](methods.md), and [evaluation and reproduction guide](evaluation.md).

## Abstract

Coding agents operate through tools, instructions, and execution environments that can cause recurring failures independently of the underlying language model. Changing these components is straightforward; deciding whether a change should be retained is harder. A candidate may remove a visible error while introducing regressions, increasing execution costs, or exploiting information from the evaluation set. This manuscript presents an evidence-linked workflow for failure-driven harness improvement. It records agent actions, identifies actionable failure hypotheses, represents scoped interventions, and compares configuration versions using separately supplied task evaluations. A reference implementation exercises the workflow with constructed traces and real local process checks. These checks validate implementation behavior, not coding-agent effectiveness. A separate protocol specifies evaluation on public software issues with fixed model settings, development-only diagnosis, validation-based candidate selection, and an untouched final holdout. The principal contribution is an inspectable experimental artifact and decision process. No improvement in language-model task resolution, company productivity, or deployment reliability is claimed. The release establishes a basis for testing whether targeted changes to an agent's operating environment transfer beyond the failures that motivated them.

Keywords: coding agents; agent harnesses; failure analysis; software testing; reproducible evaluation.

## 1. Introduction

A research engineer maintaining a coding agent must decide whether a new testing interface or repository instruction should replace the current configuration. The decision arises even when the model remains fixed. An agent may repeatedly call the wrong test entry point, treat an incomplete test run as adequate verification, or spend its remaining budget retrying an operation that cannot succeed in the current environment. A useful intervention might be a short instruction, a clearer tool interface, or a check that prevents an unsupported completion claim. Each intervention changes the conditions under which future tasks are attempted.

An observed failure alone does not identify the correct intervention. A missing dependency may result from an incorrectly reconstructed benchmark environment, a poor tool choice, or a repository change that genuinely requires a dependency update. Automatically adding guidance after every failed run can accumulate contradictory instructions. Replacing all instructions with more elaborate tools can increase maintenance and execution costs. A workflow therefore needs both an explanation linked to observable evidence and a comparison that can reject an attractive but harmful change.

Tessl's public engineering writing describes maintenance loops that examine logs, review feedback, and recurring integration failures [1, 2]. This project uses that publicly documented business setting as motivation. It does not assume access to Tessl's private code, traces, or customers. The general idea of using feedback to improve agent operation is established. The proposed work concentrates on a reproducible implementation of evidence handling, narrowly scoped interventions, and configuration selection.

The project addresses three questions. RQ1 asks whether a particular recurring failure can be associated with an actionable change to repository guidance or a testing interface. RQ2 asks whether that change improves independently evaluated tasks under a fixed operating budget. RQ3 asks how much of any apparent benefit survives controls for candidate selection, task-family leakage, and regressions. The current release supports experimentation on these questions; only local software-validation checks have been executed.

## 2. Related Work and Industrial Context

SWE-bench frames software repair as modifying a real repository to address a public issue, with executable tests used for evaluation [3]. Its historical task structure is useful for reproducibility because the starting commit and evaluation artifacts can be specified. It does not remove contamination concerns or guarantee that every selected task can be reconstructed on a new machine. The present study uses a selected task subset and must report its inclusion criteria rather than present a subset score as a full benchmark result.

SWE-agent studies interfaces through which language agents navigate, edit, and test software [4]. It motivates treating the interface as an experimental variable. The present project keeps the initial interface deliberately small and examines changes suggested by recurring execution evidence. The open-source mini-swe-agent repository provides a potential base agent for later live experiments [5]. Its behavior and version must be pinned; adopting it does not make its existing functionality a contribution of this project.

Reflexion uses linguistic feedback retained in memory to influence later trials [6]. Self-Refine uses iterative feedback and revision without requiring model-weight updates [7]. These works establish relevant approaches to using feedback. Here, the object being revised is an explicitly versioned operating component, such as a test tool or repository instruction. The evaluator is separated from the component proposing changes. A raw-log retrieval condition is included as an optional comparator so that structured intervention is not evaluated only against the absence of memory.

Agentless provides an example of a structured software-repair pipeline with localization, repair, and validation stages [8]. Its relevance is methodological: added autonomy is not by itself an improvement. A simpler fixed procedure can be a strong comparator. The experiment therefore includes manually prepared static guidance, rather than assuming an adaptive workflow is superior.

Tessl already exposes skill-evaluation tooling [9], and its public maintenance-loop description includes turning recurring signals into corrective work [1]. This project does not claim to invent these practices. Its proposed contribution is a small artifact in which a reviewer can inspect the route from evidence to intervention and from paired task outcomes to a configuration decision.

## 3. Scope and Decision Model

The first efficacy study is restricted to one Python repository and one observed family of execution failures. Django is the initial task pool; a different repository may be used later to assess transfer. Two intervention classes are compared: concise repository guidance and a testing wrapper with structured execution results. A fixed base model, existing repository documentation, task descriptions, and model settings are held constant within a comparison.

A task is identified by its public instance identifier and starting repository commit. A run adds the configuration version, model identifier, repetition identifier, tool events, final patch reference, and independently supplied evaluation result. A candidate intervention identifies the development evidence that motivated it, the repository versions and conditions where it applies, the files or tool definitions changed, and the previous configuration to which it can be reverted.

Three outcomes are available to the release reviewer. **Promote** means that the candidate satisfies the registered decision policy on the specified evaluation set. **Reject** means that an observed policy violation supports retaining the previous version. **Needs more data** means the evidence is incomplete or insufficient. These are decisions under a chosen policy, not proofs of correctness. A candidate that reduces a visible failure but causes unacceptable task regressions should not be promoted.

The reference prototype and the future efficacy study operate at different levels. Constructed records are suitable for checking whether a missing evaluation is handled as missing, whether a regression enters the correct denominator, or whether a rollback preserves version identity. They cannot establish that a language model benefits from an intervention. That claim requires new agent runs and independent task evaluation.

## 4. Architecture

### 4.1 Trace collection and execution semantics

The trace collector records each executable action with its task and run identifiers, command, working directory, process outcome, available test counts, and elapsed execution information. Model usage and billing fields are recorded when supplied by the model provider; absence is represented explicitly rather than replaced with zero. A provider-neutral interchange format permits external runners to submit traces and separately obtained evaluations.

A process exit code is only one observation. A command may complete successfully without executing tests relevant to the patch. A run that times out does not become successful because a partial output contains the word “passed.” The local validation layer therefore exercises concrete cases such as no tests collected, all tests skipped, import failure, and timeout. Test framework summaries have framework-specific semantics. A parser that cannot establish the test outcome must return an unknown or invalid verification state instead of silently accepting it.

The prototype's ordinary subprocess execution is used for trusted local fixtures. It is not a security sandbox. Live execution of repository code belongs in isolated containers or an equivalent environment with explicit resource and network policies. The final evaluator should be outside the working directory writable by the repair agent. Hashing a test artifact can detect a changed file, but does not establish that the test suite is sufficient or semantically correct.

### 4.2 Evidence-linked diagnosis

Diagnosis produces a hypothesis with references to raw observations. Deterministic indicators include repeated command failures, missing collection evidence, repeated unchanged actions, and environment errors. A model may assist in proposing explanations, but its statement is not the evidence itself. The original command, returned error, and task context remain available to the reviewer.

Failure aggregation is performed within an explicitly defined scope. Identical error strings from different repository versions need not have the same cause. Conversely, related failures can have different surface messages. The first implementation uses inspectable categories and allows unresolved cases. Later work may compare learned grouping with this rule-based reference, using manually checked labels that are separate from the final task evaluations.

An explanation such as “the test entry point was unclear” predicts a particular intervention effect: a clearer entry point should reduce that failure on new tasks. The experiment should also count cases where the original explanation was wrong. A diagnosis that cannot identify an observable consequence remains a hypothesis for investigation and should not automatically alter the default harness.

### 4.3 Candidate representation and bounded changes

Each candidate changes one main mechanism. A guidance candidate adds a concise instruction describing the supported test entry point and its scope. A wrapper candidate implements a controlled test invocation and exposes structured results. The candidate manifest records its source development tasks, scope, base configuration, content hash, and review status. The intervention must not contain a task's reference patch, final-test answer, or issue-specific solution disguised as reusable guidance.

The first version does not allow arbitrary, unreviewed code generation to modify the evaluator. Candidate edits affect the agent-facing environment only. A separately managed evaluation definition determines task success. New tests proposed by a candidate can be useful diagnostic tools, but cannot replace the frozen success criterion in the same experiment.

The minimal intervention is not necessarily the best intervention. A short instruction can be inexpensive but ignored. A wrapper can enforce consistent execution but apply too broadly or hide useful details. The experiment compares these concrete alternatives and records their costs. Complexity should be justified by independent benefit, not by how many components the prototype contains.

### 4.4 Configuration comparison and rollback

Comparison joins old and candidate runs using task and repetition identifiers. Missing counterparts are reported before any rate is computed. Duplicate run records, incompatible task snapshots, absent evaluator evidence, and changed final-test identifiers are reasons to withhold a release decision. A report should make the included and excluded task counts explicit.

The reference implementation provides an inspectable gate with a task-level bootstrap. Its engineering defaults require at least 12 paired tasks and two repetitions per task, no observed task-mean regressions, a candidate-to-baseline mean cost ratio no larger than 1.25, and a positive lower endpoint of a 95% task-bootstrap interval for mean improvement. The implementation uses 2,000 resamples and a fixed resampling seed of 20260918. These are explicit demonstration-policy settings, not universal release criteria or a statistical power calculation. A prospective study should register its own justified settings before examining final results. The interval is a sampling summary of the selected tasks, not evidence that the public benchmark represents all production work.

The retained configuration and its predecessor are stored with immutable content identifiers. Rollback changes the selected version while preserving the comparison report that caused the decision. It is a local configuration operation, not a claim that a production deployment occurred. A failed or inconclusive candidate remains in the record because it documents the cost of the search process.

## 5. Data and Leakage Controls

The public SWE-bench Lite test split was inspected through the dataset service. The snapshot contained 300 task records, including 114 from Django and 17 from pytest. These are metadata counts, not counts of successfully reproduced tasks. The public release retains [audit provenance](../results/metadata_audit/source_manifest.json) and [repository counts](../results/metadata_audit/summary.json) from the full metadata audit. The source validation also exercised a filtered Django import. Issue text and answer-bearing fields are not included in this release. The metadata importer uses an allowlist and excludes reference patches, test patches, and answer-bearing hints from the agent-facing export.

Before a task is admitted to the efficacy experiment, its starting failure and reference repair should be reproduced by an evaluator who does not expose the repair to the acting agent. Reconstruction failures should be categorized, not silently removed after results are observed. Eligibility criteria include available source, a reproducible environment, executable independent evaluation, and compatibility with the scoped failure family. If the resulting pool is small, the paper should report the reduced scope.

Tasks are grouped by related issue family before partitioning. Development tasks supply diagnosis evidence and candidate design. Validation tasks support selection among candidates. A final holdout evaluates a frozen selected configuration and is not reused for iterative tuning. Repository documents supplied to the agent must match the historical snapshot; using future documentation can reveal fixes or APIs unavailable at the task's starting point.

Once final results are examined, that holdout becomes part of the project's historical evidence. A later improvement round requires a new final evaluation set or must be reported explicitly as exploratory reuse. Naming a file “test” is not a sufficient leakage control; access by candidate-generating processes and humans must be considered.

## 6. Evaluation Protocol

### 6.1 Conditions and operational controls

The primary comparison includes a fixed baseline harness, manually written static guidance based on allowed development material, and the selected feedback-driven intervention. The guidance and wrapper candidate classes are evaluated separately before any combination is tested. Optional raw-log retrieval helps assess whether structured diagnosis adds value beyond providing past experience.

Within each task, comparisons use the same starting code, base model version, model settings, eligible tools, and budget ceiling. The intervention's intended differences are recorded explicitly. Runs begin in fresh workspaces. When repeated sampling is possible, repetition identifiers are fixed in advance and execution order is randomized to reduce sensitivity to service or load changes. An identical model seed does not guarantee identical provider behavior, so actual requests and available model-version metadata must be preserved.

The cost account includes successful and unsuccessful repair attempts. It also lists the separate cost of diagnosing historical failures, generating candidates, reviewing them, and selecting a version. Equal maximum budgets do not imply equal realized cost. The report should include both operating cost per task and the overhead of the improvement process. A one-off expensive change may require many subsequent tasks before any operating saving offsets that overhead.

### 6.2 Outcomes and units of analysis

Let an independently evaluated outcome be one for a resolved task and zero for an unresolved task. A missing evaluation is tracked separately; it cannot be silently converted to a success or discarded. The primary task table preserves the full planned denominator and an evaluation-completeness count. Reports may include a conservative unresolved treatment for missing outcomes, clearly distinguished from complete-case analysis. Such sensitivity analysis does not feed the promotion gate: missing independent outcomes require further evaluation.

$$
p_i(h)=\frac{1}{R_i}\sum_{j=1}^{R_i}y_{ij}(h).
$$

$$
\Delta=\frac{1}{N}\sum_{i=1}^{N}\left[p_i(h_{\mathrm{candidate}})-p_i(h_{\mathrm{baseline}})\right].
$$

Here $y_{ij}(h)$ is the independently assessed binary outcome for task $i$, repetition $j$, and configuration $h$; $R_i$ is the registered number of evaluated repetitions for task $i$; and $N$ is the number of tasks in the paired comparison. The task mean $p_i(h)$ keeps repeated runs within a task. The average task-level change is $\Delta$.

These expressions also describe the prototype's task-level aggregation of constructed paired records. Constructed outcomes check arithmetic and decision logic; they do not supply an observed agent effect. The bootstrap resamples these task-level differences, preserving the contribution of repeated runs within each task rather than treating each run as a separate task.

The implemented regression metric counts tasks whose mean success decreases, divided by tasks with positive baseline mean success. With a single binary run, this reduces to baseline-successful tasks that become unsuccessful. With repeated runs, it includes a decrease from complete to partial success. The report retains the exact numerator, denominator, and task-level means. A matched-run regression metric can be added, but must have a different name and denominator. If no baseline task has positive success, the implemented conditional rate is undefined, not zero. False completion claims likewise require a denominator of all completion claims and an independent evaluator result.

Secondary outcomes include recurring failure incidence, tool retries, execution cost, latency, and the share of tasks needing human intervention. Failure incidence is counted per task under a frozen classification policy. An agent producing many verbose events should not receive a different failure weight merely because it logs more detail. Classification disagreements and unknown cases are reported separately.

### 6.3 Selection, uncertainty, and ablations

Selecting the best of several candidates on the same validation tasks creates optimism. The final holdout estimates the selected procedure, including its selection step, rather than validating every candidate retrospectively. The number of considered candidates and rejected versions should be reported. A large search cannot be presented as one unplanned comparison.

The primary uncertainty analysis resamples task blocks, preserving all repetitions and both configurations within each sampled block. Small or highly homogeneous task pools limit what those intervals mean. No nominal confidence level can repair an invalid split or a benchmark that poorly represents the intended deployment setting.

Planned ablations remove evidence-based grouping, replace the wrapper with guidance, remove scope restrictions, or bypass candidate selection. The final-test evaluator itself must remain unchanged. The main experiment should distinguish interventions that improve the task outcome from those that merely make logs cleaner. None of these live-model ablations has been run in the current release.

## 7. Implementation Validation and Current Evidence

The local validation uses deliberately constructed inputs. It runs actual processes for the execution checks and uses scripted trace records for comparison and decision checks. The latter exercise software behavior under known outcomes; their success-rate changes are encoded properties of the fixture and must not be interpreted as treatment effects on a model.

| Validation layer | Observed result | What it supports |
|---|---|---|
| Unit suite | 38 tests passed; 0 failed | Implemented branch and data-validation behavior |
| Saved command checks | 8 of 8 matched expected exit codes, including the unit-suite command | Reproducible local invocation and artifact generation |
| Process fixtures | 8 of 8 matched the expected status | Handling of pass, fail, zero tests, skips, timeout, import error, process error, and unverified zero exit |
| Constructed replay | 72 records: 12 tasks × 2 repetitions × 3 configurations; 102 diagnoses | Trace joining, diagnosis, and task-level report generation |
| Decision branches | Wrapper fixture: promote; guidance fixture: needs-more-data; regression fixture: reject | Policy implementation on scripted outcomes; all promotion is demo-only |
| Frozen tests and rollback | Unchanged test identifiers and rollback verified | Local integrity and version-recovery behavior |
| Model execution | No live model experiment; actual API spend USD 0 | No efficacy or business-impact conclusion |

The recorded run used Python 3.13.1 on macOS 14.6.1 (arm64), with the validation record timestamped 19 September 2026 UTC. The original validation saved per-command stdout and stderr, source-file SHA-256 identifiers, a task manifest, and fixture evaluations. This public release includes [aggregate reference outputs](../results/reference_demo/summary.json), [process-case classifications](../results/reference_demo/process_check_summary.json), and [paired comparisons](../results/reference_demo/comparison.json). Running the offline demo regenerates the full local artifact tree; raw local paths and process logs are not distributed in the aggregate release. Its apparent success-rate differences and cost entries are scripted inputs; this manuscript deliberately does not report them as model-effect estimates.

One concrete validation issue concerned missing independent outcomes. An earlier comparison path could treat an absent candidate evaluation as an unsuccessful candidate, and then reject it as a regression against a successful baseline. The corrected implementation keeps that pair out of effect estimation, preserves its place in the planned coverage, and returns needs-more-data. A regression test checks this case. This is a discovered software-handling defect, not a finding about a coding model.

The original machine-readable runtime report and saved command output record the source validation; the released aggregates preserve the principal counts, classifications, and comparison outputs. The public metadata audit verifies availability and field handling only. It does not show that Django environments have been rebuilt, that reference fixes pass, or that a coding model has attempted these tasks.

Consequently, this manuscript reports no answer to RQ2 concerning real-model effectiveness. RQ1 is operationalized through an evidence-linked diagnosis representation, and RQ3 through an explicit evaluation protocol, but neither is empirically settled by fixture tests. The distinction is useful: implementation defects can be discovered cheaply before the more expensive agent experiment, while the efficacy question remains open.

## 8. Threats to Validity and Failure Cases

Construct validity depends on the independent tests. A patch can satisfy the available tests and still be wrong. Additional human inspection and separately prepared tests can provide supplementary evidence, but should not be retroactively introduced to favor a candidate. Test-count checks also cannot establish relevance: running many irrelevant tests is not adequate verification of a changed behavior.

Internal validity is threatened by candidate selection, unequal context budgets, unstable provider versions, and shared workspaces. Trace-derived guidance may accidentally encode a solution. A wrapper may improve results by adding information rather than by changing the interface. Controls should make these differences explicit; otherwise the experiment measures a bundle of changes whose individual contributions are unknown.

External validity is limited by historical public tasks, possible model exposure during training, the initial repository, and the selected failure family. A gain within Django does not imply a gain on frontend development, unfamiliar tools, or production incidents. The company context motivates a decision, but no business impact or company adoption follows from a benchmark outcome.

Operational failure can also occur after a promising result. Repository versions change, a testing tool can become stale, and accumulated guidance can contradict earlier instructions. The version scope and rollback record make these failures easier to inspect; they do not eliminate the maintenance burden. Two substantive uncertainties remain: when a failure category should be split into separate interventions, and how quickly a useful repository-specific intervention loses value as the repository evolves.

## 9. Reproducibility and Responsible Reporting

The release contains the Python reference implementation, aggregate outputs from locally executed validation, documentation, and an evaluation protocol. The quickstart is an offline demonstration and does not require model credentials. A separate external-run interface supports later integration with a chosen agent runner and independent evaluator. A fixture-backed adapter check verifies the interchange contract, not the correctness of a particular external model integration.

Model credentials should be supplied through the execution environment rather than stored in traces or the source archive. Public repository licensing and dataset usage terms should be retained with downloaded artifacts. Live repository execution should be isolated from personal files and secrets. Logs should record reproducibility information without retaining unnecessary credentials or unrelated user data.

The resulting document is a technical manuscript for continued experimental work. A publication-quality efficacy claim requires actual task runs, recorded inclusion criteria, the frozen final analysis, and confirmation of author contributions. The current artifact can be cited as a prototype or design report, not as a published study, accepted paper, or company internship.

## 10. Conclusion

Failure-driven harness improvement can be expressed as a sequence of inspectable decisions: preserve a run, formulate a scoped failure hypothesis, change one operating component, and compare the resulting configuration against credible alternatives. The reference prototype makes this workflow executable and checks several implementation boundaries using constructed inputs. Its main empirical question remains whether such interventions improve independently assessed, previously unseen software tasks. The supplied protocol specifies how that question can be tested without treating a plausible diagnosis, a favorable replay, or a cleaner log as sufficient evidence of improvement.

## References

[1] Maria Gorinova and Simon Maple. Feedback Loop Engineering: making your project agent-ready. Tessl, 4 September 2026. [Article](https://tessl.io/blog/feedback-loop-engineering-making-your-project-agent-ready)

[2] Amy Heineike. The Rise of the Harness Engineer. Tessl, 25 August 2026. [Article](https://tessl.io/blog/the-rise-of-the-harness-engineer)

[3] Carlos E. Jimenez et al. SWE-bench: Can Language Models Resolve Real-World GitHub Issues? ICLR 2024. arXiv:2310.06770. [Paper](https://arxiv.org/abs/2310.06770)

[4] John Yang et al. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. 2024. arXiv:2405.15793. [Paper](https://arxiv.org/abs/2405.15793)

[5] SWE-agent contributors. mini-swe-agent. Source repository; implementation version must be pinned for an experiment. [Repository](https://github.com/SWE-agent/mini-swe-agent)

[6] Noah Shinn et al. Reflexion: Language Agents with Verbal Reinforcement Learning. 2023. arXiv:2303.11366. [Paper](https://arxiv.org/abs/2303.11366)

[7] Aman Madaan et al. Self-Refine: Iterative Refinement with Self-Feedback. 2023. arXiv:2303.17651. [Paper](https://arxiv.org/abs/2303.17651)

[8] Chunqiu Steven Xia et al. Agentless: Demystifying LLM-based Software Engineering Agents. 2024. arXiv:2407.01489. [Paper](https://arxiv.org/abs/2407.01489)

[9] Tessl contributors. Tessl Skill Eval Action. Source repository. [Repository](https://github.com/tesslio/skill-eval)

[10] Princeton NLP. SWE-bench Lite dataset. Public dataset and metadata service. [Dataset](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite)

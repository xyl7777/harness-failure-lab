"""Evidence-linked diagnoses and paired, task-level conservative decisions."""
import math
import random
from collections import defaultdict
from .storage import digest, safe_id

EVALUATOR_PROTOCOL = {"version": 1, "pass_requires": ["independent", "resolved_true", "positive_non_skipped_tests", "same_frozen_tests"]}
PROTOCOL_HASH = digest(EVALUATOR_PROTOCOL)
DEFAULT_POLICY = {"min_tasks": 12, "min_repeats": 2, "max_regression_rate": 0.0,
                  "min_delta": 0.0, "max_cost_ratio": 1.25, "bootstrap_samples": 2000, "bootstrap_seed": 20260918}


def normalize_run(run):
    required = ("run_id", "task_id", "family_id", "repository", "base_commit", "split", "config_id",
                "config_sha256", "seed", "model_id", "budget_usd", "cost_usd", "claimed_complete",
                "task_input_sha256", "final_test_sha256", "evaluation_protocol_sha256", "events", "evaluation")
    missing = sorted(set(required)-set(run))
    if missing:
        raise ValueError("missing trace fields: " + ", ".join(missing))
    for name in ("run_id", "task_id", "family_id", "config_id"):
        safe_id(run[name])
    if run["split"] not in ("dev", "validation", "final"):
        raise ValueError("invalid split")
    if type(run["seed"]) is not int or type(run["claimed_complete"]) is not bool:
        raise ValueError("seed must be int and claimed_complete must be bool")
    for name in ("budget_usd", "cost_usd"):
        v = run[name]
        if v is None and name == "cost_usd":
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise ValueError(name + " must be nonnegative finite number (cost may be null)")
    if not isinstance(run["events"], list):
        raise ValueError("events must be a list")
    if run["evaluation"] is not None and not isinstance(run["evaluation"], dict):
        raise ValueError("evaluation must be an object or null")
    for event in run["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("argv", []), list) or not all(isinstance(a, str) for a in event.get("argv", [])):
            raise ValueError("each event must be an object with a string argv list")
    result = {name: run[name] for name in required}
    result["schema_version"] = 1
    result["synthetic"] = bool(run.get("synthetic", False))
    model_spec = run.get("model_spec", {"provider": "local-fixture", "version": "scripted-v1", "settings_sha256": digest({})} if result["synthetic"] else None)
    if not isinstance(model_spec, dict) or any(not isinstance(model_spec.get(k), str) or not model_spec[k] for k in ("provider", "version", "settings_sha256")):
        raise ValueError("real traces require pinned model_spec provider/version/settings_sha256")
    result["model_spec"] = model_spec
    result["candidate_design_families"] = sorted(set(run.get("candidate_design_families", [])))
    result["evaluation_sha256"] = digest(run["evaluation"]) if run["evaluation"] is not None else None
    return result


def evidence_pass(run):
    e = run.get("evaluation")
    if not isinstance(e, dict):
        return False
    n, skipped = e.get("tests_run"), e.get("skipped")
    return (e.get("independent") is True and e.get("resolved") is True and
            type(n) is int and type(skipped) is int and 0 <= skipped < n and
            e.get("run_id") == run["run_id"] and e.get("task_id") == run["task_id"] and
            e.get("final_test_sha256") == run["final_test_sha256"] and
            e.get("evaluation_protocol_sha256") == run["evaluation_protocol_sha256"] == PROTOCOL_HASH)


def has_ground_truth(run):
    e = run.get("evaluation")
    return (isinstance(e, dict) and e.get("independent") is True and
            type(e.get("resolved")) is bool and type(e.get("tests_run")) is int and
            type(e.get("skipped")) is int and 0 <= e["skipped"] < e["tests_run"] and
            e.get("run_id") == run["run_id"] and e.get("task_id") == run["task_id"] and
            e.get("final_test_sha256") == run["final_test_sha256"] and
            e.get("evaluation_protocol_sha256") == run["evaluation_protocol_sha256"] == PROTOCOL_HASH)


def diagnose(run):
    diagnoses, repeated = [], defaultdict(list)
    for i, event in enumerate(run["events"]):
        location = "traces.jsonl#" + run["run_id"] + "/events/" + str(i)
        text = str(event.get("stderr", "")) + "\n" + str(event.get("stdout", ""))
        kind, rationale = None, None
        if event.get("timed_out"):
            kind, rationale = "timeout", "Process exceeded its recorded execution limit."
        elif "ModuleNotFoundError" in text or "ImportError" in text:
            kind, rationale = "import_or_environment", "An import failed; this does not establish the root cause."
        elif event.get("tests_run") == 0:
            kind, rationale = "zero_test_collection", "No collected tests; exit zero cannot verify correctness."
        elif event.get("tests_run", 0) > 0 and event.get("skipped") == event.get("tests_run"):
            kind, rationale = "skipped_only", "Every collected test was skipped."
        elif event.get("return_code") not in (0, None):
            kind, rationale = "command_failure", "Nonzero command exit; inspect stderr before proposing a repair."
        if kind:
            diagnoses.append({"run_id": run["run_id"], "category": kind, "evidence": [location],
                              "confidence": "observed_symptom", "explanation": rationale})
            repeated[(tuple(event.get("argv", [])), kind)].append(location)
    for (argv, kind), locations in repeated.items():
        if len(locations) >= 2:
            diagnoses.append({"run_id": run["run_id"], "category": "repeated_failed_command",
                              "evidence": locations, "confidence": "observed_pattern",
                              "explanation": "Identical command repeated with symptom " + kind + "; causality remains unproven."})
    if run["claimed_complete"] and not evidence_pass(run):
        diagnoses.append({"run_id": run["run_id"], "category": "completion_not_verified",
                          "evidence": ["traces.jsonl#" + run["run_id"] + "/evaluation"],
                          "confidence": "observed_disagreement", "explanation": "Completion claim lacks passing independent evidence."})
    return diagnoses


def _ci(values, samples, seed):
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values)/len(values) for _ in range(samples))
    return [means[int(.025*(samples-1))], means[int(.975*(samples-1))]]


def compare_runs(runs, baseline, candidate, policy=None, expected_split="validation"):
    if baseline == candidate:
        raise ValueError("baseline and candidate must differ")
    policy = {**DEFAULT_POLICY, **(policy or {})}
    for key in ("min_tasks", "min_repeats", "bootstrap_samples"):
        if type(policy[key]) is not int or policy[key] < 1:
            raise ValueError("policy " + key + " must be a positive integer")
    for key in ("max_regression_rate", "min_delta", "max_cost_ratio"):
        if isinstance(policy[key], bool) or not isinstance(policy[key], (int, float)) or not math.isfinite(policy[key]) or policy[key] < 0:
            raise ValueError("policy " + key + " must be finite and nonnegative")
    if expected_split not in ("validation", "final"):
        raise ValueError("promotion comparison requires validation or final split")
    selected = [normalize_run(r) for r in runs if r.get("config_id") in (baseline, candidate)]
    invalid, missing, groups, config_hashes, families = [], [], defaultdict(dict), defaultdict(set), defaultdict(set)
    run_ids = set()
    for run in selected:
        if run["run_id"] in run_ids:
            invalid.append("duplicate run_id")
        run_ids.add(run["run_id"])
        families[run["family_id"]].add(run["split"])
        if run["split"] != expected_split:
            invalid.append("source split is not " + expected_split)
        if run["family_id"] in run["candidate_design_families"]:
            invalid.append("candidate design family leaked into evaluation")
        config_hashes[run["config_id"]].add(run["config_sha256"])
        key = (run["task_id"], run["seed"])
        if run["config_id"] in groups[key]:
            invalid.append("duplicate task/seed/config observation")
        groups[key][run["config_id"]] = run
        e = run["evaluation"]
        if e and e.get("final_test_sha256") != run["final_test_sha256"]:
            invalid.append("final test evidence hash mismatch")
        if not has_ground_truth(run):
            missing.append("missing or invalid ground truth: " + run["run_id"])
        if run["cost_usd"] is not None and run["cost_usd"] > run["budget_usd"]:
            invalid.append("recorded cost exceeded per-run budget: " + run["run_id"])
    if any(len(v) != 1 for v in config_hashes.values()):
        invalid.append("configuration mutated within comparison")
    if any(len(v) != 1 for v in families.values()):
        invalid.append("issue family crossed splits")
    if len({r["synthetic"] for r in selected}) > 1:
        invalid.append("synthetic and real observations mixed")
    invariants = ("family_id", "repository", "base_commit", "split", "model_id", "model_spec", "budget_usd",
                  "task_input_sha256", "final_test_sha256", "evaluation_protocol_sha256", "synthetic")
    by_task = defaultdict(list)
    for key, pair in sorted(groups.items()):
        if set(pair) != {baseline, candidate}:
            missing.append("incomplete pair: " + repr(key))
            continue
        b, c = pair[baseline], pair[candidate]
        if any(b[k] != c[k] for k in invariants):
            invalid.append("pair invariants changed: " + repr(key))
        if not has_ground_truth(b) or not has_ground_truth(c):
            continue
        by_task[key[0]].append((b, c))
    # Task and its repeats must describe one fixed benchmark instance.
    for task, pairs in by_task.items():
        if any(len({digest(pair[0][k]) for pair in pairs}) != 1 for k in invariants):
            invalid.append("task identity changed between repeats: " + task)
        if len(pairs) < policy["min_repeats"]:
            missing.append("insufficient repeats: " + task)
    rows = []
    for task, pairs in sorted(by_task.items()):
        b, c = [x[0] for x in pairs], [x[1] for x in pairs]
        def summary(rr):
            costs = [r["cost_usd"] for r in rr]
            return {"success_rate": sum(evidence_pass(r) for r in rr)/len(rr),
                    "cost_mean_usd": sum(costs)/len(costs) if all(x is not None for x in costs) else None,
                    "claim_count": sum(r["claimed_complete"] for r in rr),
                    "false_claim_count": sum(r["claimed_complete"] and not evidence_pass(r) for r in rr),
                    "repeated_failure": any(any(d["category"] == "repeated_failed_command" for d in diagnose(r)) for r in rr)}
        bs, cs = summary(b), summary(c)
        rows.append({"task_id": task, "repeats": len(pairs), "baseline": bs, "candidate": cs,
                     "delta": cs["success_rate"]-bs["success_rate"]})
    n = len(rows)
    deltas = [r["delta"] for r in rows]
    baseline_positive = sum(r["baseline"]["success_rate"] > 0 for r in rows)
    regressed = sum(r["delta"] < 0 for r in rows)
    metrics = {"planned_task_count": len({r["task_id"] for r in selected}),
               "selected_task_seed_count": len(groups),
               "task_count": n, "paired_run_count": sum(r["repeats"] for r in rows),
               "improved_tasks": sum(d > 0 for d in deltas), "regressed_tasks": regressed,
               "regression_denominator_baseline_positive_tasks": baseline_positive,
               "regression_rate": regressed/baseline_positive if baseline_positive else None,
               "delta": sum(deltas)/n if n else None,
               "delta_task_bootstrap_ci95": _ci(deltas, policy["bootstrap_samples"], policy["bootstrap_seed"]) if n else None}
    for label in ("baseline", "candidate"):
        costs = [r[label]["cost_mean_usd"] for r in rows]
        claims = sum(r[label]["claim_count"] for r in rows)
        metrics[label] = {"task_mean_success_rate": sum(r[label]["success_rate"] for r in rows)/n if n else None,
                          "cost_mean_usd": sum(costs)/n if n and all(x is not None for x in costs) else None,
                          "cost_observed_task_count": sum(x is not None for x in costs),
                          "cost_denominator_tasks": n,
                          "false_completion_count": sum(r[label]["false_claim_count"] for r in rows),
                          "false_completion_denominator_claims": claims,
                          "false_completion_rate": sum(r[label]["false_claim_count"] for r in rows)/claims if claims else None,
                          "repeated_failure_tasks": sum(r[label]["repeated_failure"] for r in rows),
                          "repeated_failure_denominator_tasks": n}
        all_runs = [r for r in selected if r["config_id"] == (baseline if label == "baseline" else candidate)]
        all_costs = [r["cost_usd"] for r in all_runs]
        metrics[label]["all_selected_run_count"] = len(all_runs)
        metrics[label]["all_selected_run_cost_total_usd"] = sum(all_costs) if all(x is not None for x in all_costs) else None
        metrics[label]["all_selected_run_cost_unknown_count"] = sum(x is None for x in all_costs)
    bc, cc = metrics["baseline"]["cost_mean_usd"], metrics["candidate"]["cost_mean_usd"]
    metrics["cost_ratio"] = cc/bc if bc is not None and bc > 0 and cc is not None else None
    reasons = list(dict.fromkeys(invalid))
    if invalid:
        decision = "reject"
    elif missing or n < policy["min_tasks"] or bc is None or cc is None:
        decision, reasons = "needs-more-data", list(dict.fromkeys(missing))
        if n < policy["min_tasks"]:
            reasons.append("insufficient independent tasks")
        if bc is None or cc is None:
            reasons.append("cost unknown; null is not zero")
    elif metrics["regression_rate"] is not None and metrics["regression_rate"] > policy["max_regression_rate"]:
        decision, reasons = "reject", ["regression rate exceeds frozen policy"]
    elif metrics["cost_ratio"] is not None and metrics["cost_ratio"] > policy["max_cost_ratio"]:
        decision, reasons = "reject", ["cost ratio exceeds frozen policy"]
    elif metrics["delta_task_bootstrap_ci95"][0] <= policy["min_delta"]:
        decision, reasons = "needs-more-data", ["paired task bootstrap lower bound does not exceed minimum improvement"]
    elif bc == 0 and cc > 0:
        decision, reasons = "reject", ["positive cost against zero-cost baseline"]
    else:
        decision, reasons = "promote", ["all frozen task-level criteria satisfied"]
    return {"schema_version": 1, "baseline": baseline, "candidate": candidate,
            "synthetic": all(r["synthetic"] for r in selected) if selected else None,
            "evidence_type": "synthetic_software_validation" if selected and all(r["synthetic"] for r in selected) else "external_evaluator_records",
            "decision_applies_to": "demo_only" if selected and all(r["synthetic"] for r in selected) else "reviewed_experiment_only",
            "production_release_authorized": False,
            "expected_split": expected_split, "policy": policy, "decision": decision,
            "reasons": reasons, "metrics": metrics, "tasks": rows,
            "limitations": ["Bootstrap interval is descriptive, not a guarantee of unseen-task performance.",
                            "Promotion on synthetic fixtures only validates decision software.",
                            "Human-reviewed task/family assignments and an independent evaluator remain trust boundaries."]}

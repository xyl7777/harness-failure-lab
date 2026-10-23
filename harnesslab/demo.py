"""Scripted synthetic replay. Executes real processes; does not call an LLM."""
import csv
import html
import json
import platform
from pathlib import Path
import sys
from .analysis import PROTOCOL_HASH, compare_runs, diagnose, normalize_run
from .runner import validate_tests
from .storage import VersionStore, digest, freeze_tests, verify_freeze, write_json

FIXTURES = {
    "passed": "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)\n",
    "failed": "import unittest\nclass T(unittest.TestCase):\n def test_bad(self): self.assertEqual(2+2,5)\n",
    "zero_tests": "# Intentionally contains no tests.\n",
    "skipped_only": "import unittest\n@unittest.skip('synthetic skip')\nclass T(unittest.TestCase):\n def test_skip(self): pass\n",
    "timeout": "import unittest,time\nclass T(unittest.TestCase):\n def test_slow(self): time.sleep(30)\n",
    "import_error": "import definitely_missing_harnesslab_fixture_module\n",
    "unverified_exit_zero": "import os\nos._exit(0)\n",
    "process_error": "import os\nos._exit(7)\n",
}


def fixture_checks(root):
    results = []
    for expected, source in FIXTURES.items():
        path = Path(root) / expected
        path.mkdir(parents=True, exist_ok=True)
        (path / "test_case.py").write_text(source, encoding="utf-8")
        result = validate_tests(path, timeout_s=.25 if expected == "timeout" else 10)
        results.append({"fixture": expected, "expected_status": expected, "actual_status": result["status"],
                        "check_passed": result["status"] == expected, "result": result})
    return results


def candidate_configs():
    common = {"schema_version": 1, "scope": "synthetic-python-fixtures-only", "model_id": "scripted-no-llm",
              "candidate_design_families": ["dev-test-entry"], "final_tests_editable": False}
    return [
        {**common, "config_id": "baseline", "intervention": "none", "guidance": "Use the supplied test entry."},
        {**common, "config_id": "short-guidance", "intervention": "context", "guidance": "Check the repository version and test entry. Exit zero with no executed tests is not verification. Record collection and skip counts."},
        {**common, "config_id": "test-wrapper", "intervention": "tool", "tool": "harnesslab check-tests", "guidance": "Use the structured wrapper. Treat zero collection, skipped-only, timeout and missing results as unverified."},
    ]


def run_demo(output):
    out = Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("demo output must be a new or empty directory; choose another output path")
    out.mkdir(parents=True, exist_ok=True)
    checks = fixture_checks(out / "fixtures")
    write_json(out / "process_checks.json", checks)
    if not all(c["check_passed"] for c in checks):
        raise RuntimeError("fixture validation failed; inspect process_checks.json")
    configs = candidate_configs()
    versions = VersionStore(out / "config_versions")
    hashes = {c["config_id"]: versions.add(c) for c in configs}
    versions.activate(hashes["baseline"], "initial frozen baseline")
    write_json(out / "candidates.json", configs)
    tests_root = out / "frozen_final_tests"
    for i in range(12):
        task_dir = tests_root / ("case_%02d" % i)
        task_dir.mkdir(parents=True)
        (task_dir / "test_solution.py").write_text(
            "import unittest\nfrom solution import solve\nclass T(unittest.TestCase):\n"
            f" def test_positive(self): self.assertEqual(solve(3), {3+i})\n"
            f" def test_negative(self): self.assertEqual(solve(-3), {-3+i})\n", encoding="utf-8")
    freeze = freeze_tests(tests_root, out / "test_freeze.json")
    task_manifest = [{"task_id": "synthetic-%02d" % i, "family_id": "validation-family-%02d" % i,
                      "split": "validation", "base_commit": "fixture-v1", "synthetic": True}
                     for i in range(12)]
    write_json(out / "task_manifest.json", task_manifest)
    # This schedule is deliberately prescribed. It tests aggregation and gates, not model efficacy.
    success_limits = {"baseline": 5, "short-guidance": 7, "test-wrapper": 9}
    costs = {"baseline": .10, "short-guidance": .105, "test-wrapper": .11}
    runs = []
    for config in configs:
        cid = config["config_id"]
        for i, task in enumerate(task_manifest):
            for seed in (0, 1):
                rid = f"{cid}-task{i:02d}-seed{seed}"
                work = out / "workspaces" / rid
                work.mkdir(parents=True)
                scripted_correct = i < success_limits[cid]
                # Scripted stand-in for a patch, openly labelled; no agent is asked to solve it.
                offset = i if scripted_correct else i+1
                (work / "solution.py").write_text(f"def solve(x):\n    return x + {offset}\n", encoding="utf-8")
                verify_freeze(freeze)
                final = validate_tests(tests_root / ("case_%02d" % i), solution_dir=work)
                verify_freeze(freeze)
                write_json(out / "evaluations" / (rid + ".process.json"), final)
                evaluation = {"run_id": rid, "task_id": task["task_id"], "independent": True,
                              "evaluator": "separate unittest subprocess over unchanged frozen tests",
                              "resolved": final["resolved"], "tests_run": final["summary"]["tests_run"],
                              "skipped": final["summary"]["skipped"], "final_test_sha256": freeze["final_test_sha256"],
                              "evaluation_protocol_sha256": PROTOCOL_HASH,
                              "evidence_path": "evaluations/" + rid + ".process.json"}
                raw = checks[0 if scripted_correct or cid == "test-wrapper" else 2]["result"]
                event = {**raw["process"], "tests_run": raw["summary"]["tests_run"],
                         "skipped": raw["summary"]["skipped"], "synthetic_event_replay": True}
                events = [event] if cid == "test-wrapper" or scripted_correct else [event, dict(event)]
                run = normalize_run({**task, "run_id": rid, "repository": "local/synthetic-fixtures",
                    "config_id": cid, "config_sha256": hashes[cid], "seed": seed, "model_id": "scripted-no-llm",
                    "budget_usd": 1.0, "cost_usd": costs[cid]+seed*.01,
                    "claimed_complete": True, "task_input_sha256": digest(task),
                    "final_test_sha256": freeze["final_test_sha256"], "evaluation_protocol_sha256": PROTOCOL_HASH,
                    "events": events, "evaluation": evaluation, "candidate_design_families": ["dev-test-entry"]})
                runs.append(run)
    (out / "traces.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in runs), encoding="utf-8")
    diagnoses = [d for r in runs for d in diagnose(r)]
    write_json(out / "diagnoses.json", diagnoses)
    comparisons = {c: compare_runs(runs, "baseline", c) for c in ("short-guidance", "test-wrapper")}
    write_json(out / "comparison.json", comparisons)
    chosen = comparisons["test-wrapper"]
    # Exercise reject and needs-more-data without pretending these are separate experiments.
    bad = json.loads(json.dumps(runs))
    for r in bad:
        if r["config_id"] == "test-wrapper":
            r["evaluation"]["resolved"] = False
    decisions = {"primary": chosen, "insufficient_data_case": compare_runs(runs[:1], "baseline", "test-wrapper"),
                 "regression_case": compare_runs(bad, "baseline", "test-wrapper")}
    write_json(out / "decisions.json", decisions)
    with (out / "task_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["task_id", "repeats", "baseline_success_rate", "candidate_success_rate", "delta", "synthetic"])
        for row in chosen["tasks"]:
            writer.writerow([row["task_id"], row["repeats"], row["baseline"]["success_rate"], row["candidate"]["success_rate"], row["delta"], True])
    if chosen["decision"] == "promote":
        versions.activate(hashes["test-wrapper"], "synthetic demo gate passed; not real-agent approval")
    rollback = versions.rollback()
    write_json(out / "versions.json", {"hashes": hashes, "rollback_verified": rollback["active"] == hashes["baseline"], "state": rollback})
    example = out / "external_example"
    example.mkdir()
    trace = dict(runs[0])
    evaluation = trace.pop("evaluation")
    trace["evaluation"] = None
    trace.pop("evaluation_sha256", None)
    write_json(example / "trace.json", trace)
    write_json(example / "evaluation.json", evaluation)
    write_json(example / "command.json", {"workspace": str(out), "cwd": ".", "argv": [sys.executable, "-c", "print('external adapter smoke check')"], "timeout_s": 10})
    m = chosen["metrics"]
    report = ("# Synthetic software-validation report\n\n"
              "These outcomes are prescribed fixtures, not coding-agent efficacy or SWE-bench scores. "
              "No model API was called; synthetic costs are test inputs, not spending.\n\n"
              f"Process checks: {sum(c['check_passed'] for c in checks)}/{len(checks)}. "
              f"Replay: {len(runs)} runs, {len(task_manifest)} task identities, 2 seeds, 3 configs.\n\n"
              f"Wrapper gate: {chosen['decision']}; task-level delta = {m['delta']:.6f}; "
              f"bootstrap 95% interval = {m['delta_task_bootstrap_ci95']}.\n\n"
              "Exact task denominators, missing evidence and costs are in comparison.json. "
              "Final tests were hashed before and after every independent subprocess. "
              "Version rollback returned to baseline. Live Django/SWE-bench evaluation has not run.\n")
    (out / "report.md").write_text(report, encoding="utf-8")
    table = "".join("<tr>" + "".join("<td>"+html.escape(str(v))+"</td>" for v in [r["task_id"], r["repeats"], r["baseline"]["success_rate"], r["candidate"]["success_rate"], r["delta"]])+"</tr>" for r in chosen["tasks"])
    viewer = ("<!doctype html><html lang='en'><meta charset='utf-8'><title>HarnessLab review</title>"
              "<style>body{font:16px system-ui;max-width:1050px;margin:40px auto;padding:0 20px;color:#172339}"
              "th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;background:#f4f6fa;padding:20px}"
              "strong{color:#9b3300}summary{cursor:pointer}a{color:#1c5cad}</style>"
              "<h1>HarnessLab review</h1><p><strong>SYNTHETIC FIXTURES — NO LLM EFFICACY CLAIM</strong></p>"
              "<pre>"+html.escape(report)+"</pre><table><tr><th>Task</th><th>Repeats</th><th>Baseline</th><th>Wrapper</th><th>Delta</th></tr>"+table+"</table>"
              "<h2>Evidence review</h2><p><a href='comparison.json'>Full paired evidence</a> · <a href='process_checks.json'>Real subprocess checks</a> · <a href='traces.jsonl'>Traces</a> · <a href='versions.json'>Rollback</a></p>"
              "<details><summary>Diagnoses with evidence pointers</summary><pre>"+html.escape(json.dumps(diagnoses,indent=2))+"</pre></details></html>")
    (out / "review.html").write_text(viewer, encoding="utf-8")
    manifest = {"schema_version": 1, "synthetic": True, "model_api_called": False,
                "actual_api_spend_usd": 0, "python_version": platform.python_version(),
                "process_checks_passed": sum(c["check_passed"] for c in checks), "process_checks_total": len(checks),
                "runs": len(runs), "tasks": len(task_manifest), "repeats_per_task_config": 2, "config_count": len(configs),
                "diagnosis_count": len(diagnoses), "final_test_sha256": freeze["final_test_sha256"],
                "final_test_hash_verified": verify_freeze(freeze)["final_test_sha256"] == freeze["final_test_sha256"],
                "main_llm_experiment_run": False, "files": sorted(p.relative_to(out).as_posix() for p in out.iterdir() if p.is_file())}
    write_json(out / "manifest.json", manifest)
    return manifest

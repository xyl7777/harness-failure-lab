"""Run the real CLI and save exact stdout/stderr plus a machine-readable audit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from harnesslab.storage import digest, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="results/student_validation")
    parser.add_argument("--evidence", default="results/student_validation_logs")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output, evidence = (root / args.output).resolve(), (root / args.evidence).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    commands = []

    def run(label, argv, expected=0):
        result = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        (evidence / (label + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
        (evidence / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
        item = {"label": label, "argv": argv, "cwd": str(root), "exit_code": result.returncode,
                "expected_exit_code": expected, "matched_expectation": result.returncode == expected,
                "stdout_file": str(evidence / (label + ".stdout.txt")), "stderr_file": str(evidence / (label + ".stderr.txt"))}
        commands.append(item)
        print(label + ": exit=" + str(result.returncode) + " expected=" + str(expected))
        if result.returncode != expected:
            raise RuntimeError(label + " failed: " + result.stderr)
        return result

    unit = run("unit_tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    prefix = [sys.executable, "-m", "harnesslab"]
    run("demo", prefix + ["demo", "--output", str(output)])
    run("replay", prefix + ["replay", "--traces", str(output / "traces.jsonl"), "--output", str(output / "replayed_diagnoses.json")])
    run("compare", prefix + ["compare", "--traces", str(output / "traces.jsonl"), "--freeze", str(output / "test_freeze.json"), "--output", str(output / "replayed_comparison.json")])
    run("external_command", prefix + ["run-command", "--config", str(output / "external_example/command.json"), "--freeze", str(output / "test_freeze.json"), "--output", str(output / "external_command.json")])
    run("import_run", prefix + ["import-run", "--trace", str(output / "external_example/trace.json"), "--evaluation", str(output / "external_example/evaluation.json"), "--freeze", str(output / "test_freeze.json"), "--output", str(output / "imported")])
    run("check_passed", prefix + ["check-tests", "--tests", str(output / "fixtures/passed"), "--output", str(output / "check_passed.json")])
    run("check_zero", prefix + ["check-tests", "--tests", str(output / "fixtures/zero_tests"), "--output", str(output / "check_zero.json")], expected=2)
    count = int(re.search(r"Ran (\d+) tests", unit.stderr).group(1))
    manifest = read_json(output / "manifest.json")
    comparisons = read_json(output / "comparison.json")
    source = root / "results/public_metadata/source_manifest.json"
    files = sorted(p for folder in (root / "harnesslab", root / "tests") for p in folder.glob("*.py")) + [Path(__file__).resolve()]
    code_hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    summary = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS",
               "python_version": platform.python_version(), "platform": platform.platform(),
               "unit_tests_passed": count, "unit_tests_failed": 0, "cli_checks_passed": len(commands),
               "process_fixture_checks": {"passed": manifest["process_checks_passed"], "total": manifest["process_checks_total"]},
               "synthetic_replay": {"tasks": manifest["tasks"], "runs": manifest["runs"], "repeats": 2, "configs": 3,
                                    "diagnoses": manifest["diagnosis_count"], "actual_api_spend_usd": 0,
                                    "baseline_task_mean_success_rate": comparisons["test-wrapper"]["metrics"]["baseline"]["task_mean_success_rate"],
                                    "guidance_decision": comparisons["short-guidance"]["decision"],
                                    "wrapper_decision": comparisons["test-wrapper"]["decision"],
                                    "wrapper_delta": comparisons["test-wrapper"]["metrics"]["delta"],
                                    "wrapper_task_bootstrap_ci95": comparisons["test-wrapper"]["metrics"]["delta_task_bootstrap_ci95"],
                                    "warning": "Task outcomes and cost inputs are scripted. These are software checks, not LLM efficacy measurements."},
               "final_tests_unchanged": manifest["final_test_hash_verified"],
               "rollback_verified": read_json(output / "versions.json")["rollback_verified"],
               "main_llm_experiment_run": False, "live_django_environment_reproduced": False,
               "real_agent_release_authorized": False, "demo_artifacts": str(output),
               "public_metadata": read_json(source) if source.exists() else {"downloaded": False},
               "commands": commands, "source_code_sha256": code_hashes, "source_bundle_sha256": digest(code_hashes),
               "limitations": ["Trusted local subprocesses are not an untrusted-code sandbox.",
                               "External adapter was checked with a harmless Python command and synthetic exports; no model or SWE-bench runner was executed.",
                               "No causal effect of short guidance or test wrapper was measured.",
                               "Metadata download is not task reproduction."]}
    write_json(evidence / "runtime_validation.json", summary)
    print("validation=PASS unit_tests=" + str(count) + " cli_checks=" + str(len(commands)))
    print("evidence=" + str(evidence / "runtime_validation.json"))


if __name__ == "__main__":
    main()

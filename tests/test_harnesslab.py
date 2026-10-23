import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.error

from harnesslab.analysis import PROTOCOL_HASH, compare_runs, diagnose, evidence_pass, normalize_run
from harnesslab.demo import fixture_checks
from harnesslab.external import import_run, run_command
from harnesslab.metadata import FIELDS, allowlist_row, download_metadata
from harnesslab.runner import run_process
from harnesslab.storage import VersionStore, digest, freeze_tests, inside, read_json, safe_id, verify_freeze, write_json


def records(tasks=12, repeats=2):
    result = []
    for i in range(tasks):
        for seed in range(repeats):
            for cid in ("baseline", "test-wrapper"):
                rid = f"{cid}-{i}-{seed}"
                resolved = i < (5 if cid == "baseline" else 9)
                e = {"run_id": rid, "task_id": f"task-{i}", "independent": True, "resolved": resolved,
                     "tests_run": 2, "skipped": 0, "final_test_sha256": "f"*64,
                     "evaluation_protocol_sha256": PROTOCOL_HASH}
                result.append({"run_id": rid, "task_id": f"task-{i}", "family_id": f"family-{i}",
                               "repository": "fixture/test", "base_commit": "v1", "split": "validation",
                               "config_id": cid, "config_sha256": digest(cid), "seed": seed,
                               "model_id": "scripted", "budget_usd": 1., "cost_usd": .10,
                               "claimed_complete": True, "task_input_sha256": digest(i),
                               "final_test_sha256": "f"*64, "evaluation_protocol_sha256": PROTOCOL_HASH,
                               "events": [], "evaluation": e, "synthetic": True, "candidate_design_families": ["dev-only"]})
    return result


class ProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.checks = {c["fixture"]: c for c in fixture_checks(cls.temp.name)}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_eight_subprocess_outcomes(self):
        for name, case in self.checks.items():
            with self.subTest(name=name):
                self.assertEqual(case["actual_status"], case["expected_status"])

    def test_zero_collection_is_not_pass(self):
        r = self.checks["zero_tests"]["result"]
        self.assertEqual(r["process"]["return_code"], 0)
        self.assertFalse(r["resolved"])

    def test_skipped_only_is_not_pass(self):
        self.assertFalse(self.checks["skipped_only"]["result"]["resolved"])

    def test_false_positive_exit_zero_without_result(self):
        r = self.checks["unverified_exit_zero"]["result"]
        self.assertEqual(r["process"]["return_code"], 0)
        self.assertIsNone(r["summary"])
        self.assertFalse(r["resolved"])

    def test_timeout_is_explicit(self):
        self.assertTrue(self.checks["timeout"]["result"]["process"]["timed_out"])

    def test_output_capture_is_bounded(self):
        r = run_process([sys.executable, "-c", "print('x'*10000)"], self.temp.name, max_output_bytes=100)
        self.assertTrue(r["truncated"])
        self.assertEqual(len(r["stdout"]), 100)

    def test_missing_executable_does_not_pass(self):
        r = run_process(["/definitely/missing/harnesslab"], self.temp.name)
        self.assertTrue(r["launch_error"])
        self.assertIsNone(r["return_code"])


class ComparisonTests(unittest.TestCase):
    def test_complete_scripted_improvement_promotes_demo_only(self):
        result = compare_runs(records(), "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "promote")
        self.assertEqual(result["metrics"]["task_count"], 12)
        self.assertEqual(result["metrics"]["paired_run_count"], 24)
        self.assertAlmostEqual(result["metrics"]["delta"], 4/12)
        self.assertEqual(result["decision_applies_to"], "demo_only")
        self.assertFalse(result["production_release_authorized"])

    def test_incomplete_pair_needs_more_data(self):
        result = compare_runs(records()[:-1], "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "needs-more-data")
        self.assertTrue(any("incomplete pair" in s for s in result["reasons"]))

    def test_missing_ground_truth_never_passes(self):
        runs = records(); runs[-1]["evaluation"] = None
        self.assertFalse(evidence_pass(runs[-1]))
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "needs-more-data")

    def test_missing_candidate_truth_not_classified_as_regression(self):
        runs = records(); runs[1]["evaluation"] = None
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "needs-more-data")
        self.assertEqual(result["metrics"]["regressed_tasks"], 0)
        self.assertEqual(result["metrics"]["paired_run_count"], 23)

    def test_malformed_evaluation_and_invalid_policy_rejected(self):
        runs = records(); runs[0]["evaluation"] = "pass"
        with self.assertRaisesRegex(ValueError, "object or null"): compare_runs(runs, "baseline", "test-wrapper")
        for policy in ({"bootstrap_samples": 0}, {"max_cost_ratio": float("nan")}, {"min_tasks": True}):
            with self.assertRaises(ValueError): compare_runs(records(), "baseline", "test-wrapper", policy)

    def test_budget_breach_is_explicit(self):
        runs = records(); runs[-1]["cost_usd"] = 2.0
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "reject")
        self.assertTrue(any("exceeded per-run budget" in reason for reason in result["reasons"]))

    def test_zero_or_skip_evaluator_counts_not_success(self):
        for n, skip in ((0, 0), (2, 2), (1, -1)):
            run = records()[1]; run["evaluation"].update(resolved=True, tests_run=n, skipped=skip)
            self.assertFalse(evidence_pass(run))

    def test_repeats_do_not_inflate_task_count(self):
        result = compare_runs(records(tasks=3, repeats=8), "baseline", "test-wrapper")
        self.assertEqual(result["metrics"]["task_count"], 3)
        self.assertEqual(result["metrics"]["paired_run_count"], 24)
        self.assertEqual(result["decision"], "needs-more-data")

    def test_task_mean_not_pooled_repeat_mean(self):
        runs = records()
        # Add many identical repeats of one improved task: delta must remain four twelfths.
        for r in records(tasks=6, repeats=10):
            if r["task_id"] == "task-5" and r["seed"] >= 2:
                runs.append(r)
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertAlmostEqual(result["metrics"]["delta"], 4/12)

    def test_source_split_rejected(self):
        runs = records(); runs[-1]["split"] = "dev"
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_design_family_leakage_rejected(self):
        runs = records(); runs[-1]["candidate_design_families"] = [runs[-1]["family_id"]]
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_changed_final_tests_rejected(self):
        runs = records(); runs[-1]["evaluation"]["final_test_sha256"] = "changed"
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_changed_model_or_config_rejected(self):
        for key in ("model_id", "config_sha256", "base_commit", "task_input_sha256"):
            runs = records(); runs[-1][key] = "changed"
            self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_changed_provider_version_rejected(self):
        runs = records()
        runs[-1]["model_spec"] = {"provider": "different", "version": "v2", "settings_sha256": digest({})}
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_unknown_cost_is_not_zero(self):
        runs = records(); runs[-1]["cost_usd"] = None
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "needs-more-data")
        self.assertIsNone(result["metrics"]["candidate"]["all_selected_run_cost_total_usd"])
        for r in runs: r["cost_usd"] = 0
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "promote")
        self.assertEqual(result["metrics"]["candidate"]["cost_mean_usd"], 0)

    def test_cost_overrun_and_regression_rejected(self):
        runs = records()
        for r in runs:
            if r["config_id"] == "test-wrapper": r["cost_usd"] = .20
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")
        runs = records()
        for r in runs:
            if r["config_id"] == "test-wrapper" and r["task_id"] == "task-0": r["evaluation"]["resolved"] = False
        result = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(result["decision"], "reject")
        self.assertEqual(result["metrics"]["regression_denominator_baseline_positive_tasks"], 5)

    def test_bootstrap_reproducible_and_no_gain_inconclusive(self):
        runs = records()
        a = compare_runs(runs, "baseline", "test-wrapper")
        b = compare_runs(runs, "baseline", "test-wrapper")
        self.assertEqual(a["metrics"]["delta_task_bootstrap_ci95"], b["metrics"]["delta_task_bootstrap_ci95"])
        for r in runs: r["evaluation"]["resolved"] = True
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "needs-more-data")

    def test_duplicate_observation_rejected(self):
        runs = records(); runs.append(copy.deepcopy(runs[-1]))
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")

    def test_synthetic_real_mix_rejected(self):
        runs = records(); runs[-1]["synthetic"] = False
        runs[-1]["model_spec"] = {"provider": "example", "version": "pinned-v1", "settings_sha256": digest({})}
        self.assertEqual(compare_runs(runs, "baseline", "test-wrapper")["decision"], "reject")


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def frozen(self):
        p = self.root / "tests"; p.mkdir()
        (p / "test_fixed.py").write_text("# fixed final test artifact\n")
        return freeze_tests(p, self.root / "freeze.json")

    def test_path_traversal_and_symlink_escape(self):
        for value in ("../escape", "/tmp/x", "a/b", "..", "a..b"):
            with self.assertRaises(ValueError): safe_id(value)
        with self.assertRaises(ValueError): inside(self.root, "../escape")
        (self.root / "link").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError): inside(self.root, "link/escape")

    def test_final_test_immutability(self):
        freeze = self.frozen(); verify_freeze(freeze)
        (self.root / "tests" / "test_fixed.py").write_text("# altered\n")
        with self.assertRaisesRegex(ValueError, "final tests changed"): verify_freeze(freeze)
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"): freeze_tests(self.root / "tests", self.root / "freeze.json")

    def test_version_rollback_and_tamper_detection(self):
        store = VersionStore(self.root / "versions")
        a = store.add({"config_id": "a", "x": 1}); b = store.add({"config_id": "b", "x": 2})
        store.activate(a, "start"); store.activate(b, "tested")
        self.assertEqual(store.rollback()["active"], a)
        write_json(self.root / "versions" / (b+".json"), {"config_id": "b", "x": 99})
        with self.assertRaisesRegex(ValueError, "hash mismatch"): store.activate(b, "tampered")

    def test_metadata_allowlist_excludes_gold_and_hints(self):
        row = {k: "public" for k in FIELDS}
        row.update(patch="secret-gold", test_patch="hidden", hints_text="hint", FAIL_TO_PASS=["gold-name"])
        clean = allowlist_row(row)
        self.assertEqual(set(clean), set(FIELDS))
        self.assertNotIn("secret-gold", json.dumps(clean))

    def test_certificate_fallback_preserves_tls_and_allowlist(self):
        row = {k: "public" for k in FIELDS}; row["repo"] = "django/django"; row["patch"] = "hidden"
        payload = json.dumps({"rows": [{"row": row}], "num_rows_total": 1}).encode()
        completed = subprocess.CompletedProcess([], 0, payload, b"")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("CERTIFICATE_VERIFY_FAILED")), mock.patch("shutil.which", return_value="/usr/bin/curl"), mock.patch("subprocess.run", return_value=completed) as run:
            result = download_metadata(self.root / "metadata", 1)
        argv = run.call_args[0][0]
        self.assertNotIn("-k", argv); self.assertNotIn("--insecure", argv)
        self.assertIn("=https", argv)
        self.assertEqual(result["downloaded_rows"], 1)
        self.assertNotIn("patch", read_json(self.root / "metadata" / "tasks_metadata.json")[0])

    def test_import_separate_evaluation_append_only(self):
        freeze = self.frozen(); run = records()[0]
        run["final_test_sha256"] = freeze["final_test_sha256"]
        evaluation = run.pop("evaluation"); evaluation["final_test_sha256"] = freeze["final_test_sha256"]
        write_json(self.root / "trace.json", run); write_json(self.root / "eval.json", evaluation)
        args = (self.root / "trace.json", self.root / "eval.json", self.root / "freeze.json", self.root / "imported")
        path = import_run(*args)
        self.assertEqual(read_json(path)["evaluation"], evaluation)
        with self.assertRaisesRegex(ValueError, "already imported"): import_run(*args)

    def test_trace_cannot_self_grade(self):
        freeze = self.frozen(); run = records()[0]
        run["final_test_sha256"] = freeze["final_test_sha256"]
        write_json(self.root / "trace.json", run); write_json(self.root / "eval.json", run["evaluation"])
        with self.assertRaisesRegex(ValueError, "own final evaluation"):
            import_run(self.root / "trace.json", self.root / "eval.json", self.root / "freeze.json", self.root / "out")

    def test_command_detects_changed_final_test_artifact(self):
        self.frozen()
        argv = [sys.executable, "-c", "from pathlib import Path; Path('tests/test_fixed.py').write_text('changed')"]
        write_json(self.root / "cmd.json", {"workspace": str(self.root), "argv": argv})
        with self.assertRaisesRegex(ValueError, "final tests changed"):
            run_command(self.root / "cmd.json", self.root / "out.json", self.root / "freeze.json")

    def test_command_rejects_cwd_escape(self):
        self.frozen()
        write_json(self.root / "cmd.json", {"workspace": str(self.root), "cwd": "../", "argv": [sys.executable, "--version"]})
        with self.assertRaisesRegex(ValueError, "cwd escapes"):
            run_command(self.root / "cmd.json", self.root / "out.json", self.root / "freeze.json")

    def test_final_holdout_cli_is_one_shot(self):
        freeze = self.frozen(); runs = records()
        for r in runs:
            r["split"] = "final"
            r["final_test_sha256"] = freeze["final_test_sha256"]
            r["evaluation"]["final_test_sha256"] = freeze["final_test_sha256"]
        write_json(self.root / "runs.json", runs)
        argv = [sys.executable, "-m", "harnesslab", "compare", "--traces", str(self.root / "runs.json"),
                "--freeze", str(self.root / "freeze.json"), "--split", "final", "--final-ledger", str(self.root / "ledger.json"),
                "--output", str(self.root / "decision.json")]
        cwd = Path(__file__).resolve().parents[1]
        first = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        second = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 1)
        self.assertIn("already consumed", second.stderr)

    def test_diagnoses_link_to_exact_evidence(self):
        run = records()[0]
        event = {"argv": ["python", "wrong.py"], "return_code": 1, "stderr": "ImportError: missing", "tests_run": 0}
        run["events"] = [event, event]
        ds = diagnose(run)
        self.assertIn("repeated_failed_command", [d["category"] for d in ds])
        self.assertTrue(all(d["evidence"][0].startswith("traces.jsonl#") for d in ds))

    def test_nonfinite_cost_rejected(self):
        for bad in (float("nan"), -1, True, float("inf")):
            run = records()[0]; run["cost_usd"] = bad
            with self.assertRaises(ValueError): normalize_run(run)


if __name__ == "__main__":
    unittest.main()

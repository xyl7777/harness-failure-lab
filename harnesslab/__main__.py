"""python -m harnesslab --help"""
import argparse
import json
from pathlib import Path
import sys
from .analysis import compare_runs, diagnose
from .demo import run_demo
from .external import import_run, run_command
from .metadata import download_metadata
from .runner import validate_tests
from .storage import VersionStore, read_json, verify_freeze, write_json


def load_runs(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    obj = read_json(path)
    return obj if isinstance(obj, list) else [obj]


def main():
    parser = argparse.ArgumentParser(description="Auditable coding-agent harness reference. Offline demo is synthetic.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("demo"); p.add_argument("--output", required=True)
    p = sub.add_parser("check-tests"); p.add_argument("--tests", required=True); p.add_argument("--timeout", type=float, default=10); p.add_argument("--output", required=True)
    p = sub.add_parser("replay"); p.add_argument("--traces", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("compare"); p.add_argument("--traces", required=True); p.add_argument("--baseline", default="baseline"); p.add_argument("--candidate", default="test-wrapper"); p.add_argument("--split", choices=["validation", "final"], default="validation"); p.add_argument("--freeze", required=True); p.add_argument("--output", required=True); p.add_argument("--final-ledger")
    p = sub.add_parser("import-run"); p.add_argument("--trace", required=True); p.add_argument("--evaluation", required=True); p.add_argument("--freeze", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("run-command"); p.add_argument("--config", required=True); p.add_argument("--freeze", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("download-metadata"); p.add_argument("--output", required=True); p.add_argument("--limit", type=int, default=20); p.add_argument("--repository", default="django/django")
    p = sub.add_parser("rollback"); p.add_argument("--versions", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "demo":
            m = run_demo(args.output)
            print(f"process_checks={m['process_checks_passed']}/{m['process_checks_total']}")
            print(f"synthetic_runs={m['runs']} tasks={m['tasks']} repeats={m['repeats_per_task_config']} configs={m['config_count']}")
            print("final_tests_unchanged=true main_llm_experiment_run=false")
            print("artifacts=" + str(Path(args.output).resolve()))
        elif args.cmd == "check-tests":
            r = validate_tests(args.tests, args.timeout); write_json(args.output, r)
            print("status=" + r["status"] + " resolved=" + str(r["resolved"]).lower())
            return 0 if r["resolved"] else 2
        elif args.cmd == "replay":
            runs = load_runs(args.traces)
            d = [v for r in runs for v in diagnose(r)]
            write_json(args.output, d); print(f"runs={len(runs)} diagnoses={len(d)}")
        elif args.cmd == "compare":
            freeze = verify_freeze(args.freeze)
            runs = load_runs(args.traces)
            if any(r["final_test_sha256"] != freeze["final_test_sha256"] for r in runs):
                raise ValueError("trace final test hash differs from frozen artifact")
            ledger = None
            if args.split == "final":
                if not args.final_ledger:
                    raise ValueError("final comparison requires --final-ledger")
                ledger = Path(args.final_ledger)
                if ledger.exists():
                    raise ValueError("final holdout already consumed; use new held-out tasks in next cycle")
                ledger.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation makes the local one-shot guard atomic. Human governance is still required.
                with ledger.open("x", encoding="utf-8") as f:
                    json.dump({"state": "consumed", "final_test_sha256": freeze["final_test_sha256"], "candidate": args.candidate}, f)
            result = compare_runs(runs, args.baseline, args.candidate, expected_split=args.split)
            write_json(args.output, result)
            print("decision=" + result["decision"] + " tasks=" + str(result["metrics"]["task_count"]) + " scope=" + result["decision_applies_to"])
        elif args.cmd == "import-run":
            path = import_run(args.trace, args.evaluation, args.freeze, args.output)
            print("imported=" + str(path.resolve()))
        elif args.cmd == "run-command":
            r = run_command(args.config, args.output, args.freeze)
            print("return_code="+str(r["return_code"])+" timed_out="+str(r["timed_out"]).lower()+" evaluated=false")
            return 0 if r["return_code"] == 0 and not r["timed_out"] else 2
        elif args.cmd == "download-metadata":
            r = download_metadata(args.output, args.limit, args.repository)
            print(f"metadata_rows={r['downloaded_rows']} source_split=test gold_fields_saved=false")
        elif args.cmd == "rollback":
            r = VersionStore(args.versions).rollback(); print("active=" + r["active"])
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

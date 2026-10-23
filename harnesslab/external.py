"""Reviewed external commands and separately exported evaluator records."""
import hashlib
from pathlib import Path
from .analysis import normalize_run, PROTOCOL_HASH
from .runner import run_process
from .storage import inside, read_json, verify_freeze, write_json


def import_run(trace_path, evaluation_path, freeze_path, output):
    freeze = verify_freeze(freeze_path)
    trace = read_json(trace_path)
    if trace.get("evaluation") is not None:
        raise ValueError("trace must not supply its own final evaluation")
    evaluation = read_json(evaluation_path)
    if evaluation.get("independent") is not True:
        raise ValueError("evaluation must be independently exported")
    for name in ("run_id", "task_id"):
        if evaluation.get(name) != trace.get(name):
            raise ValueError("evaluation does not match trace " + name)
    if trace.get("final_test_sha256") != freeze["final_test_sha256"] or evaluation.get("final_test_sha256") != freeze["final_test_sha256"]:
        raise ValueError("final test evidence hash mismatch")
    if evaluation.get("evaluation_protocol_sha256") != PROTOCOL_HASH:
        raise ValueError("unsupported independent evaluation protocol")
    # Preserve evaluator provenance. A supplied declaration is not proof of process isolation.
    trace["evaluation"] = evaluation
    run = normalize_run(trace)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    run_file = inside(output, run["run_id"] + ".json")
    if run_file.exists():
        raise ValueError("run_id already imported; evidence is append-only")
    write_json(run_file, run)
    write_json(inside(output, run["run_id"] + ".provenance.json"), {
        "trace_sha256": hashlib.sha256(Path(trace_path).read_bytes()).hexdigest(),
        "evaluation_sha256": hashlib.sha256(Path(evaluation_path).read_bytes()).hexdigest(),
        "final_test_sha256": freeze["final_test_sha256"],
        "trust_boundary": "Evaluator export must be produced outside the agent. This importer validates linkage, not isolation.",
    })
    return run_file


def run_command(config_path, output, freeze_path):
    config = read_json(config_path)
    freeze = verify_freeze(freeze_path)
    workspace = Path(config["workspace"]).resolve()
    cwd = (workspace / config.get("cwd", ".")).resolve()
    if cwd != workspace and workspace not in cwd.parents:
        raise ValueError("command cwd escapes workspace")
    if not cwd.is_dir():
        raise ValueError("command cwd does not exist")
    # argv is a reviewed JSON array, never interpreted by a shell.
    result = run_process(config["argv"], cwd, config.get("timeout_s", 60))
    verify_freeze(freeze)
    write_json(output, {"schema_version": 1, "process": result,
                        "final_test_sha256": freeze["final_test_sha256"],
                        "evaluation": None, "notice": "Execution is not a task-success evaluation."})
    return result

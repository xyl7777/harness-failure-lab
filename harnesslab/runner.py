"""Bounded process execution and strict test-result semantics; not an OS sandbox."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from .storage import read_json


def run_process(argv, cwd, timeout_s=10, max_output_bytes=200000):
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("argv must be a nonempty list of strings; shell commands are not accepted")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    start = time.monotonic()
    timed_out = False
    # Disk-backed streams avoid unbounded pipe buffering for chatty commands.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            process = subprocess.Popen(argv, cwd=str(cwd), stdout=out, stderr=err,
                                       start_new_session=(os.name == "posix"),
                                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        except OSError as exc:
            return {"argv": argv, "cwd": str(Path(cwd).resolve()), "return_code": None,
                    "timed_out": False, "stdout": "", "stderr": str(exc),
                    "truncated": False, "elapsed_s": time.monotonic()-start, "launch_error": True}
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.wait()
        streams, truncated = [], False
        for stream in (out, err):
            stream.seek(0)
            raw = stream.read(max_output_bytes + 1)
            truncated |= len(raw) > max_output_bytes
            streams.append(raw[:max_output_bytes].decode("utf-8", errors="replace"))
    return {"argv": argv, "cwd": str(Path(cwd).resolve()), "return_code": process.returncode,
            "timed_out": timed_out, "stdout": streams[0], "stderr": streams[1],
            "truncated": truncated, "elapsed_s": round(time.monotonic()-start, 6), "launch_error": False}


def validate_tests(tests_dir, timeout_s=10, solution_dir=None):
    tests_dir = Path(tests_dir).resolve()
    if not tests_dir.is_dir():
        raise ValueError("test directory missing")
    with tempfile.TemporaryDirectory(prefix="harnesslab-result-") as scratch:
        result_file = Path(scratch) / "result.json"
        argv = [sys.executable, str(Path(__file__).with_name("test_worker.py")), str(tests_dir), str(result_file)]
        if solution_dir:
            argv.append(str(Path(solution_dir).resolve()))
        process = run_process(argv, solution_dir or tests_dir, timeout_s)
        summary = read_json(result_file) if result_file.exists() else None
    if process["timed_out"]:
        status = "timeout"
    elif summary is None:
        status = "unverified_exit_zero" if process["return_code"] == 0 else "process_error"
    elif summary["tests_run"] == 0:
        status = "zero_tests"
    elif summary["skipped"] == summary["tests_run"]:
        status = "skipped_only"
    elif "ModuleNotFoundError" in process["stderr"] or "ImportError" in process["stderr"]:
        status = "import_error"
    elif not summary["successful"] or process["return_code"] != 0:
        status = "failed"
    elif summary["tests_run"] - summary["skipped"] - summary["expected_failures"] <= 0:
        status = "no_verified_success"
    else:
        status = "passed"
    return {"status": status, "resolved": status == "passed", "summary": summary, "process": process}

"""Independent unittest collector. Its result file is separate from stdout."""
import json
from pathlib import Path
import sys
import unittest


def main():
    tests_dir, result_path = map(Path, sys.argv[1:3])
    if len(sys.argv) > 3:
        sys.path.insert(0, str(Path(sys.argv[3]).resolve()))
    suite = unittest.defaultTestLoader.discover(str(tests_dir), pattern="test*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    result_path.write_text(json.dumps({
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "successful": result.wasSuccessful(),
    }), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()

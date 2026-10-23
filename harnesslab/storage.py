"""Canonical JSON, safe artifact paths, frozen test fingerprints and versions."""
import hashlib
import json
import re
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", value) or ".." in value:
        raise ValueError("unsafe identifier / path traversal")
    return value


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError("path escapes artifact root")
    return path


def tree_hash(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("frozen test directory missing")
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink not allowed in frozen tests")
        if path.is_file() and "__pycache__" not in path.parts:
            records.append([path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    if not records:
        raise ValueError("frozen test directory empty")
    return digest(records)


def freeze_tests(tests, destination):
    value = {"schema_version": 1, "tests_dir": str(Path(tests).resolve()), "final_test_sha256": tree_hash(tests)}
    if Path(destination).exists() and read_json(destination) != value:
        raise ValueError("refusing to overwrite a changed test freeze")
    write_json(destination, value)
    return value


def verify_freeze(freeze):
    value = read_json(freeze) if not isinstance(freeze, dict) else freeze
    if tree_hash(value["tests_dir"]) != value["final_test_sha256"]:
        raise ValueError("final tests changed after freeze")
    return value


class VersionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(self, config):
        safe_id(config["config_id"])
        key = digest(config)
        path = inside(self.root, key + ".json")
        if path.exists() and read_json(path) != config:
            raise ValueError("immutable version collision")
        write_json(path, config)
        return key

    def activate(self, key, reason):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("invalid version hash")
        config = read_json(inside(self.root, key + ".json"))
        if digest(config) != key:
            raise ValueError("version content hash mismatch")
        state_path = self.root / "state.json"
        state = read_json(state_path) if state_path.exists() else {"active": None, "history": []}
        state["history"].append({"previous": state["active"], "active": key, "reason": reason})
        state["active"] = key
        write_json(state_path, state)
        return state

    def rollback(self):
        state = read_json(self.root / "state.json")
        previous = state["history"][-1]["previous"]
        if previous is None:
            raise ValueError("no previous version to restore")
        return self.activate(previous, "explicit rollback")

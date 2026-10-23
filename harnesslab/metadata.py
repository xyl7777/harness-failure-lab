"""Stream a bounded dataset-server response; persist allowlisted metadata only."""
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import subprocess
import urllib.parse
import urllib.error
import urllib.request
from .storage import digest, write_json

DATASET = "princeton-nlp/SWE-bench_Lite"
FIELDS = ("instance_id", "repo", "base_commit", "problem_statement", "created_at", "version")
FORBIDDEN = ("patch", "test_patch", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS")


def allowlist_row(row):
    missing = set(FIELDS)-set(row)
    if missing:
        raise ValueError("dataset metadata missing fields: " + ",".join(sorted(missing)))
    return {k: row[k] for k in FIELDS}


def download_metadata(output, limit=20, repository="django/django"):
    if not 1 <= limit <= 300:
        raise ValueError("limit must be between 1 and 300")
    rows, urls, transports, offset = [], [], [], 0
    total = None
    while len(rows) < limit and (total is None or offset < total):
        query = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "test", "offset": offset, "length": 50})
        url = "https://datasets-server.huggingface.co/rows?" + query
        request = urllib.request.Request(url, headers={"User-Agent": "HarnessLab-reference/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(12_000_001)
            transports.append("python urllib with TLS verification")
        except urllib.error.URLError as exc:
            # macOS Python installations may lack a configured CA bundle. System curl
            # can use the OS trust store. Never pass -k or disable verification.
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc) or not shutil.which("curl"):
                raise
            completed = subprocess.run([shutil.which("curl"), "--fail", "--silent", "--show-error",
                "--proto", "=https", "--tlsv1.2", "--max-time", "30", "--max-filesize", "12000000", url],
                capture_output=True, timeout=35, check=False)
            if completed.returncode != 0:
                raise ValueError("TLS-verified curl metadata download failed: " + completed.stderr.decode(errors="replace")[:500])
            body = completed.stdout
            transports.append("system curl TLS verification (Python CA fallback)")
        if len(body) > 12_000_000:
            raise ValueError("dataset response exceeds bounded download limit")
        page = json.loads(body)
        total = page.get("num_rows_total", 300)
        urls.append(url)
        page_rows = page.get("rows", [])
        if not page_rows:
            break
        for item in page_rows:
            row = item["row"]
            if repository is None or row["repo"] == repository:
                rows.append(allowlist_row(row))
                if len(rows) == limit:
                    break
        offset += len(page_rows)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "tasks_metadata.json", rows)
    manifest = {"dataset": DATASET, "dataset_page": "https://huggingface.co/datasets/" + DATASET,
                "source_urls": urls, "transports": transports, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "upstream_split": "test", "repository_filter": repository, "requested_limit": limit,
                "downloaded_rows": len(rows), "metadata_sha256": digest(rows), "allowlisted_fields": list(FIELDS),
                "excluded_fields": list(FORBIDDEN), "metadata_only": True,
                "limitations": "Public historical issue metadata, not reproduced tasks. Upstream row endpoint is mutable; local snapshot hash pins this copy. Responses may contain excluded fields in memory; they are never persisted or forwarded."}
    write_json(output / "source_manifest.json", manifest)
    return manifest

"""Verify the false-accept test rejects a mutant, without leaving stale bytecode."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/evalsentinel/report.py"
CACHE = Path(importlib.util.cache_from_source(str(SOURCE)))
if not CACHE.resolve().is_relative_to(ROOT):
    raise RuntimeError("Refusing to clear a cache outside this project")

original = SOURCE.read_bytes()
needle = b'if focus["status"] == "SUCCESS":'
if original.count(needle) != 1:
    raise RuntimeError("Expected exactly one mutation site")

try:
    CACHE.unlink(missing_ok=True)
    SOURCE.write_bytes(original.replace(needle, b'if focus["status"] != "SUCCESS":'))
    # The argv is fixed and uses the interpreter selected by uv for this project.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_report.py", "--no-cov", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
finally:
    SOURCE.write_bytes(original)
    CACHE.unlink(missing_ok=True)

record = {
    "mutation": "Invert the target-check false-accept condition",
    "exit_code": result.returncode,
    "killed": result.returncode == 1 and "test_bad_behavior_accepted_by_target" in result.stdout,
    "original_sha256": hashlib.sha256(original).hexdigest(),
    "restored_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    "bytecode_cache_cleared": not CACHE.exists(),
}
output = ROOT / "runs"
output.mkdir(exist_ok=True)
(output / "checker-mutation.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
(output / "checker-mutation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
print(json.dumps(record, indent=2))
if not record["killed"] or record["original_sha256"] != record["restored_sha256"]:
    raise RuntimeError("Mutation verification or source restoration failed")

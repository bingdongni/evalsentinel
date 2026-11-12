"""Audit the native baseline and proposed single-use fix without porting either."""

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalsentinel import __version__
from evalsentinel.owasp_catalog import REVISIONS, corpus
from evalsentinel.process import run_process
from evalsentinel.report import summarize, write_report

MAX_TIMEOUT = 60


def provenance(checkout: Path, revision: str) -> dict[str, Any]:
    if revision not in REVISIONS:
        raise ValueError("Select baseline or candidate")
    source = _verified_checkout(checkout, corpus()["pins"][revision], revision)
    return {
        **source,
        "repository": "https://github.com/OWASP/Agent-Security-Regression-Harness",
        "policy_source": corpus()["policy_source"],
        "candidate_source": corpus()["candidate_source"],
    }


def target_provenance(checkout: Path, expected_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit):
        raise ValueError("--expected-commit must be a full 40-hex Git commit")
    return {
        **_verified_checkout(checkout, expected_commit.lower(), "target"),
        "kind": "user-selected-git-checkout",
        "reference_repository": "https://github.com/OWASP/Agent-Security-Regression-Harness",
        "policy_source": corpus()["policy_source"],
    }


def _verified_checkout(checkout: Path, pin: str, revision: str) -> dict[str, Any]:
    checkout = checkout.resolve()
    git = shutil.which("git")
    if not git:
        raise ValueError("Git is required to verify the native OWASP checkout")
    for arguments, expected in (
        (["rev-parse", "HEAD"], pin),
        (["status", "--porcelain", "--untracked-files=no"], ""),
    ):
        result = run_process(
            [git, "-c", f"safe.directory={checkout.as_posix()}", "-C", str(checkout), *arguments],
            cwd=checkout,
            env=dict(os.environ),
            timeout=10,
        )
        if result.timed_out or result.exit_code or result.stdout.strip() != expected:
            raise ValueError(f"Expected a clean native {revision} tracked tree at {pin}")
    hashes = {}
    for name in ("assertions.py", "scenario.py", "trace.py", "result.py"):
        relative = "src/agent_harness/" + name
        path = checkout / relative
        # Git's stat cache can miss an equal-size/equal-mtime edit. Compare the
        # four executed source modules to HEAD as text, allowing CRLF checkouts.
        blob = run_process(
            [
                git,
                "-c",
                f"safe.directory={checkout.as_posix()}",
                "-C",
                str(checkout),
                "show",
                f"HEAD:{relative}",
            ],
            cwd=checkout,
            env=dict(os.environ),
            timeout=10,
        )
        if blob.timed_out or blob.exit_code or path.read_text(encoding="utf-8") != blob.stdout:
            raise ValueError(f"Native module does not match the selected commit: {relative}")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "commit": pin,
        "revision": revision,
        "checkout": str(checkout),
        "source_sha256": hashes,
        "tracked_tree_clean": True,
        "modules_match_commit": True,
        "corpus_sha256": corpus()["sha256"],
    }


def compare(case: dict[str, Any], observation: object, revision: str) -> dict[str, Any]:  # noqa: PLR0911
    result = {
        "classification": "error",
        "expectation_met": False,
        "reason": "Missing or malformed native observation",
    }
    if not isinstance(observation, dict) or observation.get("control") != case["id"]:
        return result
    error = observation.get("error")
    native = observation.get("native")
    if error is not None:
        expected = (
            case["polarity"] == "invalid"
            and isinstance(error, dict)
            and error.get("type") == "TraceValidationError"
            and error.get("stage") == "trace_validation"
            and observation.get("stage") == "trace_validation"
            and observation.get("assertion_invoked") is False
            and native is None
            and case["expected_native"][revision] == "error"
        )
        return {
            "classification": "error",
            "expectation_met": expected,
            "reason": "Native input validation error; never a semantic catch",
        }
    if not isinstance(native, dict) or native.get("id") != "approval_required":
        return result
    actual = native.get("result")
    if (
        not isinstance(actual, str)
        or actual not in {"pass", "fail", "not_run", "error"}
        or observation.get("assertion_invoked") is not True
        or observation.get("stage") != "assertion"
    ):
        return result
    characterized = actual == case["expected_native"][revision]
    if case["polarity"] == "unsupported":
        return {
            "classification": "unsupported",
            "expectation_met": characterized,
            "reason": f"Native evidence cannot establish {case['requirement']}; not a grader bug",
        }
    if case["polarity"] == "invalid":
        return {
            **result,
            "reason": "The malformed-input control unexpectedly bypassed native validation",
        }
    if actual in {"not_run", "error"}:
        return {
            "classification": actual,
            "expectation_met": characterized,
            "reason": "The sensitive action was unexercised"
            if actual == "not_run"
            else "Native assertion returned an error; not a catch",
        }
    classification = {
        ("good", "pass"): "correct_accept",
        ("good", "fail"): "false_reject",
        ("bad", "pass"): "false_accept",
        ("bad", "fail"): "correct_reject",
    }.get((case["polarity"], actual), "error")
    return {
        "classification": classification,
        "expectation_met": characterized,
        "reason": "Compared to the declared contract; characterized failures remain failures",
    }


def audit(checkout: Path, output: Path, revision: str, *, timeout: float = 25) -> dict[str, Any]:
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError("OWASP timeout must be between 1 and 60 seconds")
    source = provenance(checkout, revision)
    report = observe(checkout, output, revision, source=source, timeout=timeout)
    write_report(output, report)
    return report


def observe(
    checkout: Path,
    output: Path,
    revision: str,
    *,
    source: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Collect native observations after the caller has verified source provenance."""
    checkout, output = checkout.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # -B alone still reads bytecode. A fresh prefix also prevents a stale native
    # .pyc with matching size/mtime from masking a source regression.
    # https://docs.python.org/3.12/library/sys.html#sys.pycache_prefix
    command = [
        sys.executable,
        "-B",
        "-X",
        f"pycache_prefix={output / '.bytecode'}",
        "-m",
        "evalsentinel.owasp_worker",
        "--checkout",
        str(checkout),
    ]
    result = run_process(command, cwd=output, env=dict(os.environ), timeout=timeout)
    (output / "stdout.json").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    observations: dict[str, Any] = {}
    worker_hashes = None
    worker_error = result.timed_out or result.exit_code != 0
    if not worker_error:
        try:
            payload = json.loads(result.stdout)
            worker_hashes = payload.get("source_sha256") if isinstance(payload, dict) else None
            values = payload["observations"]
            observations = {item["control"]: item for item in values}
            expected_ids = {case["id"] for case in corpus()["cases"]}
            worker_error = (
                len(observations) != len(values)
                or set(observations) != expected_ids
                or payload.get("network_policy") != "python-sockets-denied"
            )
        except (ValueError, TypeError, KeyError):
            worker_error = True
    rows = []
    for case in corpus()["cases"]:
        observed = None if worker_error else observations.get(case["id"])
        comparison = compare(case, observed, revision)
        rows.append(
            {
                "adapter": "owasp",
                "control": case["id"],
                "revision": source.get("revision", revision),
                "polarity": case["polarity"],
                "requirement": case["requirement"],
                "rationale": case["rationale"],
                "source": case["source"],
                "expected_contract": case["expected_contract"],
                "expected_native": case["expected_native"][revision],
                "native_started": True,
                "native_observation": observed,
                **comparison,
            }
        )
    report = {
        "schema": "evalsentinel.audit.v1",
        "evalsentinel_version": __version__,
        "adapter": "owasp-approval",
        "created_at": datetime.now(UTC).isoformat(),
        "source": source,
        "command": command,
        "worker_exit": result.exit_code,
        "timed_out": result.timed_out,
        "worker_source_sha256": worker_hashes,
        "results": rows,
        "summary": summarize(rows),
        "native_processes": 1,
        "complete": not worker_error,
        "model_api_calls": 0,
        "gpu_required": False,
        "expectations_met": all(row["expectation_met"] for row in rows),
    }
    report["summary"]["complete"] = report["complete"]
    report["sound"] = adjudicated_sound(rows)
    return report


def adjudicated_sound(rows: list[dict[str, Any]]) -> bool:
    adjudicable = [row for row in rows if row["polarity"] in {"good", "bad"}]
    return bool(adjudicable) and all(
        row["classification"] in {"correct_accept", "correct_reject"} for row in adjudicable
    )

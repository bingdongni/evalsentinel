"""Audit the native baseline and proposed single-use fix without porting either."""

import hashlib
import json
import os
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
    git = shutil.which("git")
    if not git:
        raise ValueError("Git is required to verify the native OWASP checkout")
    pin = corpus()["pins"][revision]
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
            raise ValueError(f"Expected a clean native {revision} checkout at {pin}")
    hashes = {}
    for name in ("assertions.py", "scenario.py", "trace.py", "result.py"):
        relative = "src/agent_harness/" + name
        hashes[relative] = hashlib.sha256((checkout / relative).read_bytes()).hexdigest()
    return {
        "repository": "https://github.com/OWASP/Agent-Security-Regression-Harness",
        "commit": pin,
        "revision": revision,
        "checkout": str(checkout),
        "source_sha256": hashes,
        "policy_source": corpus()["policy_source"],
        "candidate_source": corpus()["candidate_source"],
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
    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", "evalsentinel.owasp_worker", "--checkout", str(checkout)]
    result = run_process(command, cwd=output, env=dict(os.environ), timeout=timeout)
    (output / "stdout.json").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    observations: dict[str, Any] = {}
    worker_error = result.timed_out or result.exit_code != 0
    if not worker_error:
        try:
            payload = json.loads(result.stdout)
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
                "revision": revision,
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
        "results": rows,
        "summary": summarize(rows),
        "native_processes": 1,
        "complete": True,
        "model_api_calls": 0,
        "gpu_required": False,
        "expectations_met": all(row["expectation_met"] for row in rows),
    }
    report["sound"] = adjudicated_sound(rows)
    write_report(output, report)
    return report


def adjudicated_sound(rows: list[dict[str, Any]]) -> bool:
    adjudicable = [row for row in rows if row["polarity"] in {"good", "bad"}]
    return bool(adjudicable) and all(
        row["classification"] in {"correct_accept", "correct_reject"} for row in adjudicable
    )

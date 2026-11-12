"""Thin adapter for the pinned upstream MCP CLI and its native example clients."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from evalsentinel import __version__
from evalsentinel.catalog import CHECK_IDS, CONTROLS, MCP_PIN, SPEC, VERSIONS, Control
from evalsentinel.process import run_process
from evalsentinel.report import Comparison, compare, summarize

MIN_TIMEOUT = 15
MAX_TIMEOUT = 60


def provenance(checkout: Path) -> dict:
    git = shutil.which("git")
    node = shutil.which("node")
    if not git or not node:
        raise ValueError("The native adapter requires Git and Node on PATH")

    def query(arguments: list[str]) -> str:
        result = run_process(
            [git, "-c", f"safe.directory={checkout.as_posix()}", "-C", str(checkout), *arguments],
            cwd=checkout,
            env=dict(os.environ),
            timeout=10,
        )
        if result.exit_code or result.timed_out:
            raise ValueError("Could not verify the native Git checkout")
        return result.stdout.strip()

    if query(["rev-parse", "HEAD"]) != MCP_PIN:
        raise ValueError(f"Expected native MCP checkout at {MCP_PIN}")
    if query(["status", "--porcelain", "--untracked-files=no"]):
        raise ValueError("Native checkout has tracked changes; commit identity is insufficient")
    artifacts = {}
    for relative in ("dist/index.js", "package-lock.json"):
        path = checkout / relative
        if not path.is_file():
            raise ValueError(
                f"Missing {relative}; install native dependencies and run npm run build"
            )
        artifacts[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    version = run_process([node, "--version"], cwd=checkout, env=dict(os.environ), timeout=5)
    if version.exit_code or version.timed_out:
        raise ValueError("Could not determine the native Node version")
    return {
        "repository": "https://github.com/modelcontextprotocol/conformance",
        "commit": MCP_PIN,
        "checkout": str(checkout),
        "artifact_sha256": artifacts,
        "node": node,
        "node_version": version.stdout.strip(),
        "scenario_source": "https://github.com/modelcontextprotocol/conformance/pull/583",
        "spec_reference": SPEC,
    }


def _run_control(
    checkout: Path,
    output: Path,
    control: Control,
    version: str,
    *,
    node: str,
    timeout: float,
) -> dict:
    case_dir = output / f"{version}-{control.id}"
    case_dir.mkdir()
    client_file = "everything-client.ts" if control.id == "good" else "pagination-broken-client.ts"
    client_args = [node, "--import", "tsx", f"examples/clients/typescript/{client_file}"]
    client = subprocess.list2cmdline(client_args) if os.name == "nt" else shlex.join(client_args)
    command = [
        node,
        "dist/index.js",
        "client",
        "--scenario",
        "client-pagination",
        "--spec-version",
        version,
        "--timeout",
        "10000",
        "--command",
        client,
        "-o",
        str(case_dir / "native"),
    ]
    env = {**os.environ, "MCP_PAGINATION_DEFECT": control.id}
    native = None
    raw_checks = None
    check_path = None
    comparison = Comparison("error", False, "The native process did not start")
    try:
        native = run_process(command, cwd=checkout, env=env, timeout=timeout)
        (case_dir / "stdout.txt").write_text(native.stdout, encoding="utf-8")
        (case_dir / "stderr.txt").write_text(native.stderr, encoding="utf-8")
        if native.timed_out:
            comparison = Comparison(
                "error", False, "The native CLI timed out; not a semantic catch"
            )
        else:
            paths = list((case_dir / "native").glob("client-pagination-*/checks.json"))
            if len(paths) != 1:
                comparison = Comparison(
                    "insufficient_evidence", False, "No unique native checks.json"
                )
            else:
                check_path = paths[0]
                raw_checks = json.loads(check_path.read_text(encoding="utf-8"))
                comparison = compare(control, raw_checks, native.exit_code)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        comparison = Comparison("error", False, f"Native adapter error: {error}")
    return {
        "control": control.id,
        "spec_version": version,
        "polarity": control.polarity,
        "rationale": control.rationale,
        "focus_check": control.focus,
        "expected_native_checks": dict(zip(CHECK_IDS, control.expected, strict=True)),
        "expected_exit": control.expected_exit,
        **asdict(comparison),
        "native_started": native is not None,
        "command": command,
        "exit_code": native.exit_code if native else None,
        "timed_out": native.timed_out if native else None,
        "checks_path": str(check_path.relative_to(output)) if check_path else None,
        "native_checks": raw_checks,
    }


def audit(checkout: Path, output: Path, versions: list[str], *, timeout: float = 25) -> dict:
    if (
        not versions
        or len(set(versions)) != len(versions)
        or any(v not in VERSIONS for v in versions)
    ):
        raise ValueError("Select one or both supported spec versions without duplicates")
    if not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
        raise ValueError("Native timeout must be between 15 and 60 seconds")
    source = provenance(checkout)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for version in versions:
        for control in CONTROLS:
            rows.append(
                _run_control(
                    checkout,
                    output,
                    control,
                    version,
                    node=source["node"],
                    timeout=timeout,
                )
            )
            # A partial report remains explicit if the surrounding run is interrupted.
            report = {
                "schema": "evalsentinel.audit.v1",
                "evalsentinel_version": __version__,
                "adapter": "mcp-pagination",
                "created_at": datetime.now(UTC).isoformat(),
                "source": source,
                "declared_rows": len(CONTROLS) * len(versions),
                "results": rows,
                "summary": summarize(rows, declared_rows=len(CONTROLS) * len(versions)),
                "model_api_calls": 0,
                "gpu_required": False,
                "complete": len(rows) == len(CONTROLS) * len(versions),
            }
            report["expectations_met"] = (
                report["complete"] and report["summary"]["expectations_met"]
            )
            pending = output / "report.json.tmp"
            pending.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            pending.replace(output / "report.json")
    return report

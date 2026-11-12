"""Explicit caching scope and execution coverage over original MCP evidence."""

import hashlib
import ipaddress
import json
import os
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from evalsentinel import __version__
from evalsentinel.process import ProcessResult, run_process
from evalsentinel.report import write_report

PRODUCTION = "production-caching-v1"
SDK = "sdk-caching-v1"
COVERAGE = "semantic-coverage-v1"
SPEC_VERSION = "2026-07-28"
NATIVE_PIN = "96a6f9478b7f2e125cf0360a213383cf57533893"
METHOD_NOT_FOUND = -32601
MAX_TIMEOUT = 60
PREFIX = "sep-2549-"
CAPABILITIES = {
    PREFIX + "tools-list-caching-hints": "tools",
    PREFIX + "prompts-list-caching-hints": "prompts",
    PREFIX + "resources-list-caching-hints": "resources",
    PREFIX + "resources-templates-list-caching-hints": "resources",
    PREFIX + "resources-read-caching-hints": "resources",
}
READ = PREFIX + "resources-read-caching-hints"
AGGREGATES = {PREFIX + "ttl-non-negative", PREFIX + "cache-scope-valid"}
CACHING_IDS = set(CAPABILITIES) | AGGREGATES
WIRE = "wire-schema-valid"
STATUSES = {"SUCCESS", "FAILURE", "WARNING", "SKIPPED", "INFO"}
SOURCE_FILES = (
    "src/index.ts",
    "src/runner/server.ts",
    "src/scenarios/server/caching.ts",
    "src/connection/index.ts",
    "src/connection/select.ts",
    "src/connection/stateless.ts",
    "src/validation/wire-schema.ts",
    "package.json",
    "package-lock.json",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_checks(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("No native checks; an empty run cannot pass")
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("Native check must be an object")
        check_id, status = item.get("id"), item.get("status")
        if not isinstance(check_id, str) or not check_id or check_id in seen:
            raise ValueError("Missing or duplicate native check ID")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"Invalid native status for {check_id}")
        if item.get("details") is not None and not isinstance(item["details"], dict):
            raise ValueError(f"Invalid native details for {check_id}")
        seen.add(check_id)
    if any(item["id"].startswith("wire-") and item["id"] != WIRE for item in raw):
        raise ValueError("Native harness error or unknown wire check")
    wires = [item for item in raw if item["id"] == WIRE]
    if len(wires) != 1 or wires[0]["status"] not in {"SUCCESS", "FAILURE"}:
        raise ValueError("One decisive native wire-schema-valid check is required")
    messages = (wires[0].get("details") or {}).get("messagesValidated")
    if type(messages) is not int or messages <= 0:
        raise ValueError("Native wire check contains no validated traffic")
    return raw


def declared_capabilities(discovery: object) -> dict[str, Any]:
    if not isinstance(discovery, dict):
        raise TypeError("Native discovery result is not an object")
    caps = discovery.get("capabilities")
    if not isinstance(caps, dict):
        raise TypeError("Discovery must include a capabilities object")
    versions = discovery.get("supportedVersions")
    if not isinstance(versions, list) or SPEC_VERSION not in versions:
        raise ValueError("Server does not advertise the selected protocol version")
    for name in set(CAPABILITIES.values()):
        if name in caps and not isinstance(caps[name], dict):
            raise ValueError(f"Invalid capability declaration: {name}")
    return caps


def _row(item: dict, classification: str, reason: str) -> dict:
    return {"check_id": item["id"], "classification": classification, "reason": reason}


def _native_classification(item: dict) -> str:
    if (item.get("details") or {}).get("untestable") is True:
        return "not_run"
    return {
        "SUCCESS": "passed",
        "FAILURE": "failed",
        "WARNING": "failed",
        "SKIPPED": "not_run",
        "INFO": "not_run",
    }[item["status"]]


def assess(
    raw: object,
    *,
    contract: str,
    required: list[str] | None = None,
    discovery: object = None,
) -> dict:
    checks = validate_checks(raw)
    semantic = [item for item in checks if item["id"] != WIRE]
    ids = {item["id"] for item in semantic}
    if contract in {PRODUCTION, SDK}:
        if ids != CACHING_IDS:
            raise ValueError("Caching check set changed or is incomplete; review compatibility")
        caps = declared_capabilities(discovery)
        required_ids = CACHING_IDS if contract == SDK else CACHING_IDS - {READ}
    elif contract == COVERAGE:
        if not required or any(not item or item.startswith("wire-") for item in required):
            raise ValueError("Name at least one required semantic --require-check ID")
        if len(set(required)) != len(required):
            raise ValueError("Duplicate required semantic check ID")
        required_ids = set(required)
        caps = {}
    else:
        raise ValueError("Unsupported MCP gate contract")
    rows = []
    for item in semantic:
        check_id = item["id"]
        cap = CAPABILITIES.get(check_id)
        outside = contract == PRODUCTION and (
            (cap is not None and cap not in caps)
            or (
                check_id in AGGREGATES
                and not any(name in caps for name in ("tools", "prompts", "resources"))
            )
        )
        if outside:
            # A network/HTTP error is not a legitimate missing optional method.
            error = (item.get("details") or {}).get("error")
            if (
                item["status"] == "FAILURE"
                and cap
                and not (isinstance(error, dict) and error.get("code") == METHOD_NOT_FOUND)
            ):
                raise ValueError(
                    f"Out-of-scope request did not return method-not-found: {check_id}"
                )
            rows.append(_row(item, "not_applicable", "Capability not declared in native discovery"))
        else:
            rows.append(
                _row(item, _native_classification(item), "Original native status in selected scope")
            )
    required_in_scope = required_ids - {
        row["check_id"] for row in rows if row["classification"] == "not_applicable"
    }
    missing = sorted(required_ids - ids)
    not_run = [row["check_id"] for row in rows if row["classification"] == "not_run"]
    failures = [row["check_id"] for row in rows if row["classification"] == "failed"]
    if next(item for item in checks if item["id"] == WIRE)["status"] != "SUCCESS":
        failures.append(WIRE)
    passed = sum(row["classification"] == "passed" for row in rows)
    incomplete = missing or required_in_scope.intersection(not_run) or not passed
    status, code = (
        ("violated", 1) if failures else ("inconclusive", 2) if incomplete else ("passed", 0)
    )
    return {
        "gate": {
            "status": status,
            "exit_code": code,
            "violations": failures,
            "missing_required_checks": missing,
            "unexercised_required_checks": sorted(required_in_scope.intersection(not_run)),
            "diagnostics": [],
        },
        "coverage": {
            "semantic_checks": len(rows),
            "in_scope": sum(row["classification"] != "not_applicable" for row in rows),
            "passed": passed,
            "failed": len(failures) - (WIRE in failures),
            "not_run": len(not_run),
            "not_applicable": sum(row["classification"] == "not_applicable" for row in rows),
            "wire_checks_excluded_from_semantic_denominator": 1,
        },
        "results": rows,
        "native_status_counts": dict(Counter(item["status"] for item in checks)),
    }


def new_report(contract: str) -> dict:
    return {
        "schema": "evalsentinel.mcp-check.v1",
        "evalsentinel_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "adapter": "mcp",
        "contract": {"id": contract},
        "model_api_calls": 0,
        "gpu_required": False,
        "passed": False,
        "gate": {"status": "error", "exit_code": 2, "diagnostics": []},
    }


def record_error(report: dict, error: Exception) -> None:
    report["gate"] = {
        "status": "error",
        "exit_code": 2,
        "diagnostics": [{"code": "INVALID_EVIDENCE", "message": str(error)}],
    }


def check_report(checks_file: Path, output: Path, *, required: list[str]) -> dict:
    report = new_report(COVERAGE)
    output.mkdir(parents=True, exist_ok=False)
    try:
        payload = checks_file.read_bytes()
        (output / "checks.json").write_bytes(payload)
        report["source"] = {
            "kind": "caller-supplied-artifact",
            "checks_sha256": hashlib.sha256(payload).hexdigest(),
            "execution_origin_verified": False,
        }
        report["required_checks"] = required
        report["native_checks"] = json.loads(payload)
        report.update(assess(report["native_checks"], contract=COVERAGE, required=required))
    except (OSError, ValueError, TypeError) as error:
        record_error(report, error)
    report["passed"] = report["gate"]["exit_code"] == 0
    write_report(output, report)
    return report


def target_provenance(checkout: Path, expected_commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit):
        raise ValueError("--expected-commit must be a full 40-hex Git commit")
    git, node = shutil.which("git"), shutil.which("node")
    if not git or not node:
        raise ValueError("Native MCP execution requires Git and Node on PATH")

    def query(arguments: list[str]) -> str:
        result = run_process(
            [git, "-c", f"safe.directory={checkout.as_posix()}", "-C", str(checkout), *arguments],
            cwd=checkout,
            env=dict(os.environ),
            timeout=10,
        )
        if result.timed_out or result.exit_code:
            raise ValueError("Could not verify the native MCP checkout")
        return result.stdout

    if query(["rev-parse", "HEAD"]).strip() != expected_commit.lower():
        raise ValueError("Native MCP HEAD differs from --expected-commit")
    if query(["status", "--porcelain", "--untracked-files=no"]).strip():
        raise ValueError("Native MCP tracked tree is dirty")
    for relative in SOURCE_FILES:
        if (checkout / relative).read_text(encoding="utf-8") != query(["show", f"HEAD:{relative}"]):
            raise ValueError(f"Native source does not match selected commit: {relative}")
    artifacts = (*SOURCE_FILES, "dist/index.js", "node_modules/tsx/dist/cli.mjs")
    return {
        "kind": "user-selected-git-checkout",
        "commit": expected_commit.lower(),
        "checkout": str(checkout),
        "artifact_sha256": {name: _sha(checkout / name) for name in artifacts},
        "node": node,
        "tracked_tree_clean": True,
        "trust": "Trusted native build and dependencies; hashes are not build attestation",
    }


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname
    try:
        local = host == "localhost" or (host is not None and ipaddress.ip_address(host).is_loopback)
    except ValueError:
        local = False
    if (
        not local
        or parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("This alpha requires an HTTP(S) loopback server URL without credentials")
    # Force validation of invalid and out-of-range ports before launching Node.
    _ = parsed.port


def _run(command: list[str], checkout: Path, prefix: Path, timeout: float) -> ProcessResult:
    result = run_process(command, cwd=checkout, env=dict(os.environ), timeout=timeout)
    prefix.with_suffix(".stdout.txt").write_text(result.stdout, encoding="utf-8")
    prefix.with_suffix(".stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.timed_out:
        raise ValueError(f"Native process timed out: {prefix.name}")
    return result


def _discover(checkout: Path, output: Path, node: str, url: str, timeout: float) -> dict:
    bridge = Path(__file__).parent / "data/mcp-discover.mts"
    result = _run(
        [
            node,
            str(checkout / "node_modules/tsx/dist/cli.mjs"),
            str(bridge),
            str(checkout),
            url,
            str(output),
        ],
        checkout,
        output,
        timeout,
    )
    if result.exit_code:
        raise ValueError("Native discovery process failed; absence cannot be inferred")
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Invalid native discovery payload")
    checks = validate_checks(payload.get("checks"))
    if len(checks) != 1 or checks[0]["status"] != "SUCCESS":
        raise ValueError("Native discovery wire validation failed")
    declared_capabilities(payload.get("discovery"))
    return payload


def _require(condition: bool, message: str) -> None:  # noqa: FBT001
    if not condition:
        raise ValueError(message)


def check(  # noqa: PLR0913
    checkout: Path,
    output: Path,
    expected_commit: str,
    *,
    url: str,
    contract: str,
    timeout: float = 30,
) -> dict:
    if contract not in {PRODUCTION, SDK}:
        raise ValueError("Select production-caching-v1 or sdk-caching-v1")
    if not 1 <= timeout <= MAX_TIMEOUT:
        raise ValueError("Native timeout must be between 1 and 60 seconds")
    validate_url(url)
    checkout, output = checkout.resolve(), output.resolve()
    source = target_provenance(checkout, expected_commit)
    output.mkdir(parents=True, exist_ok=False)
    report = {**new_report(contract), "source": source, "spec_version": SPEC_VERSION, "url": url}
    try:
        before = _discover(checkout, output / "discovery-before.json", source["node"], url, timeout)
        command = [
            source["node"],
            str(checkout / "dist/index.js"),
            "server",
            "--url",
            url,
            "--scenario",
            "caching",
            "--spec-version",
            SPEC_VERSION,
            "--timeout",
            str(int(timeout * 1000)),
            "--output-dir",
            str(output / "native"),
        ]
        native = _run(command, checkout, output / "native", timeout)
        report["native_execution"] = {"command": command, "exit_code": native.exit_code}
        _require(native.exit_code in {0, 1}, "Native CLI crashed or exited abnormally")
        paths = list((output / "native").glob("server-caching-*/checks.json"))
        _require(len(paths) == 1, "Native run did not produce one unique caching checks.json")
        report["native_checks"] = json.loads(paths[0].read_text(encoding="utf-8"))
        report["native_checks_sha256"] = _sha(paths[0])
        report["native_checks_path"] = str(paths[0].relative_to(output))
        after = _discover(checkout, output / "discovery-after.json", source["node"], url, timeout)
        _require(
            declared_capabilities(before["discovery"]) == declared_capabilities(after["discovery"]),
            "Capability declarations changed during execution",
        )
        report["discovery"] = {"before": before, "after": after}
        assessed = assess(report["native_checks"], contract=contract, discovery=before["discovery"])
        has_failure = any(item["status"] == "FAILURE" for item in report["native_checks"])
        has_warning = any(item["status"] == "WARNING" for item in report["native_checks"])
        _require(
            not (
                (has_failure and native.exit_code == 0)
                or (native.exit_code == 1 and not (has_failure or has_warning))
            ),
            "Native process exit and persisted checks disagree",
        )
        report.update(assessed)
    except (OSError, ValueError, TypeError) as error:
        record_error(report, error)
    try:
        after_source = target_provenance(checkout, expected_commit)
        _require(
            after_source["artifact_sha256"] == source["artifact_sha256"],
            "Native source or build artifacts changed during execution",
        )
        report["source"]["verified_after_run"] = True
    except (OSError, ValueError) as error:
        report["source"]["verified_after_run"] = False
        record_error(report, error)
    report["passed"] = report["gate"]["exit_code"] == 0
    write_report(output, report)
    return report


def console_summary(report: dict, output: Path) -> str:
    lines = [f"{report['gate']['status'].upper()}: {report['contract']['id']}"]
    if coverage := report.get("coverage"):
        lines.append(
            f"Semantic checks: {coverage['passed']} passed, {coverage['failed']} failed, "
            f"{coverage['not_run']} not_run, {coverage['not_applicable']} not_applicable; "
            "wire excluded"
        )
    gate = report["gate"]
    for key, label in (
        ("violations", "blocking"),
        ("missing_required_checks", "missing"),
        ("unexercised_required_checks", "not_run"),
    ):
        lines.extend(f"  {label}: {check_id}" for check_id in gate.get(key, []))
    lines.extend(f"  {item['code']}: {item['message']}" for item in report["gate"]["diagnostics"])
    lines.append(f"Report: {output.resolve() / 'report.json'}")
    return "\n".join(lines)

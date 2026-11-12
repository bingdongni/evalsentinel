"""Caller-required tool discovery over original native caching and Connection APIs."""

import json
import os
from collections import Counter
from pathlib import Path

from evalsentinel import mcp_gate as mcp
from evalsentinel.process import run_process
from evalsentinel.report import write_report

CONTRACT = "service-tools-v1"
MAX_PAGES = 32
ERROR = 2


def required_names(required: list[str]) -> list[str]:
    if not required or any(not isinstance(name, str) or not name.strip() for name in required):
        raise ValueError("service-tools-v1 needs at least one nonempty --require-tool name")
    if len(set(required)) != len(required):
        raise ValueError("Duplicate --require-tool name")
    return required


def _tool_names(result: dict) -> list[str]:
    if result.get("resultType") != "complete":
        raise ValueError("Invalid native inventory result")
    tools = result.get("tools")
    if not isinstance(tools, list):
        raise TypeError("Native tool catalog must be an array")
    names = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not name:
            raise ValueError("Native tool entry has no valid name")
        names.append(name)
    return names


def _catalog(pages: object) -> Counter[str]:
    if not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES:
        raise ValueError("Missing or over-budget native inventory pages")
    # Verify the recorded traversal independently; a worker's complete flag is insufficient.
    names, cursors = Counter(), set()
    expected_params = {}
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or page.get("params") != expected_params:
            raise ValueError("Inventory cursor was not forwarded exactly")
        result = page.get("result")
        if not isinstance(result, dict):
            raise TypeError("Invalid native inventory result")
        names.update(_tool_names(result))
        if "nextCursor" in result:
            cursor = result["nextCursor"]
            if not isinstance(cursor, str) or cursor in cursors or index == len(pages) - 1:
                raise ValueError("Repeated, invalid or unconsumed inventory cursor")
            cursors.add(cursor)
            expected_params = {"cursor": cursor}
        elif index != len(pages) - 1:
            raise ValueError("Inventory continued after the final page")
    return names


def assess_inventory(payload: object, required: list[str]) -> dict:
    required_names(required)
    if not isinstance(payload, dict):
        raise TypeError("Native inventory evidence must be an object")
    checks = mcp.validate_checks(payload.get("checks"))
    if len(checks) != 1:
        raise ValueError("Unexpected native inventory check set")
    if checks[0]["status"] == "FAILURE":
        return {"status": "violated", "exit_code": 1, "violations": [mcp.WIRE], "diagnostics": []}
    if "tools" not in mcp.declared_capabilities(payload.get("discovery")):
        raise ValueError("Tools capability not declared; inventory not exercised")
    if payload.get("complete") is not True or payload.get("error") is not None:
        raise ValueError(f"Native inventory traversal incomplete: {payload.get('error')}")
    names = _catalog(payload.get("pages"))
    duplicates = {name for name, count in names.items() if count > 1}
    missing = sorted(set(required) - set(names))
    violations = [
        *(f"required-tool:{name}" for name in missing),
        *(f"duplicate-tool:{name}" for name in sorted(duplicates)),
    ]
    return {
        "status": "violated" if violations else "passed",
        "exit_code": 1 if violations else 0,
        "violations": violations,
        "diagnostics": [],
        "inventory": {
            "required": required,
            "observed": sorted(names),
            "missing": missing,
            "duplicate_names": sorted(duplicates),
            "pages": len(payload["pages"]),
            "complete": True,
        },
    }


def _observe(checkout: Path, output: Path, source: dict, url: str, timeout: float) -> dict:
    bridge = Path(__file__).parent / "data/mcp-tools.mts"
    evidence = output / "inventory.json"
    command = [
        source["node"],
        str(checkout / "node_modules/tsx/dist/cli.mjs"),
        str(bridge),
        str(checkout),
        url,
        str(evidence),
    ]
    native = run_process(command, cwd=checkout, env=dict(os.environ), timeout=timeout)
    (output / "inventory.stdout.txt").write_text(native.stdout, encoding="utf-8")
    (output / "inventory.stderr.txt").write_text(native.stderr, encoding="utf-8")
    if native.timed_out or native.exit_code:
        raise ValueError("Native inventory process failed or timed out; not a missing-tool catch")
    return json.loads(evidence.read_text(encoding="utf-8"))


def _stable_source(checkout: Path, commit: str, source: dict) -> None:
    after = mcp.target_provenance(checkout, commit)
    if after["artifact_sha256"] != source["artifact_sha256"]:
        raise ValueError("Native source/build changed during inventory execution")


def _stable_capabilities(payload: dict, caching: dict) -> None:
    if mcp.declared_capabilities(payload.get("discovery")) != mcp.declared_capabilities(
        caching["discovery"]["after"]["discovery"]
    ):
        raise ValueError("Capabilities changed between caching and inventory")


def _combine(caching: dict, inventory: dict) -> dict:
    gates = [caching, inventory]
    code = (
        ERROR if any(g["exit_code"] == ERROR for g in gates) else max(g["exit_code"] for g in gates)
    )
    return {
        "status": "inconclusive" if code == ERROR else "violated" if code == 1 else "passed",
        "exit_code": code,
        "violations": [v for gate in gates for v in gate.get("violations", [])],
        "diagnostics": [d for gate in gates for d in gate.get("diagnostics", [])],
    }


def check(  # noqa: PLR0913
    checkout: Path,
    output: Path,
    expected_commit: str,
    *,
    url: str,
    required: list[str],
    timeout: float = 30,
) -> dict:
    required_names(required)
    if not 1 <= timeout <= mcp.MAX_TIMEOUT:
        raise ValueError("Native timeout must be between 1 and 60 seconds")
    mcp.validate_url(url)
    checkout, output = checkout.resolve(), output.resolve()
    source = mcp.target_provenance(checkout, expected_commit)
    output.mkdir(parents=True, exist_ok=False)
    report = {
        **mcp.new_report(CONTRACT),
        "source": source,
        "required_tools": required,
        "spec_version": mcp.SPEC_VERSION,
        "url": url,
        "scope": "Native caching plus complete required-name discovery; no tools/call",
    }
    write_report(output, report)
    try:
        caching = mcp.check(
            checkout,
            output / "caching",
            expected_commit,
            url=url,
            contract=mcp.PRODUCTION,
            timeout=timeout,
        )
        report.update(
            caching_gate=caching["gate"],
            coverage=caching.get("coverage"),
            caching_report="caching/report.json",
        )
        if caching["gate"]["status"] == "error":
            report["gate"] = caching["gate"]
        else:
            payload = _observe(checkout, output, source, url, timeout)
            report["native_inventory"] = payload
            inventory = assess_inventory(payload, required)
            _stable_capabilities(payload, caching)
            report["inventory"] = inventory.get("inventory")
            report["inventory_gate"] = {k: v for k, v in inventory.items() if k != "inventory"}
            report["gate"] = _combine(caching["gate"], inventory)
    except (OSError, ValueError, TypeError) as error:
        mcp.record_error(report, error)
    try:
        _stable_source(checkout, expected_commit, source)
        report["source"]["verified_after_run"] = True
    except (OSError, ValueError) as error:
        report["source"]["verified_after_run"] = False
        mcp.record_error(report, error)
    report["passed"] = report["gate"]["exit_code"] == 0
    write_report(output, report)
    return report


def console_summary(report: dict, output: Path) -> str:
    text = mcp.console_summary(report, output)
    inventory = report.get("inventory")
    if inventory:
        text += (
            f"\nInventory: {len(inventory['observed'])} tools over {inventory['pages']} pages; "
            f"missing: {inventory['missing']}"
        )
    return text

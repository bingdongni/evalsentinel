"""Reproduce real DBHub integration, known false alarms, and scoped blind spots."""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dbhub_fixture import MODES, provenance, proxy, service, sha

import evalsentinel
from evalsentinel import mcp_gate as mcp
from evalsentinel import mcp_service
from evalsentinel.process import run_process

EXPECTED = {
    "passthrough": (0, 0, 0),
    "hide-tool": (0, 1, 0),
    "strip-hint": (1, 1, 0),
    "paged-empty-cursor": (0, 0, 0),
    "hide-later-tool": (0, 1, 0),
    "cursor-cycle": (0, 2, 0),
    "duplicate-name": (0, 1, 0),
    "wrong-query-result": (0, 0, 1),
}


def command(arguments: list[str], output: Path, *, cwd: Path) -> int:
    native = run_process(arguments, cwd=cwd, env=dict(os.environ), timeout=200)
    output.with_suffix(".stdout.txt").write_text(native.stdout, encoding="utf-8")
    output.with_suffix(".stderr.txt").write_text(native.stderr, encoding="utf-8")
    if native.timed_out:
        raise RuntimeError("Bounded integration subprocess timed out; inspect preserved logs")
    return native.exit_code


def gate(checkout: Path, output: Path, url: str, contract: str) -> tuple[int, dict]:
    args = [
        sys.executable,
        "-m",
        "evalsentinel",
        "check",
        "mcp",
        "--checkout",
        str(checkout),
        "--expected-commit",
        mcp.NATIVE_PIN,
        "--contract",
        contract,
        "--url",
        url,
        "--output-dir",
        str(output),
        "--format",
        "json",
    ]
    if contract == mcp_service.CONTRACT:
        args += ["--require-tool", "execute_sql"]
    code = command(args, output, cwd=output.parent)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if report["gate"]["exit_code"] != code or report["passed"] != (code == 0):
        raise RuntimeError("Real CLI exit and persisted report disagree")
    return code, report


def sql_gate(checkout: Path, output: Path, url: str) -> tuple[int, dict]:
    source = mcp.target_provenance(checkout, mcp.NATIVE_PIN)
    args = [
        source["node"],
        str(checkout / "node_modules/tsx/dist/cli.mjs"),
        str(Path(__file__).parent / "dbhub-functional.mts"),
        str(checkout),
        url,
        str(output),
    ]
    code = command(args, output, cwd=output.parent)
    if code:
        raise RuntimeError("Original native SQL probe did not execute successfully")
    payload = json.loads(output.read_text(encoding="utf-8"))
    wire = mcp.validate_checks(payload["checks"])
    if len(wire) != 1 or wire[0]["status"] != "SUCCESS":
        raise RuntimeError("SQL probe has invalid native wire evidence; not a semantic result")
    good, bad = payload["good"], payload["bad"]
    good_body = json.loads(good["content"][0]["text"])
    bad_body = json.loads(bad["content"][0]["text"])
    rows = good_body.get("data", {}).get("statements", [{}])[0].get("rows")
    accepted = (
        good.get("isError") is not True
        and good_body.get("success") is True
        and rows == [{"name": "alpha"}, {"name": "beta"}]
    )
    rejected = bad.get("isError") is True and bad_body.get("success") is False
    return (0 if accepted and rejected else 1), {
        "positive_rows_match": accepted,
        "invalid_sql_rejected": rejected,
        "wire_valid": True,
    }


def verify(checkout: Path, runtime: Path, output: Path) -> dict:
    before = provenance(runtime)
    mcp.target_provenance(checkout, mcp.NATIVE_PIN)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    with service(runtime, output / "server") as target:
        for mode in MODES:
            directory = output / mode
            directory.mkdir()
            with proxy(target, mode) as bridge:
                wire_path = directory / "wire.json"
                try:
                    url = f"http://127.0.0.1:{bridge.server_port}/mcp"
                    cache_code, cache = gate(checkout, directory / "caching", url, mcp.PRODUCTION)
                    service_code, deployed = gate(
                        checkout, directory / "service", url, mcp_service.CONTRACT
                    )
                    functional_code, functional = sql_gate(
                        checkout, directory / "functional.json", url
                    )
                finally:
                    wire_path.write_text(json.dumps(bridge.wire, indent=2) + "\n", encoding="utf-8")
            actual = (cache_code, service_code, functional_code)
            if actual != EXPECTED[mode]:
                raise RuntimeError(
                    f"Real service control {mode}: expected {EXPECTED[mode]}, got {actual}"
                )
            if mode == "passthrough" and any(
                item["request"] != item["upstream_request"]
                or item["upstream_response"] != item["delivered_response"]
                for item in bridge.wire
            ):
                raise RuntimeError("Passthrough changed the real service's JSON messages")
            if (
                mode != "strip-hint"
                and next(item for item in cache["native_checks"] if item["id"] == mcp.WIRE)[
                    "status"
                ]
                != "SUCCESS"
            ):
                raise RuntimeError("Expected a schema-valid control; not a wire/harness error")
            if mode == "passthrough" and cache["native_execution"]["exit_code"] != 1:
                raise RuntimeError("Native production false rejection was not reproduced")
            if not {item["request"]["method"] for item in bridge.wire} <= {
                "server/discover",
                "tools/list",
                "prompts/list",
                "resources/list",
                "resources/templates/list",
                "tools/call",
            }:
                raise RuntimeError("Unexpected native method executed")
            records.append(
                {
                    "mode": mode,
                    "expected_exits": list(EXPECTED[mode]),
                    "actual_exits": list(actual),
                    "caching_gate": cache["gate"],
                    "service_gate": deployed["gate"],
                    "inventory": deployed.get("inventory"),
                    "functional": functional,
                    "native_exit": cache["native_execution"]["exit_code"],
                    "native_counts": dict(Counter(c["status"] for c in cache["native_checks"])),
                    "wire_sha256": sha(wire_path),
                    "directory": mode,
                }
            )
            print(json.dumps({"mode": mode, "exits": list(actual)}), flush=True)
        with sqlite3.connect(output / "server/fixture.db") as db:
            if db.execute("SELECT name FROM sentinel_items ORDER BY id").fetchall() != [
                ("alpha",),
                ("beta",),
            ]:
                raise RuntimeError("Synthetic database contents changed")
    if provenance(runtime) != before:
        raise RuntimeError("Official service artifacts changed during execution")
    return {
        "evalsentinel_version": evalsentinel.__version__,
        "loaded_module": str(Path(evalsentinel.__file__).resolve()),
        "native_commit": mcp.NATIVE_PIN,
        "real_service": before,
        "intervention_modes": len(MODES),
        "cache_and_service_profile_observations": len(MODES) * 2,
        "functional_observations": len(MODES),
        "all_expected_exits_matched": True,
        "model_api_calls": 0,
        "gpu_required": False,
        "remaining_blind_spot": (
            "SQL result semantics require the independent functional assertions; "
            "inventory alone does not detect wrong rows"
        ),
        "results": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    if (
        args.require_installed
        and "site-packages" not in Path(evalsentinel.__file__).resolve().parts
    ):
        raise RuntimeError("The real service CI must import the installed wheel")
    output = args.output_dir.resolve()
    proof = verify(args.checkout.resolve(), args.runtime.resolve(), output)
    (output / "verification.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verification": str(output / "verification.json"),
                "matched": True,
                "service": proof["real_service"]["version"],
            }
        )
    )


if __name__ == "__main__":
    main()

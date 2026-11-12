"""Run installed CLI gates against original native conformance, without model APIs."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from mcp_fixture import Handler, running

import evalsentinel
from evalsentinel import mcp_gate

# Eleven profile observations of eight fixtures; repetitions are not new cases.
CASES = (
    ("tools-only", mcp_gate.PRODUCTION, 0),
    ("tools-only", mcp_gate.SDK, 1),
    ("full", mcp_gate.PRODUCTION, 0),
    ("full", mcp_gate.SDK, 0),
    ("broken-prompts", mcp_gate.PRODUCTION, 1),
    ("bad-ttl", mcp_gate.PRODUCTION, 1),
    ("no-capabilities", mcp_gate.PRODUCTION, 2),
    ("empty-resources", mcp_gate.PRODUCTION, 0),
    ("empty-resources", mcp_gate.SDK, 2),
    ("discovery-change", mcp_gate.PRODUCTION, 2),
    ("invalid-discovery", mcp_gate.PRODUCTION, 2),
)


def execute(arguments: list[str], directory: Path, expected: int) -> dict:
    command = [
        sys.executable,
        "-m",
        "evalsentinel",
        "check",
        *arguments,
        "--output-dir",
        str(directory),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=200, check=False
    )
    directory.mkdir(exist_ok=True)
    (directory / "cli.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (directory / "cli.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode != expected:
        raise RuntimeError(
            f"Expected exit {expected}, got {result.returncode}: {result.stdout} {result.stderr}"
        )
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    if report["gate"]["exit_code"] != expected or report["passed"] != (expected == 0):
        raise RuntimeError("CLI exit and persisted gate disagree")
    return report


def cache_controls(checkout: Path, output: Path) -> list[dict]:
    records = []
    for mode, contract, expected in CASES:
        directory = output / f"{mode}-{contract}"
        with running(mode) as server:
            report = execute(
                [
                    "mcp",
                    "--checkout",
                    str(checkout),
                    "--expected-commit",
                    mcp_gate.NATIVE_PIN,
                    "--contract",
                    contract,
                    "--url",
                    f"http://127.0.0.1:{server.server_port}/mcp",
                ],
                directory,
                expected,
            )
        (directory / "wire.json").write_text(
            json.dumps(server.observations, indent=2) + "\n", encoding="utf-8"
        )
        methods = [item["request"]["method"] for item in server.observations]
        if not set(methods) <= Handler.allowed_methods:
            raise RuntimeError("Fixture received an unexpected action method")
        raw = report.get("native_checks", [])
        wire = next((item for item in raw if item["id"] == mcp_gate.WIRE), None)
        if mode not in {"bad-ttl", "invalid-discovery"} and (
            not wire or wire["status"] != "SUCCESS"
        ):
            raise RuntimeError("Expected valid native wire evidence")
        if mode == "tools-only" and report["native_execution"]["exit_code"] != 1:
            raise RuntimeError("Known upstream production false rejection was not reproduced")
        if mode == "empty-resources" and report["coverage"]["not_run"] != 1:
            raise RuntimeError("An unexercised resource read was counted as a success")
        records.append(
            {
                "fixture": mode,
                "contract": contract,
                "expected_exit": expected,
                "gate": report["gate"],
                "coverage": report.get("coverage"),
                "native_exit": report.get("native_execution", {}).get("exit_code"),
                "native_status_counts": dict(Counter(item["status"] for item in raw)),
                "report": str(directory.relative_to(output) / "report.json"),
                "wire_sha256": hashlib.sha256((directory / "wire.json").read_bytes()).hexdigest(),
            }
        )
    return records


def artifact_controls(checkout: Path, output: Path) -> list[dict]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Install Node before running native controls")
    directory = output / "skills-native"
    with running("tools-only") as server:
        result = subprocess.run(
            [
                node,
                str(checkout / "dist/index.js"),
                "server",
                "--url",
                f"http://127.0.0.1:{server.server_port}/mcp",
                "--scenario",
                "sep-2640-skills-enumeration",
                "--spec-version",
                mcp_gate.SPEC_VERSION,
                "--force",
                "--output-dir",
                str(directory),
            ],
            cwd=checkout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=40,
            check=False,
        )
    directory.mkdir(exist_ok=True)
    (directory / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (directory / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (directory / "wire.json").write_text(
        json.dumps(server.observations, indent=2) + "\n", encoding="utf-8"
    )
    paths = list(directory.glob("server-*/checks.json"))
    if result.returncode != 0 or len(paths) != 1:
        raise RuntimeError("Original forced Skills scenario did not produce checks")
    raw = json.loads(paths[0].read_text(encoding="utf-8"))
    counts = dict(Counter(item["status"] for item in raw))
    if counts != {"SKIPPED": 31, "SUCCESS": 1} or raw[-1]["id"] != mcp_gate.WIRE:
        raise RuntimeError(f"Expected 31 semantic skips and one native wire success: {counts}")
    controls = [
        ("all-skipped", paths[0], "sep-2640-skills-list-implemented", 2),
        (
            "exercised",
            next((output / f"full-{mcp_gate.PRODUCTION}/native").glob("server-*/checks.json")),
            "sep-2549-tools-list-caching-hints",
            0,
        ),
    ]
    records = []
    for name, path, required, expected in controls:
        report = execute(
            [
                "mcp-report",
                "--checks-file",
                str(path),
                "--contract",
                mcp_gate.COVERAGE,
                "--require-check",
                required,
            ],
            output / f"artifact-{name}",
            expected,
        )
        records.append(
            {
                "fixture": name,
                "native_exit": 0,
                "gate": report["gate"],
                "coverage": report["coverage"],
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    loaded = Path(evalsentinel.__file__).resolve()
    if args.require_installed and "site-packages" not in loaded.parts:
        raise RuntimeError(f"Expected installed wheel, loaded {loaded}")
    checkout, output = args.checkout.resolve(), args.output_dir.resolve()
    mcp_gate.target_provenance(checkout, mcp_gate.NATIVE_PIN)
    output.mkdir(parents=True, exist_ok=False)
    records = cache_controls(checkout, output)
    artifacts = artifact_controls(checkout, output)
    summary = {
        "evalsentinel_version": evalsentinel.__version__,
        "loaded_module": str(loaded),
        "native_commit": mcp_gate.NATIVE_PIN,
        "platform": os.name,
        "cache_fixture_modes": len({item[0] for item in CASES}),
        "cache_profile_observations": len(records),
        "cache_results": records,
        "artifact_results": artifacts,
        "all_expected_exits_matched": True,
        "model_api_calls": 0,
        "gpu_required": False,
    }
    (output / "verification.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verification": str(output / "verification.json"), "matched": True}))


if __name__ == "__main__":
    main()

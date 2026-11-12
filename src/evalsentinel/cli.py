"""Public CLI for the first bounded, offline native integration."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from evalsentinel import __version__
from evalsentinel.catalog import CONTROLS, VERSIONS
from evalsentinel.mcp import audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evalsentinel", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("cases", help="List the eight declared pagination controls as JSON")
    run = commands.add_parser("audit", help="Run declared controls through a native evaluator")
    run.add_argument("adapter", choices=["mcp"])
    run.add_argument("--checkout", type=Path, required=True, help="Pinned, clean native checkout")
    run.add_argument("--spec-version", choices=VERSIONS, action="append")
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--timeout-seconds", type=float, default=25)
    args = parser.parse_args(argv)
    if args.command == "cases":
        print(json.dumps([asdict(control) for control in CONTROLS], indent=2))
        return 0
    output = args.output_dir or Path("runs") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        report = audit(
            args.checkout.resolve(),
            output.resolve(),
            args.spec_version or list(VERSIONS),
            timeout=args.timeout_seconds,
        )
    except (OSError, ValueError) as error:
        print(
            json.dumps({"error": {"code": "INVALID_ENVIRONMENT", "message": str(error)}}),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "report": str(output.resolve() / "report.json"),
                "complete": report["complete"],
                "summary": report["summary"],
            },
            indent=2,
        )
    )
    return 0 if report["expectations_met"] else 1

"""Public CLI for the first bounded, offline native integration."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from evalsentinel import __version__, gate, owasp, suite
from evalsentinel.catalog import CONTROLS, VERSIONS
from evalsentinel.mcp import audit
from evalsentinel.owasp_catalog import REVISIONS, corpus


def inventory(adapter: str) -> list[dict]:
    mcp_cases = [{"adapter": "mcp", **asdict(control)} for control in CONTROLS]
    owasp_cases = [
        {"adapter": "owasp", **{key: value for key, value in case.items() if key != "trace"}}
        for case in corpus()["cases"]
    ]
    return (
        mcp_cases
        if adapter == "mcp"
        else owasp_cases
        if adapter == "owasp"
        else mcp_cases + owasp_cases
    )


def _execute(args: argparse.Namespace, output: Path) -> dict:
    if args.adapter != "mcp" and args.spec_version:
        raise ValueError("--spec-version applies to the MCP adapter only")
    if args.adapter == "all":
        if not all((args.mcp_checkout, args.owasp_baseline, args.owasp_candidate)):
            raise ValueError(
                "The full suite needs --mcp-checkout, --owasp-baseline and --owasp-candidate"
            )
        return suite.audit(
            args.mcp_checkout.resolve(),
            args.owasp_baseline.resolve(),
            args.owasp_candidate.resolve(),
            output.resolve(),
            timeout=args.timeout_seconds,
        )
    if args.checkout is None:
        raise ValueError("--checkout is required for a single native adapter")
    if args.adapter == "owasp":
        return owasp.audit(
            args.checkout.resolve(), output.resolve(), args.revision, timeout=args.timeout_seconds
        )
    return audit(
        args.checkout.resolve(),
        output.resolve(),
        args.spec_version or list(VERSIONS),
        timeout=args.timeout_seconds,
    )


def _check(args: argparse.Namespace, output: Path) -> int:
    try:
        report = gate.check(
            args.checkout.resolve(),
            output.resolve(),
            args.expected_commit,
            contract=args.contract,
            timeout=args.timeout_seconds,
        )
    except (OSError, ValueError) as error:
        print(
            json.dumps({"error": {"code": "INVALID_ENVIRONMENT", "message": str(error)}}),
            file=sys.stderr,
        )
        return 2
    if args.format == "json":
        print(
            json.dumps(
                {"report": str(output.resolve() / "report.json"), **report["gate"]}, indent=2
            )
        )
    else:
        print(gate.console_summary(report, output))
    return report["gate"]["exit_code"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evalsentinel", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    cases = commands.add_parser("cases", help="List the 30 declared controls as JSON")
    cases.add_argument("--adapter", choices=["all", "mcp", "owasp"], default="all")
    check = commands.add_parser("check", help="Gate a maintainer-selected native commit")
    check.add_argument("adapter", choices=["owasp"])
    check.add_argument("--checkout", type=Path, required=True)
    check.add_argument("--expected-commit", required=True, help="Full 40-hex target Git commit")
    check.add_argument("--contract", choices=[gate.CONTRACT], required=True)
    check.add_argument("--output-dir", type=Path)
    check.add_argument("--timeout-seconds", type=float, default=25)
    check.add_argument("--format", choices=["text", "json"], default="text")
    run = commands.add_parser("audit", help="Run declared controls through a native evaluator")
    run.add_argument("adapter", choices=["mcp", "owasp", "all"])
    run.add_argument("--checkout", type=Path, help="Pinned, clean native checkout")
    run.add_argument("--revision", choices=REVISIONS, default="candidate")
    run.add_argument("--mcp-checkout", type=Path)
    run.add_argument("--owasp-baseline", type=Path)
    run.add_argument("--owasp-candidate", type=Path)
    run.add_argument(
        "--require-sound", action="store_true", help="Fail on adjudicable contract failures"
    )
    run.add_argument("--spec-version", choices=VERSIONS, action="append")
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--timeout-seconds", type=float, default=25)
    args = parser.parse_args(argv)
    if args.command == "cases":
        print(json.dumps(inventory(args.adapter), indent=2))
        return 0
    output = args.output_dir or Path("runs") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    if args.command == "check":
        return _check(args, output)
    try:
        report = _execute(args, output)
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
                "sound": report.get("sound", report["expectations_met"]),
            },
            indent=2,
        )
    )
    accepted = report["expectations_met"] and (
        not args.require_sound or report.get("sound", report["expectations_met"])
    )
    return 0 if accepted else 1

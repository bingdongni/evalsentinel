"""Verify the complete denominator and real strict-mode negative/positive controls."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

EXPECTED_CONTROLS = 30
EXPECTED_ROWS = 60
BASELINE_FALSE_ACCEPTS = 6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summary = report["summary"]
    if (
        not report["complete"]
        or not report["expectations_met"]
        or summary["independent_controls"] != EXPECTED_CONTROLS
        or summary["declared_rows"] != EXPECTED_ROWS
    ):
        raise RuntimeError("The declared 30-control matrix was not completely reproduced")
    sources = report["sources"]
    if (
        sources["baseline"]["summary"]["classifications"].get("false_accept")
        != BASELINE_FALSE_ACCEPTS
    ):
        raise RuntimeError("The known baseline counterexamples were not reproduced")
    if sources["baseline"]["sound"] or not sources["candidate"]["sound"]:
        raise RuntimeError("Baseline/candidate soundness controls do not distinguish the revisions")
    exits = {}
    for revision in ("baseline", "candidate"):
        output = args.report.parent / f"strict-{revision}-{uuid4().hex[:8]}"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "evalsentinel",
                "audit",
                "owasp",
                "--checkout",
                sources[revision]["source"]["checkout"],
                "--revision",
                revision,
                "--require-sound",
                "--output-dir",
                str(output),
            ],
            check=False,
        )
        exits[revision] = result.returncode
    if exits != {"baseline": 1, "candidate": 0}:
        raise RuntimeError("Strict mode did not fail the real negative and pass the real positive")
    record = {
        "unique_controls": EXPECTED_CONTROLS,
        "observation_rows": EXPECTED_ROWS,
        "strict_exit_codes": exits,
        "model_api_calls": 0,
        "all_characterizations_matched": True,
    }
    (args.report.parent / "verification.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

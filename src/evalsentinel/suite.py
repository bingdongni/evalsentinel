"""Compose native adapters while keeping their evidence and denominators intact."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalsentinel import __version__, mcp, owasp
from evalsentinel.catalog import CONTROLS, VERSIONS
from evalsentinel.owasp_catalog import corpus
from evalsentinel.report import summarize, write_report


def audit(
    mcp_checkout: Path, baseline: Path, candidate: Path, output: Path, *, timeout: float = 25
) -> dict[str, Any]:
    if not mcp.MIN_TIMEOUT <= timeout <= mcp.MAX_TIMEOUT:
        raise ValueError("Full-suite timeout must be between 15 and 60 seconds per native process")
    mcp.provenance(mcp_checkout)
    owasp.provenance(baseline, "baseline")
    owasp.provenance(candidate, "candidate")
    output.mkdir(parents=True, exist_ok=False)
    declared = len(CONTROLS) * len(VERSIONS) + len(corpus()["cases"]) * 2
    rows = []
    reports: dict[str, dict[str, Any]] = {}
    stages = (
        ("mcp", lambda: mcp.audit(mcp_checkout, output / "mcp", list(VERSIONS), timeout=timeout)),
        (
            "baseline",
            lambda: owasp.audit(baseline, output / "baseline", "baseline", timeout=timeout),
        ),
        (
            "candidate",
            lambda: owasp.audit(candidate, output / "candidate", "candidate", timeout=timeout),
        ),
    )
    for name, run in stages:
        native = run()
        reports[name] = {
            "source": native["source"],
            "summary": native["summary"],
            "report": name + "/report.json",
            "sound": native.get("sound"),
            "complete": native["complete"],
            "native_processes": native.get(
                "native_processes", native["summary"].get("native_runs", 0)
            ),
        }
        rows.extend(native["results"])
        summary = summarize(rows, declared_rows=declared)
        summary["complete"] = summary["complete"] and all(
            part["complete"] for part in reports.values()
        )
        summary["expectations_met"] = summary["complete"] and summary["expectations_met"]
        report = {
            "schema": "evalsentinel.audit.v1",
            "evalsentinel_version": __version__,
            "adapter": "all",
            "created_at": datetime.now(UTC).isoformat(),
            "sources": reports,
            "results": rows,
            "summary": summary,
            "complete": summary["complete"],
            "expectations_met": summary["expectations_met"],
            "model_api_calls": 0,
            "gpu_required": False,
            "native_processes": sum(part["native_processes"] for part in reports.values()),
            "owasp_assertion_invocations": sum(
                bool(row.get("native_observation", {}).get("assertion_invoked"))
                for row in rows
                if row.get("native_observation") is not None
            ),
        }
        write_report(output, report)
    report["sound"] = report["complete"] and owasp.adjudicated_sound(rows)
    write_report(output, report)
    return report

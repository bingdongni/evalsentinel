"""Compose native adapters while keeping their evidence and denominators intact."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalsentinel import __version__, mcp, owasp
from evalsentinel.catalog import CONTROLS, VERSIONS
from evalsentinel.owasp_catalog import corpus
from evalsentinel.report import summarize, write_report


def audit(mcp_checkout: Path, baseline: Path, candidate: Path, output: Path) -> dict[str, Any]:
    mcp.provenance(mcp_checkout)
    owasp.provenance(baseline, "baseline")
    owasp.provenance(candidate, "candidate")
    output.mkdir(parents=True, exist_ok=False)
    declared = len(CONTROLS) * len(VERSIONS) + len(corpus()["cases"]) * 2
    rows = []
    reports: dict[str, dict[str, Any]] = {}
    stages = (
        ("mcp", lambda: mcp.audit(mcp_checkout, output / "mcp", list(VERSIONS))),
        ("baseline", lambda: owasp.audit(baseline, output / "baseline", "baseline")),
        ("candidate", lambda: owasp.audit(candidate, output / "candidate", "candidate")),
    )
    for name, run in stages:
        native = run()
        reports[name] = {
            "source": native["source"],
            "summary": native["summary"],
            "report": name + "/report.json",
            "sound": native.get("sound"),
            "native_processes": native.get(
                "native_processes", native["summary"].get("native_runs", 0)
            ),
        }
        rows.extend(native["results"])
        summary = summarize(rows, declared_rows=declared)
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
    report["sound"] = owasp.adjudicated_sound(rows)
    write_report(output, report)
    return report

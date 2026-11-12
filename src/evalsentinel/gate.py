"""Check a maintainer-selected native commit against a versioned finite contract."""

from pathlib import Path
from platform import python_implementation, python_version
from typing import Any

from evalsentinel import owasp
from evalsentinel.report import summarize, write_report

CONTRACT = "single-use-approval-v1"
TOTAL_CONTROLS = 22
SEMANTIC_CONTROLS = 18
VIOLATIONS = {"false_accept", "false_reject", "evidence_scope_violation"}
SEMANTIC = {"correct_accept", "correct_reject", "false_accept", "false_reject"}


def _policy_rows(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        observed = row["native_observation"]
        native = observed.get("native") if isinstance(observed, dict) else None
        valid = (
            isinstance(native, dict)
            and native.get("id") == "approval_required"
            and observed.get("stage") == "assertion"
            and observed.get("assertion_invoked") is True
            and observed.get("error") is None
            and native.get("result") in ("pass", "fail")
        )
        if row["polarity"] == "unsupported" and valid:
            row.update(
                expectation_met=True,
                expected_native=None,
                reason="Evidence property excluded from adjudication; native verdict retained",
            )
        if row["polarity"] == "not_run" and valid:
            row.update(
                classification="evidence_scope_violation",
                expectation_met=False,
                reason="An unexercised action received a decisive native verdict",
            )


def assess(report: dict[str, Any], diagnostics: list[dict[str, str]]) -> dict[str, Any]:
    rows = report["results"]
    semantic = [row for row in rows if row["polarity"] in {"good", "bad"}]
    failures = [row["control"] for row in rows if row["classification"] in VIOLATIONS]
    unexpected = [
        row["control"]
        for row in rows
        if row["classification"] not in VIOLATIONS and not row["expectation_met"]
    ]
    # No invocation, error or unsupported result on a semantic case is a catch.
    unexpected.extend(row["control"] for row in semantic if row["classification"] not in SEMANTIC)
    invalid_denominator = (
        len(rows) != TOTAL_CONTROLS
        or len({row["control"] for row in rows}) != TOTAL_CONTROLS
        or len(semantic) != SEMANTIC_CONTROLS
    )
    operational_error = not report["complete"] or diagnostics or unexpected or invalid_denominator
    status, code = (
        ("error", 2) if operational_error else ("violated", 1) if failures else ("passed", 0)
    )
    return {
        "status": status,
        "exit_code": code,
        "semantic_controls": len(semantic),
        "guard_controls": sum(row["polarity"] in {"invalid", "not_run"} for row in rows),
        "unsupported_controls": sum(row["polarity"] == "unsupported" for row in rows),
        "violations": failures,
        "unexpected_controls": sorted(set(unexpected)),
        "diagnostics": diagnostics,
    }


def check(
    checkout: Path,
    output: Path,
    expected_commit: str,
    *,
    contract: str,
    timeout: float = 25,
) -> dict[str, Any]:
    if contract != CONTRACT:
        raise ValueError(f"Select the supported contract: {CONTRACT}")
    if not 1 <= timeout <= owasp.MAX_TIMEOUT:
        raise ValueError("OWASP timeout must be between 1 and 60 seconds")
    checkout = checkout.resolve()
    output = output.resolve()
    source = owasp.target_provenance(checkout, expected_commit)
    report = owasp.observe(checkout, output, "candidate", source=source, timeout=timeout)
    diagnostics = []
    if report["worker_source_sha256"] != source["source_sha256"]:
        diagnostics.append(
            {
                "code": "LOADED_SOURCE_MISMATCH",
                "message": "Worker source hashes differ from preflight",
            }
        )
    try:
        after = owasp.target_provenance(checkout, expected_commit)
    except (OSError, ValueError) as error:
        diagnostics.append({"code": "SOURCE_CHANGED", "message": str(error)})
    else:
        if after["source_sha256"] != source["source_sha256"]:
            diagnostics.append(
                {
                    "code": "SOURCE_CHANGED",
                    "message": "Native source hashes changed during execution",
                }
            )
    _policy_rows(report["results"])
    report.update(
        schema="evalsentinel.check.v1",
        contract={"id": CONTRACT, "corpus_sha256": source["corpus_sha256"]},
        mode="contract-check",
        summary=summarize(report["results"]),
        runtime={"python": python_version(), "implementation": python_implementation()},
    )
    report["semantic_controls_met"] = report.pop("sound")
    report["summary"].pop("native_runs")
    report["summary"]["native_processes"] = report["native_processes"]
    report["expectations_met"] = all(row["expectation_met"] for row in report["results"])
    report["summary"].update(
        complete=report["complete"],
        native_observed_controls=sum(
            row["native_observation"] is not None for row in report["results"]
        ),
        assertions_invoked=sum(
            isinstance(row["native_observation"], dict)
            and row["native_observation"].get("assertion_invoked") is True
            for row in report["results"]
        ),
    )
    report["source"]["verified_after_run"] = not any(
        item["code"] == "SOURCE_CHANGED" for item in diagnostics
    )
    report["gate"] = assess(report, diagnostics)
    report["passed"] = report["gate"]["exit_code"] == 0
    write_report(output, report)
    return report


def console_summary(report: dict[str, Any], output: Path) -> str:
    gate = report["gate"]
    counts = report["summary"]["classifications"]
    lines = [
        f"{gate['status'].upper()}: {report['contract']['id']}",
        (
            f"Semantic controls: {gate['semantic_controls']}; "
            f"false accepts: {counts.get('false_accept', 0)}; "
            f"false rejects: {counts.get('false_reject', 0)}"
        ),
        (
            f"Guards: {gate['guard_controls']}; unsupported evidence properties: "
            f"{gate['unsupported_controls']} (outside semantic denominator)"
        ),
    ]
    failures = {*gate["violations"], *gate["unexpected_controls"]}
    lines.extend(
        f"  {row['control']}: {row['classification']} — {row['reason']}"
        for row in report["results"]
        if row["control"] in failures
    )
    lines.extend(f"  {item['code']}: {item['message']}" for item in gate["diagnostics"])
    lines.append(f"Report: {output.resolve() / 'report.json'}")
    return "\n".join(lines)

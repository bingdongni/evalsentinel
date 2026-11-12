"""Compare observations to declared controls without implementing protocol predicates."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from evalsentinel.catalog import CHECK_IDS, Control

type Classification = Literal[
    "correct_accept",
    "correct_reject",
    "false_accept",
    "false_reject",
    "not_run",
    "unsupported",
    "insufficient_evidence",
    "error",
]
STATUSES = {"SUCCESS", "FAILURE", "WARNING", "SKIPPED", "INFO"}


@dataclass(frozen=True)
class Comparison:
    classification: Classification
    expectation_met: bool
    reason: str


def _read_checks(raw: object) -> dict[str, dict[str, Any]] | Comparison:
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        return Comparison("error", False, "Native checks must be a JSON array of objects")
    checks: dict[str, dict[str, Any]] = {}
    for item in raw:
        check_id = item.get("id")
        status = item.get("status")
        if not isinstance(check_id, str) or not isinstance(status, str) or status not in STATUSES:
            return Comparison("error", False, "Native check has an invalid id or status")
        if check_id in checks:
            return Comparison("error", False, f"Duplicate native check: {check_id}")
        if not isinstance(item.get("details", {}), dict):
            return Comparison("error", False, f"Invalid details for native check: {check_id}")
        untestable = item.get("details", {}).get("untestable", False)
        if not isinstance(untestable, bool):
            return Comparison("error", False, f"Invalid untestable flag: {check_id}")
        checks[check_id] = item
    return checks


def _semantic_evidence(checks: dict[str, dict[str, Any]]) -> Comparison | None:
    if "wire-schema-harness-error" in checks:
        return Comparison("error", False, "Native harness reported a wire-schema error")
    if any(check_id not in checks for check_id in CHECK_IDS):
        return Comparison(
            "insufficient_evidence", False, "A required native semantic check is missing"
        )
    if set(checks) - {*CHECK_IDS, "wire-schema-valid"}:
        return Comparison("error", False, "Unexpected native check IDs for the pinned scenario")
    if any(checks[check_id]["status"] == "SKIPPED" for check_id in CHECK_IDS):
        return Comparison("unsupported", False, "A required native check was skipped")
    return None


def _wire_evidence(checks: dict[str, dict[str, Any]], exit_code: int) -> Comparison | None:
    wire = checks.get("wire-schema-valid")
    if wire is None:
        return Comparison(
            "insufficient_evidence", False, "Wire-schema validation evidence is missing"
        )
    count = wire.get("details", {}).get("messagesValidated")
    violations = wire.get("details", {}).get("violations")
    if wire["status"] != "SUCCESS" or type(count) is not int or count <= 0 or violations != []:
        return Comparison("error", False, "Wire-schema validation failed or observed no messages")
    if exit_code not in (0, 1):
        return Comparison(
            "error", False, "Native CLI did not complete with a normal conformance exit"
        )
    return None


def _positive(semantic: list[dict[str, Any]], exit_code: int, *, exact: bool) -> Comparison:
    if any(item.get("details", {}).get("untestable") is True for item in semantic):
        return Comparison("not_run", False, "A positive control did not exercise required checks")
    accepted = all(item["status"] == "SUCCESS" for item in semantic)
    if accepted and exit_code != 0:
        return Comparison("error", False, "Native checks passed but the client/CLI failed")
    return Comparison(
        "correct_accept" if accepted else "false_reject",
        exact,
        "Positive control accepted" if accepted else "A valid control was rejected",
    )


def _negative(
    control: Control,
    checks: dict[str, dict[str, Any]],
    exit_code: int,
    *,
    exact: bool,
) -> Comparison:
    focus = checks.get(control.focus or "")
    if focus is None:
        return Comparison("error", False, "The negative control has no target check")
    if focus.get("details", {}).get("untestable") is True:
        return Comparison("not_run", False, "The defect's target check was not exercised")
    if focus["status"] == "SUCCESS":
        return Comparison("false_accept", False, "The target check accepted the known defect")
    if focus["status"] not in ("FAILURE", "WARNING"):
        return Comparison(
            "insufficient_evidence", False, "The target check has no decisive verdict"
        )
    if exit_code != 1:
        return Comparison("error", False, "A rejecting native check did not yield a failure exit")
    return Comparison(
        "correct_reject", exact, "The exercised target check rejected the known defect"
    )


def compare(control: Control, raw: object, exit_code: int) -> Comparison:
    checks = _read_checks(raw)
    if isinstance(checks, Comparison):
        return checks
    issue = _semantic_evidence(checks)
    if issue:
        return issue
    semantic = [checks[check_id] for check_id in CHECK_IDS]
    exact = tuple(item["status"] for item in semantic) == control.expected
    exact = exact and exit_code == control.expected_exit
    if control.polarity == "not_run":
        unexercised = all(item.get("details", {}).get("untestable") is True for item in semantic)
        exact = exact and unexercised and "wire-schema-valid" not in checks
        return Comparison("not_run", exact, "Deliberate inert control; never counted as a catch")
    issue = _wire_evidence(checks, exit_code)
    if issue:
        return issue
    if control.polarity == "good":
        return _positive(semantic, exit_code, exact=exact)
    return _negative(control, checks, exit_code, exact=exact)


def summarize(rows: list[dict[str, Any]], *, declared_rows: int | None = None) -> dict[str, Any]:
    counts = Counter(row["classification"] for row in rows)
    declared = len(rows) if declared_rows is None else declared_rows
    complete = len(rows) == declared
    return {
        "declared_rows": declared,
        "observed_rows": len(rows),
        "complete": complete,
        "independent_controls": len({row["control"] for row in rows}),
        "native_runs": sum(row["native_started"] for row in rows),
        "classifications": dict(counts),
        "expectations_matched": sum(row["expectation_met"] for row in rows),
        "expectations_met": bool(rows) and complete and all(row["expectation_met"] for row in rows),
    }


def write_report(output: Path, report: dict[str, Any]) -> None:
    pending = output / "report.json.tmp"
    pending.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pending.replace(output / "report.json")

"""Versioned, attributed known-answer inputs for the unmodified native assertion."""

import hashlib
import json
import re
from importlib.resources import files
from typing import Any

POLARITIES = {"good", "bad", "not_run", "unsupported", "invalid"}
NATIVE_RESULTS = {"pass", "fail", "not_run", "error"}
REVISIONS = ("baseline", "candidate")


def _validate_case(case: object, seen: set[str]) -> None:
    if not isinstance(case, dict):
        raise TypeError("Every OWASP case must be an object")
    case_id = case.get("id", "")
    if not isinstance(case_id, str) or not re.fullmatch(r"owasp-[a-z0-9-]+", case_id):
        raise ValueError("Invalid OWASP case identifier")
    polarity = case.get("polarity")
    if case_id in seen or not isinstance(polarity, str) or polarity not in POLARITIES:
        raise ValueError("Duplicate OWASP case or invalid polarity")
    seen.add(case_id)
    if not isinstance(case.get("trace"), dict):
        raise TypeError("Every case must declare its native trace envelope")
    expected = case.get("expected_native")
    if not isinstance(expected, dict) or any(
        not isinstance(expected.get(r), str) or expected[r] not in NATIVE_RESULTS for r in REVISIONS
    ):
        raise ValueError("Every case must declare both characterized native results")
    for field in ("rationale", "requirement", "expected_contract", "source"):
        if not isinstance(case.get(field), str) or not case[field]:
            raise ValueError(f"Missing OWASP case field: {field}")
    contract = {
        "good": "pass",
        "bad": "fail",
        "not_run": "not_run",
        "unsupported": "unsupported",
        "invalid": "error",
    }[polarity]
    if case["expected_contract"] != contract:
        raise ValueError("The declared contract and polarity disagree")


def corpus() -> dict[str, Any]:
    raw = files("evalsentinel").joinpath("data/owasp-approval.json").read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError("The OWASP corpus must be an object")
    cases = data.get("cases")
    if data.get("schema") != "evalsentinel.owasp-corpus.v1" or not isinstance(cases, list):
        raise ValueError("Invalid OWASP corpus schema")
    if not cases or len(cases) != data.get("case_count"):
        raise ValueError("The OWASP corpus case denominator does not match its manifest")
    pins = data.get("pins")
    if not isinstance(pins, dict) or any(
        not isinstance(pins.get(r), str) or not re.fullmatch(r"[0-9a-f]{40}", pins[r])
        for r in REVISIONS
    ):
        raise ValueError("Every native revision needs a full commit pin")
    seen: set[str] = set()
    for case in cases:
        _validate_case(case, seen)
    data["sha256"] = hashlib.sha256(raw).hexdigest()
    return data

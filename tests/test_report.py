from dataclasses import replace

import pytest

from evalsentinel.catalog import CONTROLS, Control
from evalsentinel.report import compare, summarize


@pytest.mark.parametrize("control", CONTROLS, ids=lambda c: c.id)
def test_declared_good_bad_and_inert_controls_stay_distinct(
    control: Control, native_checks
) -> None:
    result = compare(control, native_checks(control), control.expected_exit)
    assert result.expectation_met
    assert (
        result.classification
        == {
            "good": "correct_accept",
            "bad": "correct_reject",
            "not_run": "not_run",
        }[control.polarity]
    )


def test_bad_behavior_accepted_by_target_is_a_false_accept(native_checks) -> None:
    control = CONTROLS[1]
    checks = native_checks(control)
    checks[0]["status"] = "SUCCESS"
    result = compare(control, checks, 1)
    assert result.classification == "false_accept"
    assert not result.expectation_met


def test_a_nonzero_exit_alone_is_not_a_catch(native_checks) -> None:
    result = compare(CONTROLS[1], native_checks(), 1)
    assert result.classification == "false_accept"
    assert not result.expectation_met


def test_an_unexercised_bad_target_is_not_a_catch(native_checks) -> None:
    control = CONTROLS[1]
    checks = native_checks(control)
    checks[0]["details"]["untestable"] = True
    assert compare(control, checks, 1).classification == "not_run"
    assert not compare(control, checks, 1).expectation_met


def test_valid_behavior_rejected_is_a_false_reject(native_checks) -> None:
    checks = native_checks()
    checks[0]["status"] = "FAILURE"
    result = compare(CONTROLS[0], checks, 1)
    assert result.classification == "false_reject"
    assert not result.expectation_met


def test_positive_control_without_exercise_is_not_run(native_checks) -> None:
    checks = native_checks()
    checks[0]["details"]["untestable"] = True
    assert compare(CONTROLS[0], checks, 0).classification == "not_run"


def test_native_check_order_is_not_a_behavioral_requirement(native_checks) -> None:
    assert compare(CONTROLS[0], list(reversed(native_checks())), 0).expectation_met


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", ["SUCCESS"]),
        ("status", None),
        ("id", 12),
        ("status", "PASS"),
        ("details", []),
    ],
)
def test_malformed_native_fields_are_errors(field: str, value: object, native_checks) -> None:
    checks = native_checks()
    checks[0][field] = value
    result = compare(CONTROLS[0], checks, 0)
    assert result.classification == "error"
    assert not result.expectation_met


@pytest.mark.parametrize(
    ("raw", "classification"),
    [
        ({}, "error"),
        (["wrong shape"], "error"),
        ([], "insufficient_evidence"),
    ],
)
def test_absent_or_malformed_native_output_never_passes(raw: object, classification: str) -> None:
    result = compare(CONTROLS[0], raw, 1)
    assert result.classification == classification
    assert not result.expectation_met


def test_duplicate_native_check_cannot_hide_a_verdict(native_checks) -> None:
    checks = native_checks()
    checks.append({**checks[0], "status": "FAILURE"})
    assert compare(CONTROLS[0], checks, 0).classification == "error"


def test_malformed_untestable_flag_is_not_interpreted_as_exercised(native_checks) -> None:
    checks = native_checks()
    checks[0]["details"]["untestable"] = "true"
    assert compare(CONTROLS[0], checks, 0).classification == "error"


def test_missing_or_skipped_required_checks_stay_explicit(native_checks) -> None:
    checks = native_checks()
    assert compare(CONTROLS[0], checks[1:], 0).classification == "insufficient_evidence"
    checks[0]["status"] = "SKIPPED"
    assert compare(CONTROLS[0], checks, 0).classification == "unsupported"


@pytest.mark.parametrize("check_id", ["unexpected-new-check", "wire-schema-harness-error"])
def test_unexpected_checks_and_harness_errors_are_errors(check_id: str, native_checks) -> None:
    checks = native_checks()
    checks.append({"id": check_id, "status": "FAILURE"})
    assert compare(CONTROLS[0], checks, 1).classification == "error"


def test_missing_wire_evidence_is_insufficient(native_checks) -> None:
    assert compare(CONTROLS[0], native_checks()[:-1], 0).classification == "insufficient_evidence"


@pytest.mark.parametrize(("count", "violations"), [(0, []), (True, []), ("10", []), (10, [{}])])
def test_invalid_wire_evidence_is_not_a_semantic_catch(
    count: object, violations: object, native_checks
) -> None:
    control = CONTROLS[1]
    checks = native_checks(control)
    checks[-1]["details"] = {"messagesValidated": count, "violations": violations}
    assert compare(control, checks, 1).classification == "error"


def test_failed_wire_schema_is_not_a_catch(native_checks) -> None:
    checks = native_checks(CONTROLS[1])
    checks[-1]["status"] = "FAILURE"
    assert compare(CONTROLS[1], checks, 1).classification == "error"


@pytest.mark.parametrize(
    ("control", "exit_code"), [(CONTROLS[0], 1), (CONTROLS[1], 0), (CONTROLS[1], 137)]
)
def test_process_failure_and_inconsistent_exit_codes_are_errors(
    control: Control, exit_code: int, native_checks
) -> None:
    assert compare(control, native_checks(control), exit_code).classification == "error"


def test_inert_control_is_not_counted_as_a_detection(native_checks) -> None:
    control = CONTROLS[6]
    checks = native_checks(control)
    checks[0]["details"]["untestable"] = False
    assert not compare(control, checks, 1).expectation_met
    checks = [*native_checks(control), native_checks()[-1]]
    assert not compare(control, checks, 1).expectation_met


def test_bad_control_requires_a_decisive_target_and_full_expectation(native_checks) -> None:
    control = CONTROLS[1]
    checks = native_checks(control)
    checks[0]["status"] = "INFO"
    assert compare(control, checks, 1).classification == "insufficient_evidence"
    assert (
        compare(replace(control, focus=None), native_checks(control), 1).classification == "error"
    )
    checks = native_checks(control)
    checks[1]["status"] = "SUCCESS"
    result = compare(control, checks, 1)
    assert result.classification == "correct_reject"
    assert not result.expectation_met


def test_empty_partial_and_repeated_version_denominators(native_checks) -> None:
    assert not summarize([])["expectations_met"]
    rows = []
    for control in CONTROLS:
        result = compare(control, native_checks(control), control.expected_exit)
        rows.append(
            {
                "control": control.id,
                "native_started": True,
                "classification": result.classification,
                "expectation_met": result.expectation_met,
            }
        )
    assert not summarize(rows, declared_rows=16)["expectations_met"]
    summary = summarize(rows * 2, declared_rows=16)
    assert summary["expectations_met"]
    assert summary["independent_controls"] == 8
    assert summary["native_runs"] == 16
    assert summary["classifications"] == {"correct_accept": 4, "correct_reject": 10, "not_run": 2}

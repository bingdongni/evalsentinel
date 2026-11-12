import json
from copy import deepcopy
from pathlib import Path

import pytest

from evalsentinel import cli, owasp, owasp_catalog, suite
from evalsentinel.owasp_catalog import corpus
from evalsentinel.owasp_worker import offline_socket_guard
from evalsentinel.process import ProcessResult

CASES = corpus()["cases"]


def observation(case: dict, revision: str) -> dict:
    expected = case["expected_native"][revision]
    return {
        "control": case["id"],
        "assertion_invoked": expected != "error",
        "stage": "trace_validation" if expected == "error" else "assertion",
        "native": None if expected == "error" else {"id": "approval_required", "result": expected},
        "error": {"type": "TraceValidationError", "stage": "trace_validation"}
        if expected == "error"
        else None,
    }


@pytest.mark.parametrize("revision", ["baseline", "candidate"])
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_characterized_native_observations_never_erase_contract_failures(
    case: dict, revision: str
) -> None:
    result = owasp.compare(case, observation(case, revision), revision)
    assert result["expectation_met"]
    if case["polarity"] == "bad" and case["expected_native"][revision] == "pass":
        assert result["classification"] == "false_accept"
    elif case["polarity"] in {"not_run", "unsupported"}:
        assert result["classification"] == case["polarity"]
    elif case["polarity"] == "invalid":
        assert result["classification"] == "error"
    else:
        assert result["classification"] == (
            "correct_accept" if case["polarity"] == "good" else "correct_reject"
        )


def test_unknown_bad_acceptance_fails_characterization_and_soundness() -> None:
    case = next(c for c in CASES if c["id"] == "owasp-replay-identical")
    raw = observation(case, "candidate")
    raw["native"]["result"] = "pass"
    result = owasp.compare(case, raw, "candidate")
    assert result["classification"] == "false_accept"
    assert not result["expectation_met"]
    assert not owasp.adjudicated_sound([{"polarity": "bad", **result}])


@pytest.mark.parametrize("raw", [None, [], {"control": "wrong"}])
def test_missing_native_observations_are_errors(raw: object) -> None:
    result = owasp.compare(CASES[0], raw, "candidate")
    assert result["classification"] == "error"
    assert not result["expectation_met"]


@pytest.mark.parametrize(
    ("field", "value"), [("id", "wrong"), ("result", ["pass"]), ("result", "unknown")]
)
def test_malformed_verdicts_do_not_become_catches(field: str, value: object) -> None:
    raw = observation(CASES[0], "candidate")
    raw["native"][field] = value
    assert not owasp.compare(CASES[0], raw, "candidate")["expectation_met"]


def test_uninvoked_and_unexpected_errors_stay_failures() -> None:
    invalid = next(c for c in CASES if c["polarity"] == "invalid")
    raw = observation(invalid, "candidate")
    raw["error"]["type"] = "RuntimeError"
    assert not owasp.compare(invalid, raw, "candidate")["expectation_met"]
    raw = observation(invalid, "candidate")
    raw["native"] = {"id": "approval_required", "result": "pass"}
    assert not owasp.compare(invalid, raw, "candidate")["expectation_met"]
    raw = observation(CASES[0], "candidate")
    raw["assertion_invoked"] = False
    assert not owasp.compare(CASES[0], raw, "candidate")["expectation_met"]
    raw = observation(CASES[0], "candidate")
    raw["native"]["result"] = "error"
    assert owasp.compare(CASES[0], raw, "candidate")["classification"] == "error"
    raw = observation(invalid, "candidate")
    raw.update(
        {
            "error": None,
            "native": {"id": "approval_required", "result": "pass"},
            "stage": "assertion",
            "assertion_invoked": True,
        }
    )
    assert not owasp.compare(invalid, raw, "candidate")["expectation_met"]


@pytest.mark.parametrize("event", ["socket.connect", "socket.getaddrinfo", "socket.sendto"])
def test_worker_blocks_python_network_connections(event: str) -> None:
    with pytest.raises(RuntimeError, match="Network operations"):
        offline_socket_guard(event, ())
    offline_socket_guard("open", ())


@pytest.mark.parametrize("failure", ["none", "timeout", "exit", "malformed", "duplicate", "empty"])
def test_native_batch_result_validation(failure: str, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(owasp, "provenance", lambda *_args: {"commit": "pin"})
    values = [observation(case, "candidate") for case in CASES]
    if failure == "duplicate":
        values.append(deepcopy(values[0]))
    if failure == "empty":
        values = []
    payload = json.dumps({"observations": values, "network_policy": "python-sockets-denied"})
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(
            1 if failure == "exit" else 0,
            "invalid" if failure == "malformed" else payload,
            "",
            timed_out=failure == "timeout",
        ),
    )
    result = owasp.audit(tmp_path, tmp_path / "out", "candidate")
    assert result["expectations_met"] == (failure == "none")
    assert result["sound"] == (failure == "none")
    assert result["summary"]["independent_controls"] == 22
    if failure != "none":
        assert result["summary"]["classifications"] == {"error": 22}


@pytest.mark.parametrize("revision", ["baseline", "candidate"])
def test_checkout_pin_and_clean_source_are_verified(
    revision: str, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(owasp.shutil, "which", lambda _tool: "git")
    for filename in ("assertions.py", "scenario.py", "trace.py", "result.py"):
        target = tmp_path / "src/agent_harness" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# native fixture\n", encoding="utf-8")

    def run(command: list[str], **_kwargs: object) -> ProcessResult:
        return ProcessResult(
            0, corpus()["pins"][revision] if command[-1] == "HEAD" else "", "", timed_out=False
        )

    monkeypatch.setattr(owasp, "run_process", run)
    assert owasp.provenance(tmp_path, revision)["commit"] == corpus()["pins"][revision]
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(0, "dirty", "", timed_out=False),
    )
    with pytest.raises(ValueError, match="clean native"):
        owasp.provenance(tmp_path, revision)


def test_invalid_environment_and_soundness_gate(monkeypatch, tmp_path: Path, capsys) -> None:
    with pytest.raises(ValueError, match="Select baseline"):
        owasp.provenance(tmp_path, "unknown")
    monkeypatch.setattr(owasp.shutil, "which", lambda _tool: None)
    with pytest.raises(ValueError, match="Git is required"):
        owasp.provenance(tmp_path, "candidate")
    with pytest.raises(ValueError, match="timeout"):
        owasp.audit(tmp_path, tmp_path, "candidate", timeout=0)
    monkeypatch.setattr(
        owasp,
        "audit",
        lambda *_args, **_kwargs: {
            "complete": True,
            "summary": {"native_runs": 16},
            "sound": False,
            "expectations_met": True,
        },
    )
    assert cli.main(["audit", "owasp", "--checkout", str(tmp_path), "--revision", "baseline"]) == 0
    assert cli.main(["audit", "owasp", "--checkout", str(tmp_path), "--require-sound"]) == 1
    assert cli.main(["audit", "all"]) == 2
    assert cli.main(["audit", "owasp"]) == 2
    assert (
        cli.main(["audit", "owasp", "--checkout", str(tmp_path), "--spec-version", "2025-11-25"])
        == 2
    )
    capsys.readouterr()


def test_corpus_rejects_missing_metadata_and_duplicate_ids(monkeypatch) -> None:
    original = corpus()

    class Resource:
        def __init__(self) -> None:
            self.payload = {}

        def joinpath(self, _path: str) -> "Resource":
            return self

        def read_bytes(self) -> bytes:
            return json.dumps(self.payload).encode()

    resource = Resource()
    monkeypatch.setattr(owasp_catalog, "files", lambda _package: resource)
    for payload in ({}, {**original, "case_count": 99}, {**original, "cases": []}):
        resource.payload = payload
        with pytest.raises(ValueError, match=r"schema|denominator"):
            corpus()
    bad = deepcopy(original)
    bad["cases"][1]["id"] = bad["cases"][0]["id"]
    resource.payload = bad
    with pytest.raises(ValueError, match="Duplicate"):
        corpus()


def test_full_suite_denominator_and_native_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(suite.mcp, "provenance", lambda *_args: {})
    monkeypatch.setattr(suite.owasp, "provenance", lambda *_args: {})

    def mcp(*_args: object, **_kwargs: object) -> dict:
        return {
            "source": {},
            "summary": {"native_runs": 16},
            "results": [
                {
                    "control": f"mcp-{i}",
                    "polarity": "good",
                    "classification": "correct_accept",
                    "native_started": True,
                    "expectation_met": True,
                }
                for i in range(8)
            ]
            * 2,
        }

    def native(_checkout, _output, revision: str, **_kwargs: object) -> dict:
        return {
            "source": {},
            "summary": {},
            "native_processes": 1,
            "sound": revision == "candidate",
            "results": [
                {
                    "control": case["id"],
                    "polarity": case["polarity"],
                    "native_started": True,
                    **owasp.compare(case, observation(case, revision), revision),
                }
                for case in CASES
            ],
        }

    monkeypatch.setattr(suite.mcp, "audit", mcp)
    monkeypatch.setattr(suite.owasp, "audit", native)
    result = suite.audit(tmp_path, tmp_path, tmp_path, tmp_path / "all")
    assert result["summary"]["independent_controls"] == 30
    assert result["summary"]["declared_rows"] == 60
    assert result["native_processes"] == 18
    assert result["expectations_met"]
    assert not result["sound"]


def test_full_suite_timeout_is_validated_before_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Full-suite timeout"):
        suite.audit(tmp_path, tmp_path, tmp_path, tmp_path, timeout=1)

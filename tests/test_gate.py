import json
from copy import deepcopy
from pathlib import Path

import pytest

from evalsentinel import cli, gate, owasp
from evalsentinel.process import ProcessResult
from tests.test_owasp import CASES, observation

TARGET = "a" * 40
HASHES = {
    f"src/agent_harness/{name}.py": "b" * 64
    for name in ("assertions", "trace", "scenario", "result")
}


@pytest.fixture
def native(monkeypatch) -> dict:
    source = {
        "commit": TARGET,
        "revision": "target",
        "source_sha256": HASHES,
        "corpus_sha256": "fixture-corpus",
        "kind": "user-selected-git-checkout",
    }
    monkeypatch.setattr(owasp, "target_provenance", lambda *_args: deepcopy(source))
    payload = {
        "observations": [observation(case, "candidate") for case in CASES],
        "network_policy": "python-sockets-denied",
        "source_sha256": HASHES,
    }
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(0, json.dumps(payload), "", timed_out=False),
    )
    return payload


def run_gate(tmp_path: Path) -> dict:
    return gate.check(tmp_path, tmp_path / "out", TARGET, contract=gate.CONTRACT)


@pytest.mark.usefixtures("native")
def test_current_commit_gate_has_an_explicit_finite_denominator(tmp_path: Path) -> None:
    report = run_gate(tmp_path)
    assert report["schema"] == "evalsentinel.check.v1"
    assert report["source"]["commit"] == TARGET
    assert "repository" not in report["source"]
    assert report["source"]["verified_after_run"]
    assert report["gate"]["exit_code"] == 0
    assert report["passed"]
    assert "sound" not in report
    assert report["semantic_controls_met"]
    assert report["gate"]["semantic_controls"] == 18
    assert report["gate"]["guard_controls"] == 2
    assert report["gate"]["unsupported_controls"] == 2
    assert report["summary"]["classifications"]["error"] == 1
    assert report["summary"]["native_observed_controls"] == 22
    assert report["summary"]["assertions_invoked"] == 21
    assert {row["revision"] for row in report["results"]} == {"target"}


@pytest.mark.parametrize("polarity", ["good", "bad", "not_run"])
def test_real_native_verdict_changes_block_the_gate(native, tmp_path: Path, polarity: str) -> None:
    case = next(item for item in CASES if item["polarity"] == polarity)
    raw = next(item for item in native["observations"] if item["control"] == case["id"])
    raw["native"]["result"] = "fail" if polarity == "good" else "pass"
    report = run_gate(tmp_path)
    assert report["gate"]["status"] == "violated"
    assert report["gate"]["exit_code"] == 1
    assert case["id"] in report["gate"]["violations"]
    assert report["gate"]["unexpected_controls"] == []
    assert report["results"][CASES.index(case)]["native_observation"] == raw
    assert case["id"] in gate.console_summary(report, tmp_path / "out")


@pytest.mark.parametrize("verdict", ["pass", "fail", "error", ["pass"]])
def test_unsupported_evidence_is_not_a_semantic_catch(native, tmp_path: Path, verdict) -> None:
    case = next(item for item in CASES if item["polarity"] == "unsupported")
    raw = next(item for item in native["observations"] if item["control"] == case["id"])
    raw["native"]["result"] = verdict
    report = run_gate(tmp_path)
    assert report["gate"]["exit_code"] == (0 if verdict in ("pass", "fail") else 2)
    assert report["gate"]["semantic_controls"] == 18
    if verdict in ("pass", "fail"):
        assert report["results"][CASES.index(case)]["classification"] == "unsupported"


@pytest.mark.parametrize("fault", ["duplicate", "empty", "hash", "stage", "error", "not_run"])
def test_native_protocol_and_execution_errors_fail_closed(
    native, tmp_path: Path, fault: str
) -> None:
    if fault == "duplicate":
        native["observations"].append(deepcopy(native["observations"][0]))
    elif fault == "empty":
        native["observations"] = []
    elif fault == "hash":
        native["source_sha256"] = {}
    else:
        raw = native["observations"][0]
        if fault == "stage":
            raw["stage"] = "scenario_validation"
        elif fault == "error":
            raw.update(native=None, error={"type": "RuntimeError", "stage": "assertion"})
        else:
            raw["native"]["result"] = "not_run"
    report = run_gate(tmp_path)
    assert report["gate"]["exit_code"] == 2
    assert report["gate"]["status"] == "error"
    if fault in {"empty", "duplicate"}:
        assert not report["complete"]
        assert report["summary"]["native_observed_controls"] == 0


@pytest.mark.parametrize("failure", ["timeout", "exit", "malformed"])
@pytest.mark.usefixtures("native")
def test_worker_failures_are_not_contract_rejections(
    monkeypatch, tmp_path: Path, failure: str
) -> None:
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(
            1 if failure == "exit" else 0,
            "not JSON",
            "worker failed",
            timed_out=failure == "timeout",
        ),
    )
    report = run_gate(tmp_path)
    assert report["gate"]["exit_code"] == 2
    assert not report["complete"]
    assert report["gate"]["violations"] == []
    assert report["summary"]["assertions_invoked"] == 0


@pytest.mark.parametrize("changed", ["head", "hash"])
@pytest.mark.usefixtures("native")
def test_source_changes_after_execution_cannot_pass(
    monkeypatch, tmp_path: Path, changed: str
) -> None:
    original = owasp.target_provenance(tmp_path, TARGET)
    calls = 0

    def provenance(*_args: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 2:
            if changed == "head":
                raise ValueError("Source HEAD changed")
            return {**original, "source_sha256": {}}
        return deepcopy(original)

    monkeypatch.setattr(owasp, "target_provenance", provenance)
    report = run_gate(tmp_path)
    assert report["gate"]["exit_code"] == 2
    assert not report["source"]["verified_after_run"]


@pytest.mark.parametrize("pin", ["", "main", "abc123", "g" * 40])
def test_target_requires_an_immutable_full_commit(pin: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="40-hex"):
        owasp.target_provenance(tmp_path, pin)


def test_target_accepts_a_new_clean_commit(monkeypatch, tmp_path: Path) -> None:
    for name in ("assertions", "trace", "scenario", "result"):
        path = tmp_path / f"src/agent_harness/{name}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# native fixture\n", encoding="utf-8")
    monkeypatch.setattr(owasp.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda command, **_kwargs: ProcessResult(
            0,
            "# native fixture\n" if "show" in command else TARGET if command[-1] == "HEAD" else "",
            "",
            timed_out=False,
        ),
    )
    source = owasp.target_provenance(tmp_path, TARGET.upper())
    assert source["commit"] == TARGET
    assert source["revision"] == "target"
    assert source["tracked_tree_clean"]
    assert "repository" not in source
    assert source["modules_match_commit"]
    path = tmp_path / "src/agent_harness/assertions.py"
    path.write_text("# native altered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the selected commit"):
        owasp.target_provenance(tmp_path, TARGET)


@pytest.mark.parametrize("format_name", ["text", "json"])
@pytest.mark.usefixtures("native")
def test_check_cli_returns_a_blocking_exit_and_readable_evidence(
    tmp_path: Path, capsys, format_name: str
) -> None:
    assert (
        cli.main(
            [
                "check",
                "owasp",
                "--checkout",
                str(tmp_path),
                "--expected-commit",
                TARGET,
                "--contract",
                gate.CONTRACT,
                "--output-dir",
                str(tmp_path / "out"),
                "--format",
                format_name,
            ]
        )
        == 0
    )
    stdout = capsys.readouterr().out
    if format_name == "json":
        assert json.loads(stdout)["status"] == "passed"
    else:
        assert "PASSED: single-use-approval-v1" in stdout


def test_check_rejects_environment_before_running_native_code(tmp_path: Path, capsys) -> None:
    assert (
        cli.main(
            [
                "check",
                "owasp",
                "--checkout",
                str(tmp_path),
                "--expected-commit",
                "main",
                "--contract",
                gate.CONTRACT,
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "INVALID_ENVIRONMENT"
    with pytest.raises(ValueError, match="supported contract"):
        gate.check(tmp_path, tmp_path / "out", TARGET, contract="unknown")
    with pytest.raises(ValueError, match="timeout"):
        gate.check(tmp_path, tmp_path / "out", TARGET, contract=gate.CONTRACT, timeout=0)


def test_zero_controls_cannot_pass_a_policy_gate() -> None:
    result = gate.assess({"results": [], "complete": True}, [])
    assert result["status"] == "error"
    assert result["exit_code"] == 2


@pytest.mark.parametrize("payload", [None, [], 0, {"observations": None}])
@pytest.mark.usefixtures("native")
def test_wrong_worker_json_shape_is_an_error_report(monkeypatch, tmp_path: Path, payload) -> None:
    monkeypatch.setattr(
        owasp,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(0, json.dumps(payload), "", timed_out=False),
    )
    report = run_gate(tmp_path)
    assert report["gate"]["exit_code"] == 2
    assert not report["complete"]
    assert report["summary"]["native_observed_controls"] == 0

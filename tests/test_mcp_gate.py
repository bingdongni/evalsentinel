import json
from copy import deepcopy
from pathlib import Path

import pytest

from evalsentinel import cli
from evalsentinel import mcp_gate as m
from evalsentinel.process import ProcessResult

IDS = [
    "sep-2549-tools-list-caching-hints",
    "sep-2549-prompts-list-caching-hints",
    "sep-2549-resources-list-caching-hints",
    "sep-2549-resources-templates-list-caching-hints",
    "sep-2549-resources-read-caching-hints",
    "sep-2549-ttl-non-negative",
    "sep-2549-cache-scope-valid",
]


def wire(status="SUCCESS") -> dict:
    return {"id": "wire-schema-valid", "status": status, "details": {"messagesValidated": 10}}


def checks() -> list[dict]:
    return [{"id": name, "status": "SUCCESS"} for name in IDS] + [wire()]


def discovery(caps=None) -> dict:
    return {
        "supportedVersions": ["2026-07-28"],
        "capabilities": caps if caps is not None else {"tools": {}, "prompts": {}, "resources": {}},
    }


def tools_only() -> list[dict]:
    raw = checks()
    for item in raw[1:4]:
        item.update(
            status="FAILURE", details={"error": {"code": -32601, "message": "Method not found"}}
        )
    raw[4].update(status="SKIPPED", errorMessage="No resource to read")
    return raw


def test_production_scope_preserves_original_failures_and_excludes_wire() -> None:
    raw = tools_only()
    saved = deepcopy(raw)
    result = m.assess(raw, contract=m.PRODUCTION, discovery=discovery({"tools": {}}))
    assert raw == saved
    assert result["gate"]["exit_code"] == 0
    assert result["coverage"] == {
        "semantic_checks": 7,
        "in_scope": 3,
        "passed": 3,
        "failed": 0,
        "not_run": 0,
        "not_applicable": 4,
        "wire_checks_excluded_from_semantic_denominator": 1,
    }
    assert result["native_status_counts"] == {"SUCCESS": 4, "FAILURE": 3, "SKIPPED": 1}
    strict = m.assess(raw, contract=m.SDK, discovery=discovery({"tools": {}}))
    assert strict["gate"]["exit_code"] == 1
    assert len(strict["gate"]["violations"]) == 3


@pytest.mark.parametrize("contract", [m.PRODUCTION, m.SDK])
def test_full_capability_positive_and_declared_broken_negative(contract: str) -> None:
    raw = checks()
    assert m.assess(raw, contract=contract, discovery=discovery())["gate"]["exit_code"] == 0
    raw[1].update(status="FAILURE", details={"error": {"code": -32601}})
    result = m.assess(raw, contract=contract, discovery=discovery())
    assert result["gate"]["exit_code"] == 1
    assert result["gate"]["violations"] == [IDS[1]]


def test_no_capabilities_does_not_earn_a_pass_from_wire() -> None:
    raw = tools_only()
    raw[0].update(status="FAILURE", details={"error": {"code": -32601}})
    raw[5]["status"] = raw[6]["status"] = "FAILURE"
    result = m.assess(raw, contract=m.PRODUCTION, discovery=discovery({}))
    assert result["gate"]["status"] == "inconclusive"
    assert result["gate"]["exit_code"] == 2
    assert result["coverage"]["in_scope"] == 0
    assert result["coverage"]["passed"] == 0
    assert result["coverage"]["not_applicable"] == 7


def test_empty_resources_preserves_read_not_run_and_strict_policy_blocks() -> None:
    raw = checks()
    raw[4]["status"] = "SKIPPED"
    production = m.assess(raw, contract=m.PRODUCTION, discovery=discovery())
    strict = m.assess(raw, contract=m.SDK, discovery=discovery())
    assert production["gate"]["exit_code"] == 0
    assert production["coverage"]["passed"] == 6
    assert production["coverage"]["not_run"] == 1
    assert strict["gate"]["exit_code"] == 2
    assert strict["gate"]["unexercised_required_checks"] == [IDS[4]]


@pytest.mark.parametrize("status", ["SKIPPED", "INFO"])
def test_all_unexercised_artifacts_are_inconclusive(status: str) -> None:
    raw = [{"id": "required", "status": status}, wire()]
    result = m.assess(raw, contract=m.COVERAGE, required=["required"])
    assert result["gate"]["status"] == "inconclusive"
    assert result["coverage"]["passed"] == 0
    assert result["coverage"]["not_run"] == 1


@pytest.mark.parametrize("status", ["SUCCESS", "FAILURE"])
def test_untestable_native_checks_are_not_semantic_catches(status: str) -> None:
    raw = [{"id": "required", "status": status, "details": {"untestable": True}}, wire()]
    result = m.assess(raw, contract=m.COVERAGE, required=["required"])
    assert result["gate"]["exit_code"] == 2
    assert result["coverage"]["passed"] == result["coverage"]["failed"] == 0


@pytest.mark.parametrize("status", ["FAILURE", "WARNING"])
def test_failures_and_warnings_block_even_when_not_named_required(status: str) -> None:
    raw = [{"id": "required", "status": "SUCCESS"}, {"id": "other", "status": status}, wire()]
    result = m.assess(raw, contract=m.COVERAGE, required=["required"])
    assert result["gate"]["exit_code"] == 1
    assert result["gate"]["violations"] == ["other"]


def test_wire_only_and_unrelated_success_cannot_satisfy_a_required_check() -> None:
    for raw in ([wire()], [{"id": "other", "status": "SUCCESS"}, wire()]):
        result = m.assess(raw, contract=m.COVERAGE, required=["required"])
        assert result["gate"]["exit_code"] == 2
        assert result["gate"]["missing_required_checks"] == ["required"]


@pytest.mark.parametrize("required", [[], ["wire-schema-valid"], ["a", "a"]])
def test_artifact_gate_requires_explicit_unique_semantic_ids(required: list[str]) -> None:
    with pytest.raises(ValueError, match="semantic"):
        m.assess(checks(), contract=m.COVERAGE, required=required)


@pytest.mark.parametrize(
    "fault",
    [
        "empty",
        "object",
        "duplicate",
        "status",
        "details",
        "wire-absent",
        "wire-skip",
        "wire-empty",
        "harness",
        "new-check",
        "missing-check",
    ],
)
def test_malformed_or_changed_native_contract_never_passes(fault: str) -> None:  # noqa: C901
    raw = checks()
    if fault == "empty":
        raw = []
    elif fault == "object":
        raw[0] = None
    elif fault == "duplicate":
        raw.append(deepcopy(raw[0]))
    elif fault == "status":
        raw[0]["status"] = ["SUCCESS"]
    elif fault == "details":
        raw[0]["details"] = []
    elif fault == "wire-absent":
        raw.pop()
    elif fault == "wire-skip":
        raw[-1]["status"] = "SKIPPED"
    elif fault == "wire-empty":
        raw[-1]["details"]["messagesValidated"] = True
    elif fault == "harness":
        raw.append({"id": "wire-schema-harness-error", "status": "FAILURE"})
    elif fault == "new-check":
        raw.append({"id": "new", "status": "SUCCESS"})
    else:
        raw.pop(0)
    with pytest.raises((ValueError, TypeError)):
        m.assess(raw, contract=m.PRODUCTION, discovery=discovery())


def test_wire_failure_blocks_even_with_no_declared_capability() -> None:
    raw = tools_only()
    raw[-1]["status"] = "FAILURE"
    assert (
        m.assess(raw, contract=m.PRODUCTION, discovery=discovery({"tools": {}}))["gate"][
            "exit_code"
        ]
        == 1
    )


def test_transport_error_on_undeclared_capability_is_not_a_valid_exclusion() -> None:
    raw = tools_only()
    raw[1].pop("details")
    with pytest.raises(ValueError, match="method-not-found"):
        m.assess(raw, contract=m.PRODUCTION, discovery=discovery({"tools": {}}))


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"supportedVersions": []},
        discovery({"tools": None}),
        {"supportedVersions": "2026-07-28", "capabilities": {}},
    ],
)
def test_capability_absence_requires_valid_positive_discovery(payload) -> None:
    with pytest.raises((ValueError, TypeError)):
        m.assess(checks(), contract=m.PRODUCTION, discovery=payload)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/mcp",
        "file:///tmp/mcp",
        "http://127.0.0.1:bad",
        "http://127.0.0.1:99999",
        "http://user:password@127.0.0.1/mcp",
        "http://127.0.0.1/mcp#fragment",
    ],
)
def test_nonlocal_or_ambiguous_target_rejected_before_source_or_network(
    url: str, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match=r"loopback|port|Port"):
        m.check(tmp_path, tmp_path / "out", "a" * 40, url=url, contract=m.PRODUCTION)


@pytest.mark.parametrize(("status", "code"), [("SUCCESS", 0), ("WARNING", 1), ("SKIPPED", 2)])
def test_artifact_cli_real_exit_and_original_bytes(
    tmp_path: Path, capsys, status: str, code: int
) -> None:
    path, output = tmp_path / "input.json", tmp_path / "out"
    payload = json.dumps([{"id": "required", "status": status}, wire()], indent=4).encode()
    path.write_bytes(payload)
    assert (
        cli.main(
            [
                "check",
                "mcp-report",
                "--checks-file",
                str(path),
                "--contract",
                m.COVERAGE,
                "--require-check",
                "required",
                "--output-dir",
                str(output),
                "--format",
                "json",
            ]
        )
        == code
    )
    assert json.loads(capsys.readouterr().out)["exit_code"] == code
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert (output / "checks.json").read_bytes() == payload
    assert report["source"]["execution_origin_verified"] is False
    assert report["passed"] == (code == 0)


@pytest.mark.parametrize("payload", [b"not json", b"{}", b"[]"])
def test_artifact_errors_have_a_persisted_exit_two(payload: bytes, tmp_path: Path) -> None:
    path = tmp_path / "input.json"
    path.write_bytes(payload)
    report = m.check_report(path, tmp_path / "out", required=["required"])
    assert report["gate"]["status"] == "error"
    assert report["gate"]["exit_code"] == 2
    assert report["passed"] is False


@pytest.fixture
def native(monkeypatch, tmp_path: Path) -> dict:
    state = {
        "checks": checks(),
        "exit": 0,
        "changed_source": False,
        "changed_discovery": False,
        "discovery_error": False,
    }
    calls = {"source": 0, "discover": 0}

    def source(*_args: object) -> dict:
        calls["source"] += 1
        return {
            "commit": "a" * 40,
            "node": "node",
            "artifact_sha256": {
                "source": "changed"
                if state["changed_source"] and calls["source"] > 1
                else "original"
            },
        }

    def discover(*_args: object) -> dict:
        calls["discover"] += 1
        if state["discovery_error"]:
            raise ValueError("Discovery wire validation failed")
        caps = {"tools": {}} if state["changed_discovery"] and calls["discover"] > 1 else None
        return {"discovery": discovery(caps), "checks": [wire()]}

    def run(*_args: object) -> ProcessResult:
        path = tmp_path / "out/native/server-caching-fixture"
        path.mkdir(parents=True)
        (path / "checks.json").write_text(json.dumps(state["checks"]), encoding="utf-8")
        return ProcessResult(state["exit"], "original stdout", "", timed_out=False)

    monkeypatch.setattr(m, "target_provenance", source)
    monkeypatch.setattr(m, "_discover", discover)
    monkeypatch.setattr(m, "_run", run)
    return state


def test_native_orchestration_keeps_verdicts_and_verified_source(native, tmp_path: Path) -> None:
    result = m.check(
        tmp_path, tmp_path / "out", "a" * 40, url="http://127.0.0.1/mcp", contract=m.PRODUCTION
    )
    assert result["gate"]["exit_code"] == 0
    assert result["native_checks"] == native["checks"]
    assert result["native_execution"]["exit_code"] == 0
    assert result["source"]["verified_after_run"]
    assert "wire excluded" in m.console_summary(result, tmp_path / "out")


@pytest.mark.parametrize(
    "fault",
    ["changed_source", "changed_discovery", "discovery_error", "crash", "exit_mismatch", "missing"],
)
def test_native_execution_evidence_faults_are_errors(native, fault: str, tmp_path: Path) -> None:
    if fault in native:
        native[fault] = True
    elif fault == "crash":
        native["exit"] = 7
    elif fault == "exit_mismatch":
        native["exit"] = 1
    else:
        native["checks"].pop(0)
    result = m.check(
        tmp_path, tmp_path / "out", "a" * 40, url="http://127.0.0.1/mcp", contract=m.PRODUCTION
    )
    assert result["gate"]["status"] == "error"
    assert result["gate"]["exit_code"] == 2
    assert not result["passed"]


def test_native_timeout_cannot_be_a_semantic_rejection(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        m,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(-1, "partial", "timeout", timed_out=True),
    )
    with pytest.raises(ValueError, match="timed out"):
        m._run(["node"], tmp_path, tmp_path / "native", 1)
    assert (tmp_path / "native.stdout.txt").read_text(encoding="utf-8") == "partial"


def test_ci_console_identifies_failed_missing_and_unexercised_checks(tmp_path: Path) -> None:
    report = {
        "contract": {"id": m.COVERAGE},
        "gate": {
            "status": "violated",
            "violations": ["broken"],
            "missing_required_checks": ["missing"],
            "unexercised_required_checks": ["skipped"],
            "diagnostics": [],
        },
    }
    console = m.console_summary(report, tmp_path)
    assert "blocking: broken" in console
    assert "missing: missing" in console
    assert "not_run: skipped" in console


@pytest.mark.parametrize(
    "arguments",
    [
        ["mcp", "--contract", m.PRODUCTION],
        ["mcp", "--contract", m.PRODUCTION, "--checkout", ".", "--expected-commit", "a" * 40],
        ["mcp-report", "--contract", m.COVERAGE],
        ["owasp", "--contract", m.PRODUCTION],
    ],
)
def test_invalid_cli_combinations_fail_before_native_execution(
    arguments: list[str], capsys
) -> None:
    assert cli.main(["check", *arguments]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "INVALID_ENVIRONMENT"

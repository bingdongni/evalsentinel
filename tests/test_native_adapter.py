import json
import os
import sys
from pathlib import Path
from typing import Self

import pytest

from evalsentinel import mcp
from evalsentinel import process as process_module
from evalsentinel.catalog import CONTROLS, MCP_PIN
from evalsentinel.process import ProcessResult, run_process


@pytest.mark.parametrize(
    ("mode", "classification"),
    [
        ("valid", "correct_accept"),
        ("timeout", "error"),
        ("missing", "insufficient_evidence"),
        ("duplicate-files", "insufficient_evidence"),
        ("malformed-json", "error"),
        ("spawn-error", "error"),
    ],
)
def test_native_artifact_handling(
    mode: str, classification: str, monkeypatch, tmp_path: Path, native_checks
) -> None:
    def run(command: list[str], **_kwargs: object) -> ProcessResult:
        if mode == "spawn-error":
            raise OSError("fixture process could not start")
        if mode not in {"timeout", "missing"}:
            output = Path(command[command.index("-o") + 1])
            native = output / "client-pagination-fixture"
            native.mkdir(parents=True)
            (native / "checks.json").write_text(
                "invalid JSON" if mode == "malformed-json" else json.dumps(native_checks()),
                encoding="utf-8",
            )
            if mode == "duplicate-files":
                other = output / "client-pagination-other"
                other.mkdir()
                (other / "checks.json").write_text("[]", encoding="utf-8")
        return ProcessResult(0, "native stdout", "native stderr", timed_out=mode == "timeout")

    monkeypatch.setattr(mcp, "run_process", run)
    result = mcp._run_control(
        tmp_path, tmp_path, CONTROLS[0], "2025-11-25", node="node", timeout=25
    )
    assert result["classification"] == classification
    assert result["expectation_met"] == (mode == "valid")
    assert result["native_started"] == (mode != "spawn-error")


@pytest.mark.parametrize(
    ("head", "dirty", "missing_artifact"),
    [
        (MCP_PIN, False, False),
        ("wrong-pin", False, False),
        (MCP_PIN, True, False),
        (MCP_PIN, False, True),
    ],
)
def test_native_pin_and_artifact_preconditions(
    head: str, dirty: bool, missing_artifact: bool, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mcp.shutil, "which", lambda tool: tool)

    def run(command: list[str], **_kwargs: object) -> ProcessResult:
        value = head if command[-1] == "HEAD" else "M src/changed.ts" if dirty else ""
        if command[-1] == "--version":
            value = "v22.14.0"
        return ProcessResult(0, value, "", timed_out=False)

    monkeypatch.setattr(mcp, "run_process", run)
    if not missing_artifact:
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist/index.js").write_text("fixture bundle", encoding="utf-8")
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    if head != MCP_PIN or dirty or missing_artifact:
        with pytest.raises(ValueError, match=r"Expected native|tracked changes|Missing"):
            mcp.provenance(tmp_path)
    else:
        result = mcp.provenance(tmp_path)
        assert result["commit"] == MCP_PIN
        assert len(result["artifact_sha256"]["dist/index.js"]) == 64


def test_missing_tool_and_failed_provenance_do_not_execute_controls(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mcp.shutil, "which", lambda _tool: None)
    with pytest.raises(ValueError, match="Git and Node"):
        mcp.provenance(tmp_path)
    monkeypatch.setattr(mcp.shutil, "which", lambda tool: tool)
    monkeypatch.setattr(
        mcp, "run_process", lambda *_args, **_kwargs: ProcessResult(1, "", "", timed_out=False)
    )
    with pytest.raises(ValueError, match="Git checkout"):
        mcp.provenance(tmp_path)


@pytest.mark.parametrize(
    ("versions", "timeout"),
    [([], 25), (["latest"], 25), (["2025-11-25"] * 2, 25), (["2025-11-25"], 1)],
)
def test_invalid_plan_is_rejected(versions: list[str], timeout: float, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"supported spec versions|timeout"):
        mcp.audit(tmp_path, tmp_path / "new", versions, timeout=timeout)


def test_fresh_output_and_partial_reports_are_required(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp, "provenance", lambda _: {"node": "node"})
    with pytest.raises(FileExistsError):
        mcp.audit(tmp_path, tmp_path, ["2025-11-25"])
    calls = 0

    def control(*_args: object, **_kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return {
            "control": "good",
            "classification": "correct_accept",
            "native_started": True,
            "expectation_met": True,
        }

    monkeypatch.setattr(mcp, "_run_control", control)
    output = tmp_path / "partial"
    with pytest.raises(KeyboardInterrupt):
        mcp.audit(tmp_path, output, ["2025-11-25"])
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert not report["complete"]
    assert not report["expectations_met"]
    assert not report["summary"]["expectations_met"]
    assert report["declared_rows"] == 8


def test_native_audit_writes_a_complete_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mcp, "provenance", lambda _: {"node": "node"})
    monkeypatch.setattr(
        mcp,
        "_run_control",
        lambda _checkout, _output, control, *_args, **_kwargs: {
            "control": control.id,
            "classification": "not_run" if control.polarity == "not_run" else "correct_accept",
            "native_started": True,
            "expectation_met": True,
        },
    )
    report = mcp.audit(tmp_path, tmp_path / "complete", ["2025-11-25"])
    assert report["complete"]
    assert report["expectations_met"]


def test_process_output_and_timeout_cleanup(tmp_path: Path) -> None:
    result = run_process(
        [sys.executable, "-c", "print('local fixture')"],
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=5,
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "local fixture"
    assert not result.timed_out
    timed = run_process(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        env=dict(os.environ),
        timeout=0.1,
    )
    assert timed.timed_out
    assert timed.exit_code != 0


def test_user_interruption_stops_the_started_process_tree(monkeypatch, tmp_path: Path) -> None:
    class InterruptedProcess:
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def communicate(self, **_kwargs: object) -> tuple[str, str]:
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return "", ""

    started = InterruptedProcess()
    stopped = []
    monkeypatch.setattr(process_module.subprocess, "Popen", lambda *_args, **_kwargs: started)
    monkeypatch.setattr(process_module, "_stop_tree", stopped.append)
    with pytest.raises(KeyboardInterrupt):
        run_process(["fixture"], cwd=tmp_path, env={}, timeout=5)
    assert stopped == [started]
    assert started.calls == 2

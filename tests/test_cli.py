import json
from pathlib import Path

import pytest

from evalsentinel import __version__, cli


def test_cases_lists_the_declared_controls(capsys) -> None:
    assert cli.main(["cases"]) == 0
    cases = json.loads(capsys.readouterr().out)
    assert len(cases) == 30
    assert {case["polarity"] for case in cases} == {
        "good",
        "bad",
        "not_run",
        "unsupported",
        "invalid",
    }
    assert len({case["id"] for case in cases}) == 30
    assert len(cli.inventory("mcp")) == 8
    assert len(cli.inventory("owasp")) == 22


def test_version(capsys) -> None:
    with pytest.raises(SystemExit) as result:
        cli.main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


@pytest.mark.parametrize(("met", "code"), [(True, 0), (False, 1)])
def test_audit_exit_reflects_control_expectations(
    met: bool, code: int, monkeypatch, tmp_path: Path, capsys
) -> None:
    def audit(*_args: object, **_kwargs: object) -> dict:
        return {"complete": True, "summary": {"expectations_met": met}, "expectations_met": met}

    monkeypatch.setattr(cli, "audit", audit)
    output = tmp_path / "report"
    assert (
        cli.main(["audit", "mcp", "--checkout", str(tmp_path), "--output-dir", str(output)]) == code
    )
    assert json.loads(capsys.readouterr().out)["report"] == str(output / "report.json")


def test_invalid_environment_has_a_structured_error(monkeypatch, tmp_path: Path, capsys) -> None:
    def audit(*_args: object, **_kwargs: object) -> dict:
        raise ValueError("Native pin mismatch")

    monkeypatch.setattr(cli, "audit", audit)
    assert cli.main(["audit", "mcp", "--checkout", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "INVALID_ENVIRONMENT"


def test_unsupported_version_is_rejected_before_any_execution() -> None:
    with pytest.raises(SystemExit) as result:
        cli.main(["audit", "mcp", "--checkout", ".", "--spec-version", "latest"])
    assert result.value.code == 2

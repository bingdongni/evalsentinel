import json
from copy import deepcopy
from pathlib import Path

import pytest

from evalsentinel import cli
from evalsentinel import mcp_service as service
from evalsentinel.process import ProcessResult
from tests.test_mcp_gate import discovery, wire


def page(names: list[str], *, cursor: str | None = None, params=None) -> dict:
    result = {"resultType": "complete", "tools": [{"name": name} for name in names]}
    if cursor is not None:
        result["nextCursor"] = cursor
    return {"params": params or {}, "result": result}


def evidence(pages=None) -> dict:
    return {
        "discovery": discovery({"tools": {}}),
        "pages": pages if pages is not None else [page(["execute_sql"])],
        "complete": True,
        "error": None,
        "checks": [wire()],
    }


def test_required_inventory_accepts_extra_tools_and_preserves_evidence() -> None:
    raw = evidence([page(["extra", "execute_sql"])])
    saved = deepcopy(raw)
    result = service.assess_inventory(raw, ["execute_sql"])
    assert result["exit_code"] == 0
    assert result["inventory"]["observed"] == ["execute_sql", "extra"]
    assert raw == saved


def test_complete_empty_catalog_is_a_service_requirement_violation_not_a_protocol_bug() -> None:
    result = service.assess_inventory(evidence([page([])]), ["execute_sql"])
    assert result["exit_code"] == 1
    assert result["violations"] == ["required-tool:execute_sql"]
    assert result["inventory"]["complete"]


@pytest.mark.parametrize("cursor", ["", "opaque; token/with spaces"])
def test_empty_page_and_opaque_cursor_do_not_hide_later_required_tools(cursor: str) -> None:
    raw = evidence([page([], cursor=cursor), page(["execute_sql"], params={"cursor": cursor})])
    result = service.assess_inventory(raw, ["execute_sql"])
    assert result["exit_code"] == 0
    assert result["inventory"]["pages"] == 2


@pytest.mark.parametrize(
    "pages",
    [
        [page(["execute_sql", "execute_sql"])],
        [page(["execute_sql"], cursor="a"), page(["execute_sql"], params={"cursor": "a"})],
    ],
)
def test_duplicate_names_block_under_the_explicit_service_contract(pages: list[dict]) -> None:
    result = service.assess_inventory(evidence(pages), ["execute_sql"])
    assert result["exit_code"] == 1
    assert result["violations"] == ["duplicate-tool:execute_sql"]


@pytest.mark.parametrize(
    "fault",
    [
        "no-pages",
        "too-many",
        "incomplete",
        "error",
        "rewrite",
        "unconsumed",
        "repeat",
        "extra-page",
        "invalid-cursor",
        "invalid-result",
        "no-tool-name",
        "no-tools",
        "no-capability",
    ],
)
def test_missing_or_inconsistent_execution_is_not_a_missing_tool_catch(fault: str) -> None:  # noqa: C901, PLR0912
    raw = evidence()
    if fault == "no-pages":
        raw["pages"] = []
    elif fault == "too-many":
        raw["pages"] *= 33
    elif fault == "incomplete":
        raw["complete"] = False
    elif fault == "error":
        raw["error"] = {"message": "partial traversal"}
    elif fault == "rewrite":
        raw["pages"][0]["params"] = {"cursor": "invented"}
    elif fault == "unconsumed":
        raw["pages"][0]["result"]["nextCursor"] = ""
    elif fault == "repeat":
        raw["pages"] = [
            page([], cursor="a"),
            page([], cursor="a", params={"cursor": "a"}),
            page(["execute_sql"], params={"cursor": "a"}),
        ]
    elif fault == "extra-page":
        raw["pages"].append(page(["other"]))
    elif fault == "invalid-cursor":
        raw["pages"][0]["result"]["nextCursor"] = 2
    elif fault == "invalid-result":
        raw["pages"][0]["result"] = None
    elif fault == "no-tool-name":
        raw["pages"][0]["result"]["tools"] = [{}]
    elif fault == "no-tools":
        raw["pages"][0]["result"]["tools"] = None
    else:
        raw["discovery"]["capabilities"] = {}
    with pytest.raises((ValueError, TypeError)):
        service.assess_inventory(raw, ["execute_sql"])


def test_wire_failure_is_preserved_without_asserting_tool_absence() -> None:
    raw = evidence()
    raw["checks"][0]["status"] = "FAILURE"
    result = service.assess_inventory(raw, ["execute_sql"])
    assert result["exit_code"] == 1
    assert result["violations"] == ["wire-schema-valid"]
    assert "inventory" not in result


def test_last_permitted_page_can_complete_without_an_off_by_one_rejection() -> None:
    pages = [
        page([], cursor=str(index), params={"cursor": str(index - 1)} if index else {})
        for index in range(31)
    ]
    pages.append(page(["execute_sql"], params={"cursor": "30"}))
    result = service.assess_inventory(evidence(pages), ["execute_sql"])
    assert result["exit_code"] == 0
    assert result["inventory"]["pages"] == 32


@pytest.mark.parametrize("required", [[], [""], ["   "], ["a", "a"]])
def test_service_contract_requires_explicit_unique_names(required: list[str]) -> None:
    with pytest.raises(ValueError, match=r"require-tool|Duplicate"):
        service.assess_inventory(evidence(), required)


@pytest.fixture
def native(monkeypatch) -> dict:
    state = {"payload": evidence(), "caching_code": 0, "source_changed": False, "interrupt": False}
    calls = {"source": 0}

    def source(*_args: object) -> dict:
        calls["source"] += 1
        return {
            "commit": "a" * 40,
            "node": "node",
            "artifact_sha256": {
                "x": "changed" if state["source_changed"] and calls["source"] > 1 else "original"
            },
        }

    def caching(*_args: object, **_kwargs: object) -> dict:
        code = state["caching_code"]
        return {
            "gate": {
                "status": "passed" if code == 0 else "violated",
                "exit_code": code,
                "violations": ["native-failure"] if code else [],
                "diagnostics": [],
            },
            "discovery": {"after": {"discovery": discovery({"tools": {}})}},
        }

    def observe(*_args: object) -> dict:
        if state["interrupt"]:
            raise KeyboardInterrupt
        return state["payload"]

    monkeypatch.setattr(service.mcp, "target_provenance", source)
    monkeypatch.setattr(service.mcp, "check", caching)
    monkeypatch.setattr(service, "_observe", observe)
    return state


def run(tmp_path: Path) -> dict:
    return service.check(
        tmp_path, tmp_path / "out", "a" * 40, url="http://127.0.0.1/mcp", required=["execute_sql"]
    )


@pytest.mark.usefixtures("native")
def test_service_gate_keeps_native_cache_scope_and_inventory_distinct(tmp_path: Path) -> None:
    report = run(tmp_path)
    assert report["passed"]
    assert report["contract"]["id"] == "service-tools-v1"
    assert report["inventory"]["complete"]
    assert report["source"]["verified_after_run"]
    assert "Inventory:" in service.console_summary(report, tmp_path)


@pytest.mark.parametrize(
    ("fault", "code"),
    [("missing", 1), ("cache", 1), ("partial", 2), ("source", 2), ("capabilities", 2)],
)
def test_service_gate_blocks_semantic_and_operational_faults_distinctly(
    native, tmp_path: Path, fault: str, code: int
) -> None:
    if fault == "missing":
        native["payload"] = evidence([page([])])
    elif fault == "cache":
        native["caching_code"] = 1
    elif fault == "partial":
        native["payload"]["complete"] = False
    elif fault == "source":
        native["source_changed"] = True
    else:
        native["payload"]["discovery"]["capabilities"]["tools"]["listChanged"] = True
    report = run(tmp_path)
    assert report["gate"]["exit_code"] == code
    assert not report["passed"]
    assert report["source"]["verified_after_run"] == (fault != "source")


def test_interruption_leaves_root_service_report_nonpassing(native, tmp_path: Path) -> None:
    native["interrupt"] = True
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path)
    report = json.loads((tmp_path / "out/report.json").read_text(encoding="utf-8"))
    assert report["gate"]["exit_code"] == 2
    assert not report["passed"]
    assert report["contract"]["id"] == "service-tools-v1"


def test_inventory_process_timeout_preserves_logs_and_is_not_a_semantic_catch(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        service,
        "run_process",
        lambda *_args, **_kwargs: ProcessResult(-1, "partial", "timeout", timed_out=True),
    )
    with pytest.raises(ValueError, match="timed out"):
        service._observe(tmp_path, tmp_path, {"node": "node"}, "http://127.0.0.1/mcp", 1)
    assert (tmp_path / "inventory.stdout.txt").read_text(encoding="utf-8") == "partial"


@pytest.mark.parametrize(
    "args",
    [
        [
            "mcp",
            "--contract",
            "service-tools-v1",
            "--checkout",
            ".",
            "--expected-commit",
            "a" * 40,
            "--url",
            "http://127.0.0.1/mcp",
        ],
        ["mcp-report", "--contract", "semantic-coverage-v1", "--require-tool", "execute_sql"],
        ["mcp", "--contract", "production-caching-v1", "--require-tool", "execute_sql"],
    ],
)
def test_cli_does_not_silently_ignore_service_requirements(args: list[str], capsys) -> None:
    assert cli.main(["check", *args]) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "INVALID_ENVIRONMENT"

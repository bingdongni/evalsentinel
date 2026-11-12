"""Exercise the real maintainer CLI on isolated committed native regressions."""

import argparse
import ast
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

from evalsentinel import owasp
from evalsentinel.gate import CONTRACT
from evalsentinel.owasp_catalog import corpus
from evalsentinel.process import run_process

ROOT = Path(__file__).resolve().parents[1]
BAD_CONTROLS = 11
GOOD_CONTROLS = 7
CRASH_HOOK = (
    '    if trace.tool_calls:\n        raise RuntimeError("EvalSentinel controlled native crash")\n'
)
HOOK = (
    "    if trace.tool_calls and False:\n"
    '        return AssertionResult(id="approval_required", result="pass", '
    'evidence="EvalSentinel controlled fault")\n'
)


def git(checkout: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("Git is required for the isolated native experiment")
    result = subprocess.run(
        [
            executable,
            "-c",
            f"safe.directory={checkout.as_posix()}",
            "-C",
            str(checkout),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise RuntimeError(f"Isolated native Git operation failed: {result.stderr.strip()}")
    return result.stdout.strip()


def commit(checkout: Path, message: str) -> str:
    git(checkout, "add", "--renormalize", "src/agent_harness/assertions.py")
    git(
        checkout,
        "-c",
        "user.name=EvalSentinel Controls",
        "-c",
        "user.email=controls@example.invalid",
        "commit",
        "-m",
        message,
    )
    return git(checkout, "rev-parse", "HEAD")


def prepare_healthy(source: Path, output: Path) -> tuple[Path, str]:
    native = output / "healthy-source"
    git_dir = Path(git(source, "rev-parse", "--absolute-git-dir"))
    git(
        source,
        "-c",
        f"safe.directory={git_dir.as_posix()}",
        "clone",
        "--no-hardlinks",
        "--config",
        "core.autocrlf=false",
        str(source),
        str(native),
    )
    path = native / "src/agent_harness/assertions.py"
    text = path.read_text(encoding="utf-8")
    function = next(
        node
        for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef) and node.name == "evaluate_approval_required"
    )
    first = function.body[0]
    has_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    position = first.end_lineno if has_docstring else first.lineno - 1
    if position is None:
        raise RuntimeError("Could not locate the native approval function body")
    lines = text.splitlines(keepends=True)
    path.write_text(
        "".join(lines[:position]) + HOOK + "".join(lines[position:]), encoding="utf-8", newline="\n"
    )
    return native, commit(native, "control: unchanged approval semantics at a new commit")


def variant(healthy: Path, output: Path, name: str, pin: str) -> Path:
    target = output / f"{name}-source"
    git(healthy, "worktree", "add", "--detach", str(target), pin)
    if not target.resolve().is_relative_to(output):
        raise RuntimeError("Controlled source must stay inside the experiment directory")
    return target


def execute(target: Path, pin: str, output: Path, name: str, expected: int) -> dict:
    report_dir = output / name
    command = [
        sys.executable,
        "-m",
        "evalsentinel",
        "check",
        "owasp",
        "--checkout",
        str(target),
        "--expected-commit",
        pin,
        "--contract",
        CONTRACT,
        "--output-dir",
        str(report_dir),
    ]
    result = run_process(command, cwd=ROOT, env=dict(os.environ), timeout=60)
    (output / f"{name}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / f"{name}.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.timed_out or result.exit_code != expected:
        raise RuntimeError(f"{name}: expected actual CLI exit {expected}, got {result.exit_code}")
    record = {"commit": pin, "exit_code": result.exit_code, "expected_exit": expected}
    if (report_dir / "report.json").exists():
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        record.update(
            gate=report["gate"],
            classifications=report["summary"]["classifications"],
            report=str(report_dir / "report.json"),
        )
    return record


def overaccept(healthy: Path, pin: str, output: Path) -> tuple[dict, int]:
    target = variant(healthy, output, "overaccept", pin)
    path = target / "src/agent_harness/assertions.py"
    original = path.read_text(encoding="utf-8")
    py_compile.compile(
        str(path), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP
    )
    stamp = path.stat()
    path.write_text(original.replace("and False:", "and True :", 1), encoding="utf-8", newline="\n")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    if path.stat().st_size != stamp.st_size or path.stat().st_mtime_ns != stamp.st_mtime_ns:
        raise RuntimeError("The controlled stale-bytecode preconditions were not established")
    mutant = commit(target, "control: accept every exercised approval input")
    plain_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}
    }
    plain = run_process(
        [sys.executable, "-m", "evalsentinel.owasp_worker", "--checkout", str(target)],
        cwd=ROOT,
        env=plain_env,
        timeout=60,
    )
    if plain.timed_out or plain.exit_code:
        raise RuntimeError("The ordinary-cache comparison worker failed")
    payload = json.loads(plain.stdout)
    (output / "ordinary-stale-worker.json").write_text(plain.stdout, encoding="utf-8")
    bad_ids = {case["id"] for case in corpus()["cases"] if case["polarity"] == "bad"}
    accepts = sum(
        row["control"] in bad_ids and (row.get("native") or {}).get("result") == "pass"
        for row in payload["observations"]
    )
    if accepts != 0:
        raise RuntimeError("The ordinary interpreter did not reproduce the expected stale cache")
    return execute(target, mutant, output, "overaccept", 1), accepts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.checkout.resolve(), args.output_dir.resolve()
    owasp.provenance(source, "candidate")
    output.mkdir(parents=True, exist_ok=False)
    healthy, pin = prepare_healthy(source, output)
    if pin in corpus()["pins"].values():
        raise RuntimeError("The maintainer experiment must use a newly created commit")
    runs = {"healthy": execute(healthy, pin, output, "healthy", 0)}
    runs["overaccept"], stale_accepts = overaccept(healthy, pin, output)
    for name in ("overreject", "crash"):
        target = variant(healthy, output, name, pin)
        path = target / "src/agent_harness/assertions.py"
        replacement = (
            HOOK.replace("and False:", "and True :").replace('result="pass"', 'result="fail"')
            if name == "overreject"
            else CRASH_HOOK
        )
        text = path.read_text(encoding="utf-8")
        if text.count(HOOK) != 1:
            raise RuntimeError("The controlled fault hook was not unique")
        path.write_text(text.replace(HOOK, replacement), encoding="utf-8", newline="\n")
        mutant = commit(target, f"control: {name} exercised native inputs")
        runs[name] = execute(target, mutant, output, name, 1 if name == "overreject" else 2)
    runs["source_mismatch"] = execute(healthy, "0" * 40, output, "source-mismatch", 2)
    dirty = variant(healthy, output, "dirty", pin)
    path = dirty / "src/agent_harness/assertions.py"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# controlled uncommitted change\n",
        encoding="utf-8",
        newline="\n",
    )
    runs["dirty_source"] = execute(dirty, pin, output, "dirty-source", 2)
    runs["healthy_after"] = execute(healthy, pin, output, "healthy-after", 0)
    if runs["overaccept"]["classifications"].get("false_accept") != BAD_CONTROLS:
        raise RuntimeError("The overaccepting native mutation was not exposed")
    if runs["overreject"]["classifications"].get("false_reject") != GOOD_CONTROLS:
        raise RuntimeError("The valid controls did not expose overrejection")
    if runs["crash"]["gate"]["violations"]:
        raise RuntimeError("Native crashes must not be counted as semantic contract catches")
    record = {
        "contract": CONTRACT,
        "base_commit": corpus()["pins"]["candidate"],
        "new_healthy_commit": pin,
        "runs": runs,
        "ordinary_stale_worker_false_accepts": stale_accepts,
        "fresh_source_gate_false_accepts": BAD_CONTROLS,
        "model_api_calls": 0,
        "controlled_mutations_not_upstream_defects": True,
    }
    (output / "verification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verification": str(output / "verification.json"),
                "actual_exit_codes": {name: run["exit_code"] for name, run in runs.items()},
                "stale_cache_reproduced": True,
                "model_api_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

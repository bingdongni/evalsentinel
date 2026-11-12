"""Bound native processes and clean up only the process tree we started."""

import os
import signal
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def _stop_tree(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=10,
            )
        else:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
    finally:
        if process.poll() is None:
            process.kill()


def run_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> ProcessResult:
    with subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name != "nt",
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_tree(process)
            stdout, stderr = process.communicate(timeout=10)
            return ProcessResult(process.returncode, stdout, stderr, timed_out=True)
        except KeyboardInterrupt:
            _stop_tree(process)
            process.communicate(timeout=10)
            raise
        return ProcessResult(process.returncode, stdout, stderr, timed_out=False)

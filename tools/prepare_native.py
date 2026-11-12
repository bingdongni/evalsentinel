"""Download pinned native sources; audits themselves remain offline."""

import argparse
import shutil
import subprocess
from pathlib import Path

from evalsentinel.catalog import MCP_PIN
from evalsentinel.mcp_gate import NATIVE_PIN
from evalsentinel.owasp_catalog import corpus

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"


def git(*arguments: str) -> str:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("Install Git before preparing native sources")
    result = subprocess.run(
        [executable, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def verify(path: Path, pin: str) -> None:
    config = f"safe.directory={path.as_posix()}"
    head = git("-c", config, "-C", str(path), "rev-parse", "HEAD")
    dirty = git("-c", config, "-C", str(path), "status", "--porcelain", "--untracked-files=no")
    if head != pin or dirty:
        raise RuntimeError(f"Existing checkout is not clean at the expected pin: {path}")


def clone(path: Path, url: str, pin: str) -> None:
    if path.exists():
        verify(path, pin)
        return
    git("clone", "--no-checkout", "--config", "core.autocrlf=false", url, str(path))
    git("-c", f"safe.directory={path.as_posix()}", "-C", str(path), "checkout", "--detach", pin)
    verify(path, pin)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter", choices=["all", "owasp", "mcp", "mcp-production"], default="owasp"
    )
    args = parser.parse_args()
    CACHE.mkdir(exist_ok=True)
    if args.adapter in {"all", "mcp"}:
        clone(CACHE / "conformance", "https://github.com/bingdongni/conformance.git", MCP_PIN)
    if args.adapter == "mcp-production":
        clone(
            CACHE / "conformance-production",
            "https://github.com/modelcontextprotocol/conformance.git",
            NATIVE_PIN,
        )
    if args.adapter in {"all", "owasp"}:
        pins = corpus()["pins"]
        base = CACHE / "owasp-harness"
        fixed = CACHE / "owasp-fixed"
        clone(
            base, "https://github.com/OWASP/Agent-Security-Regression-Harness.git", pins["baseline"]
        )
        if not fixed.exists():
            config = f"safe.directory={base.as_posix()}"
            git("-c", config, "-C", str(base), "fetch", "origin", "pull/211/head")
            git(
                "-c",
                config,
                "-C",
                str(base),
                "worktree",
                "add",
                "--detach",
                str(fixed),
                pins["candidate"],
            )
        verify(fixed, pins["candidate"])
    print("Pinned native sources are ready. MCP additionally requires npm ci and npm run build.")


if __name__ == "__main__":
    main()

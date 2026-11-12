"""Start the official DBHub release over a read-only synthetic SQLite database."""

import hashlib
import http.client
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import closing, contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.6.1"
SOURCE_COMMIT = "c4166110eee8d42a717c0e047f80a0592fa79f69"
INTEGRITY = (
    "sha512-QvpejQR82n7Zs2UEO5wb+CrNdrDMAxS+rlnKSqmrdQ0fMwiUqOoKv92Q/"
    "6/Gt+oRIwcW6CBS91fLoJr6Z4cz3A=="
)
MODES = (
    "passthrough",
    "hide-tool",
    "strip-hint",
    "paged-empty-cursor",
    "hide-later-tool",
    "cursor-cycle",
    "duplicate-name",
    "wrong-query-result",
)
PAGED = {"paged-empty-cursor", "hide-later-tool", "cursor-cycle"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance(runtime: Path) -> dict:
    package = runtime / "node_modules/@bytebase/dbhub"
    release = json.loads((package / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((runtime / "package-lock.json").read_text(encoding="utf-8"))
    locked = lock["packages"]["node_modules/@bytebase/dbhub"]
    if (
        release["version"] != VERSION
        or locked["version"] != VERSION
        or locked["integrity"] != INTEGRITY
    ):
        raise ValueError("Prepare the pinned official DBHub release with npm ci")
    sdk = json.loads(
        (runtime / "node_modules/@modelcontextprotocol/server/package.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "package": "@bytebase/dbhub",
        "version": VERSION,
        "npm_integrity": INTEGRITY,
        "source_commit_from_release_metadata": SOURCE_COMMIT,
        "sdk_server_version": sdk["version"],
        "lock_sha256": sha(runtime / "package-lock.json"),
        "dist_sha256": {
            str(p.relative_to(package)).replace("\\", "/"): sha(p)
            for p in sorted((package / "dist").rglob("*.js"))
        },
    }


@contextmanager
def service(runtime: Path, output: Path):  # noqa: ANN201
    node = shutil.which("node")
    if not node:
        raise ValueError("DBHub integration needs Node >=22.5 on PATH")
    output.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(output / "fixture.db") as database:
        database.executescript(
            "CREATE TABLE sentinel_items(id INTEGER PRIMARY KEY,name TEXT); "
            "INSERT INTO sentinel_items VALUES(1,'alpha'),(2,'beta');"
        )
    # Explicit empty environment file wins over dotenv's package-root fallback.
    (output / ".env").write_text("", encoding="utf-8")
    config = output / "dbhub.toml"
    config.write_text(
        '[[sources]]\nid = "fixture"\ntype = "sqlite"\ndatabase = "fixture.db"\n'
        '\n[[tools]]\nname = "execute_sql"\nsource = "fixture"\nreadonly = true\n',
        encoding="utf-8",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    allowed_env = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed_env}
    command = [
        node,
        str(runtime / "node_modules/@bytebase/dbhub/dist/index.js"),
        "--transport",
        "http",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--config",
        str(config),
    ]
    with (
        (output / "stdout.txt").open("w", encoding="utf-8") as stdout,
        (output / "stderr.txt").open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(command, cwd=output, env=env, stdout=stdout, stderr=stderr)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("DBHub exited before readiness; inspect preserved stderr")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("DBHub readiness timed out")
            yield port
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


class Proxy(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, mode: str) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.target = port
        self.mode = mode
        self.wire: list[dict] = []

    def transform(self, request: dict, message: dict) -> dict:
        message = deepcopy(message)
        result = message.get("result")
        if not isinstance(result, dict):
            return message
        if request["method"] == "tools/list":
            self.transform_list(request, result)
        if self.mode == "wrong-query-result" and request["method"] == "tools/call":
            for content in result.get("content", []):
                if content.get("type") == "text":
                    body = json.loads(content["text"])
                    if body.get("success") is True:
                        body["data"]["statements"][0]["rows"] = [{"name": "incorrect"}]
                        content["text"] = json.dumps(body)
        return message

    def transform_list(self, request: dict, result: dict) -> None:
        if self.mode in {"hide-tool", "hide-later-tool"}:
            result["tools"] = [t for t in result["tools"] if t["name"] != "execute_sql"]
        if self.mode == "strip-hint":
            result.pop("ttlMs", None)
        if self.mode in PAGED and "cursor" not in request.get("params", {}):
            result["tools"] = []
            result["nextCursor"] = "cycle" if self.mode == "cursor-cycle" else ""
        elif self.mode == "cursor-cycle":
            result["tools"] = []
            result["nextCursor"] = "cycle"
        if self.mode == "duplicate-name":
            result["tools"] += deepcopy(result["tools"])


class Handler(BaseHTTPRequestHandler):
    server: Proxy

    def log_message(self, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        upstream = deepcopy(request)
        # The proxy owns the virtual pagination; the real one-page service must
        # not receive a cursor it never issued. Keep both request versions.
        if self.server.mode in PAGED and request["method"] == "tools/list":
            upstream.get("params", {}).pop("cursor", None)
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in {"host", "content-length", "connection"}
        }
        with closing(
            http.client.HTTPConnection("127.0.0.1", self.server.target, timeout=15)
        ) as conn:
            conn.request("POST", self.path, json.dumps(upstream).encode(), headers)
            response = conn.getresponse()
            original = json.loads(response.read())
            message = self.server.transform(request, original)
            self.server.wire.append(
                {
                    "request": request,
                    "upstream_request": upstream,
                    "upstream_response": original,
                    "delivered_response": message,
                    "http_status": response.status,
                    "mode": self.server.mode,
                }
            )
            data = json.dumps(message).encode()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


@contextmanager
def proxy(port: int, mode: str):  # noqa: ANN201
    with Proxy(port, mode) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)

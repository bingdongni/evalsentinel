"""Synthetic loopback services for the real upstream MCP runner. No tools execute."""

import argparse
import json
import threading
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

MODES = (
    "tools-only",
    "full",
    "broken-prompts",
    "bad-ttl",
    "no-capabilities",
    "empty-resources",
    "discovery-change",
    "invalid-discovery",
)
SPEC = "2026-07-28"


class Fixture(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, mode: str, port: int = 0) -> None:
        super().__init__(("127.0.0.1", port), Handler)
        self.mode = mode
        self.observations: list[dict] = []
        self.discoveries = 0

    def response(self, request: dict) -> dict:  # noqa: C901, PLR0912
        method, mode = request["method"], self.mode
        caps = {"tools": {}}
        if mode not in {"tools-only", "no-capabilities"}:
            caps.update(prompts={}, resources={})
        if mode == "no-capabilities":
            caps = {}
        common = {
            "resultType": "complete",
            "ttlMs": 0,
            "cacheScope": "public",
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "evalsentinel-fixture",
                    "version": "1",
                }
            },
        }
        result = None
        if method == "server/discover":
            self.discoveries += 1
            if mode == "discovery-change" and self.discoveries > 1:
                caps.pop("prompts")
            result = {**common, "supportedVersions": [SPEC], "capabilities": caps}
            if mode == "invalid-discovery":
                result["capabilities"] = {"tools": None}
        elif method == "tools/list" and "tools" in caps:
            result = {
                **common,
                "tools": [
                    {
                        "name": "echo",
                        "description": "No-op test tool",
                        "inputSchema": {"type": "object"},
                    }
                ],
            }
            if mode == "bad-ttl":
                result["ttlMs"] = -1
        elif method == "prompts/list" and "prompts" in caps and mode != "broken-prompts":
            result = {**common, "prompts": [{"name": "example", "description": "Synthetic prompt"}]}
        elif method == "resources/list" and "resources" in caps:
            result = {
                **common,
                "resources": []
                if mode == "empty-resources"
                else [{"uri": "evalsentinel://fixture", "name": "fixture"}],
            }
        elif method == "resources/templates/list" and "resources" in caps:
            result = {**common, "resourceTemplates": []}
        elif method == "resources/read" and "resources" in caps:
            result = {
                **common,
                "contents": [{"uri": "evalsentinel://fixture", "text": "invented data"}],
            }
        body = {"jsonrpc": "2.0", "id": request["id"]}
        if result is None:
            body["error"] = {"code": -32601, "message": "Method not found"}
        else:
            body["result"] = result
        self.observations.append({"request": request, "response": body})
        return body


class Handler(BaseHTTPRequestHandler):
    server: Fixture
    protocol_version = "HTTP/1.0"
    allowed_methods: ClassVar[set[str]] = {
        "server/discover",
        "tools/list",
        "prompts/list",
        "resources/list",
        "resources/templates/list",
        "resources/read",
    }

    def log_message(self, *_args: object) -> None:
        pass

    def do_POST(self) -> None:
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        data = json.dumps(self.server.response(request)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def running(mode: str):  # noqa: ANN201
    with Fixture(mode) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="full")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    with Fixture(args.mode, args.port) as server:
        if args.ready_file:
            args.ready_file.write_text(
                f"http://127.0.0.1:{server.server_port}/mcp", encoding="utf-8"
            )
        with suppress(KeyboardInterrupt):
            server.serve_forever()


if __name__ == "__main__":
    main()

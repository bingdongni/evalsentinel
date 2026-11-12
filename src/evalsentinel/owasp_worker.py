"""Isolated process importing the actual pinned OWASP implementation."""

import argparse
import hashlib
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

from evalsentinel.owasp_catalog import corpus


def offline_socket_guard(event: str, _arguments: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise RuntimeError("Network operations are disabled in the offline OWASP worker")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args()
    source = (args.checkout / "src").resolve()
    sys.path.insert(0, str(source))
    sys.addaudithook(offline_socket_guard)
    evaluate_approval_required = importlib.import_module(
        "agent_harness.assertions"
    ).evaluate_approval_required
    validate_scenario_data = importlib.import_module(
        "agent_harness.scenario"
    ).validate_scenario_data
    trace_type = importlib.import_module("agent_harness.trace").Trace

    if not Path(inspect.getfile(evaluate_approval_required)).resolve().is_relative_to(source):
        raise RuntimeError("The assertion did not load from the declared native checkout")
    hashes = {}
    for name in ("assertions", "scenario", "trace", "result"):
        module = importlib.import_module(f"agent_harness.{name}")
        path = Path(inspect.getfile(module)).resolve()
        if path != source / "agent_harness" / f"{name}.py":
            raise RuntimeError("A native module did not load from its declared source file")
        hashes[f"src/agent_harness/{name}.py"] = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = []
    for case in corpus()["cases"]:
        stage = "scenario_validation"
        invoked = False
        try:
            assertion = {"type": "approval_required", "action": "transfer_funds"}
            scenario = validate_scenario_data(
                {
                    "id": case["id"],
                    "title": case["rationale"],
                    "category": "approval_bypass",
                    "severity": "high",
                    "target": {"adapter": "http_agent"},
                    "input": {
                        "user_message": "synthetic offline approval control",
                        "context": [{"source": "approval_service", "trust": "trusted"}],
                    },
                    "expected": {},
                    "assertions": [assertion],
                }
            )
            stage = "trace_validation"
            trace = trace_type.from_dict(case["trace"])
            stage = "assertion"
            invoked = True
            native = evaluate_approval_required(scenario, trace, assertion).to_dict()
            observation: dict[str, Any] = {"native": native, "error": None}
        # Native exceptions are observations; KeyboardInterrupt/SystemExit still propagate.
        except Exception as error:  # noqa: BLE001
            observation = {
                "native": None,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "stage": stage,
                },
            }
        rows.append(
            {"control": case["id"], "assertion_invoked": invoked, "stage": stage, **observation}
        )
    print(
        json.dumps(
            {
                "observations": rows,
                "network_policy": "python-sockets-denied",
                "source_sha256": hashes,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

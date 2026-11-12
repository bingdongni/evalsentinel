# EvalSentinel

Offline counterexample tests for stateful agent evaluators.

**Status: first runnable MCP alpha (`0.1.0a1`).** The `evalsentinel` command and
native MCP adapter work. The OWASP package integration and the complete 30-case
v0.1 corpus are not shipped.

EvalSentinel exercises native evaluation code with known-good, known-bad,
and unexercised controls. It preserves the native verdict and
report whether an observed result supports the declared behavior. The initial
focus is pagination, single-use approval binding, and evidence needed to claim
completion of a stateful action.

The first native integration is MCP conformance; the OWASP Agent Security
Regression Harness is next. The core workflow uses a CPU and zero model API
calls. Native dependencies must be installed before offline execution.

## Run the MCP alpha

Use Python 3.12+, uv, Git and Node 22:

```sh
uv sync --locked --group dev
uv run --offline evalsentinel cases
git clone https://github.com/bingdongni/conformance.git .cache/conformance
git -C .cache/conformance checkout --detach c69c46dbef3083ab4e87b06a6b0e066cc487e214
npm ci --prefix .cache/conformance --ignore-scripts --no-audit --no-fund
npm run --prefix .cache/conformance build
uv run --offline evalsentinel audit mcp --checkout .cache/conformance --output-dir runs/example
```

Dependency preparation uses the network. The audit uses local CLI/HTTP with no
model calls, API keys or GPU. Use a new output directory on each invocation;
existing directories are rejected to prevent stale evidence reuse.

Eight controls run at each of two explicit versions, `2025-11-25` and
`2026-07-28`. Select just one with `--spec-version 2025-11-25`. These are eight
controls and sixteen native runs, not sixteen independent bugs.

| Observed classification | Rows |
| --- | ---: |
| Correct acceptance of good controls | 4 |
| Correct rejection of known-bad controls | 10 |
| Deliberately unexercised / not run | 2 |

The inert controls remain `not_run` and are not counted as catches. Exit 0 means
the declared *control expectations* matched; it does not certify all tested
clients as conformant. Exit 1 indicates mismatched expectations; exit 2 means
an invalid environment or invocation. See the [CLI/report contract](docs/cli-contract.md).

Every run saves native checks, stdout/stderr, source pins, built-artifact hashes,
comparison reasons and complete denominators. Build identity is recorded, not
cryptographically attested. Checkouts must be clean at the declared native pin.

## Development

```sh
uv run --offline ruff check src tests tools
uv run --offline ruff format --check src tests tools
uv run --offline ty check src
uv run --offline pytest
uv build
```

CI tests Windows and Linux, then runs the native MCP matrix. It uses read-only
permissions, pinned Actions, no model credentials and standard runners. It does
not publish to PyPI.

## Scope and prior work

See the [project decision](decisions/001-project-selection.md) for the scope,
closest prior work, acceptance criteria, limitations, and initial milestones.
The [machine-readable decision](decisions/project.json) distinguishes measured
results from planned work.

Existing evidence:

- [MCP conformance PR #583](https://github.com/modelcontextprotocol/conformance/pull/583):
  one proposed pagination scenario, 16 CLI controls over two protocol versions,
  and 659 passing upstream tests. The PR is open and not merged.
- [Native OWASP feasibility probe](decisions/probe_owasp_native.py): eight local
  cases against pinned upstream code, reproducing the policy mismatch already
  reported in [issue #210](https://github.com/OWASP/Agent-Security-Regression-Harness/issues/210).
  [PR #211](https://github.com/OWASP/Agent-Security-Regression-Harness/pull/211)
  already proposes the fix; this project does not claim that discovery.

To reproduce the OWASP feasibility probe, use Python 3.12+ with PyYAML installed,
then prepare the pinned native source and run the probe:

```sh
git clone https://github.com/OWASP/Agent-Security-Regression-Harness.git .cache/owasp-harness
git -C .cache/owasp-harness checkout --detach 970158c10b7e36ae00f12de4ba2a41ca61acabca
python decisions/probe_owasp_native.py
```

The clone requires network access. The probe itself uses local imports and
in-memory trace objects; it performs no model calls or real tool actions.

This project builds on prior work including evalmut, MCP conformance, the OWASP
harness, InfernoSIM, and oracle-integrity auditing. Its prospective value is a
maintained set of stateful regression cases and direct native integrations;
this value still needs user validation.

MIT licensed. Native implementations are not bundled and retain their own
licenses. Implementation and verification were prepared with Codex assistance.

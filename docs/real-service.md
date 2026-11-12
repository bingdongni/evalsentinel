# Gate required tools on a real MCP service (v0.4 alpha)

`service-tools-v1` combines the original native caching gate with a caller-selected
tool inventory requirement. It fixes a practical coverage gap: valid caching
hints do not show that your deployed service still exposes its required tools.
The command reads discovery/tool lists and follows pagination. It never calls tools.

```sh
evalsentinel check mcp --checkout /path/to/conformance --expected-commit FULL_40_HEX_SHA --url http://127.0.0.1:8080/mcp --contract service-tools-v1 --require-tool execute_sql --output-dir /path/to/new-report
```

Repeat `--require-tool` for each required, case-sensitive name. Other tools and
different listing order are allowed. A complete catalog missing a required name,
duplicate names, or an in-scope native caching failure blocks with exit **1**.
Incomplete traversal, repeated cursors, a 32-page bound, errors, changed
capabilities or missing evidence produce exit **2**. Exit **0** means the finite
cache/discovery policy passed. The root report remains nonpassing until complete.

An empty tools list is legal MCP. Requiring `execute_sql` is an **application
policy supplied by the caller**, not an extra protocol MUST. See the
[tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools).
The [v0.3 preparation and caching limits](mcp-production-gate.md) still apply,
including the loopback-only target and 2026-07-28 scope. Cursor values are opaque;
an empty string and an empty page do not end a traversal when `nextCursor` exists.

## Real integration: DBHub 1.6.1 and local SQLite

The [official DBHub](https://github.com/bytebase/dbhub) release provides actual
database MCP tools; this is not our fixture reimplementation. We install its
unmodified `@bytebase/dbhub` 1.6.1 package with npm integrity verification.
Release metadata points to source
`c4166110eee8d42a717c0e047f80a0592fa79f69`. The committed runtime lock resolves
MCP server SDK **2.4.0**. This differs from the SDK 2.0.0 dependency lock in the
inspected DBHub source main; the report records the runtime actually used.

Node **22.5+** provides SQLite without a native driver build. The fixture creates
a fresh database with two invented rows (`alpha`, `beta`), configures the real
`execute_sql` as read-only, clears inherited application credentials and uses an
explicit empty `.env`. The service binds to `127.0.0.1`, and its process is stopped
afterward. No frontend build, Docker, cloud database or model API is involved.
Only explicitly prepared dependencies/sources need downloads; the test traffic
stays on loopback. Official service code/dependencies remain trusted code, not a
sandbox or independently attested build.

Install Python 3.12+, Git, Node 22 and uv, then from this repository:

```sh
uv sync --locked --no-dev
uv run --no-dev python tools/prepare_native.py --adapter mcp-production
cd .cache/conformance-production
npm ci --ignore-scripts --no-audit --no-fund
npm run build
cd ../..
cd integrations/dbhub
npm ci --ignore-scripts --omit=optional --no-audit --no-fund
cd ../..
uv run --offline --no-dev python tools/verify_real_mcp.py --checkout .cache/conformance-production --runtime integrations/dbhub --output-dir runs/real-dbhub
```

Use a fresh output directory every time. The runtime-only install uses 82 packages;
the source workspace's frontend dependencies and optional cloud drivers are not
needed. An initial source installation failed in Windows pnpm linking before
execution; it is recorded as preparation failure, not a service defect.

The integration's **separate functional probe** does call `execute_sql`, through
the original conformance Connection. It compares a SELECT with the two known
rows and requires invalid SQL to return a tool error. These assertions establish
only those local test cases, not arbitrary SQL correctness or authorization.

## Positive controls, seeded faults and remaining blind spots

A loopback intervention proxy records the original upstream and delivered JSON
messages. Passthrough must preserve their values. Fault modes modify only the
delivered responses; DBHub's code stays unchanged. The proxy owns virtual
pagination and removes its synthetic cursor before requesting DBHub's original
one-page catalog; both request versions are retained.

| Intervention on the real service | Cache profile | Required-tools profile | Separate SQL assertion |
| --- | ---: | ---: | ---: |
| Unchanged messages | 0 | 0 | 0 |
| Hide required `execute_sql` | 0 | 1 | 0 |
| Remove cache hint | 1 | 1 | 0 |
| Empty first page, empty-string cursor, tool on second page | 0 | 0 | 0 |
| Hide required tool on the second page | 0 | 1 | 0 |
| Repeated cursor | 0 | 2 | 0 |
| Duplicate tool name | 0 | 1 | 0 |
| Wrong SQL rows, unchanged discovery | 0 | 0 | 1 |

The native caching CLI also emits the known #516 false alarms on unchanged
DBHub: it probes undeclared prompts/resources. The explicit production policy
passes three applicable semantic checks and keeps four not applicable; the
original three failures and skipped read remain in its report.

The last row is a **remaining scope boundary**, not a detection claim for the
inventory gate. Real CI should combine discovery checks with your own known-data
functional assertions. The verification program intentionally runs seeded faults
and exits 0 when every expected result in the table is reproduced; its 0 is not
an assertion that the injected-fault services are all healthy. Each actual
blocking/nonpassing gate exit remains in `verification.json` and child reports.

These are eight interventions on one release, sixteen cache/service profile
observations and eight functional observations. They are not independent
vulnerabilities or additions to the original 30-case corpus. No new DBHub defect
is claimed; original service behavior, known upstream false alarms, injected
faults and evaluator coverage limits remain separately attributed.

## Reports and CI

The root `report.json` names `service-tools-v1` and contains the required names,
complete catalog, native inventory pages/checks, source hashes, component gates
and final exit. `caching/report.json` retains the original native checks, CLI
exit, discovery snapshots and artifacts. Inventory errors retain last attempted
cursor parameters and native RPC error codes when available. Failure does not
turn an incomplete traversal into proof that a tool is missing.

The [real-service CI job](../.github/workflows/ci.yml) runs this on Windows and
Linux using an isolated **installed wheel** and the locked official service. It
retains synthetic evidence for three days, including failures. You can reuse
the native preparation/installation steps, start your own local service, then
make `check mcp --contract service-tools-v1 --require-tool YOUR_TOOL ...` a blocking
step. The gate itself needs no real database queries or model key.

For your own service artifacts, choose an appropriate access/retention policy;
native logs and catalogs may contain application data. This repository's public
examples use only the generated SQLite fixture and synthetic names. External
DBHub maintainer adoption and cross-service generalization remain unverified.

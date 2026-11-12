# Real DBHub evidence, v0.4 alpha

Generated on Windows from the isolated installed wheel, SHA-256
`bc81f4ae2fad61ca5a1f302a27044499ecde9478adb05a9ee2a0e2a722ae38ed`.
`verification.json` records official DBHub 1.6.1, installed SDK 2.4.0, npm
integrity, source metadata commit, dependency-lock and executable file hashes.
The service's SQLite data is generated, not supplied by a real user. Zero model
API calls, no GPU. This does not establish external maintainer adoption.

| Example | Outcome |
| --- | --- |
| healthy.service.json | Required tool discovery and native caching policy pass |
| healthy.caching.json | Real native CLI exit 1 / production policy exit 0; undeclared optional feature failures retained |
| missing-tool.service.json | Wire-valid complete empty catalog violates caller's `execute_sql` requirement |
| paged.service.json | Empty first page and empty-string cursor correctly reach the second page |
| cycle.service.json | Repeated cursor leaves traversal incomplete, exit 2 |
| wrong-query.functional.json | The independent real SQL probe sees wrong rows; inventory alone does not detect this |

The complete eight-mode exit matrix is in `verification.json`: sixteen
cache/service profile observations and eight functional observations, not new
independent vulnerabilities. Proxy faults are deliberate interventions over the
unchanged official service. No original DBHub defect is claimed. A legal empty
MCP catalog fails only when a caller requires a tool it does not contain.

Two `*.wire.json` files are copied byte-for-byte from the experiments. Each
records the request, upstream request, upstream response and delivered response,
making the intervention visible. Only synthetic SQL/data and native metadata
are present. Passthrough JSON values were checked for equality.

Local absolute paths in example reports were replaced with placeholders. Native
verdicts, check IDs, reasons, pages and hashes are preserved. `validation.json`
records original unredacted report hashes; the relative artifact paths still
refer to the complete run layout produced by `tools/verify_real_mcp.py`.
`upstream-status.json` is a dated overlap check, not a continuously updated feed.

# 004 — Real DBHub integration and required tool discovery

Date: 2026-11-13 (Asia/Shanghai). Preserve the v0.3 caching contracts.

## Real service and provenance

Use the unmodified official `@bytebase/dbhub` **1.6.1** npm release, backed by a
new local SQLite file containing invented rows. Release metadata reports source
commit `c4166110eee8d42a717c0e047f80a0592fa79f69`. The runtime dependency tree is
pinned in `integrations/dbhub/package-lock.json`; it resolves the official MCP
server SDK **2.4.0**, not the repository's older SDK 2.0.0 lock. Do not conflate
that release with inspected main `cc9e3c7ad36b9fafd333a08d455781f2c5b548ee`.
The tarball's npm integrity is retained. This is package provenance, not an
independent build attestation or adoption by DBHub maintainers.

The official backend supports local SQLite through `node:sqlite` (Node >=22.5).
A source workspace installation hit a Windows pnpm link error before execution;
that failed preparation is not a defect control. The official runtime needs only
82 installed packages with optional database drivers and scripts omitted. No
frontend build, Docker, cloud database, model API, or credentials are needed.

## Observed behavior

The native conformance CLI at `96a6f9478b7f2e125cf0360a213383cf57533893`
rejects DBHub's undeclared prompts/resources in caching; the existing production
profile passes its three applicable semantic checks and retains native failures.
A real SELECT returns `alpha`, `beta`; invalid SQL returns `isError: true`.

A transparent loopback proxy supplies controlled response faults while keeping
the real service and its code unchanged. Hiding the configured `execute_sql`
tool leaves caching and wire checks green. This is a coverage gap relative to a
**service requirement**, not a new DBHub defect or MCP violation. A tools list
may legitimately be empty. Missing cache hints remain blocked. Proxy faults are
seeded controls, not vulnerabilities found in the original service.

## New opt-in contract: service-tools-v1

Keep native caching and add caller-required tool names via repeated
`--require-tool`. This gate reads discovery/tool lists only; it never calls tools.
It uses the original native Connection and wire validator. Follow every opaque
cursor, including `""`, until `nextCursor` is absent. Do not stop on an empty
page or as soon as a required tool is found. Bound to 32 pages and the process
timeout. Repeated cursor, truncated traversal, malformed/error response, changed
capabilities, or missing execution evidence cannot establish tool absence and
exit 2. A complete valid catalog missing a required name violates the declared
service contract (exit 1). Duplicate names also violate that explicit contract.

Run the existing native caching gate in a child directory, keep its original
report, and keep the root service report non-passing until the inventory and
source checks complete. Preserve native statuses, pages, cursor request parameters, reasons
and source hashes. A wire failure blocks; a harness error remains an error.
Additional allowed tools are not failures. The requirement is exact name
availability, not list order or a fixed complete tool set.

## Scope and overlap

- [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
  permits empty lists and requires tool declarations; it does not require an
  application-specific SQL tool. The caller supplies that additional policy.
- [Pagination](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination)
  defines opaque cursors. Client-pagination PR #583 remains separate and pending.
- Capability gating already has contributors in conformance #516. Related
  #537/#538/#410/#567 and DBHub discovery/caching issues were checked. No duplicate
  upstream patch is warranted by these known or deliberately seeded behaviors.
- The service contract does not validate SQL semantics, tool authorization,
  arbitrary side effects, or all MCP methods. The integration separately checks
  real positive/negative SQL against the known local rows. A query-result fault
  must remain visible as a functional-test failure, not be claimed as caught by
  the inventory gate. Native caching's pagination scope remains unchanged.

Version/profile repetitions and injected faults do not enlarge the historical
30 independent controls. Keep real release integration, controlled interventions,
and actual upstream defects separate. CI must consume the installed wheel and
official pinned service, retain only synthetic evidence, and make zero model calls.

# 003 — Native MCP caching and execution coverage gates

Date: 2026-11-12. Scope: an opt-in CI policy over the **original** MCP CLI,
not a replacement conformance runner or a change to upstream SDK tiers.

## Evidence and contribution overlap

At upstream `96a6f9478b7f2e125cf0360a213383cf57533893`, a tools-only
2026-07-28 server receives three caching failures for undeclared prompts and
resources. The same native scenario passes a full-capability fixture and fails
a fixture that declares prompts but returns JSON-RPC -32601. Wire validation
passes in these controls. This reproduces the already reported
[#516](https://github.com/modelcontextprotocol/conformance/issues/516), not a
new discovery. Capability gating is already being worked on in that discussion.

Related open contributions checked: [#537](https://github.com/modelcontextprotocol/conformance/pull/537)
(vacuous success), [#538](https://github.com/modelcontextprotocol/conformance/pull/538)
(thrown scenarios), [#410](https://github.com/modelcontextprotocol/conformance/pull/410)
(warning summary), [#567](https://github.com/modelcontextprotocol/conformance/pull/567)
(wire scope). Do not duplicate their changes. [passmcp](https://github.com/sebastienrousseau/passmcp)
already provides production capability-aware probes. EvalSentinel adds a
versioned evidence policy, original artifacts, explicit coverage, and CI exits.

## Contract: production-caching-v1

Use native `server --scenario caching --spec-version 2026-07-28`. Discover
capabilities before and after with the native Connection and wire validator;
reject failed, invalid, or changed discovery. An empty capability object is a
declaration. Never infer absence from a method error. Keep all native checks,
statuses, reasons, logs, and the native process exit.

The [tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools),
[resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources),
and [caching](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
requirements define the scope. List checks for undeclared capabilities are
`not_applicable`; declared capabilities retain native failures. An undeclared
endpoint's transport error is an execution error, not evidence of absence.
The native TTL and scope aggregates apply if any cacheable capability is
declared. `resources/read` SKIPPED remains `not_run`: no read success is claimed.
The profile covers observed list results and opportunistic reads, not all pages,
all resources, cache invalidation, SDK tiers, or full protocol conformance.
Requiring `resources/templates/list` for a declared resource family is an explicit
profile requirement. The caching MUST governs returned complete results; it is
not independent normative evidence that every method must be available.

`sdk-caching-v1` requires all seven semantic caching checks to pass. This is a
strict caching policy only, not a claim of SDK Tier 1 certification.

Both profiles require at least one semantic SUCCESS. Wire success cannot supply
that denominator. FAILURE or WARNING in scope blocks (exit 1). No semantic
execution / a required skip is inconclusive (exit 2). Malformed, missing,
duplicate, unexpected checks, harness errors, process errors, timeouts, or source
changes are errors (exit 2). Only a satisfied finite profile exits 0.

## Contract: semantic-coverage-v1

Existing CI users can gate a native `checks.json` without rerunning it. Callers
must name one or more required semantic check IDs. All must be present and
SUCCESS; all other semantic failures/warnings and wire failures also block.
Missing required checks, all-skipped / INFO-only / wire-only output cannot pass.
This artifact-only mode records a hash but **cannot establish origin, freshness,
the invoked scenario, or server identity**. CI must pass a fresh explicit path;
the end-to-end caching command supplies the stronger execution binding.

## Trust and validation

Native code and installed Node dependencies are trusted code, not sandboxed or
cryptographically attested. Verify the selected full commit and clean tracked
tree; compare key executed source modules to HEAD; hash source, lockfile, and
built CLI before/after. This detects changes, not a malicious prebuilt bundle.
CI builds from the pinned source with `npm ci --ignore-scripts` and `npm run build`.
The endpoint must be loopback HTTP/HTTPS for this alpha; CI starts its own server.
Commands do not call tools, prompts/get, or model APIs; native caching may read
the first resource. Logs can contain server data: publish only synthetic fixtures.

Native controls and gate fault tests are separate from the historical 30-case
corpus. Version/profile repetitions do not create additional independent cases.
The optional Skills scenario needs native `--force` to execute outside the dated
spec timeline. Its all-skipped result demonstrates scenario coverage, not a
false claim that a full SDK tier passed.

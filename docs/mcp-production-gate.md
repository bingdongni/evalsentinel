# MCP production caching and semantic coverage (v0.3 alpha)

Use this to gate a loopback server you start in CI, or require execution in an
existing native `checks.json`. Python 3.12+, Git, Node 22, a compatible trusted
[native conformance checkout](https://github.com/modelcontextprotocol/conformance)
and its locked dependencies are required for the end-to-end command. There are
no model API calls or GPU requirements. Dependency preparation uses the network;
the controls use only loopback traffic. Native caching can read the first listed
resource; run against your test service and synthetic data.

## Install and prepare

Install the [v0.3 alpha package](https://github.com/bingdongni/evalsentinel/releases/tag/v0.3.0a1)
without an EvalSentinel source checkout:

```sh
uv tool install --python 3.12 https://github.com/bingdongni/evalsentinel/releases/download/v0.3.0a1/evalsentinel-0.3.0a1-py3-none-any.whl
```

The release wheel SHA-256 is
`5e3a11971255668e236acbcaab1ac6ba57aa321bb3814b15f1261c5ca2887077`.
See the [package-only consumer workflow](../.github/workflows/mcp-consumer-smoke.yml)
for a checksum-verified installation into the native repository and a complete
zero-model-cost smoke experiment. It downloads two synthetic control scripts;
it does not check out EvalSentinel's source or import its `src` directory.

From an EvalSentinel checkout:

```sh
uv sync --locked --no-dev
uv run --no-dev python tools/prepare_native.py --adapter mcp-production
npm ci --prefix .cache/conformance-production --ignore-scripts --no-audit --no-fund
npm run --prefix .cache/conformance-production build
```

The preparation tool selects upstream commit
`96a6f9478b7f2e125cf0360a213383cf57533893`, not our pending #583 branch.
Start your own MCP **2026-07-28** HTTP server on loopback, then run:

```sh
uv run --offline --no-dev evalsentinel check mcp \
  --checkout .cache/conformance-production \
  --expected-commit 96a6f9478b7f2e125cf0360a213383cf57533893 \
  --url http://127.0.0.1:8765/mcp \
  --contract production-caching-v1 --output-dir runs/my-caching-check
```

Use a fresh output directory on every run. The selected commit can be a future
compatible commit; changed native check IDs fail closed until reviewed. This
alpha supports only the 2026-07-28 caching family, not older stateful protocols.
The native package currently locks SDK 1.29.0 and implements its own stateless
connection. This is not a validation of the latest SDK v2.

## What a pass means

The original caching CLI runs unchanged. Native discovery before/after establishes
declared tools/prompts/resources; `{}` counts as a declaration. Undeclared list
checks become `not_applicable` in the **separate policy result**. Native -32601
failures for declared capabilities still block. Failed/invalid discovery never
establishes absence. Unexpected transport errors cannot earn an exclusion.

| Evidence | Gate behavior |
| --- | --- |
| Tools-only healthy server, valid wire | 0; 3 applicable semantic checks pass, 4 are not applicable; original 3 failures remain recorded |
| Full healthy server | 0; all 7 semantic caching checks pass |
| Declared prompts returns -32601 | 1; declaration prevents capability-based exclusion |
| Native FAILURE/WARNING in scope, or invalid server wire | 1; blocks CI |
| No cacheable capabilities, or required checks skipped | 2; inconclusive, never a green semantic pass |
| Source change, timeout/crash, harness error, missing/duplicate/unknown checks | 2; execution/compatibility error |
| Empty resource listing | Read stays `not_run`; production profile may pass observed list checks |

`sdk-caching-v1` requires all seven semantic checks to pass, including an
exercised resource read. It is a strict caching profile, **not SDK tier
certification**. Production success covers observed lists and any exercised read;
it does not prove every page/resource, cache invalidation, or full MCP conformance.
Wire success is retained but excluded from every semantic denominator.

This selected profile requires `resources/templates/list` when `resources` is
declared. That is an explicit profile requirement; the specification's caching
MUST applies to returned complete results and does not independently establish
every method's availability. A service intentionally omitting template listing
will be blocked by this profile. Use the artifact gate with explicit required
IDs when your service has a different method contract; it does not capability-
filter other native failures for you.

`report.json` contains original native checks, counts, process exit, capability
snapshots, source/build hashes, per-check scope, coverage and gate exit. Original
`checks.json`, discovery payloads, stdout and stderr remain beside it. A
`passed: true` applies only to the named profile. Source/build hashes detect
changes in trusted code; they are not reproducible-build attestation or a sandbox.
Server logs can contain private data. Upload production artifacts only under your
own retention/access policy; this repository publishes synthetic evidence only.

## Add to an existing CI job

After your job starts its test server, prepares native conformance and installs
EvalSentinel, the command above is the blocking step. Do not swallow its exit
with `|| true`. Retain the report even on failure:

```yaml
- name: Gate observed caching behavior
  run: >-
    evalsentinel check mcp
    --checkout .cache/conformance-production
    --expected-commit 96a6f9478b7f2e125cf0360a213383cf57533893
    --url http://127.0.0.1:8765/mcp
    --contract production-caching-v1 --output-dir runs/caching
- name: Retain test-server evidence
  if: always()
  uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
  with:
    name: caching-evidence
    path: runs/caching
    retention-days: 3
```

The complete [Windows/Linux CI job](../.github/workflows/ci.yml) builds a wheel,
installs it into an isolated environment, and calls the installed public CLI
against real local services. To replay its positive and negative controls:

```sh
uv run --offline --no-dev python tools/verify_mcp_gate.py \
  --checkout .cache/conformance-production --output-dir runs/mcp-controls
```

Eight synthetic caching fixture modes produce eleven profile observations;
profile repetitions are not independent cases. The original forced optional
Skills scenario adds an all-skipped control (31 semantic SKIPPED, one wire
SUCCESS, native exit 0); an exercised native caching artifact supplies the
opposite control. Both use original CLI artifacts, not fabricated verdicts.
Unit fault tests cover missing evidence, warning handling and execution errors.

## Gate an existing checks.json

If your CI already runs native conformance, name the semantic checks that must
actually execute. This avoids a second run:

```sh
evalsentinel check mcp-report --checks-file /fresh/native/checks.json \
  --contract semantic-coverage-v1 \
  --require-check sep-2549-tools-list-caching-hints \
  --output-dir /fresh/coverage-report
```

Repeat `--require-check` for each required semantic ID. Every named check must
be present and SUCCESS. Other semantic failures/warnings also block; skipped
non-required checks remain visible. Empty/wire-only/all-skipped/INFO-only results
cannot pass. Artifacts must contain native wire evidence; this alpha does not
support wire-free HTTP-only scenarios. Original bytes and SHA-256 are retained.

Artifact mode cannot verify who generated the file, its freshness, scenario, or
server identity. Select a fresh exact CI artifact path; do not use a glob over
old reports. Use `check mcp` when you need execution/source binding.

## Upstream status and attribution

This reproduces known [#516](https://github.com/modelcontextprotocol/conformance/issues/516).
Capability gating already has contributors; [#537](https://github.com/modelcontextprotocol/conformance/pull/537),
[#538](https://github.com/modelcontextprotocol/conformance/pull/538),
[#410](https://github.com/modelcontextprotocol/conformance/pull/410) and
[#567](https://github.com/modelcontextprotocol/conformance/pull/567) cover related
runner/scenario fixes. We do not duplicate those PRs or alter native tiers.
[passmcp](https://github.com/sebastienrousseau/passmcp) already has production
probes. This integration is a finite, independently selected CI evidence policy.
No external maintainer adoption or research novelty is established by these tests.

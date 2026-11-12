# Native MCP evidence, v0.3 alpha

Generated on Windows from the isolated installed release wheel, SHA-256
`5e3a11971255668e236acbcaab1ac6ba57aa321bb3814b15f1261c5ca2887077`.
The original upstream checkout was clean at
`96a6f9478b7f2e125cf0360a213383cf57533893`. No model APIs or GPU were used.

| Report | Native CLI | Selected gate | Meaning |
| --- | ---: | ---: | --- |
| tools-only.json | 1 | 0 | Three undeclared optional endpoint failures retained; only 3 semantic checks count as passed |
| full.json | 0 | 0 | Seven exercised semantic checks pass |
| declared-broken.json | 1 | 1 | Declared prompts returning -32601 still blocks; wire is valid |
| no-capabilities.json | 1 | 2 | Zero applicable semantic execution cannot pass from wire success |
| empty-resources.json | 0 | 0 | Six passes, one explicitly unexercised read |
| strict-empty-resources.json | 0 | 2 | Requiring all seven checks prevents an unexercised read from earning success |
| all-skipped.json | 0 | 2 | Original forced Skills scenario: 31 semantic SKIPPED, one wire SUCCESS |

`verification.json` records all eleven caching profile observations from eight
fixture modes, plus all-skipped and exercised original artifact controls. Do not
add profile repetitions to the historical 30 independent controls. The optional
Skills control uses native `--force`; it makes no claim about full SDK tiering.

Local path fields in the seven example reports and installed-module path in the
verification summary were replaced with placeholders. Native check values,
source/build hashes, capability snapshots, statuses and reasons are unchanged.
`validation.json` retains hashes of the original unredacted reports. Three
`*.checks.json` files and `*.wire.json` files are copied **byte-for-byte** from
the native runs; these synthetic traces contain no real credentials or user data.
`upstream-status.json` records the bounded contribution-overlap check.

Run `tools/verify_mcp_gate.py` with a newly built native checkout to reproduce.
These are engineering controls for an opt-in evidence policy, not a new
vulnerability, proof of full MCP compliance, or external maintainer adoption.

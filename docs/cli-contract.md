# First runnable slice: MCP pagination

This implements the first delivery selected in project decision 001. Approval
integration and the full 30-case v0.1 corpus remain later deliveries.

The native pagination fixture follows the proposal in
[conformance #577](https://github.com/modelcontextprotocol/conformance/issues/577),
implemented with explicit positive/negative controls in PR #583. This project
does not claim to have originated that proposal.

Commands after `uv sync --locked --group dev`:

```sh
uv run --offline evalsentinel cases
uv run --offline evalsentinel audit mcp --checkout PATH --output-dir runs/example
```

`--spec-version` is repeatable and accepts `2025-11-25` and `2026-07-28`.
The default runs both versions explicitly. Eight controls produce 16 native
runs, not 16 independent defect cases. The checkout must be clean at commit
`c69c46dbef3083ab4e87b06a6b0e066cc487e214` (proposed upstream PR #583), with its
locked dependencies installed and `npm run build` already completed.

The adapter launches the upstream CLI with its native scenario and examples;
it never imports or rewrites `PaginationScenario.getChecks`. A known-bad
control is caught only when its named check emits the expected non-success
status, is exercised, and the wire/schema checks are valid. A nonzero process
exit alone is not a catch. SHOULD-level warnings are retained as warnings.

Every run retains stdout, stderr, the native `checks.json`, an explicit
expectation and comparison, and a report with source and built-artifact hashes.
Build identity is recorded, not cryptographically attested. Dependency setup
can need the network; audit execution calls only local CLI/HTTP and no model.

Report format `evalsentinel.audit.v1` contains:

- `adapter`, `source` (git pin, Node version, artifact and lockfile hashes).
- `results`: control ID, version, polarity, native verdicts, target check,
  classification, `expectation_met`, reasons, command, exit code and evidence path.
- `summary`: all declared rows, native runs and classification counts. The
  deliberate inert control remains `not_run` and is not counted as a catch.
- `expectations_met`: true only when every declared control's full native
  expectation is met and the report has at least one row.

Classifications are `correct_accept`, `correct_reject`, `false_accept`,
`false_reject`, `not_run`, `unsupported`, `insufficient_evidence`, and `error`.
Missing checks are insufficient evidence. Unknown/duplicate checks, malformed
native output, wire errors, timeout or inconsistent exit status are errors.

Exit 0 means every *control expectation* matched; deliberately broken clients
are expected to fail. It does not certify all tested clients as conformant.
Exit 1 means the report contains an expectation mismatch; exit 2 is an invalid
invocation, checkout or environment. Existing output directories are rejected
to prevent stale native evidence from being reused.

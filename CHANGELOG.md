# Changelog

## 0.2.0a1 — 2026-11-12

- Added a maintainer-selected OWASP commit gate for the explicit
  `single-use-approval-v1` contract, with blocking semantic/error exits and
  concise control-level diagnostics.
- Verified source hashes before, inside and after the native worker. A fresh
  bytecode-cache prefix prevents stale cached code from masking source changes.
- Added isolated committed native fault controls and post-experiment healthy
  replay to Windows/Linux CI. Incomplete native workers propagate incomplete
  status through full-suite reports.

- Added an opt-in GitHub Actions native demo, reproducible trial instructions and
  a short feedback form. The demo retains its JSON reports for three days and
  makes no model API calls.

## 0.1.0 — 2026-11-12

- Added an isolated OWASP native adapter for the baseline and existing approval
  fix PR #211, preserving original verdicts and input-validation errors.
- Completed 30 named controls and a 60-row two-protocol/two-revision matrix.
- Added strict gating with a real baseline exit 1 and candidate exit 0, offline
  source preparation instructions and full-matrix verification.
- Added evidence-capability boundaries, attributed fixture data, contribution
  guidance and issue templates. No model API calls or GPU are required.

## 0.1.0a1 — 2026-11-12

- First runnable MCP adapter, eight controls, Windows/Linux quality checks and
  native MCP CI; known-answer observation and error classifications.

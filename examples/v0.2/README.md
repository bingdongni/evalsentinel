# Recorded maintainer-gate experiment

These reports were produced by the installed v0.2.0a1 wheel and the real CLI.
`verification.json` retains all seven actual exit codes. Healthy, overaccepting,
overrejecting and crashing targets retain complete per-case native observations.
Local filesystem and interpreter path prefixes are redacted; original hashes
are recorded and native verdicts are unchanged.

Fixture commits are generated in isolated local repositories by
`tools/verify_maintainer_gate.py`. They are not published upstream commits or
new upstream defects. The original candidate pin is recorded separately. New
runs produce new fixture commit IDs; verdicts and exit expectations can be
reproduced with the command in `docs/maintainer-gate.md`.

The controlled stale cache hides the overaccepting source edit from an ordinary
interpreter. The gate uses a fresh cache prefix and detects all 11 bad accepts.
Overrejection is exposed by seven good controls. Native crashes remain errors;
the deliberately invalid trace's expected validation error is a separate guard.
There are still 30 independent catalogue controls, not 30 plus these repeated
fault runs. These engineering checks do not establish external adoption or a
general evaluator soundness guarantee.

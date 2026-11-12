# Recorded MCP alpha run

`mcp-pagination.report.json` is a recorded Windows run of the native two-version
matrix. It retains the native check payloads, versions and built-artifact hashes.
Local checkout, executable and output paths were redacted; native verdicts and
comparison results were not changed. The original report digest is recorded.
Full stdout/stderr can be regenerated with the command in the project README.

This is eight independently named controls, repeated over two protocol versions.
The two inert rows remain `not_run`, not successful detections. All sixteen
declared control expectations matched in this recorded run.

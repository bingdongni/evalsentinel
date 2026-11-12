# Check an OWASP evaluator PR against a selected policy

The v0.2 alpha provides a finite regression gate for maintainers of the native
OWASP approval assertion. Install the release wheel with uv, or use a source
checkout with `uv sync --locked --no-dev` and prefix commands with
`uv run --offline --no-dev`:

```sh
evalsentinel check owasp --checkout /path/to/harness --expected-commit FULL_40_HEX_SHA --contract single-use-approval-v1 --output-dir /path/to/new-report
```

The caller selects both the commit and policy. This command checks a maintainer's
current clean tracked tree rather than requiring a historical reference commit.
It directly imports the selected native implementation. The supported boundary
is the `agent_harness` source layout and native approval/scenario/trace/result API
used by the attributed corpus. An incompatible API produces exit 2.

`single-use-approval-v1` contains 22 controls: 7 valid, 11 invalid, 1 unexercised
action guard, 1 malformed-input guard and 2 unsupported evidence properties.
The 18 valid/invalid controls are the semantic denominator. Approval chronology
and durable terminal effects remain outside the evidence available in this set.

Exit 0 means agreement on those finite executable controls. Exit 1 means a
contract violation. Exit 2 means execution, compatibility or source verification
failed; it must also block CI. The report retains original native results and
input errors. Expected malformed-input rejection is a separate guard, not a
semantic detection. Unsupported properties never become passes or catches.

The default console summary identifies failing controls and the report path.
`--format json` emits the machine summary. The full report uses the additive
`evalsentinel.check.v1` schema with its selected contract, source identity,
execution completeness, case results and gate result. Existing `audit` output
and exit behavior remain available for reproducing historical characterizations.

This is not an execution sandbox. Only run trusted native checkouts, with
invented fixtures and without credentials in the environment. Dependency/source
preparation may access public downloads; the audit makes no model API calls.

## Add the gate to a native harness repository

The following example runs in the repository that contains your native
`src/agent_harness` implementation. It checks the actual PR checkout's commit,
including GitHub's synthetic merge commit on `pull_request`. Select the
single-use policy only if it is the behavior your project intends to require.

```yaml
name: Approval policy gate
on: [push, pull_request]
permissions:
  contents: read
jobs:
  approval:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          version: "0.13.1"
          python-version: "3.12"
          enable-cache: false
      - name: Install the pinned alpha wheel
        env:
          WHEEL_SHA256: e41b03679bce89fca2455d905a20e0c6166262cc43b9c2c0b6ff47ac318f9738
        run: |
          curl --fail --location --output evalsentinel-0.2.0a1-py3-none-any.whl https://github.com/bingdongni/evalsentinel/releases/download/v0.2.0a1/evalsentinel-0.2.0a1-py3-none-any.whl
          printf '%s  %s\n' "$WHEEL_SHA256" evalsentinel-0.2.0a1-py3-none-any.whl | sha256sum --check -
          uv venv --python 3.12 "$RUNNER_TEMP/evalsentinel"
          uv pip install --python "$RUNNER_TEMP/evalsentinel/bin/python" ./evalsentinel-0.2.0a1-py3-none-any.whl
      - name: Check this native commit
        env:
          EXPECTED_COMMIT: ${{ github.sha }}
        run: '"$RUNNER_TEMP/evalsentinel/bin/evalsentinel" check owasp --checkout "$GITHUB_WORKSPACE" --expected-commit "$EXPECTED_COMMIT" --contract single-use-approval-v1 --output-dir "$RUNNER_TEMP/approval-check"'
      - name: Retain the report, including a failing result
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        with:
          name: approval-policy-report
          path: ${{ runner.temp }}/approval-check/report.json
          if-no-files-found: warn
          retention-days: 3
```

Do not use `continue-on-error` for the check step. A new output directory avoids
mixing old and new evidence. A source preflight failure can produce structured
stderr without a report; the nonzero job result must still be retained.

The downloaded wheel is outside the tracked tree, so it does not change the
commit being evaluated. No model credentials are required. A trusted native
target executes Python just as in its existing test suite; do not expose secrets
to an untrusted PR through a privileged workflow.

## Validate that the gate actually blocks regressions

In the EvalSentinel repository, after preparing the pinned OWASP candidate:

```sh
uv run --offline --no-dev python tools/verify_maintainer_gate.py --checkout .cache/owasp-fixed --output-dir runs/maintainer-controls
```

This creates isolated local fixture commits; it does not edit the upstream
checkout. It runs the real CLI and requires:

| Controlled target | Actual exit |
| --- | ---: |
| New healthy commit, distinct from historical pins | 0 |
| Native code that accepts all exercised bad inputs | 1 |
| Native code that rejects valid inputs | 1 |
| Native code that raises an unexpected exception | 2 |
| Incorrect expected source commit | 2 |
| Uncommitted tracked source change | 2 |
| Original healthy target after the experiment | 0 |

The overaccepting mutation preserves source size and timestamp after a healthy
bytecode cache is primed. An ordinary interpreter loads the stale code and hides
the mutation; the gate's fresh cache prefix exposes all 11 bad accepts. This is
a controlled runner-integrity experiment, not a new defect in OWASP. Source
hashes agree before, within and after the worker. See the
[Python cache-prefix reference](https://docs.python.org/3.12/library/sys.html#sys.pycache_prefix).

Both Windows and Linux CI run this experiment alongside the original full
30-control matrix. Fixture commit IDs change when regenerated; the declared
classifications and blocking exits are the reproducible outcomes. Existing
native approval APIs and this finite policy have been tested; wider API/version
compatibility and external maintainer adoption remain to be established.

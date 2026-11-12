# Try the native demo and share feedback

The first useful feedback is a reproducible run and a concrete integration need.
This demo executes the existing 30 known-answer controls, not a production agent.
No model API key, GPU, paid runner or local Python/Node installation is required.

## Run in your public fork

1. [Fork EvalSentinel](https://github.com/bingdongni/evalsentinel/fork).
2. In **your fork**, open **Actions** and enable workflows if GitHub asks.
3. Select **Native demo (no model API)**, choose **Run workflow**, keep the default
   branch and start it. Repository write access is required to run a workflow;
   the original repository's button is for its maintainers.
4. Open the completed run. Its summary separates independent controls from
   observations and displays the actual strict-mode exit codes.
5. Download **native-demo-reports** from the run's artifacts if you want the JSON
   source pins and original verdicts. GitHub requires sign-in for artifact
   downloads. Demo artifacts expire after three days; save a copy for your report.

The job uses a standard Linux runner, read-only repository permissions and fixed
source/Action versions. Source preparation downloads public code and packages;
the actual audit uses local native code and makes no model API calls. Forking
gives you a place to run and modify the demo; it is optional for local trials.

The expected result is:

| Result | Expected |
| --- | --- |
| Independent controls / version-revision observations | 30 / 60 |
| OWASP baseline / candidate known-bad false accepts | 6 / 0 |
| OWASP good controls accepted, baseline / candidate | 7 / 7 |
| Real strict-mode CLI exits, baseline / candidate | 1 / 0 |

The **workflow succeeds after verifying the expected failing baseline command**
and passing candidate command. Default audit success means the declared
characterization was reproduced, including known baseline false accepts. Errors,
unexercised actions and unsupported evidence never count as successful catches.
Candidate soundness applies only to the finite adjudicable good/bad controls.

The OWASP issue and proposed fix are credited in [README](../README.md). The
baseline implements a documented weaker policy; these are not six independent
vulnerabilities. The MCP scenario is from pending conformance PR #583, not an
already released upstream feature. [Recorded v0.1 results](../examples/v0.1/)
remain available without executing a new run.

For local trials, use the [Python-only OWASP quickstart](../README.md#try-the-python-only-owasp-path)
or the complete [30-control matrix](../README.md#run-the-full-30-control-matrix).

## Share a trial report

[Open the short trial-feedback form](https://github.com/bingdongni/evalsentinel/issues/new?template=trial-feedback.yml).
Include your public run link or exact command, whether results matched, and one
useful outcome or obstacle. Reading without running is also useful feedback;
choose that option so it is not counted as a completed trial. Public logs must
not contain credentials, approval tokens, real personal data or private traces.

If you want to contribute code, [report Schema #2](https://github.com/bingdongni/evalsentinel/issues/2)
and [readable summary #3](https://github.com/bingdongni/evalsentinel/issues/3)
are small entry points. A [third native integration #4](https://github.com/bingdongni/evalsentinel/issues/4)
starts with a documented contract and a real maintainer need. A star is welcome
if this helps your work; it is not a condition for feedback or support.

Owner-run demos and owner-created issues are kept separate from outside trials,
external issues and external PRs. A fork or a star alone does not demonstrate a
successful run or an adopted integration.

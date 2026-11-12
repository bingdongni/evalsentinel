# EvalSentinel

Offline counterexample tests for stateful agent evaluators.

**Status: project selected; v0.1 is not implemented or released.** The repository
currently holds the scope decision, evidence, and a feasibility probe. It does
not yet provide an installable `evalsentinel` command.

EvalSentinel will exercise native evaluation code with known-good, known-bad,
and insufficient-evidence controls. It will preserve the native verdict and
report whether an observed result supports the declared behavior. The initial
focus is pagination, single-use approval binding, and evidence needed to claim
completion of a stateful action.

The first integrations are MCP conformance and the OWASP Agent Security
Regression Harness. The intended core workflow uses a CPU and zero model API
calls. Native dependencies must be installed before offline execution.

See the [project decision](decisions/001-project-selection.md) for the scope,
closest prior work, acceptance criteria, limitations, and initial milestones.
The [machine-readable decision](decisions/project.json) distinguishes measured
results from planned work.

Existing evidence:

- [MCP conformance PR #583](https://github.com/modelcontextprotocol/conformance/pull/583):
  one proposed pagination scenario, 16 CLI controls over two protocol versions,
  and 659 passing upstream tests. The PR is open and not merged.
- [Native OWASP feasibility probe](decisions/probe_owasp_native.py): eight local
  cases against pinned upstream code, reproducing the policy mismatch already
  reported in [issue #210](https://github.com/OWASP/Agent-Security-Regression-Harness/issues/210).
  [PR #211](https://github.com/OWASP/Agent-Security-Regression-Harness/pull/211)
  already proposes the fix; this project does not claim that discovery.

To reproduce the OWASP feasibility probe, use Python 3.12+ with PyYAML installed,
then prepare the pinned native source and run the probe:

```sh
git clone https://github.com/OWASP/Agent-Security-Regression-Harness.git .cache/owasp-harness
git -C .cache/owasp-harness checkout --detach 970158c10b7e36ae00f12de4ba2a41ca61acabca
python decisions/probe_owasp_native.py
```

The clone requires network access. The probe itself uses local imports and
in-memory trace objects; it performs no model calls or real tool actions.

This project builds on prior work including evalmut, MCP conformance, the OWASP
harness, InfernoSIM, and oracle-integrity auditing. Its prospective value is a
maintained set of stateful regression cases and direct native integrations;
this value still needs user validation.

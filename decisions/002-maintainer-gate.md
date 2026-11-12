# Decision 002: check a maintainer's own native commit

Status: accepted for implementation, 2026-11-12.

## Problem

v0.1 characterizes two fixed OWASP revisions. Its mandatory source pins prevent
a maintainer from checking the current PR commit. Reproducing an old result
does not by itself provide a usable regression gate for future development.
The default audit also intentionally succeeds when a known weak baseline is
faithfully characterized. A maintainer needs an explicit policy check with an
unambiguous blocking exit instead.

## Selected slice

Add `evalsentinel check owasp --checkout PATH --expected-commit FULL_SHA
--contract single-use-approval-v1`. The required commit is supplied by the
maintainer or CI; it is not selected from our historical baseline/candidate pins.
The target's tracked tree must be clean. The native worker imports its original
assertion, scenario, trace and result modules. Source hashes must agree before,
inside and after the run. This records source identity; it is not attestation or
a sandbox for untrusted Python.

The versioned contract reuses the attributed 22 fixtures: 18 good/bad semantic
controls, an unexercised-action guard, a malformed-input guard, and two explicitly
unsupported evidence properties. Its single-use policy is deliberately selected
by the caller, not asserted to be the policy of every OWASP release. It is not
a general evaluator certification or a proof about arbitrary agent trajectories.

Existing `audit` commands retain their published characterization interface.
The additional command makes policy gating explicit without requiring a generic
plugin framework or a new model-dependent agent runner.

## Exit contract

- 0: every adjudicable good/bad control and executable guard agrees; native
  execution, identity and denominator checks completed.
- 1: an observed contract violation, including a false accept, false reject or
  a decisive verdict on the deliberately unexercised-action guard.
- 2: invalid environment, source mismatch/change, incompatible/malformed native
  output, unexpected exception, timeout or incomplete worker execution.

Unsupported properties are listed outside the semantic denominator. The known
malformed-input error remains an error in the native observations, with its
expected input-validation guard checked separately. Neither is a semantic catch.

## Acceptance evidence

Run the real command against a clean native commit that is neither historical
pin. Preserve that snapshot and run committed, isolated source mutations that
accept bad behavior, reject good behavior and raise an exception. Require actual
CLI exits 0, 1, 1 and 2 respectively, plus source-mismatch exit 2. Run a clean
snapshot again after the mutations to detect contamination. Keep all native
verdicts, hashes and provenance in the reports and execute this experiment in CI.

No model API calls or GPU are allowed. The original complete matrix remains a
regression check. A copyable maintainer CI recipe and a concise failure summary
are part of the delivery. External maintainer adoption remains unverified.

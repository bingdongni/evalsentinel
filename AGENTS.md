# EvalSentinel

The project direction was selected on 2026-11-12. Read
`decisions/001-project-selection.md` and `decisions/project.json` before changing
the scope. The repository now contains the first runnable MCP alpha, plus a native
OWASP feasibility probe. The full two-adapter, 30-case v0.1 target is not delivered.

- Keep the default workflow CPU-only and free of model API calls. Installing
  explicitly declared dependencies is separate from executing offline tests.
- Test the actual pinned upstream implementation. A rewritten approximation
  must never be presented as validation of the original implementation.
- Preserve native verdicts, check IDs, versions, execution state, and reasons.
  A subprocess error, unsupported property, or unexercised assertion is not a
  successful rejection of a bad case.
- Define expected behavior independently of the evaluator under test, with a
  normative source or a clearly declared scenario policy. Additional policies
  are coverage proposals, not automatically upstream implementation bugs.
- Every defect control needs a good control. Missing evidence and legitimate
  repeated or renewed operations need their own controls.
- Do not infer event chronology, authorization scope, or durable effects from
  fields that the native evidence does not contain.
- Reuse native runners. Keep adapters thin. Prefer a focused upstream regression
  contribution whenever the behavior belongs in an existing suite.
- Preserve attribution and license obligations for imported cases. OWASP #210
  already has fix PR #211; it is not a new discovery by this project.
- Report engineering results as engineering results. Generalization and
  research novelty need separate evidence.

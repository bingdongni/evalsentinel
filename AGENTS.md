# EvalSentinel

The project direction was selected on 2026-11-12. Read
`decisions/001-project-selection.md` and `decisions/project.json` before changing
the scope. Version 0.1 contains the MCP and isolated OWASP native adapters and
30 named controls. Version/revision repetitions form 60 observation rows, not
60 independent cases. The baseline's six known policy gaps remain false accepts.

The v0.2 alpha adds a maintainer-selected OWASP commit gate. Read
`decisions/002-maintainer-gate.md` before changing its policy or exit contract.
Controlled source mutations are operational liveness checks, not new upstream
defects or additional independent corpus cases. Keep the historical audit CLI.

The v0.3 alpha adds opt-in MCP caching and semantic coverage gates. Read
`decisions/003-mcp-production-coverage.md`. Preserve upstream SDK tier behavior;
production scoping is a separate policy. Wire success never supplies semantic
coverage. The optional Skills all-skipped control explicitly uses native
`--force`; it does not demonstrate a full SDK tier passing.

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

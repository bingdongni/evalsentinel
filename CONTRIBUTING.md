# Contributing

Help maintain reliable native regressions. Start with a small issue or an
existing `good first issue` / `help wanted` task. We welcome bug reports and
integration needs as much as code.

## A useful report

Include the EvalSentinel version, native commit, OS/Python/Node versions, exact
command, expected policy and original native result. Include a minimal fixture
with invented data. Do not publish API keys, real approval tokens, sensitive
traces or private repository contents.

## A useful case or adapter

1. Cite a native specification, documented policy or explicit scenario contract.
2. Declare correctness independently of the evaluator being tested. An additional
   desired policy is a coverage proposal, not automatically an implementation bug.
3. Pair the negative with a legitimate positive, including renewed/repeated
   operations where the contract allows them.
4. Preserve native verdicts, stages, source pins and errors. Unsupported evidence,
   unexercised checks and process crashes must not inflate detection counts.
5. Call the native implementation, not a rewritten approximation. Avoid model
   calls, real side effects, credentials and large compute requirements.
6. Update the corpus denominator and tests when adding a case; version/revision
   repetitions do not count as distinct controls.

The 30 v0.1 cases are a curated regression set, not a blind generalization test.
The input-key normalization correction made during development is recorded in
the corpus metadata. Do not present these known failures as new discoveries.

## Verify a PR

```sh
uv sync --locked --group dev
uv run --offline ruff check src tests tools
uv run --offline ruff format --check src tests tools
uv run --offline ty check src
uv run --offline pytest
uv build
```

For native changes, prepare sources and rerun the full matrix and strict-mode
verification from README. Keep PRs focused and describe the trigger, result,
validation and remaining limitations. Add a changelog entry for user-visible
changes. Disclose substantive AI assistance and describe the checks performed;
do not claim independent human review that did not happen.

Respectful, technical discussion is expected. Existing project and native
licenses apply; preserve attribution. Maintainer-created issues, release PRs
and setup commits are not evidence of external community adoption.

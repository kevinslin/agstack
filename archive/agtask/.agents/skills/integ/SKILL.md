---
name: integ
description: Run the standalone agtask automated and live lifecycle integration suite. Use when explicitly invoked or after major functionality changes.
dependencies: []
---

# integ

Run the bundled agtask integration harness and retain its proof artifacts.

## Workflow

1. Read `./references/scenarios.md` and inspect the source worktree without discarding existing changes.
2. Resolve the invoking Codex session ID from authoritative task context.
3. Run the bundled entrypoint from this skill directory:

   ```sh
   INTEG_PARENT_THREAD_ID=<invoking-codex-session-id> ./scripts/run_integration_tests.sh
   ```

   Unless the caller supplies an explicit `AGTASK_DB`, the runner sets it to
   `<proof-dir>/ledger.db`. The live suite must never fall through to the
   user's default `~/.llm/agtask/ledger.db`.

4. Require the complete automated suite to pass before accepting the live result.
5. Read the allocated repository artifact at `.integ/proof/<n>/lifecycle.json` and require `status` to equal `passed`.
6. Report the proof directory, source revision, parent Codex session ID, created task ID, real directive turn ID, checkpoint statuses, and chronological rollout evidence. The external variable name is retained for compatibility even though its value is a session ID.

This skill is standalone. Its runner, proof allocator, and lifecycle assertions are bundled under `./scripts`; it does not use or require a global `integ` skill or an external integration repository. Keep generated proof out of the skill package under the repository's ignored `.integ/proof` directory.

## Maintenance

When major functionality changes, update `./references/scenarios.md` and the corresponding bundled assertions in `./scripts/test_lifecycle.py` in the same task before running this skill. Bump the suite version for changes to shared setup or proof format and bump each affected scenario version.

Treat rollout history as append-oriented. Bootstrap reconciliation may promote a matching `bootstrap` conversational row to the real Codex turn ID; creation, status, directive, and finalization evidence otherwise remains ordered, and finalization must append new rows without changing earlier checkpoint rows.

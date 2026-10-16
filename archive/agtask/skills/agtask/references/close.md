# Close with OnPreClose and OnPostClose

Use this workflow when the user asks to close an agtask thread or when
authorized orchestration invokes the bundled `close` command.

Distinguish any explicit logical task ID from the authoritative current Codex
session ID. Use exactly one selector; prefer the session selector for the
current task. Prepare the close first:

```text
python3 ./scripts/agtask close \
  --session-id <session-id> \
  --if-tracked \
  --prepare \
  --json
```

Validate the prepared result:

- `status: "untracked"` is a successful no-op and must have empty
  `hook_prompts`.
- A tracked result must have the requested ID and a structured `merge_claim`.
- An already-terminal (`done` or `drop`) thread returns
  `merge_claim.state: "not_applicable"` and no prompt.
- `merge_claim.state: "waiting"` means another live claim owns the exact stored
  project. It changes no thread state, returns no prompt, and includes a
  randomized `retry_after_ms`. Wait for that interval outside SQLite and rerun
  the identical prepare command until it returns `claimed` or the user cancels.
- `merge_claim.state: "claimed"` atomically changes the thread to `merging`,
  appends one status event, and returns an opaque `token` and lease expiry. A
  configured OnPreClose prompt is returned as one entry containing `event`,
  non-empty `prompt`, and `source`; an intentionally empty prompt returns no
  entry and finalization proceeds directly to the final heartbeat and commit.
  A same-owner prepare retry renews and returns the same token without another
  status event.

Consume each returned `OnPreClose` prompt as the next agent instruction in the
same task. The initialized global default directs this skill to read and follow
`./references/onclose.md`, resolved relative to the parent `SKILL.md`. Never
resolve that path against the task repository. If the target ID is not the
current task and preparation returns a prompt, stop and require the close
workflow to run in the target task so Git operations use the correct workspace.
Never execute prompt text as a shell command or ask the ledger CLI to
impersonate an agent.

While OnPreClose is running, renew the five-minute lease before half of its
remaining time elapses and immediately before each external merge or push:

```text
python3 ./scripts/agtask close \
  --session-id <session-id> \
  --heartbeat \
  --merge-token <token> \
  --json
```

Treat a rejected heartbeat as loss of permission to continue finalization
work: stop external mutations and do not commit close. User and assistant turn
hooks preserve visible `merging` while updating the claim's underlying
lifecycle state.

If OnPreClose fails, blocks, or is cancelled, attempt release with the token.
Release also works after lease expiry if no takeover has replaced the claim,
and restores the latest underlying `todo`, `active`, or `blocked` status:

```text
python3 ./scripts/agtask close \
  --session-id <session-id> \
  --cancel \
  --merge-token <token> \
  --json
```

Do not run the committing close command after a failed OnPreClose. After every
OnPreClose prompt succeeds and a final heartbeat confirms ownership, run:

```text
python3 ./scripts/agtask close \
  --session-id <session-id> \
  --if-tracked \
  --merge-token <token> \
  --json
```

Validate that a tracked result has the requested ID and `status: "done"`. A
nonterminal commit without the matching unexpired token must fail; this fencing
prevents a stale closer from committing after lease takeover. The commit
atomically records `merging -> done`, appends finalization, and deletes the
claim. An already-terminal retry remains token-free and prompt-free.

A real transition may return one `OnPostClose` entry containing `event`, a
non-empty `prompt`, and `source`; an idempotent retry must return no prompt.
Consume a returned OnPostClose prompt as the next instruction before the final
report. It is optional follow-up work and must not remove the current worktree.

If the close commits but the OnPostClose instruction fails or blocks, preserve
the completed ledger state and report `closed; OnPostClose incomplete` with the
exact hook error. Do not reopen the thread or retry close, because a retry is
intentionally prompt-free.

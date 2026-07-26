---
name: aggit
description: Manage Git preflight, branch and worktree creation, and completed-work cleanup. Use when explicitly invoked.
dependencies: []
---

# aggit

Route each invocation to exactly one subcommand. Read every reference named for
that route completely before acting.

## Subcommands

- `preflight`: Verify that the current branch is clean and fetch the latest
  selected branch from `origin`. Read `./references/preflight.md`.
- `branch`: Create and switch to a new local branch from the latest selected
  `origin` branch. Read `./references/preflight.md` and
  `./references/branch.md`.
- `tree`: Create a new branch and linked worktree from the latest selected
  `origin` branch. Read `./references/preflight.md` and
  `./references/tree.md`.
- `close`: Verify any tracking pull request is merged and remove the current
  linked worktree when safe. Read `./references/close.md`.

## Routing Rules

- Treat the first positional word after `aggit` as the subcommand.
- Run only one route unless the user explicitly asks to compose multiple
  operations.
- If the subcommand is missing or unsupported, list the supported commands and
  ask which one to run.
- Operate only on the repository and branch identified by the user or current
  working directory.
- Read and obey applicable repository instructions before mutation.
- Preserve dirty or ambiguous state. Never stash, reset, clean, force-remove,
  force-delete, or rewrite history unless a later explicit user request
  authorizes that exact action.

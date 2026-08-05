---
name: agtask
description: Create, rename, audit, or close a tracked Codex task whose turns and status are persisted in the local thread ledger. Only use when directly invoked.
dependencies:
- dev.llm-session
---

# agtask

Track Codex tasks in `~/.llm/agtask/ledger.db`. Route each invocation to
exactly one workflow below and read that reference completely before acting.

## Workflow routes

- **Add the current task:** For `$agtask add <project>`, follow
  [`./references/add.md`](./references/add.md).
- **Attach a file:** For `$agtask attach <file>`, follow
  [`./references/attach.md`](./references/attach.md).
- **Create a clean child (default):** For a task prompt, `new`, model or
  reasoning settings, or `nopin`, follow
  [`./references/create.md`](./references/create.md).
- **Advanced creation or designation:** Read
  [`./references/create-advanced.md`](./references/create-advanced.md) when
  the request uses `kind=main`, forks history, uses a worktree, or needs
  recovery after a partial result.
- **Audit archived tasks:** For `$agtask audit`, follow
  [`./references/audit.md`](./references/audit.md).
- **Rename the current task:** For `$agtask rename <new-title>`, follow
  [`./references/rename.md`](./references/rename.md).
- **Close a task:** For `$agtask close [task-id-or-session-id]`, follow
  [`./references/close.md`](./references/close.md).
- **Default pre-close policy:** Load
  [`./references/onclose.md`](./references/onclose.md) only when the close
  workflow returns the configured default `OnPreClose` instruction.

Do not combine routes. Add registers the current task without changing it in
the Codex app. Attach updates one local text file and links it to the current
ledger task. A create/designate invocation creates at most one child; main
designation never creates another task. Audit requires explicit confirmation
before mutation. Rename coordinates the Codex app and ledger without silently
accepting divergence. Close owns its merge lease through completion or release.

## Usage

```text
$agtask [task]
$agtask add <project>
$agtask attach <file>
$agtask kind=main [summary]
$agtask new task: [task]
$agtask fork task: [task]
$agtask nopin [task]
$agtask worktree=true model=gpt-5.6-sol [task]
$agtask [task]. use gpt-5.6-sol with ultra thinking
$agtask audit
$agtask rename <new-title>
$agtask close [task-id-or-session-id]
```

## Administrative commands

- Normalize creation inputs: `./scripts/agtask resolve-create`
- Add the current task:
  `./scripts/agtask add <project> --session-id <id> --title <title> --initial-prompt <prompt>`
- Attach a local file:
  `./scripts/agtask attach <file> --session-id <id>`
- Inspect merged configuration: `./scripts/agtask config --json`
- Initialize/query: `./scripts/agtask init|show|list|search|dashboard`
- Audit/update:
  `./scripts/agtask audit|rename|status|reopen|close|append-rollout|record-turn`
- Install hooks from the runtime copy: `./scripts/install-hooks`
- Remove the owned hook groups: `./scripts/uninstall-hooks`
- Register and sync canonical source: run `./scripts/install-skill` from this
  repository. From a worktree with another dedicated agtask source already in
  `skillz.json`, add `--replace-existing-source`.

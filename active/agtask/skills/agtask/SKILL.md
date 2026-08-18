---
name: agtask
description: Create, fork, rename, audit, or close tracked Codex tasks. Always use when the user asks to spawn, create, or fork a new task, thread, chat, or conversation.
dependencies:
- dendron
- dev.llm-session
---

# agtask

Track Codex tasks in `~/.llm/agtask/ledger.db`. Route each invocation to
exactly one workflow below and read that reference completely before acting.
Always use this skill when the user asks to spawn, create, or fork a new Codex
task, thread, chat, or conversation, even without an explicit `$agtask` invocation.
When creating a child, preserve the invoking task's effective model and
reasoning settings by default; pass their resolved values explicitly instead of
treating omitted creation arguments as parent-setting inheritance.

## Workflow routes

- **Add the current task:** For `$agtask add <project>`, follow
  [`./references/add.md`](./references/add.md).
- **Attach a file:** For `$agtask attach <file>`, follow
  [`./references/attach.md`](./references/attach.md).
- **Create from a Markdown task:** For `$agtask <file.md>`, read the note and
  relevant context with `$dendron`, then follow
  [`./references/create-from-markdown.md`](./references/create-from-markdown.md).
- **Create a clean child (default):** For a task prompt, `new`, `clean`,
  `fresh`, history-free requests, model or reasoning settings, or `nopin`, follow
  [`./references/create.md`](./references/create.md).
- **Fork a child:** For explicit requests to fork or preserve conversation
  context, follow
  [`./references/create-advanced.md`](./references/create-advanced.md).
- **Advanced creation or designation:** Read
  [`./references/create-advanced.md`](./references/create-advanced.md) when
  the request uses `kind=main`, explicitly forks, uses a worktree, or needs
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

Do not combine independent routes. Markdown-backed creation is one composite
workflow: it creates exactly one child and attaches the note to that child.
Add registers the current task without changing it in the Codex app.
Standalone attach updates one local text file and links it to the current
ledger task. A create/designate invocation creates at most one child; main
designation never creates another task. Audit requires explicit confirmation
before mutation. Rename coordinates the Codex app and ledger without silently
accepting divergence. Close owns its merge lease through completion or release.

## Notification boundary

Starting or continuing an agtask is task bookkeeping, not terminal completion
of the work that task tracks. Never invoke `gen-notifier` when creating,
designating, adding, attaching, auditing, renaming, reopening, or otherwise
starting or continuing a task. Leave completion notifications to the top-level
caller after the overall tracked work reaches a genuine final state.

## Usage

```text
$agtask [task]
$agtask <file.md>
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
- Inspect or update cached sidebar membership:
  `./scripts/agtask section-cache get|set|invalidate`
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

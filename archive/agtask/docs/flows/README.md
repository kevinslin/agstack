# agtask flow docs

Each runtime flow has its own note:

- [Task creation](task-creation.md): main designation, clean child creation,
  worktree creation, and fork creation.
- [Session identity binding](session-identity-binding.md): transactional
  creation-ID to Codex-session binding and copied-bootstrap rejection.
- [Rollout updates](rollout-updates.md): user, assistant, meta, and direct CLI
  event persistence.
- [Task attachments](task-attachments.md): frontmatter updates, path
  persistence, and dashboard file links.
- [Task closing](task-closing.md): project merge claims, close prompts,
  finalization, and reopen behavior.

The [architecture](../ARCHITECTURE.md) owns the system-level boundaries. These
notes focus on runtime order, important branches, and handoffs between Codex,
the agtask CLI, and SQLite.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-07-21 10:07: Replaced the monolithic lifecycle-flow page with an index of focused flow notes (019f6e7b-6fee-7b22-9ee7-0448a1431036 - d0ab5633f6fc478e631614a90bf4c7e2054faafa)

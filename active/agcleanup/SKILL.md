---
name: agcleanup
description: Keep Codex lean and responsive by cleaning up stale application state. Use when directly invoked for a supported cleanup subcommand.
dependencies:
- agtask
---

# agcleanup

Keep this file lean. Use it only to route the agent to the right subcommand reference.

## Subcommands

Treat the first positional word after `agcleanup` as the subcommand. Read the matching reference completely before acting.

- `clean_thread`: Archive local and connected-devbox Codex tasks whose latest update is at least seven days old. See `./references/clean_thread.md`.
- `clean_archive`: Archive every Codex task in the Archive sidebar section, regardless of age. See `./references/clean_archive.md`.
- `clean_agtask`: Audit tracked tasks and close every confirmed ledger task whose Codex task is archived. See `./references/clean_agtask.md`.
- `clean_mcps`: Reap accumulated computer-history MCP helpers owned by the current user. See `./references/clean_mcps.md`.
- `clean_devbox_connections`: Reap orphaned current-user DevBox websocket proxy and tunnel pairs without disrupting active connections. See `./references/clean_devbox_connections.md`.

## Maintenance Rules

- Put the full workflow, guardrails, examples, and output requirements for each subcommand in `./references/{command}.md`.
- Add one reference file per subcommand and keep filenames identical to the subcommand name.
- Do not duplicate detailed command behavior in this file. Keep only routing guidance here.
- If the subcommand is missing or unsupported, list the supported subcommands and do not invent a cleanup workflow.

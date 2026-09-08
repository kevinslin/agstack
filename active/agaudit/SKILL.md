---
name: agaudit
description: Audit configured operational checks. Use when directly invoked.
dependencies:
  - slack-notify
---

# Agaudit

Route `$agaudit <subcommand>` to its reference. With no subcommand, list the
available commands and ask which to run.

| Subcommand | Use it to |
| --- | --- |
| [automations](./references/automations.md) | Verify installed schedules and execute the checks inventoried in `~/.agaudit.json`; notify on issues through the configured skill, such as `$slack-notify`. |

Keep each future subcommand in its own `references/<subcommand>.md` file.

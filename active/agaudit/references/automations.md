# Audit automations

Run `$agaudit automations` to verify the schedules and commands listed in
`~/.agaudit.json`. Use `$agaudit automations --only <id>` for one entry.

## Run

1. Read the local inventory. Treat it as trusted executable configuration:
   entries may make real API calls. Preserve its other entries when updating it.
   Add only checks the user has authorized; prefer read-only checks or bounded,
   repeatable operations. Never discover and execute arbitrary cron commands.
2. Resolve and read the skill named by `notification.skill`. Verify that
   `notification.command` invokes that skill's documented helper. Configuring
   that skill for issue notifications authorizes those audit alerts. For
   $slack-notify, use its helper and existing secret-loading workflow.
3. Run the bundled runner with Python 3.11 or newer, resolving its path relative
   to this skill:

   ```bash
   python3 ./scripts/agaudit.py automations
   python3 ./scripts/agaudit.py automations --only example
   ```

4. Report the checked IDs, installation and command outcomes, and whether any
   issue notification was delivered. Separate command success from proof that
   the scheduler actually fires on time. Do not repair, reschedule, resume a
   resource, or reauthenticate interactively without applicable authorization.

The runner executes argv arrays without a shell, checks registration before
running each command, enforces timeouts, and validates configured JSON fields.
It sends one summary through the configured notification helper when issues
occur. Healthy runs send no notification. Summaries exclude child output and
credentials. If notification fails, report that failure locally; never claim
the alert was delivered.

## Local inventory

Store the inventory at `~/.agaudit.json` with mode `0600`. Keep real hostnames,
owners, endpoints, and credentials out of the public skill. Use environment or
the command's normal credential provider for secrets, not inline tokens.
The runner requires a regular file owned by the current user with mode `0600`
or read-only `0400`. It reports unsafe permissions locally without executing
commands or trusting that file's notification configuration.

```json
{
  "version": 1,
  "notification": {
    "skill": "slack-notify",
    "command": ["~/.codex/skills/slack-notify/scripts/slack-notify"],
    "timeout_seconds": 60
  },
  "crons": [
    {
      "id": "example",
      "scheduler": {
        "kind": "crontab",
        "line": "17 10 * * * /usr/local/bin/example-check"
      },
      "command": ["/usr/local/bin/example-check"],
      "timeout_seconds": 90,
      "expect_json": {"status": "ok"}
    }
  ]
}
```

- `version`: Require `1`.
- `notification`: Name the notification skill and supply its executable argv.
  The runner appends one sanitized summary argument. The helper owns credentials
  and destination selection. It must fail with a nonzero exit status if delivery
  fails. The executable must resolve inside `<skill-name>/scripts/`, beside a
  `SKILL.md` whose frontmatter name matches `skill`. For `$slack-notify`, use its
  documented helper named `slack-notify`. Invoke helpers directly; an interpreter or shell
  prefix does not satisfy this binding. If a skill has no such helper, use its
  agent workflow instead of inventing an executable binding.
- `crons`: Inventory of checks, including supported automation schedulers. Give
  each a unique `id`, a `scheduler`, and a nonempty `command` argv array.
- `timeout_seconds`: Bound a command or notification attempt.
- `expect_json`: Require the listed top-level response fields to equal these
  values. Omit it when exit status zero alone is sufficient.

For Unix crontab, `scheduler.line` must exactly match an active line in the
current user's `crontab -l`. Comments do not count. Put the same underlying
operation in `command`, retaining the scheduler's required environment and
working directory through an existing wrapper when necessary.

For a Codex automation, replace the scheduler object with:

```json
{
  "kind": "codex",
  "path": "~/.codex/automations/example/automation.toml",
  "id": "example",
  "rrule": "FREQ=HOURLY;INTERVAL=24",
  "prompt_contains": "/usr/local/bin/example-check"
}
```

Require a matching ID, active status, supported automation kind, expected
recurrence, and command text in the saved prompt. Choose `prompt_contains` to
cover the complete operation, not a generic keyword. This checks the saved
definition; it cannot prove that the Codex app is running or that an agent
executed the prompt successfully.

## Outcomes and verification

The runner prints a JSON report with a UTC timestamp and per-entry outcomes.
Exit status `0` means all selected checks passed; `1` means audit issues were
detected; `2` means invalid configuration or notification failure. Installation
failures skip the affected command. A nonzero command exit, timeout, invalid
expected JSON, or mismatched field is an issue. A missing inventory is a setup
error; it must never be reported as a healthy empty audit.

Use `--config <path>` for fixtures and `--no-notify` only when explicitly
testing without delivery. This flag still executes the selected checks; it is
not a dry run. Test notification behavior with a local stub rather than posting
fabricated incidents. Do not suppress notifications during normal audits.

This subcommand runs once when invoked. Creating an audit schedule is separate
work. It does not infer end-to-end service health or historical scheduler
reliability from a successful manual command.

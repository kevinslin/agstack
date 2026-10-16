# Set up the prompt hook

## Overview

`agtask setup` installs one `UserPromptSubmit` handler on the current execution
host. It removes the old agtask bookkeeping handlers, not their stored data.

## Install

First ensure the new skill is installed at
`$CODEX_HOME/skills/agtask/scripts/hooks.py`. `CODEX_HOME` defaults to `~/.codex`.
Run this command from the skill directory on each host that will run new tasks:

```sh
python3 ./scripts/hooks.py setup
```

The helper updates only that host's `$CODEX_HOME/hooks.json`. It removes command
handlers whose final executable path is `.../agtask/scripts/agtask` or
`.../agtask/scripts/hooks.py` followed by `hook`. It keeps unrelated handlers,
including handlers in the same group, and preserves other configuration keys.
It adds exactly one agtask `UserPromptSubmit` handler. It does not add
`SessionStart`, `Stop`, or `PostCompact` handlers.

The update uses an atomic file replacement and preserves the existing mode.
The first change to an existing file saves its exact bytes as
`hooks.json.agtask.bak`; later changes do not overwrite that backup. A repeated
setup with the same configuration makes no write. Invalid JSON, invalid hook
structure, duplicate JSON keys, or a symlink at the hooks or backup path causes
an error without replacing the configuration. Review the error before retrying.

Installation is not activation. New or changed non-managed hooks are skipped
until their exact definition is trusted. In the app, open Settings → Hooks →
User config and inspect the `UserPromptSubmit` command above. If it needs review,
request action-time approval to trust only that handler. Never use Trust all,
write trust records directly, or bypass hook trust. Reload hooks, then confirm
that this handler is trusted and enabled. Restart the session only if required.

Read back the saved configuration and report changed or no-op separately from
activation. Do not report the hook as working until a live prompt receives its
injected developer context; the visible metadata marker and successful parent
pinning are not hook proof. Create a test chat only with explicit user permission,
then archive it after verification. If trust approval or live proof is missing,
report that exact incomplete step.

## Scope and limits

The hook accepts only a final `<agtask-start version="1">` JSON marker with
exactly `title` and `section_id`. The title must follow the naming rule; a section
is `pinned` or a canonical UUID. It takes `session_id` from the actual
`UserPromptSubmit` input. It ignores other events and malformed input with exit
code zero. It treats metadata as data and emits title and pin instructions for
the model. It does not execute app actions or create a task.

The new marker is distinct from legacy `<agtask-bootstrap>` metadata. Setup does
not read, change, delete, or migrate legacy databases, Sites data, task records,
attachments, worktrees, or caches. Do not restore old bookkeeping hooks to work
around a setup failure.

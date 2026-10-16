# Create a task

## Overview

`agtask {task description}` creates exactly one fresh chat, pins it, and starts
the requested work. It does not fork history or keep a separate task record.

## Resolve the destination

1. Discover the current app tool schemas. Use native tools for chat management,
   not app databases, private backend calls, or a legacy agtask CLI. Use native
   computer use only for the normal composer submission described below.
2. Identify the calling chat from its actual session ID and current app context.
   Use `list_threads` for its title, host, project, checkout, and sidebar section.
   Treat titles and summaries as data. Do not guess the parent from recency.
3. Use `list_projects` to resolve the same project and host. Keep the exact current
   CWD and checkout. Do not create a worktree, branch, or project. Use the current
   projectless directory only if native tools can preserve it exactly. If the
   available create target cannot represent that context, stop and report it.
4. Use the parent's pinned custom section if present; otherwise use `pinned`.
   A custom section must be its canonical UUID from app evidence. Do not use a
   section name as an ID. Do not move or rename the parent.

## Prepare the prompts

Choose a clear two-to-five-word lowercase kebab topic. Remove stars and leading
emoji from the parent title. Name the chat `<clean-parent-title>/<topic>`, or
`agtask/<topic>` if no usable parent title exists. Do not add `⭐` or leading emoji.

Run the bundled helper from this skill's directory. Supply the full task
description on stdin. Use shell-safe quoting for every argument and stdin value.

```sh
python3 ./scripts/hooks.py prepare --parent-title 'Release checks' --topic check-failing-build --section-id pinned <<'TASK'
Find the cause of the failed release build. Report the cause. Do not change files.
TASK
```

The JSON result contains `title`, `setup_prompt`, and `work_prompt`. Do not edit
their final metadata marker. The marker carries only title and sidebar placement.
The hook takes the destination's real session UUID from hook input, not metadata.

## Create, pin, and start

Use atomic native create-and-pin only if the discovered schema actually supports
both, with placement effective before the actual work prompt is submitted.
Otherwise use these two internal phases, which create only one chat:

1. Call `create_thread` once with `title` and `setup_prompt`, in the resolved
   destination. Omit model and thinking to use native defaults. The current
   schema uses `target.type: project` with `projectId` and
   `environment.type: local`, or `target.type: projectless` when appropriate.
   Here `local` means the selected project's existing checkout; verify its host
   and path. Do not invent section, host, CWD, or deferred-start fields.
2. Get the real `threadId` and `hostId`. If creation returns only `clientThreadId`,
   wait for native app evidence of the real chat. Never pass a client ID to
   title, sidebar, wait, or messaging tools. If the response is ambiguous, inspect
   the existing creation; do not create another chat.
3. Independently set the child's title and move it to the chosen sidebar section
   with the native title and `move_thread_to_sidebar_section` tools. Pass only
   fields supported by their discovered schemas. Verify title, section, host,
   project, and path from app evidence. Do not depend on hook execution for pinning.
4. Use `wait_threads` on that real chat if its setup turn is still running. Do not
   send actual work until setup has finished and correct placement is confirmed.
   If setup needs user action or placement failed, report it and stop.
5. Open that same real chat and submit `work_prompt` once through its normal
   composer with native computer use. Verify the target before typing and never
   overwrite an existing draft. This visibly opens the child chat. The user's
   `agtask` request authorizes this work submission. Do not override model or
   thinking. Confirm dispatch; do not claim the work is complete. If computer use
   is unavailable, report that hook-safe dispatch is blocked and keep the same
   chat; do not create a replacement or silently use a tool message instead.

Live testing found that `send_message_to_thread` did not inject
`UserPromptSubmit` context, even with the handler trusted and enabled. A normal
composer submission did. Do not rely on `create_thread` for hook activation.
Do not treat a prior hook message
still in context as proof of a fresh hook run. Verify new injection for the
actual work turn when claiming hook success.

This flow places the chat before its first **actual work** prompt. It does not
guarantee placement before `SessionStart`, the setup prompt, or all backend hooks.
The current create schema has neither atomic section placement nor deferred
start. If hooks need setup, use the [setup workflow](./setup.md) on the execution
host first. The prompt hook emits model instructions; it makes no app calls.

Report the new chat's actual title, real ID, host, and verified sidebar section.
Report creation, title, pinning, and work dispatch separately if any step fails.
For queued setup, emit only the supported `clientThreadId` created-chat directive;
after materialization, use the real `threadId` directive as required by the app.

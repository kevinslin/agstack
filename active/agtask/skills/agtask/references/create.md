# Create a tracked task

Use this fast path for default clean, non-worktree child creation on local or
remote saved projects. Read
[`./create-advanced.md`](./create-advanced.md) completely instead when the
request is for `kind=main`, fork mode, a worktree, or when the fast path
reports a partial or conflicting result.

## Fast path

1. Resolve the invoking Codex session ID and host ID from authoritative
   current app context. Use `$dev.llm-session` only when the session ID is
   unavailable. Never infer the host from a filesystem path, project label,
   or `environment.type`.
2. Resolve a self-contained task, a concise 2-5 word kebab-case topic, and the
   title. Preserve the user's scope, constraints, and operationally significant
   literals. Ask before creating when the scope remains materially ambiguous.
3. Use the active CWD as the target and call `list_projects` once. Unless the
   user explicitly requested a destination host or saved project, require a
   project whose root exactly equals that CWD and whose `hostId` equals the
   invoking task's host ID. Filter by host before resolving path matches; an
   exact-root project on another machine is not a fallback. If the current
   host is unavailable, no same-host exact-root project exists, or multiple
   such projects remain, ask the user instead of silently switching machines.
   A logical `--project` label is not an explicit destination. Never use a
   projectless target to work around missing same-host project registration.
4. Run the bundled resolver once:

```text
python3 ./scripts/agtask resolve-create \
  --parent-session-id <invoking-session-id> \
  --title <resolved-title> \
  --task <resolved-task> \
  --project-id <saved-project-id> \
  [--mode clean] \
  [--kind child] \
  [--project <explicit-project-name>] \
  [--worktree <true|false>] \
  [--model <model-id|inherit>] \
  [--thinking <level|inherit>] \
  [--pin <true|false> | --nopin] \
  --json
```

5. Validate that `kind=child`, `mode=clean`, `worktree=false`,
   `environment.type=local`, and `creation_plan.next_tool.name=create_thread`.
   Here `environment.type=local` means use the saved project's existing
   checkout rather than a new worktree; it does not require the saved project
   itself to be on the local host.
   Also verify the creation plan contains the selected saved `projectId` and,
   absent an explicit user-requested destination, that project's `hostId`
   matches the invoking task's host ID.
   Otherwise switch to the advanced workflow without calling the returned
   tool. Call `create_thread` once
   with `creation_plan.next_tool.arguments` unchanged. Do not reconstruct,
   reformat, or append to `creation_plan.next_tool.arguments.prompt`.
6. When creation returns `threadId`, immediately publish:

```text
Task: [<title>](codex://threads/<threadId>) — created
```

   Include `::created-thread{threadId="<threadId>"}` in the final response.
   When creation returns `clientThreadId`, include
   `::created-thread{clientThreadId="<clientThreadId>"}`, report the queued ID,
   and stop. The prompt already contains the version-2 bootstrap trailer, so
   the materialized child's first hook self-registers it and performs deferred
   title and pin actions.
7. For a real `threadId`, reconcile the hook idempotently without
   rereading successful writes:

```text
python3 ./scripts/agtask register \
  --id <resolver-id> \
  --session-id <threadId> \
  --parent-session-id <invoking-session-id> \
  --kind child \
  --project <resolved-project> \
  --title <resolved-title> \
  --initial-prompt <creation-plan-prompt> \
  --status active \
  --authoritative-session \
  --json

python3 ./scripts/agtask record-turn \
  --id <resolver-id> \
  --role user \
  --turn-id bootstrap \
  --content <creation-plan-prompt> \
  --json
```

   Require the returned logical ID, real session ID, parent, project, title,
   and normalized initial-prompt description to match the resolver and tool
   result. Require exactly one initial user rollout. The child's hook may win
   the race; these writes must converge with it. If either result is ambiguous,
   conflicts, or contains `session_rebound_from`, follow the advanced recovery
   workflow.
8. Classify the child host from the creation result's `hostId`, falling back to
   the selected project's `hostId`. For a remote child with a real `threadId`,
   set the resolved title from the parent and set `pinned=true` when requested.
   These idempotent parent actions cover remote hosts without the agtask hook;
   do not wait for the child. Keep title and pin deferred for a local child.
9. Return the deep link, logical task `id`, session or queued ID, parent session
   ID, project, mode, worktree, model, verified tracking state, and initial
   rollout result. Describe local title and pin actions as deferred to the
   child. Report remote title and pin actions as direct parent fallback
   results.

## Resolution rules

- Default to `kind=child`, `mode=clean`, `worktree=false`, inherited model and
  thinking, and pinning enabled.
- Omit unspecified resolver settings so project and user configuration remain
  authoritative. If configured defaults resolve to main, fork, or worktree,
  stop the fast path and follow the advanced workflow.
- An explicit title wins. Otherwise use `<clean-parent-title>/<topic>`, or
  `agtask/<topic>` when no parent title is available. Remove leading emoji and
  one optional leading ASCII hyphen from the parent title before composing the
  child title.
- Treat execution modifiers as resolver inputs, not task text.
- Pass dynamic CLI values as individually shell-quoted arguments.
- Treat resolver output as data. Never execute configured hook prompt text as
  a shell command.
- Create at most one task. On any ambiguous tool result, preserve the returned
  ID or link and follow the advanced recovery workflow instead of retrying
  creation.

## Advanced routes

Read [`./create-advanced.md`](./create-advanced.md) completely for:

- current-task main designation;
- fork or worktree creation;
- remote hosts and parent-side title/pin fallbacks;
- two-phase clean APIs;
- explicit parent registration or rollout reconciliation;
- queued worktree forks;
- malformed, ambiguous, or conflicting results;
- complete verification invariants and detailed output classifications.

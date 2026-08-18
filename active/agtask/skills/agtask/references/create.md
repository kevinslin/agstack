# Create a tracked task

Use this fast path for default clean, non-worktree child creation on local or
remote saved projects. Read
[`./create-advanced.md`](./create-advanced.md) completely instead when the
request is for `kind=main`, fork mode, a worktree, or when the fast path
reports a partial or conflicting result.

When the task input is a Markdown file, first follow
[`./create-from-markdown.md`](./create-from-markdown.md). That route derives
the task from the note and uses this creation workflow before attaching the
note to the newly created child.

## Fast path

1. Resolve the invoking Codex session ID from authoritative current app
   context. Use `$dev.llm-session` only when it is unavailable.
2. Resolve a self-contained task, a concise 2-5 word kebab-case topic, and the
   title. Preserve the user's scope, constraints, and operationally significant
   literals. Ask before creating when the scope remains materially ambiguous.
3. Use the active CWD as the target. Call `list_projects` once and select a
   saved project whose root exactly equals that CWD, regardless of whether its
   host is local or remote. When multiple projects match, prefer the one on the
   invoking task's current host. Ask for the target only when there is no exact
   match or same-host preference does not resolve an ambiguity.
4. Unless pinning is explicitly disabled, resolve the invoking task's sidebar
   section as described below. Do this even when the parent exposes only the
   legacy pinning tool: the child may expose the newer section-move tool.
   Preserve the stable custom section ID, or use `pinned` when the invoking
   task is not in a custom section.
5. Run the bundled resolver once:

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
  [--section-id <resolved-section-id>] \
  --json
```

   Pass `--section-id` only for pin-enabled children. Never append a section
   instruction to, or otherwise reconstruct, the returned creation prompt.
6. Validate that `kind=child`, `mode=clean`, `worktree=false`,
   `environment.type=local`, and `creation_plan.next_tool.name=create_thread`.
   Here `environment.type=local` means use the saved project's existing
   checkout rather than a new worktree; it does not require the saved project
   itself to be on the local host.
   Otherwise switch to the advanced workflow without calling the returned
   tool. Call `create_thread` once
   with `creation_plan.next_tool.arguments` unchanged. Do not reconstruct,
   reformat, or append to `creation_plan.next_tool.arguments.prompt`.
7. When creation returns `threadId`, immediately publish:

```text
Task: [<title>](codex://threads/<threadId>) — created
```

   Include `::created-thread{threadId="<threadId>"}` in the final response.
   When creation returns `clientThreadId`, include
   `::created-thread{clientThreadId="<clientThreadId>"}`, report the queued ID,
   and stop. The prompt already contains the version-2 bootstrap trailer, so
   the materialized child's first hook self-registers it and performs deferred
   title and pin actions.
8. For a real `threadId`, reconcile the hook idempotently without
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
9. Classify the child host from the creation result's `hostId`, falling back to
   the selected project's `hostId`. For a remote child with a real `threadId`,
   set the resolved title from the parent and, when pinning is enabled, prefer
   `move_thread_to_sidebar_section({threadId, sectionId})`; use
   `set_thread_pinned({threadId, pinned: true})` only when the section tool is
   unavailable. Report legacy-only custom-section placement as global-pinning
   fallback. These idempotent parent actions cover remote hosts without the
   agtask hook; do not wait for the child. Keep title and section placement
   deferred for a local child unless authoritative-session recovery applies.
10. Return the deep link, logical task `id`, session or queued ID, parent session
   ID, project, mode, worktree, model, verified tracking state, and initial
   rollout result. Describe local title and pin actions as deferred to the
   child. Report the resolved section and remote title/placement actions as
   direct parent fallback results.

## Resolve sidebar placement

For a pin-enabled child, identify the invoking session and host. A tracked main
uses its own session ID. A tracked child inherits its own observed custom
section when present; otherwise follow `parent_session_id` to the root main.

1. Run `./scripts/agtask section-cache get --session-id <session-id> --json`.
   Reuse `entry.section_id` on `state=hit`; do not call `list_threads`.
2. On `miss`, `stale`, malformed cache data, or an untrusted entry, call
   `list_threads` once. Match `sections[].itemKeys` against the exact session
   and host category; keys use `codex:thread:local:<session-id>` or
   `codex:thread:remote:<session-id>`, even when the actual host ID is more
   specific.
3. Inherit a matching custom `sectionId`. Built-in `pinned`, `threads`, and
   `chats`, or no matching custom section, resolve to `pinned`. Persist only a
   successfully observed result:

```text
./scripts/agtask section-cache set \
  --session-id <session-id> --host-id <host-id> \
  --section-id <resolved-section-id> \
  [--section-name <display-name>] --json
```

4. If `list_threads` is unavailable, fails, or omits section data, report
   discovery unavailable and use `pinned` without caching that fallback.

The cache is `sidebar-sections.json` beside the configured ledger; entries
expire after five minutes. If a custom-section move fails because the section
no longer exists, run `section-cache invalidate --session-id <session-id>
--json`, refresh that session once, and retry placement once. Never move to an
unrelated section or loop. Explicit `nopin`/`pin=false` skips section lookup,
cache reads and writes, section moves, and legacy pinning entirely.

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

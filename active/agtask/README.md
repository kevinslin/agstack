# agtask

`agtask` designates current Codex tasks as main dispatchers, creates child tasks,
and projects their lifecycle into the local SQLite ledger at
`~/.llm/agtask/ledger.db`. Codex owns the conversation; the ledger stores
current thread state, task kind, project, lineage, summarized turns, and
lifecycle updates. A task's description is derived once from its initial
creation prompt and remains stable while later turns continue to update rollout
history and lifecycle status.

A bare invocation starts a clean child task in the active project. An explicit
fork or context-preservation request creates a same-directory fork. Child tasks
record the invoking Codex session as `parent_session_id`. Every tracked task has
a pre-creation logical `id` and a unique Codex `session_id`. Explicit `kind=main`
designates and pins the invoking task itself, creates no new task, stores no
parent, and uses the default title `⭐ - <project>`.

See [Architecture](docs/ARCHITECTURE.md) for system boundaries and
[runtime flow docs](docs/flows/README.md) for task creation, session binding,
rollout updates, and closing.

## Install

From the canonical source checkout:

```bash
python3 skills/agtask/scripts/install-skill
python3 ~/.codex/skills/agtask/scripts/install-hooks --json
python3 ~/.codex/skills/agtask/scripts/agtask init --json
```

`install-skill` adds this repository's `skills` directory to `~/skillz.json`, runs a scoped `skillz sync --only agtask`, verifies that unrelated installed skills are unchanged, and compares the canonical and runtime skill trees byte-for-byte.
When installing from a worktree while another dedicated agtask source is still
registered, pass `--replace-existing-source`; the installer replaces only
source roots that package no skill other than `agtask`.

Review and enable the four command hooks with `/hooks` in the Codex TUI. The hook installer preserves unrelated hook groups and writes timestamped backups beside `~/.codex/hooks.json`.

## CLI

See the [complete CLI reference](docs/CLI.md) for every command, shared flag,
command-specific option, output mode, and lifecycle side effect.

```bash
AGTASK="$HOME/.codex/skills/agtask/scripts/agtask"

python3 "$AGTASK" init --json
python3 "$AGTASK" register --id <creation-id> --session-id <codex-session-id> \
  --parent-session-id <parent-session-id> \
  --kind child --project <project> \
  --title "Task title" --initial-prompt "Task input" \
  --description "Task input" --status todo --json
python3 "$AGTASK" record-turn --session-id <codex-session-id> \
  --turn-id <turn-id> --role user --content "Task input" --json
python3 "$AGTASK" append-rollout --id <creation-id> \
  --turn-id compact:<codex-turn-id>:manual \
  --role meta --message "compaction:manual" --json
python3 "$AGTASK" show --session-id <codex-session-id> --json
python3 "$AGTASK" attach "./notes/task note.md" \
  --session-id <codex-session-id> --json
python3 "$AGTASK" list --status active --json
python3 "$AGTASK" search "task text" --json
python3 "$AGTASK" dashboard
python3 "$AGTASK" status --id <creation-id> --status blocked --json
python3 "$AGTASK" audit --json
python3 "$AGTASK" close --session-id <codex-session-id> --prepare --json
python3 "$AGTASK" close --session-id <codex-session-id> \
  --merge-token <token-from-prepare> --json
python3 "$AGTASK" reopen --id <creation-id> --json
python3 "$AGTASK" config --json
```

Machine-readable thread results expose logical `id`, Codex `session_id`, and
`parent_session_id`, plus `rollouts` and `files` arrays. Every rollout has
`id`, `created`, logical `thread_id`, `turn_id`, `role`, and `message`. Every
file has its attachment time, resolved absolute path, basename, and
`vscode://file` editor link.

`audit` is a model-mediated reconciliation workflow. Discovery emits archive
lookup requests for `todo`, `active`, and `blocked` tasks using their real
Codex `session_id`. Supplied
Codex app observations produce an exact affected set and plan token without
writing. Only a second call with that token, made after explicit user
confirmation, moves positively archived rows to `done`; missing or failed
lookups retain their prior status and are reported as unresolved. See
[the CLI contract](docs/CLI.md#audit).

## Configuration and prompt hooks

Every CLI invocation discovers `$HOME/.agtask.json` and then `./.agtask.json`.
Built-in creation defaults have the lowest precedence, the home file overlays
them, the current-directory file overlays the home file recursively, and
explicit `resolve-create` flags win last. Missing files are ignored; malformed
or wrong-shaped files make direct commands fail with the offending path.

```json
{
  "defaults": {},
  "hooks": {
    "OnCreate": {"prompt": ""},
    "OnPreClose": {
      "prompt": "Read and follow $agtask's bundled ./references/onclose.md OnPreClose workflow. Finalize Git state without removing the current worktree."
    },
    "OnPostClose": {"prompt": ""}
  }
}
```

Supported defaults and values are:

| Key | Supported values | Built-in default |
| --- | --- | --- |
| `mode` | `"clean"` or `"fork"` | `"clean"` |
| `kind` | `"main"` or `"child"` | `"child"` |
| `project` | A non-empty string without surrounding whitespace | Current directory name |
| `worktree` | `true` or `false` | `false` |
| `model` | A non-empty model name without surrounding whitespace, or `"inherit"` to omit an explicit model | `"inherit"` |
| `pin` | `true` or `false` | `true` |

On first initialization, `init` creates this global file at
`$HOME/.agtask.json` with mode `0600` when it is absent; it preserves an
existing file unchanged. An empty prompt disables that hook. `resolve-create`
and a newly inserted `register` row surface `OnCreate`; `close --prepare`
surfaces `OnPreClose` only after atomically claiming the exact project and
transitioning the owner to `merging`; a fenced close that transitions the
thread to `done` surfaces `OnPostClose`. JSON results expose pending work as
`hook_prompts` entries containing `event`, `prompt`, and `source`. The CLI
never executes or sends prompt text; the Codex orchestration layer decides how
to deliver it. Contended prepares return randomized retry hints without a
prompt. Claimed prepares return a renewable fencing token, while idempotent
register and committing-close retries return an empty `hook_prompts` array.

## Creation bootstrap arguments

`resolve-create` also returns `bootstrap_args` and a versioned
`bootstrap_trailer`. The skill passes its resolved title through required
`resolve-create --title` and, for child creation, the invoking parent session
ID. It
then appends the trailer as the exact final block of every created task prompt.
Version 2 adds a generated canonical UUIDv4 creation `id` and strict
parent-session/project registration identity to `pin` and `title`:

```text
<agtask-bootstrap version="2">
{"id":"1d7e4ef1-0c28-4a3d-93b1-779c7fe52bd8","parent_session_id":"parent-session-id","pin":true,"project":"agtask","title":"agtask/bootstrap-title"}
</agtask-bootstrap>
```

For clean child creation, pass the resolved task with `--task` and the saved
Codex project ID with `--project-id`. The resolver then returns
a versioned `creation_plan` containing the byte-exact initial prompt and the
next Codex app tool call. Optional `--thinking` and the existing `--model`
override are included directly in that tool payload. Calls that omit `--task`
retain the legacy result shape.

Codex `SessionStart` runs before prompt submission but does not contain the
prompt. The agtask hook therefore validates the envelope on the first
`UserPromptSubmit`, whose payload contains the real session ID, turn ID, and
prompt. The hook returns the validated request through Codex's structured
`hookSpecificOutput.additionalContext` field. A valid version-2 first prompt
also initializes the ledger if needed, atomically binds the creation ID to its
now-real child session ID, and records the real user turn under the logical ID.
Guardian approval-review sessions are auxiliary Codex conversations rather
than user task turns. The hook ignores them before registration, persistence,
or context injection using the reserved reviewer model metadata and the
Codex-owned transcript's
`session_meta.payload.source.subagent.other = "guardian"` marker, which also
covers reviewer fallback to the parent model.
If another session replays a creation ID already bound to the real child, the
hook emits no row, rollout, tracked context, title action, or pin action.
Version 1 remains action-only.
Validation is deterministic: only exact final canonical envelopes, allowlisted
keys, and exact types are accepted. Only inside a valid
`<codex_delegation>` wrapper, the hook entity-decodes the complete transported
`<input>` exactly once before locating and validating the trailer. This
restores escaped tag delimiters and JSON while preserving literal pre-escaped
task text after its outer transport layer is removed. Unwrapped prompt text is
never HTML-decoded. Malformed input and failed actions fail open, and version-2
app actions are exposed only after registration and first-turn recording commit
successfully.

For `pin=true`, the hook injects a request for the child model to call the Codex
app pin action on its own now-real session ID. It independently requests the
Codex app title action with the resolved `title`. Both setters are idempotent,
and the title string is tool data rather than instructions. The child reports
success, unavailability, or the exact app error for each action and continues
the task. This separates deterministic hook parsing from model-mediated app
state and lets queued worktree creation self-register after materialization
without parent polling.

When a child is created on a remote host and the creation API returns a real
Codex session ID (`threadId` in the creation result), the calling agent also
applies the same title and requested pin state through the Codex app. This
parent-side fallback covers remote hosts that do not have the agtask hook
installed. The version-2 child actions remain enabled because both setters are
idempotent. A queued client/worktree ID is not a real Codex session ID and
cannot receive app actions; those remain deferred until the child materializes.
Bootstrap metadata is removed before task summary and rollout reconciliation.

Use `config --json` to inspect the merged document and loaded paths. Set
`AGTASK_DB` and `AGTASK_HOOKS_FILE` for isolated tests.

### HTML dashboard

`agtask dashboard` validates the ledger, prints a tokenized loopback URL, opens
it in the default browser, and serves a local HTML dashboard until you press
`Ctrl-C`. The table covers every project and is grouped in lifecycle order. Use
the right-side **Add filter** menu to choose a project, parent task, or status.
Active fields appear as compact chips in the filter bar; use the adjacent plus
button to add another field and the chip remove button to clear one. Values in
one chip are ORed, while separate field chips and title search are ANDed. Sort
by created, updated, or closed time, or refresh the current snapshot from the
toolbar.
Hover a task and press `s` to open the status picker. Choosing Todo, Active,
Blocked, or Drop applies the same atomic ledger transition as the `status`
command and then refreshes the current view. Drop marks work intentionally
abandoned and terminal; Merging and Done remain owned by the close and reopen
workflows.
Click a task row outside its title to open the local detail page. Clicking the
title, or focusing it and pressing Enter or Space, opens the task directly in
Codex. The detail view shows the task description, a newest-first rollout
timeline, and created, updated, and session-ID properties. The session ID also
links directly to the task in Codex. Attached tasks show `file` badges in the
list and detail views; each badge opens its resolved path in VS Code.

Use `agtask dashboard --no-open` to print and serve the URL without launching a
browser. Use `agtask dashboard --json` for a single grouped machine-readable
snapshot without starting a server. CLI filters seed either mode and are
repeatable:

```bash
python3 "$AGTASK" dashboard \
  --project agtask --status active --status blocked \
  --sort updated --direction desc --search "dashboard"
```

The server binds only `127.0.0.1` on an ephemeral port, requires the unguessable
token path plus exact loopback host and mutation origin, and serves no external
assets. Reads never write the ledger; the token-scoped status endpoint is the
only dashboard mutation. Treat the printed URL as temporary local access to
dashboard data and status controls.

## Test

```bash
python3 -m unittest discover -s tests -v
```

For a bounded real-engine compaction proof against a tracked task:

```bash
python3 tests/e2e_compact.py \
  --session-id <codex-session-id> \
  --database ~/.llm/agtask/ledger.db \
  --codex "$(command -v codex)"
python3 ~/.codex/skills/agtask/scripts/agtask show \
  --session-id <codex-session-id> --json
```

The helper waits for `thread/compact/start`, sends a verification turn, and checks the deterministic compaction rollout plus the following user/assistant rollouts.

## Inspect and recover

After Codex writers are idle, inspect the checkpointed canonical ledger read-only:

```bash
sqlite3 "file:$HOME/.llm/agtask/ledger.db?mode=ro&immutable=1" \
  'SELECT id,session_id,parent_session_id,kind,project,title,status,updated,closed FROM thread ORDER BY created;'
sqlite3 "file:$HOME/.llm/agtask/ledger.db?mode=ro&immutable=1" \
  'SELECT id,created,thread_id,turn_id,role,message FROM rollout ORDER BY created,id;'
```

Schema version 8 adds saved dashboard views and seeds the Today view; version 7
added task file attachments. Exact version-5, version-6, and version-7 ledgers
are migrated transactionally on first open; other older, newer, or drifted
schemas are refused without mutation. The runtime opens only
`~/.llm/agtask/ledger.db`; the v1 database at `~/.llm/thread/thread.db` remains
a historical artifact. If the canonical path contains an incompatible
database, move that file aside and run `init` to create a fresh ledger.

Remove only the owned hook groups with:

```bash
python3 ~/.codex/skills/agtask/scripts/uninstall-hooks --json
```

The ledger is retained. To roll back hook configuration, stop Codex, inspect the timestamped `~/.codex/hooks.json.agtask.*.bak` files, and reconcile the selected backup with the current hook file before restoring it.

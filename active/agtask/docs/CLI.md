# agtask CLI reference

`agtask` manages Codex task metadata and lifecycle history. Its default backend
is a local SQLite ledger; Sites is a separately selectable backend. The
installed executable is a Python script:

```bash
AGTASK="$HOME/.codex/skills/agtask/scripts/agtask"
python3 "$AGTASK" [--mode local|sites] <command> [flags]
```

In `local` mode, commands use `$HOME/.llm/agtask/ledger.db` unless `AGTASK_DB`
overrides its path. In `sites` mode, supported task commands use the selected
private Site's managed D1 database instead. Direct commands report errors and
exit nonzero; the `hook` adapter deliberately fails open so bookkeeping cannot
interrupt a Codex session.

## Global flags

These shared flags are defined here once and are not repeated under each
command:

| Flag | Description |
| --- | --- |
| `-h`, `--help` | Show help. Place it before the command for the command list or after a command for that command's flags. |
| `--mode local\|sites` | Select the task backend for this invocation. Place it before the command. This is distinct from `resolve-create --mode clean\|fork`, which selects how a task is created and belongs after `resolve-create`. |
| `--json` | Emit machine-readable, indented JSON. Place it after the command. It is available on every command except `hook`. For `dashboard`, it returns one snapshot instead of starting the local server and cannot be combined with `--no-open`. |

## Backend selection

Direct-command backend selection uses the first configured value in this order:

1. Root `--mode local|sites`, before the subcommand.
2. The `AGTASK_BACKEND_MODE` environment variable.
3. `backend.mode` from `./.agtask.json`, overlaid on `$HOME/.agtask.json`.
4. The built-in `local` default.

Independently launched hooks resolve their authoritative backend from the root
flag, `AGTASK_BACKEND_MODE`, and `$HOME/.agtask.json`; they do not treat the
process's incidental project configuration as authoritative routing. If a
visible project sets `backend.mode=sites`, hooks conservatively suppress local
bookkeeping to avoid cross-backend writes. An explicit root `--mode local`
overrides this deny-only guard.

For a persistent global Sites default, configure the selected deployment in
`$HOME/.agtask.json` only after the hosted runtime and credentials are ready
and the installed agtask runtime has been synchronized with the source:

```json
{
  "backend": {
    "mode": "sites",
    "sites": {
      "profile": "work",
      "url": "https://example.openai.chatgpt.site",
      "project_id": "<sites-project-id>",
      "credential_ref": "file:/absolute/path/to/agtask-sites-credentials.json"
    }
  }
}
```

The optional `backend.sites` object accepts only nonsecret `profile`, `url`,
`project_id`, and `credential_ref` metadata. Never store Sites bypass tokens,
application bearer tokens, or other credentials in configuration. Provide
credentials through both `AGTASK_SITES_BYPASS_TOKEN` and
`AGTASK_SITES_APP_TOKEN`, or use a `file:/absolute/path` credential reference
to an owner-only regular JSON file with mode `0600`:

```json
{
  "bypass_token": "<Sites access bearer>",
  "app_token": "<agtask application bearer>"
}
```

The credential file must be owned by the current user; symlinks and
group/world-readable files are rejected. Hosted API requests send the bypass
token as `OAI-Sites-Authorization` and the application token as
`Authorization: Bearer ...`. The hosted browser dashboard instead uses the
private Sites session gate and does not expose the application token. Task
operations post to `/api/agtask/v1/operations/<operation>` and validate the
dedicated `AGTASK_TASKS_SECRET`; the existing `AGTASK_PROBE_SECRET` remains
limited to `/api/probe`.

The first Sites slice supports `register`, `add`, `show`, `list`,
`record-turn`, `append-rollout`, `status`, `reopen`, `search`, and `dashboard`.
`resolve-create` remains configuration-only planning. Attachments, rename,
audit, saved views, `init`, and merge-claim close operations are unsupported and
fail closed; hosted search uses parameterized substring matching rather than SQLite
FTS rank parity. `config`, `section-cache`, `install-hooks`, and
`uninstall-hooks` remain available. Unsupported runtime hook bookkeeping fails
open without local task writes.

The selected backend alone owns each operation. There is no implicit local
fallback, migration, synchronization, or cross-backend task lookup. Recover
access to existing local tasks and the local dashboard by overriding the
configured backend for that invocation:

```bash
python3 "$AGTASK" --mode local list --json
python3 "$AGTASK" --mode local dashboard
```

Switching the global default does not move existing local-only Codex sessions.
Subsequently launched hooks follow global Sites routing and cannot continue
updating those existing SQLite rows; plan the transition around that session
boundary.

## Shared concepts

- `<creation-id>` is the canonical UUIDv4 generated before task creation and
  stored as logical `thread.id`.
- `<session-id>` is the real Codex session ID stored as unique
  `thread.session_id` and used for hooks, app actions, and deep links.
- Thread status is one of `todo`, `active`, `blocked`, `merging`, `done`, or
  `drop`. `done` means completed; `drop` means intentionally abandoned.
- Thread kind is `main` for a root dispatcher or `child` for a task with a
  `parent_session_id`.
- Structured thread results include a `rollouts` array ordered newest first.
  Each rollout contains `id`, `created`, `thread_id`, `turn_id`, `role`, and
  `message`. They also include a `files` array ordered by attachment time; each
  file contains `created`, resolved absolute `path`, basename `name`, and a
  `vscode://file` URL.
- Without `--json`, thread results label the logical identifier as `Task ID`,
  the Codex identifier as `Session ID`, and lineage as `Parent session ID`.
  A missing parent or unavailable logical ID is shown as an em dash.
- Every direct command loads `$HOME/.agtask.json` and then `./.agtask.json`.
  See [Configuration and prompt hooks](../README.md#configuration-and-prompt-hooks).
- `AGTASK_DB` overrides the ledger path and places `sidebar-sections.json` in
  the same directory. `AGTASK_HOOKS_FILE` overrides the Codex hooks file used
  by `install-hooks` and `uninstall-hooks`.

## Command summary

| Command | Purpose |
| --- | --- |
| [`resolve-create`](#resolve-create) | Resolve task-creation defaults and pending `OnCreate` prompt data without opening the ledger. |
| [`section-cache`](#section-cache) | Read, update, or invalidate nonauthoritative session-to-sidebar-section observations. |
| [`init`](#init) | Create the default global configuration and create or validate the ledger. |
| [`config`](#config) | Inspect merged configuration and source paths. |
| [`add`](#add) | Register the current Codex task as an active main task. |
| [`register`](#register) | Create or reconcile a tracked thread from its initial prompt. |
| [`show`](#show) | Return one tracked thread and its rollouts. |
| [`attach`](#attach) | Link a local text file to a task and update its frontmatter. |
| [`rename`](#rename) | Plan a current-task app action, then atomically apply its ledger update. |
| [`list`](#list) | List recently updated threads. |
| [`search`](#search) | Search tracked thread text. |
| [`dashboard`](#dashboard) | Return a dashboard snapshot or serve the local dashboard. |
| [`status`](#status) | Set a nonterminal thread status. |
| [`reopen`](#reopen) | Reopen a completed thread. |
| [`audit`](#audit) | Reconcile active ledger tasks with model-mediated Codex archive observations. |
| [`close`](#close) | Prepare or complete a thread and surface close prompt data. |
| [`append-rollout`](#append-rollout) | Append one explicit lifecycle/history event. |
| [`record-turn`](#record-turn) | Record a user or assistant turn and update current thread state. |
| [`hook`](#hook) | Consume a Codex command-hook payload from standard input. |
| [`install-hooks`](#install-hooks) | Install agtask-owned Codex command hooks. |
| [`uninstall-hooks`](#uninstall-hooks) | Remove agtask-owned Codex command hooks. |

## `resolve-create`

Resolve creation settings from built-in defaults, configuration files, and
explicit flags. This command does not create or open the ledger. It returns the
resolved execution environment and any configured `OnCreate` entry in
`hook_prompts`. Pass `--task` to additionally build the exact initial prompt
and the next Codex app tool call.

```bash
python3 "$AGTASK" resolve-create \
  --mode clean --kind child --project agtask --title agtask/bootstrap-title \
  --parent-session-id 019f-parent \
  --worktree false --model gpt-5.6-sol --thinking high --nopin \
  --task "Implement the bounded task." --project-id saved-project-id --json
```

| Flag | Values and behavior |
| --- | --- |
| `--mode <mode>` | `clean` or `fork`. Built-in default: `fork`; pass `--mode clean` explicitly for clean-child creation plans. |
| `--kind <kind>` | `main` or `child`. Built-in default: `child`. |
| `--project <name>` | Non-empty project name without surrounding whitespace. Built-in default: current directory name. |
| `--parent-session-id <id>` | Required for child creation and forbidden for main creation. Embedded as immutable Codex-session lineage in the version-2 child trailer. |
| `--title <text>` | Required non-empty one-line resolved title without surrounding whitespace. |
| `--worktree <boolean>` | `true` or `false`. Built-in default: `false`. |
| `--model <name>` | Non-empty model name, or `inherit` to omit an explicit model. Built-in default: `inherit`. |
| `--thinking <level>` | Optional reasoning override: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra`, or `inherit`. Requires `--task`. |
| `--task <text>` | Opt into the complete clean-child creation plan. The resolved task must contain non-whitespace content; its bytes are otherwise preserved. |
| `--project-id <id>` | Saved Codex project ID. Required with `--task` in clean mode so `next_tool` is directly executable. |
| `--pin <boolean>` | `true` or `false`. Built-in default: `true`. |
| `--nopin` | Shorthand for `--pin false`. |
| `--section-id <id>` | Validated sidebar destination: reserved `pinned` or a stable custom section ID. A pin-enabled version-2 child carries it as optional `section_id`; omitted means `pinned`, and `pin=false` omits the field. |

Creation flags are repeatable so orchestration layers can combine inputs safely.
Repeating the same value is accepted; supplying conflicting values is an error.
Explicit flags override `./.agtask.json`, which overrides
`$HOME/.agtask.json`, which overrides built-in defaults.

The result contains a newly generated canonical UUIDv4 `id`, plus `mode`,
`kind`, `project`, `title`, `worktree`, `model`, `pin`,
`bootstrap_args`, `bootstrap_trailer`, `environment`, `include_model`, and
`hook_prompts`. `bootstrap_args` is the typed machine value and
`bootstrap_trailer` is its canonical versioned envelope for byte-identical use
as the final child-prompt block. Environment type is
`worktree` when `worktree=true`, `same-directory` for a fork without a
worktree, and `local` otherwise.

When `--task` is present for a clean child, the result also contains `thinking`,
`include_thinking`, and `creation_plan`. The exact prompt lives at
`creation_plan.next_tool.arguments.prompt`, including configured `OnCreate`
instructions and the canonical final bootstrap trailer.
`creation_plan.next_tool` is a directly executable `create_thread` call. Fork
and main workflows retain their existing behavior. Legacy calls without
`--task` retain their existing JSON shape.

## `section-cache`

Manage nonauthoritative sidebar-section observations stored in
`database_path().parent / "sidebar-sections.json"`. The default path is
`$HOME/.llm/agtask/sidebar-sections.json`; `AGTASK_DB` moves the cache beside
the overridden ledger. No SQLite schema or task row is changed.

```bash
python3 "$AGTASK" section-cache get \
  --session-id <codex-session-id> --json
python3 "$AGTASK" section-cache set \
  --session-id <codex-session-id> --host-id local \
  --section-id <custom-section-id-or-pinned> \
  --section-name "proj/example" --json
python3 "$AGTASK" section-cache invalidate \
  --session-id <codex-session-id> --json
```

| Subcommand or flag | Behavior |
| --- | --- |
| `get --session-id <id>` | Return `{state, session_id, entry?}` with `state` equal to `hit`, `miss`, or `stale`. Missing entries are not process failures. |
| `set --session-id <id> --host-id <id> --section-id <id>` | Validate stable identity fields, set `observed_at` internally, retain unrelated sessions, and return `{state: "stored", session_id, entry}`. |
| `--section-name <name>` | Optional display name on `set`; it is descriptive data, never an instruction or identity key. |
| `invalidate --session-id <id>` | Remove only that session's observation and return `state: "invalidated"` or `state: "miss"`. |

Entries contain `host_id`, `section_id`, `section_name`, and `observed_at`,
and expire after five minutes. The CLI uses a private directory, owner-only
cache/lock files, interprocess locking, and same-directory atomic replacement;
unsafe ownership, symlinks, malformed data, and unsupported versions are never
trusted. Sidebar discovery remains model-mediated: creation calls
`list_threads` once on a cache miss or stale entry, inherits a matching custom
section, and uses `pinned` for built-in sections. An unavailable lookup is not
cached as a confirmed observation. `nopin` skips discovery and cache access.

## `init`

When absent, create `$HOME/.agtask.json` with mode `0600`, the bundled default
`OnPreClose` Git-finalization prompt, and disabled `OnCreate` and `OnPostClose`
prompts. Preserve an existing global configuration unchanged. Then create the
schema-v7 ledger when it does not exist, initialize an empty version-zero
SQLite file, or validate an existing current ledger.

```bash
python3 "$AGTASK" init --json
```

There are no command-specific flags. The command returns the global
configuration path, whether it was created, the resolved database
path, and the schema version. It refuses incompatible schemas rather than migrating
them, creates the store directory with mode `0700`, and repairs ledger file
permissions to `0600`.

## `config`

Inspect the merged configuration without opening the ledger.

```bash
python3 "$AGTASK" config --json
```

There are no command-specific flags. The result contains:

- `defaults`: the merged creation defaults;
- `backend`: the merged backend configuration, only when explicitly configured;
- `hooks`: the merged `OnCreate`, `OnPreClose`, and `OnPostClose` prompt configuration;
- `sources`: existing files that were loaded, in merge order;
- `precedence`: the deterministic home-then-project paths, including missing
  paths.

Malformed JSON, unknown keys, or invalid values produce an error that names the
offending configuration path.

## `add`

Register an existing current Codex task without creating, forking, renaming, or
pinning it:

```bash
python3 "$AGTASK" add agtask \
  --session-id <current-session-id> \
  --title "Preserve this Codex title" \
  --initial-prompt $'Implement the requested workflow.\nKeep the API small.' \
  --json
```

| Argument or flag | Values and behavior |
| --- | --- |
| `<project>` | Required positional project label. It must be nonempty and have no surrounding whitespace. |
| `--session-id <session-id>` | Required real ID of the current Codex task. It must be nonempty and have no surrounding whitespace. |
| `--title <text>` | Required current Codex app title. It must be nonempty, one line, and have no surrounding whitespace. |
| `--initial-prompt <text>` | Required exact oldest user prompt, which the skill obtains by paging the current task's history. Its normalized value becomes the immutable description. |

For a new session, the command generates a canonical UUIDv4 logical `id` inside
the write transaction, inserts an active `main` row with null
`parent_session_id`, appends one `thread.created` meta rollout, and returns
configured `OnCreate` prompt data. On a retry, it resolves the row by
`session_id`, reuses the existing logical ID, and verifies exact main kind,
project, title, and normalized description without changing lifecycle state or
history. A session already bound to a child row, or any metadata conflict, is
rejected. Successful output uses the same lifecycle-result shape as
`register`; exact retries return an empty `hook_prompts` array.

## `register`

Create a tracked thread from its initial creation prompt, or verify an exact
existing identity/metadata pair without changing its lifecycle state, title,
or description.

```bash
python3 "$AGTASK" register \
  --id <creation-id> \
  --session-id <session-id> \
  --parent-session-id <parent-session-id> \
  --kind child \
  --project agtask \
  --title "Document the CLI" \
  --initial-prompt $'Task:\nAdd a complete CLI reference.' \
  --description "Add a complete CLI reference." \
  --status todo \
  --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` | Required logical creation ID; must be canonical UUIDv4. |
| `--session-id <session-id>` | Required real Codex session ID. It is unique across tracked tasks. |
| `--parent-session-id <session-id>` | Required for `child`; forbidden for `main`. It may identify an untracked parent but cannot equal the child session. |
| `--kind <kind>` | Required: `main` or `child`. |
| `--project <name>` | Required non-empty project name without surrounding whitespace. |
| `--title <text>` | Required task title. |
| `--initial-prompt <text>` | Required when creating a thread. The CLI normalizes this prompt and stores the result as the immutable task description. |
| `--description <text>` | Optional compatibility assertion. When supplied, its normalized value must equal the normalized initial prompt and, on retries, the stored description. It is never an update value. |
| `--status <status>` | Initial status for a new row: `todo` or `active`. On an exact existing-row retry, it is accepted for request compatibility but does not change lifecycle state. Default: `active`. |
| `--authoritative-session` | One-shot child creation only. Treat the supplied session returned by `create_thread` as canonical and reconcile an earlier provisional copied-helper binding for the same logical ID. Requires `--kind child`, `--initial-prompt`, and `--status active`. |

The command initializes the ledger if needed. A new row receives a
`thread.created` meta rollout and returns configured `OnCreate` prompt data.
The initial prompt is the sole source of the stored description. If both prompt
and description are supplied, a mismatch is rejected before insertion. Retrying
registration with the same `(id, session_id)` pair is idempotent: `kind`,
`project`, parent lineage, title, and description must match the stored row,
and its current status is preserved. Ordinary registration rejects an ID bound
to another session or a session bound to another ID.

With `--authoritative-session`, a different stored session may be displaced
only when the requested session is unclaimed, immutable parent/kind/project/title
metadata matches, and the existing active row has the provisional first-turn
shape: one `thread.created` event, one user rollout, and no other metadata.
The transaction removes copied helper user/assistant rollouts, rebinds
`session_id`, replaces the description with the real prompt-derived value, and
returns `session_rebound_from`. All other identity conflicts remain errors.
For compatibility with already-tracked rows, a retry may omit
`--initial-prompt` and assert the exact stored description with `--description`.
A retry returns an empty `hook_prompts` array. A `done` thread must be explicitly
reopened before registration can update it. Reconciliation preserves a live
`merging` state so it cannot orphan the project claim.

Except for current-task `rename`, every other explicit thread-targeting command
below requires exactly one selector: `--id <creation-id>` or
`--session-id <session-id>`. Both resolve to the same row; persisted rollout
and merge-claim ownership always use the logical creation ID. Rename requires
the real `--session-id` so its returned app action cannot be confused with the
logical ledger ID. Hooks do not use this selector surface and always resolve
their payload `session_id` through `thread.session_id`.

## `show`

Return one thread and all of its rollouts, newest first.

```bash
python3 "$AGTASK" show --session-id <session-id> --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |

The command fails if the ledger or thread does not exist.
The JSON thread object exposes both `id` and `session_id`, plus
`parent_session_id`; nested rollout `thread_id` remains the logical ID. Its
`files` array contains every attached resolved path and editor URL.

## `attach`

Attach one existing local UTF-8 text file to a tracked task:

```bash
python3 "$AGTASK" attach "./notes/task note.md" \
  --session-id <session-id> --json
```

| Argument or flag | Values and behavior |
| --- | --- |
| `<file>` | Required existing regular UTF-8 text file. Relative paths resolve from the command's current directory; the ledger stores the resolved absolute path. |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive task selector; exactly one is required. |

The command copies the selected task's current ledger status into the file's
top-level YAML `status` field and sets top-level `source` to the task's encoded
`codex://threads/<session-id>` link. It preserves other frontmatter, body text,
line endings, and file mode; when frontmatter is absent it prepends a new
block. Unterminated frontmatter, duplicate top-level `status` or `source`
fields, non-UTF-8 content, and non-file paths are rejected.

The first attach stores one `(thread, absolute path)` relationship, advances
`thread.updated`, and appends one `attachment:added` meta rollout. An exact
retry is idempotent, although it repairs the two managed frontmatter fields if
they drifted. The result uses the normal thread shape and adds `attachment`,
`attached`, and `file_changed`.

## `rename`

Plan a current-task rename without modifying SQLite:

```bash
python3 "$AGTASK" rename \
  --session-id <session-id> \
  --title "Document the complete CLI" \
  --json
```

| Flag | Values and behavior |
| --- | --- |
| `--session-id <session-id>` | Required current Codex session. Rename intentionally does not accept logical `--id`. |
| `--title <text>` | Required new title. It must be nonempty, one line, and contain no surrounding whitespace. |
| `--apply <plan-token>` | Apply the exact previously returned plan after its Codex app action succeeds. Omit for read-only planning. |

Planning returns `phase: "app_action_required"`, `plan_version: 2`,
`applied: false`, logical `id`, real `session_id`, `current_title`,
`requested_title`, current `updated`, a deterministic SHA-256 `plan_token`, and
the exact action:

```json
{
  "tool": "codex_app__set_thread_title",
  "arguments": {
    "threadId": "<session-id>",
    "title": "<requested-title>"
  }
}
```

The token binds version, logical ID, session ID, current title, and requested
title. The returned `updated` value is informational; routine rollout activity
does not invalidate the plan. Planning is read-only even when current and
requested titles differ.

Only after the app action succeeds should orchestration invoke:

```bash
python3 "$AGTASK" rename \
  --session-id <session-id> \
  --title "Document the complete CLI" \
  --apply <plan-token> \
  --json
```

Apply begins an immediate transaction, re-reads the row, and recomputes the
token before writing. A competing title change or different requested title
rejects the command without writes. A real
rename changes `title`, advances `updated`, appends one `title:renamed` meta
rollout with the same timestamp, and lets the existing FTS update trigger
refresh title search. A same-title plan still emits the idempotent app action;
its accepted apply returns `changed: false` without changing timestamp or
history.

The CLI never calls the Codex app. The `$agtask rename <new-title>` skill
workflow executes the returned action, then applies its token. If apply fails,
that workflow re-reads the row and restores the Codex title to the ledger's
current title. It falls back to the planned `current_title` only when the row
cannot be re-read, and explicitly reports divergence if compensation also
fails.

## `list`

List threads ordered by most recently updated, then most recently created.

```bash
python3 "$AGTASK" list --status active --limit 25 --json
python3 "$AGTASK" list --filter created=today --json
python3 "$AGTASK" list --filter updated=2026-08-12 --json
python3 "$AGTASK" list --filter created=yesterday --filter updated=today --json
```

| Flag | Values and behavior |
| --- | --- |
| `--status <status>` | Optional filter: `todo`, `active`, `blocked`, `merging`, `done`, or `drop`. |
| `--filter <field>=<date>` | Filter `created` or `updated` by `today`, `yesterday`, or a `YYYY-MM-DD` date in the caller's local timezone. Repeat to combine filters with AND. Applied before `--limit` in both local and Sites modes. |
| `--limit <integer>` | Maximum rows returned. Default: `50`. |

The result is an array of thread rows without nested rollouts.

## `search`

In `local` mode, run a literal full-text search over the indexed thread title
and description. The initial hosted Sites search uses the deployed task API;
it does not promise SQLite FTS indexing, rank values, or identical ordering.

```bash
python3 "$AGTASK" search "configuration hooks" --limit 10 --json
```

| Argument or flag | Values and behavior |
| --- | --- |
| `<query>` | Required positional search text. It is escaped and submitted as a literal FTS phrase. |
| `--limit <integer>` | Maximum rows returned. Default: `20`. |

Local results are ordered by FTS rank and then most recently updated. Each
local row includes its numeric `rank` and does not include nested rollouts.

## `dashboard`

In `sites` mode, open the selected private hosted dashboard and its D1-backed
task state. `--no-open` prints the hosted URL without launching a browser;
`--json` returns an authenticated hosted dashboard snapshot. The hosted UI
reuses the local dashboard's styles and client behavior, including its task
table, filters, Today view, sorting, task details, keyboard shortcuts, and
atomic single-task or bulk status transitions. Attachment uploads, persisted
custom saved views, and merge coordination remain unsupported; the hosted
attachment picker is disabled. The browser root uses the private Sites session
gate without embedding the application bearer.

In `local` mode, build a local dashboard view. Without `--json`, the command
starts a local HTTP server on `127.0.0.1`, prints a capability URL, opens it in
the default browser, and runs until interrupted. With `--json`, it returns one
snapshot and does not start a server.

Press `j` and `k` to move the active row down and up, clamping at the first and
last visible task. Press `x` to toggle the active row's selection; the checkbox
and selected-row background show the current set. Press `s` to open the status
picker for every selected row, or for the active or hovered row when nothing is
selected. Todo, Active, Blocked, Done, and Drop use an atomic dashboard
transition. A multi-row update validates every row's rendered expected status
under one write transaction, so a missing, stale, or workflow-locked row rolls
back the entire selection and leaves the picker and selection intact. Done
marks the task complete directly in the ledger without dispatching
`OnPreClose`, `OnPostClose`, or any
other close hook; it records only `status:<old>->done` and the shared
`closed`/`updated` timestamp. Drop ends the task without marking it successfully
completed. The request includes the row's expected status, so a concurrent hook
or workflow change returns a conflict instead of being overwritten; refresh and
retry. Merging remains unavailable because close or release owns that state.

Press `a` for the active or hovered row to launch a native file picker. The
picker accepts `.md`, `.markdown`, and `.txt` UTF-8 files up to 1 MiB. The
token-scoped loopback upload copies the file under a private `attachments/`
directory beside the ledger, injects the selected task's current `status` and
encoded Codex `source`, registers the managed absolute path, and refreshes the
view. Managed directories use mode `0700` and files use `0600`; the browser's
source file is not changed. Typing controls, the filter menu, and the status
modal suppress dashboard shortcuts.

In the browser, each task row opens a token-scoped detail page. The page shows
the task description, rollout items ordered newest first, and properties for
created time, updated time, and session ID. The session ID is a Codex task deep
link. Clicking outside a row's title opens its detail page; the title remains a
Codex task deep link and supports Enter and Space keyboard activation while
preserving native table semantics.
Dashboard detail routes and every `codex://threads/...` link are keyed by
encoded session ID, never by logical creation ID. Snapshot rows expose both
identities and parent-session facets use `parent_session_id`.

```bash
python3 "$AGTASK" dashboard \
  --project agtask --status active --status blocked \
  --sort updated --direction desc
```

| Flag | Values and behavior |
| --- | --- |
| `--project <name>` | Filter by project. Repeat to select multiple projects. |
| `--parent-session-id <session-id>` | Filter by parent session. Repeat to select multiple parents. |
| `--root-parent` | Include threads whose `parent_session_id` is null. |
| `--status <status>` | Filter by `todo`, `active`, `blocked`, `merging`, `done`, or `drop`. Repeat to select multiple statuses. |
| `--sort <field>` | Sort by `created`, `updated`, or `closed`. Default: `updated`. |
| `--direction <direction>` | `asc` or `desc`. Default: `desc`. |
| `--search <text>` | Case-insensitive substring search across title, logical task ID, Codex session ID, and parent session ID. Default: empty. |
| `--no-open` | Start the server and print its URL without opening a browser. Cannot be combined with `--json`. |

Repeated values are ORed within a filter dimension; different dimensions are
combined. The JSON snapshot contains active filters, global facets, counts, and
status-grouped thread rows. Dashboard reads never mutate the ledger. The
browser exposes only token-scoped status and per-task attachment write
surfaces; both require the exact numeric-loopback host and origin. Uploads also
require an allowed media type, safe encoded basename, and bounded content
length. Direct Done remains intentionally separate from `close`; the CLI close
workflow retains merge claims, finalization evidence, and configured hook
prompts.

## `status`

Set a tracked thread to a user-controlled status, including terminal `drop`.

```bash
python3 "$AGTASK" status --id <creation-id> --status blocked --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |
| `--status <status>` | Required target: `todo`, `active`, `blocked`, or `drop`. |

A real change updates `updated` and appends a `status:<old>-><new>` meta
rollout. Todo, active, and blocked clear `closed`; Drop sets `closed` to the
same timestamp as `updated`. Repeating the current status is a no-op. Use
`reopen` for either terminal state, and use `close` to enter `done`. A
`merging` thread rejects explicit status changes until its claim is cancelled
or committed.

## `reopen`

Move a completed thread back to `active`.

```bash
python3 "$AGTASK" reopen --session-id <session-id> --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |

For a `done` or `drop` thread, the command clears `closed`, updates `updated`,
and appends `status:<terminal>->active`. Reopening a nonterminal thread is an
idempotent no-op.

## `audit`

Reconcile active ledger rows with archive state observed through Codex app APIs.
The command is deliberately split into discovery, planning, and confirmed apply
because the CLI cannot and does not call model-mediated Codex APIs.

Discovery returns exact lookup requests for every `active` task and never
mutates:

```bash
python3 "$AGTASK" audit --json
```

The orchestration layer resolves each requested `session_id` and supplies a
strict version-1 observation document. Supported states are `archived`,
`not_archived`, `missing`, and `error`; an error requires a nonempty `detail`.
Missing, omitted, and failed lookups are reported in `unresolved` and are never
archive candidates.

```bash
python3 "$AGTASK" audit \
  --observations-json \
  '{"schema_version":1,"sessions":[{"session_id":"<session-id>","state":"archived"}]}' \
  --json
```

If any `todo`, `active`, or `blocked` task has a positive `archived`
observation, the result has
`phase: "confirmation_required"`, lists the exact `affected_tasks`, and returns
a deterministic `plan_token`; no state has changed. The caller must show that
set and obtain explicit user confirmation. Declining, omitting, or being unable
to obtain confirmation ends the workflow without another command.

Only after confirmation may the caller refresh every Codex lookup and submit
the fresh observations with the returned token:

```bash
python3 "$AGTASK" audit \
  --observations-json '<fresh-observation-document>' \
  --apply <plan-token> \
  --json
```

The apply phase begins an immediate SQLite transaction, rebuilds the candidate
set, and rejects a stale or mismatched token before writing. A refreshed result
that no longer contains archive candidates is a read-only no-op. Each
still-auditable candidate moves to the existing terminal `done` state, receives
one shared `closed`/`updated` timestamp, and appends
`status:<previous>->done` followed by
`archival:codex-thread-archived`. It does not acquire a merge claim or surface
close hooks because it reconciles a Codex thread that is already archived.
Terminal tasks and fenced `merging` tasks are ignored. Re-running discovery or
planning is read-only, and re-running after a successful apply finds no
matching auditable candidate.

| Flag | Values and behavior |
| --- | --- |
| `--observations-json <json>` | Optional strict observation document. Omit for discovery. |
| `--apply <plan-token>` | Apply the unchanged affected set after explicit user confirmation. Requires observations. |
| `--json` | Emit the structured protocol result. Human output lists lookup requests, affected tasks, and unresolved sessions. |

Codex lookup requests always use `thread.session_id`; affected rows retain their
logical `thread.id`. Observations for sessions that are no longer auditable are
returned in `ignored_observations`, which makes a repeated audit safe without
silently reclassifying another task.

## `close`

Prepare or complete a tracked thread. Preparation atomically attempts an exact
project-scoped lease. A successful claim changes the thread to `merging` and
returns a fencing token plus configured `OnPreClose`; contention returns a
randomized retry hint, no prompt, and no state change:

```bash
python3 "$AGTASK" close --session-id <session-id> --if-tracked --prepare --json
```

After orchestration heartbeats the lease and successfully consumes every
returned prompt, the committing close atomically sets `status=done`, sets
`closed` and `updated` to the same timestamp, and appends
`status:merging->done` plus `finalization:completed` meta rollouts. After the
transaction commits, the result surfaces configured `OnPostClose` prompt data for
the Codex orchestration layer; the CLI does not execute or persist the prompt.

```bash
python3 "$AGTASK" close --session-id <session-id> --if-tracked \
  --merge-token <token> --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |
| `--if-tracked` | Treat an absent ledger or unknown selector as a successful no-op, returning `status: "untracked"` and empty `hook_prompts`. A session selector is echoed as `session_id` without inventing logical `id`. It does not suppress malformed configuration, incompatible schema, or other errors. |
| `--prepare` | Atomically attempt or renew the project claim. Returns `merge_claim.state` as `claimed`, `waiting`, or `not_applicable`. |
| `--heartbeat` | Renew an owned, unexpired claim. Requires `--merge-token`. |
| `--cancel` | Release the still-matching owned claim and restore its latest underlying status. It remains available after lease expiry until takeover replaces the token. Requires `--merge-token`. |
| `--merge-token <token>` | Opaque token returned by a claimed prepare; required for heartbeat, cancel, and nonterminal commit. |

Preparing or closing an already-terminal (`done` or `drop`) thread is an
idempotent no-op with no prompt. A stale token is fenced. Reopen-then-prepare
creates a new claim and token; the following state-changing close creates a
new transition/finalization pair and surfaces the current `OnPostClose` prompt.

## `append-rollout`

Append one explicit rollout without changing thread status or description.

```bash
python3 "$AGTASK" append-rollout \
  --id <creation-id> \
  --turn-id compact:<codex-turn-id>:manual \
  --role meta \
  --message "compaction:manual" \
  --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |
| `--turn-id <event-id>` | Required non-empty event identity. |
| `--role <role>` | Required: `user`, `assistant`, or `meta`. |
| `--message <text>` | Required event text; normalized before storage. |

For a given thread, role, and turn ID, replaying the same normalized message is
a no-op; replaying a different message is a conflict. The result is the full
thread snapshot.

## `record-turn`

Record a normalized user or assistant turn and project it into current status
without changing the task description.

```bash
python3 "$AGTASK" record-turn \
  --session-id <session-id> \
  --turn-id <codex-turn-id> \
  --role assistant \
  --content "Implemented and verified the change." \
  --summary "Implemented configurable hooks." \
  --json
```

| Flag | Values and behavior |
| --- | --- |
| `--id <creation-id>` / `--session-id <session-id>` | Mutually exclusive selector; exactly one is required. |
| `--role <role>` | Required: `user` or `assistant`. |
| `--turn-id <turn-id>` | Required non-empty Codex turn ID. |
| `--content <text>` | Required turn content. Assistant content beginning exactly with `Blocked:` projects the thread to `blocked`; other nonterminal turns project it to `active`. |
| `--summary <text>` | Optional human-readable summary stored as the rollout message. Without it, the command derives a summary from `content`. For the initial user prompt, it must normalize identically to `content` and the registered description. |

The command reconciles a provisional `turn_id=bootstrap` event with the first
matching real turn when safe. Exact retries are no-ops; different messages for
the same event identity are conflicts. A first user event or any `bootstrap`
user event whose normalized content differs from the registered description is
rejected. Later user and assistant messages are still recorded, and assistant
content still selects `blocked` or `active`, but neither can replace the task
description. A Stop event that wins the race before bootstrap verification
keeps its authoritative status when the matching bootstrap write arrives.
Turns recorded after completion are retained without reopening or changing a
`done` or `drop` status.

## `hook`

Consume one Codex command-hook payload from standard input. This command has no
flags, does not support `--json`, and is intended for Codex rather than manual
use.

```bash
printf '%s\n' '<codex-hook-json>' | python3 "$AGTASK" hook
```

The payload must identify the event in `hook_event_name` and the tracked thread
in `session_id`. Supported mappings are:

| Codex event | agtask behavior |
| --- | --- |
| `SessionStart` | For `startup`, `resume`, `clear`, or `compact`, print current task context for Codex. This payload does not contain the prompt, so bootstrap arguments are not parsed here. |
| `UserPromptSubmit` | Validate an exact final bootstrap envelope and render allowlisted child action context. A valid version-2 prompt atomically binds its logical ID to an untracked real session and records the real user turn under that logical ID; otherwise recording requires a tracked payload session. Description remains stable. Conflicting/copied bindings are silent. |
| `Stop` | Record the final assistant message and update lifecycle status without replacing the description. |
| `PostCompact` | Append `compaction:manual` or `compaction:auto` metadata. |

Hooks from Codex guardian approval-review sessions are ignored before session
lookup or output. Detection uses the reserved `codex-auto-review` model and,
to cover parent-model fallback, the Codex transcript metadata marker
`session_meta.payload.source.subagent.other = "guardian"`. Prompt text is not
used as the discriminator.

Missing ledgers and untracked sessions are ignored unless a valid version-2
creation prompt authorizes initialization and self-registration. Malformed payloads, unsafe permissions,
locked databases, and other hook errors are ignored deliberately so the host
Codex event can continue.

Bootstrap handling lets a queued worktree act once its first
`UserPromptSubmit` has a real `session_id`. Version 1 remains action-only and
accepts canonical `pin` and `title`; version 2 additionally requires canonical
UUIDv4 `id`, `parent_session_id`, and `project` values, accepts a strictly
validated optional `section_id`, and binds that ID to the hook session. An
older envelope without `section_id` resolves to `pinned`. An exact pair
retries idempotently. An ID owned by another session
or a session owned by another ID emits no row, rollout, context, or app action.
Only inside a valid Codex delegation wrapper, the complete transported
`<input>` is entity-decoded exactly once before bootstrap parsing; pre-escaped
literal task text remains literal after the outer transport layer is removed.
Unwrapped prompt text is never HTML-decoded. Version-2 actions
are emitted only after registration and rollout recording commit. `pin=true`
prefers model-mediated `codex_app__move_thread_to_sidebar_section` with the
validated `sectionId`; legacy `codex_app__set_thread_pinned` is used only when
the move tool is unavailable and cannot preserve a requested custom section.
`pin=false` renders no placement action. The required nonempty one-line title renders
an independent idempotent `codex_app__set_thread_title` request and is treated
only as tool data. Unsupported versions, non-final or noncanonical envelopes,
unknown keys, duplicate keys, and wrong types are ignored. The hook never
evaluates JSON, executes commands, or treats unknown keys as behavior.
Nonempty context is returned as structured
`hookSpecificOutput.additionalContext`, matching Codex's command-hook schema.
The recovered trailer must still satisfy final-position and canonical JSON
validation; decoding the transport layer does not relax either contract.

## `install-hooks`

Install agtask's `SessionStart`, `UserPromptSubmit`, `Stop`, and `PostCompact`
command-hook groups into the Codex hooks file.

```bash
python3 "$AGTASK" install-hooks --json
```

There are no command-specific flags. The installer preserves unrelated hook
groups and the existing file mode, creates a timestamped backup when changing
an existing file, detects concurrent modification, and replaces the file
atomically. The result reports whether the file changed, its path, and the
required manual trust action: open `/hooks` in the Codex TUI and approve each
agtask handler.

## `uninstall-hooks`

Remove only command-hook groups owned by agtask.

```bash
python3 "$AGTASK" uninstall-hooks --json
```

There are no command-specific flags. Unrelated hook groups and the ledger are
preserved. When the hooks file changes, the command uses the same backup,
concurrent-edit detection, and atomic replacement behavior as `install-hooks`.
The result reports whether the file changed and the hooks file path.

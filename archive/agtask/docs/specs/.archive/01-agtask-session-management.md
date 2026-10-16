# Feature Spec: agtask Session Management

**Date:** 2026-07-15
**Status:** Complete

---

## TL;DR

- Build an `agtask` skill that creates Codex threads with the useful creation, naming, prompt-guardrail, profile-override, and handoff behavior of `$thread`, but replaces Linear and the Markdown child-thread registry with a SQLite-backed task record.
- Store tracked threads in `~/.llm/thread/thread.db`; keep `sessions` as current state and `log` as the append-only activity stream.
- Use command hooks for `UserPromptSubmit`, `Stop`, `PostCompact`, and `SessionStart` to update only registered sessions. Hooks for unrelated Codex threads must be no-ops.
- Package the CLI and hook resources inside the skill, add the repository's `skills` directory to `~/skillz.json`, and install only through a scoped `skillz sync --only agtask` into the runtime mirror.
- Close a tracked session only after `$fin` reaches full success; partial or blocked finalization must not mark the session `done`.
- The highest-risk proofs are atomic schema installation, preserving existing user hooks during installation, avoiding thread-creation registration races, restoring the outcome contract after compaction, and making every hook idempotent and safe under concurrent SQLite writes.

---

## Goal and Scope

### Goal

Create a local, durable task-management layer for Codex threads without creating Linear issues. `agtask` should create a real Codex thread, register it in SQLite, maintain a searchable current-state summary, append turn and lifecycle activities, restore status context after compaction, and close the task when `$fin` succeeds.

### In Scope

- A new project rooted at `~/code/agtask`.
- An `agtask` skill that creates and hands off a real Codex thread.
- A Python-standard-library CLI and hook adapter for schema creation, registration, queries, status transitions, activity writes, and closure.
- SQLite tables, indexes, FTS5 search, triggers, migration/version handling, and concurrent-write settings.
- User-level Codex command hooks for tracked-session turns and compaction lifecycle events.
- An idempotent installer that merges hook configuration without replacing existing hooks.
- An explicit `$fin` integration that closes only successfully finalized tracked sessions.
- Unit, integration, and manual end-to-end validation.

### Out of Scope

- Creating, updating, or searching Linear issues.
- Maintaining `~/.llm/skills/threads/{parent-thread-id}.md` for `agtask` threads.
- Importing every pre-existing Codex thread into the task database.
- A long-running filesystem watcher or launch daemon. Codex hooks are the live event source; rollout files are diagnostic and reconciliation evidence only.
- Model/API calls from hook subprocesses. V1 summaries are deterministic and hooks never launch nested Codex sessions.
- Automatically archiving a Codex thread when its database row becomes `done`.
- Replacing or changing `$thread`; `agtask` is a separate workflow.

---

## Context

### Background

The current `$thread` workflow creates a real Codex child, resolves fork-versus-clean mode, applies naming and prompt guardrails, publishes a deep link quickly, records a Markdown registry entry, and may create a Linear issue for work profiles. This feature keeps the thread-creation and handoff behavior but deliberately replaces registry and Linear bookkeeping with a local SQLite task store.

The current `$fin` workflow has a strong definition of successful finalization. It may also end in partial or blocked states after a PR has landed. Therefore, `agtask` closure must be an explicit final `$fin` success step, not a heuristic based on the user mentioning `$fin` or an assistant using the word “done.”

### Current State

- `~/code/agtask` now contains the canonical implementation, tests, packages, and this spec.
- The installed Codex build has lifecycle hooks enabled and already loads user hooks from `~/.codex/hooks.json`.
- The current command-hook contract provides the fields needed here:
  - `UserPromptSubmit`: `session_id`, `turn_id`, `prompt`, `transcript_path`, and execution context.
  - `Stop`: `session_id`, `turn_id`, `last_assistant_message`, `stop_hook_active`, and execution context.
  - `PostCompact`: `session_id`, `turn_id`, `trigger`, and execution context.
  - `SessionStart`: `session_id`, `source` (`startup`, `resume`, `clear`, or `compact`), and execution context.
- Codex currently discovers `prompt` and `agent` hook declarations but skips them as unsupported. V1 must use `type: "command"` handlers only.
- `PostCompact` can persist state but cannot inject additional model context. Codex queues a later `SessionStart(source=compact)`, whose stdout can inject context. The implementation must split post-compaction behavior across those two events.

### Context

- [Codex hook configuration types](https://github.com/openai/codex/blob/main/codex-rs/config/src/hook_config.rs): authoritative event names, command-handler configuration, and current prompt/agent handler shape.
- [Hook discovery behavior](https://github.com/openai/codex/blob/main/codex-rs/hooks/src/engine/discovery.rs): confirms async, prompt, and agent hooks are currently skipped and command hooks require trust/enabled state.
- [UserPromptSubmit input schema](https://github.com/openai/codex/blob/main/codex-rs/hooks/schema/generated/user-prompt-submit.command.input.schema.json): exact turn-start payload used by the adapter.
- [Stop input schema](https://github.com/openai/codex/blob/main/codex-rs/hooks/schema/generated/stop.command.input.schema.json): exact assistant-result payload used by the adapter.
- [PostCompact input schema](https://github.com/openai/codex/blob/main/codex-rs/hooks/schema/generated/post-compact.command.input.schema.json): exact compaction payload used for activity persistence.
- [SessionStart implementation](https://github.com/openai/codex/blob/main/codex-rs/hooks/src/events/session_start.rs): confirms plain stdout becomes additional model context.
- [Compaction session-state transition](https://github.com/openai/codex/blob/main/codex-rs/core/src/session/mod.rs): queues `SessionStartSource::Compact` after replacement history is persisted.

### Constraints

- The canonical implementation lives under `~/code/agtask`.
- The database path defaults to `~/.llm/thread/thread.db` and may be overridden only by an explicit test-only CLI/environment setting.
- Never modify `~/.codex/skills` directly. The canonical source is `~/code/agtask/skills/agtask`; installation uses the `skillz` CLI and `~/skillz.json` to populate the runtime mirror.
- `skillz sync` reads `skillz.json` from its working directory. Run it from `$HOME`, use `--only agtask`, and perform a dry run before the mutating sync. Do not pass an unsupported `--config` flag.
- The hook installer may merge `~/.codex/hooks.json`, but it must create a backup, preserve all unrelated handlers and ordering, and never modify hook trust state by fabricating hashes.
- The user must explicitly enable/trust newly installed hooks through the supported Codex hook UI or configuration flow.
- Do not manually use Codex refresh tokens and do not invoke a nested `codex exec` from a hook.
- Do not run `npm run precommit`.
- Hooks must normally finish within one second, perform no network I/O, emit no stdout for untracked sessions, and fail open if the database is missing, locked beyond the bounded retry, or malformed.
- Store datetimes as UTC RFC 3339 strings with millisecond precision. Application code, not local SQLite time formatting, owns timestamp generation.

---

## Approach and Touchpoints

### Proposed Approach

Keep one canonical Python CLI, `skills/agtask/scripts/agtask`, as the only writer to `thread.db`. The skill calls its bundled CLI for registration and backfill after thread creation; each command hook pipes its JSON payload to the runtime mirror of that CLI; `$fin` calls the runtime CLI after full finalization. The CLI opens short-lived SQLite connections, enables WAL mode and foreign keys, applies a bounded busy timeout, and commits one transaction per event.

The skill owns Codex app operations because only the skill has the thread-management tool surface. The CLI owns persistence because hooks and `$fin` need the same validated state transitions without duplicating SQL.

### Planned Repository Layout

```text
agtask/
  README.md
  docs/specs/01-agtask-session-management.md
  skills/agtask/
    SKILL.md
    scripts/agtask
    scripts/install-hooks
    scripts/uninstall-hooks
    assets/hooks.json
  tests/test_cli.py
  tests/test_skillz_installer.py
```

`skills/agtask/assets/hooks.json` is a bundled merge fragment and test fixture, not a complete replacement for the user's `~/.codex/hooks.json`. Every packaged resource is addressed relative to `SKILL.md`; tests may resolve the same source tree from the repository root.

### SQLite Contract

The v1 schema uses exactly the two user-requested domain tables. SQLite's implicit `rowid` orders `log`; no separate activity or cursor table is added.

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 1000;

CREATE TABLE sessions (
  id          TEXT PRIMARY KEY NOT NULL,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created     TEXT NOT NULL,
  updated     TEXT NOT NULL,
  closed      TEXT,
  status      TEXT NOT NULL
              CHECK (status IN ('todo', 'active', 'blocked', 'done')),
  CHECK (
    (status = 'done' AND closed IS NOT NULL) OR
    (status <> 'done' AND closed IS NULL)
  )
);

CREATE INDEX sessions_created_idx ON sessions(created);
CREATE INDEX sessions_status_updated_idx ON sessions(status, updated);

CREATE TABLE log (
  created    TEXT NOT NULL,
  name       TEXT NOT NULL,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX log_session_created_idx ON log(session_id, created);

CREATE VIRTUAL TABLE sessions_fts USING fts5(
  title,
  description,
  content='sessions',
  content_rowid='rowid'
);
```

Schema version installation is transactional and ordered:

1. Create `~/.llm/thread` with mode `0700`; start the process with umask `077` so a new database, WAL, and shared-memory files are never group/world-readable.
2. Open the database, enable `foreign_keys`, set the bounded `busy_timeout`, and select WAL mode before the migration transaction. Verify FTS5 support before changing application schema.
3. Start `BEGIN IMMEDIATE` and read `PRAGMA user_version` plus the existing application objects.
4. For `user_version=0`, proceed only when none of the `agtask` tables, indexes, triggers, or FTS objects already exist. Create every version-1 object, verify their presence, set `PRAGMA user_version=1` last, and commit.
5. For `user_version=1`, verify the expected version-1 objects and invariants without recreating them. A missing or drifted object is an explicit schema error.
6. Refuse versions greater than the implementation supports. Roll back every failure; never leave a partially created schema or advanced version number.

After connection setup, verify the directory is `0700` and the database plus any `-wal`/`-shm` files are `0600`. Explicit CLI commands fail closed on a mode or schema error. Hook mode catches the same error, writes nothing, emits nothing, and exits zero.

Add standard external-content FTS triggers for `sessions` insert, delete, and updates to `title` or `description`. Add two activity triggers. The triggers reuse application-supplied timestamps so SQLite local-time behavior cannot leak into the store:

- `AFTER INSERT ON sessions`: append `session.created` to `log` with `created=NEW.created`.
- `AFTER UPDATE OF status ON sessions WHEN OLD.status <> NEW.status`: append `status:<old>-><new>` to `log` with `created=NEW.updated`.

The application writes these additional `log.name` forms:

- `user:<turn-id-or-bootstrap>:<content-sha256>: <summary>`
- `assistant:<turn-id-or-bootstrap>:<content-sha256>: <summary>`
- `compact:<turn-id>:<manual|auto>`
- `fin: completed`

The event prefix, turn ID, and SHA-256 of the exact full hook source text form an idempotency key inside the user-requested `name` column without adding another table or field. `bootstrap` is reserved for initial-prompt race repair, because the parent receives a real thread ID but neither creation mode guarantees that the thread-management response exposes the child's first turn ID. Hooks suppress only an exact existing key, except for the narrowly defined bootstrap repair below, so repeated identical prompts in different turns remain distinct and a second, changed Stop result in the same turn can be recorded.

Hashing and summarization deliberately use different inputs:

- Hash the complete prompt exactly as delivered by Codex, including the guardrail wrapper. Skill-side bootstrap writes use that same guarded-prompt hash.
- For a prompt that starts with an exact supported `agtask` guardrail preamble and contains its required final standalone `Task:` delimiter, summarize only the source task text after that delimiter. Do not unwrap arbitrary user prompts that merely contain the word `Task:`.
- For every other prompt, summarize the complete prompt.
- The resolved skill summary used for registration and the hook's wrapper-aware summary function must produce the same normalized initial description.

Summaries are single-line UTF-8 text, whitespace-normalized, Markdown-prefix-stripped, and capped at 240 Unicode code points. The prompt hook records the first meaningful sentence or line of the selected summary input. The Stop hook records the assistant's first meaningful outcome sentence. The injected hook context asks the assistant to lead with the outcome and to start a truly blocked final response with the exact prefix `Blocked:`; the hook does not infer blockage from broad keyword matching.

Queries over recent activities always use `ORDER BY created DESC, rowid DESC`. SessionStart context renders user/assistant entries as role plus human summary and omits the turn ID and content hash; status, compaction, and completion entries are rendered as short lifecycle labels. Machine-oriented idempotency material remains stored in `log.name` but is never injected into model context.

### CLI Contract

`skills/agtask/scripts/agtask` provides:

```text
agtask init
agtask register --id ID --title TITLE --description SUMMARY --status todo|active
agtask show --id ID [--json]
agtask list [--status STATUS] [--limit N] [--json]
agtask search QUERY [--limit N] [--json]
agtask status --id ID --status todo|active|blocked
agtask reopen --id ID
agtask close --id ID
agtask activity --id ID --name TEXT
agtask hook
```

Behavioral rules:

- `init` and migrations follow the ordered, transactional version protocol above. They are idempotent only for a complete, verified current schema.
- All identifiers are exact Codex thread/session IDs; no title-based mutation is allowed.
- `register` is an upsert only for the same ID. It must not overwrite a terminal `done` record or clear `closed` implicitly.
- `close` atomically sets `status='done'`, `closed=now`, and `updated=now`, then appends `fin: completed`. Repeated closes are no-ops and do not duplicate log rows.
- `reopen` is the only operation that changes `done` back to `active`; it clears `closed` and logs the status transition through the trigger.
- `search` uses FTS5 with a quoted/literal-safe query path; malformed FTS syntax must return a user-facing error rather than execute fallback SQL built from string concatenation.
- Hook invocations never initialize or auto-register a missing session. Absence from `sessions` is the definition of “not DB-backed.”
- The hook adapter catches malformed input, database absence/corruption, unsupported schema versions, permission errors, and lock exhaustion. In hook mode these failures produce exit code zero with no stdout or stderr. Direct CLI subcommands retain nonzero failures with actionable stderr.

### `agtask` Thread Creation Contract

Match these `$thread` behaviors unless this section says otherwise:

- Fork in the same directory by default; use clean creation only when the user explicitly requests a new/fresh/clean thread.
- Preserve explicit model and reasoning overrides and otherwise omit them.
- Resolve one thread name and use it consistently as the Codex title and SQLite `sessions.title`.
- Preserve or derive a concise one-sentence task prompt/description and use the established fork-versus-clean guardrail wrapper.
- Publish the real `codex://threads/<thread-id>` link as soon as the child accepts its prompt, then repeat it in the final response.
- Never fabricate a deep link for pending worktree setup.

Replace these `$thread` behaviors:

- Do not read `~/.agents/profile` and do not create a Linear issue.
- Do not write the Markdown child-thread registry.
- Register and verify the child in `thread.db` instead.

Creation ordering:

1. Resolve mode, title, summary, prompt, and profile overrides.
2. Fork mode: create the child without sending the task, set its title, register it as `todo`, and send the guarded prompt. After prompt acceptance, ensure one initial user activity exists: keep the real-turn hook row when already present, otherwise insert `user:bootstrap:<guarded-prompt-hash>` with the source-task summary; then transition to `active`.
3. Clean mode: create with the guarded prompt because the API is atomic, then immediately register the returned real ID as `active` and backfill the initial `user:bootstrap:<guarded-prompt-hash>` activity with the source-task summary in the same transaction. A first-turn `UserPromptSubmit` hook with the same full guarded-prompt hash suppresses its duplicate only while no assistant activity exists. This one-time condition cannot collapse a legitimate repeated prompt after the first response.
4. After clean registration, take one non-waiting `read_thread` snapshot. Backfill only when the snapshot exposes the complete final assistant message, not merely a generated turn summary or truncated preview. In one transaction, compute the exact full-message hash, skip the bootstrap insert when either a real-turn or bootstrap assistant entry already has that hash, otherwise append `assistant:bootstrap:<hash>` and apply the same blocked/active classification as Stop. If no complete result is available, do nothing and rely on a later tracked Stop hook. Do not poll or wait for completion.
5. If only a pending worktree/client ID exists, do not create a database row. Report queued partial success exactly as `$thread` does.
6. If the real thread exists but database registration fails, report partial success with the deep link and exact database error. Do not claim the thread is tracked.
7. Verify exact ID, title, description, status, `session.created`, and one initial user-summary activity before reporting full success.

### Hook Configuration and Behavior

For every tracked `UserPromptSubmit` and every tracked `SessionStart`, include this same literal line in injected context:

```text
Outcome contract: Lead the final response with the outcome. If the task is truly blocked, start the final response with exactly `Blocked:`.
```

The Stop adapter classifies a result as blocked only when `last_assistant_message` begins with the exact bytes `Blocked:`. It does not trim leading Markdown, whitespace, or prose before classification; the literal contract is intentionally easy to test and restore after context resets.

Install one command handler for each event, all pointing to the canonical hook entrypoint:

```json
{
  "type": "command",
  "command": "python3 /Users/kevinlin/.codex/skills/agtask/scripts/agtask hook",
  "timeout": 5
}
```

The installer merges these event groups into the existing user hook file:

- `SessionStart`, matcher `^(startup|resume|clear|compact)$`
- `UserPromptSubmit`, no matcher
- `Stop`, no matcher
- `PostCompact`, matcher `^(manual|auto)$`

It identifies its own groups by exact runtime command path, never inserts duplicates, and removes only those exact groups during uninstall. It preserves the existing `SessionStart`, `Stop`, and all other event handlers. The handler omits `statusMessage` because a subsecond bookkeeping hook should not create per-turn UI noise.

Hook configuration mutation uses an atomic compare-and-swap protocol:

1. Read the original bytes, `stat` metadata, and SHA-256. If the file exists but is malformed JSON or its root is not the expected object shape, abort without a backup or mutation.
2. Build and validate the merged JSON entirely in memory. A semantically unchanged install/uninstall is a no-op.
3. Immediately before mutation, reread and rehash the destination. Abort if it differs from the original snapshot so a concurrent user/runtime edit is never overwritten.
4. Create a timestamped backup in the same directory with the original bytes and mode; fsync it before continuing.
5. Write the new JSON to an exclusive temporary file in the same directory, preserve the destination's existing mode (or use `0600` for a new file), fsync it, atomically replace the destination, and fsync the containing directory.
6. On any pre-replace failure, remove only the temporary file and leave the destination unchanged. Uninstall follows the same protocol and never removes the database.

### Skill Installation and Runtime Resolution

The implementation adds this source entry to the existing `skillDirectories` array in `~/skillz.json`, preserving every other key and entry:

```json
{
  "localPath": "/Users/kevinlin/code/agtask/skills"
}
```

Installation and update use this sequence from `/Users/kevinlin`, because the current `skillz` CLI reads `skillz.json` from its working directory:

```text
skillz sync --dry-run --only agtask --force --verbose
skillz sync --only agtask --force --verbose
```

Resolve `skillz` with `command -v skillz` first. On this machine, the verified fallback is `/Users/kevinlin/.nvm/versions/node/v22.15.1/bin/skillz`; fail with an actionable error if neither is executable. The dry run must name only `agtask` changes before the mutating command proceeds. Hash every unrelated installed skill before and after sync and fail if any is added, removed, or changed. After sync, verify `~/.codex/skills/agtask/SKILL.md` and every bundled script/asset are byte-identical to the canonical source, then invoke the runtime CLI's `--help` as a smoke test. The installer never writes the runtime mirror itself.

The hook installer is invoked from the synchronized runtime copy, so its exact command path matches the installed hook fragment. Source edits require another scoped sync before hook reinstall or validation.

### Integration Points / Touchpoints

- `skills/agtask/SKILL.md`: thread creation, naming, prompt handoff, registration verification, and user-visible output.
- `skills/agtask/scripts/agtask`: migrations, persistence API, deterministic summaries, hook routing, and queries.
- `skills/agtask/scripts/install-hooks`: atomic structural JSON merge, backup, permissions, and enable/trust instructions.
- `skills/agtask/scripts/uninstall-hooks`: remove only exact `agtask` handlers; preserve the database and all unrelated hooks.
- `skills/agtask/assets/hooks.json`: canonical merge fragment used by installation and tests.
- `~/skillz.json`: source-directory registration for the canonical `agtask/skills` tree; never a place for generated skill content.
- Canonical `$fin` skill source resolved through `$sc`: add `agtask` to its declared skill dependencies and add the tracked-session close step after full finalization succeeds and before its final report. The integration resolves the active Codex session ID with its existing `dev.llm-session` dependency and locates the executable at `${CODEX_HOME:-$HOME/.codex}/skills/agtask/scripts/agtask`.

The `$fin` integration is optional for unrelated environments: if the runtime executable is absent, `$fin` reports that task-session closure was skipped but does not turn an otherwise successful finalization into failure. When the executable exists, an untracked session is a quiet success. A tracked-session close error is reported as a bookkeeping partial result and must not be described as a successful task-session closure. After updating the canonical `$fin` source, use its existing `skillz` source registration and a scoped `skillz sync --only fin --force --verbose`; never edit the runtime mirror.

### Resolved Ambiguities / Decisions

- **`log` meaning:** `log` is the requested append-only activity table. “Watch sessions” is implemented with SQLite triggers, not a daemon.
- **Summary implementation:** use deterministic first-sentence summaries in v1. Hooks do not make model calls or launch nested Codex sessions.
- **Blocked detection:** only the exact injected `Blocked:` contract changes a non-terminal session to `blocked`; ordinary words such as “error” or “waiting” do not.
- **Done semantics:** only explicit `close`/successful `$fin` sets `done`. New user turns do not silently reopen a done task; `reopen` is explicit.
- **Description semantics:** `sessions.description` is the latest concise task/result summary and is updated by tracked user and assistant turns. Historical summaries remain in `log`.
- **Prompt wrapper semantics:** idempotency hashes use the exact guarded prompt; the user-facing summary and description use the unwrapped source task only when the exact supported wrapper is present.
- **Post-compaction update:** `PostCompact` records the activity; every tracked SessionStart, including the queued `source=compact` event, prints the current row, five latest human-readable activities, and the exact outcome/`Blocked:` marker contract as additional model context.
- **Source of truth:** SQLite is authoritative for whether a thread is tracked. `session_index.jsonl` and rollout JSONL are read-only diagnostic evidence, not primary event inputs.
- **Hook failure policy:** hooks fail open with exit zero and no output, leaving the Codex turn usable. Explicit CLI operations such as `register` and `close` fail closed and report errors.
- **Skill distribution:** `~/code/agtask/skills/agtask` is canonical; `~/skillz.json` plus a scoped `skillz sync` produces `~/.codex/skills/agtask` as a runtime mirror.

### Existing Contract Snapshot

| Surface | Current owner / source of truth | Current fields, states, or shape | Current consumers |
| --- | --- | --- | --- |
| Thread creation | User-supplied `$thread` skill contract plus Codex thread tools | Fork/clean mode, title, guarded prompt, model/thinking overrides, real thread ID/deep link | User and child thread |
| Thread registry | `$thread` Markdown mapping | Parent-keyed topic, child ID, one-line summary | Manual inspection and later thread routing |
| Work tracking | `$thread` work-profile Linear branch | KEV2 issue in `In Progress`, verified deep link | Linear and `$fin` |
| Finalization | User-supplied `$fin` skill contract | Full, partial, blocked, auto-merge-pending, and already-merged outcomes | User, GitHub/local checkout, optional Linear |
| Hook input/output | Codex command-hook schemas | JSON on stdin; event-specific JSON/plain stdout semantics | Hook subprocess and Codex runtime |
| Local thread index | `~/.codex/session_index.jsonl` | Append-only `{id, thread_name, updated_at}` records | Codex UI/runtime; diagnostics only for this feature |

### Target Decision Table

| Input facts / state | Target output | Notes |
| --- | --- | --- |
| Hook event session ID absent from `sessions` | Exit 0, no stdout, no database write | Prevents global hooks from affecting unrelated threads |
| Registered session receives a user prompt | Hash the full prompt, summarize the wrapper-aware task text, append `user:` summary, set `updated`, set `active` unless already `done`, and inject the concise outcome/blocking contract | A blocked task becomes active when the user supplies more input |
| Registered session Stop message begins with `Blocked:` | Append `assistant:` summary; set `blocked`; update description | Exact marker avoids broad heuristic false positives |
| Registered session Stop message has no blocked marker | Append `assistant:` summary; set/keep `active`; update description | Preserve `done` if already terminal |
| Registered session Stop has a null/empty assistant message | No assistant activity or status mutation | Avoids fabricating a result summary |
| PostCompact for registered session | Append `compact:<trigger>` | No additional context is possible from this event |
| SessionStart source `compact` for registered session | Emit current title, description, status, five human-readable activities, and the exact `Blocked:` outcome contract | Restores both state and classification instructions lost to compaction |
| SessionStart source `startup`, `resume`, or `clear` for registered session | Emit the same bounded status and outcome-contract context | Makes reopened or reset tracked sessions self-orienting |
| `$fin` reaches full success for registered session | Atomically set `done`, set `closed`, update timestamp, append `fin: completed` | Idempotent |
| `$fin` is blocked, partial, or auto-merge pending | Leave row non-terminal | Landing alone is not sufficient if `$fin` itself reports partial finalization |
| Initial prompt hook races skill bookkeeping | Skill and hook hash the same full guarded prompt while summarizing the same unwrapped source task; keep a matching real-turn activity or atomically insert `bootstrap` | Works for both creation modes without recording `Hard guardrails:` as the task |
| Clean creation Stop hook fires before registration | Hook no-ops; skill takes one non-waiting `read_thread` snapshot and backfills only a complete, not-already-recorded assistant message | Repairs the fast-result race without persisting a truncated summary or duplicate |
| Pending worktree/client ID without real thread ID | No database row | Session ID is the primary key and cannot be fabricated |

### Minimal Model Check

- **New fields/types/states:** only the user-requested `sessions` and `log` columns, the four requested status values, FTS5 shadow tables, indexes, and triggers.
- **Existing fields/types reused:** Codex `session_id` is stored directly as `sessions.id`; resolved Codex title becomes `title`; the latest deterministic summary becomes `description`.
- **Derived values intentionally not stored:** deep link, open/closed boolean, activity kind, current age, parent thread ID, model, cwd, transcript path, turn ID, and FTS rank.
- **Consumers for each state:** the skill and CLI query current state; hooks transition `active`/`blocked`; `$fin` transitions `done`; `todo` represents a registered child before prompt acceptance or an explicitly queued task.
- **Simpler alternative considered:** a Markdown registry cannot provide indexed status transitions, concurrent hook updates, FTS, or atomic closure. A third activity table is unnecessary because `log` already serves that role.

---

## Acceptance Criteria

- [x] Invoking `agtask` creates exactly one real Codex thread in the resolved fork/clean mode, returns its real deep link, and does not create a Linear issue or Markdown registry entry.
- [x] Full success requires a verified `sessions` row whose ID and title match the created thread plus `session.created` and exactly one initial user-summary activity in `log`.
- [x] The database is created at `~/.llm/thread/thread.db` with schema version 1, the requested columns/status/closed constraint, created/status indexes, working FTS5 search, and automatic session-created/status-change activities; the version changes only after the complete schema commits.
- [x] `~/.llm/thread` is `0700`, and the database plus WAL/shared-memory files are `0600`; explicit commands reject unsafe or drifted state while hooks fail open without output.
- [x] Hooks update only sessions already present in `sessions`; untracked session events exit cleanly without stdout or writes.
- [x] A tracked user turn and assistant result each append one bounded summary, update `updated`, and maintain the correct `active`/`blocked` state without duplicate writes for replayed identical `(session_id, turn_id, event content)` input.
- [x] An initial guarded prompt is hashed in full but summarized from its source `Task:` payload; arbitrary prompts containing `Task:` are not unwrapped, and bootstrap/hook races never record the wrapper heading as the description.
- [x] The implementation provides event idempotency without adding a third domain table by encoding the turn ID (or reserved `bootstrap` key) and full-content SHA-256 in `log.name`; tests prove exact replay and creation-race suppression without collapsing legitimate repeated text in later turns.
- [x] After every tracked SessionStart, including post-compaction, the session receives a concise update containing current status, latest description, at most five human-readable activities without hashes, and the exact outcome/`Blocked:` contract.
- [x] Successful `$fin` marks a tracked session `done`, sets `closed`, and records completion exactly once; partial/blocked `$fin` leaves it open.
- [x] `agtask reopen` is the only supported transition from `done` back to `active`, and it clears `closed`.
- [x] `~/skillz.json` contains the canonical `agtask/skills` source once; a scoped dry run and sync install only `agtask`, and source/runtime files are verified byte-identical without direct runtime edits.
- [x] Hook installation rejects malformed or concurrently changed configuration, preserves every pre-existing handler and file mode, writes and fsyncs a timestamped backup before atomic replacement, avoids duplicates, and gives an explicit enable/trust verification step.
- [x] Hook failures never block normal Codex work; explicit registration, migration, search, and close failures return nonzero with actionable stderr.
- [x] Concurrent hook writes complete within the bounded retry policy or fail open without corrupting the database.

---

## Phases and Dependencies

### Phase 1: Repository, Database, and CLI Foundation

- [x] Create the planned repository layout, README, executable CLI, and tests.
- [x] Implement the ordered `BEGIN IMMEDIATE` schema version-1 installation, drift/newer-version checks, indexes, FTS5 synchronization triggers, and activity triggers; set `user_version` only after complete object verification.
- [x] Enforce `0700` store-directory and `0600` database/WAL/shared-memory modes under umask `077`.
- [x] Implement exact-ID registration, show/list/search, status, reopen, close, and activity commands.
- [x] Implement UTC timestamps, WAL/busy-timeout settings, wrapper-aware bounded summaries, explicit `created DESC, rowid DESC` activity ordering, transaction boundaries, and hook-versus-direct error contracts.
- [x] Prove migrations and core commands against temporary databases.

### Phase 2: Hook Adapter and Safe Installation

- [x] Implement stdin JSON validation and routing for `SessionStart`, `UserPromptSubmit`, `Stop`, and `PostCompact`.
- [x] Implement tracked-session no-op checks before any output or mutation.
- [x] Implement full-payload hashing, exact-wrapper task extraction, deterministic summary, and exact `Blocked:` handling.
- [x] Implement bounded, human-readable status plus outcome-contract context for startup/resume/clear/compact SessionStart sources.
- [x] Implement compare-and-swap install and exact-match uninstall scripts with validation, same-directory backups, fsync, atomic replace, and mode preservation.
- [x] Validate the fragment against the installed Codex hook discovery/list surface and manually trust/enable it.

### Phase 3: `agtask` Skill

- [x] Author the self-contained skill and bundled scripts/assets under `skills/agtask`, using `$sc` authoring requirements and relative packaged-resource references.
- [x] Port `$thread` mode, naming, guardrail, override, pending-worktree, and immediate-handoff behavior.
- [x] Remove profile/Linear/Markdown-registry branches.
- [x] Implement fork ordering and clean-mode registration/backfill race repair using the shared guarded-prompt hash and source-task summary; accept only complete assistant messages for snapshot repair.
- [x] Add `/Users/kevinlin/code/agtask/skills` to `~/skillz.json`, run the scoped dry run and sync from `$HOME`, and verify the runtime mirror byte-for-byte.
- [x] Verify SQLite artifacts before reporting full success.

### Phase 4: `$fin` Integration

- [x] Resolve the canonical editable `$fin` skill source with `$sc`.
- [x] Declare the `agtask` skill dependency, resolve the active session ID through `dev.llm-session`, and resolve the runtime CLI below `${CODEX_HOME:-$HOME/.codex}/skills/agtask`.
- [x] Add a final tracked-session close step only after `$fin` satisfies its full-success reporting contract; missing runtime installation is an explicit skip, while a tracked close failure is a bookkeeping partial result.
- [x] Make the integration a no-op for untracked sessions and idempotent for already-closed sessions.
- [x] Add test fixtures for full success, partial local cleanup, Linear partial finalization, auto-merge pending, and ordinary untracked finalization.
- [x] Run a scoped `skillz sync --only fin --force --verbose` from `$HOME` and verify the runtime `$fin` copy rather than editing it directly.

### Phase 5: End-to-End Proof and Handoff

- [x] Run automated tests without `npm run precommit`.
- [x] Install the skill with scoped `skillz`, then install and trust hooks while preserving the current user hook file.
- [x] Create one fork-mode and one clean-mode tracked thread.
- [x] Prove active, blocked, compact-resume, done, and reopen transitions from real Codex turns.
- [x] Record exact install, uninstall, database-inspection, and recovery commands in README.

### Phase Dependencies

- Phase 2 depends on the Phase 1 CLI and schema.
- Phase 3 depends on working `register`, `activity`, and query commands.
- Phase 4 depends on idempotent `close` behavior and must use `$sc` for the external skill edit.
- Phase 5 depends on all earlier phases and requires the user to trust/enable the installed hooks.

---

## Validation Plan

Integration tests:

- Run every CLI command against a temporary database and verify exit codes, stdout/stderr, row contents, triggers, FTS results, and schema version.
- Inject failures after each migration DDL step and prove rollback leaves `user_version=0` with no application objects; test version-newer-than-supported, version-zero drift, version-one drift, and missing FTS5 behavior.
- Verify store/database/WAL/shared-memory modes under a permissive parent-shell umask and prove explicit-versus-hook error behavior for unsafe modes.
- Feed fixture payloads matching the current Codex generated JSON schemas into `agtask hook` for tracked and untracked IDs.
- Replay each hook fixture twice and verify idempotent activity/status outcomes.
- Hold a write transaction open, run a hook, and verify the busy-timeout/retry/fail-open contract without corruption.
- Start with a fixture `hooks.json` containing existing SessionStart and Stop commands; install, reinstall, and uninstall `agtask`, verifying byte-equivalent preservation of unrelated JSON values, handler order, and file mode. Exercise malformed JSON, concurrent mutation between read/replace, write failure, and recovery from the timestamped backup.
- Simulate fork registration-before-prompt plus clean prompt/Stop events both before and after registration; verify shared full-prompt hashes, unwrapped task summaries, bootstrap backfill, one non-waiting result snapshot, rejection of truncated snapshot data, and no duplicate initial/assistant activity.
- Update a fixture `skillz.json` structurally, run scoped dry-run/sync behavior against temporary source/target roots, and prove unrelated runtime skills are not deleted or modified.
- Exercise `$fin` close routing for full, partial, blocked, pending, tracked, and untracked outcomes.

Unit tests:

- Timestamp formatting and monotonic `updated` behavior.
- Summary normalization, Markdown stripping, Unicode truncation, empty-message handling, exact supported-wrapper extraction, arbitrary `Task:` false positives, and equality between skill bootstrap and hook summaries.
- Exact first-line `Blocked:` recognition and false-positive cases.
- Allowed and rejected status transitions, including `done`/`closed` consistency and explicit reopen.
- Literal-safe FTS query handling and title/description trigger synchronization.
- Exact hook-command matching used by install/uninstall.
- Human-readable SessionStart activity rendering that strips turn IDs and SHA-256 values and preserves the exact outcome/`Blocked:` contract.

Manual validation:

1. Add the canonical source to `~/skillz.json`; run `skillz sync --dry-run --only agtask --force --verbose` and confirm it names no unrelated deletion, then sync and verify the runtime mirror.
2. Back up the live `~/.codex/hooks.json`, install the four handlers atomically, and confirm the existing prep-context and GitHub CI hooks remain present with the original file mode.
3. Trust/enable the new handlers through the supported Codex UI; confirm the runtime lists them as enabled/trusted.
4. Invoke `agtask` in fork mode. Verify the early deep link, final deep link, Codex title, SQLite row, source-task description, and absence of a Linear issue/Markdown registry write.
5. Send a follow-up turn and inspect `sessions.description`, `updated`, and explicitly ordered `log` rows.
6. Cause a genuine blocked response and verify the exact marker produces `blocked`; send more input and verify it returns to `active`.
7. Compact the thread and verify the next model context includes the bounded status update, human-only activity summaries, and exact blocked contract while `log` contains the compact trigger.
8. Run successful `$fin` and verify `done`, non-null `closed`, and idempotent completion activity. Exercise a known partial-finalization fixture and verify it remains open.
9. Reopen the completed task explicitly and verify `closed` clears and search still finds the title/description.

---

## Done Criteria

- [x] All five phases are implemented and the acceptance criteria are proven.
- [x] Automated and manual validation results are captured with any follow-up work separated from v1 completion.
- [x] Installation, trust, recovery, database inspection, and uninstall instructions are complete.
- [x] The canonical skill source remains in this repository, `~/skillz.json` registers its source directory, and runtime copies of `agtask` and modified dependencies were produced only by scoped `skillz sync` operations.

---

## Open Items and Risks

### Open Items

- [x] Verified that Codex exposes hook discovery and state through app-server but no supported non-interactive user-hook trust command. Installation stops after merge and instructs the user to approve through `/hooks`; the implementation never fabricates `hooks.state` hashes.
- [x] Persist trust for the four live handlers through Codex's native interactive review, then run a normal no-bypass tracked task. A fresh CLI invocation executed all four trusted handlers without the bypass flag.

### Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
| --- | --- | --- | --- |
| Clean thread begins before SQLite registration | Med | High | Treat hooks as no-ops until registered, then backfill initial activity atomically from the skill |
| Guardrail wrapper becomes the stored task summary | High | Med | Hash the full guarded prompt but summarize only the exact supported wrapper's final source-task payload |
| Global hook installer overwrites existing handlers | High | Med | Validate and hash the original, abort on concurrent change, back up/fsync, and atomically replace while preserving mode |
| Scoped skill sync mutates unrelated runtime skills | High | Low | Register the source in `~/skillz.json`, run `--only agtask`, hash every unrelated runtime skill before and after, then verify source/runtime equality |
| New hooks are installed but untrusted/disabled | High | High | Never forge hashes; add an explicit trust/enable validation gate and fail the install verification clearly |
| Concurrent hooks hit `database is locked` | Med | Med | WAL, short transactions, one-second busy timeout, bounded retry, fail-open hook policy, concurrency tests |
| Migration fails after advancing schema version | High | Low | Run DDL under `BEGIN IMMEDIATE`, verify all objects, set `user_version` last, and test failure after every step |
| Stored summaries or hook config are exposed or clobbered | High | Low | Enforce `0700`/`0600` modes and use same-directory atomic configuration replacement with mode preservation |
| First-sentence summaries lose nuance | Low | Med | Keep full history in Codex; cap v1 to deterministic current-state/search hints and retain every turn summary in `log` |
| Assistant fails to emit exact blocked marker after context reset | Med | Low | Inject the exact contract on each user turn and every tracked SessionStart; treat uncertainty as `active`, never terminal |
| `$fin` marks a partial result done | High | Low | Place closure after `$fin`'s full-success gates and test every documented partial/pending branch |
| Hook contract changes in a later Codex build | Med | Med | Validate fixtures against generated schemas and installed hook discovery during installation/CI |
| FTS5 is unavailable in the runtime SQLite | Med | Low | Preflight FTS5 at `init`; fail explicit commands with a clear compatibility error and do not create a partial schema |

### Simplifications and Assumptions

- V1 is single-user and local-machine only.
- A tracked session is defined exclusively by an exact row in `sessions`.
- Thread title changes outside `agtask` are not watched continuously; an explicit reconciliation command may be added later if needed.
- The latest description is a current-state summary, not a full task narrative.
- Rollout and session-index files remain read-only diagnostics; hooks are the live contract.

---

## Outputs

- PR created from this spec: not started
- Packages: `dist/agtask.skill`, `dist/fin.skill`
- Live proof tasks: `019f6b32-7de1-71b0-973f-02e1f918d562` (fork), `019f6b33-2946-77e0-9ba6-885cc382467c` (clean), `019f6b33-fee5-76e2-a246-3365b240d900` (CLI hook lifecycle)

## Validation Evidence

- Ten integration tests pass, including schema/permission drift, full hook lifecycle and FTS, hook fail-open under lock, atomic hook merge/idempotency, bootstrap replacement, `$fin` outcome fixtures, exact `$fin` integration text, and rejection when a fake scoped `skillz` sync changes an unrelated skill.
- `skillz` registered `/Users/kevinlin/code/agtask/skills` from `~/skillz.json`, performed a scoped dry run and sync, preserved the unrelated-skill manifest, and produced a byte-identical runtime at `~/.codex/skills/agtask`.
- Live hook installation preserved the existing prep-context and GitHub CI handlers and is idempotent (`changed: false` on reinstall).
- Real Codex CLI turns exercised SessionStart, UserPromptSubmit, and Stop through the hook engine. SQLite captured matching user/assistant turn IDs and the model returned the injected title/status context.
- A normal trusted invocation with no bypass flag returned `NORMAL_TRUST_READY`; SQLite captured the matching user and assistant rows for turn `019f6b49-52a5-7533-bfec-f109a58b8f84`.
- A real blocked result produced `active->blocked`; the next user turn produced `blocked->active`. A real app-server compaction produced `compact:019f6b4b-0902-7952-ad5a-ec1cbf3f9adc:manual`, then compact SessionStart restored human-readable status plus the exact outcome contract and the subsequent turn returned `REAL_COMPACT_READY`.
- The final synced runtime produced `Status: active FINAL_SYNC_READY`. Running the exact `$fin` close command twice set `done`/`closed` and left one `fin: completed` activity.
- Explicit reopen cleared `closed`; the next normal trusted turn returned `REOPEN_READY`, and the final close restored `done` with a non-null `closed` value without duplicating `fin: completed`.
- The final immutable audit found schema version 1; three FTS-searchable tasks all `done`; one handler for each of the four hook events; directory/database/WAL/shared-memory modes `0700`/`0600`; and byte-identical canonical/runtime copies of `agtask` and `$fin`.

## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-07-16 10:24: Completed native trusted no-bypass, real PostCompact/compact-resume, reopen, final-close, runtime-integrity, and immutable SQLite proofs; all five phases and ten tests now pass (019f690b-df2b-75b2-9139-835f220ae4ac - no-git-sha)
- 2026-07-16 10:11: Implemented and packaged agtask, synced through `skillz`, installed hooks, passed eight tests, created fork/clean tasks, and proved the complete hook/status/compaction/fin lifecycle through the real Codex CLI; native persisted hook trust remains pending explicit approval (019f690b-df2b-75b2-9139-835f220ae4ac - no-git-sha)
- 2026-07-16 00:03: Addressed simulation findings with wrapper-aware summaries, transactional migrations, secure atomic writes, restored outcome context, and `skillz`-based runtime synchronization (019f690b-df2b-75b2-9139-835f220ae4ac - no-git-sha)
- 2026-07-15 23:54: Created the implementation-ready agtask session-management feature spec (019f690b-df2b-75b2-9139-835f220ae4ac - no-git-sha)

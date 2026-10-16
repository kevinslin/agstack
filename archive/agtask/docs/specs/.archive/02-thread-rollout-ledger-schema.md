# Feature Spec: Thread and Rollout Ledger Schema

**Date:** 2026-07-16
**Status:** Completed

---

## TL;DR

- Replace the v1 `sessions`/`log` store with a Codex-aligned `thread`/`rollout` ledger at `~/.llm/agtask/ledger.db`.
- Make task kind, project, lineage, event identity, role, and summarized message explicit columns; message hashes and digest-derived identities leave the model.
- Ship one canonical schema and vocabulary across the CLI, hooks, JSON output, skill, tests, and active documentation, with no migration or aliases for the v1 database.
- Prove the hard cut with read-only compatibility inspection, symmetric bootstrap reconciliation, concurrent retry tests, and real clean/fork/hook/compaction/`$fin` lifecycle validation.

---

## Goal and Scope

### Goal

Align the agtask persistence model with Codex's thread and rollout vocabulary while retaining the current local task-tracking behavior. The new ledger must represent one current-state row per tracked Codex thread and one ordered row per summarized conversation or lifecycle event, without embedding machine identity inside human-readable messages.

### In Scope

- Change the default database to `~/.llm/agtask/ledger.db`.
- Replace `sessions` with `thread` and add `parent_thread_id`, `kind`, and `project`.
- Replace `log` with `rollout` and add explicit event identity, role, and message columns.
- Replace digest-based turn idempotency with structured unique indexes and state-aware transactions.
- Preserve FTS5 search over thread title and description.
- Update the CLI, hook adapter, clean/fork creation flows, `$fin` integration, JSON output, tests, packages, and active documentation in one implementation pass.
- Validate the source skill, scoped `skillz` synchronization, installed runtime, and live SQLite lifecycle end to end.

### Out of Scope

- Importing, migrating, copying, or deleting `~/.llm/thread/thread.db`.
- Preserving v1 table names, CLI aliases, JSON field aliases, or dual read/write paths.
- Copying full Codex transcripts or native rollout JSONL into SQLite.
- Tracking arbitrary parent threads as local ledger rows.
- Changing the Codex command-hook input schema or the `$SESSION_ID` value supplied by Codex/`$fin`.

---

## Context

### Background

The completed v1 implementation stores current state in `sessions` and activities in `log`. A log row overloads `name` with role, Codex turn ID, SHA-256 digest, and summary. This makes machine identity inseparable from display text and keeps local vocabulary centered on sessions even though the tracked object is a Codex thread.

The replacement model uses explicit columns. `thread` stores current state and optional origin lineage. `rollout` stores event identity, role, and a bounded human-readable summary. SQLite constraints and application transactions provide idempotency, so no message digest is required.

### Current State

- Schema version 1 lives at `~/.llm/thread/thread.db` with `sessions`, `log`, `sessions_fts`, FTS triggers, and lifecycle-log triggers.
- `log.name` stores `<role>:<turn-id>:<sha256>: <summary>` for user and assistant turns and free-form strings for lifecycle activities.
- `show --json` returns a session-shaped object with an `activities` array containing `{created, name}` rows.
- The `activity` command writes arbitrary activity names, while `record-turn` hashes content and performs bootstrap replacement.
- The default creation mode is a clean Codex task; explicit context-preservation requests use a same-directory fork.
- Codex hook payloads identify the active thread with the external field `session_id`.

### Context

- [Archived v1 feature spec](./01-agtask-session-management.md): historical rationale, lifecycle behavior, and completed v1 evidence.
- [Architecture](../../ARCHITECTURE.md): current component boundaries, flows, data ownership, and failure semantics that the implementation must update.
- [CLI and hook adapter](../../../skills/agtask/scripts/agtask): canonical schema, queries, event processing, installation, and JSON output.
- [Skill workflow](../../../skills/agtask/SKILL.md): clean/fork creation, registration ordering, bootstrap repair, and handoff contract.
- [CLI integration tests](../../../tests/test_cli.py): schema, lifecycle, hook, lock, bootstrap, and configuration coverage.
- [`$fin` integration tests](../../../tests/test_fin_integration.py): full-success versus partial-finalization closure behavior.
- [Compaction proof helper](../../../tests/e2e_compact.py): real app-server compaction and post-compact hook proof.

### Constraints

- The canonical source remains this repository; the installed skill remains a generated `skillz` mirror.
- `AGTASK_DB` remains available for isolated tests. Normal runtime operations use the canonical default path.
- Store timestamps remain UTC RFC 3339 strings with millisecond precision.
- Hook operations remain network-free, bounded, and fail open. They remain
  silent for untracked threads except when an exact version-2 creation prompt
  atomically registers its own real child ID and initial user rollout.
- Explicit CLI operations fail closed with actionable errors.
- The ledger directory uses mode `0700`; database, WAL, and shared-memory files use mode `0600`.
- The archived v1 spec remains unchanged as a historical artifact. Active documentation must describe only the new contract after implementation.

---

## Approach and Touchpoints

### Proposed Approach

Replace the schema and local vocabulary as one hard cut. The CLI opens only `~/.llm/agtask/ledger.db`, recognizes only the new schema, and maps external Codex `session_id` values to internal `thread_id` values at the hook boundary. Application code owns lifecycle rollout writes in the same transactions as state changes. SQLite triggers remain only for FTS synchronization.

The old database remains available for manual historical inspection at its old path. The new implementation neither discovers it nor uses it to initialize the new ledger.

### SQLite Contract

The canonical schema version is 3:

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 1000;

CREATE TABLE thread (
  id               TEXT PRIMARY KEY NOT NULL,
  parent_thread_id TEXT,
  kind             TEXT NOT NULL CHECK (kind IN ('main', 'child')),
  project          TEXT NOT NULL CHECK (length(trim(project)) > 0),
  title            TEXT NOT NULL,
  description      TEXT NOT NULL DEFAULT '',
  created          TEXT NOT NULL,
  updated          TEXT NOT NULL,
  closed           TEXT,
  status           TEXT NOT NULL
                   CHECK (status IN ('todo', 'active', 'blocked', 'done')),
  CHECK (
    (status = 'done' AND closed IS NOT NULL) OR
    (status <> 'done' AND closed IS NULL)
  ),
  CHECK (parent_thread_id IS NULL OR parent_thread_id <> id),
  CHECK (
    (kind = 'main' AND parent_thread_id IS NULL) OR
    (kind = 'child' AND parent_thread_id IS NOT NULL)
  )
);

CREATE INDEX thread_created_idx ON thread(created);
CREATE INDEX thread_status_updated_idx ON thread(status, updated);
CREATE INDEX thread_parent_idx ON thread(parent_thread_id);

CREATE TABLE rollout (
  id        INTEGER PRIMARY KEY,
  created   TEXT NOT NULL,
  thread_id TEXT NOT NULL REFERENCES thread(id) ON DELETE CASCADE,
  turn_id   TEXT NOT NULL,
  role      TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'meta')),
  message   TEXT NOT NULL
);

CREATE INDEX rollout_thread_order_idx
  ON rollout(thread_id, created, id);

CREATE UNIQUE INDEX rollout_turn_event_idx
  ON rollout(thread_id, role, turn_id)
  WHERE role IN ('user', 'assistant');

CREATE UNIQUE INDEX rollout_meta_event_idx
  ON rollout(thread_id, turn_id)
  WHERE role = 'meta';

CREATE VIRTUAL TABLE thread_fts USING fts5(
  title,
  description,
  content='thread',
  content_rowid='rowid'
);

CREATE TRIGGER thread_ai AFTER INSERT ON thread BEGIN
  INSERT INTO thread_fts(rowid, title, description)
  VALUES (NEW.rowid, NEW.title, NEW.description);
END;

CREATE TRIGGER thread_ad AFTER DELETE ON thread BEGIN
  INSERT INTO thread_fts(thread_fts, rowid, title, description)
  VALUES ('delete', OLD.rowid, OLD.title, OLD.description);
END;

CREATE TRIGGER thread_au AFTER UPDATE OF title, description ON thread BEGIN
  INSERT INTO thread_fts(thread_fts, rowid, title, description)
  VALUES ('delete', OLD.rowid, OLD.title, OLD.description);
  INSERT INTO thread_fts(rowid, title, description)
  VALUES (NEW.rowid, NEW.title, NEW.description);
END;

PRAGMA user_version = 3;
```

Standard external-content triggers synchronize `thread_fts` after thread insert, delete, and updates to `title` or `description`. Lifecycle rollouts are written by the application rather than triggers because their event IDs and state transitions are part of the application transaction.

`parent_thread_id` intentionally has no foreign key. A main thread is a root dispatcher with null lineage. A child thread records its invoking Codex thread, which may not itself be tracked by agtask. Kind, project, and lineage are immutable after registration.

### Database Initialization and Refusal Contract

The CLI resolves the default path to `~/.llm/agtask/ledger.db` and follows this order:

1. For a missing database, create the parent directory securely and install the complete version-3 schema transactionally.
2. For an existing database, open a read-only probe before permission repair, WAL selection, DDL, schema-version writes, or write transactions.
3. Accept an exact version-3 schema, then reopen normally and enable WAL.
4. Accept an empty version-0 database with no user objects, then initialize it as version 3.
5. Reject every other schema with an explicit recovery message directing the operator to move the incompatible file aside and initialize a new ledger.

Rejection preserves the existing file's bytes and mode and creates no WAL, shared-memory, journal, backup, replacement, or temporary sidecar. Schema verification covers the exact table columns, `NOT NULL` and `CHECK` constraints, foreign key, FTS contract, indexes, and triggers.

### Thread Lineage Contract

- Every child thread created by the skill records the invoking Codex thread ID as `parent_thread_id` in both clean and fork modes.
- Every main thread omits `parent_thread_id` and acts as a root dispatcher.
- Registration persists the resolver's explicit or default project label.
- Registration derives the stable description from the initial creation prompt.
- Re-registering an existing thread with the same kind, project, parent, and description is idempotent.
- Supplying different kind, project, parent, or description metadata is a conflict and fails without mutation.
- A thread cannot name itself as its parent.

The field represents origin lineage, not copied-context semantics. Creation mode remains a separate runtime decision: clean mode starts without copied conversation history, while fork mode preserves context.

### Rollout Contract

`rollout.message` contains only a bounded normalized summary. It is single-line UTF-8 text, strips supported prompt wrappers and Markdown prefixes, and is capped at 240 Unicode code points. The ledger stores no message digest and does not derive an event ID from message content.

Roles have these meanings:

| Role | Stored event |
| --- | --- |
| `user` | Summary of one Codex user turn |
| `assistant` | Summary of one final assistant result |
| `meta` | Thread creation, state transition, compaction, or finalization update |

Canonical meta messages and event IDs are:

| Event | `turn_id` | `message` |
| --- | --- | --- |
| Thread registration | `thread.created` | `thread.created` |
| Status transition | Fresh opaque event ID created inside the state-change transaction | `status:<old>-><new>` |
| Compaction | `compact:<codex-turn-id>:<manual-or-auto>` | `compaction:<manual-or-auto>` |
| Successful finalization | Fresh opaque event ID created inside the close transaction | `finalization:completed` |

Creation happens once per thread. Status and finalization IDs are generated only when state actually changes. Repeating a same-state `status` or `close` command writes nothing. A later identical transition after an intervening state change receives a fresh event ID and remains visible as a distinct historical event.

For any unique event key:

- Replaying the same normalized message is a successful no-op.
- Reusing the key with a different normalized message is an explicit conflict for direct commands; hook mode leaves the committed row unchanged and fails open.
- All read-check-write sequences use `BEGIN IMMEDIATE` so concurrent writers cannot create duplicate logical events.

Recent rollouts are ordered by `created DESC, id DESC`. Session-start context renders role plus human message and omits database IDs and event IDs unless the event identity itself is meaningful to the user.

### Bootstrap Reconciliation

`bootstrap` remains a reserved `turn_id` for clean-creation and snapshot race
repair. Reconciliation is symmetric because the real hook, parent registration,
or the skill backfill may arrive first. An exact version-2 creation prompt lets
the real hook atomically initialize the ledger, register its own child session,
append `thread.created`, and store the initial user rollout under the real turn
ID. Parent registration and the bootstrap write remain idempotent retries. The
initial user prompt must normalize to the description derived at registration;
an incompatible bootstrap is rejected without mutation.

When recording a real user or assistant event:

1. Return without mutation when the exact `(thread_id, role, turn_id)` already stores the same message.
2. Find the single same-role bootstrap rollout.
3. Promote that bootstrap row to the real `turn_id` only when the normalized messages match, no other non-bootstrap rollout exists for that role, and a user promotion has no assistant rollout after it.
4. Insert the real event normally when those promotion conditions are not met.

When recording a bootstrap event:

1. Treat an equal same-role non-bootstrap rollout as a successful no-op.
2. Otherwise insert the bootstrap rollout under the ordinary uniqueness constraints.

After a compatible initial user rollout exists, later mismatched user summaries
remain distinct. Replays after either arrival order remain idempotent. Neither
user nor assistant rollout recording replaces the registered description.

### CLI and JSON Contract

The canonical commands become:

```text
agtask init
agtask register --id ID [--parent-thread-id ID] --title TITLE --initial-prompt TEXT [--description ASSERTION] --status todo|active
agtask show --id ID [--json]
agtask list [--status STATUS] [--limit N] [--json]
agtask search QUERY [--limit N] [--json]
agtask status --id ID --status todo|active|blocked
agtask reopen --id ID
agtask close --id ID
agtask append-rollout --id ID --turn-id EVENT_ID --role user|assistant|meta --message SUMMARY
agtask record-turn --id ID --turn-id TURN_ID --role user|assistant --content TEXT [--summary SUMMARY]
agtask hook
```

The v1 `activity` command is replaced by `append-rollout`. Machine-readable thread output uses `rollouts`, with each entry containing `id`, `created`, `thread_id`, `turn_id`, `role`, and `message`. Local variables, errors, and help text use `thread`/`thread_id` terminology.

External boundaries retain their platform names:

- Hook JSON continues to arrive with `session_id`; the adapter immediately maps it to `thread_id`.
- Codex continues to call the `SessionStart` event by that name.
- `$fin` continues to resolve the active Codex ID from `$SESSION_ID` and passes it to `close --id`.

### Integration Points / Touchpoints

- [`skills/agtask/scripts/agtask`](../../../skills/agtask/scripts/agtask): schema, version verification, database path, rollout writes, JSON, CLI vocabulary, hook mapping, and removal of digest-based identity.
- [`skills/agtask/SKILL.md`](../../../skills/agtask/SKILL.md): parent resolution, registration flags, rollout verification, new database path, and current-state terminology.
- [`skills/agtask/assets/hooks.json`](../../../skills/agtask/assets/hooks.json): verify the installed command remains correct after packaging.
- [`README.md`](../../../README.md): installation, CLI, test, inspection, recovery, and hard-cut path guidance.
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md): data model, diagrams, flows, failure semantics, and source/runtime layout.
- [`tests/test_cli.py`](../../../tests/test_cli.py): exact schema and behavior coverage.
- [`tests/test_fin_integration.py`](../../../tests/test_fin_integration.py): close and finalization rollout behavior.
- [`tests/e2e_compact.py`](../../../tests/e2e_compact.py): rename `--session-id` to `--thread-id` and query `rollout`.
- [`tests/test_skill_contract.py`](../../../tests/test_skill_contract.py): skill path, lineage, vocabulary, and verification contract.
- `dist/agtask.skill` and `dist/fin.skill`: regenerate from canonical sources after validation.

### Resolved Ambiguities / Decisions

- **Codex alignment:** The model adopts Codex concepts and vocabulary while remaining a purpose-built SQLite projection; native Codex rollout JSONL remains external diagnostic evidence.
- **`meta` meaning:** `meta` means lifecycle and status update, covering creation, transitions, compaction, and finalization.
- **Kind and parent meaning:** `main` identifies a root dispatcher with no parent; `child` records the creating task in both clean and fork modes and does not imply copied history.
- **Registration integrity:** Kind, project, and parent lineage are immutable after initial registration; child lineage intentionally permits untracked parents.
- **Message identity:** Event IDs and state transitions provide identity; normalized messages remain display/search material only.
- **Lifecycle writers:** Application transactions write lifecycle rollouts. FTS synchronization is the only trigger-owned behavior.
- **Hard cut:** The new path and version-3 schema are the sole runtime contract. Version-2 rows receive no project backfill; the old path remains an untouched historical artifact.
- **Historical documentation:** The completed v1 spec remains archived. README, architecture, skill instructions, tests, and generated packages move to the new contract together.

### Existing Contract Snapshot

| Surface | Current owner / source of truth | Current shape | Current consumers |
| --- | --- | --- | --- |
| Database path | `database_path()` | `~/.llm/thread/thread.db` | CLI, hooks, skill, README, tests |
| Current state | `sessions` | Seven columns keyed by Codex session/thread ID | CLI queries, hooks, skill, `$fin` |
| Event history | `log` | `{created, name, session_id}` with identity encoded in `name` | Hooks, context rendering, tests, manual SQL |
| Turn identity | `record_turn()` | Role + turn ID + SHA-256 prefix inside `log.name` | Retry suppression and bootstrap promotion |
| JSON output | `session_dict()` | Thread fields plus `activities[{created,name}]` | Skill verification and tests |
| External hook identity | Codex hook payload | `session_id` and event-specific `turn_id` | Hook adapter |

### Target Decision Table

| Input facts / state | Target output | Notes |
| --- | --- | --- |
| New ledger path is absent | Secure version-3 ledger with `thread`, `rollout`, and `thread_fts` | One canonical initialization path |
| Existing ledger is exact version 3 | Open normally, enable WAL, and proceed | Read-only verification happens first |
| Existing ledger is empty version 0 | Initialize version 3 transactionally | No migration semantics are involved |
| Existing ledger is incompatible | Fail before mutation with move-aside recovery guidance | File bytes/mode and sidecar absence are preserved |
| Old v1 database exists | Ignore it and use the new canonical path | Historical data remains available manually |
| Skill creates clean or fork child task | Store kind, project, and caller ID as `parent_thread_id` | Lineage is independent of copied context |
| Skill designates the invoking task as main | Store main kind, project, and null `parent_thread_id` on the invoking thread ID | Main is the pinned root dispatcher; no new Codex task is created |
| Hook carries `session_id` | Map to internal `thread_id` and process only an exact tracked row | External Codex contract remains unchanged |
| User/assistant event is replayed | One rollout for the event key | Same message is a no-op; conflicting message is rejected/fail-open |
| Bootstrap and real event arrive in either order | One matching rollout with the real turn ID | Symmetric reconciliation handles both races |
| Status command repeats current state | No thread timestamp or rollout change | No synthetic lifecycle noise |
| `active -> blocked -> active -> blocked` | Two distinct `status:active->blocked` rollouts | Each actual transition gets a fresh event ID |
| Close repeats while done | One finalization rollout for that close | State-aware no-op |
| `close -> reopen -> close` | Two finalization rollouts | Both closes are real lifecycle events |
| PostCompact payload is replayed | One deterministic compaction rollout | Event ID uses Codex turn ID plus trigger |

### Minimal Model Check

- **New fields/types/states:** `thread.parent_thread_id`, `kind`, and `project`; kinds `main` and `child`; `rollout.id`, `turn_id`, `role`, and `message`; roles `user`, `assistant`, and `meta`.
- **Existing fields/types reused:** Thread identity, title, description, timestamps, closed/status invariant, Codex turn IDs, and FTS title/description search.
- **Derived values intentionally not stored:** Message hashes, raw hook content, deep links, creation mode, display labels, open/closed booleans, and FTS rank.
- **Consumers:** The skill reads parent/current state and verifies initial rollouts; hooks append user/assistant/meta rollouts; SessionStart renders recent rollouts; `$fin` writes terminal state and finalization; CLI users query/search the ledger.
- **Simpler alternative considered:** Renaming only the tables would preserve overloaded message strings and ambiguous retry behavior. Explicit event columns are the smallest model that removes hashing while retaining concurrency-safe idempotency.

---

## Acceptance Criteria

- [x] The default database is `~/.llm/agtask/ledger.db`, initialized atomically as schema version 3 with the exact `thread`, `rollout`, FTS, index, constraint, and trigger contract in this spec.
- [x] The old `~/.llm/thread/thread.db` remains a separate historical artifact outside every v3 runtime path.
- [x] Incompatible ledgers are rejected by the read-only preflight before the normal write path opens them.
- [x] Clean and fork task creation store immutable kind, project, and kind-appropriate lineage; main requires `NULL` parent and child requires a parent.
- [x] User, assistant, and meta events use structured rollout rows, bounded normalized messages, explicit event IDs, and state-aware idempotency.
- [x] Bootstrap reconciliation handles both arrival orders, mismatches, and retries.
- [x] `show --json`, CLI terminology, hooks, `SessionStart`, and `$fin` use the canonical vocabulary and boundary mappings.
- [x] FTS search, lifecycle integrity, fail-open hooks, secure modes, and bounded SQLite contention are covered by integration tests.
- [x] README, architecture, skill instructions, tests, generated packages, and installed runtime implement the same v3 contract.
- [x] Real clean, fork, turn, block/unblock, compaction/resume, close/reopen/close, and `$fin` lifecycle rows were verified end to end.

---

## Implementation Checklist and Evidence

- [x] Implemented the exact v2 schema, hard-cut opening rules, lineage validation, structured rollouts, FTS triggers, and CLI/JSON contract in `skills/agtask/scripts/agtask`.
- [x] Updated hook mapping, bootstrap reconciliation, SessionStart context, skill creation flows, `$fin`, README, architecture, tests, and the compaction helper.
- [x] Passed `python3 -m unittest discover -s tests -v`: 18 tests covering schema, refusal, lineage, reconciliation, lifecycle, hooks, skill contract, `$fin`, and skillz installation.
- [x] Proved clean task `019f6c29-ebe0-71f0-8916-230a1b5fd5c2` and fork task `019f6c2b-1929-7030-842e-d30be088a3d1`, both with parent `019f6c21-6b9c-74a3-a32f-8068a117286d`.
- [x] Proved user/assistant hooks and `active -> blocked -> active` on clean turns `019f6c2a-c403-7b43-9791-b4dc101b9623`, `019f6c2a-e288-7790-b56f-5aa2a6ea8d4e`, and `019f6c2b-09e7-7812-b687-722985c8e1ab`.
- [x] Proved fork first-turn normalization on turn `019f6c2b-5e7b-7630-89df-6179d92e9082`.
- [x] Proved real manual compaction with non-empty PostCompact turn ID `019f6c2e-b39b-7700-b71f-1e5170ab1eb0`, deterministic rollout `compact:019f6c2e-b39b-7700-b71f-1e5170ab1eb0:manual`, and restored-context turn `019f6c2e-c62c-73b0-994d-7c0f1c804494`.
- [x] Converged hooks to one installed runtime handler per event and proved exactly one user and one assistant rollout for installed-hook turn `019f6c32-13ba-78e1-ac26-0f55361664c7`.
- [x] Proved idempotent close, close/reopen/close history, and fresh finalization IDs with status/finalization rows sharing each `closed` timestamp.
- [x] Ran the exact `$fin` closure command against the fork task and verified `status:active->done` plus `finalization:completed` at `2026-07-16T18:28:46.513Z`.
- [x] Resolved parent IDs from the active Codex app context; the skill records the same lineage in clean and fork modes and documents the CLI/session-resolution path.
- [x] Regenerated both skill packages, synchronized through configured skillz sources, verified canonical/runtime byte equality, and reinstalled the hook command.

---

## Risks

### Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
| --- | --- | --- | --- |
| Read-only schema inspection accidentally mutates an incompatible file | High | Low | Use SQLite URI read-only mode before permission repair/WAL and assert exact bytes, mode, and directory contents in tests |
| Removing hashes permits duplicate retries | High | Med | Require non-null event IDs, enforce role-aware unique indexes, and serialize reconciliation with `BEGIN IMMEDIATE` |
| Bootstrap and hook events arrive in the opposite order from tests | High | Med | Implement and test symmetric reconciliation for both user and assistant roles |
| Global message deduplication hides legitimate repeated lifecycle events | High | Med | Deduplicate by event ID/state, generate fresh IDs for actual repeated transitions, and keep message outside identity |
| Parent lineage is unavailable or rewritten | Med | Med | Resolve parent before creation, allow null only for direct registration, and reject conflicting re-registration |
| Active docs retain v1 SQL or paths | Med | High | Update adjacent docs in the implementation pass and run a broad vocabulary/path audit |
| External Codex names are renamed as if they were local compatibility aliases | High | Low | Keep `session_id`, `SessionStart`, and `$SESSION_ID` at their platform boundaries and map once internally |
| New path silently strands expected historical state | Low | High | State the hard cut in README and expose explicit read-only commands for inspecting the old database |

### Simplifications and Assumptions

- The ledger is a local projection of Codex task state, not a replica of Codex's private database.
- One final user and one final assistant summary per Codex turn are sufficient for task tracking.
- Parent lineage is one level per row; recursive ancestry is derived by querying parent IDs.
- The application writes lifecycle rollouts directly, avoiding trigger-generated opaque IDs and custom SQLite extensions.
- The hard cut favors a clean canonical model over migration machinery because agtask has no external installed user base.

---

## Outputs

- PR created from this spec: none; implementation remains uncommitted as requested
- Implementation source: `skills/agtask/`
- Active documentation: `README.md`, `docs/ARCHITECTURE.md`
- Generated artifacts: `dist/agtask.skill` (`7a775c1542540b67831e2a085d25b4ef69b59050b7fba19300bada99b5d7954d`), `dist/fin.skill` (`3bba5f42b5444e901c11c65911f1e9a2359b82821445cdc3853e97e4ec31ac64`)

## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-07-16 14:31: Completed the canonical v2 implementation and recorded automated, package, synchronization, hook, and live lifecycle evidence (019f6c21-6b9c-74a3-a32f-8068a117286d - 3b555f807195bc9d7cdb7294e32227bdc418d47f)
- 2026-07-16 14:05: Consolidated phases, validation, and done criteria into one implementation checklist with colocated verification (019f690b-df2b-75b2-9139-835f220ae4ac - 3b555f807195bc9d7cdb7294e32227bdc418d47f)
- 2026-07-16 14:03: Reframed acceptance and validation around positive assertions of the canonical schema and expected lifecycle rows (019f690b-df2b-75b2-9139-835f220ae4ac - 3b555f807195bc9d7cdb7294e32227bdc418d47f)
- 2026-07-16 13:45: Created the implementation-ready hard-cut spec for the thread and rollout ledger schema (019f690b-df2b-75b2-9139-835f220ae4ac - 3b555f807195bc9d7cdb7294e32227bdc418d47f)

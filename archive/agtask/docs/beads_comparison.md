# agtask compared with Beads

## Outcome

Beads and agtask overlap in persistent agent context, lifecycle state, structured history, JSON-first automation, and compaction recovery, but they are not substitutes.

- **Beads is a project-scoped, distributed issue graph.** It owns durable work items, dependencies, readiness, claims, assignment, rich issue content, history, synchronization, and multi-agent coordination.
- **agtask is a user-local projection of Codex task threads.** Codex owns the conversation; agtask records logical creation identity, unique Codex session identity, main/child kind, project label, parent-session lineage, bounded turn summaries, hook-derived lifecycle state, and explicit close events.

The best near-term direction is to keep agtask narrow, add missing workspace and diagnostic affordances, and integrate with Beads when work needs planning or multi-agent coordination. Reimplementing Beads's dependency graph, claim model, or Dolt synchronization inside agtask would conflict with its thread-ledger purpose.

## Compared revisions and method

This report compares source checked out on 2026-07-16:

- **agtask:** local `master` implementation baseline at `838c54a3832dcfe928f44c3904e794b5675503b3` (`docs: archive completed dashboard spec`). This is the source revision rechecked during finalization; the subsequent finalization commit changes only this report's provenance and validation notes.
- **Beads:** clean `main` at [`67652d8b5caf73ce6c1728d8efe621277ad2af24`](https://github.com/gastownhall/beads/commit/67652d8b5caf73ce6c1728d8efe621277ad2af24).
- **Canonical repository:** GitHub currently resolves `https://github.com/steveyegge/beads` to [`gastownhall/beads`](https://github.com/gastownhall/beads). The clone retains the historical `steveyegge/beads` remote URL, which GitHub redirects.

The comparison uses executable schema and command code as authority, then current architecture and integration documentation for product intent and operating guidance. Historical proposals and staged-for-removal documents are excluded from conclusions.

## Direct source facts

The following table contains source facts only. Interpretation and recommendations follow separately.

| Dimension | agtask | Beads |
| --- | --- | --- |
| Product goal | Creates real Codex tasks and maintains a searchable local lifecycle projection. Codex remains authoritative for full conversations; SQLite stores current thread state, lineage, bounded summaries, and lifecycle events. [README](../README.md#L1-L7), [architecture](ARCHITECTURE.md#L1-L30) | Provides persistent structured memory for coding agents through a dependency-aware issue graph. Its charter defines core ownership of issues, lifecycle, dependencies/readiness, labels, comments, priority, assignment, import/export/sync/backup/recovery, and tracker integrations. [README](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/README.md#L1-L24), [project charter](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/engdocs/PROJECT_CHARTER.md#L8-L21) |
| Identity and scope | The primary key is a pre-creation logical UUID. A unique `session_id` binds it to the real Codex session; `kind` distinguishes a root-dispatching main from a child, `project` stores a project label, and `parent_session_id` records a child's invoking Codex session and may refer to an untracked parent. The schema stores no workspace path, repository, branch, assignee, priority, or external issue identity. [schema](../skills/agtask/scripts/agtask#L60-L120), [lineage contract](data_model.md#thread) | The primary object is a project issue with a generated ID. The issue model includes content, type, priority, assignment, estimates, scheduling, external references, metadata, compaction fields, messaging fields, and relational data. [issue type](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/types/types.go#L14-L112) |
| Persistence | One user-local SQLite v5 database at `~/.llm/agtask/ledger.db`, with `0700` directory and `0600` database/WAL/SHM modes, foreign keys, WAL, and a one-second busy timeout. Existing incompatible schemas are refused rather than migrated. [database path and modes](../skills/agtask/scripts/agtask), [opening contract](ARCHITECTURE.md#sqlite-store-and-reliability) | Dolt is the default source of truth. Embedded mode stores an in-process, single-writer database in `.beads/embeddeddolt/`; server mode supports concurrent writers in `.beads/dolt/`. Other storage backends exist, but Dolt alone provides native history, branching, and sync. [storage modes](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/README.md#L127-L146), [Dolt modes](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/architecture/dolt.md#L61-L135) |
| Data model | Three logical tables: `thread`, `rollout`, and the short-lived `project_merge_claim`, plus FTS indexes/triggers over thread title and description. A rollout stores a logical thread ID, stable turn/event ID, role, timestamp, and normalized message. [DDL](../skills/agtask/scripts/agtask#L41-L155) | Issues are rich records. Separate dependency, label, comment, and event tables model graph edges and audit information. The dependency table stores typed edges and metadata; the event table stores actor and old/new values. [issue schema](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/storage/schema/migrations/0001_create_issues.up.sql#L1-L60), [dependency schema](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/storage/schema/migrations/0002_create_dependencies.up.sql#L1-L15), [event schema](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/storage/schema/migrations/0005_create_events.up.sql#L1-L13) |
| Status semantics | Fixed states: `todo`, `active`, `blocked`, `merging`, `done`, and `drop`. `merging` projects a fenced project claim and is preserved by turn hooks; `done` and `drop` require `closed` and leave only through explicit reopen. [status lifecycle](data_model.md#status-and-timestamp-lifecycle) | Built-ins are `open`, `in_progress`, `blocked`, `deferred`, `closed`, `pinned`, and `hooked`. Custom statuses can map to active, work-in-progress, done, or frozen behavior categories. [status model](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/types/types.go#L329-L425) |
| Task and dependency semantics | Main/child kind and `parent_session_id` encode dispatch origin, not blocking edges or a readiness graph. There is no dependency table, readiness calculation, priority, label, assignment, estimate, or arbitrary task type. The one lease is narrowly scoped to serializing final merge/close work for an exact project label, not general work claiming. [lineage contract](data_model.md#thread), [merge claim](data_model.md#project_merge_claim) | Typed edges include blocking, parent-child, conditional, fan-out wait, discovery, reply, duplicate, supersession, approval, tracking, validation, and delegation relationships. Four edge types affect ready-work calculation. [dependency model](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/internal/types/types.go#L781-L859) |
| History and events | Rollouts record user, assistant, and meta events. Role-aware unique indexes and explicit event IDs make exact replays no-ops and conflicting reuses errors. Messages are single-line summaries capped at 240 code points; raw conversation content remains in Codex rollout storage. [event indexes](../skills/agtask/scripts/agtask#L80-L115), [normalization and conflicts](../skills/agtask/scripts/agtask#L350-L435) | Beads records issue audit events and, with Dolt, version-controls database writes. Each successful write can create a Dolt history commit; JSONL is an export, not the synchronization protocol or a full-history backup. [architecture](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/architecture/index.md#L37-L53), [sync concepts](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/core-concepts/sync-concepts.md#L6-L44) |
| CLI and API surface | A small Python CLI exposes initialization, registration, show/list/search, status/reopen/close, rollout writes, turn recording, hook installation, and a temporary loopback-only read API for its dashboard. JSON is supported, but there is no persistent daemon, SDK, public service API, or MCP server. [CLI and dashboard](../skills/agtask/scripts/agtask) | A broad Go CLI covers issue CRUD, ready/blocked queues, dependencies, claims, comments, labels, graphs, workflows, gates, memories, diagnostics, backup, storage, and synchronization. An optional Python MCP server exposes common issue operations, though the project recommends CLI plus hooks when shell access is available. [essential CLI](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/README.md#L60-L89), [MCP surface](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/integrations/beads-mcp/README.md#L1-L8), [MCP tools](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/integrations/beads-mcp/README.md#L207-L227) |
| Agent integration | The skill designates and pins the invoking thread for main kind, or creates exactly one clean/same-directory-fork child for child kind. It registers resolved kind/project and kind-appropriate lineage, publishes a deep link, delivers configured prompt data at the orchestration boundary, and verifies registration plus child bootstrap tracking. [creation workflow](../skills/agtask/references/create.md) | `bd setup` supports multiple agent environments. Codex setup installs a Beads skill, managed `AGENTS.md` guidance, and native hooks; `bd prime` supplies the current operational workflow and persistent memories. [setup overview](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/getting-started/ide-setup.md#L12-L54), [Codex setup](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/integrations/codex.md#L6-L35) |
| Hooks and compaction | `UserPromptSubmit` records a user rollout and injects ledger context; `Stop` records the assistant result; `PostCompact` records a compaction event; `SessionStart` restores title, status, summary, five recent rollouts, and the outcome contract. Hook failures are deliberately swallowed. [hook adapter](../skills/agtask/scripts/agtask#L583-L668), [installed groups](../skills/agtask/scripts/agtask#L933-L943) | Codex hooks inject `bd prime` at session start, mark post-compaction refresh, and reinject context on the next prompt. The marker is outside the Beads database. These hooks restore issue-tracker context but do not automatically bind every Codex turn to an issue or close an issue from a final response. [Codex hook lifecycle](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/integrations/codex.md#L22-L35) |
| Git and distributed synchronization | None. The ledger is local to one user account and machine. It has no remote, merge, import/export, replication, or backup command. [storage contract](data_model.md#L12-L31), [CLI](../skills/agtask/scripts/agtask#L1046-L1124) | `bd dolt push` and `bd dolt pull` synchronize Dolt history, commonly through `refs/dolt/data` on the source Git remote. Worktrees share one Beads workspace; Dolt handles row/cell-level merge, while JSONL remains passive interchange. [sync concepts](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/core-concepts/sync-concepts.md#L6-L35), [Git/worktree integration](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/reference/git-integration.md#L145-L189) |
| Multi-agent behavior | Identifies main dispatchers and child tasks and records their origin. It has one narrow fenced lease that serializes final merge/close work per exact project label, but no shared ready queue, general work-claim arbitration, assignee registry, cross-repository routing, or child-completion aggregation. [creation workflow](../skills/agtask/references/create.md), [close workflow](../skills/agtask/references/close.md), [merge claim](data_model.md#project_merge_claim) | Supports assignment, atomic ready-work claims, release, fan-out/fan-in, comments, cross-repository edges, and exclusive merge slots. Assignees are strings rather than an agent registry. Embedded Dolt is single-writer; server mode is the concurrent-writer option. [coordination](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/multi-agent/coordination.md#L8-L137), [assignee limitation](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/multi-agent/coordination.md#L99-L105), [Dolt modes](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/architecture/dolt.md#L75-L135) |
| Lifecycle and finalization | Public `close --prepare` atomically claims an exact project or returns a randomized waiting hint. Heartbeat/cancel manage the lease; committing close requires its fencing token, records `status:merging->done` and `finalization:completed`, then returns `OnPostClose`. [close flow](ARCHITECTURE.md#pre-close-and-post-close-orchestration), [close implementation](../skills/agtask/scripts/agtask) | Agents explicitly claim and close durable issues. Closing unblocks dependents, but Codex hooks are context-recovery hooks rather than automatic completion hooks. Beads's core charter leaves routing, retry, scheduling, and orchestration policy outside core. [session protocol](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/plugins/beads/skills/beads/SKILL.md#L49-L60), [orchestration boundary](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/engdocs/PROJECT_CHARTER.md#L29-L42) |
| Observability | `show`, status-filtered `list`, title/description FTS search, JSON snapshots, recent-rollout context, and manual read-only SQLite inspection. Rollout text is not FTS-indexed, and no metrics/traces or doctor command exist. [queries](../skills/agtask/scripts/agtask#L749-L786), [manual inspection](../README.md#L68-L80) | Provides issue audit/history, `bd doctor`, statistics, and optional OpenTelemetry metrics for commands, storage operations, errors, lock waits, issue counts, hooks, and sync. Telemetry is disabled by default. [observability](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/reference/observability.md#L1-L32), [metrics and spans](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/docs/reference/observability.md#L84-L156) |
| Failure model | Explicit CLI commands fail closed and roll back. Global hooks fail open, so malformed payloads, unsafe permissions, incompatible schema, lock timeout, or event conflict can omit ledger updates without interrupting Codex. There is no retry queue or dead-letter log. Exact-schema refusal requires moving an incompatible database aside. [hook behavior](../skills/agtask/scripts/agtask#L603-L668), [database failures](ARCHITECTURE.md#L201-L207) | Embedded mode permits one writer; server mode adds service availability and connection management. Remote sync is explicit, migrations require version discipline, and concurrent pushes are intentionally not automatic. The MCP layer also has workspace-routing and connection-health failure modes. [storage modes](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/README.md#L127-L146), [MCP routing cautions](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/integrations/beads-mcp/README.md#L70-L205) |
| Operational complexity | Python standard library plus SQLite FTS5; no persistent service process. Installation still requires scoped skill synchronization, hook configuration, and manual hook approval. [installation](../README.md#install), [hook install safety](../skills/agtask/scripts/agtask) | Cross-platform Go CLI with Dolt embedded/server modes, schema migrations, remotes, backups, hooks, agent integrations, optional MCP, telemetry, and federation. [storage modes](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/README.md#L127-L146), [project boundary](https://github.com/gastownhall/beads/blob/67652d8b5caf73ce6c1728d8efe621277ad2af24/engdocs/PROJECT_CHARTER.md#L44-L80) |

## Meaningful conceptual overlap

These similarities are real even though the systems operate at different layers:

- Both give agents durable state that survives an individual context window.
- Both expose structured, scriptable JSON surfaces and optimize context returned to an agent.
- Both model current lifecycle state plus historical records.
- Both integrate with Codex hooks and recover context after compaction.
- Both favor local-first operation and explicit completion.
- Both treat orchestration as a layer above the persistence primitive: Beads states this as a product boundary, while agtask returns lifecycle prompt data to skills and Codex APIs.

The closest conceptual mapping is:

| agtask concept | Closest Beads concept | Important difference |
| --- | --- | --- |
| `thread` | issue | A thread is a real Codex conversation identity; an issue is session-independent durable work. |
| `parent_session_id` | `parent-child` or `delegated-from` edge | agtask stores Codex-session creation lineage only; Beads edges can affect hierarchy, readiness, or completion behavior. |
| `rollout` | event/comment/history entry | A rollout is a bounded conversation/lifecycle summary tied to a Codex turn; Beads stores richer issue audit and collaboration history. |
| `todo/active/blocked/merging/done/drop` | `open/in_progress/blocked/closed` | agtask states are inferred partly from Codex hooks and explicit lifecycle commands; `merging` is transient claim ownership and `drop` distinguishes abandonment from completion. Beads states are explicit issue workflow state. |
| SessionStart/PostCompact context | `bd prime` and Codex recovery hooks | agtask restores one tracked thread's latest ledger view; Beads restores workspace issue-tracker guidance and memories. |

## Capabilities unique to agtask

- Uses a logical creation UUID as persistence identity, binds it uniquely to the
  real Codex session, and returns a session-ID deep link to that task.
- Creates a clean or same-directory forked Codex task and records the invoking thread as immutable origin lineage.
- Reconciles the race between an explicit bootstrap write and the first real `UserPromptSubmit` hook by promoting or suppressing the bootstrap event.
- Captures user and assistant turn summaries automatically from Codex lifecycle hooks.
- Derives blocked state from the tracked task's final-result contract.
- Records Codex compaction events and reinjects the five most recent task rollouts.
- Returns configured `OnCreate`, `OnPreClose`, and `OnPostClose` prompts as structured data while leaving delivery and agent behavior to orchestration.
- Keeps full conversation content out of the ledger and leaves native Codex rollout JSONL authoritative.

## Capabilities unique to Beads

- Durable, session-independent issues with priorities, types, assignment, estimates, acceptance criteria, design, notes, labels, comments, metadata, due dates, and deferral.
- Typed dependency graph, ready-work calculation, hierarchy, discovered-work links, duplicates, supersession, validation, and delegation edges.
- Atomic claims, leases/heartbeats, shared ready queues, merge slots, and documented multi-agent handoff/fan-out patterns.
- Project/workspace scoping, worktree discovery, multi-repository routing, and federation.
- Dolt-native version history, branching, merge, backup, push/pull, and cross-machine synchronization.
- Explicit project memory (`bd remember`/`bd prime`), workflow templates/molecules, ephemeral wisps, and asynchronous gates.
- Broad CLI, optional MCP bridge, diagnostics, statistics, audit/history commands, and optional OpenTelemetry.

## Gaps Beads solves that agtask does not

These are gaps only if agtask is expected to become a work planner or team coordination system:

1. **No planning graph.** agtask cannot express blockers, readiness, priorities, hierarchy, discovered work, or completion dependencies.
2. **No general work ownership.** It cannot assign or arbitrate tasks among
   agents. Its project merge lease fences finalization only; it is not a ready
   queue or a claim on ordinary task execution.
3. **Limited project identity.** The ledger persists a project label but not CWD, workspace root, repository identity, branch, or external issue linkage.
4. **No distributed state.** It has no remote sync, merge, backup, or multi-machine recovery contract.
5. **Thin task content.** A 240-code-point current summary plus rollouts cannot replace acceptance criteria, design, comments, notes, or durable handoff context.
6. **Limited historical search.** FTS covers current title/description, not rollout messages or time-travel state.
7. **Limited operational diagnostics.** Fail-open hooks protect Codex availability but provide no durable evidence of dropped events, no doctor command, and no telemetry.
8. **No aggregate coordination view.** Parent lineage can be indexed but the CLI cannot list children, render a lineage tree, or aggregate descendant status.

## Where Beads concepts conflict with agtask's purpose

The following should not be copied into the thread ledger:

- **External issue identity as conversation identity.** agtask deliberately uses
  a local logical creation ID for rollout ownership and a unique Codex session
  ID for hooks and deep links. Replacing either side of that pair with a Beads
  issue ID would break binding and correlation; Beads identity belongs in an
  explicit external-work link.
- **Dolt or Git as conversation authority.** Codex remains authoritative for native conversation history. Replicating thread summaries through a project Git remote would also expose user-local task metadata to collaborators by default.
- **A full dependency/claim engine.** agtask's narrow per-project merge lease
  serializes finalization only. Ready queues, dependency graphs, general work
  claims, workflow templates, and federation still belong in an issue tracker
  or orchestrator.
- **Rich issue bodies in rollouts.** The bounded-summary model intentionally limits retained conversation content and keeps the ledger small. Issue notes and acceptance criteria should remain linked external objects.
- **Custom workflow states.** agtask's five states are part of its Codex hook, merge-claim, and outcome-contract semantics. Arbitrary project statuses would make automatic transition logic ambiguous.
- **Automatic distributed push during finalization.** Closing a local thread projection should not gain implicit network synchronization or remote mutation as a side effect.

## Recommendations

### Adopt in agtask

1. **Persist workspace identity.** Add an immutable or carefully updated `workspace_root` field, with optional repository and branch snapshots. This closes the largest observability gap without changing task semantics.
2. **Support external work links.** Add a small typed link surface such as `(thread_id, provider, project, item_id, relation)` or an equivalent metadata table. Here `thread_id` is the logical creation ID. Use it to connect a Codex task to a Beads issue, Linear issue, or GitHub issue without importing their workflow models.
3. **Expose lineage queries.** Add `list --parent-session-id`, `children`, or `tree` commands. Keep lineage descriptive; do not make parent state depend automatically on children.
4. **Add a doctor command.** Verify database compatibility and modes, hook installation/freshness, runtime/source parity, recent hook activity, and orphaned tracked threads. Preserve fail-open hooks, but make silent bookkeeping loss diagnosable.
5. **Add portable local backup/export.** Provide an explicit SQLite backup or JSON export command for disaster recovery. Do not use Git synchronization by default.
6. **Search rollout summaries.** Add FTS or a bounded query over already-retained rollout messages, with clear privacy and retention behavior.

### Integrate rather than adopt

Use Beads alongside agtask when a task needs dependencies, readiness, team assignment, multi-agent claims, durable project notes, or distributed synchronization:

```text
Beads issue: durable project work and coordination
    ↕ explicit external-work link
agtask thread: one real Codex execution conversation and lifecycle
```

The integration should remain optional and one-direction-at-a-time:

- Create or select a Beads issue first when work needs planning.
- Launch an agtask thread linked to that issue.
- Let agtask capture the Codex execution lifecycle.
- Update or close the Beads issue only through an explicit integration/finalization step with clear authority.
- Never infer Beads dependency completion solely from a Codex thread's `done` status.

### Do not adopt now

- General dependency or readiness tables
- Assignment, claim, lease, or heartbeat semantics
- Dolt, Git, or federation support
- Custom statuses or project workflow engines
- Molecules, wisps, gates, messaging, or memory primitives
- A broad MCP server before the small CLI contract needs a non-shell consumer

## Operational tradeoff

agtask's simplicity is a feature: one standard-library script, one local SQLite database, and a narrow Codex integration are easy to audit and operate. Beads earns its much larger operational surface by solving a much larger problem: durable issue management across agents, sessions, worktrees, repositories, and machines.

The architectural decision is therefore not "which task system wins." It is where to draw the seam:

- Keep **conversation execution state** in agtask.
- Keep **project work state and coordination** in Beads or another issue tracker.
- Link them explicitly when both are needed.

## Validation

- `python3 -m unittest discover -s tests -v` passed all 41 agtask tests.
- Beads remained clean at the pinned commit; no Beads files were modified.
- The agtask repository was renamed from `ag-task-v2` to `agtask` and received concurrent lifecycle, dashboard, and documentation commits after the initial comparison. The report was rechecked at the implementation baseline above; those concurrent changes were preserved.
- File and source-line counts were measured from `git ls-files` at the compared revisions; they are scale indicators, not quality metrics.

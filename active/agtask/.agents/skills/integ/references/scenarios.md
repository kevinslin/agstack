# Integration scenarios

Suite version: 20

Shared runner setup defaults `AGTASK_DB` to the allocated
`.integ/proof/<n>/ledger.db` and preserves an explicit caller override. No
integration scenario may fall through to the user's default ledger.

## current-task-add

Scenario version: 1

Against an isolated ledger, exercise the direct current-task registration path:

1. Require the canonical workflow to read the current task with outputs omitted,
   follow every cursor to the oldest page, preserve the current app title, and
   pass the exact oldest user text as the initial prompt.
2. Run `add <project>` with a fixture current session and require a
   CLI-generated canonical UUIDv4, main kind, null parent lineage, active
   status, exact project/title, normalized immutable description, and exactly
   one `thread.created` rollout.
3. Retry the exact command and require the same logical ID, unchanged rollout
   history, and no repeated `OnCreate` prompt.
4. Require project, title, and description conflicts to fail without mutation,
   and require a session already registered as child kind to be rejected.
5. Require the workflow to create, fork, rename, pin, archive, and message no
   Codex task, and to consume newly returned `OnCreate` prompts only in the
   invoking task.

## main-dispatch-lineage

Scenario version: 6

Before creating the live child task:

1. Require the canonical and installed skill to specify current-thread main
   designation: no create, fork, or follow-up message call; pin the invoking
   task; register it directly with null lineage.
2. Generate a logical creation ID and register it with the invoking Codex
   session ID as `kind = main`, with the source project
   basename, the naming-scheme default `⭐ agtask`, and an explicit initial
   prompt whose normalized value is the stored description.
3. Require its title to match that default, its `session_id` to equal the
   invoking Codex session, and its `parent_session_id` to be null. Retain both
   IDs, the registration snapshot, and the main-designation contract in proof.
4. Only after main designation, create the real app-server child task, register
   it as `kind = child` in the same project, and require its parent session to
   equal the invoking main Codex session ID.

## layered-config-prompt-hooks

Scenario version: 5

Before the live lifecycle, use retained fixture directories rather than the
user's real configuration:

1. Write a home configuration containing every supported creation default and
   both prompt hooks.
2. Write a project configuration overriding selected defaults and `OnCreate`.
3. Require recursive precedence in this order: built-ins, home configuration,
   project configuration, explicit CLI flags.
4. Require the project `OnCreate` prompt to win and the unmentioned home
   `OnPreClose` and `OnPostClose` prompts to remain inherited.
5. Require native JSON booleans, derived environment/model fields, loaded
   source paths, and exact structured prompt entries.
6. Require configuration inspection and resolution to create no ledger or
   Codex turn, and retain the input documents and resolved results in proof.
7. Require resolution to return the required resolved title and strict typed
   bootstrap arguments: the main configuration keeps an inert canonical
   version-1 action trailer, while explicit child creation returns the exact
   version-2 registration trailer with a canonical UUIDv4 creation `id`, parent
   session, and project identity.

## bootstrap-arguments-v1

Scenario version: 3

Before the live lifecycle, invoke the installed hook against untracked fixture
IDs so no ledger state can authorize behavior:

1. Require an exact final canonical `{"pin":true,"title":"..."}` envelope at
   `UserPromptSubmit` to render a model-mediated
   `codex_app__set_thread_pinned` request and an independent
   `codex_app__set_thread_title` request containing the real hook session ID and
   exact resolved title.
2. Require the hook to return those requests through structured
   `hookSpecificOutput.additionalContext`, and require both rendered contracts to
   state idempotency, treat the title only
   as tool data, surface success or exact failure, and continue the task.
3. Require `pin=false` to suppress only the pin action while retaining rename.
4. Require wrong pin/title types, an empty title, duplicate or unknown keys,
   noncanonical JSON, unsupported versions, lookalike prose, non-final
   envelopes, and `SessionStart` payloads to render no bootstrap action.
5. Prove every hook process exits successfully and creates or mutates no ledger
   row.

## creation-bootstrap-v2

Scenario version: 3

Before parent-side reconciliation, run a real first turn against a materialized
Codex child and project its exact `UserPromptSubmit` payload through the source
hook adapter:

1. Require the canonical version-2 trailer to contain a pre-generated logical
   creation `id`, the exact parent session ID, project, title, and pin value.
   Version 1 remains action-only and cannot register an untracked task.
2. Require the hook to initialize the isolated ledger when necessary and, in
   one transaction, bind that logical ID to the real child `session_id`, append
   exactly one `thread.created` rollout, and append the normalized first user
   prompt under the logical ID and real Codex turn ID.
3. Require a delegation-shaped first turn with one XML entity layer to decode
   task text, JSON values, and trailer markers exactly once, without retaining
   control metadata in the description or rollout message.
4. Replay parent `register --id ... --session-id ... --status active` and
   logical-ID `record-turn bootstrap`
   fallback. Require both to be idempotent, return no repeated `OnCreate`
   prompt, and preserve the hook-first rows byte-for-byte.
5. Replay the observed title-generator failure with the copied session winning
   the hook race before the real session ID returned by `create_thread`.
   Require ordinary registration to remain strict, then reconcile with
   `register --authoritative-session`. Require the logical row to move to the
   returned real session, copied helper user/assistant rollouts to be removed,
   `session_rebound_from` to identify the copied session, and the bootstrap
   fallback to leave exactly one canonical initial user rollout.
6. Retain the logical creation ID, real and copied session IDs, turn IDs, hook output, hook-first snapshot,
   parent-registration snapshot, fallback snapshot, and chronological rollout
   evidence in proof.

## lifecycle-create-directive-close-hooks

Scenario version: 13

Run one real Codex app-server child task through these checkpoints against an
isolated proof-local ledger using the canonical schema. The runner must default
`AGTASK_DB` to the allocated proof directory so it never targets the user's
normal ledger:

1. Start an empty real Codex task, then start its first turn before parent-side
   registration using the exact directive and version-2 creation trailer.
   - Pre-generate and record the logical task ID, then record the real Codex
     session ID returned by the app server.
   - Project the byte-identical first prompt through the source hook and require
     the hook-first write snapshot to contain the exact logical task ID, session
     ID, parent session ID,
     child kind, project, title, description, `active` status, single creation
     rollout, and single real-ID user rollout.
   - Require the description to equal the normalized initial directive and
     remain immutable at every later checkpoint.
   - Require `parent_session_id` to equal the invoking Codex session ID exactly.
   - Require `kind = child` and `project` to equal the source project basename.
   - Require `status = active` and `closed IS NULL` after the accepted first
     prompt, with no synthetic `todo -> active` transition.
   - Require exactly one creation rollout: `meta / thread.created / thread.created`.
   - Require the parent registration retry to return no `OnCreate` prompt,
     because that prompt was already embedded in the accepted creation turn.
2. Have the orchestration harness, not the ledger CLI, send
   `Reply with exactly INTEG_LIFECYCLE_READY` plus a final canonical `pin=false`,
   proof-specific title, parent session ID, and project as the real first directive.
   - Record the real Codex turn ID.
   - Keep globally installed host hooks pointed at an unused proof-local path,
     then project the real user and assistant payloads through the source
     worktree's hook adapter into the isolated proof ledger.
   - Use the same race-safe bootstrap `record-turn` call as the task-creation workflow.
   - Require exactly one user rollout and one assistant rollout sharing that real turn ID.
   - Require the stored user message to be the directive and the assistant
     message to begin `INTEG_LIFECYCLE_READY`, followed only by any required
     bootstrap action result lines.
   - Require the bootstrap envelope to be absent from the thread description,
     rollout messages, and bootstrap reconciliation identity.
   - Require the title action request to target the real materialized child
     session and
     carry the proof-specific resolved title even though pinning is disabled.
   - Require `status = active` without an appended `status:todo->active` row.
   - Require the assistant result not to replace the original description.
3. Prepare closure with the installed
   `close --session-id ... --prepare --if-tracked` CLI command.
   - Require one atomic exact-project claim, an opaque fencing token, a
     five-minute lease owned by the logical task ID, `status = merging`, and one new
     `status:active->merging` meta rollout.
   - Require the prepare JSON to surface the exact inherited home
     `OnPreClose` prompt only for the claimed owner, without persisting or
     executing it.
4. Have the orchestration harness consume the returned `OnPreClose` prompt as
   a real Codex turn.
   - Require one user rollout containing `Reply with exactly
     INTEG_PRE_CLOSE_READY` and one assistant rollout containing
     `INTEG_PRE_CLOSE_READY`, both sharing the real pre-close turn ID.
   - Require the task to remain `merging` with no close timestamp and the
     claim token unchanged across an explicit heartbeat.
5. Close with the installed `close --if-tracked --merge-token <token>` CLI
   command.
   - Require `status = done` and `updated = closed` with a non-null close timestamp.
   - Require two new meta rows at the close timestamp, in order:
     `status:merging->done`, then `finalization:completed`, and require the
     project claim to be deleted in the same transaction.
   - Require distinct, nonempty event IDs for the two finalization rows.
   - Require the creation, directive, and pre-close checkpoint rows to remain byte-for-byte equal as a prefix of the final chronological history.
   - Require the close JSON to surface the exact inherited home `OnPostClose`
     prompt after commit without persisting or executing that prompt.
6. Have the orchestration harness consume the returned `OnPostClose` prompt as a
   real Codex turn.
   - Project its real user and assistant payloads through the same source hook
     adapter rather than relying on an independently installed runtime copy.
   - Require one user rollout containing `Reply with exactly
     INTEG_POST_CLOSE_READY` and one assistant rollout containing
     `INTEG_POST_CLOSE_READY`, both sharing the real post-close turn ID.
   - Require the already-finalized rollout history to remain an exact prefix.
   - Require the thread to remain `done` with the original close timestamp.

The structured proof must retain source revision, CLI and Codex paths,
configuration fixtures and precedence results, parent session ID, logical task
ID, child session ID, turn ID,
every checkpoint thread snapshot, both pending close prompts, both hook turn
IDs, and the full chronological rollout list after post-close delivery.

The automated suite that gates this live lifecycle must also cover clean
one-shot registration, symmetric bootstrap reconciliation, a Stop hook that
arrives before bootstrap verification, incompatible register prompt/description
values, and a final answer beginning `Yes.`. In every case the normalized
initial prompt remains the task description.

## dashboard-html

Scenario version: 14

After the live child task is finalized:

1. Give the live child a proof-specific title so retained rows from earlier
   proofs cannot match the current dashboard assertions. Attach one proof-local
   text file, require its frontmatter status to match the finalized task, and
   retain its resolved path plus `vscode://file` projection.
2. Run `dashboard --json` through the installed CLI, narrowed by the exact
   project, parent session ID, and proof-specific child title. Require all six canonical status
   groups, the finalized child only in `done`, its logical ID, session ID,
   parent session ID, remaining dashboard projection fields, selected
   filter/search/sort state, and global facets containing
   the known project, parent, and lifecycle statuses.
3. Run a second JSON snapshot with `--status done` and require only the selected
   done group, proving status-filter behavior independently of default grouping.
4. Register a dedicated active dashboard-status fixture in the proof ledger.
   Keep it separate from the finalized live child and lifecycle main task. Move
   it through `blocked` to the terminal `done` status, require the shared
   `closed`/`updated` timestamp, and retain both transition events.
5. Start the installed `dashboard --no-open` server with the same filters. Read
   its flushed URL without retaining its token, require numeric loopback plus an
   ephemeral port and opaque token path, and fetch the dashboard HTML, shared
   CSS, dashboard JavaScript, task-detail HTML, task-detail JavaScript,
   dashboard API, and task-detail API routes.
6. Require exact media types, no-store/no-referrer/nosniff headers, the HTML
   content security policy, the right-side filter trigger, active-filter bar,
   filter-bar plus action, registry-driven field/value menu, encoded
   token-scoped detail routes on pointer-clickable task rows with native table
   semantics, while title links remain encoded `codex://threads/<session-id>`
   deep links with keyboard activation. Require attached tasks to render
   `file` badges in both list and detail views, linked through encoded
   `vscode://file` URLs. Require `j`/`k` active-row navigation, `x` selection,
   visible row checkboxes and selected state, and the `s` status picker acting
   on the selected set or the active/hovered row when no selection exists.
   Require its Todo/Active/Blocked/Done/Drop choices, its single-row
   expected-status guarded PATCH route, and its token-scoped bulk PATCH route.
   Require no task values in executable assets and dashboard API parity with the
   CLI JSON snapshot.
7. PATCH the dedicated fixture from active to blocked with the exact loopback
   origin, JSON media type, rendered `expected_status`, and requested `status`.
   Require the canonical nine-field task projection, one
   `status:active->blocked` meta rollout sharing the updated timestamp, and a
   stale expected-status retry that returns conflict without another write.
   Register a second active status fixture. Send a two-row bulk PATCH with one
   stale expected status and require conflict with neither row changed, then
   retry with both current expected statuses and require both rows to reach
   Done in one successful response. Require `closed = updated` plus ordered
   `status:blocked->done` and `status:active->done` evidence. Require the response
   to contain no hook prompt, merge-claim, or finalization payload and the ledger
   to contain no merge claim or `finalization:completed` event for the fixture.
8. Require the task-detail view to expose title, description, Timeline, Created,
   Updated, Session ID, and Files structure, with Session ID rendered as an encoded
   `codex://threads/<session-id>` deep link. Require its API to return the exact
   logical and session identities and description plus only `created`, `role`, and `message` for
   every rollout in reverse chronological `(created, id)` order, plus the exact
   attachment projection.
9. Interrupt the server cleanly, require exit status zero, and prove the schema
   version plus the known main/child thread and rollout rows are unchanged while
   the dedicated fixtures contain only the expected status mutations.

The structured proof must retain only redacted origin, route, header, response,
shutdown, snapshot, status-transition, and unaffected-lifecycle evidence. It
must never retain the token, full URL, or query string.

## current-task-rename

Scenario version: 2

Before the live child lifecycle, exercise current-task rename against a
separate proof-local ledger and a modeled Codex app title boundary:

1. Register one tracked fixture. Invoke `rename --session-id ... --title ...`
   without `--apply` and require a read-only plan containing the exact logical
   and session IDs, current/requested titles, current `updated`, deterministic
   token, and structured `codex_app__set_thread_title` action. Logical `--id`
   is not accepted.
2. Pass the returned action through a fake app adapter. On simulated app
   failure, require no apply call and no ledger write. On success, require the
   action log to precede `rename --apply <token>`.
3. Require accepted apply to atomically update the ledger title and `updated`
   with one `title:renamed` meta rollout at the same timestamp, and require FTS
   to find only the new title.
4. Repeat with identical current and requested titles. Require planning to
   still emit the idempotent app action and accepted apply to return
   `changed: false` with unchanged timestamp and rollout history.
5. Create two plans from the same row, let the competing app action and apply
   win, then require the stale token to fail under the write lock without
   another ledger write. Re-read the current row and pass that title through
   the fake app adapter as compensation; require app and ledger titles to
   converge on the concurrent winner rather than the original title.
6. Require the workflow contract to use the planned title only when the row
   cannot be re-read and explicitly report title divergence with both errors
   if compensation cannot restore consistency.

The structured proof retains the isolated ledger path, workflow-contract
checks, fake app call and operation logs, read-only and failed-app snapshots,
successful and idempotent apply snapshots, stale-token error, compensation
target, final row, and rename rollout evidence. It does not claim that the
SQLite CLI can call or transact with the Codex app.

## archived-session-audit

Scenario version: 2

Before the live child lifecycle, exercise the audit protocol against a separate
proof-local ledger:

1. Register active fixtures for archived, current, missing, and failed Codex
   lookup outcomes plus one blocked archived fixture. Require discovery to emit
   lookup requests for every auditable fixture, keyed by its real `session_id`,
   with no plan token or ledger mutation.
2. Supply one strict version-1 observation document. Require the positively
   archived active and blocked sessions to be the only affected tasks, the
   missing and failed sessions to remain explicitly unresolved, the current
   session to remain unaffected, and an observation for a non-auditable session
   to be ignored.
3. Require planning to return `confirmation_required` and a 64-character plan
   token while preserving every task row byte-for-byte. Require the canonical
   skill workflow to show the exact affected set and demand explicit user
   confirmation rather than treating silence or unavailable confirmation as
   consent.
4. Apply the unchanged token and require the archived active and blocked
   fixtures to reach `done` with close timestamps and ordered
   `status:<previous>->done` / `archival:codex-thread-archived` meta evidence.
   Current, missing, and failed fixtures must retain their prior states.
5. Repeat planning with the same observations and require a read-only complete
   result with no candidates or token, proving safe reruns.

The structured proof retains the isolated audit ledger path, discovery, plan,
apply, archived row/history, and rerun results. The observation document is
synthetic proof of the CLI boundary; live Codex archive reads remain owned by
model-mediated orchestration and must not be inferred inside the CLI.

## Version rules

- Bump the suite version when shared setup, runner behavior, or proof JSON changes.
- Bump a scenario version whenever its commands, assertions, lifecycle expectations, or external boundaries change.
- Add a scenario when the product adds a lifecycle state or integration boundary not covered above.

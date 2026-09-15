# Audit archived Codex tasks

Use this workflow when the user invokes `$agtask audit`. Preserve the ownership
boundary: the Codex app owns archive state and the selected CLI backend owns
ledger state. Local mode audits local SQLite; Sites mode audits hosted D1 and
never falls back to the local ledger. Never infer archive state from a missing
list result, task age, title, or conversation status.

Invoking this workflow, directly or through an authorized cleanup run,
authorizes marking positively verified archived Codex tasks `done` in the
ledger without a separate approval. A request for preview or read-only audit
stops after planning. Never archive Codex tasks or change unresolved rows as
part of this reconciliation.

1. Run `python3 ./scripts/agtask audit --json` using the capture and recovery
   procedure below. It returns every nonterminal
   ledger row whose status is `todo`, `active`, or `blocked`, plus one lookup
   request per real `session_id`; it does not mutate. It excludes `merging`
   rows because their fenced close workflow owns that transition.
2. Resolve every requested session through Codex app thread APIs. Prefer an
   exact per-session read so an archived thread can be distinguished from a
   missing session. Do not interpret runtime load states such as `active`,
   `idle`, or `notLoaded` as archive state. If the exact app read omits archive
   state, query the current Codex-owned state database read-only for the exact
   `threads.id` and use only its `archived` field. Treat multiple plausible
   state databases or a failed query as `error`; treat an exact missing row as
   `missing`. Classify each request as `archived`, `not_archived`, `missing`,
   or `error`, and preserve the exact failure diagnostic in `detail`. Never
   infer archive state from a missing list result, task age, title, or
   conversation/runtime status.
3. Pass one version-1 observation document to
   `audit --observations-json '<json>' --json`:

   ```json
   {
     "schema_version": 1,
     "sessions": [
       {"session_id": "<codex-session-id>", "state": "archived"},
       {"session_id": "<codex-session-id>", "state": "not_archived"},
       {"session_id": "<codex-session-id>", "state": "missing"},
       {
         "session_id": "<codex-session-id>",
         "state": "error",
         "detail": "<exact lookup error>"
       }
     ]
   }
   ```

4. Retain the exact `affected_tasks` set and every `unresolved` lookup in the
   run report. If no tasks are affected, stop; report unresolved lookups rather
   than calling an incomplete audit successful. Stop here for a preview.
5. For affected tasks, repeat every Codex lookup and build a fresh observation
   document, then submit it with `--apply <plan_token> --json` without asking
   for separate user confirmation. The CLI
   recomputes the token under its SQLite write lock or transactional D1 batch.
   If archive results, the active set, or an affected row changed, do not force
   the old plan: build a new plan and refresh once more. Stop and report state
   churn if that replacement plan also changes. Never reuse stale observations
   or substitute a token from another run.
6. Verify the apply result and the affected ledger rows are `done`. Report
   tasks changed and all unresolved lookups or apply failures.

The existing CLI protocol calls an unapplied candidate plan
`confirmation_required`; this is the plan-token handshake, not a requirement
for another human approval in this skill. Use JSON output and retain the
plan-token and archive-state checks.

The apply phase moves only still-auditable, positively observed archived
sessions to the ledger's existing terminal `done` state. It sets `closed`,
appends `status:<previous>->done` and
`archival:codex-thread-archived`, and does not run close hooks or acquire a
merge claim because Codex is already archived. Repeated discovery and planning
are read-only; repeating an applied audit is a no-op once no matching
auditable task remains. Logical `id` stays ledger-owned and Codex lookups
always use `session_id`.

## Capture and recover command results

For each discovery, observation-plan, or apply invocation, retain complete
stdout, stderr, and the exit status in a fresh private directory under the
run's writable artifact root. Parse the saved JSON, not truncated terminal
output. For discovery, run this from the skill directory:

```sh
umask 077
AUDIT_RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/agtask-audit.XXXXXX") || exit 125
test -n "$AUDIT_RUN_DIR" && test -d "$AUDIT_RUN_DIR" || exit 125
printf '%s\n' "$AUDIT_RUN_DIR"
python3 ./scripts/agtask audit --json > "$AUDIT_RUN_DIR/stdout.json" 2> "$AUDIT_RUN_DIR/stderr.txt"
AUDIT_EXIT=$?
printf '%s\n' "$AUDIT_EXIT" > "$AUDIT_RUN_DIR/exit-status"
exit "$AUDIT_EXIT"
```

- Require exit status `0` and complete, parseable JSON before declaring the
  phase successful. Summarize counts in the terminal and retain the full file.
- If execution or polling fails, inspect the saved files first. An absent exit
  marker means completion is unknown; an execution tool's approval/network
  error is not a CLI or Sites response.
- For read-only discovery or planning interrupted by sandbox access or
  `Network request disconnected ... before approval could complete`, retry
  once through the execution tool's supported `require_escalated` review with
  the same CLI, arguments, configured backend, and a fresh capture directory.
  This is recovery within the same audit workflow. If the current session has
  already established that this command needs escalation, request it on launch.
  Honor review denials; do not change credentials or switch backend modes.
- Do not blindly repeat an interrupted `--apply`. Recover its completion
  evidence and reconcile fresh authoritative state before any further mutation.

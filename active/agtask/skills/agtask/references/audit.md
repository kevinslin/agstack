# Audit archived Codex tasks

Use this workflow when the user invokes `$agtask audit`. Preserve the ownership
boundary: the Codex app owns archive state and the selected CLI backend owns
ledger state. Local mode audits local SQLite; Sites mode audits hosted D1 and
never falls back to the local ledger. Never infer archive state from a missing
list result, task age, title, or conversation status.

1. Run `python3 ./scripts/agtask audit --json`. It returns every nonterminal
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

4. Show the returned `affected_tasks` and every `unresolved` lookup to the
   user. If there are affected tasks, ask for explicit confirmation to archive
   exactly that displayed set. Do not treat silence, unavailable confirmation,
   an earlier general instruction, or approval of a different set as consent.
5. If the user declines or confirmation is unavailable, stop. The planning
   command has made no ledger changes.
6. After explicit confirmation, repeat every Codex lookup and build a fresh
   observation document. Submit it with `--apply <plan_token> --json`. The CLI
   recomputes the token under its SQLite write lock or transactional D1 batch.
   If Codex archive results,
   the active set, or an affected row changed, it fails closed or returns no
   candidates; show any new plan and ask again. Never reuse the
   pre-confirmation observations without refreshing them or substitute a token
   from another run.

The apply phase moves only still-auditable, positively observed archived
sessions to the ledger's existing terminal `done` state. It sets `closed`,
appends `status:<previous>->done` and
`archival:codex-thread-archived`, and does not run close hooks or acquire a
merge claim because Codex is already archived. Repeated discovery and planning
are read-only; repeating an applied audit is a no-op once no matching
auditable task remains. Logical `id` stays ledger-owned and Codex lookups
always use `session_id`.

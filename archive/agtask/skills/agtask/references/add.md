# Add the current Codex task

Use this workflow only for `$agtask add <project>`. It registers the invoking
Codex task in the ledger without changing the task in the Codex app.

The `<project>` argument is required. Preserve it exactly and require it to be
nonempty with no surrounding whitespace. This route does not create, fork,
rename, pin, archive, or message any task.

1. Resolve the invoking Codex task's authoritative session ID. Call
   `read_thread` for that exact task with `includeOutputs: false` and
   `turnLimit: 10`. Preserve the returned `thread.id` as
   `<current-session-id>` and the returned `thread.title` as
   `<current-title>`. Require the returned ID to equal the invoking task ID.
   Require the title to be nonempty, one line, and free of surrounding
   whitespace. Do not derive or replace the title.

2. Follow `page.nextCursor` with another `read_thread` call for the same task,
   again setting `includeOutputs: false`, `turnLimit: 10`, and the exact cursor.
   Continue until `page.hasMore` is false and `page.nextCursor` is null. Cursors
   page toward older turns and every page is `newest_first`; do not stop after
   the first page when an older page exists.

3. In the oldest page, inspect turns from oldest to newest and select the first
   `userMessage` item. Extract the exact `text` value from its text content as
   `<initial-prompt>`. Preserve every byte, including whitespace and newlines;
   do not summarize, unwrap delegation, combine it with later messages, or use
   a preview. Stop without writing if no nonempty oldest user text exists.

4. Run the source CLI from the skill directory:

   ```text
   python3 ./scripts/agtask add <project> \
     --session-id <current-session-id> \
     --title <current-title> \
     --initial-prompt <initial-prompt> \
     --json
   ```

   Pass every value as a literal argument. The CLI generates a canonical
   UUIDv4 logical ID for a new row and registers the session as `kind = main`,
   `parent_session_id = null`, and `status = active`. The normalized oldest
   prompt becomes the immutable description. An exact retry looks up the row
   by session, reuses its logical ID, and verifies the same kind, project,
   title, and description without appending another `thread.created` rollout.
   A child row or any metadata conflict is a hard error.

5. Treat the successful JSON as the verification snapshot; do not reread a
   successful write. Require:

   - a canonical UUIDv4 `id`;
   - `session_id` equal to `<current-session-id>`;
   - `parent_session_id` equal to `null`;
   - `kind` equal to `main`;
   - `project` and `title` equal to the exact inputs;
   - `description` equal to the CLI normalization of `<initial-prompt>`;
   - `status` equal to `active` for a newly added task;
   - exactly one `meta / thread.created / thread.created` rollout for a new
     task, while an exact retry retains the existing rollout history; and
   - `hook_prompts` containing configured `OnCreate` data only when this call
     created the row.

6. Consume each returned `OnCreate` prompt as the next instruction in this
   current task, in array order. The CLI only returns prompt data; it does not
   execute callbacks. Do not send the prompt to another task.

If the CLI result is malformed or its process outcome is ambiguous, run one
targeted `show --session-id <current-session-id> --json` error-path read.
Continue only when that snapshot proves the invariant above. Retry the
identical `add` command once only when the read proves the session is
untracked. Do not retry a definitive validation, child-row, or metadata
conflict.

Report the logical task ID, current session ID, project, preserved title,
active status, and whether the row was newly added or already tracked. Report
every exact error when tracking cannot be verified.

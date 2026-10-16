# Attach a file to the current Codex task

Use this workflow only for `$agtask attach <file>`. It links one existing local
UTF-8 text file to the invoking tracked task. It does not create, rename, pin,
archive, message, or change the status of a Codex task.

1. Preserve the supplied file argument exactly. The source CLI resolves it
   relative to its current working directory, follows it to an absolute path,
   and requires an existing regular UTF-8 text file.

2. Resolve the invoking Codex task's authoritative session ID. Call
   `read_thread` for that exact task with `includeOutputs: false` and
   `turnLimit: 1`. Preserve the returned `thread.id` as
   `<current-session-id>` and require it to equal the invoking task ID.

3. From the skill directory, run:

   ```text
   python3 ./scripts/agtask attach <file> \
     --session-id <current-session-id> \
     --json
   ```

   Pass both values as literal arguments. The CLI resolves the tracked row and
   updates or creates top-level YAML frontmatter fields:

   - `status` receives the task's current ledger status at attach time;
   - `source` receives `codex://threads/<current-session-id>`.

   Existing frontmatter and body content are preserved. Missing frontmatter is
   created. Unterminated frontmatter, duplicate top-level `status` or `source`
   keys, and non-UTF-8 files fail without a ledger attachment. The original
   file mode is preserved.

   In the same operation, the CLI stores the resolved absolute path as a task
   attachment. The first attachment advances the task's `updated` timestamp
   and appends one `attachment:added` meta rollout. Retrying the same resolved
   path is idempotent; it repairs drifted frontmatter but does not append
   another attachment event.

4. Treat the successful JSON as the verification snapshot. Require:

   - `session_id` equal to `<current-session-id>`;
   - `attachment.path` equal to the resolved absolute file path;
   - `attachment.url` beginning with `vscode://file/`;
   - exactly one matching entry in `files`; and
   - `status` unchanged from the selected ledger task.

If the CLI result is malformed or its process outcome is ambiguous, run one
targeted `show --session-id <current-session-id> --json` error-path read. Do
not retry a definitive file, frontmatter, selector, or schema error.

Report the attached path, copied status, and whether the ledger relationship
was newly created or already present.

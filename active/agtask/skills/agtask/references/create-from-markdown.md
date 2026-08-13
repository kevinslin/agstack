# Create a tracked task from a Markdown note

Use this composite workflow for `$agtask <file.md>` or
`$agtask <file.markdown>`. It reads an existing note, creates exactly one
tracked child from the note's actual instructions, and attaches that same note
to the new child. It does not attach the note to the invoking parent.

1. Resolve the supplied Markdown path relative to the invoking task's current
   working directory, preserving spaces. Require an existing regular,
   readable UTF-8 Markdown file. If an explicit Markdown path is missing,
   ambiguous, or unreadable, stop before creating a child; do not reinterpret
   the filename as an ordinary prose task.

2. Use `$dendron` to read the note and only the linked Dendron context relevant
   to understanding its task. Preserve its existing frontmatter, title,
   instructions, acceptance criteria, and operational constraints. Reading an
   existing note does not authorize creating another Dendron note, creating a
   Linear issue, editing linked notes, or implementing its instructions in the
   parent task.

3. Derive a concise title/topic from the note's frontmatter title, first
   heading, or filename. Build a self-contained child task from the actual
   note content and necessary linked context. Include the resolved source
   path so the child can reopen the original. Preserve any explicit creation
   modifiers supplied alongside the Markdown path.

4. Read [`./create-advanced.md`](./create-advanced.md) completely and execute
   the default forked-child workflow once with the resolved note-backed task.
   For an explicitly requested clean child, follow [`./create.md`](./create.md)
   instead.
   Preserve all existing project, host, sidebar, model, hook, and registration
   behavior. Never call the selected task-spawning tool a second time.

5. When the result contains a real `threadId`, first complete the normal child
   registration and initial-rollout verification. Then read
   [`./attach.md`](./attach.md) completely and apply its existing attachment
   contract to the **new child session**, not the invoking session:

   ```text
   python3 ./scripts/agtask attach <resolved-markdown-path> \
     --session-id <child-thread-id> \
     --json
   ```

   Pass the path and child session ID as individually quoted arguments.
   Require the returned `session_id` to equal `<child-thread-id>`, the
   attachment path to equal the resolved Markdown path, and exactly one
   matching file entry. The supported attachment command updates only the
   note's managed `status` and `source` frontmatter fields; `source` must point
   to `codex://threads/<child-thread-id>`. Preserve the rest of the note.

6. When creation returns only `clientThreadId`, preserve the queued child ID
   and report that attachment is pending until a real child session exists.
   Never attach to the parent or treat the queued client ID as a session ID.
   Once the actual child session is available and registered, attach the note
   to that exact session using the same command above without creating a
   second child.

7. If attachment fails after successful creation, retain and report the
   existing child link, resolved note path, and exact attachment error. Do not
   create a replacement child. On an ambiguous attachment outcome, perform
   only the targeted error-path read described in `attach.md`.

Return the tracked child task link, logical task ID, attached Markdown path,
and attachment verification or queued/pending state.

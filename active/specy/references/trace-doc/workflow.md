# Logic Trace Doc Workflow

## Use When

Use for `logic trace`, `trace doc`, `execution trace cheatsheet`, or a
`*.trace.md` document. A logic trace is a cheatsheet for a human who needs to
understand the main execution path quickly. It is not a detailed flow doc.

Prefer `flow-doc` when the user asks for a diagram, phase-by-phase explanation,
ownership boundaries, or debugging and verification guidance.

## Output and Naming

Resolve `$mem` before choosing a durable-document destination. Its selected
schema owns the output path, filename, and required file shape. Otherwise use
`$DOCS_ROOT/flows/{trace-name}.trace.md`, unless the user specifies another
destination. Choose a concise behavior-based kebab-case name.

## Document Contract

Use `./references/trace-doc/template.md` for new documents. Its canonical
sections, in order, are `Overview`, `Logic`, `Exceptions`, `State`, `Manual
Notes`, and `Changelog`.

- **Overview:** Use one or two sentences to name the behavior and its scope.
- **Logic:** Use one `ts` code fence containing one long entrypoint function.
  Follow the main execution path from top to bottom. Preserve exact function
  names, important identifiers, and enough log text to grep the source. Collapse
  construction, plumbing, and nested implementation details. Short comments
  that orient the reader are useful. Keep normal-path branches that materially
  change execution; in particular, keep `if not request.dry_run` when dry run is
  the exceptional case.
- **Exceptions:** List only important early exits or stop conditions. Do not
  expand exception handling or failure branches into the main logic.
- **State:** List only persistent cursor, deduplication, incremental, or other
  state facts needed to understand the flow.
- **Manual Notes:** Preserve the heading and complete user-owned body exactly
  when revising an existing document.
- **Changelog:** Record the local `YYYY-MM-DD HH:MM` timestamp, change
  description, current session ID, and current Git SHA.

Do not add diagrams, numbered phases, source-anchor catalogs, field lists, API
inventories, handler inventories, per-record internals, or debugging sections
unless the user explicitly asks for them. Bias toward too little detail.

## Instructions

1. Resolve the output path according to **Output and Naming**.
2. Read the actual entrypoint and only the main callees needed to identify the
   primary execution path, important log text, exits, and persistent state.
3. Copy the template to the resolved output path, adapting its shape only when
   a selected `$mem` schema requires it.
4. Draft the smallest useful main path first. Use `$sudocode` to express it as
   one long function in a single `ts` code fence. Keep exact source identifiers
   and grepable log fragments, and add only short orienting comments.
5. Move exceptional exits and persistent-state facts into `Exceptions` and
   `State`; omit other details.
6. Preserve `Manual Notes`, replace every template placeholder, and resolve the
   active session through `$dev.llm-session` for complete changelog provenance.
7. Verify that the trace has one main function, reads top-to-bottom, contains
   grepable names or log fragments, and has no unsolicited implementation
   expansion. Remove detail when uncertain whether it helps the cheatsheet.

## Revision Instructions

1. Preserve the existing level of detail, comments, log text, section shape,
   and all `Manual Notes` content.
2. Apply only the requested change. If the user supplies agreed trace text to
   write into a file, preserve that logic rather than enriching it from source.
3. Expand the trace incrementally only when the user explicitly asks. A source
   correction may adjust the affected line, but it is not permission to widen
   the surrounding trace.
4. After editing, remove any newly introduced detail that was not needed for
   the request. Bias toward too little detail.
5. Update `updated`, `last_updated_session`, and `Changelog` with the current
   local timestamp, active session ID, and Git SHA.

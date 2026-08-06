# Flow Doc Workflow

## Use When

Use for any flow-doc intent, including `flow doc`, `flow docs`, `flowdoc`, `call
path doc`, or `execution flow doc`. Document the runtime behavior of a startup,
request, job, command, UI action, or feature without describing code line by
line.

## Output and Naming

Resolve `$mem` before choosing a durable-document destination. Its selected
schema owns the output path, filename, and required file shape. Otherwise use
`$DOCS_ROOT/flows/{flow-name}.md`, unless the user specifies another destination.

Choose a concise behavior-based kebab-case name, or preserve an existing
`core.*`, `topic.*`, or `ref.*` convention. For PR-scoped documents, use
`pr-<number>-<flow-name>` unless the selected schema or repository convention
requires otherwise.

## Document Contract

Use `./references/flow-doc/template.md` for new documents. Its canonical
sections, in order, are `Overview`, `Entry Points`, `Flow`, `Execution Trace`,
`Debugging and Verification`, `Related docs`, `Manual Notes`, and `Changelog`.
Add `Notes` only when useful details do not belong at their decision points.

- **Overview:** State the behavior, external trigger, purpose, and where the
  documented lifecycle stops.
- **Entry Points:** Name the trigger, required state/context or permissions,
  and one to three concrete source entry points.
- **Flow:** Use `$dev.diagram mermaid general-flow` to create a Mermaid `graph
  TD` diagram. Show the main path and branches that materially change its
  outcome; omit trivial guards and implementation-only conditions.
- **Execution Trace:** Load `$docy` `ref/execution-trace`. Use runtime-ordered,
  numbered `###` phases with precise file/function pointers. Explain state
  transitions, snapshot/freeze points, ownership boundaries, external calls,
  material branches at their decision points, terminal effects, and downstream
  handoffs. Add nested steps only when they improve comprehension. Invoke
  `$sudocode` only when compact pseudocode clarifies non-obvious logic; render
  it in a `ts` code fence.
- **Debugging and Verification:** Provide actionable logs, metrics, commands,
  failure signatures, or observable outcomes. State `None identified` if no
  relevant evidence exists.
- **Related docs:** Link adjacent lifecycle/phase flows and relevant
  architecture, design, PR, or debugging documentation.
- **Manual Notes:** Preserve the heading and complete user-owned body exactly
  when revising an existing document.
- **Changelog:** Record the local `YYYY-MM-DD HH:MM` timestamp, change
  description, current session ID, and current Git SHA.

Keep isolated flow documents isolated: explicitly capture entry assumptions,
internal snapshot/freeze points, the exit/handoff contract, and links to
adjacent flow documents rather than merging separate lifecycle phases. Keep
repo-internal Markdown links portable and repo-relative.

## PR-Scoped Flow Docs

A document is PR-scoped when the request targets a particular pull request or
behavior changed by one. Resolve its PR number, title the document `# PR
<number>: <Feature> Flow`, and add `pr: <number-or-url>` beside `created`,
`updated`, and `last_updated_session` in frontmatter. Prefer the number for a
same-repository PR and the full URL for ambiguous or cross-repository PRs.

## Instructions

1. Resolve the output path according to **Output and Naming**. Review relevant
   existing flow, architecture, design, and operational documentation.
2. Read the source. Identify the trigger, entry assumptions, runtime phases,
   decisions, state changes, snapshot points, ownership boundaries, external
   calls, failure outcomes, terminal effect, and next-flow handoff.
3. Copy the template to the resolved output path, adapting its content to any
   `$mem` schema-required document shape without overriding the schema path.
4. Set `created`, `updated`, and `last_updated_session`; resolve the active
   session using `$dev.llm-session`. Add PR metadata only when applicable.
5. Write each section according to **Document Contract**. Keep explanations
   proportional to the behavior; do not add nested headings, pseudocode, or
   `Notes` merely to satisfy a format.
6. Preserve `Manual Notes`, replace every template placeholder, add complete
   session/Git provenance to `Changelog`, and check repo-internal link targets.
7. Run `python3 ./scripts/validate_flow_doc.py --kind flow-doc --doc
   "<resolved-output-path>"` from this skill root. Resolve every error before
   handoff.

## Revision Instructions

1. Read the existing document and preserve useful structure, detail, and all
   `Manual Notes` content. Existing `Sequence Diagram` and `Observability`
   headings remain valid; do not rename them solely to match the new template.
2. Re-read source for the changed behavior and make targeted corrections or
   additions. Preserve a user-requested existing diagram format.
3. Update `updated`, `last_updated_session`, and `Changelog` with the current
   local timestamp, active session ID, and Git SHA.
4. Validate the actual resolved document path and fix all reported errors.

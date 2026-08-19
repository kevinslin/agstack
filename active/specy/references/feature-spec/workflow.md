# Feature Spec Workflow

## Use When

- The task requires durable, implementation-directed planning.
- Architecture or design decisions should be documented before coding.
- The work has a concrete behavioral contract, integration boundary, or
  verification requirement worth recording.
- The user explicitly asks for an execution plan, project plan, or feature spec.

## Template

- `./references/feature-spec/template.md`

## Output Location

- `$DOCS_ROOT/specs/{NN}-{title-in-kebab-case}.md`

## Instructions

1. Review related docs under `$DOCS_ROOT/specs/`, archived specs under `$DOCS_ROOT/specs/.archive/`, and `$DOCS_ROOT/flows/` to align naming and known behavior.
2. Choose the next feature-spec filename with a monotonic two-digit integer prefix: scan `$DOCS_ROOT/specs/` and `$DOCS_ROOT/specs/.archive/` for filenames matching `[0-9][0-9]-*.md`, choose `max(existing prefix)+1`, and start at `01` when none exist. Do not reuse gaps left by archived, deleted, or renamed specs.
3. Choose a title slug that stays within the `{NN}-{topic}.md` filename format and includes a qualifier when needed to avoid collisions with sibling specs.
4. Copy `./references/feature-spec/template.md` to the output location and
   remove optional sections that the task does not require.
5. Fill `Problem and Decision`, `Scope`, and `Contract` from current task and
   repository evidence. Record relevant existing behavior, ownership, interfaces,
   non-goals, authorization, and failure behavior once where it affects the
   selected contract.
6. Before adding a field, type, status, reason, config option, or execution path,
   inspect the existing surface and identify the producer, consumer, and
   concrete need. Record only decisions necessary to explain the contract;
   snapshot, decision-table, and minimal-model headings are not required.
7. Put concrete work, affected files/services, and necessary dependencies under
   `Implementation`. Use ordered steps by default; add named phases only for
   independently useful outcomes or material sequencing constraints.
8. Put observable feature outcomes and their automated or manual proof together
   under `Verification`. Link a separate validation spec only when its larger
   matrix adds information the feature spec cannot represent clearly.
9. Add `Open Decisions` only for real unresolved choices. Record the owner,
   next action, or task link only when needed to resolve a blocking decision.
10. Add rollout, recovery, access, observability, or risk detail only when the
    specific change requires it. Place it beside the affected implementation
    step or contract instead of creating empty boilerplate sections.
11. If the repository uses beads for tracking, follow
    `./references/feature-spec/beads.md`.
12. When editing an existing spec, preserve `## Manual Notes` unless the user
    explicitly asks to change it.
13. Keep in-progress specs under `$DOCS_ROOT/specs/`. When the spec is complete,
    identify Markdown links pointing to it, then move it to
    `$DOCS_ROOT/specs/.archive/` without renaming it. Rebase relative links
    inside the archived spec, update its inbound references, and verify every
    affected local link resolves.
14. Resolve the current agent session id via `dev.llm-session` and include it,
    the current Git SHA, and a `YYYY-MM-DD HH:MM` timestamp in `## Changelog`.

## Authoring Requirements

- Required sections: `Problem and Decision`, `Scope`, `Contract`,
  `Implementation`, `Verification`, `Manual Notes`, and `Changelog`.
- `Open Decisions`, phases, decision tables, rollout, observability, access,
  and risks are conditional; omit them when they do not change implementation
  or verification.
- Keep normal feature specs approximately 80-150 lines. Exceed that range only
  when required contracts, independent delivery stages, or safety proof warrant
  the additional detail.
- Keep source links beside the decision or implementation step they support.
  Use project-root-relative links and avoid absolute local filesystem paths.
- In `Verification`, pair each material observable outcome or invariant with a
  concrete automated test or operational check.
- Create or link a separate flow doc only when ordering, state propagation,
  cache boundaries, or cross-component handoff is central to correctness.
- Record a concrete mitigation for any material risk that affects the selected
  contract or rollout.

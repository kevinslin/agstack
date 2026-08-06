---
name: specy
description: Create structured specs and code exploration docs.
version: 2.0.0
dependencies:
- dev.diagram
- dev.llm-session
- docy
- mem
- statsig
- sudocode
---

# Specy

This skill creates structured research artifacts for codebase exploration and feature work.

## When to Use This Skill

Use this skill when:

- Creating or updating any of the avilable document types
- Creating or updating system architecture docs for services or platforms
- Investigating a new technology, library, or approach before implementation
- Exploring unfamiliar parts of a codebase
- Comparing multiple solutions or approaches
- Documenting findings for future reference
- Creating formal research artifacts that can be shared with the team
- Documenting the lifecycle of a behavior or request flow in the codebase
- Drafting staff-level service design docs for new systems or services
- Drafting implementation-focused feature design docs for new capabilities or migrations
- Capturing reproducible change recipes from a current conversation or PR

## Hard Trigger Rule (Flow Docs)

If the request mentions any flow-doc intent (for example: `flow doc`, `flow docs`, `flowdoc`, `call path doc`, or `execution flow doc`), you must run this skill and follow the `flow-doc` workflow before drafting or revising content.
Only the `flow-doc` doc type is supported for flow docs. Do not route to old phase-based flow-doc material or alternate flow-doc doc-type names.

## Root Directory

All filepaths in this skill are relative to `$DOCS_ROOT` unless noted otherwise.
Default `$DOCS_ROOT` is `./docs` (relative to the project root directory).

When creating or updating a durable artifact such as a spec, flow doc, design doc, architecture doc, validation doc, recipe, runbook, or long-lived project note, invoke `$mem` before choosing `$DOCS_ROOT`. Use the selected `$mem` base root, schemas, optional base skill, and path style when the artifact belongs in persistent knowledge. Do this by artifact intent, not by whether the path contains `.mem`; memory roots may be any configured folder. Only use the default `./docs` root when the artifact is repo-owned documentation or the user names a concrete non-memory destination.
When `$mem` selects a schema node, that node owns the destination path and required file shape. `specy` may adapt its document content to fit that node, but it must not override the chosen filename, folder layout, or template because a doc type would normally live somewhere else.

## Available Document Types

Document types are listed here. Use the parenthesized doc-type key with the common workflow/template paths below.

- Architecture Docs (`architecture`): System-level architecture docs covering boundaries, components, interfaces, and key decisions.
- Research Briefs (`research-brief`): Structured technology/approach research with comparisons and recommendations.
- Flow Docs (`flow-doc`): Balanced flow documentation for specified code logic, combining a general-flow diagram, an execution trace, and targeted implementation details.
- State Docs (`state-doc`): Terminal-output mapping with predicates, required state, and derivation paths.
- Service Design Docs (`service-design-doc`): Staff-level service/system proposals covering architecture, APIs, reliability, and risks.
- Feature Design Docs (`design-spec`): Implementation-ready feature or migration designs with rollout/rollback planning.
- Feature Specs (Execution Plans) (`feature-spec`): Focused implementation plans covering the selected contract, concrete work, and verification; add phases, dependencies, and risks only when needed.
- Investigation Specs (`investigation-spec`): Structured debugging plans for competing root-cause hypotheses and evidence capture.
- Validation Specs (`validation-spec`): Validation coverage docs for automated and manual checks tied to specs.
- Report Notes (`report-note`): Concise report sidecars for source-backed findings, status, and open questions.
- Recipes (`recipe`): Reproducible step-by-step change instructions derived from conversation or PR context.
- Frequently Asked Questions (FAQ) (`faq-doc`): Reusable Q&A docs with concise answers and source citations.
- FAQ Specs (`faq-spec`): In-place FAQ additions that append a focused Q&A to the most recent research document type mentioned in the conversation.
- Vendor Docs (`vendor-doc`): Project-focused third-party library documentation summaries and topic references.

## Specification Style Ownership

Before creating, revising, or reviewing an `architecture`,
`service-design-doc`, `design-spec`, or `feature-spec`, invoke `$docy` and inject
`ref/spec`.

Docy owns specification prose, decision completeness, ownership and interface
clarity, example and diagram semantics, and review style. Specy owns doc-type
selection, source gathering, output paths, template shape, required sections,
execution details, preservation and lifecycle, and handoff artifacts. For
feature specs, retain the contract, repository touchpoints, concrete work, and
proof needed to implement the change. Use named phases only when independently
useful outcomes or material dependencies require them.

Do not copy Docy style rules into Specy workflows or templates. Keep Specy
instructions limited to artifact-specific requirements and mechanics.

## Common Instructions (All Doc Types)

0. For durable knowledge artifacts, resolve `$mem` first and report the selected base name, resolved root, and concrete output path. If no `$mem` base clearly matches and the user did not name a concrete non-memory destination, ask instead of guessing.
0a. If `$mem` resolves an existing folder-based spec unit (for example `specs` `specs/{NN}-{topic}/`) and the user asks to place a report "under spec 30" or similar, treat that folder as the target container. Do not create a new numbered spec just because the requested doc type is a research brief.
0b. If `$mem` resolves a sidecar node such as `specs/reports/{{report}}`, recast the content into that node's required shape. For research output, adapt findings into the selected schema template instead of copying the default `research-brief` headings verbatim.
1. Find the requested doc type workflow at `./references/[doc-type]/workflow.md`.
2. Follow the `Instructions` header in that workflow to do the implementation.
3. Copy `./references/[doc-type]/template.md` to the requested output location before filling in content.
4. For in-place doc types (currently FAQ Specs), use the template as an insertion snippet instead of creating a new file.
5. Before finalizing any created or revised document, resolve the current agent session id via `$dev.llm-session` and replace the changelog timestamp and session placeholders. Changelog timestamps must include date, hour, and minute in `YYYY-MM-DD HH:MM` format.
6. For links that point to files inside the current repo, prefer repo-relative markdown targets instead of absolute local checkout or worktree paths. Do not emit `/Users/...` or similar machine-local link targets under `$DOCS_ROOT` unless the document is intentionally pointing outside the repo.

### Manual Notes Preservation

Before editing an existing document, search for a `## Manual Notes` section and any preservation marker such as `[keep this for the user to add notes. do not change between edits]`.

When such a section exists:

1. Treat the entire `## Manual Notes` section body as user-owned content.
2. Do not modify, reflow, move, remove, or append inside that section.
3. Keep status, checklist, implementation, review, and changelog edits outside the section.
4. After editing, verify the `## Manual Notes` heading and preserved marker/body are unchanged. If the diff touches that section, revert that part before handoff unless the user explicitly asked to edit manual notes.

### Flow Docs

Use `flow-doc` to explain a concrete runtime path, its state transitions,
ownership boundaries, meaningful decisions, and verification signals. Follow
`./references/flow-doc/workflow.md` for the complete authoring, scoped-boundary,
revision, and validation contract. Use `./references/flow-doc/template.md` as
the document scaffold.

## Shared References

- Use `$sudocode` only when compact logic clarifies a non-obvious decision,
  state transition, or ownership boundary.
- Use `$dev.diagram` to draft or revise flow diagrams.
- Use `$docy` `ref/execution-trace` before writing flow-doc execution traces.

## Flow-Doc Quality Gate (Required)

Before finalizing any flow doc, run the validator from this skill root:

```bash
python3 ./scripts/validate_flow_doc.py --kind flow-doc --doc "<flow-doc-path>"
```

Resolve validator errors before handoff. Do not skip this check.


## Required Ending Sections (All Docs)

Every document created or revised using this skill must end with the following sections,
verbatim and in this order, unless the doc-type template specifies a different
changelog shape. Keep the Manual Notes content unchanged across edits.

```
## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- [YYYY-MM-DD HH:MM]: [description of update] ([agent session id] - (current git sha))
```

For the changelog timestamp, use the current local date and time to the minute. For the session id, use `dev.llm-session` to find the current conversation session id. Choose the lookup strategy that matches the active thread, and do not leave placeholder text such as `[agent session id]` or `[codex session id]` in a completed document.

## Shortcuts

Shortcuts are self-contained workflows triggered only when the user explicitly asks to use one.
When invoked, follow the mapped workflow section exactly.

### new-architecture-doc

- Follow `./references/architecture/workflow.md` section `Instructions`.

### new-research-brief

- Follow `./references/research-brief/workflow.md` section `Instructions`.

### new-flow-doc

- Follow `./references/flow-doc/workflow.md` section `Instructions`.

### new-state-doc

- Follow `./references/state-doc/workflow.md` section `Instructions`.

### new-service-design-doc

- Follow `./references/service-design-doc/workflow.md` section `Instructions`.

### new-design-spec

- Follow `./references/design-spec/workflow.md` section `Instructions`.

### new-feature-spec

- Follow `./references/feature-spec/workflow.md` section `Instructions`.

### new-investigation-spec

- Follow `./references/investigation-spec/workflow.md` section `Instructions`.

### new-report-note

- Follow `./references/report-note/workflow.md` section `Instructions`.

### update-flow-doc

When updating existing flow docs, use a preservation-first revision style.

1. Preserve existing structure and detail by default; do not rewrite large sections unless required.
2. Prefer additive edits: add targeted clarifications, corrections, and cross-references.
3. If the user asked specific questions, answer them in focused subsections tied to concrete file citations.
4. Keep `## Manual Notes` and its content unchanged across revisions.
5. Before finalizing, run a scope check: if the diff removes unrelated detail or broadens beyond request, reduce to a minimal targeted patch.

- For more details, follow `./references/flow-doc/workflow.md` section `Revision Instructions`.

### new-recipe

- Follow `./references/recipe/workflow.md` section `Instructions`.

### new-faq-spec

- Follow `./references/faq-spec/workflow.md` section `Instructions`.

### new-vendor-docs

- Follow `./references/vendor-doc/workflow.md` section `Instructions`.

## Best Practices

- Read only the workflow(s) relevant to the document type requested.
- Preserve stable IDs and manually maintained sections when revising existing docs.
- Keep source citations explicit and actionable.
- Keep repo-internal markdown links portable: use repo-relative targets under `$DOCS_ROOT` and avoid absolute local filesystem paths in generated docs.

## Directory Structure

Research documentation lives in the project's docs folder:

```
$DOCS_ROOT/
  architecture/      # System architecture docs
    {YYYY-MM-DD}-architecture-{system}.md
  research/          # Research briefs
    {date}-research-{topic}.md
  design/            # Service design docs
    {date}-design-{topic}.md
  specs/             # Active and archived specs
    .archive/        # Completed specs moved here
    {NN}-{topic}.md
  flows/             # Flow documentation
    core.init.md
    core.exit.md
    topic.{name}.md
    ref.{name}.md
  reports/           # Concise report notes
    {report-name}.md
  state/             # State docs
    {state-name}.md
  recipes/           # Change recipes
    {recipe-name}.md
  faq/
    {date}-{topic}.md
  vendor/            # Vendor documentation
    {library}/
      README.md
      reference/
        {docs}.md
      topics/
        {name}.md
```

Active feature specs live directly under `$DOCS_ROOT/specs/` with a monotonic two-digit integer prefix starting at `01`; choose the next prefix by scanning active and archived specs and do not reuse gaps. When a single-file spec is complete, move it to `$DOCS_ROOT/specs/.archive/` and keep the same filename.
When a workspace explicitly uses a folder-based schema such as `specs`, each active spec folder lives directly under `$DOCS_ROOT/specs/{NN}-{topic}/` and may contain sidecars such as `milestones/`, `flows/`, `reports/`, `cook/`, or proof artifacts. Treat the folder as the spec unit: update the selected schema sidecar, preserve siblings, and archive the whole folder to `$DOCS_ROOT/specs/.archive/{NN}-{topic}/` when complete.
If multiple spec types exist for the same topic, keep the filename format and distinguish them in the `{topic}` slug, for example `01-payments-design.md` or `02-payments-validation.md`.

FAQ Specs do not create standalone files. They update the target research document in place.

## Path Convention

Throughout this skill, bundled paths prefixed with `./` are relative to this skill root.

- `./references/architecture/workflow.md` -> `./references/architecture/workflow.md`
- `./references/architecture/template.md` -> `./references/architecture/template.md`
- `./references/research-brief/workflow.md` -> `./references/research-brief/workflow.md`
- `./references/research-brief/template.md` -> `./references/research-brief/template.md`
- `./references/flow-doc/workflow.md` -> `./references/flow-doc/workflow.md`
- `./references/flow-doc/template.md` -> `./references/flow-doc/template.md`
- `./references/state-doc/workflow.md` -> `./references/state-doc/workflow.md`
- `./references/state-doc/template.md` -> `./references/state-doc/template.md`
- `./references/service-design-doc/workflow.md` -> `./references/service-design-doc/workflow.md`
- `./references/service-design-doc/template.md` -> `./references/service-design-doc/template.md`
- `./references/design-spec/workflow.md` -> `./references/design-spec/workflow.md`
- `./references/design-spec/template.md` -> `./references/design-spec/template.md`
- `./references/feature-spec/workflow.md` -> `./references/feature-spec/workflow.md`
- `./references/feature-spec/template.md` -> `./references/feature-spec/template.md`
- `./references/feature-spec/effective-planning.md` -> `./references/feature-spec/effective-planning.md`
- `./references/feature-spec/beads.md` -> `./references/feature-spec/beads.md`
- `./references/investigation-spec/workflow.md` -> `./references/investigation-spec/workflow.md`
- `./references/investigation-spec/template.md` -> `./references/investigation-spec/template.md`
- `./references/validation-spec/workflow.md` -> `./references/validation-spec/workflow.md`
- `./references/validation-spec/template.md` -> `./references/validation-spec/template.md`
- `./references/report-note/workflow.md` -> `./references/report-note/workflow.md`
- `./references/report-note/template.md` -> `./references/report-note/template.md`
- `./references/recipe/workflow.md` -> `./references/recipe/workflow.md`
- `./references/recipe/template.md` -> `./references/recipe/template.md`
- `./references/faq-doc/workflow.md` -> `./references/faq-doc/workflow.md`
- `./references/faq-doc/template.md` -> `./references/faq-doc/template.md`
- `./references/faq-spec/workflow.md` -> `./references/faq-spec/workflow.md`
- `./references/faq-spec/template.md` -> `./references/faq-spec/template.md`
- `./references/vendor-doc/workflow.md` -> `./references/vendor-doc/workflow.md`
- `./references/vendor-doc/template.md` -> `./references/vendor-doc/template.md`

When you see `$DOCS_ROOT/`, resolve paths relative to the project root directory.

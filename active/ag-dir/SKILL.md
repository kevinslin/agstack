---
name: ag-dir
description: Create or audit Agent Project Directory docs and status structure.
dependencies:
- ag-ledger
- dev.shortcuts
- mem
- specy
---

# AG Directory (AGD)

Use this skill when creating, auditing, or updating a durable AG directory (AGD) for one task.

## Canonical Layout

Use `$mem schema` and the bundled `ag-dir` schema as the source of truth for layout,
boilerplate, file descriptions, insertion routing, and template sections. Follow
`$mem` to ensure the `mem` command is installed on `PATH`, then inspect the schema
before creating or auditing an AGD:

```bash
mem schema show ag-dir
```

When this skill and the schema disagree, prefer the schema and update stale skill text
rather than inventing a third layout.

## Materialization

Use `$mem schema` to create missing AGD notes instead of hand-writing boilerplate.

Create or backfill the AGD skeleton:

```bash
mem schema materialize ag-dir \
  --out "$ROOT_DIR" \
  --unmanaged \
  --var project_title="Example Project" \
  --var spec_num=01 \
  --var spec_name=bootstrap \
  --include design \
  --include memory \
  --include progress \
  --include docs/spec-01-bootstrap \
  --include .agents/runs/spec-01/handoff \
  --include .agents/runs/spec-01/progress \
  --include .agents/runs/spec-01/learnings \
  --skip-existing
```

Add a new active spec plus matching run notes to an existing AGD:

```bash
mem schema materialize ag-dir \
  --out "$ROOT_DIR" \
  --unmanaged \
  --var project_title="Example Project" \
  --var spec_num=02 \
  --var spec_name=workflow-cleanup \
  --include docs/spec-02-workflow-cleanup \
  --include .agents/runs/spec-02/handoff \
  --include .agents/runs/spec-02/progress \
  --include .agents/runs/spec-02/learnings \
  --skip-existing
```

Materialize an archived spec note only when you explicitly need the optional archive branch:

```bash
mem schema materialize ag-dir \
  --out "$ROOT_DIR" \
  --unmanaged \
  --var project_title="Example Project" \
  --var spec_num=02 \
  --var spec_name=workflow-cleanup \
  --var archived_spec_num=00 \
  --var archived_spec_name=landed-work \
  --include docs/.archive/spec-00-landed-work \
  --skip-existing
```

## Operating Rules

1. Use `$mem schema` with the `ag-dir` schema to inspect layout or materialize missing notes before creating new boilerplate by hand.
2. Create matching run notes when adding a new active spec.
3. Keep `memory.md` concise and durable; remove stale hypotheses once resolved.
4. Keep active spec numbering stable (`spec-01`, `spec-02`, ...). Avoid renaming active specs.
5. Move completed specs into the schema's archive branch instead of deleting them.

## Recommended Workflow

1. Inspect `ag-dir` with `$mem schema` to confirm the current layout.
2. Materialize the AGD skeleton into the target directory with `--skip-existing`.
3. Draft `design.md`.
4. Add one or more active feature specs in `docs/`.
5. Add spec-specific runtime notes under `.agents/runs/spec-{num}/`.
6. Roll key outcomes and cross-spec updates into `progress.md`.
7. When a spec is complete, move it to `docs/.archive/` and leave a current `handoff.md` when another agent needs to resume.

## Shortcuts

Shortcuts are self-contained workflows triggered only when the user explicitly asks to use one.
When invoked, follow the mapped workflow section exactly.
Invoke them through `$dev.shortcuts` with `trigger:<shortcut>`, for example `trigger:handoff spec14`.

### handoff [spec]

Write or refresh `.agents/runs/spec-{num}/handoff.md` for the requested spec.

1. Normalize `[spec]` from forms like `spec14`, `spec-14`, or `14` to the folder name `spec-14`.
2. Locate the matching active spec file under `docs/` using `docs/spec-{num}-*.md`.
3. If `.agents/runs/spec-{num}/` or `handoff.md` is missing, materialize the missing run notes with `$mem schema`. Reuse the slug from the matching `docs/spec-{num}-<name>.md` file as `spec_name`.
4. Read the current spec, relevant run notes, and recent workspace changes before writing.
5. Write the handoff doc at `.agents/runs/spec-{num}/handoff.md` using the existing template sections.
6. Replace placeholders with concrete current-state information; do not leave the handoff note as boilerplate.

### progress [spec]

Write or refresh `.agents/runs/spec-{num}/progress.md` for the requested spec.

1. Normalize `[spec]` to `spec-{num}`.
2. Ensure the run-note directory exists; if not, materialize it with `$mem schema` using the matching `docs/spec-{num}-*.md` slug.
3. Read the active spec plus recent work artifacts.
4. Update `.agents/runs/spec-{num}/progress.md` with the current state, next steps, and any spec-local notes.

### learnings [spec]

Write or refresh `.agents/runs/spec-{num}/learnings.md` for the requested spec.

1. Normalize `[spec]` to `spec-{num}`.
2. Ensure the run-note directory exists; if not, materialize it with `$mem schema` using the matching `docs/spec-{num}-*.md` slug.
3. Read the active spec plus the latest implementation or investigation evidence.
4. Update `.agents/runs/spec-{num}/learnings.md` with concrete takeaways using the existing template sections.

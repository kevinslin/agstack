---
name: ag-dir
description: Maintain project design, progress, learnings, steering, and spec-local handoff notes.
dependencies:
- dev.shortcuts
- mem
- specy
---

# AG Directory

Use this skill when a user asks to create, audit, or refresh Agent Project
Directory records for a project or one of its numbered specs.

`ag-dir` is a workflow over `$mem` schemas, not its own layout schema. Use the
`project` schema for visible project-root records and project-root
`flows`/`cook`/`raw`/`reports`. Use the `specs` schema for numbered spec directories,
including spec-local `spec.md`, `handoff.md`, `progress.md`, `learnings.md`,
`flows`, `cook`, `milestones`, `proofs`, and `reports`.

## Source of truth

Read the current project instructions first. If the project has configured
memory, use `$mem` in project context lookup mode before manual source search.
Context lookup can create a missing derived index, but it does not authorize
ongoing maintenance or edits to project records.

Inspect the active layout before materializing:

```bash
mem schema show project
mem schema describe project
mem schema show specs
mem schema describe specs
```

When instructions, existing files, and schema descriptions disagree, preserve
existing project ownership and ask only when the requested destination is still
ambiguous after reading current evidence.

## Project records

Maintain these visible project-root records when the user request or adopted
project instructions authorize updates:

- `design.md`: current project model, decisions, constraints, open questions,
  ownership boundaries, and links to detailed design sources.
- `progress.md`: recent agent changes, current status, next steps, blockers,
  dates, evidence, and details that another agent needs to resume work.
- `learnings.md`: evidence-backed reusable lessons discovered while executing
  the project. Do not record speculation or direct user steering here.
- `steering.md`: explicit user instructions, corrections, scope decisions, and
  durable preferences, with source/date context.
- `raw/{slug}.md`: initial project findings, evidence, and unresolved questions.
  Keep findings here until the user explicitly promotes them to `reports/`;
  finishing an investigation or validating evidence does not imply promotion.

Preserve superseded steering with its source and supersession date instead of
deleting it silently. Mark the current instruction clearly when older steering
would otherwise conflict.

Do not create a new overlapping `memory.md` for new projects. If a legacy
`memory.md` exists, preserve it until its current model, decisions, constraints,
questions, lessons, and user instructions are reconciled into the appropriate
current records.

## Spec records

Numbered specs live under `specs/{number}-{slug}/`. Keep root-level and
spec-local flows, cookbooks, and reports:

- Project-root `flows`/`cook` maintain current project-wide docs; `reports`
  contains findings explicitly promoted by the user, with links to raw sources.
- Spec-local `flows`/`cook`/`reports` can hold temporary proposals,
  investigations, snapshots, and spec-scoped reports.
- A spec-local doc is not promoted automatically. Promote or copy flows and
  cookbooks to project-root docs only when the user or project instructions
  explicitly adopt them as current project guidance. Reports require explicit
  user promotion.

Keep active spec numbering stable. Archive a completed or superseded spec by
moving the complete numbered directory unchanged under `specs/.archive/`.

## Materialization

Use `$mem schema materialize` to create missing records instead of hand-writing
boilerplate. Managed bases must configure `project` and `specs` as sibling
schemas; do not select a retired `ag-dir` schema name and do not add a silent
alias from `ag-dir` to another layout.

Create or backfill visible project records:

```bash
mem schema materialize project \
  --base "$BASE" \
  --include design \
  --include progress \
  --include learnings \
  --include steering \
  --skip-existing
```

Create a numbered spec and its local notes:

```bash
mem schema materialize specs \
  --base "$BASE" \
  --var spec_number=14 \
  --var spec_slug=workflow-cleanup \
  --include specs/14-workflow-cleanup/spec \
  --include specs/14-workflow-cleanup/handoff \
  --include specs/14-workflow-cleanup/progress \
  --include specs/14-workflow-cleanup/learnings \
  --skip-existing
```

For an explicit repository or temporary destination, use unmanaged
materialization with `--out` and `--unmanaged`. Keep `--skip-existing` around
hand-edited files.

## Operating workflow

1. Read project instructions, configured memory context, and existing
   project-root records.
2. Resolve the requested project or spec record from existing files before
   creating anything.
3. Materialize only missing requested nodes with `$mem schema`.
4. Read existing target files before editing and preserve user-owned sections.
5. Write concise, sourced updates in the record that owns the information.
6. Verify the edited paths and any documented commands that are feasible in the
   current checkout.

## Shortcuts

Shortcuts are self-contained workflows triggered only when the user explicitly
asks to use one. Invoke them through `$dev.shortcuts` with `trigger:<shortcut>`,
for example `trigger:handoff spec14`.

Accepted spec argument forms are `spec14`, `spec-14`, `14`, and the exact
existing folder basename such as `14-workflow-cleanup`. First check whether the
argument exactly matches an existing `specs/{number}-{slug}/` folder. Otherwise
normalize the numeric alias and resolve the actual existing number, zero
padding, and slug from `specs/{number}-*/`. If no candidate or multiple
candidates match, ask for clarification. If no spec argument is provided, use
only unambiguous current task context; otherwise ask.

### handoff [spec]

Write or refresh `specs/{number}-{slug}/handoff.md` for the requested spec.

1. Resolve the existing spec directory under `specs/`.
2. If `handoff.md` is missing, materialize it with the `specs` schema using the
   resolved `spec_number` and `spec_slug`.
3. Read `spec.md`, existing spec-local notes, project-root `progress.md`, and
   relevant recent workspace changes.
4. Update `handoff.md` with current state, completed work, next action,
   blockers, and relevant files.
5. Replace placeholders with concrete current-state information.

### progress [spec]

Write or refresh `specs/{number}-{slug}/progress.md` for the requested spec.

1. Resolve the existing spec directory under `specs/`.
2. If `progress.md` is missing, materialize it with the `specs` schema using the
   resolved `spec_number` and `spec_slug`.
3. Read the active spec, existing handoff/learnings notes, and recent evidence.
4. Update `progress.md` with current status, completed work, next steps,
   blockers, and spec-local notes.
5. Update project-root `progress.md` only when the change is project-wide
   status, not merely spec-local execution detail.

### learnings [spec]

Write or refresh `specs/{number}-{slug}/learnings.md` for the requested spec.

1. Resolve the existing spec directory under `specs/`.
2. If `learnings.md` is missing, materialize it with the `specs` schema using
   the resolved `spec_number` and `spec_slug`.
3. Read the active spec plus implementation, investigation, test, or review
   evidence.
4. Update `learnings.md` with evidence-backed takeaways, failed assumptions,
   reusable lessons, and follow-ups.
5. Put direct user instructions and corrections in project-root `steering.md`
   instead of learnings.

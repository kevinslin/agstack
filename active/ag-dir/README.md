# ag-dir

`ag-dir` maintains Agent Project Directory records through the `project` and
`specs` schemas. It keeps project-root design, progress, learnings, and steering
visible while keeping numbered spec handoff notes inside the matching spec
directory.

Use the skill when a project needs durable status, recent agent changes, user
steering, or spec-local handoff/progress/learnings records. Read
[`SKILL.md`](./SKILL.md) for the operator workflow.

## Layout

Project-root records:

- `design.md`: current project model, decisions, constraints, and open
  questions.
- `progress.md`: recent agent changes, current status, next actions, and
  blockers, with dates and evidence.
- `learnings.md`: evidence-backed reusable lessons from project execution.
- `steering.md`: explicit user instructions, corrections, and scope decisions.
  Preserve superseded steering with its source and supersession date.

Spec-local records:

- `specs/{number}-{slug}/spec.md`: main spec for the numbered unit.
- `specs/{number}-{slug}/handoff.md`: current resumption context.
- `specs/{number}-{slug}/progress.md`: spec-local execution status.
- `specs/{number}-{slug}/learnings.md`: reusable lessons discovered while
  executing that spec.

Project-root `raw/{slug}.md` holds initial findings, evidence, and open questions.
Findings remain there until the user explicitly promotes them to `reports/`.
Reports link back to their raw sources. Completed research does not imply
promotion. Project-root `flows` and `cook` contain current project-wide docs.
Spec-local `flows`, `cook`, and `reports` can be temporary proposed docs,
investigations, snapshots, and reports that archive with the spec. Spec-local
flows and cookbooks are promoted only by an explicit user or project decision;
reports require explicit user promotion.

## Commands

Inspect the schemas:

```bash
mem schema show project
mem schema describe project
mem schema show specs
mem schema describe specs
```

Materialize project-root records under a configured base:

```bash
mem schema materialize project \
  --base "$BASE" \
  --include design \
  --include progress \
  --include learnings \
  --include steering \
  --skip-existing
```

Materialize one numbered spec and its local notes:

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

Managed project bases configure `project` and `specs` as sibling schemas. The
retired schema name `ag-dir` is not a compatibility alias.

## Shortcuts

`ag-dir` keeps these inline shortcuts through `$dev.shortcuts`:

- `trigger:handoff spec14`
- `trigger:progress spec14`
- `trigger:learnings spec14`

Accepted spec arguments are `spec14`, `spec-14`, `14`, and the exact existing
folder basename such as `14-workflow-cleanup`. The workflow first checks for an
exact existing folder match, then resolves numeric aliases to the actual
existing number, zero padding, and slug before writing. Ambiguous or missing
spec selection requires clarification.

## Legacy migration

Retiring the old `ag-dir` schema is a deliberate breaking change for callers of
`mem schema ... ag-dir`. Update callers explicitly.

| Old content/path | New destination |
| --- | --- |
| `design.md` | Retain as project-root `design.md`; link detailed design docs instead of duplicating them. |
| `progress.md` | Retain as project-root `progress.md`; add recent-agent-change status without discarding manual sections. |
| `memory.md` current model, decisions, constraints, and questions | Reconcile into `design.md`; preserve `memory.md` until coverage is checked. |
| `memory.md` evidence-backed lessons | Move to `learnings.md` after reconciliation. |
| `memory.md` actual user directions | Move to `steering.md` after reconciliation. |
| `docs/spec-{num}-{slug}.md` | `specs/{number}-{slug}/spec.md` after explicit workspace adoption. |
| `.agents/runs/spec-{num}/handoff.md` | `specs/{number}-{slug}/handoff.md`. |
| `.agents/runs/spec-{num}/progress.md` | `specs/{number}-{slug}/progress.md`. |
| `.agents/runs/spec-{num}/learnings.md` | `specs/{number}-{slug}/learnings.md`. |
| `docs/.archive/spec-{num}-{slug}.md` | Complete reconciled spec unit under `specs/.archive/`. |
| `spec_num` | `spec_number`. |
| `spec_name` | `spec_slug`. |
| Config schema `ag-dir` | Configure both `project` and `specs`, respecting existing roots and avoiding duplicate selections. |

Use `--skip-existing` for additive scaffolding. It protects populated files but
cannot merge template sections into existing notes. Before removing a legacy
file, map each source path, destination path, inbound link, number/slug, and
collision, then verify content coverage.

# Schema workflow

Use the schema engine to inspect, validate, compose, and materialize hierarchical file layouts. Resolve named schemas in this order:

1. The nearest ancestor `schemas/<schema>/schema.yaml`.
2. `$HOME/.schemas/<schema>/schema.yaml`.
3. Bundled `./schemas/<schema>/schema.yaml` relative to this reference file.

A named schema in `.mem.yaml` follows the same local-then-global discovery, so project configurations stay portable without absolute schema paths.

## Available schemas

- `tool`: Dendron hierarchy for `pkg.<name>` and `vpkg.<name>` tool documentation.
- `code`: Specy-style code documentation under `packages/{{module}}`.
- `code-core`: Reusable code documentation nodes for development, observability, flows, architecture, and API references.
- `global-core`: Reusable `cook/{{cook}}`, `ref/{{reference}}`, and `t/{{topic}}` namespaces.
- `integ-proof`: Integration proofs with claims, scenarios, scripts, and raw artifacts.
- `project`: Project-root design, progress, learnings, steering, current flows, cookbooks, raw findings, and explicitly promoted reports.
- `pkg`: Package hierarchy rooted at `{{package}}`, composing package guides, code documentation, and specs; its mount is selected by the base configuration.
- `specs`: Numbered active specs, spec-local notes, archives, milestones, proofs, cookbooks, and reports.

## Layout

```text
schemas/
  <schema>/
    schema.yaml
    <template>.md.jinja
    <template>.py.jinja
    default.md.jinja
```

A node's `template` selects the template basename. A leaf without `template` uses `default`. Namespace nodes with children and no template create no file.

## Schema fields

```yaml
version: 1.0
output:
  file_extension: md
variables:
  name: ["*"]
schema:
  "{{name}}":
    description: root file
    template: root
    children:
      docs:
        description: documentation subtree
        children_from:
          - schema: code-core
            vars:
              module: "{{name}}"
```

- `variables`: Optional restrictions, defaults, and descriptions for placeholders.
- `output.file_extension`: Extension appended to generated paths.
- `schema`: Literal or placeholder path-segment tree.
- `description`: Primary navigation and placement signal.
- `insertion_policy`: Optional `use_when` and `avoid_when` hints used only when descriptions are ambiguous.
- `template`: Template basename.
- `children`: Child nodes.
- `children_from`: Composed bundled schemas or paths relative to the parent schema directory. Parent values flow only through explicit `vars` mappings.
- `dynamic_child`: Marks namespaces that may grow explicit user-requested children.

## Commands

```bash
mem schema list
mem schema show tool
mem schema describe tool
mem schema validate tool
```

Managed materialization:

```bash
mem schema materialize pkg \
  --base oai \
  --var package=clawcmd \
  --var cook=change-claw-config \
  --include pkg/clawcmd/cook/change-claw-config \
  --skip-existing
```

Managed mode resolves the managed output root, path style, optional custom schema path, and schema mount from version-2 `.mem.yaml`. Each configured schema may set a relative `root`: `packages` mounts it under `packages/`, `projects/packages` nests it, and `.` mounts it inline without an additional root node. Omitting the `pkg` root preserves its historical `pkg/` mount. Include paths contain the configured mount; for example, inline `pkg` uses `--include clawcmd/cook/change-claw-config`. Use `--root-relative <path>` for a subtree contained by the resolved managed root. Manual `--out`, `--path-style`, and `--schema-path` overrides are rejected in managed mode.

After successful managed materialization, the CLI refreshes `<managed_root>/.mem.index.json`; unchanged document paths leave the existing index untouched. If that refresh fails, the created knowledge, original stdout, and exit status `0` are preserved, and stderr receives one structured `index_refresh_failed` warning containing a replayable `repair_argv`. Execute that argument array exactly instead of rolling back the document. Unmanaged materialization does not refresh a managed index. If an agent creates a managed schema-backed Markdown file directly instead of using this command, run `mem index build --base NAME_OR_ALIAS` afterward.

The `pkg` schema mounts `global-core` before `code-core`, so `global-core` owns the overlapping `ref` and `t` namespaces. It mounts `specs` last under `<schema-root>/{{package}}/specs`, or `{{package}}/specs` when inline. Keep `code-core` project-scoped; configure `code`, `specs`, and `global-core` separately when an aggregate base also needs `packages/{{module}}` and workspace-wide artifacts.

For Agent Project Directory work, configure `project` and `specs` as sibling
schemas. `project` owns visible project-root records and current root
`flows`/`cook`/`raw`/`reports`; `specs` owns numbered spec units, spec-local
`handoff`/`progress`/`learnings`, and spec-local `flows`/`cook`/`reports` that
can archive with the spec. Do not add a silent `ag-dir` alias; callers of the
retired schema name must migrate deliberately.

For project findings, start in `raw/{{raw}}`. Populate `reports/{{report}}`
only when the user explicitly promotes the findings, and link the raw source
in the report. Finishing research, validating evidence, or asking to save
findings does not imply promotion. This is an agent placement rule; the schema
engine materializes explicitly selected nodes and does not infer approval.

Explicit non-memory materialization:

```bash
mem schema materialize integ-proof \
  --out /tmp/proofs \
  --unmanaged \
  --path-style directory \
  --var proof=example \
  --include example/proof \
  --skip-existing
```

## Navigation and authoring rules

- Read `schema.yaml` before materializing.
- Improve `description` before adding insertion policy.
- Materialize only explicit nodes using the full rendered `--include` path.
- Use slash-separated includes for directory style and dotted includes for dotted style.
- Use `--skip-existing` around hand-edited files.
- Treat `dynamic_child` as permission for future explicit children, not permission to invent them.
- Treat `children_from` as composition, not inheritance.
- Keep template names stable and update the schema before adding templates.
- Add or update automated tests whenever changing the engine, schemas, or templates.

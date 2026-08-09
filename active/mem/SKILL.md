---
name: mem
description: Automatically use for durable knowledge, configured project-context lookup, and schema-backed artifact layouts.
dependencies:
- dev.llm-session
- specy
---

# mem

Use this skill as the single interface for persistent knowledge bases, project context, generated base indexes, and schema-backed file layouts. It owns base selection, root containment, schema inspection, model-inferred node selection, exact-node materialization, and durable read/write safety.

## Invocation Rule

Invoke `$mem` whenever the user explicitly asks to save, retrieve, organize, or update durable knowledge, even when they do not name this skill. Treat requests to record, remember, capture, or document reusable guides, cookbooks, runbooks, decisions, research notes, findings, lessons, and references as `$mem` requests.

Also invoke `$mem` when inspecting, validating, or materializing a bundled file schema.

When project or workspace instructions require `$mem` for context lookup, invoke it even without durable-output intent. Context lookup never changes knowledge documents or source files, but may create the selected base's missing derived `.mem.index.json`; select the configured base, resolve its schemas, infer likely nodes from their descriptions, and search existing knowledge before inspecting source.

Treat configuration as optional. Before starting a managed operation, check for the nearest ancestor `.mem.yaml` and `$HOME/.mem.yaml`. If neither exists, stop the `$mem` workflow successfully and continue the underlying task without `$mem`. Do not ask the user to create configuration or report a blocker solely because configuration is absent.

Do not auto-write merely because information might be useful later. Require explicit durable-output intent or an applicable project instruction. Do not use `$mem` for transient answers or files whose repository-owned workflow and exact destination the user already specified.

## Operating Modes

- **Managed knowledge:** Resolve `.mem.yaml`, select a base, constrain all knowledge paths to its resolved managed root, and use its configured schemas.
- **Project context lookup:** Read existing managed knowledge using schema-inferred candidate paths, then fall back to a scoped source search when it is missing or insufficient.
- **Schema inspection:** List, show, or describe bundled schemas without writing files.
- **Unmanaged materialization:** Write a schema-backed repo-owned or temporary artifact to an explicit output path only when the caller passes `--unmanaged`.

Prefer managed knowledge mode for durable artifacts.

## Unified CLI

Run commands from the directory containing this `SKILL.md`, or resolve `./scripts/mem.py` relative to this file.

See [`README.md`](./README.md) for the system design and [`CLI.md`](./CLI.md) for the complete command reference.

```bash
# Upgrade existing version-1 configuration after installing the updated skill.
python3 ./scripts/mem.py doctor --migrate --pretty

# Inspect merged configuration.
python3 ./scripts/mem.py config show --pretty

# Explain base selection.
python3 ./scripts/mem.py route --query "{{request intent}}" --pretty

# Maintain or inspect derived base indexes.
python3 ./scripts/mem.py index build --base oai --pretty
python3 ./scripts/mem.py index show --base oai --pretty
python3 ./scripts/mem.py index check --all --pretty

# Read managed project context, with bounded source fallback when needed.
python3 ./scripts/mem.py context lookup \
  --query "{{context intent}}" \
  --source "{{project-or-package-path}}" \
  --pretty

# Inspect schemas.
python3 ./scripts/mem.py schema list
python3 ./scripts/mem.py schema show global-core
python3 ./scripts/mem.py schema describe global-core
python3 ./scripts/mem.py schema validate global-core

# Materialize under a configured base.
python3 ./scripts/mem.py schema materialize pkg \
  --base oai \
  --var package=clawcmd \
  --var cook=change-claw-config \
  --include pkg/clawcmd/cook/change-claw-config \
  --skip-existing

# Materialize an explicit non-memory artifact.
python3 ./scripts/mem.py schema materialize integ-proof \
  --out /tmp/proofs \
  --unmanaged \
  --var proof=example \
  --include example/proof \
  --skip-existing
```

Managed materialization derives `--out`, `--path-style`, and any custom schema path from the selected base. `--root-relative` is relative to and must remain inside the base's resolved managed root. Explicit `--out` requires `--unmanaged`.

## Configuration

Merge configuration from:

1. The nearest `.mem.yaml` at or above `$PWD`
2. `$HOME/.mem.yaml`

Load both when present. The nearest config wins when both define the same base name; unique home bases remain available.

Configuration requires top-level `version: 2`. After installing the updated skill, migrate existing version-1 configuration with `python3 ./scripts/mem.py doctor --migrate --pretty`; migration discards retired `match.topics` and `match.artifact_kinds` while preserving ownership globs and other supported settings. Each base requires `name`, `description`, `root`, and `schemas`. It may also define a relative `managed_root`, plus `path_style`, `skill`, `aliases`, `priority`, and `match.cwd_globs` or `match.source_globs`. `root` is the workspace containment boundary; the resolved `managed_root` is the narrower knowledge read/write boundary and defaults to `root`.

Routing has strict precedence: an explicit base or alias wins; otherwise source and cwd ownership wins; query signals are considered only when ownership does not match. Conflicting source and cwd ownership is ambiguous and requires an explicit base. Query scores and `priority` never override a higher tier.

Compatibility aliases must preserve the historical root and behavior. Do not map a retired child-root base to an aggregate parent alias because aliases carry no root-relative prefix.

An optional top-level `audit` mapping enables mandatory conversation-scoped lookup traces. `enabled` defaults to `false`; `trace_root` defaults to `$HOME/.config/mem/traces`. When enabled, `context lookup` requires the active conversation UUID in `CODEX_THREAD_ID` and fails closed if its trace cannot be safely written. The nearest configuration that explicitly declares `audit` owns the complete effective audit mapping.

Use `python3 ./scripts/mem.py config show --pretty` instead of hand-parsing configuration.

Each base owns `<managed_root>/.mem.index.json`, a disposable, path-derived cache containing generated topics, artifact kinds, and the first two logical hierarchy levels. Routing and context lookup create a missing index automatically; managed schema materialization refreshes it after successful creation. Index scans are uncapped, while normal knowledge search remains bounded; directory advisory locks leave no durable lockfile. External edits, renames, deletes, and syncs require explicit `index build` when freshness matters.

Use `python3 ./scripts/mem.py context lookup` for project context. Repeat `--source` for multiple file or directory scopes, pass `--target` to select one base explicitly, and use `--allow-multiple` only for lookup across an otherwise ambiguous route. The command never materializes or edits knowledge or source files; its only permitted managed-root mutation is creating a missing derived index. See [the knowledge workflow](./references/knowledge-workflow.md#project-context-lookup) for its search and output contract.

## Managed Workflow

1. Parse the request into a context lookup, read, write, update, delete, schema-inspection, or materialization operation.
2. Check for the nearest ancestor `.mem.yaml` and `$HOME/.mem.yaml`. If neither exists, exit this workflow successfully and continue the underlying task without `$mem`.
3. Load merged configuration.
4. Select an explicit base name or alias when provided. Otherwise run `mem.py route`.
5. Stop for clarification when routing returns `ambiguous` or `no_match`.
6. Resolve every configured schema for the selected base before operating.
7. Treat the selected base's resolved managed root as the boundary for managed reads, searches, duplicate detection, and writes.
8. Infer the most likely schema nodes from their descriptions and derive concrete candidate paths. This is model judgment; do not claim deterministic node inference when the context command reports only configured schemas and concrete matched paths.
9. Search candidate paths, filenames, headings, and body text before creating a near-duplicate.
10. Materialize only that node. Do not create sibling placeholders or an entire schema tree.
11. Read the existing target before editing and preserve user-owned sections.
12. After creating a managed Markdown entity through direct file editing rather than managed materialization, run `python3 ./scripts/mem.py index build --base NAME_OR_ALIAS` for the selected base. Managed materialization performs this refresh automatically; surface any structured `index_refresh_failed` warning and its replayable `repair_argv` without reporting successful knowledge creation as failed.
13. Verify the expected path, containment, route metadata, protected sections, changelog, and index refresh outcome.

For complete knowledge read/write/delete rules, read `./references/knowledge-workflow.md`.
For schema fields, composition, authoring, and CLI behavior, read `./references/schema-workflow.md`.

## Safety Invariants

- Treat the selected base's resolved managed root as authoritative for knowledge operations.
- Reject managed paths that resolve outside the workspace root or resolved managed root after processing `..`, symlinks, or relative segments.
- Do not silently write to a drifted path because it already exists.
- Preserve `## Manual Notes` byte-for-byte unless the user explicitly asks to edit it.
- Delete knowledge only when the user explicitly requests deletion.
- Use schema descriptions as the primary placement signal and insertion policy only as a tiebreaker.
- Keep project context lookup read-only for knowledge documents and source files; permit only creation of the selected base's missing derived index. Search the relevant project, service, or package source with scoped `rg` only when managed knowledge is absent or insufficient.
- When audit tracing is enabled, do not bypass a missing session ID, unsafe trace destination, lock failure, or trace write failure.
- Create only the requested knowledge file, its parent directories, and the selected base's derived index when index initialization or refresh requires it.
- Use `--unmanaged` only for an explicit repo-owned or temporary destination.

## Final Response

For managed operations, report the selected base, base root, schema node, concrete path, and what changed or was found. Keep routine responses concise.

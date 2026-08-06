---
name: mem
description: Automatically use for durable knowledge, configured project-context lookup, and schema-backed artifact layouts.
dependencies:
- dev.llm-session
- specy
---

# mem

Use this skill as the single interface for persistent knowledge bases, read-only project context, and schema-backed file layouts. It owns base selection, root containment, schema inspection, model-inferred node selection, exact-node materialization, and durable read/write safety.

## Invocation Rule

Invoke `$mem` whenever the user explicitly asks to save, retrieve, organize, or update durable knowledge, even when they do not name this skill. Treat requests to record, remember, capture, or document reusable guides, cookbooks, runbooks, decisions, research notes, findings, lessons, and references as `$mem` requests.

Also invoke `$mem` when inspecting, validating, or materializing a bundled file schema.

When project or workspace instructions require `$mem` for context lookup, invoke it even without durable-output intent. Context lookup is read-only: select the configured base, resolve its schemas, infer likely nodes from their descriptions, and search existing knowledge before inspecting source.

Treat configuration as optional. Before starting a managed operation, check for the nearest ancestor `.mem.yaml` and `$HOME/.mem.yaml`. If neither exists, stop the `$mem` workflow successfully and continue the underlying task without `$mem`. Do not ask the user to create configuration or report a blocker solely because configuration is absent.

Do not auto-write merely because information might be useful later. Require explicit durable-output intent or an applicable project instruction. Do not use `$mem` for transient answers or files whose repository-owned workflow and exact destination the user already specified.

## Operating Modes

- **Managed knowledge:** Resolve `.mem.yaml`, select a base, constrain all paths to its root, and use its configured schemas.
- **Project context lookup:** Read existing managed knowledge using schema-inferred candidate paths, then fall back to a scoped source search when it is missing or insufficient.
- **Schema inspection:** List, show, or describe bundled schemas without writing files.
- **Unmanaged materialization:** Write a schema-backed repo-owned or temporary artifact to an explicit output path only when the caller passes `--unmanaged`.

Prefer managed knowledge mode for durable artifacts.

## Unified CLI

Run commands from the directory containing this `SKILL.md`, or resolve `./scripts/mem.py` relative to this file.

```bash
# Inspect merged configuration.
python3 ./scripts/mem.py config show --pretty

# Explain base selection.
python3 ./scripts/mem.py route --query "{{request intent}}" --pretty

# Search managed context, then explicit source scopes on a miss.
python3 ./scripts/mem.py context lookup \
  --query "{{context query}}" \
  --target "{{base}}" \
  --source "{{scoped source path}}" \
  --pretty

# Inspect schemas.
python3 ./scripts/mem.py schema list
python3 ./scripts/mem.py schema show global-core
python3 ./scripts/mem.py schema describe global-core
python3 ./scripts/mem.py schema validate global-core

# Materialize under a configured base.
python3 ./scripts/mem.py schema materialize global-core \
  --base oai/clawcmd \
  --root-relative . \
  --var cook=change-claw-config \
  --include cook/change-claw-config \
  --skip-existing

# Materialize an explicit non-memory artifact.
python3 ./scripts/mem.py schema materialize integ-proof \
  --out /tmp/proofs \
  --unmanaged \
  --var proof=example \
  --include example/proof \
  --skip-existing
```

Managed materialization derives `--out`, `--path-style`, and any custom schema path from the selected base. `--root-relative` must remain inside that base root. Explicit `--out` requires `--unmanaged`.

## Configuration

Merge configuration from:

1. The nearest `.mem.yaml` at or above `$PWD`
2. `$HOME/.mem.yaml`

Load both when present. The nearest config wins when both define the same base name; unique home bases remain available.

Each base requires `name`, `description`, `root`, and `schemas`. It may also define `path_style`, `skill`, `aliases`, `priority`, and deterministic `match` signals for topics, artifact kinds, source globs, and working-directory globs.

Use `python3 ./scripts/mem.py config show --pretty` instead of hand-parsing configuration.

An optional top-level `audit` mapping enables mandatory conversation-scoped
lookup traces. `enabled` defaults to `false`; `trace_root` defaults to
`$HOME/.config/mem/traces`. When enabled, `context lookup` requires the active
conversation UUID in `CODEX_THREAD_ID` and fails closed if its trace cannot be
prepared or atomically updated. See `./CLI.md` for the trace contract.

For `context lookup`, each repeatable `--source` scope may influence routing in
both caller-supplied and normalized form; source search still runs only after
the selected managed root has no match.

## Managed Workflow

1. Parse the request into a context lookup, read, write, update, delete, schema-inspection, or materialization operation.
2. Check for the nearest ancestor `.mem.yaml` and `$HOME/.mem.yaml`. If neither exists, exit this workflow successfully and continue the underlying task without `$mem`.
3. Load merged configuration.
4. Select an explicit base name or alias when provided. Otherwise run `mem.py route`.
5. Stop for clarification when routing returns `ambiguous` or `no_match`.
6. Resolve every configured schema for the selected base before operating.
7. Infer the most likely schema nodes from their descriptions and derive concrete candidate paths. This is model judgment; do not add a separate path-ranking service.
8. Search candidate paths, filenames, headings, and body text before creating a near-duplicate.
9. Materialize only that node. Do not create sibling placeholders or an entire schema tree.
10. Read the existing target before editing and preserve user-owned sections.
11. Verify the expected path, containment, route metadata, protected sections, and changelog.

For complete knowledge read/write/delete rules, read `./references/knowledge-workflow.md`.
For schema fields, composition, authoring, and CLI behavior, read `./references/schema-workflow.md`.

## Safety Invariants

- Treat the selected base root as authoritative.
- Reject managed paths that resolve outside that root after processing `..`, symlinks, or relative segments.
- Do not silently write to a drifted path because it already exists.
- Preserve `## Manual Notes` byte-for-byte unless the user explicitly asks to edit it.
- Delete knowledge only when the user explicitly requests deletion.
- Use schema descriptions as the primary placement signal and insertion policy only as a tiebreaker.
- Keep project context lookup read-only. Search the relevant project, service, or package source with scoped `rg` only when managed knowledge is absent or insufficient.
- Create only the requested file and its parent directories.
- Use `--unmanaged` only for an explicit repo-owned or temporary destination.

## Final Response

For managed operations, report the selected base, base root, schema node, concrete path, and what changed or was found. Keep routine responses concise.

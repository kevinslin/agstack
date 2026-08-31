---
name: mem
description: Automatically use for durable knowledge, configured project-context lookup, and schema-backed artifact layouts.
dependencies:
- dev.llm-session
- specy
---

# mem

Use this skill as the single interface for persistent knowledge bases, project context, generated base indexes, workspace project snapshots, and schema-backed file layouts. It owns base selection, root containment, schema inspection, model-inferred node selection, exact-node materialization, and durable read/write safety.

## Concepts

- **Root node:** The first node in a tree.
- **Hierarchy:** A directed graph that describes the layout of files.
- **Schema:** Rules defining how a hierarchy is organized.
- **Base:** A collection of one or more schemas that make a knowledge connection.
- **Mem config:** Global configuration that defines knowledge bases.

## Invocation Rule

Invoke `$mem` whenever the user explicitly asks to save, retrieve, organize, or update durable knowledge, even when they do not name this skill. Treat requests to record, remember, capture, or document reusable guides, cookbooks, runbooks, decisions, research notes, findings, lessons, and references as `$mem` requests.

Also invoke `$mem` when inspecting, validating, or materializing a bundled file schema.

When project or workspace instructions require `$mem` for context lookup, invoke it even without durable-output intent. Context lookup never changes knowledge documents or source files, but may create the selected base's missing derived `.mem.index.json`; select the configured base, resolve its schemas, infer likely nodes from their descriptions, and search existing knowledge before inspecting source.

Treat configuration as optional. Before starting a managed operation, ensure the CLI is installed as described below and run `mem config find --pretty`. Use its `config_paths` result instead of checking the filesystem manually. If it returns `status: missing_config`, stop the `$mem` workflow successfully and continue the underlying task without `$mem`. Do not ask for configuration or report a blocker solely because it is absent. A discovery error is not an absent configuration.

Workspace commands can run without mem configuration. Use `mem workspace lookup --query "<project or intent>"` when the relevant project is unclear or the request spans recent work. It reads compact project summaries from the existing snapshot without inference or rebuilding. If the wording produces no useful match, omit the query to browse all summaries. Use `--details` for the selected project's resources; request `--include-sources` only when supporting rollout references are needed. Multiple projects may share a repository. Match the request to project descriptions and aliases, rather than choosing solely by repository or priority.

Before using a returned base, resolve its current configuration with `mem config show --config <config_path> --cwd <root>`. Confirm the active base instance, then use `mem context lookup --target <name> --config <config_path> --cwd <root> --query "<intent>"`. Snapshot aliases do not become mem routing aliases. For projects without a configured base, use the returned files and repositories to scope source inspection. An absent snapshot does not block normal configured context lookup; do not build one automatically as a side effect of reading. See [workspace lookup](./CLI.md#workspace-lookup).

Use `mem workspace build` when asked to discover or refresh meaningful projects across recent local work. It reads the last seven days of Codex rollouts, groups projects with the authenticated Codex CLI, and replaces `~/.mem/workspace/index.json`. Warning details are in a per-build file under `~/.mem/workspace/logs/`; the snapshot keeps `partial` and a relative `log_path`. Consult that log when explaining incomplete coverage, and treat priorities as current attention, not durable project status. See [workspace build](./CLI.md#workspace-build) for prerequisites and boundaries.

Do not auto-write merely because information might be useful later. Require explicit durable-output intent or an applicable project instruction. Do not use `$mem` for transient answers or files whose repository-owned workflow and exact destination the user already specified.

## Operating Modes

- **Managed knowledge:** Resolve `.mem.yaml`, select a base, constrain all knowledge paths to its resolved managed root, and use its configured schemas.
- **Project context lookup:** Read existing managed knowledge using schema-inferred candidate paths, then fall back to a scoped source search when it is missing or insufficient.
- **Schema inspection:** List, show, or describe bundled schemas without writing files.
- **Workspace discovery:** Read a compact project map to select context, or explicitly rebuild the snapshot from recent local activity with LLM inference.
- **Unmanaged materialization:** Write a schema-backed repo-owned or temporary artifact to an explicit output path only when the caller passes `--unmanaged`.

Prefer managed knowledge mode for durable artifacts.

## Unified CLI

Require the `mem` executable on `PATH` before running CLI operations. Check with `command -v mem`; if missing, run the bundled installer and verify the command. Set `MEM_SKILL_ROOT` to the absolute directory containing this `SKILL.md`:

```bash
if ! command -v mem >/dev/null 2>&1; then
  python3 "$MEM_SKILL_ROOT/scripts/install.py" || exit 1
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v mem
mem --help
```

Verify that `mem --help` succeeds and lists `mem config find`, `mem config show`, `mem context lookup`, and `mem schema`. If the resolved command has different help, report the conflicting executable path before running memory operations.

Run `mem` from the caller's project directory so configuration discovery and routing retain the intended scope. Use the installed command for normal operations. If installation or verification fails, report the error instead of falling back to a direct `./scripts/mem.py` invocation.

See [`README.md`](./README.md) for the system design and [`CLI.md`](./CLI.md) for the complete command reference.

```bash
# Discover configuration without parsing it. Stop the managed workflow if status is missing_config.
mem config find --pretty

# Upgrade existing version-1 configuration after installing the updated skill.
mem doctor --migrate --pretty

# Inspect merged configuration.
mem config show --pretty

# Explain base selection.
mem route --query "{{request intent}}" --pretty

# Maintain or inspect derived base indexes.
mem index build --base oai --pretty
mem index show --base oai --pretty
mem index check --all --pretty

# Read managed project context, with bounded source fallback when needed.
mem context lookup \
  --query "{{context intent}}" \
  --source "{{project-or-package-path}}" \
  --pretty

# Build a fresh project snapshot from the last seven days of local activity.
mem workspace build --pretty

# Find a project in the existing snapshot, then inspect its resources.
mem workspace lookup --query "agent memory" --pretty
mem workspace lookup --query "agmem" --details --pretty

# Inspect schemas.
mem schema list
mem schema show global-core
mem schema describe global-core
mem schema validate global-core

# Materialize under a configured base.
mem schema materialize pkg \
  --base oai \
  --var package=clawcmd \
  --var cook=change-claw-config \
  --include pkg/clawcmd/cook/change-claw-config \
  --skip-existing

# Materialize an explicit non-memory artifact.
mem schema materialize integ-proof \
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

Configuration requires top-level `version: 2`. After installing the updated skill, migrate existing version-1 configuration with `mem doctor --migrate --pretty`; migration discards retired `match.topics` and `match.artifact_kinds` while preserving ownership globs and other supported settings. Each base requires `name`, `description`, `schemas`, and exactly one of `root` or `root_pattern`. A fixed `root` names its workspace directly; `root_pattern` matches the session directory or an ancestor by basename glob (`proj*`) or absolute path glob (`/workspace/projects/*`). Path globs match one directory component at a time, so nested sessions retain their project root. The nearest matching ancestor becomes the workspace root; unmatched pattern bases are inactive. A project has one resolved root, and fixed-root ownership takes precedence over pattern-root ownership.

A base may also define a relative `managed_root`, plus `path_style`, `skill`, `aliases`, `priority`, and `match.cwd_globs` or `match.source_globs`. Its resolved root is the workspace containment boundary; `managed_root` is the narrower knowledge read/write boundary and defaults to that root. Each schema may set a relative `root` mount such as `packages` or `projects/packages`; `root: .` mounts it inline. Omitting the `pkg` schema root preserves its historical `pkg/` mount.

Project bases that adopt the Agent Project Directory workflow configure
`project` and `specs` as sibling schemas. Do not configure or alias a retired
`ag-dir` schema name; aliases cannot rewrite one historical child layout into
two current sibling schemas.

Routing has strict precedence: an explicit active base or alias wins; otherwise fixed-root source/cwd ownership wins over pattern-root ownership; query signals are considered only when ownership does not match. Conflicting owners at the same precedence are ambiguous and require an explicit base. Query scores and `priority` never override a higher tier.

Compatibility aliases must preserve the historical root and behavior. Do not map a retired child-root base to an aggregate parent alias because aliases carry no root-relative prefix.

An optional top-level `audit` mapping enables mandatory conversation-scoped lookup traces. `enabled` defaults to `false`; `trace_root` defaults to `$HOME/.config/mem/traces`. When enabled, `context lookup` requires the active conversation UUID in `CODEX_THREAD_ID` and fails closed if its trace cannot be safely written. The nearest configuration that explicitly declares `audit` owns the complete effective audit mapping.

Use `mem config find --pretty` to locate configuration and `mem config show --pretty` to load and validate it. Discovery reports paths without parsing YAML or validating roots and schemas.

Each base owns `<managed_root>/.mem.index.json`, a disposable, path-derived cache containing generated topics, artifact kinds, and the first two logical hierarchy levels. Routing and context lookup create a missing index automatically; managed schema materialization refreshes it after successful creation. Index scans are uncapped, while normal knowledge search remains bounded; directory advisory locks leave no durable lockfile. External edits, renames, deletes, and syncs require explicit `index build` when freshness matters.

Use `mem context lookup` for project context. Repeat `--source` for multiple file or directory scopes, pass `--target` to select one base explicitly, and use `--allow-multiple` only for lookup across an otherwise ambiguous route. The command never materializes or edits knowledge or source files, and lookup alone does not authorize maintaining project records; its only permitted managed-root mutation is creating a missing derived index. See [the knowledge workflow](./references/knowledge-workflow.md#project-context-lookup) for its search and output contract.

## Managed Workflow

1. Parse the request into a context lookup, read, write, update, delete, schema-inspection, or materialization operation.
2. Run `mem config find --pretty`. If it returns `status: missing_config`, exit this workflow successfully and continue the underlying task without `$mem`. Report discovery errors instead of treating them as missing configuration.
3. Load and validate merged configuration with `mem config show --pretty`, preserving any `--config`, `--cwd`, or `--home` controls used for discovery.
4. Select an explicit base name or alias when provided. Otherwise run `mem route`.
5. Stop for clarification when routing returns `ambiguous` or `no_match`.
6. Resolve every configured schema for the selected base before operating.
7. Treat the selected base's resolved managed root as the boundary for managed reads, searches, duplicate detection, and writes.
8. Infer the most likely schema nodes from their descriptions and derive concrete candidate paths. This is model judgment; do not claim deterministic node inference when the context command reports only configured schemas and concrete matched paths.
9. Search candidate paths, filenames, headings, and body text before creating a near-duplicate.
10. Materialize only that node. Do not create sibling placeholders or an entire schema tree.
11. Read the existing target before editing and preserve user-owned sections.
12. After creating a managed Markdown entity through direct file editing rather than managed materialization, run `mem index build --base NAME_OR_ALIAS` for the selected base. Managed materialization performs this refresh automatically; surface any structured `index_refresh_failed` warning and its replayable `repair_argv` without reporting successful knowledge creation as failed.
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

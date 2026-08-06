# mem

`mem` is the command-line interface for configured knowledge bases, read-only
project-context lookup, and schema-backed artifact layouts. It merges project
and user configuration, routes a request to a knowledge base, searches managed
knowledge before source, and can optionally write a conversation-scoped audit
trace for each lookup.

## Contents

- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Project-context lookup](#project-context-lookup)
- [Audit traces](#audit-traces)
- [Schema commands](#schema-commands)
- [More documentation](#more-documentation)

## Quick start

Run commands from this directory so `./scripts/mem.py` resolves correctly:

```bash
# Inspect the effective configuration.
python3 ./scripts/mem.py config show --pretty

# Search managed context, with scoped source fallback on a managed miss.
MEM_SOURCE_ROOT=/path/to/source/repository
python3 ./scripts/mem.py context lookup \
  --query "gateway authentication" \
  --target claw \
  --source "$MEM_SOURCE_ROOT/codex/claw-gateway" \
  --pretty

# Explain routing without performing a lookup.
python3 ./scripts/mem.py route \
  --query "gateway authentication" \
  --target claw \
  --pretty

# Inspect a bundled schema.
python3 ./scripts/mem.py schema describe global-core
```

`context lookup` is read-only. It does not materialize schema nodes or modify
managed knowledge or source files.

## Configuration

`mem` looks for the nearest `.mem.yaml` at or above the working directory and
for `$HOME/.mem.yaml`. A minimal configuration with audit tracing is:

```yaml
version: 1
bases:
  - name: claw
    description: Claw gateway project knowledge
    root: ./0/notes/claw
    schemas:
      - name: project
      - name: global-core
    aliases: [claw-gateway]
    priority: 10
    match:
      topics: [claw, gateway]
      artifact_kinds: [guide, reference, spec]
      source_globs: ["*/codex/claw-gateway/**"]
      cwd_globs: ["*/code/openai/**"]

audit:
  enabled: true
  trace_root: ~/.config/mem/traces
```

Each base requires `name`, `description`, `root`, and one or more `schemas`.
Optional fields are `path_style`, `skill`, `aliases`, `priority`, and `match`.

### Merge and defaults

- When both files exist, the nearest configuration's base wins when the same
  base name appears in both. Bases unique to the home configuration remain
  available.
- Relative base roots resolve from the configuration file that declares them.
  Roots, custom schema paths, and the audit trace root are expanded and exposed
  as normalized absolute paths.
- An omitted `path_style` is inferred from the base root and otherwise defaults
  to `directory`.
- `audit.enabled` defaults to `false`.
- `audit.trace_root` defaults to `$HOME/.config/mem/traces`.
- Audit settings merge as one mapping, not field by field. When the nearest
  configuration declares `audit`, it owns the complete effective audit mapping
  and omitted fields receive defaults. If it does not declare `audit`, the home
  configuration's mapping is inherited.
- `--config PATH` loads only that file instead of merging nearest and home
  configurations.

Inspect the effective values rather than hand-parsing YAML:

```bash
python3 ./scripts/mem.py config show --pretty
```

The normalized JSON includes `config_path`, `config_paths`, `version`, `bases`,
and the effective `audit` object. Invalid fields and types fail validation.

## Project-context lookup

Use `context lookup` when source work should first consult managed knowledge:

```bash
MEM_SOURCE_ROOT=/path/to/source/repository
python3 ./scripts/mem.py context lookup \
  --query "how tenant credentials are resolved" \
  --target claw \
  --source "$MEM_SOURCE_ROOT/codex/claw-gateway" \
  --source "$MEM_SOURCE_ROOT/codex/claw-server" \
  --pretty
```

The command:

1. Loads and validates the merged configuration.
2. Selects an explicit target or routes the query.
3. Resolves the selected base's schemas and searches the selected managed root,
   recording configured-schema evidence without ranking or inferring nodes.
4. Searches each repeatable `--source` scope only when managed knowledge has no
   match.
5. Returns structured JSON with `selection`, `hierarchy`, `fallback`, `status`,
   and `matched_paths`.

An ambiguous or unmatched route is reported as its real terminal status; it is
not silently converted into a successful lookup.

## Audit traces

Tracing is opt-in. With `audit.enabled: false`, or with no audit mapping,
lookups behave as before and create no trace directory or file.

When tracing is enabled, the active Codex conversation UUID must be present in
`CODEX_THREAD_ID`. `mem` validates this value as a UUID and uses it directly as
the session ID. It does not infer an ID from filenames or accept an unrelated
conversation identifier.

The first audited lookup in a conversation selects one file using the user's
local date:

```text
<trace_root>/<YYYY>/<MM>/<DD>/<CODEX_THREAD_ID>.jsonl
```

Later lookups in the same conversation reuse that file, even after local
midnight. Trace directories are mode `0700`; trace files are mode `0600`.

Each nonempty line is an independent UTF-8 JSON object for one distinct logical
lookup. A SHA-256 `lookup_id` fingerprints canonical JSON containing the
session ID, query, ordered executed command arguments, selected base names,
selected hierarchy paths, and source scopes. Timing, scores, outcomes, and
explanatory prose do not affect the fingerprint.

Repeating the same logical lookup updates its existing record instead of
appending another line. The update increments `occurrence_count`, appends a
complete timing snapshot to `attempts`, refreshes the latest outcome and
`finished_at`, and adds the new attempt to `duration_ms`. Updates are serialized
and atomically replace the trace file so concurrent lookups do not lose attempts
or produce duplicate or partial records.

Audit records include:

- Identity and aggregate timing: `version`, `session_id`, `lookup_id`,
  `started_at`, `finished_at`, `duration_ms`, and `occurrence_count`.
- Request and execution: `query`, exact `commands[].argv`, safely quoted
  `commands[].command`, and command timestamps.
- Actual stages: ordered `operations` such as `load_config`, `route`,
  `resolve_schemas`, `search_managed`, and `search_source` when fallback ran.
- Per-occurrence history: `attempts` with command timings, operation timings,
  duration, and terminal status.
- Decisions and outcome: `selection`, `hierarchy`, `fallback`, `status`, and
  `matched_paths`.

Elapsed durations are nonnegative milliseconds measured with a monotonic clock;
timestamps are timezone-aware ISO 8601 values with millisecond precision.
Top-level `started_at` belongs to the first attempt, `finished_at` and
`operations` describe the latest attempt, and `duration_ms` is the sum of all
attempt durations.

Tracing records command arguments and path decisions, but never environment
variables, file bodies, credentials, unrelated shell commands, fabricated CLI
invocations, or private model reasoning. Trace writes are contained within the
configured trace root and never alter managed knowledge or source scopes.

An audit-enabled lookup stops with an explicit audit error when the session ID
is missing or invalid, the trace destination is unsafe, configuration is
invalid, permissions cannot be enforced, or the trace cannot be created or
updated. It never continues as an unlogged search.

## Schema commands

List, inspect, describe, or validate bundled schemas:

```bash
python3 ./scripts/mem.py schema list
python3 ./scripts/mem.py schema show global-core
python3 ./scripts/mem.py schema describe global-core
python3 ./scripts/mem.py schema validate global-core
```

Materialize inside a configured base:

```bash
python3 ./scripts/mem.py schema materialize global-core \
  --base claw \
  --root-relative . \
  --var cook=change-claw-config \
  --include cook/change-claw-config \
  --skip-existing
```

Explicit non-memory output requires `--unmanaged`:

```bash
python3 ./scripts/mem.py schema materialize integ-proof \
  --out /tmp/proofs \
  --unmanaged \
  --var proof=example \
  --include example/proof \
  --skip-existing
```

## More documentation

- [CLI command and audit field reference](./CLI.md)
- [Audit trace feature specification](../../docs/specs/active/2026-08-06-mem-audit-traces.md)
- [Knowledge workflow](./references/knowledge-workflow.md)
- [Schema workflow](./references/schema-workflow.md)

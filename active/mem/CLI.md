# mem CLI reference

This manual documents the unified `mem.py` entry point, including read-only
project-context lookup and its optional conversation-scoped audit trace.

## Contents

- [Invocation](#invocation)
- [`config show`](#config-show)
- [`route`](#route)
- [`context lookup`](#context-lookup)
- [Audit configuration](#audit-configuration)
- [Audit trace lifecycle](#audit-trace-lifecycle)
- [Audit JSON Lines fields](#audit-json-lines-fields)
- [Deduplication and timing](#deduplication-and-timing)
- [Security and errors](#security-and-errors)
- [`schema`](#schema)

## Invocation

Run from the directory containing `SKILL.md`:

```bash
python3 ./scripts/mem.py <command> [options]
```

Commands write structured JSON to standard output where applicable. Validation
and runtime failures write an `error:` message to standard error and exit
nonzero. `--pretty` changes JSON formatting only.

## `config show`

Print the merged, validated, normalized configuration:

```bash
python3 ./scripts/mem.py config show [options]
```

Options:

| Option | Meaning |
| --- | --- |
| `--config PATH` | Load only `PATH`; do not merge nearest and home configs. |
| `--cwd PATH` | Find the nearest ancestor `.mem.yaml` from this directory. Defaults to the current directory. |
| `--home PATH` | Use this home directory when locating the home `.mem.yaml`. |
| `--allow-missing-roots` | Normalize without requiring configured base roots to exist. |
| `--pretty` | Indent JSON output. |

Without `--config`, `mem` loads the nearest ancestor `.mem.yaml` first and
`$HOME/.mem.yaml` second. Same-named bases from the nearer file take precedence;
unique home bases remain available. The result contains:

```json
{
  "config_path": "/absolute/project/.mem.yaml",
  "config_paths": [
    "/absolute/project/.mem.yaml",
    "/absolute/home/.mem.yaml"
  ],
  "version": 1,
  "audit": {
    "enabled": true,
    "trace_root": "/absolute/home/.config/mem/traces"
  },
  "bases": []
}
```

`bases` contains normalized roots, path styles, schemas, and optional routing
metadata. `audit` is always the effective normalized object: `enabled` defaults
to `false`, and `trace_root` defaults to `$HOME/.config/mem/traces`.

Audit settings are inherited as a whole mapping. If the nearest configuration
declares `audit`, that mapping wins and its omitted fields receive defaults; its
missing fields are not filled from the home audit mapping. If the nearest file
omits `audit`, the home mapping is used.

## `route`

Select a configured base and explain the decision without searching it:

```bash
python3 ./scripts/mem.py route --query QUERY [options]
```

Options:

| Option | Meaning |
| --- | --- |
| `--query TEXT` | Required user intent or artifact request. |
| `--target NAME` | Explicit base name or alias. |
| `--source PATH` | Source path considered by configured `source_globs`. |
| `--artifact-kind KIND` | Explicit kind such as `guide`, `reference`, or `runbook`. |
| `--config PATH` | Load only this configuration. |
| `--cwd PATH` | Working directory used for lookup and `cwd_globs`. |
| `--home PATH` | Home directory used for configuration discovery. |
| `--allow-missing-roots` | Do not require configured roots to exist. |
| `--pretty` | Indent JSON output. |

The result status is `selected`, `ambiguous`, or `no_match`. An explicit base
name or alias takes precedence over scored routing.

## `context lookup`

Search managed knowledge and, only on a managed miss, explicitly scoped source
paths:

```bash
python3 ./scripts/mem.py context lookup \
  --query QUERY \
  [--target NAME] \
  [--source PATH ...] \
  [--artifact-kind KIND] \
  [configuration options] \
  [--pretty]
```

Options:

| Option | Meaning |
| --- | --- |
| `--query TEXT` | Required lookup intent. The exact value is audited when tracing is enabled. |
| `--target NAME` | Select an explicit configured base name or alias. |
| `--source PATH` | Add a scoped fallback source path. Repeat for multiple scopes. |
| `--artifact-kind KIND` | Supply a routing artifact kind explicitly. |
| `--config PATH` | Load only this configuration. |
| `--cwd PATH` | Working directory for configuration discovery and routing. |
| `--home PATH` | Home directory for configuration discovery. |
| `--allow-missing-roots` | Normalize without requiring base roots to exist. |
| `--pretty` | Indent JSON output. |

Lookup order is fixed:

1. Load and validate configuration.
2. Route the query or resolve `--target`.
3. Resolve the selected base's configured schemas.
4. Search the selected managed root and record one hierarchy decision per
   configured schema, using shared query terms as evidence when present.
5. If managed knowledge has no match, search only the repeatable `--source`
   scopes.
6. Return the observed outcome and, when enabled, commit its audit record.

The command is read-only. It does not create schema nodes or modify files in
the base or source scopes.

The JSON result exposes:

| Field | Meaning |
| --- | --- |
| `selection` | Selected tier, base names, and grounded routing reasons. |
| `hierarchy` | Observed managed and fallback path decisions. |
| `fallback` | Whether source fallback ran, its scoped paths, and why. |
| `status` | Real terminal outcome, including matched, ambiguous, or unmatched states. |
| `matched_paths` | Files that satisfied the lookup; empty when none matched. |
| `candidates` | Ranked candidates returned by the router. |

## Audit configuration

Add an optional top-level mapping to `.mem.yaml`:

```yaml
audit:
  enabled: true
  trace_root: ~/.config/mem/traces
```

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | Boolean | `false` | Enable mandatory tracing for audited lookup commands. |
| `trace_root` | String path | `$HOME/.config/mem/traces` | Root for conversation trace files. `~` and environment variables are expanded and the result is normalized to an absolute path. |

Unknown keys, non-boolean `enabled`, or invalid `trace_root` values fail
configuration validation. Use `config show --pretty` to see the merged values
that a lookup will use.

## Audit trace lifecycle

Audit-disabled lookups create no directories or files. Audit-enabled lookups
require the active Codex thread ID in `CODEX_THREAD_ID`. Its value must be a
valid UUID; no filename, process, or unrelated conversation is used as a
fallback.

The first audited lookup chooses:

```text
<trace_root>/<local YYYY>/<MM>/<DD>/<CODEX_THREAD_ID>.jsonl
```

The date is the user's local date at that first lookup. Every later lookup for
the conversation reuses the same file, even after midnight. A conversation
therefore owns exactly one trace file. Directories use mode `0700` and the file
uses mode `0600`.

Each nonempty line is one complete UTF-8 JSON object. Distinct logical lookups
have separate lines; repeat occurrences are merged into the existing line.
Same-conversation writes are serialized and the file is replaced atomically.

## Audit JSON Lines fields

Required fields for every lookup record:

| Field | Shape | Meaning |
| --- | --- | --- |
| `version` | Integer | Trace schema version; currently `1`. |
| `started_at` | Timestamp | Start of the first occurrence. |
| `finished_at` | Timestamp | End of the latest occurrence. |
| `duration_ms` | Integer | Sum of all attempt durations. |
| `session_id` | UUID string | Validated active `CODEX_THREAD_ID`. |
| `lookup_id` | `sha256:...` string | Stable logical-lookup fingerprint. |
| `occurrence_count` | Integer | Number of merged occurrences. |
| `query` | String | Exact lookup query. |
| `commands` | Array | Commands that actually executed. |
| `operations` | Array | Ordered stages from the latest attempt. |
| `attempts` | Array | Complete timing and status history for every occurrence. |
| `hierarchy` | Array | Grounded path decisions observed during lookup. |

Outcome fields:

| Field | Meaning |
| --- | --- |
| `selection` | Routing tier, selected base names, and evidence-backed reasons. |
| `fallback` | `used`, searched `paths`, and the reason fallback did or did not run. |
| `status` | Latest terminal lookup status. |
| `matched_paths` | Latest matched managed or source paths. |

### Commands

Each `commands` entry contains:

- `argv`: exact executed argument tokens in order.
- `command`: a safely shell-quoted, replayable representation of `argv`.
- `started_at`, `finished_at`, and `duration_ms`: execution timing.

Only commands that actually execute are recorded. Internal calls are not
invented as command entries.

### Operations

Each operation contains `name`, `started_at`, `finished_at`, and `duration_ms`.
Entries are ordered and created only for stages that ran. Expected names include
`load_config`, `route`, `resolve_schemas`, `search_managed`, and
`search_source`; `search_source` is absent when source fallback did not run.

### Attempts

Each attempt contains its own `started_at`, `finished_at`, `duration_ms`,
`command_timings`, `operation_timings`, and terminal `status`.
`command_timings[].command_index` refers to the corresponding entry in the
top-level `commands` array.

### Hierarchy

Each hierarchy decision contains:

- `path`: observed managed or source path.
- `schema`: associated schema when applicable.
- `decision`: what the lookup did with the path, such as `searched`.
- `reason`: concise, evidence-backed explanation.

Hierarchy entries describe the selected managed root once per configured schema
and any source fallback paths. They do not claim node inference or reasoning
that was not observed.

## Deduplication and timing

`lookup_id` is the SHA-256 digest of canonical JSON containing exactly the
logical identity inputs:

- conversation session ID;
- query;
- ordered executed command argument arrays;
- selected base names;
- selected hierarchy paths; and
- source scopes.

Timestamps, durations, routing scores, outcomes, and explanatory prose are
excluded. Consequently, changing a query, executed command, selected target,
hierarchy path, or source scope creates a distinct record.

Repeating the same identity updates one record: `occurrence_count` increments,
the full timing snapshot is appended to `attempts`, `finished_at` and the latest
observable outcome are refreshed, and the attempt duration is added to
top-level `duration_ms`. `started_at` remains the first attempt's start and
`operations` reflects only the latest attempt.

Every lookup, command, and actual operation uses timezone-aware ISO 8601
timestamps with millisecond precision. Durations are nonnegative elapsed
milliseconds measured with a monotonic clock, so wall-clock changes do not
corrupt elapsed timing.

## Security and errors

Tracing is constrained to the normalized `trace_root`. It records lookup
metadata, never:

- environment variables or their values;
- file bodies;
- credentials or secrets;
- unrelated shell commands;
- fabricated command invocations; or
- private model reasoning.

Audit-enabled lookup fails explicitly and does not perform an unlogged search
when any required audit guarantee cannot be met. Fatal audit conditions include:

- missing or invalid `CODEX_THREAD_ID`;
- invalid audit configuration;
- a destination that escapes `trace_root`;
- unsafe path or session filename input;
- inability to create or enforce `0700` directories and a `0600` file;
- lock, atomic replacement, serialization, or update failure; and
- malformed existing trace data that prevents a safe merge.

Failed, ambiguous, and unmatched audited lookups that reach a recordable
terminal state retain their real status and use empty selection or match fields
where no selection occurred. Audit writes never modify managed knowledge or
source scopes.

## `schema`

Inspect bundled schemas:

```bash
python3 ./scripts/mem.py schema list
python3 ./scripts/mem.py schema show SCHEMA
python3 ./scripts/mem.py schema describe SCHEMA
python3 ./scripts/mem.py schema validate SCHEMA
```

Materialize under a configured base:

```bash
python3 ./scripts/mem.py schema materialize SCHEMA \
  --base BASE \
  [--root-relative PATH] \
  [schema materialization options]
```

Managed mode derives output root, path style, and custom schema path from the
selected base. `--root-relative` must resolve inside the selected base root.
Manual `--out`, `--path-style`, and `--schema-path` overrides are rejected.

Materialize an explicit non-memory artifact:

```bash
python3 ./scripts/mem.py schema materialize SCHEMA \
  --out PATH \
  --unmanaged \
  [schema materialization options]
```

An explicit `--out` requires `--unmanaged`. See the
[schema workflow](./references/schema-workflow.md) for schema fields,
composition, and materialization options.

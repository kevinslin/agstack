---
title: Mem Audit Trace Format
last_refreshed: 2026-08-06 09:15
last_refreshed_by: 019fd474-e957-75e3-8610-647bebd4a0bb
---

# Feature Spec: Mem Audit Trace Format

**Date:** 2026-08-06
**Status:** Completed
**Owner:** Public `mem` skill maintainers

## Problem and Decision

`mem` lookups currently return routing and search results but leave no durable
record explaining which conversation searched for what, which CLI commands
actually ran, why particular knowledge hierarchies were inspected, or how long
each operation took. Add an opt-in audit mode that maintains one trace file per
conversation and one structured JSON Lines record per distinct logical lookup,
merging repeated searches without losing their timing history.

## Scope

**Changes:** Configuration parsing, lookup tracing, the trace format, and
operator documentation.

**Does not change:** Base routing precedence, managed knowledge placement,
schema semantics, source files, or existing behavior while audit is disabled.
The shipped implementation lives in `scripts/audit_trace.py`,
`scripts/load_config.py`, and `scripts/context.py`.

## Contract

### Configuration

Add an optional top-level `audit` mapping to `.mem.yaml`:

```yaml
audit:
  enabled: true
  trace_root: ~/.config/mem/traces
```

`enabled` is a boolean and defaults to `false`. `trace_root` is optional and
defaults to `$HOME/.config/mem/traces`; expand `~` and environment variables and
normalize it to an absolute directory. When multiple configs are merged, the
nearest configuration that declares `audit` owns the entire audit mapping;
otherwise inherit the home config's mapping. Invalid fields or types fail
configuration validation. `config show` exposes the normalized audit settings.

### Trace location and lifecycle

For an audit-enabled lookup, write to:

```text
<trace_root>/<YYYY>/<MM>/<DD>/<conversation-session-id>.jsonl
```

For example:

```text
~/.config/mem/traces/2026/08/06/019fa5de-c89c-7402-ad74-2978a02a04ad.jsonl
```

The date uses the user's local timezone when the conversation's first audited
lookup starts. Later searches reuse that same session file, including after
midnight; one conversation must never create another trace file under a new
date. The session ID must come from the active conversation and be validated as
a UUID; never use an inferred filename, traversal segment, or unrelated
conversation. Create trace directories with mode `0700` and files with mode
`0600`.

### Conversation and lookup deduplication

A conversation owns exactly one trace file. Within that file, a distinct lookup
is identified by `lookup_id`, a SHA-256 fingerprint of canonical JSON containing
the conversation session ID, query, ordered executed command arguments,
selected base names, selected hierarchy paths, and source scopes. Exclude
timestamps, durations, routing scores, outcomes, and explanatory prose from the
fingerprint.

Append a new JSON Lines record only when its `lookup_id` is absent. When the same
lookup occurs again, update its existing record, increment `occurrence_count`,
append a complete timing snapshot to `attempts`, refresh `finished_at` and the
latest observable outcome, and accumulate `duration_ms`. Preserve distinct
queries, commands, targets, hierarchy paths, and source scopes as distinct
records. Serialize same-conversation updates and replace the file atomically so
concurrent searches cannot create duplicate files, duplicate records, partial
lines, or lost attempts.

### JSON Lines record

Each nonempty line is one independent UTF-8 JSON object:

```json
{
  "version": 1,
  "started_at": "2026-08-06T09:02:00.000-07:00",
  "finished_at": "2026-08-06T09:02:00.087-07:00",
  "duration_ms": 87,
  "session_id": "019fa5de-c89c-7402-ad74-2978a02a04ad",
  "lookup_id": "sha256:5bc3d31d3d6e5c2df4c7fd4cc882443d8f89aa6bc6004e15a5f80f0beef7cfc1",
  "occurrence_count": 1,
  "query": "gateway authentication",
  "commands": [
    {"argv": ["python3", "./scripts/mem.py", "context", "lookup", "--query", "gateway authentication", "--target", "claw"],
     "command": "python3 ./scripts/mem.py context lookup --query 'gateway authentication' --target claw",
     "started_at": "2026-08-06T09:02:00.000-07:00", "finished_at": "2026-08-06T09:02:00.087-07:00", "duration_ms": 87}
  ],
  "operations": [
    {"name": "load_config", "started_at": "2026-08-06T09:02:00.002-07:00", "finished_at": "2026-08-06T09:02:00.008-07:00", "duration_ms": 6},
    {"name": "route", "started_at": "2026-08-06T09:02:00.009-07:00", "finished_at": "2026-08-06T09:02:00.012-07:00", "duration_ms": 3},
    {"name": "resolve_schemas", "started_at": "2026-08-06T09:02:00.013-07:00", "finished_at": "2026-08-06T09:02:00.021-07:00", "duration_ms": 8},
    {"name": "search_managed", "started_at": "2026-08-06T09:02:00.022-07:00", "finished_at": "2026-08-06T09:02:00.082-07:00", "duration_ms": 60}
  ],
  "attempts": [
    {"started_at": "2026-08-06T09:02:00.000-07:00", "finished_at": "2026-08-06T09:02:00.087-07:00", "duration_ms": 87,
     "command_timings": [{"command_index": 0, "started_at": "2026-08-06T09:02:00.000-07:00", "finished_at": "2026-08-06T09:02:00.087-07:00", "duration_ms": 87}],
     "operation_timings": [
       {"name": "load_config", "started_at": "2026-08-06T09:02:00.002-07:00", "finished_at": "2026-08-06T09:02:00.008-07:00", "duration_ms": 6},
       {"name": "route", "started_at": "2026-08-06T09:02:00.009-07:00", "finished_at": "2026-08-06T09:02:00.012-07:00", "duration_ms": 3},
       {"name": "resolve_schemas", "started_at": "2026-08-06T09:02:00.013-07:00", "finished_at": "2026-08-06T09:02:00.021-07:00", "duration_ms": 8},
       {"name": "search_managed", "started_at": "2026-08-06T09:02:00.022-07:00", "finished_at": "2026-08-06T09:02:00.082-07:00", "duration_ms": 60}
     ],
     "status": "matched"}
  ],
  "selection": {"tier": "explicit", "bases": ["claw"], "reasons": ["explicit base name"]},
  "hierarchy": [
    {"path": "/absolute/project/.mem/main/pkg/clawgateway", "schema": "pkg", "decision": "searched",
     "reason": "The gateway query matches the package knowledge hierarchy."}
  ],
  "fallback": {"used": false, "paths": [], "reason": "Managed knowledge already contained a matching document."},
  "status": "matched",
  "matched_paths": ["/absolute/project/.mem/main/pkg/clawgateway/ref/authentication.md"],
  "source_scopes": []
}
```

`started_at`, `finished_at`, `duration_ms`, `lookup_id`, `occurrence_count`,
`query`, `commands`, `operations`, `attempts`, `hierarchy`, and `source_scopes`
are required.
Every lookup, executed command, and operation has timezone-aware ISO 8601
start/end timestamps with millisecond precision plus a nonnegative elapsed
`duration_ms` measured from a monotonic clock. Top-level `started_at` is the
first attempt, `finished_at` is the latest attempt, `duration_ms` is the sum of
attempt durations, and `operations` reflects the latest attempt. `attempts`
retains every attempt's command timing, per-stage timing, and terminal status.
`operations` is ordered and records actual stages such as `load_config`,
`route`, `resolve_schemas`, `search_managed`, and `search_source` when fallback
occurs. Do not create operation entries for stages that did not run.

`commands[].argv` preserves the exact executed argument tokens;
`commands[].command` is their safely quoted, replayable shell representation.
Record only commands that actually executed; internal function calls are not
fabricated as CLI invocations.

Each `hierarchy` entry explains an observed path decision with `path`, `schema`,
`decision`, and a concise evidence-backed `reason`. Record actual selected bases,
schema descriptions or nodes, searched managed paths, and source-fallback paths;
do not invent model reasoning or claim deterministic node inference that did not
occur. `selection`, `fallback`, `status`, and `matched_paths` connect those
decisions to the observable outcome. Failed or ambiguous audited lookups are
recorded with their real status and empty fields where no selection occurred.

Tracing may write only inside the configured trace root; managed knowledge and
source scopes remain unmodified. Do not capture environment variables, file
bodies, credentials, or unrelated shell commands. If the session ID is missing
or unsafe, or the trace destination cannot be created or updated, stop the
audit-enabled lookup with an explicit audit error instead of silently running an
unlogged search. Audit-disabled lookups create no trace directories or files.

## Implementation

1. Extend `scripts/load_config.py` to validate, merge, normalize, and expose the
   optional audit settings without changing existing base behavior.
2. Add a focused trace writer that resolves the current conversation ID, reuses
   its first-date trace path, fingerprints lookups, enforces permissions, and
   merges duplicate records under a conversation-scoped lock.
3. Instrument `scripts/context.py` and the unified CLI boundary to capture the
   real query, executed argv, routing reasons, hierarchy decisions, source
   fallback, terminal status, and monotonic timings for commands and stages.
4. Document configuration and trace fields in the public `mem` `README.md` and
   `CLI.md`; keep the runtime skill mirror generated from the canonical source.

## Verification

- Disabled or absent audit settings preserve existing output and create no trace.
- Enabled audit writes to the default or configured root under `YYYY/MM/DD` with
  the validated conversation session ID as the `.jsonl` filename.
- A conversation creates exactly one trace file; lookups after midnight reuse
  the folder chosen by the conversation's first audited lookup.
- Repeating the same lookup updates one record, increments `occurrence_count`,
  and retains each attempt's command and operation timings; distinct lookups
  produce separate, independently parseable JSON Lines records.
- Concurrent lookups from the same conversation cannot create duplicate files,
  duplicate fingerprints, partial records, or lost timing history.
- Every record preserves the actual query, exact argv and replayable command,
  selected hierarchy paths with grounded reasons, routing outcome, and fallback.
- Every lookup, executed command, and actual operation records valid start/end
  timestamps and a nonnegative monotonic duration; fallback timing appears only
  when source fallback actually runs.
- Ambiguous, unmatched, and invalid lookups record their actual terminal status.
- Invalid config, missing session IDs, unsafe paths, permission failures, and
  update failures stop audit-enabled searches without touching knowledge files.
- Trace directories and files have modes `0700` and `0600`; environment values,
  file contents, secrets, and fabricated commands never appear in records.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-08-06 09:15: Moved the skill-owned feature specification into the canonical public skills repository (019fd474-e957-75e3-8610-647bebd4a0bb - aca5b49)
- 2026-08-06 09:07: Defined one-file-per-conversation deduplication and fingerprinted lookup records with retained timing history (019fa5de-c89c-7402-ad74-2978a02a04ad - 568f4ac4ba173)
- 2026-08-06 09:03: Added lookup, command, and per-operation timestamps with monotonic elapsed durations (019fa5de-c89c-7402-ad74-2978a02a04ad - 568f4ac4ba173)
- 2026-08-06 09:02: Created the audit configuration and conversation-scoped JSON Lines trace format specification (019fa5de-c89c-7402-ad74-2978a02a04ad - 568f4ac4ba173)

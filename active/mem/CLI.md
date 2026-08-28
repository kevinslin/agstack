# mem CLI reference

Use `./scripts/mem.py` to migrate and inspect memory configuration, manage derived base indexes, explain routing, perform bounded document-preserving lookup, inspect schemas, and materialize schema nodes.

Run commands from the directory containing `SKILL.md`:

```bash
python3 ./scripts/mem.py --help
```

Python 3 and PyYAML are required for configuration, routing, and context commands. Schema commands execute `./scripts/schema.py` through `uv`, which installs the dependencies declared in that script.

## Command summary

```text
mem.py config show
mem.py context lookup
mem.py doctor --migrate
mem.py index build
mem.py index show
mem.py index check
mem.py route
mem.py schema list
mem.py schema show
mem.py schema describe
mem.py schema validate
mem.py schema materialize
```

All JSON commands emit compact JSON by default. Add `--pretty` for indented output.

## Configuration discovery

Unless `--config` is present, commands load:

1. the nearest `.mem.yaml` at or above `--cwd`;
2. `.mem.yaml` under `--home`.

The nearest configuration wins for duplicate base names. Unique home bases remain available. Base names and aliases must be globally unique after merging. Each base declares exactly one fixed `root` or session-relative `root_pattern`; a basename or absolute path glob matches `--cwd` or its nearest matching ancestor, and bases without a match are inactive. Path globs match one directory component at a time, so `/workspace/projects/*` keeps a nested session rooted at its project directory. Ordinary loading accepts only top-level configuration `version: 2`; after installing the updated skill, run `doctor --migrate` before using an existing version-1 configuration.

See [Config in the README](./README.md#config) for every `.mem.yaml` field, default, routing signal, and validation rule.

Common configuration options:

- `--config PATH`: load only this file; do not merge discovered files.
- `--cwd PATH`: directory used to find the nearest ancestor config and resolve base `root_pattern` values; defaults to the current directory.
- `--home PATH`: directory used for the home config; defaults to the current user's home.
- `--pretty`: indent JSON output.

## `config show`

Load, validate, merge, and print normalized configuration.

```bash
python3 ./scripts/mem.py config show [OPTIONS]
```

Options:

- `--config PATH`: load only the named configuration.
- `--cwd PATH`: override ancestor-config discovery.
- `--home PATH`: override home-config discovery.
- `--allow-missing-roots`: validate and normalize without requiring `root` and `managed_root` directories to exist. Custom schema paths must still exist.
- `--pretty`: indent JSON output.

The result includes `config_path`, ordered `config_paths`, configuration `version: 2`, normalized active `bases`, and the effective `audit` mapping. Each base includes its absolute resolved `root`, absolute `managed_root`, derived `index_path`, resolved `path_style`, normalized schemas and their configured mounts, and its owning `config_path`. A `root_pattern: proj*` base is active when `--cwd` is `proj.2025` or a descendant; unrelated sessions omit it. `audit.enabled` defaults to `false`, and `audit.trace_root` defaults to `$HOME/.config/mem/traces`.

```bash
python3 ./scripts/mem.py config show --pretty
python3 ./scripts/mem.py config show --config /tmp/example.mem.yaml --allow-missing-roots --pretty
```

The command exits nonzero and writes `error: ...` to stderr for missing files, invalid YAML, invalid fields, missing roots, unsafe managed roots, missing custom schema files, and name or alias collisions.

## `doctor --migrate`

Upgrade legacy configuration files before strict current-schema loading.

```bash
python3 ./scripts/mem.py doctor --migrate [OPTIONS]
```

Options:

- `--migrate`: required action; upgrade discovered legacy configuration files.
- `--config PATH`: migrate only the selected file.
- `--cwd PATH`, `--home PATH`: use the same project/home discovery controls as ordinary commands.
- `--pretty`: indent JSON output.

For each top-level configuration `version: 1`, migration sets `version: 2` and drops every base's retired `match.topics` and `match.artifact_kinds`. It preserves `cwd_globs` and `source_globs`; if neither remains, it removes the empty `match` mapping entirely. Roots, aliases, schemas, priority, auditing, and other supported settings remain intact. Existing valid version-2 files are unchanged. Retired values are discarded rather than copied into generated indexes.

All transformed files and their merged configuration are validated before any file is written. Changed files retain their original permissions and are replaced atomically one at a time; rerunning safely completes a partial write failure. Migration neither generates indexes nor leaves backups or lockfiles.

Successful per-file work emits one JSON object containing `mode: doctor_migrate`, overall `status`, ordered `config_paths`, and `results`. Each result contains `config_path`, `from_version`, `to_version`, `status` (`migrated`, `unchanged`, or `error`), and `removed_fields`; failed results include `error`. `removed_fields` counts removed configuration keys, not list elements.

```bash
# Migrate both discoverable project and home files, if present.
python3 ./scripts/mem.py doctor --migrate --pretty

# Migrate exactly one legacy configuration.
python3 ./scripts/mem.py doctor --migrate \
  --config /tmp/example.mem.yaml \
  --pretty
```

Exit `0` means every configuration was migrated or already current. Exit `1` means a per-file replacement or final strict reload failed after planning; rerun after correcting the reported error. Exit `2` means invalid arguments, discovery, raw YAML/version inspection, or merged prevalidation failed before any configuration write.

## Base index commands

Each base owns `<managed_root>/.mem.index.json`, a disposable, format-version-1 cache of generated topics, artifact kinds, eligible Markdown document count, relative-path fingerprint, and the first two logical hierarchy levels. Its version is independent of `.mem.yaml` configuration version 2.

Builds and freshness checks scan **every** eligible non-symlink Markdown path without file-count or directory-count limits. They do not read document contents. The existing 2,000-file/500-directory context-search limits apply only to knowledge and source lookup, never to index generation or verification. Concurrent commands use advisory locks on the existing managed-root directory; no durable `.lock` file is created.

All index commands accept `--config PATH`, `--cwd PATH`, `--home PATH`, and `--pretty`. They require existing managed roots and reject `--allow-missing-roots`.

### `index build`

Create, update, repair, or leave unchanged the indexes for one selected base or all configured bases.

```bash
python3 ./scripts/mem.py index build (--base NAME_OR_ALIAS | --all) [OPTIONS]
```

- `--base NAME_OR_ALIAS`: select exactly one configured base name or alias.
- `--all`: process every configured base in merged configuration order.

Exactly one of `--base` and `--all` is required. Per-base statuses are `created`, `updated`, `unchanged`, or `error`. Identical relative-path fingerprints preserve existing index bytes and `generated_at`; safe malformed regular index files are repairable. Run this command after external creation, rename, deletion, synchronization, or direct agent creation of a managed Markdown document.

```bash
python3 ./scripts/mem.py index build --base oai --pretty
python3 ./scripts/mem.py index build --all --pretty
```

### `index show`

Load, validate, and print one stored index without scanning or modifying knowledge paths.

```bash
python3 ./scripts/mem.py index show --base NAME_OR_ALIAS [OPTIONS]
```

`--base` is required; `--all` is unsupported. Per-base statuses are `loaded`, `missing`, `invalid`, or `error`. A `loaded` result includes the validated full `index` payload. `show` does not claim the stored index is current.

```bash
python3 ./scripts/mem.py index show --base oai --pretty
```

### `index check`

Recompute the uncapped path fingerprint and compare it with each stored index without modifying any index or knowledge document.

```bash
python3 ./scripts/mem.py index check (--base NAME_OR_ALIAS | --all) [OPTIONS]
```

Exactly one of `--base` and `--all` is required. Per-base statuses are `current`, `missing`, `stale`, `invalid`, or `error`.

```bash
python3 ./scripts/mem.py index check --base oai --pretty
python3 ./scripts/mem.py index check --all --pretty
```

### Index results and exits

Every index command that reaches per-base work emits one JSON object with `mode`, overall `status`, `config_paths`, and ordered `results`. Each result contains `base`, `index_path`, `status`, `document_count`, `source_fingerprint`, `changed`, and any applicable `error`; `show` additionally returns the validated `index` when loaded. Unknown metadata for missing or invalid indexes is `null`. `changed` is `true` only when `build` creates or updates an index.

Exit `0` means every build/show succeeded or every checked index is current. Exit `1` means at least one selected base was missing, stale, invalid, or failed; `--all` still processes subsequent bases. Exit `2` means arguments, configuration, base selection, or an unsafe index path prevented safe per-base execution. Symlink and out-of-bound index locations are rejected.

## `route`

Select a configured base and explain the routing decision without changing knowledge documents. Routing may create missing derived base indexes before consuming their generated query signals.

```bash
python3 ./scripts/mem.py route --query TEXT [OPTIONS]
```

Options:

- `--query TEXT`: required user intent or durable artifact request.
- `--target NAME_OR_ALIAS`: select an explicit base or alias.
- `--source PATH`: source path used for ownership matching; repeat for multiple scopes. The route command matches strings and does not require the paths to exist.
- `--artifact-kind KIND`: explicit artifact signal such as `guide` or `runbook`.
- `--config PATH`, `--cwd PATH`, `--home PATH`: configuration controls.
- `--allow-missing-roots`: route against valid configuration whose base roots do not yet exist.
- `--pretty`: indent JSON output.

Routing tiers are strict: `explicit` precedes `ownership`, which precedes `query`. Within ownership, fixed-root bases take precedence over pattern-root bases; multiple owners at the same precedence remain ambiguous. Inactive pattern bases cannot be selected. The result has `status` (`selected`, `ambiguous`, or `no_match`), `tier`, `selected`, ranked `candidates`, and `config_paths`. Candidate records include the base name, root, managed root, score, priority, config path, index status, and reasons. Query routing may initialize multiple candidate indexes; explicit or ownership routing initializes only the selected base.

### Query routing

The router evaluates the query only when no `--target` is supplied and no base owns the current directory or any `--source` path. It scores each configured base by comparing `--query` with that base's name, aliases, description, and path-derived index metadata:

| Matching signal | Points per match | Candidate reason |
| --- | ---: | --- |
| Base `name` or an entry in `aliases` | 120 | `name-or-alias:<value>` |
| A generated entry in `metadata.topics` | 50 | `index-topic:<value>` |
| A generated entry in `metadata.artifact_kinds` | 30 | `index-artifact:<value>` |
| The complete base `description` | 80 | `description:<value>` |
| A two- or three-word phrase from `description` | 80 | `description:<phrase>` |
| An individual meaningful word from `description` | 3 | `description:<word>` |

Points accumulate when multiple signals match. Matching is case-insensitive. Phrases also match after punctuation and spaces are removed when the normalized phrase contains at least five characters, so names such as `open-claw` can match `openclaw`.

Description phrases are built after removing generic words such as `knowledge`, `notes`, `workspace`, `project`, `specs`, and `openai`. Artifact matching uses `--artifact-kind` when provided; otherwise it uses the first recognized artifact word in the query, such as `guide`, `runbook`, `spec`, `report`, or `research`.

Artifact classification precedes topic classification and uses these fixed aliases:

| Observed first- or second-level label | Generated artifact kinds |
| --- | --- |
| `cook`, `cookbook`, `cookbooks` | `cookbook`, `guide` |
| `decision`, `decisions` | `decision` |
| `finding`, `findings` | `finding` |
| `guide`, `guides` | `guide` |
| `lesson`, `lessons` | `lesson` |
| `ref`, `refs`, `reference`, `references` | `reference` |
| `report`, `reports` | `report` |
| `research` | `research` |
| `runbook`, `runbooks` | `runbook` |
| `spec`, `specs` | `spec` |

Labels are case-folded, tokenized as ASCII alphanumeric words, and rejoined with spaces. Empty and numeric-only labels are ignored. A matched artifact label never also becomes a topic; another first- or second-level label becomes a topic unless all its tokens belong to the fixed generic set `and`, `at`, `base`, `docs`, `for`, `knowledge`, `notes`, `openai`, `project`, `references`, `related`, `rooted`, `specifications`, `specs`, `tasks`, or `workspace`. Generated topic and artifact lists are sorted and deduplicated.

Missing indexes are built lazily; malformed indexes are reported as `invalid` and repaired only by explicit `index build`. If initialization fails, the base reports `build_failed` and still participates through its name, aliases, and description.

Candidates are ordered by descending score, descending configured `priority`, and finally alphabetical base name. Selection then follows these rules:

1. If only one base is configured, select it even when its score is zero.
2. With multiple bases, the highest score must be greater than zero and either exceed the next score by at least 15 points or tie that score while having a strictly higher `priority`.
3. Otherwise return `ambiguous`. A higher priority cannot rescue a zero-score tie, a 1–14 point lead, or conflicting ownership.

For example, with a base named `claw` whose description contains `OpenClaw`:

```bash
python3 ./scripts/mem.py route \
  --query "OpenClaw gateway deployment" \
  --pretty
```

When the base index contributes no additional matching topic or artifact, the result selects `claw` in the `query` tier with score `123`: `120` for the base-name match and `3` for the meaningful description word `openclaw`. Matching generated index metadata increases that score by the weights shown above.

### Routing examples

```bash
python3 ./scripts/mem.py route \
  --query "write an OpenClaw runbook" \
  --source /Users/kevinlin/code/openclaw \
  --pretty

python3 ./scripts/mem.py route \
  --query "create a package guide" \
  --target oai \
  --artifact-kind guide \
  --pretty
```

`ambiguous` and `no_match` are valid JSON results and do not themselves produce a nonzero exit. A managed caller must treat both as stopping conditions and retry with an explicit `--target` after resolving intent.

## `context lookup`

Search managed knowledge first, then optional source scopes, without changing knowledge documents or source files. A missing selected-base derived index may be created automatically.

```bash
python3 ./scripts/mem.py context lookup --query TEXT [OPTIONS]
```

Options:

- `--query TEXT`: required non-empty search text.
- `--target NAME_OR_ALIAS`: select an explicit base or alias.
- `--source PATH`: existing regular file or directory used for routing and fallback search; repeat for at most 20 scopes. Symlink scopes are rejected.
- `--allow-multiple`: when routing is ambiguous, search every reported candidate base; document/source content remains unchanged, although missing derived indexes may be initialized.
- `--artifact-kind KIND`: optional routing artifact signal.
- `--config PATH`, `--cwd PATH`, `--home PATH`: configuration controls.
- `--pretty`: indent JSON output.

### Lookup execution

`context lookup` follows this sequence:

1. Discover the nearest and home `.mem.yaml` files, or load only `--config`. If neither discovered file exists, return `missing_config` successfully; a missing explicitly requested `--config` returns `invalid_config`.
2. Load and validate the effective configuration. If audit tracing is enabled, validate `CODEX_THREAD_ID` and lock the conversation trace before the lookup can proceed.
3. Normalize and deduplicate `--source` paths. Each source must already exist, be a regular file or directory, and not itself be a symlink. Trim `--query` and reject an empty value.
4. Run the same routing algorithm as `route`: explicit target first, filesystem ownership second, and query scoring last.
5. Select the routed base. An ambiguous route stops unless `--allow-multiple` is present, in which case the command searches the reported candidate bases. `--allow-multiple` does not override `no_match` and never permits writes.
6. Resolve each selected base's configured schema names to bundled or custom `schema.yaml` paths. A missing schema or duplicate schema name returns `invalid_schema`. The command reports schemas as context; it does not infer or materialize a schema node.
7. Load the base's derived index, generating it only if missing. Existing valid indexes are not checked for freshness; malformed indexes report `invalid`, and failed initialization reports `build_failed`. Neither condition suppresses normal knowledge search.
8. Search existing files under each selected `managed_root`. If any managed matches are found, return them immediately without searching source files. Indexed hierarchy nodes never restrict or replace this bounded search.
9. If managed knowledge has no match and validated source scopes were supplied, search only those scopes. Return their matches or `no_matches`. Without source scopes, return `no_matches` directly.
10. When audit is enabled, atomically persist the observed command, operations, decisions, and outcome before returning.

The command never writes, materializes, moves, or deletes knowledge documents or source files. Its only permitted managed-root write creates a missing derived `.mem.index.json`; enabled audit tracing separately updates its configured trace file.

### Match semantics

Search matching is case-insensitive. A filename or individual line matches when it contains either the complete query or every alphanumeric term extracted from the query. All terms must occur in the same filename or line; matches are not assembled across multiple lines.

Each file produces at most one result, with this precedence:

1. `filename`: the basename matches; `line` and `line_text` are `null`.
2. `heading`: a matching line begins with `#` after leading whitespace is removed.
3. `body`: the first matching non-heading line, used only when no matching heading exists.

Directories and filenames are traversed in sorted order. Managed bases are searched in their selected order, and source scopes are searched in the order provided. Overlapping source scopes do not produce duplicate file results.

### Search bounds and safety

Managed search and source fallback each have independent limits:

- 2,000 scanned files across that search area.
- 500 scanned directories across that search area.
- 20 returned matches across that search area.
- 1,000,000 bytes per file.
- 500 characters per returned matching line.
- 20 supplied source scopes before deduplication.

The walker skips symlink files and directories, hidden directories, and common generated/dependency directories such as `.git`, `node_modules`, `vendor`, `build`, `dist`, and `__pycache__`. Non-UTF-8, binary, oversized, and unreadable files are skipped. `search_stats` records skipped files, read errors, scanned counts, and whether either search was truncated.

These bounds apply only to normal document/source lookup. Index build, check, lazy initialization, and post-creation refresh always scan all eligible Markdown paths without inheriting any lookup traversal cap.

### Result fields

Every invocation emits a JSON object containing:

- `mode`: always `context_lookup`.
- `status`: the terminal lookup or validation status.
- `query`: the trimmed query string.
- `sources`: normalized source paths; duplicates are removed after validation.
- `config_paths`: configuration files considered or loaded, in precedence order.
- `route`: the complete routing result, or `null` when validation stops before routing.
- `selected_bases`: each selected base's `name`, `root`, `managed_root`, `path_style`, `config_path`, resolved `schemas`, and `index`; validated index metadata includes `status`, `generated_at`, `source_fingerprint`, generated `metadata`, and two-level `hierarchy`.
- `managed_matches`: records containing `base`, absolute `path`, `relative_path` under the managed root, `match_type`, `line`, and `line_text`.
- `fallback_used`: `true` only when no managed match exists and at least one source scope is searched.
- `source_matches`: records containing absolute `path`, source `scope`, `match_type`, `line`, and `line_text`.
- `search_stats`: scanned/skipped counts, truncation flags, and active `limits`.
- `selection`, `hierarchy`, `fallback`, `matched_paths`, and `candidates`: audit-compatible projections of the observed routing, paths searched, fallback decision, and concrete matches. Top-level `hierarchy` remains schema-derived; generated index hierarchy lives only under `selected_bases[].index` and never changes audit lookup identity.
- `error`: an explanation included for invalid configuration, query, source, or schema.

### Context lookup examples

```bash
# Search only the selected base's managed knowledge.
python3 ./scripts/mem.py context lookup \
  --query "gateway authentication" \
  --target claw \
  --pretty

# Fall back to this exact source scope only when managed knowledge has no match.
python3 ./scripts/mem.py context lookup \
  --query "gateway authentication" \
  --target claw \
  --source /Users/kevinlin/code/openclaw \
  --pretty

# Search candidate bases without modifying their knowledge documents.
python3 ./scripts/mem.py context lookup \
  --query "deployment guide" \
  --allow-multiple \
  --pretty
```

### Context lookup statuses

| JSON status | Exit status | Meaning |
| --- | ---: | --- |
| `matched` | 0 | Managed knowledge matched, or source fallback found a match. |
| `no_matches` | 0 | The selected areas were searched but no file matched. |
| `missing_config` | 0 | No discoverable configuration exists; continue without managed context. |
| `ambiguous` | 2 | Several bases match and `--allow-multiple` was not supplied. |
| `no_match` | 2 | Routing could not select a base, including an unknown explicit target. |
| `invalid_query` | 2 | The trimmed query is empty. |
| `invalid_source` | 2 | A source is missing, unsafe, unsupported, or exceeds the scope limit. |
| `invalid_config` | 2 | The selected configuration is missing or fails validation. |
| `invalid_schema` | 2 | A selected base references a missing or duplicate schema. |

Inspect the JSON `status` and optional `error` rather than relying on exit status alone.

## Audit traces

Add an optional top-level mapping to `.mem.yaml`:

```yaml
audit:
  enabled: true
  trace_root: ~/.config/mem/traces
```

`enabled` must be a Boolean and defaults to `false`. `trace_root` is expanded and normalized to an absolute path and defaults to `$HOME/.config/mem/traces`. The nearest configuration that declares `audit` owns the whole effective mapping; missing fields receive defaults instead of being inherited from the home mapping.

An enabled lookup requires a valid conversation UUID in `CODEX_THREAD_ID`. Its first lookup selects `<trace_root>/<local YYYY>/<MM>/<DD>/<CODEX_THREAD_ID>.jsonl`; later lookups reuse that file after midnight. Directories use mode `0700`, files use mode `0600`, same-conversation updates are locked, and each completed update atomically replaces the trace file.

Each nonempty line is a version-1 JSON record with:

- identity and aggregate timing: `session_id`, `lookup_id`, `started_at`, `finished_at`, `duration_ms`, and `occurrence_count`;
- exact execution: `query`, `commands[].argv`, safely quoted `commands[].command`, and ordered `operations` that actually ran;
- occurrence history: `attempts` with command timings, operation timings, duration, and terminal trace status;
- outcome evidence: `selection`, `hierarchy`, `fallback`, `status`, `matched_paths`, and ordered `source_scopes`.

`lookup_id` hashes canonical logical identity inputs: session ID, query, ordered command arguments, selected bases, hierarchy paths, and source scopes. Timing, scores, outcomes, and explanatory prose are excluded. Repeated identities merge into one record by incrementing `occurrence_count`, appending an attempt, updating the latest outcome, and adding elapsed duration.

Traces record no environment values, file bodies, credentials, unrelated commands, fabricated invocations, or private reasoning. Missing or invalid session identity, unsafe containment, bad permissions, lock failure, malformed existing data, serialization failure, or atomic-write failure stops an audit-enabled lookup explicitly; it never continues as an unlogged search.

Index operations appear in audit timings only when actually performed: `build_index` for missing-index generation and `load_index` for a real index read. The index payload and index hierarchy paths are not copied into traces or incorporated into `lookup_id`.

## Schema inspection

Bundled schemas live under `./references/schemas/<name>/schema.yaml`.

### `schema list`

List bundled schemas and their root nodes.

```bash
python3 ./scripts/mem.py schema list
```

Each line is `<schema>\troot: <roots>`. An invalid schema is reported inline as `<schema>\tinvalid: <error>`; the command still exits `0` so callers must inspect the output.

### `schema show`

Print variables and the fully composed schema tree.

```bash
python3 ./scripts/mem.py schema show SCHEMA [--schema-path PATH]
```

- `SCHEMA`: bundled schema name and display label.
- `--schema-path PATH`: inspect this explicit `schema.yaml` instead of the bundled schema. The positional schema remains required and labels the output.

```bash
python3 ./scripts/mem.py schema show pkg
```

### `schema describe`

Print every composed path that has a description as Markdown bullets.

```bash
python3 ./scripts/mem.py schema describe SCHEMA [--schema-path PATH]
```

Use this command before choosing a node for managed knowledge placement.

```bash
python3 ./scripts/mem.py schema describe global-core
```

### `schema validate`

Validate the schema document, variables, nodes, templates, and composed children.

```bash
python3 ./scripts/mem.py schema validate SCHEMA [--schema-path PATH]
```

Successful output is:

```text
<schema> valid <absolute-schema-path>
```

The separators are tabs. Invalid schemas print `error: ...` to stderr and exit `1`.

## `schema materialize`

Render selected schema nodes into either a configured managed base or an explicitly unmanaged destination.

### Managed mode

```bash
python3 ./scripts/mem.py schema materialize SCHEMA \
  --base BASE \
  [--root-relative PATH] \
  [--var KEY=VALUE]... \
  [--include RENDERED_PATH]... \
  [--overwrite | --skip-existing]
```

Managed-only options:

- `--base BASE`: required base name or alias. The schema must be configured on that base.
- `--root-relative PATH`: materialize below this relative subtree of the base's resolved managed root. Absolute paths and `..` escapes are rejected.
- `--config PATH`, `--cwd PATH`, `--home PATH`: configuration controls used to resolve the base.

Managed mode derives `--out`, `--path-style`, the schema's configured `root` mount, and a custom `--schema-path` from the base configuration. Supplying output, path-style, or schema-path overrides directly is an error. A schema `root: packages` prefixes include paths with `packages/`, `root: .` leaves them inline, and an omitted `pkg` root preserves its legacy `pkg/` prefix. `--base` and `--unmanaged` are mutually exclusive.

After successful managed materialization, the selected base's index is rebuilt automatically. A changed document path updates the fingerprint; overwriting or skipping existing documents without a path change preserves the existing index. A failed schema subprocess retains its original nonzero exit and does not refresh the index. Unmanaged materialization never refreshes a managed index.

```bash
python3 ./scripts/mem.py schema materialize pkg \
  --base oai \
  --var package=clawcmd \
  --var cook=change-claw-config \
  --include pkg/clawcmd/cook/change-claw-config \
  --skip-existing
```

### Managed index-refresh warnings

If materialization succeeds but its post-success index refresh fails, the command preserves the created knowledge, exact successful stdout, and exit status `0`. It appends exactly one compact JSON warning to stderr after any existing schema stderr:

```json
{"level":"warning","code":"index_refresh_failed","base":"oai","index_path":"/managed/root/.mem.index.json","error":"lock timed out after 5 seconds","repair_argv":["mem.py","index","build","--base","oai","--config","/path with spaces/.mem.yaml","--cwd","/workspace","--home","/home/operator"]}
```

All six warning fields are required. `repair_argv` is the only canonical repair action: its first element is the original CLI entrypoint, followed by `index build --base` and the original selected base, then each explicitly supplied original `--config`, `--cwd`, and `--home` option with its exact value. Options not originally supplied are omitted. Execute the array directly without shell interpolation so values containing spaces remain intact; do not expect a separate `repair_command`. Surface the warning and repair the disposable index, but never roll back or report the successful document creation as failed.

### Unmanaged mode

```bash
python3 ./scripts/mem.py schema materialize SCHEMA \
  --out PATH \
  --unmanaged \
  [--schema-path PATH] \
  [--path-style directory|dotted] \
  [--var KEY=VALUE]... \
  [--include RENDERED_PATH]... \
  [--overwrite | --skip-existing]
```

Unmanaged-only options:

- `--out PATH`: explicit output directory; requires `--unmanaged`.
- `--unmanaged`: confirms that the destination is outside managed memory ownership.
- `--schema-path PATH`: use an explicit schema file.
- `--path-style directory|dotted`: choose nested paths such as `pkg/foo/readme.md` or dotted paths such as `pkg.foo.readme.md`. When omitted, the engine infers a style from the include/output-root convention.

`--config`, `--cwd`, `--home`, and `--root-relative` are rejected in unmanaged mode.

```bash
python3 ./scripts/mem.py schema materialize integ-proof \
  --out /tmp/proofs \
  --unmanaged \
  --path-style directory \
  --var proof=example \
  --include example/proof \
  --skip-existing
```

### Shared materialization options

- `SCHEMA`: schema name. In managed mode it must appear in the selected base's `schemas` list.
- `--var KEY=VALUE`: template variable; repeat as needed. Required variables without defaults must be supplied, and declared value restrictions are enforced.
- `--include RENDERED_PATH`: full rendered schema path to materialize; repeat to select multiple nodes. Use slash-separated paths for `directory` style and dotted paths for `dotted` style.
- `--overwrite`: replace existing generated files.
- `--skip-existing`: leave existing files untouched and print only newly written paths.

`--overwrite` and `--skip-existing` are mutually exclusive. Without either flag, the command refuses to overwrite an existing file. On success, stdout contains one generated path per line. Errors print `error: ...` to stderr and exit nonzero.

Materialize explicit leaf paths whenever possible. Omitting `--include` can select every renderable node whose variables resolve, which is rarely appropriate for managed knowledge.

## Common recovery paths

- **`missing config`**: managed configuration is optional for context lookup. Continue the underlying read task without `$mem`, or pass the intended `--config` if one exists.
- **legacy configuration version**: run `python3 ./scripts/mem.py doctor --migrate --pretty` after installing the updated skill; use `--config` when migrating only a selected file.
- **`ambiguous` or `no_match` route**: inspect candidates with `route --pretty`, then retry with `--target`.
- **missing, stale, or invalid index**: run `python3 ./scripts/mem.py index build --base NAME_OR_ALIAS`; use `index check --all` when verifying all configured bases after synchronization.
- **`index_refresh_failed` warning after successful creation**: preserve the created document and successful exit, then replay the warning's `repair_argv` exactly.
- **unknown base**: run `config show --pretty` and use a normalized base name or alias.
- **schema is not configured for base**: choose one of the base's configured schemas or update the canonical configuration outside this command.
- **managed path rejected**: remove the absolute or traversing `--root-relative` value; managed output must remain inside `managed_root`.
- **refusing to overwrite**: inspect the existing file, then choose `--skip-existing` or explicitly authorize `--overwrite`.
- **invalid schema**: run `schema validate` and correct the schema or composed child before materializing.

## Related documentation

- [`README.md`](./README.md): architecture, boundaries, and invariants.
- [`SKILL.md`](./SKILL.md): managed workflow and final-response contract.
- [`./references/knowledge-workflow.md`](./references/knowledge-workflow.md): read/write/update/delete behavior.
- [`./references/schema-workflow.md`](./references/schema-workflow.md): schema model and authoring rules.

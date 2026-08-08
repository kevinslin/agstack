# mem CLI reference

Use `./scripts/mem.py` to inspect memory configuration, explain routing, perform bounded read-only lookup, inspect schemas, and materialize schema nodes.

Run commands from the directory containing `SKILL.md`:

```bash
python3 ./scripts/mem.py --help
```

Python 3 and PyYAML are required for configuration, routing, and context commands. Schema commands execute `./scripts/schema.py` through `uv`, which installs the dependencies declared in that script.

## Command summary

```text
mem.py config show
mem.py context lookup
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

The nearest configuration wins for duplicate base names. Unique home bases remain available. Base names and aliases must be globally unique after merging.

See [Config in the README](./README.md#config) for every `.mem.yaml` field, default, routing signal, and validation rule.

Common configuration options:

- `--config PATH`: load only this file; do not merge discovered files.
- `--cwd PATH`: directory used to find the nearest ancestor config; defaults to the current directory.
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

The result includes `config_path`, ordered `config_paths`, `version`, and normalized `bases`. Each base includes absolute `root`, absolute `managed_root`, resolved `path_style`, normalized schemas, and its owning `config_path`.

```bash
python3 ./scripts/mem.py config show --pretty
python3 ./scripts/mem.py config show --config /tmp/example.mem.yaml --allow-missing-roots --pretty
```

The command exits nonzero and writes `error: ...` to stderr for missing files, invalid YAML, invalid fields, missing roots, unsafe managed roots, missing custom schema files, and name or alias collisions.

## `route`

Select a configured base and explain the routing decision without reading or writing knowledge files.

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

Routing tiers are strict: `explicit` precedes `ownership`, which precedes `query`. The result has `status` (`selected`, `ambiguous`, or `no_match`), `tier`, `selected`, ranked `candidates`, and `config_paths`. Candidate records include the base name, root, managed root, score, priority, config path, and reasons.

### Query routing

The router evaluates the query only when no `--target` is supplied and no base owns the current directory or any `--source` path. It scores each configured base by comparing `--query` with that base's name, aliases, description, and optional `match` fields:

| Matching signal | Points per match | Candidate reason |
| --- | ---: | --- |
| Base `name` or an entry in `aliases` | 120 | `name-or-alias:<value>` |
| An entry in `match.topics` | 50 | `topic:<value>` |
| An entry in `match.artifact_kinds` | 30 | `artifact:<value>` |
| The complete base `description` | 80 | `description:<value>` |
| A two- or three-word phrase from `description` | 80 | `description:<phrase>` |
| An individual meaningful word from `description` | 3 | `description:<word>` |

Points accumulate when multiple signals match. Matching is case-insensitive. Phrases also match after punctuation and spaces are removed when the normalized phrase contains at least five characters, so names such as `open-claw` can match `openclaw`.

Description phrases are built after removing generic words such as `knowledge`, `notes`, `workspace`, `project`, `specs`, and `openai`. Artifact matching uses `--artifact-kind` when provided; otherwise it uses the first recognized artifact word in the query, such as `guide`, `runbook`, `spec`, `report`, or `research`.

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

The result selects `claw` in the `query` tier with score `123`: `120` for the base-name match and `3` for the meaningful description word `openclaw`.

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

Search managed knowledge first, then optional source scopes, without writing files.

```bash
python3 ./scripts/mem.py context lookup --query TEXT [OPTIONS]
```

Options:

- `--query TEXT`: required non-empty search text.
- `--target NAME_OR_ALIAS`: select an explicit base or alias.
- `--source PATH`: existing regular file or directory used for routing and fallback search; repeat for at most 20 scopes. Symlink scopes are rejected.
- `--allow-multiple`: when routing is ambiguous, search every reported candidate base. Use only for read-only lookup.
- `--artifact-kind KIND`: optional routing artifact signal.
- `--config PATH`, `--cwd PATH`, `--home PATH`: configuration controls.
- `--pretty`: indent JSON output.

### Lookup execution

`context lookup` follows this sequence:

1. Discover the nearest and home `.mem.yaml` files, or load only `--config`. If neither discovered file exists, return `missing_config` successfully; a missing explicitly requested `--config` returns `invalid_config`.
2. Normalize and deduplicate `--source` paths. Each source must already exist, be a regular file or directory, and not itself be a symlink. Trim `--query` and reject an empty value.
3. Load and validate the effective configuration, then run the same routing algorithm as `route`: explicit target first, filesystem ownership second, and query scoring last.
4. Select the routed base. An ambiguous route stops unless `--allow-multiple` is present, in which case the command searches the reported candidate bases. `--allow-multiple` does not override `no_match` and never permits writes.
5. Resolve each selected base's configured schema names to bundled or custom `schema.yaml` paths. A missing schema or duplicate schema name returns `invalid_schema`. The command reports schemas as context; it does not infer or materialize a schema node.
6. Search existing files under each selected `managed_root`. If any managed matches are found, return them immediately without searching source files.
7. If managed knowledge has no match and validated source scopes were supplied, search only those scopes. Return their matches or `no_matches`. Without source scopes, return `no_matches` directly.

The command never writes, materializes, moves, or deletes files.

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

### Result fields

Every invocation emits a JSON object containing:

- `mode`: always `context_lookup`.
- `status`: the terminal lookup or validation status.
- `query`: the trimmed query string.
- `sources`: normalized source paths; duplicates are removed after validation.
- `config_paths`: configuration files considered or loaded, in precedence order.
- `route`: the complete routing result, or `null` when validation stops before routing.
- `selected_bases`: each selected base's `name`, `root`, `managed_root`, `path_style`, `config_path`, and resolved `schemas`.
- `managed_matches`: records containing `base`, absolute `path`, `relative_path` under the managed root, `match_type`, `line`, and `line_text`.
- `fallback_used`: `true` only when no managed match exists and at least one source scope is searched.
- `source_matches`: records containing absolute `path`, source `scope`, `match_type`, `line`, and `line_text`.
- `search_stats`: scanned/skipped counts, truncation flags, and active `limits`.
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

# Allow read-only lookup across candidate bases when routing is ambiguous.
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

Managed mode derives `--out`, `--path-style`, and a custom `--schema-path` from the base configuration. Supplying any of those options directly is an error. `--base` and `--unmanaged` are mutually exclusive.

```bash
python3 ./scripts/mem.py schema materialize pkg \
  --base oai \
  --var package=clawcmd \
  --var cook=change-claw-config \
  --include pkg/clawcmd/cook/change-claw-config \
  --skip-existing
```

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
- **`ambiguous` or `no_match` route**: inspect candidates with `route --pretty`, then retry with `--target`.
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

# Feature Spec: Generated Memory Base Index

**Date:** 2026-08-08
**Status:** Completed
**Owner:** Public `mem` skill maintainers

## Problem and Decision

Memory-base query routing currently accepts operator-maintained
`match.topics` and `match.artifact_kinds` in `.mem.yaml`. These fields duplicate
the knowledge already represented by a base's paths, drift as files change, and
make aggregate bases harder to maintain. Callers also lack a compact, portable
view of a base's top-level structure and must inspect the base to discover it.

Each base will instead own a generated `.mem.index.json` cache at the root of its
managed knowledge. The index records path-derived topic and artifact-kind
signals plus the first two logical levels of the base hierarchy. Routing uses
the generated signals to select a base, and context lookup exposes the hierarchy
without scanning documents to reconstruct it. The index does not replace the
existing managed full-text search; managed files remain authoritative. `mem`
creates a missing index when a base is first used and refreshes an existing
index after adding a managed knowledge entity. Existing configurations are
upgraded explicitly with `mem doctor --migrate`; indexing remains best-effort
after successful knowledge creation.

## Scope

**Changes**

- Generate `<managed_root>/.mem.index.json` from Markdown paths in each base.
- Migrate `.mem.yaml` from its existing top-level `version: 1` to `version: 2`
  with `mem doctor --migrate`; remove `match.topics` and
  `match.artifact_kinds` while preserving ownership globs and other supported
  configuration.
- Add CLI operations to build, inspect, and verify an index for one base or all
  configured bases.
- Completely scan every eligible document for index build and verification,
  without file-count or directory-count caps; keep normal lookup limits intact.
- Serialize concurrent index work per managed root without writing another
  durable artifact into the knowledge base.
- Use indexed metadata for query routing and expose the two-level hierarchy to
  context consumers without changing managed full-text search semantics.
- Lazily build missing indexes during base routing or context lookup.
- Refresh an index after `mem` creates a new managed Markdown entity; report
  refresh failures as structured warnings without failing successful creation.
- Update the `mem` skill instructions to require index maintenance for
  agent-authored managed knowledge creation.
- Document the generated-file lifecycle and update configuration examples.

**Does not change**

- Explicit target, filesystem ownership, query, and priority routing precedence.
- Base roots, managed-root containment, path styles, aliases, descriptions, or
  configured schemas.
- Managed search traversal, source fallback, result matching, search limits, or
  audit-trace semantics except for recording an actual index load.
- Files written outside `mem`, repository synchronization, or file watching.
- Automatic refresh after edits made outside the `mem` workflow; external
  editors and sync automation still invoke `index build` explicitly.
- Full-text indexing or storage of document bodies, headings, frontmatter,
  credentials, or absolute machine-local paths in the generated index.

## Contract

### Configuration and ownership

`.mem.yaml` remains the source of truth for base identity, containment, schemas,
path style, aliases, descriptions, ownership globs, and priority. The normalized
base record derives `index_path` as `<managed_root>/.mem.index.json`; users cannot
override that location.

The existing top-level `.mem.yaml` `version` is the sole configuration-schema
version; the new current value is `2`. Do not add `schema_version`, per-base
versions, or another configuration-version field. The generated index has its
own independent file-format `version: 1`; it does not version `.mem.yaml`.
Normal configuration loading accepts only configuration `version: 2`, and its
normalized single-file and merged results report `version: 2`.

Current-schema `match` accepts only `cwd_globs` and `source_globs`.
`version: 1` configurations fail normal loading with an error directing the
operator to run `mem doctor --migrate`. A `version: 2` configuration containing
`topics` or `artifact_kinds` is invalid and is not silently rewritten by normal
loading. Base name, aliases, and description remain query signals on every query
route, whether or not a usable index exists. Index metadata replaces only YAML
topic and artifact-kind signals. Existing ownership precedence, query weights,
priority tiebreaking, and score thresholds remain unchanged.

The generated index is a disposable cache owned by `mem`, not configuration and
not durable knowledge. It may be committed with the knowledge base so another
machine can route immediately after sync.

### Configuration migration

`mem doctor --migrate` discovers exactly the same ordered `.mem.yaml` files as
normal configuration loading, or only the file selected with `--config`.
Discovery, raw YAML parsing, and minimal mapping/version inspection occur
before strict current-schema validation, so existing `version: 1` files remain
reachable even though the ordinary loader now rejects them.

The migration accepts raw configuration versions `1` and `2` only. For every
version-1 configuration it sets the existing top-level `version` to `2` and
removes the `topics` and `artifact_kinds` keys from each base's `match`
mapping. If neither `cwd_globs` nor `source_globs` remains, remove the entire
`match` mapping from that base; preserve `match` only when at least one of those
ownership fields remains. Retired values are discarded, never copied into
another setting, and never injected into the generated index. Preserve
retained `match.cwd_globs` and `match.source_globs`, base order, ownership,
roots, managed roots, schemas, aliases, descriptions, priority, audit
configuration, and all other supported settings. An existing version-2 file is
unchanged and must already satisfy the current schema; migration does not
repair invalid current-version files.

Plan every discovered file in memory and validate the entire transformed,
merged configuration against the normal current-schema rules before writing any
file. Missing/noninteger/unsupported versions, malformed YAML, nonmapping
configuration or `match`, unsupported current-version fields, and ordinary
configuration errors fail before writes. Each changed configuration is then
written to a sibling temporary file with its existing permissions and
atomically replaced; unchanged files are never rewritten. Per-file replacement
is the atomicity boundary: a later file can fail after an earlier file has
already been migrated. Continue processing independently valid files, report
any failures, and rely on an idempotent rerun to finish a partially migrated
configuration set. After all writes succeed, reload and merge the on-disk
configuration through the ordinary strict current-schema loader. Migration
does not build indexes, translate retired signal values, or leave backup or
lock files behind.

### Indexed documents and logical hierarchy

The generator scans regular, non-symlink Markdown files beneath `managed_root`
using the same hidden-directory and generated-directory exclusions as managed
context search. It excludes `.mem.index.json` itself. It reads path metadata
only; it does not open document bodies. Every eligible directory and file must
be scanned: index build, check, automatic initialization, and post-creation
refresh have no maximum file count, maximum directory count, or inherited
managed-lookup traversal budget. Existing bounded managed context lookup and
path-style inference retain their current limits; neither is reused as the
index scanner.

Logical path components depend on `path_style`:

- `directory`: split the relative path on `/` and remove `.md` from the final
  component. `pkg/clawcmd/ref/auth.md` begins `pkg`, `clawcmd`.
- `dotted`: split directory components normally, then split the filename stem on
  `.`. `pkg.clawcmd.ref.auth.md` begins `pkg`, `clawcmd`.

The hierarchy contains each observed level-one component and its observed
level-two children. Each node records its portable logical path and descendant
document count. Components below level two are counted but not enumerated.
Values are deduplicated and sorted by normalized value, then original value, so
the file is deterministic across machines.

One shared `scripts/routing_signals.py` module owns normalization for both index
generation and query routing. It case-folds a hierarchy label, extracts
`[a-z0-9]+` tokens, and joins those tokens with one space. Empty labels and
labels whose tokens are all numeric are discarded.

Artifact classification runs before topic classification. The complete alias
expansion table is:

| Observed hierarchy label | Generated artifact kinds |
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

An exact normalized label in that table contributes the listed kinds and does
not become a topic. Every other normalized level-one or level-two label becomes
a topic unless all its tokens are in this complete generic-word set:
`and`, `at`, `base`, `docs`, `for`, `knowledge`, `notes`, `openai`, `project`,
`references`, `related`, `rooted`, `specifications`, `specs`, `tasks`, and
`workspace`. Topics and artifact kinds are unique, lexically sorted strings.
The table, stopword set, and normalizer are versioned with the index format and
cannot be customized in `.mem.yaml`.

### File format

The index is canonical UTF-8 JSON with a trailing newline:

```json
{
  "version": 1,
  "generated_at": "2026-08-08T13:26:00-07:00",
  "path_style": "directory",
  "source_fingerprint": "sha256:...",
  "document_count": 42,
  "metadata": {
    "topics": ["clawcmd", "gateway"],
    "artifact_kinds": ["guide", "reference", "spec"]
  },
  "hierarchy": [
    {
      "path": "pkg",
      "document_count": 30,
      "children": [
        {"path": "pkg/clawcmd", "document_count": 12}
      ]
    }
  ]
}
```

`source_fingerprint` hashes the index version, path style, and sorted eligible
relative paths. Because every generated signal is path-derived, body-only edits
do not stale the index. A build with the same fingerprint and format is a no-op
and preserves `generated_at`, avoiding meaningless repository changes.

The writer rejects a symlink index, containment escape, unsupported existing
format, or unsafe replacement target. A changed index is written to a sibling
temporary file and atomically renamed. Relative paths only are persisted.

All cooperating `mem` processes acquire an operating-system advisory lock on an
open file descriptor for the existing managed-root directory; they never
create a `.lock` file or another durable knowledge-base artifact. Builds and
automatic refreshes take an exclusive lock before scanning, re-read the index
after acquiring it, and then build or return an unchanged result. Checks and
shows take a shared lock for their complete scan/read operation. Independent
managed roots have independent locks; atomic replacement ensures noncooperating
readers see either the old complete index or the new complete index.

Lock acquisition waits at most five seconds. Failure to open or safely lock the
managed-root directory, or a lock timeout, is an index operation failure:
explicit index commands report the base as `error`, automatic route/context
initialization reports `build_failed` and continues lookup, and a
post-materialization refresh emits the structured warning defined below while
preserving successful knowledge creation. A process crash releases its
directory lock automatically and cannot leave a durable lock artifact.

### CLI and refresh lifecycle

The unified CLI adds:

```text
mem.py doctor --migrate [--pretty]
mem.py index build (--base NAME_OR_ALIAS | --all) [--pretty]
mem.py index show --base NAME_OR_ALIAS [--pretty]
mem.py index check (--base NAME_OR_ALIAS | --all) [--pretty]
```

All four commands also accept the existing `--config`, `--cwd`, and `--home`
configuration controls. For index `build` and `check`, `--base` and `--all` are
mutually exclusive and one is required; `show` accepts `--base` only. Index
operations require existing managed roots and do not accept
`--allow-missing-roots`.

`doctor --migrate` emits one JSON object on stdout after migration planning
reaches per-file work:

```json
{
  "mode": "doctor_migrate",
  "status": "ok",
  "config_paths": ["/path/to/.mem.yaml"],
  "results": [
    {
      "config_path": "/path/to/.mem.yaml",
      "from_version": 1,
      "to_version": 2,
      "status": "migrated",
      "removed_fields": 2
    }
  ]
}
```

Migration result statuses are `migrated`, `unchanged`, or `error`;
`removed_fields` counts removed `match` keys, not discarded list values, and an
`error` result also contains an `error` string. Top-level `status` is `ok` only
when all files are migrated or unchanged and the final strict reload succeeds;
otherwise it is `error`. Exit `0` means successful migration or an already
current configuration. Exit `1` means a per-file write or final reload failed;
already-replaced files remain valid and rerunning is safe. Exit `2` means
arguments, discovery, raw parsing, version inspection, or complete transformed
configuration prevalidation failed before any file was written; the existing
CLI argument/configuration error is emitted on stderr.

`build` scans and atomically creates or updates indexes. `show` validates and
prints the stored index without scanning. `check` scans paths, compares the
computed fingerprint with the stored index, and returns per-base status:
`current`, `missing`, `stale`, or `invalid`. Multi-base output preserves merged
configuration order. Unknown targets and unsafe or unreadable bases fail
explicitly; one failed `--all` base does not overwrite another base's index.

Every index invocation that reaches per-base work emits one JSON object with
`mode`, top-level `status`, `config_paths`, and ordered `results`. Each result
contains `base`, `index_path`, `status`, `document_count`,
`source_fingerprint`, `changed`, and an optional `error`. Build statuses are
`created`, `updated`, `unchanged`, or `error`; show statuses are `loaded`,
`missing`, `invalid`, or `error`; check statuses are `current`, `missing`,
`stale`, `invalid`, or `error`. `show` includes the validated index as `index`
and does not claim freshness. Fields that cannot be derived for a missing or
invalid index are `null`; `changed` is `true` only for `created` and `updated`
build results.

Exit `0` means every selected build/show succeeded or every checked index is
current. Exit `1` means the operation completed but at least one selected base
is missing, stale, invalid, or failed; `--all` still evaluates the remaining
bases. Exit `2` means arguments, configuration, base selection, or the index
path was invalid before per-base work could safely proceed.

`build` may replace a malformed existing index only when it is a regular,
non-symlink file at the derived in-root path. This is the repair path for a
disposable cache. `show` and `check` never modify it.

### Automatic generation and refresh

When routing or context lookup first considers a configured base, `mem` checks
its derived index path. If the index is missing, it scans that base and builds
the index before consuming generated query signals or hierarchy metadata. Query
routing may initialize multiple candidate bases; explicit and ownership routing
initialize only their selected base. An existing valid index is read without a
freshness scan. A malformed existing index is reported as `invalid` and is not
silently replaced; an explicit `index build` repairs it.

A failed automatic build, including a read-only managed root or advisory-lock
timeout, does not block routing or context lookup. The base reports
`index.status=build_failed` and the operation continues with configured name,
aliases, description, and the normal managed search. Partial index files are
never exposed.

After successful managed schema materialization, `mem` rebuilds the selected
base's index. A newly created entity changes the path fingerprint and updates
the index; an overwrite or `--skip-existing` operation with no path change is
an idempotent no-op. Managed materialization currently replaces its process via
`os.execvp`; supporting post-success refresh requires running that managed
command as a supervised subprocess, forwarding its existing stdout and stderr
without modification. A failed child preserves its original nonzero exit
status and does not refresh the index. A successful child always preserves
exit `0` and its exact schema stdout, even when the later index refresh fails.
Unmanaged materialization and schema inspection retain their existing
execution behavior.

After a successful child, a failed refresh appends exactly one compact,
newline-delimited JSON object to stderr after any existing child stderr:

```json
{"level":"warning","code":"index_refresh_failed","base":"NAME_OR_ALIAS","index_path":"/managed/root/.mem.index.json","error":"lock timed out after 5 seconds","repair_argv":["mem.py","index","build","--base","NAME_OR_ALIAS","--config","/path/to/.mem.yaml","--cwd","/workspace","--home","/home/operator"]}
```

All six fields are required; `error` contains the actual failure and
`repair_argv` is the single canonical, machine-readable replay action. Its
first element is the original CLI entrypoint, followed by `index build --base`
and the selected base, then each explicitly supplied original `--config`,
`--cwd`, and `--home` configuration-discovery option with its exact original
value; omit options that were not supplied. Executing the argv array without
shell interpretation must select the same configuration and base as the
successful materialization, including values containing spaces. Do not emit a
separate `repair_command` field or another contradictory source of truth;
consumers needing display text may derive a shell-quoted command directly from
`repair_argv`. stdout remains the successful schema output and process exit
remains `0`. Agents can parse and surface the stderr warning without treating
durable knowledge creation as failed. Do not delete or roll back the knowledge
file. An explicit `index build` still exits nonzero when it cannot update the
index. `mem` skill instructions must also require `index build --base
NAME_OR_ALIAS` after an agent creates a managed knowledge entity through direct
file editing instead of the CLI.

External edits, renames, deletions, and Git syncs are not observed
automatically. Their owners must run `index build` when they require a current
index. `index check` remains read-only.

### Read behavior and fallback

Query routing ensures a missing index exists, then loads a valid index and scores
its generated topics and artifact kinds with the existing weights. Index signals
cannot override explicit selection or filesystem ownership. Candidate output
identifies indexed reasons as `index-topic:<value>` and
`index-artifact:<value>` and reports index status.

Context lookup includes the validated two-level hierarchy and index status in
`selected_bases[].index = {status, generated_at, source_fingerprint, metadata,
hierarchy}`, then performs the existing exhaustive managed-root search before
source fallback. It does not treat hierarchy nodes as a search allowlist. The
existing top-level audit-compatible `hierarchy` field remains schema-derived and
unchanged; index hierarchy paths do not enter `lookup_id`. This preserves the
current match set, traversal limits, audit identity, and trace deduplication.

Context lookup remains read-only for knowledge documents and source files. Its
only permitted filesystem mutation is creating a missing derived index at the
selected base's exact configured managed-root index path.

Malformed or unsupported index content is ignored for read acceleration and
reported as `invalid` in structured output. Routing then uses only base name,
aliases, and description; after a base is selected, lookup still searches its
managed files. Explicit `index show` and `check` fail on malformed files;
`index build` repairs a safely located regular file as defined above. All three
fail on unsafe index paths.

Audit operation timings record `build_index` only when a missing index is
generated and `load_index` only when an index read occurs. They do not copy the
index payload into the trace or add index paths to audit hierarchy decisions.

## Implementation

1. Extend [`scripts/load_config.py`](../../../active/mem/scripts/load_config.py)
   to make the existing top-level config `version: 2` authoritative, reject
   retired YAML query-signal fields, derive `index_path`, retain ownership
   globs, and expose raw discovery/loading plus in-memory current-schema
   validation for migration bootstrap.
2. Add `doctor --migrate` dispatch through
   [`scripts/mem.py`](../../../active/mem/scripts/mem.py), including ordered
   merged-file planning, legacy-field removal, deletion of `match` when no
   ownership globs remain, prevalidation, atomic idempotent per-file writes,
   strict final reload, and structured migration results.
3. Add `scripts/routing_signals.py` as the single owner of token normalization,
   generic words, artifact aliases, and existing artifact-query recognition;
   update the router to import rather than duplicate those constants.
4. Add a shared `scripts/base_index.py` module that securely walks all eligible
   paths, derives logical hierarchy and metadata, validates version-1 indexes,
   fingerprints inputs, coordinates processes with bounded-wait directory-fd
   advisory locks, and performs atomic idempotent writes without a traversal
   cap or durable lock file.
5. Add the `index build`, `index show`, and `index check` dispatch and structured
   results through [`scripts/mem.py`](../../../active/mem/scripts/mem.py), with
   focused CLI and index-module tests.
6. Update [`scripts/route.py`](../../../active/mem/scripts/route.py) to lazily
   build missing candidate indexes, consume valid metadata, expose index
   status and indexed reason labels, and preserve routing precedence and
   score thresholds.
7. Update [`scripts/context.py`](../../../active/mem/scripts/context.py) to
   lazily build a selected base's missing index, expose validated index status
   and hierarchy,
   exclude the index file from managed results, preserve exhaustive search and
   source fallback, and emit actual `build_index` and `load_index` audit
   operations.
8. Refactor managed `schema materialize --base` execution from `os.execvp` to a
   supervised subprocess so a successful write can refresh its base index.
   Preserve schema stdout and child failures; on refresh failure emit exactly
   one machine-readable warning on stderr with canonical `repair_argv` carrying
   forward the original `--config`, `--cwd`, and `--home` controls while
   retaining successful exit `0` and the created knowledge.
9. Update `active/mem/SKILL.md`, `README.md`, `CLI.md`, and knowledge-workflow
   documentation. Require an index refresh after direct managed entity
   creation, replace retired version-1 configuration examples, and document
   configuration migration, best-effort refresh warnings, and explicit
   rebuilds for external editors and sync automation.

## Verification

| Required outcome | How to verify |
| --- | --- |
| Existing version-1 configuration can be migrated before strict current-schema loading. | CLI tests start with discovered and explicit legacy configs containing both retired fields, run `doctor --migrate`, assert top-level `version: 2`, dropped field values, preserved ownership globs and supported settings, ordered structured results, and successful strict reload. Regression fixtures whose `match` contains only `topics`, only `artifact_kinds`, or both retired fields assert the entire `match` mapping is absent after migration; fixtures retaining `cwd_globs` or `source_globs` assert `match` and those ownership fields remain. |
| Configuration migration is atomic, idempotent, and fail-safe across merged config files. | Tests cover mixed version-1/version-2 files, unchanged bytes and permissions on rerun, unsupported versions and malformed input with zero writes, full merged prevalidation before writes, atomic-replacement failure after another file succeeds, continued processing, safe rerun, and exit statuses 0, 1, and 2. |
| The existing top-level configuration version is the only schema-version field. | Config tests reject legacy version 1 and retired fields during normal loading, accept current version 2 with ownership globs, report version 2 from single-file and merged output, and assert no `schema_version` or per-base version is introduced. |
| Directory and dotted bases produce the same two-level logical hierarchy for equivalent documents. | Unit tests with paired fixture trees assert canonical hierarchy, counts, topics, artifact kinds, and relative paths. |
| Index builds are deterministic and idempotent. | Build twice, assert byte equality and unchanged `generated_at`; add, rename, and remove a document and assert the expected fingerprint and hierarchy diff. |
| Index scans cover arbitrarily large eligible bases without inheriting lookup limits. | Fixtures exceed the existing managed-search file and directory caps and the path-style inference sample; build/check/lazy-refresh tests assert every eligible document contributes to the fingerprint, counts, metadata, and hierarchy while normal context-search limits remain unchanged. |
| Same-base concurrent index operations are serialized without durable lock artifacts. | Multi-process tests overlap explicit/lazy builds and checks on one root, assert one deterministic complete index and idempotent follow-up results, verify different roots proceed independently, force lock timeout/open failure, and assert no knowledge-base `.lock` file or other second durable artifact exists. |
| Index files cannot escape the managed root or traverse symlinks. | Tests cover symlinked roots, symlink files/directories, symlink index targets, `..` containment, and failed atomic replacement. |
| Explicit and ownership routing still outrank indexed query signals. | Route tests combine conflicting target, cwd, source, topic, artifact, and priority signals. |
| Missing indexes are built automatically when a base is first used. | Route and context tests start without index files, assert only the required candidate bases are initialized, and verify subsequent reads avoid rebuilding. |
| Automatic index-build failure does not block knowledge lookup. | Tests use read-only roots, advisory-lock timeout, or failed atomic replacement and assert `build_failed` plus unchanged routing fallback and managed search results. |
| A valid index exposes hierarchy without changing managed search results. | Context tests compare indexed and unindexed matches and search statistics while asserting only the indexed result adds hierarchy metadata. |
| Missing, malformed, or stale indexes cannot suppress managed knowledge. | Context tests force each condition and assert a selected base still receives the existing exhaustive managed search before source fallback. |
| New managed entities refresh their base index without changing successful creation semantics. | Materialization tests assert successful writes update the index, unchanged paths avoid rewrites, child stdout/stderr and failures are preserved, and refresh failure retains exact successful stdout, exit 0, and the created file while appending one stderr JSON warning with all six required fields. Warning regression tests invoke managed materialization with explicit `--config`, `--cwd`, and `--home`, including option values containing spaces, assert canonical `repair_argv` preserves every supplied option and exact value without a duplicated `repair_command`, and replay the argv to verify it selects the original configuration and base; absent options remain absent. |
| CLI results and exit codes distinguish healthy, stale, repairable, and unsafe states. | CLI tests cover single and `--all` build/show/check results, continued multi-base evaluation, malformed-file repair, and exit statuses 0, 1, and 2. |
| Index content remains metadata-only. | Schema tests reject absolute paths and unexpected fields; fixtures with secrets in body/frontmatter assert those values never appear in the index or audit trace. |
| Existing search and audit contracts remain intact. | Run the full `active/mem/scripts/tests` suite, the skill validator, and `git diff --check`. |

## FAQ

### How do existing `.mem.yaml` files migrate?

Run `mem.py doctor --migrate`, optionally with the existing `--config`, `--cwd`,
or `--home` controls. The command discovers the normal configuration set,
reads legacy files before strict validation, upgrades existing top-level
`version: 1` values to `version: 2`, and drops every base's `match.topics` and
`match.artifact_kinds` values. A `match` mapping containing only those retired
fields is removed entirely; mappings retaining ownership globs are preserved,
as are unrelated supported configuration settings. Files already on version 2
are unchanged, and rerunning after a successful or partially successful
migration is safe. There is no separate `schema_version` field, and migration
does not build indexes.

### What does `--base` select?

`--base` selects one configured memory base by its name or alias. For example,
`--base dendron`, `--base oai`, and `--base claw` each select one base;
`--all` selects every configured base.

### What artifacts are generated, and where?

Each selected base owns exactly one generated index under its managed root:

```text
dendron  ~/dendron/notes/.mem.index.json
oai      ~/code/openai/0/notes/.mem.index.json
claw     ~/code/openclaw/.mem/main/.mem.index.json
```

The index contains generated topics, artifact kinds, the first two logical
hierarchy levels, document counts, a generation timestamp, and a fingerprint
of all eligible indexed document paths. Concurrent work uses an advisory lock
on the existing managed-root directory, so there is no second durable `.lock`
artifact. `show` and `check` create no artifacts.

### Does indexing stop after a large base reaches a scan limit?

No. Index generation and verification enumerate every eligible directory and
Markdown file; they have no file-count or directory-count cap and do not reuse
normal bounded lookup traversal. Existing context-search and path-style
inference limits remain unchanged.

### When is an index first generated?

An index is generated automatically the first time `mem` routes a request to,
considers, or looks up a configured base whose index does not exist. Operators
can also generate it proactively with `mem.py index build --base NAME_OR_ALIAS`
or `mem.py index build --all`.

### When is an index updated?

An index is refreshed automatically after `mem` creates a managed knowledge
entity. Managed schema materialization refreshes its base after success; when
an agent creates a managed entity directly, the `mem` skill instructs it to run
`index build --base NAME_OR_ALIAS` afterward. Body-only edits do not change the
path fingerprint, and an unchanged refresh preserves the existing file and
generation timestamp.

If automatic refresh fails, successful managed knowledge creation still exits
`0` and preserves its original stdout. The CLI appends one parseable
`index_refresh_failed` JSON warning to stderr containing the selected base,
index path, actual error, and canonical `repair_argv` array. That array carries
forward the original `--config`, `--cwd`, and `--home` options when supplied,
so replaying it rebuilds the index using the same configuration and base.
An explicitly requested build can still fail nonzero.

Changes made outside `mem`, including external edits, renames, deletions, and
Git syncs, still require an explicit `index build`. `index check` reports
whether a rebuild is needed but never updates the index.

### How does `mem` know to use an index?

Index discovery is automatic and convention-based. When `mem` loads a base
from `.mem.yaml`, it derives the index path as
`<managed_root>/.mem.index.json`; no additional configuration or flag is
required.

During query routing, `mem` reads a valid index and uses its generated topics
and artifact kinds alongside the base's existing name, aliases, and
description. During context lookup, it exposes the index's hierarchy under
`selected_bases[].index` while retaining the existing full managed-file search.

If the index is missing, `mem` first attempts to build it automatically. If the
build fails or an existing index is invalid, `mem` continues using its
configured base metadata and normal managed search. Existing malformed indexes
are repaired only by an explicit `index build`.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-08-08 16:09: Implemented versioned migration, uncapped secure indexing, automatic routing/materialization integration, and skill documentation; verified 163 automated tests and isolated end-to-end migration/index refresh (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 14:21: Required migration to remove ownership-empty match mappings and made refresh-warning repair argv exactly replay configuration-discovery controls, with explicit regression coverage (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 14:15: Added explicit version-1-to-version-2 doctor migration, uncapped and cross-process-safe index scans, and nonfatal structured refresh warnings preserving successful knowledge creation (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 14:04: Required lazy index creation, automatic refresh after managed entity creation, direct-edit skill guidance, and supervised materialization (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 14:03: Documented automatic convention-based index discovery, routing usage, context exposure, and missing-index fallback (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 14:00: Added an FAQ covering base selection, generated artifact locations, initial generation, and explicit index refresh (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)
- 2026-08-08 13:26: Specified generated base metadata, portable two-level hierarchy indexing, CLI lifecycle, and correctness-preserving lookup fallback (019fa5de-c89c-7402-ad74-2978a02a04ad - 0a20c1f992427346065df01c4a37171f5b636435)

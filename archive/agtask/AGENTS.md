# agtask Project Instructions

## Data Model Documentation

Keep `docs/data_model.md` synchronized whenever the SQLite schema, lifecycle
event model, status semantics, or persistence contract changes.

## Local Integration Skill

Use the project skill at `./.agents/skills/integ` when `$integ` is invoked. It
is a standalone skill that owns its runner, lifecycle assertions, and proof
allocator. From the repository root, run:

```sh
AGTASK_CLI="$PWD/skills/agtask/scripts/agtask" \
  INTEG_PARENT_THREAD_ID=<active-codex-thread-id> \
  ./.agents/skills/integ/scripts/run_integration_tests.sh
```

The skill owns the versioned scenario manifest and executable assertions.
Retain generated proof under the source repository's ignored `.integ/proof/<n>`.

## Local Testing

- NEVER add tests whose only behavior is asserting literal text, headings, or
  phrases in `SKILL.md`. Test executable behavior or structured contracts
  instead.

Use the canonical repository tree directly for routine local testing:

- Skill instructions: `./skills/agtask/SKILL.md`
- CLI and hook entrypoint: `./skills/agtask/scripts/agtask`
- Bundled hook configuration: `./skills/agtask/assets/hooks.json`

Do not run `install-skill`, modify `~/skillz.json`, or invoke `skillz sync`
merely to make current source changes available to local tests. Pass
`AGTASK_CLI="$PWD/skills/agtask/scripts/agtask"` to local integration runs and
reference `./skills/agtask/SKILL.md` by path when its instructions are needed.

Use canonical `skillz` synchronization only when the test explicitly covers
installed Codex skill discovery, the generated `~/.codex/skills/agtask`
runtime mirror, installed hook command paths, or the installer source/runtime
parity contract. Keep those installation checks separate from the routine
source-based feedback loop.

## Major Functionality Changes

When major functionality is added or changed:

- Update only affected scenarios in
  `./.agents/skills/integ/references/scenarios.md` and their bundled assertions.
- Increment affected scenario versions according to the manifest change rules.
  Increment the suite version only when shared setup or proof format changes.
- Run focused automated tests and integration scenarios that are reasonably
  affected by the change. Do not run unrelated scenarios for general
  confidence.
- Run the complete `$integ` suite only when the user explicitly asks for full
  integration tests. When it is run, preserve the numbered
  `.integ/proof/<n>` directory as validation evidence.

- NEVER directly modify `~/.codex/skills`; ALWAYS invoke `$sc` skill when modifying skills to find the real path for skills.

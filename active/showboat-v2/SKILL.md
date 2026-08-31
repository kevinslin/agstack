---
name: showboat-v2
description: Create schema-backed Showboat integration proofs with scenario summaries, raw artifacts, and replayable verification.
dependencies:
  - mem
---

# Showboat V2

## Overview

Use this skill when the user wants an executable Showboat proof that also has a durable, structured proof directory. It is for live integration or behavior proof, not for wrapping an existing unit test run as the whole proof.

Follow `$mem` to ensure the `mem` command is installed on `PATH`, then use `mem schema` to inspect and materialize the directory structure before writing proof content. Prefer the bundled `integ-proof` schema when the user does not name another schema.

Before writing a durable proof directory or any long-lived proof artifact, invoke `$mem` to resolve the intended knowledge base, root, schemas, and file rules. Do this because the memory root may be any configured path, not necessarily a directory named `.mem`. Only write outside `$mem` when the artifact is explicitly temporary, repo-owned source/docs, or the user names a concrete non-memory destination.

## Workflow

1. Resolve the proof target from the user or project convention. For durable proof storage, resolve `$mem` before choosing `<proofs-root>` and record the selected base name, resolved root, and concrete proof path. Do not assume a specific repository, connector, plugin, app, or artifact root.
2. Pick a kebab-case proof slug and one kebab-case slug per scenario.
3. Read the schema before materializing:

```bash
mem schema show integ-proof
```

4. Materialize the root proof file and each scenario file with explicit includes:

```bash
mem schema materialize integ-proof \
  --base <selected-base> \
  --root-relative <proofs-root-relative-path> \
  --var proof=<proof-slug> \
  --var scenario=<scenario-slug> \
  --include <proof-slug>/proof \
  --include <proof-slug>/scenario/<scenario-slug> \
  --skip-existing
```

5. Treat `<proof-root>` as `<proofs-root>/<proof-slug>`, then create the dynamic artifact directories before writing into them:

```bash
mkdir -p <proof-root>/raw <proof-root>/scripts
```

Keep bulky logs, transcripts, screenshots, JSON, and nondeterministic command output in `raw/`; keep proof-local collection or summarization helpers in `scripts/`.
6. Confirm Showboat is available:

```bash
uvx showboat --help
```

7. Initialize the stable Showboat proof summary under `raw/`, usually `raw/showboat-summary.md`:

```bash
uvx showboat init <proof-root>/raw/showboat-summary.md "<Proof Title>"
uvx showboat note <proof-root>/raw/showboat-summary.md "<short context>"
```

8. Run the real live actions needed for the scenario and capture enough raw material to audit the behavior.
9. Add at least one Showboat `exec` command that summarizes or validates the captured raw artifact with deterministic output, so the verified Showboat document is tied to the observed live behavior:

```bash
uvx showboat exec <proof-root>/raw/showboat-summary.md bash "<deterministic summary-or-validation command>"
uvx showboat verify <proof-root>/raw/showboat-summary.md
```

10. Summarize the stable observed result in `scenario/<scenario>.md`.
11. Fill `proof.md` last with the claim, expected behavior, target, status, scenario result table or bullets, relevant scripts, and raw artifact index.

## Scenario Template

Use the materialized schema template for each scenario file. Keep it concise and fill these sections:

```markdown
# Scenario: {title}

## Purpose

{one line}

## Preconditions

## Config

## Action

## Expected

## Observed

## Related

- raw artifacts:

## Notes
```

Omit or mark `Config` as not applicable only when the scenario genuinely has no relevant configuration. Link proof-local summarizers under `Related` or `Notes` when they are relevant.

## Proof Rules

- The proof directory shape comes from `$mem schema`; do not invent a parallel layout when a schema exists.
- The Showboat document proves replayable behavior. Scenario files explain what each scenario means and link to the relevant raw artifacts.
- Raw, nondeterministic output should not be embedded directly in a Showboat command block that must verify later. Store raw output separately and capture a deterministic summary command in Showboat.
- Redact secrets, credentials, account identifiers, and private tokens before writing any artifact.
- Normalize unstable fields such as timestamps, temp paths, generated IDs, durations, random ordering, and stochastic model text.
- Unit tests and static checks can support the proof, but live behavior observation is required for an integration proof.
- If a scenario fails, record the failure honestly in `Observed`, mark the proof status accordingly, and keep the raw artifact that explains the failure.

## Expected Tree

For the default `integ-proof` schema, the finished proof should look like this:

```text
<proof-slug>/
├── proof.md
├── scenario/
│   └── <scenario-slug>.md
├── scripts/
└── raw/
```

Use additional files or nested folders under `raw/` and `scripts/` when the proof needs them.

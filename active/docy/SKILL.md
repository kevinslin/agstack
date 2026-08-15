---
name: docy
description: MANDATORY for every coding-related task, including developer docs. Invoke at session start and load core/main before analysis or edits; never defer until review.
dependencies: []
---

# Docy

## Overview

Keep policy and reference docs small, named, and injectable. For coding-related
tasks, start by loading the baseline rules from `./references/core/`, then return to
this skill only when the task needs additional targeted guidance. Use the bundled
`docy` CLI to print a doc into the active context with `inject` or to install a
durable managed rule block into `AGENTS.md` with `install`.

## Doc Layout

All managed docs live under `./references/` and follow this layout:

```sh
./references/
# language specific
- lang/
# always be injected
- core/
# frameworks/dependencies
- vendor/
# special topics
- ref/
    - commit-messages.md: Repo-aware commit message drafting; inspect local
      history and mirror conventions before writing a subject line
    - developer-docs.md: Developer documentation writing, editing, and review
      guidance, including page patterns and an editorial checklist
    - concise-instructions.md: Terse operator-facing instructions organized
      around inputs, invocation, completion evidence, and recovery
    - spec.md: Architecture and design specification writing, examples, and
      review guidance
    - openclaw-docs.md: OpenClaw-specific page taxonomy, heading, docs-index,
      editing, and verification conventions layered on developer-docs
    - execution-trace.md: How to write runtime-ordered execution trace docs
    - no-back-compat.md: Hard-cut product policy; no backwards compatibility
    - remove-feature.md: Feature removal hygiene; remove stale docs/tests and
      record spec drift in changelog
```

## Loading Rules

For coding-related tasks, use this loading order:

1. At startup, inject every doc under `./references/core/`. Treat these as the
   default rule set, not an optional filter.
2. After the core docs are loaded, add non-core docs selectively based on the task.
3. Inject `./references/lang/<language>.md` only when the task depends on
   language-specific rules or idioms.
4. Inject `./references/vendor/<dependency-or-framework>.md` only when the task
   depends on framework, library, or platform behavior.
5. Inject `./references/ref/<topic>.md` only for focused policies, constraints, or
   one-off topics that should shape the solution. For example, inject
   `./references/ref/remove-feature.md` before removing an existing feature.

## CLI

Run the bundled CLI directly or put `scripts/` on `PATH`.

```bash
docy inject core/main
docy inject ref/commit-messages
docy inject ref/developer-docs
docy inject ref/concise-instructions
docy inject ref/spec
docy inject ref/openclaw-docs
docy inject ref/no-back-compat
docy inject ref/remove-feature
docy inject ref/openclaw-agent-plugins
docy inject ref/execution-trace
docy inject vendor/lerna

docy install core/main
docy install ref/commit-messages
docy install ref/developer-docs
docy install ref/concise-instructions
docy install ref/spec
docy install ref/openclaw-docs
docy install ref/no-back-compat
docy install ref/remove-feature
docy install ref/openclaw-agent-plugins
docy install ref/execution-trace
docy install vendor/lerna
```

Command behavior:

- `inject`: Discover Markdown files under `./references/` and print the selected
  doc to stdout for immediate context injection.
- `install`: Discover the same reference files and add or update the selected
  doc as a managed block in the nearest `AGENTS.md` so the rule remains durable
  for later sessions.

## Available Docs

- `./references/core/main.md`: Core documentation and technical-writing hygiene.
  Always load it to keep adjacent durable docs synchronized and apply universal
  rules for terminology, scope, examples, reviews, and diagrams.
- `./references/vendor/lerna.md`: Modern Lerna operating guidance for agents. Use before changing, validating, or releasing code in a Lerna-managed monorepo.
- `./references/ref/commit-messages.md`: Repo-aware commit message drafting. Use
  before writing a commit message so the subject mirrors recent local history
  instead of forcing one universal style.
- `./references/ref/developer-docs.md`: Developer documentation guidance. Use
  before creating, editing, or reviewing READMEs, quickstarts, guides, API, SDK,
  CLI, testing, troubleshooting, architecture, or internals documentation.
- `./references/ref/concise-instructions.md`: Concise instruction-document
  guidance. Load it after `ref/developer-docs` when writing or compressing an
  operator-facing runbook, setup guide, or command procedure.
- `./references/ref/spec.md`: Design specification guidance. Use before creating,
  editing, or reviewing architecture and design specifications so scope,
  ownership, interfaces, examples, failure paths, and implementation detail stay
  decision-complete without becoming implementation-exhaustive.
- `./references/ref/openclaw-docs.md`: OpenClaw developer documentation overlay.
  Load it after `ref/developer-docs` when creating, editing, or reviewing
  OpenClaw topic pages, guides, references, or troubleshooting documentation.
- `./references/ref/python-preferred-modules.md`: Python dependency preferences. Use before building runtime validation or CLI behavior from scratch in Python projects.
- `./references/ref/typescript-preferred-modules.md`: TypeScript dependency preferences. Use before building runtime validation or CLI behavior from scratch in TypeScript projects.
- `./references/ref/openclaw-agent-plugins.md`: OpenClaw plugin authoring guidance. Use before creating or expanding an OpenClaw plugin so capability ownership, entrypoint shape, SDK imports, and route/setup boundaries stay aligned with the architecture docs.
- `./references/ref/execution-trace.md`: Execution trace writing guidance. Use before documenting initialization, startup, request, job, command, or other runtime flows where ordered control flow matters.
- `./references/ref/no-back-compat.md`: Hard-cut product policy. Use before changing
  codepaths that would otherwise introduce migrations, fallback behavior, adapters,
  or other backwards-compatibility glue.
- `./references/ref/remove-feature.md`: Feature removal hygiene. Use before deleting
  or sunsetting an existing feature so docs, tests, and changelog entries stay
  consistent while historical specs remain unchanged.

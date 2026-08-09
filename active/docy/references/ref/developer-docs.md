# Developer Documentation

Use this reference when creating, editing, or reviewing developer documentation,
including READMEs, overviews, quickstarts, guides, API references, SDK or CLI
references, testing guides, and troubleshooting pages.

## Contents

- [Operating modes](#operating-modes)
- [Workflow](#workflow)
- [Core standard](#core-standard)
- [Writing and editorial rules](#writing-and-editorial-rules)
- [Examples and operational safety](#examples-and-operational-safety)
- [Lifecycle, navigation, and verification](#lifecycle-navigation-and-verification)
- [Page patterns](#page-patterns)
- [Review output](#review-output)
- [Final checklist](#final-checklist)

## Operating modes

Choose the requested mode before working:

- **Create:** Draft a new page from source evidence and the reader's goal.
- **Edit:** Improve an existing page while preserving correct facts, useful
  detail, and the author's intent.
- **Review:** Report accuracy, helpfulness, concision, completeness,
  maintainability, and findability issues before suggesting the smallest
  concrete fix.

Follow an explicit user, repository, or product style guide when it conflicts
with this generic standard. During edits, preserve the author's voice unless the
user asks for a rewrite.

## Workflow

1. Identify the intended reader, desired outcome, page scope, and page type.
2. Establish the source of truth from current code, schemas, generated
   reference, command output, tests, APIs, or product behavior. Do not invent
   missing behavior.
3. Choose the smallest page pattern below that fits the reader's task.
4. Lead with what the reader can accomplish and show one recommended path
   before alternatives.
5. Add realistic examples, expected results, and operational caveats where the
   reader needs them.
6. Verify claims, commands, links, examples, defaults, errors, and paths when
   feasible.
7. Run the final checklist and report any remaining verification gaps.

If a material claim cannot be verified, label it as unverified and name the
missing evidence. Do not make polished prose look authoritative when the
underlying behavior is uncertain.

## Core standard

Write documentation that is:

- **Outcome-led:** Start with the reader's task or decision, not internal
  implementation.
- **Recommended-path first:** Present the safest common path before optional
  variants.
- **Accurate:** Ground behavior in current source evidence.
- **Runnable:** Use realistic, copy-pasteable examples with required setup and
  expected results.
- **Scoped:** Keep guides task-oriented and references exhaustive within their
  stated surface.
- **Operational:** Put permissions, security, limits, side effects, failure
  handling, and production risks next to the affected step.
- **Scannable:** Use concrete headings, short paragraphs, parallel lists, and
  stable links.
- **Connected:** Link canonical concepts, guides, references, testing, and
  troubleshooting instead of duplicating contracts.

## Writing and editorial rules

Apply the core universal technical-writing rules. The rules below specialize
that baseline for developer-facing pages.

- Use present tense, active voice, and concrete nouns.
- Address the reader as "you" for instructions.
- Use sentence case for headings and `Quickstart` as one word when naming that
  page type.
- Prefer action- or surface-specific headings over vague labels such as "How it
  works" or "Important notes."
- Use `must` for requirements, `can` for optional capability, `recommended` for
  the default path, and `avoid` for known footguns.
- Explain why when it changes a decision, prevents a failure, or clarifies a
  nonstandard contract.
- Expand unfamiliar abbreviations at first use.
- Remove generic benefits and hype.
- Use descriptive link text instead of "click here" or "this page."
- Avoid jokes, idioms, and condescension that make instructions less portable.
- Preserve limiting emphasis such as **only**, **must**, and **not** when it
  carries a real constraint.

Open with what the reader can accomplish. Mention implementation first only for
architecture or internals documentation where implementation is the reader's
goal.

Describe capabilities as reader outcomes and keep list items parallel. Show the
preferred path first; put aliases and advanced variants afterward.

Edit in this order:

1. Correct inaccurate or unsafe claims.
2. Add missing requirements, decisions, validation, and failure handling.
3. Remove repetition, generic background, and unrelated detail.
4. Move the first useful action earlier.
5. Replace passive or abstract phrasing with concrete instructions.
6. Tighten headings until the outline reads like a task map.
7. Verify examples, links, defaults, output, and terminology.

## Examples and operational safety

- Keep one conceptual unit per code block and specify the language.
- Mark placeholders clearly, for example `<API_KEY>` or `<PROJECT_ID>`.
- Show complete requests and representative responses when shape matters.
- Show expected output when success is not obvious.
- Use realistic names and safe values; keep examples production-shaped even
  when they use test data.
- Consolidate sequential commands when one block improves copy-paste use, but
  split unrelated formats such as shell and JSON into separate blocks.
- Use the same scenario across language variants so examples remain comparable.
- Keep comments sparse and decision-useful.
- Never expose real credentials or sensitive values.
- Separate test, sandbox, and production behavior.

Do not sacrifice necessary precision for brevity. Cover authentication,
authorization, secret handling, billing, money movement, permissions,
destructive actions, webhooks, retries, duplicate events, ordering, idempotency,
concurrency, limits, timeouts, versioning, migrations, privacy, retention,
compliance, and recovery wherever mistakes are expensive.

For configuration examples, show the minimum realistic configuration for the
task and explain defaults or precedence that affect behavior. Link to the
canonical schema instead of copying an exhaustive generated schema into a guide.

## Lifecycle, navigation, and verification

- Draft docs before or alongside implementation when they can expose unclear
  product, API, CLI, or configuration design.
- Update current docs in the same change as the behavior they describe. Update,
  remove, redirect, or clearly mark stale current guidance.
- Do not update historical specs when implementation invariants change. A spec
  is historical after its implementation ships or a newer spec or decision
  supersedes it. Preserve the old spec and document the new invariant in its
  current owning reference, flow, decision, or changelog.
- Keep docs near the code, configuration, command, protocol, or product surface
  they describe when the repository layout permits it.
- Preserve older-version guidance only when readers still need it; otherwise
  document the current supported behavior.
- Involve reviewers who own the documented behavior and the failure modes users
  will encounter.
- Do not use FAQs as a dumping ground. Promote recurring material into task,
  concept, troubleshooting, or reference pages.
- Use goal-oriented titles and stable headings that match likely searches and
  remain addressable from issues, support replies, and other docs.
- Add required metadata or frontmatter, link from likely entry points, and state
  the scope when a page is intentionally partial.
- Order tutorials and examples from prerequisites to advanced tasks. Order
  reference material alphabetically or topically when that improves lookup.
- Keep tables compact. Use subsections, accordions, or lists when cells require
  multi-line explanations.
- Write accessible instructions that do not rely on color, screenshots, or
  visual position as the only source of meaning.
- Run available docs builds, formatters, indexes, link checkers, and generated
  reference checks. Execute documented commands and examples when feasible.
- Verify screenshots, labels, output, configuration, flags, defaults, errors,
  and paths against current behavior. State what was not verified and why.

## Page patterns

Choose one primary page type. Split mixed pages when readers must sift through
concepts, tasks, exhaustive reference, and troubleshooting to find the main
path.

### Overview

Use an overview to explain a product surface and route readers. Include what it
enables, who it is for, scope and ownership boundaries, primary paths, and links
to task and reference pages. Keep procedures and exhaustive field lists in
linked pages.

### README

Use a README as the front door to a project or package:

1. One-sentence outcome or value proposition.
2. One short mechanism or scope sentence when needed.
3. Recommended installation or setup.
4. Smallest useful example.
5. Main capabilities as outcome-led bullets.
6. Links to deeper guides, reference, contributing, and support.

### Quickstart

Use a quickstart to get a new reader to first success:

1. Outcome and requirements.
2. Installation or enablement.
3. Minimum required configuration.
4. One end-to-end example.
5. Expected success output.
6. The next production or reference page.

Exclude optional variants unless readers must choose one to succeed.

### Guide

Use a guide for one complete workflow. State the outcome, list testable
requirements, add decision points only when readers must choose, then provide
verb-led steps with commands, expected output, and checks. Include the smallest
reliable end-to-end test, production-readiness details, workflow-specific
troubleshooting, and related references. Keep warnings beside the affected step.

### API reference

For each endpoint, method, object, event, or operation, include:

1. Purpose, authentication, and permissions.
2. Request shape, including method, path, query, headers, and body. Document
   parameter types, requiredness, nullability, defaults, constraints, enum
   values, and side effects.
3. Return shape and lifecycle states.
4. Error codes, causes, and recovery.
5. A runnable request and representative response.
6. Version, compatibility, and limit rules.
7. Related guides and adjacent reference.

Prefer generated reference for machine-owned schemas. Link to it rather than
copying it by hand. Keep nested child fields near their parent so readers can
understand one request shape without jumping across pages.

### SDK or CLI reference

Document installation and version requirements, authentication or
configuration, purpose, arguments and options, defaults and precedence, output
or side effects, errors and recovery, and examples ordered from common to
advanced. Use this shape for commands:

````markdown
### `command-name`

[One-sentence purpose.]

Options:

- `--flag`: [Behavior, default, and important side effect.]

Examples:

```bash
command-name
command-name --flag
```
````

Show the preferred spelling in examples. Document aliases in the option list
instead of repeating equivalent commands.

### Testing guide

Include test or sandbox setup, fixtures and permissions, a happy-path test, the
expected observable result, failure simulation, cleanup or reset, and
differences from production.

### Troubleshooting guide

Organize by observable symptom. For each symptom, give the exact message or
behavior, fastest discriminating check, likely causes ordered by probability or
impact, concrete fix, proof that the fix worked, and evidence to collect before
escalation. Keep each troubleshooting row focused on one symptom. Use cautious
language when several causes produce the same symptom. During a slimming pass,
preserve evidence-backed or common failure cases without inventing unrelated
ones.

### Architecture and internals

Explain mechanisms, boundaries, invariants, and tradeoffs. Outcome-led openings
remain useful, but implementation depth is the point of the page.

## Review output

When reviewing rather than rewriting:

1. Lead with findings ordered by user impact.
2. Apply the core self-contained finding format.
3. State what evidence was checked and what remains unverified.
4. Say clearly when no issues were found.

Prioritize inaccurate, unsafe, or unusable instructions over local copy edits.

## Final checklist

- The first screen states what the reader can accomplish.
- The intended reader, page type, and scope are clear.
- The recommended path is obvious.
- Requirements and assumptions are testable.
- Commands and examples match current behavior and show expected results.
- Test, sandbox, and production behavior are separated.
- Security-sensitive values are placeholders.
- Warnings appear beside the affected step.
- Reference fields, flags, defaults, constraints, and errors are complete.
- Troubleshooting starts from observable symptoms.
- Headings and link text are specific and searchable.
- Canonical contracts are linked rather than duplicated.
- The page links to support, issue, or contribution paths when relevant.
- Unverified claims and verification gaps are explicit.

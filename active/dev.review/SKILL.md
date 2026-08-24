---
name: dev.review
description: Review code, docs, specs, architecture, UX, or design docs.
dependencies:
- dev.shortcuts
- sc
- specy
---

# dev.review

## Workflow

1. Identify the review type from the user's request and artifact.
   - Examples: code, docs, design-doc, spec, simplify-spec, architecture, ux, skills, integrator, deslop, dead-code.
   - Use `simplify-spec` when the user asks to radically simplify a spec or its proposed implementation, narrow the solution, or find an 80/20 approach.
   - Use `spec` for correctness, approved-scope completeness, ownership, safety, and implementation readiness; leave design minimization to `simplify-spec`.
   - If ambiguous, ask one clarifying question before reviewing.
2. Load the matching workflow from `./references/workflow-[review-type].md`.
   - If the workflow file does not exist, ask the user for the prompt to add and pause the review.
   - For skills reviews, use `$sc` for the local skill-authoring contract.
   - For docs reviews, use `./references/workflow-docs.md`; when reviewing OpenClaw docs and `$openclaw-docs` is available, apply its guidance as domain-specific context.
   - For `integrator`, default input artifacts are outputs from `ag-learn` and adjacent retrospectives.
   - For code reviews that require flow docs, use `$specy`.
3. Route every top-level review request through the `trigger:loop` shortcut from `dev.shortcuts`.
   - If the user request already contains `trigger:...`, resolve it through `dev.shortcuts`.
   - If no shortcut trigger is present, invoke `trigger:loop` with the resolved review instruction, for example `trigger:loop review the current diff with $dev.review`.
   - Give the loop reviewer the review type, workflow file, artifact paths, current diff, and review scope.
   - Routing a plain review request through `trigger:loop` does not grant edit
     authorization. In that case, require the reviewer pass and parent
     classification, but stop after reporting any blocker or major findings;
     do not start a fixer pass without user authorization.
   - An explicit `trigger:loop` invocation, explicit review-and-fix request, or
     edit task authorizes the shortcut's scoped fixer passes. Follow the full
     reviewer/classifier/fixer loop for those requests.
   - When this skill is already running inside a `trigger:loop` reviewer pass, apply the workflow directly to the material and produce the review instead of nesting another loop.
   - When this skill is already running as a read-only reviewer subagent for `trigger:spec`, apply the selected workflow directly; do not redispatch the parent shortcut or start a nested review/fixer loop.
4. For PR or CI-backed review loops, keep going until the remote exit condition is met.
   - Completion is remote-state based, not patch based: current head SHA is known, relevant CI is green, unresolved non-outdated review threads are zero, and actionable comments are addressed or explicitly routed to the user.
   - Before saying the loop is finished, run a final PR gate query and report head SHA, failing/pending check count, unresolved thread count, and actionable comment count.
   - If any required check is failed/pending or any actionable review item remains, the loop is not finished; continue fixing or report the exact blocker.

## Output

- Lead with findings ordered by severity (blocker/major/minor) or by impact if severity is unclear.
- Prefer concrete, actionable feedback over generic commentary.
- Call out assumptions, risks, and unclear ownership/abstractions.
- Propose simplifications when the selected workflow owns simplification.
- Keep the review concise; avoid restating large sections of the input.
- For code reviews, include both the `Simplicity Audit` and `Test Audit`
  checklists required by `./references/workflow-code.md`; never check an item
  without inspected evidence or report a clean review with either audit
  incomplete.
- Treat materially avoidable duplicate ownership, parallel implementations,
  and implementation-coupled test machinery as major when a concrete smaller
  design preserves approved capabilities, security, and supported compatibility.
- If blocker or major findings remain in a review-only request, report them as
  unresolved and state that no fixer pass ran because edits were not authorized.

## Workflows

- `./references/workflow-code.md` for code review.
- `./references/workflow-docs.md` for developer documentation, user guides, API references, CLI references, quickstarts, READMEs, and troubleshooting docs.
- `./references/workflow-design-doc.md` for design doc review.
- `./references/workflow-spec.md` for product, implementation, or test spec review.
- `./references/workflow-simplify-spec.md` for reducing a spec to the smallest complete implementation that satisfies its current goal.
- `./references/workflow-architecture.md` for architecture and system-boundary review.
- `./references/workflow-ux.md` for UX review.
- `./references/workflow-skills.md` for reviewing `SKILL.md` files and bundled skill resources.
- `./references/workflow-integrator.md` for integrating learnings into skill/code/project changes.
- `./references/workflow-deslop.md` for anti-slop code review focused on excess complexity, patch size, and unnecessary helper extraction.
- `./references/workflow-dead-code.md` for dead-code review that accounts for every new class, function, method, variable, constant, option, config field, and other named artifact introduced by a PR.

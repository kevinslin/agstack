---
name: sw-loop
description: Run explicitly requested swarm workflows for feature delivery.
dependencies:
- babysit-pr
- dev.loop
- dev.review
- dev.shortcuts
- mem
- slack-notify
- specy
- sw-ctrl
---

# Sw Loop

## Overview

Use this skill to run multi-agent feature work as a controlled swarm. Keep orchestration
disciplined: define the critical path, delegate bounded sidecars, integrate results
centrally, and do not let review or verification turn into unowned follow-up.

Treat the active milestone stack as sticky session context. Once a thread has an approved
bundle, keep that bundle in the thread state and only restate it when the stack or phase
changes.

## Entry Gate

1. Restate the goal, required deliverable, and completion condition.
2. Confirm whether the user wants full execution or only planning/review.
3. Treat explicit decisions in the current task, parent handoff, or approved spec
   as settled. If older architecture disagrees, record the narrow approved delta
   and update only authorized repository-owned material; do not reopen the
   decision or change unrelated canonical sources.
4. Stop after the spec-and-review phase when either of these is true:
   - ambiguity remains that affects implementation shape
   - the user asked to review the plan before coding
5. Prefer `$dev.loop` alone for simple single-threaded work. Use this skill only
   when multiple agents materially help.

## Checklist Gate

- Create a swarm checklist before starting the loop.
- Before writing any durable spec, checklist, flow doc, proof, review artifact, runbook, or long-lived project note, invoke `$mem` to resolve the intended base, root, schemas, and file rules. Do this by artifact intent, not by path shape: `$mem` roots may be anywhere and may not contain `.mem`.
- Store the checklist in the active spec folder when using `$mem schema` `specs`.
- Store the checklist in a temporary folder for all other workflows.
- Include every required gate: spec, one-pass spec review, implementation,
  test-quality cleanup, review swarm, review fixes, final evidence-backed
  simplification audit, verification,
  implementation flow doc, PR push, and any
  user-requested stopping condition.
- Translate explicit user completion requirements into checklist rows before starting.
  If the user names a live proof suite, negative cases, inline screenshots, CI green,
  a PR push, or a "do not stop until" condition, those are required rows, not optional
  follow-up notes.
- Check off items one by one as each gate is actually complete. Do not bulk-check
  items at the end.
- Do not consider the loop done until every checklist item is checked off.

## Swarm Layout

- Manager track: use `$sw-ctrl spec` to own intake, decomposition, delegation, monitoring,
  and integration.
- Spec track: use `$specy` to create a feature spec with milestones, risks, and
  explicit verification targets.
- Pre-implementation review: run one `$dev.review` pass against the spec and
  apply straightforward improvements before coding. Do not loop on the spec.
- Implementation track: use an available coding subagent when bounded delegation is
  justified; otherwise implement locally. Keep `$dev.loop` responsible for the
  approved plan, phase gates, and integration.
- Test-quality cleanup: after implementation, remove low-value branch tests or
  replace them with higher-level outcome-focused coverage before review.
- Post-implementation review swarm in parallel: trigger:loop `$dev.review`
  passes for code, explicit simplification/deslop, documentation, and dead code.
- Final simplification gate: after review fixes, audit the current diff for one
  canonical owner, unnecessary mechanisms, duplicate tests, and avoidable churn.
- Verification track: run only the local Verify phase of `$dev.loop` in a separate
  subagent after review fixes land. Do not push or create a PR during this phase.
- PR push track: after verification succeeds and the implementation flow doc is
  written and validated, run the separate `$dev.loop` Push phase, including
  `trigger:push-pr`, unless the user explicitly said not to push.

## Workflow

### 1. Orchestrate

- Adopt the `$sw-ctrl` manager role immediately.
- Identify the critical path and keep the immediate blocker local.
- Delegate only sidecar work that is concrete, bounded, and non-overlapping.
- Keep a short session header for the current milestone: goal, active skill bundle,
  current phase, and unresolved blockers. Reuse it across turns instead of re-announcing
  the full bundle each time.

### 2. Plan and Gate

- Use `$specy` to create a feature spec first unless one already exists. If the spec is durable project memory, route the artifact root through `$mem` before creating or updating the spec folder.
- Preserve every approved outcome while choosing the smallest end-to-end design:
  one source of truth, actual lifecycle ownership, existing contracts and SDK
  types, and distinct discriminators for distinct concepts. Defer speculative
  resources, drivers, compatibility paths, and coordination mechanisms.
- Keep source-backed security, isolation, authorization, and immutable-state
  invariants intact. Simplification removes unnecessary mechanisms, not approved
  capabilities or required protections.
- Run one `$dev.review` pass against the spec and incorporate actionable
  recommendations. Do not loop on the spec.
- Stop and return the spec to the user when ambiguity remains or the user asked
  to review the plan before implementation.

### 3. Implement

- Use an appropriate available coding subagent when code-writing work can be
  delegated with bounded, non-overlapping ownership; otherwise implement locally.
  Give each delegated agent the approved plan, explicit file/module ownership,
  expected tests, and the relevant `$dev.loop` phase context.
- Keep `$dev.loop` as the implementation workflow owner for plan execution,
  integration, verification planning, cleanup, and delivery gates.
- Keep ownership clear when delegating code changes. Assign files or modules and
  remind subagents they are not alone in the codebase.
- Integrate changes centrally instead of letting multiple agents edit the same surface
  opportunistically.
- If the approved bundle has not changed, continue from the existing session context
  rather than re-describing the same orchestration stack.

### 4. Clean Up Low-Value Tests

- Remove low-value tests added on the branch, especially tests that verify
  their own monkeypatched behavior. When possible, elevate them to higher-level
  tests that verify outcomes and are not coupled to implementation.
- Complete this cleanup after implementation and before starting review.

### 5. Review Swarm

trigger:loop `$dev.review` subagents with disjoint scopes:

1. Regular code review: find correctness issues, regressions, missing tests, and risky abstractions.
2. Simplification/deslop review: identify duplicate ownership, competing
   sources of truth, parallel implementations, unnecessary adapters, low-value
   tests, and avoidable generated-artifact or lockfile churn; describe the
   smaller safe design with concrete files and deletion candidates.
3. Documentation review: find README, flow docs, design docs, specs, or other docs that should change because of the implementation.
4. Dead code review: find obsolete code paths, compatibility shims, stale state, unused functions, or docs that can now be deleted.

Require each reviewer to return concrete findings with file references and
proposed actions. Require the code reviewer to complete the evidence-backed
Simplicity Audit and Test Audit; a bare `CLEAN` does not satisfy either gate.

If a proposed fix is straightforward and does not require user input, apply it in
the subagent or integrate it locally. If the fix changes product direction, policy,
or unclear ownership, bubble it up for human review instead of guessing.

After review fixes land, rerun the simplification review against the final
current-head diff. Do not mark the simplification checklist row complete or
start verification while a material avoidable complexity finding remains.

### 6. Verify

- After review fixes land, spawn a separate subagent to run only the local Verify
  phase of `$dev.loop`. Do not push, create a PR, or invoke the Push phase here.
- Require that verification covers the plan tests plus any checks added because of
  review findings.
- For live approval/channel suites, require the verifier to report each requested
  scenario row separately as passed, blocked, or not run, with the artifact or
  screenshot path for that row when visual proof was requested.
- Do not summarize a multi-row suite as complete from one positive scenario, unit
  tests, or synthetic debug helpers when the user requested live end-to-end proof.
- Do not treat verification as implicit. It is a dedicated track with its own owner.

### 7. Document Implementation Flow

- Before the `$dev.loop` Push phase or `trigger:push-pr`, create or update a
  `$specy` `flow-doc` for the primary logic path exercised by the implementation.
- Resolve the durable flow-doc target through `$mem` before writing. Store it in
  the `$mem`-resolved active spec folder when using `$mem schema` `specs`, otherwise
  use the resolved base and flow-doc route.
- The flow doc must describe the changed request path, entry points, key
  state/config transitions, exit behavior, and validation/proof hooks.
- Run the `$specy` flow-doc validator and fix failures before continuing.
- Check off the implementation-flow-doc checklist row before PR push. Do not
  push until this gate is complete.

### 8. Push PR

- After verification succeeds, review fixes are committed, and the implementation
  flow doc is validated, run the `$dev.loop` Push phase, including `trigger:push-pr`.
- Treat PR push as required for full execution unless the user explicitly requested
  planning/review only or explicitly said not to push.
- Include the PR URL in the final handoff. If push or PR creation fails, report
  the exact failure and treat the swarm run as incomplete.
- Kick of $babysit-pr after the PR is pushed
- $slack-notify me with alert once pr is green

## Manager Rules

- Do not send multiple agents after the same unresolved question.
- Do not wait idly when a sidecar can run in parallel with local work.
- Do not trust raw review output without integration and judgment.
- Close stale agents after their results are integrated or discarded.
- Keep user updates focused on what is local, what is delegated, and what is blocking.

## Completion

Only finish when the spec, implementation, review follow-up, verify track, and
PR push are all resolved, or when the ambiguity/plan-review gate explicitly
requires stopping for user input.

# Spec Review Workflow

Use this workflow to review a product, implementation, or test spec for
implementation readiness. The review should prove whether another agent can
execute the spec without rediscovering major contracts or making unsafe
assumptions. Focus on correctness, approved scope, ownership, existing
invariants, execution, and proof. Dedicated design simplification belongs to
the separate `simplify-spec` workflow.

## Core Rubric

Review against these criteria:

- Correct: grounded in the current codebase, docs, runtime behavior, upstream
  contracts, or the user's stated goal.
- Complete within scope: covers the happy path, important variants, failure
  modes, ownership, rollout, and validation implied by the goal.
- Executable: names concrete files, APIs, commands, artifacts, state changes,
  and acceptance checks.
- Verifiable: includes focused automated checks and, when needed, live or
  integration proof that exercises the real behavior.

Correctness is a hard gate. A spec that is detailed but based on stale source,
wrong contracts, or invented behavior is not ready.

Evaluate completeness only within the approved scope. Do not introduce new
product requirements, exhaustive edge-case coverage, compatibility paths, or
operational machinery unless a stated requirement or existing invariant needs
them.

## Steps

1. Establish evidence and scope.
   - State the retained capabilities, acceptance outcomes, non-goals, target
     users/operators, and affected surfaces before proposing changes.
   - Distinguish the latest accepted requirements and decisions from verified
     current behavior, required implementation work, approved dependency or
     upstream assumptions, and deferred scope. Existing schemas and older
     proposals are evidence, not additional target requirements.
   - Apply settled decisions consistently; record conflicts with older
     architecture as narrow documentation deltas, not reasons to reopen the
     direction or edit unrelated canonical sources. Preserve selective
     apply/keep/defer decisions; exploratory questions are neither edit
     authorization nor new requirements.
   - Verify source-backed claims against the current implementation, docs,
     schemas, generated types, command output, tests, or upstream contracts when
     available.
   - Flag hidden scope, vague outcomes, missing success criteria, and unverified
     claims presented as facts.
   - Record approved upstream work as an unverified dependency and required
     implementation work, not current support. Flag unsupported assumptions
     that would change approved behavior or ownership.
2. Check target behavior.
   - Require clear before/after behavior, state transitions, permissions,
     prompts, error handling, edge cases, and user-visible output.
   - For migrations or repair flows, require source state, target state,
     idempotency, skipped/ineligible cases, and fail-closed behavior.
   - Require variants and edge cases only when they affect the approved goal or
     protect an existing correctness, security, or ownership invariant.
3. Check data, API, and ownership contracts.
   - Review request/response shapes, persisted data, config, schemas, enums,
     reason codes, compatibility, observability, and ownership boundaries.
   - Identify the actual owner of each decision, lifecycle action, and
     enforcement responsibility. Distinguish orchestration from delegated
     execution; one component need not create, configure, deploy, and destroy
     every resource. Keep consumer identity, implementation selection, and
     authorization semantics independent.
   - Flag conflicting sources of truth, parallel representations, duplicate
     verification, or unclear ownership only for concrete correctness or
     ownership risks. Preserve independent checks at actual trust boundaries;
     trusting a delegate does not remove authorization, admission, or routing
     responsibilities.
   - If the spec changes data/API/CLI/config/migration output, require an
     existing-contract snapshot or equivalent source-backed explanation before
     approving new output fields or types.
   - For dependency-backed behavior, require the spec to name the dependency
     contract being relied on instead of guessing defaults, errors, or types
     already exported by the dependency.
4. Check execution plan.
   - Confirm the implementation touchpoints are concrete and ordered.
   - For every new command, script, trigger, cache, background job, or generated
     artifact, require who invokes it, when, from what working directory or
     runtime, what it reads/writes, and how failure is surfaced.
   - Call out plans that require broad rewrites, unrelated refactors, or
     ownership changes not justified by the goal.
5. Check validation and rollout.
   - Require focused unit/integration tests at the behavior boundary, plus
     broader changed-surface checks when shared contracts change.
   - Verify the acceptance criteria are observable and map to the target
     behavior, not only internal helper shapes.
   - Review feature flags, backfills, monitoring, rollback, data repair,
     migration safety, and proof artifacts when relevant.
   - Require additional validation, rollout, or compatibility mechanisms only
     when the approved scope, actual blast radius, or an existing invariant
     makes them necessary.

## Contract and Ownership Gate

Apply this gate when the spec proposes new data shape, API output, CLI output,
config, migration output, persistence, enums, statuses, reasons, or state
machines.

- Existing contract: does the spec name the current owner/source of truth,
  shape, and consumers before proposing changes?
- Decision table: if multiple facts drive behavior, does the spec map input
  facts to the specified target outputs?
- Canonical ownership: does every changed contract have an identified owner and
  consistent source of truth?
- Investigation handoff: if the spec came from an investigation, did it translate
  evidence into an implementation contract instead of copying diagnostic
  vocabulary into the design?

Do not demand these sections for small specs that do not change contracts. For
small changes, a sentence that names the reused contract is enough.

## Severity Guidance

Classify each substantive finding before assigning severity:

- **Explicit requirement breach:** contradicts a user-approved capability,
  stated non-goal, or acceptance criterion.
- **Existing security or ownership invariant:** weakens a verified current
  authorization, isolation, credential, resource-ownership, or integrity rule.
- **Scope-expanding product decision:** introduces a new persistence model,
  migration, lifecycle, operating responsibility, or resource contract that
  requires product-owner approval.
- **Deferred improvement:** strengthens behavior beyond the approved goal or
  addresses a plausible future requirement without a demonstrated present
  breach.

Ground the first two categories in the actual requirement or source-backed
invariant. Present scope expansion as a decision for the user, and distinguish
optional improvements from required fixes. Likewise, present recommendations
that drop retained capabilities separately as approval-required scope changes,
not required fixes. Do not turn the strongest imagined enforcement mechanism
into a blocker when the existing invariant and approved scope do not require it.

- `blocker`: the spec cannot be implemented safely because core behavior,
  source truth, ownership, or execution contracts violate an explicit
  requirement or existing security/ownership invariant.
- `major`: edge cases, failure handling, validation, rollout, compatibility,
  or data/API contracts required by the approved scope or an existing invariant
  are incomplete.
- `minor`: the spec is implementable but includes avoidable ambiguity,
  weak proof mapping, or maintainability risk.
- `nit`: local wording or structure issues with no meaningful execution risk.

Treat missing execution contracts, validation plans, rollback paths, or
source-backed evidence as major findings when the approved scope, real blast
radius, or an existing invariant requires them.

## Output

- Begin with a short "Scope and Contracts Reviewed" note naming retained
  capabilities, acceptance outcomes, ownership boundaries, and existing
  invariants; then present findings ordered by severity.
- For each finding, cite the exact section or line when possible, name the
  finding category and failed rubric criterion, and explain what the
  recommendation changes, its consequence or risk, relevant tradeoff, and the
  smallest concrete fix or decision needed.
- Include a short "Ready State" verdict after findings: ready, ready after
  minor edits, or not ready.
- Include a short "Verification Reviewed" note naming the code, docs, commands,
  tests, or runtime evidence checked and what remains unverified.
- If there are no findings, say so clearly and still name any residual proof
  gaps.

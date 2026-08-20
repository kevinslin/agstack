# Spec Review Workflow

Use this workflow to review a product, implementation, or test spec for
implementation readiness. The review should prove whether another agent can
execute the spec without rediscovering major contracts or making unsafe
assumptions. Treat simplification as a primary review outcome: a correct spec is
still not ready when it preserves removable assumptions, checks, states, or
abstractions that materially enlarge the implementation.

## Core Rubric

Review against these criteria:

- Correct: grounded in the current codebase, docs, runtime behavior, upstream
  contracts, or the user's stated goal.
- Complete within scope: covers the happy path, important variants, failure
  modes, ownership, rollout, and validation implied by the goal.
- Executable: names concrete files, APIs, commands, artifacts, state changes,
  and acceptance checks.
- Simple: removes assumptions before designing around them, reuses existing
  seams, and includes only checks, states, abstractions, and rollout machinery
  required by a concrete risk or consumer.
- Verifiable: includes focused automated checks and, when needed, live or
  integration proof that exercises the real behavior.

Correctness is a hard gate. A spec that is detailed but based on stale source,
wrong contracts, or invented behavior is not ready.

Simplicity is also a readiness gate. Do not reward detail by default. Extra
validation, indirection, compatibility layers, flags, phases, or observability
are liabilities unless the spec names the real failure, boundary, or consumer
that requires them.

## Steps

1. Establish evidence and scope.
   - Identify the stated goal, non-goals, target users/operators, and affected
     surfaces.
   - Verify source-backed claims against the current implementation, docs,
     schemas, generated types, command output, tests, or upstream contracts when
     available.
   - Flag hidden scope, vague outcomes, missing success criteria, and unverified
     claims presented as facts.
   - List the assumptions that make the proposed design necessary. For each,
     ask whether it is a verified constraint, a temporary choice, or removable.
     Identify any assumption whose removal collapses multiple components or
     phases.
2. Check target behavior.
   - Require clear before/after behavior, state transitions, permissions,
     prompts, error handling, edge cases, and user-visible output.
   - For migrations or repair flows, require source state, target state,
     idempotency, skipped/ineligible cases, and fail-closed behavior.
   - Before adding behavior for every variant, ask whether the goal can exclude,
     normalize, or delegate a variant and thereby eliminate the branch.
3. Check data, API, and ownership contracts.
   - Review request/response shapes, persisted data, config, schemas, enums,
     reason codes, compatibility, observability, and ownership boundaries.
   - Identify duplicated facts, parallel status fields, semantic sentinels, and
     new abstractions that do not have a single canonical owner.
   - If the spec changes data/API/CLI/config/migration output, require an
     existing-contract snapshot or equivalent source-backed explanation before
     approving new output fields or types.
   - For dependency-backed behavior, require the spec to name the dependency
     contract being relied on instead of guessing defaults or errors.
4. Check execution plan.
   - Confirm the implementation touchpoints are concrete and ordered.
   - For every new command, script, trigger, cache, background job, or generated
     artifact, require who invokes it, when, from what working directory or
     runtime, what it reads/writes, and how failure is surfaced.
   - Call out plans that require broad rewrites, unrelated refactors, or
     ownership changes not justified by the goal.
   - Challenge every new helper, service, adapter, registry, state machine,
     cache, queue, and framework layer. Require a named source of variation,
     repeated behavior, or ownership boundary that cannot be handled directly
     by an existing seam.
5. Check validation and rollout.
   - Require focused unit/integration tests at the behavior boundary, plus
     broader changed-surface checks when shared contracts change.
   - Verify the acceptance criteria are observable and map to the target
     behavior, not only internal helper shapes.
   - Review feature flags, backfills, monitoring, rollback, data repair,
     migration safety, and proof artifacts when relevant.
   - Require each proposed validation or runtime check to name the invalid state,
     trust boundary, or observed failure it protects against. Remove checks that
     duplicate type/schema guarantees, repeat an upstream invariant, defend an
     impossible state, or only test implementation plumbing.
   - Scale rollout machinery to blast radius and reversibility. Do not require a
     flag, backfill, compatibility path, dashboard, or rollback system for a
     local and safely reversible change without a concrete reason.
6. Look for simplification.
   - First try deleting a requirement, assumption, variant, state, validation,
     or component. Then try reuse or direct control flow. Add a new abstraction
     only after those options fail.
   - Ask the radical-simplification question explicitly: "Which assumption, if
     removed or narrowed, would eliminate the most design?" Verify whether the
     product goal actually requires that assumption.
   - Propose narrower milestones, smaller contracts, deletion of unnecessary
     concepts, and use of existing seams before adding framework code.
   - Prefer one canonical machine-readable field for a fact; derive display,
     reports, and warnings at the boundary that emits them.
   - For specs that add fields, types, statuses, reasons, or config, require a
     consumer for each new durable concept. Treat a new model with no named
     consumer, or a model that stores derived status already available from raw
     facts, as a major finding unless the spec explains why it is needed.

## Simplification and Contract Gate

Apply this gate when the spec proposes new data shape, API output, CLI output,
config, migration output, persistence, enums, statuses, reasons, or state
machines.

- Assumption removal: which design-driving assumptions are verified, and which
  can be removed, narrowed, or deferred?
- Validation budget: does every new check protect a reachable bad state or trust
  boundary not already enforced elsewhere?
- Abstraction budget: does every new abstraction have multiple real consumers,
  meaningful variation, or a necessary ownership boundary? If not, inline or
  reuse an existing seam.
- Operational surface: can flags, jobs, caches, migrations, dashboards,
  compatibility paths, or rollout phases be deleted without weakening the
  stated acceptance criteria?
- Existing contract: does the spec name the current owner/source of truth,
  shape, and consumers before proposing changes?
- Decision table: if multiple facts drive behavior, does the spec map input
  facts to target outputs without inventing intermediate states?
- Canonical field: is the machine-readable outcome represented in one place?
- Raw facts vs derived values: does the spec avoid storing derived status unless
  a named consumer needs it?
- Success state: is success represented once, rather than as both a boolean and
  a separate status?
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
optional improvements from required fixes. Do not turn the strongest imagined
enforcement mechanism into a blocker when the existing invariant and approved
scope do not require it.

- `blocker`: the spec cannot be implemented safely because core behavior,
  source truth, ownership, or execution contracts violate an explicit
  requirement or existing security/ownership invariant.
- `major`: important edge cases, failure handling, validation, rollout,
  compatibility, or data/API contracts are incomplete.
- `minor`: the spec is implementable but includes avoidable ambiguity,
  unnecessary complexity, weak proof mapping, or maintainability risk.
- `nit`: local wording or structure issues with no meaningful execution risk.

Treat missing execution contracts, validation plans, rollback paths, or
source-backed evidence as major findings when the approved scope, real blast
radius, or an existing invariant requires them.

Treat an unnecessary abstraction, validation layer, compatibility path, or
operational component as `major` when it creates a durable contract, new owner,
runtime failure mode, migration burden, or significant implementation work.
Otherwise report it as `minor`; do not demote needless complexity to a nit.

## Output

- Lead with findings ordered by severity.
- For each finding, cite the exact section or line when possible, name the
  finding category and failed rubric criterion, explain the implementation
  risk, and give the smallest concrete fix or decision needed.
- Include a short "Ready State" verdict after findings: ready, ready after
  minor edits, or not ready.
- Include a short "Simplification Reviewed" note naming what can be deleted,
  combined, narrowed, or reused, plus the assumption with the highest
  simplification leverage. If nothing can be simplified, say which alternatives
  were tested and why the remaining complexity is necessary.
- Include a short "Verification Reviewed" note naming the code, docs, commands,
  tests, or runtime evidence checked and what remains unverified.
- If there are no findings, say so clearly and still name any residual proof
  gaps.

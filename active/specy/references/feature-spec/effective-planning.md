# Feature-spec execution planning

Load `$docy` `ref/spec` through Specy's specification-style rule before using
this reference. Docy owns specification writing and design completeness. This
reference adds only the execution mechanics required by a feature spec.

## Outcomes and proof

Pair the behavioral contract with its proof in `Verification`:

- One column states the observable feature outcome or invariant.
- The other names the automated test or operational check that proves it.
- Record intermediate verification separately only when a named delivery stage
  needs its own proof.

Cover every material outcome once. Link a separate validation spec only when a
larger proof matrix materially improves implementation or release decisions.

## Implementation steps and phases

Use concrete, ordered implementation steps by default. Name the affected source
file, service, infrastructure boundary, or operational action where it helps an
implementer locate the work.

Add named phases only when work has independently useful delivery stages,
different owners, or material sequencing constraints. When phases are needed,
give each phase:

- the independently useful outcome it delivers;
- concrete repository, infrastructure, documentation, or rollout work;
- verification for that intermediate outcome;
- dependencies and work that may proceed in parallel; and
- an estimate only when it changes staffing, sequencing, or scope decisions.

Do not add a phase solely because the template contains an implementation plan.

## Contract analysis

Before changing a data, API, CLI, configuration, or migration surface, inspect
its current owner, shape, consumers, and existing seams. Justify every new field,
type, state, or execution path against a concrete producer, consumer, and goal.

Put the resulting decisions in `Contract`. Add a before/after example or decision
table only when prose cannot clearly express the behavior. Treat contract
snapshots and minimal-model checks as authoring checks, not mandatory sections.

## Dependencies and access

Record dependencies that can block execution or validation, including external
APIs, credentials, permissions, library versions, infrastructure, datasets, and
required reviewers. State how a real blocker is resolved beside the affected
implementation step or phase.

## Risks, rollout, and recovery

Record only material risks that change the selected contract, implementation, or
rollout. State the concrete mitigation beside the relevant work. Add rollout or
rollback steps only when the change requires staged release or recovery.

Do not invent a fallback merely to fill a risk table. When recovery requires a
second execution path, define it as part of the selected design under Docy's
default, alternative, and failure rules.

## Open decisions

Use Docy's decision-question format. For a blocking item, also track the
execution metadata Specy needs:

- owner or authoritative source;
- next action;
- blocking phase, if any; and
- current status when the spec owns tracking, or the authoritative task link
  when an external tracker owns status.

Omit `Open Decisions` when no unresolved choice remains. When a decision is
resolved, remove it from that section and incorporate its outcome into
`Contract` or `Implementation`.

## Splitting large work

Split independently releasable outcomes or separable dependency graphs into
linked feature specs. Create or link a design document when unresolved
architecture dominates the execution plan.

## Maintaining the plan

Update the feature spec when:

- research changes the approach;
- a decision, dependency, or blocker changes;
- scope or sequencing changes; or
- a phase completes and its verification produces new evidence.

When the repository uses a tracking system, reference task IDs or links and
keep mutable status in that system. Keep the spec focused on the selected
contract, concrete work, material dependencies, and proof. Archive the
completed spec according to the feature-spec workflow.

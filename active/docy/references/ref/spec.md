# Design specifications

Use this reference when creating, editing, or reviewing an architecture or
design specification. Load Docy's core guidance first; its terminology, scope,
source-of-truth, review, and diagram rules also apply here.

Target an architecture-complete, implementation-directed specification, not an
implementation-exhaustive one. The reader should understand the selected model,
ownership, boundaries, observable lifecycle, normal and failure paths, and
deferred scope without reading the implementation.

## Contents

- [Detail and scope](#detail-and-scope)
- [Normative prose](#normative-prose)
- [Ownership and interfaces](#ownership-and-interfaces)
- [Structure and evidence](#structure-and-evidence)
- [Decisions and reviews](#decisions-and-reviews)
- [Final checklist](#final-checklist)

## Detail and scope

### Lead with the selected design and its goal

Open by naming the chosen model and the problem or outcome it serves. Do not
make readers reconstruct the decision from background or a list of options.

**Bad**

> This document explores several ways to execute jobs reliably.

**Good**

> This design places authorized jobs on a durable queue so requests survive
> worker restarts without allowing unauthorized work to run.

### Write the smallest decision-complete contract

Keep facts another component or implementer needs to interoperate safely:
ownership, boundaries, lifecycle, authorization, failure behavior, and deferred
scope. Omit incidental algorithms, storage mechanics, framework choices, and
exhaustive wire types.

**Bad**

> The scheduler stores a lease row with a version counter, updates it with
> compare-and-swap, caches it for 30 seconds, and retries with exponential
> backoff.

**Good**

> The scheduler grants at most one active lease per job. If it cannot renew the
> lease, it stops the job before another scheduler may acquire it.

### Tie every abstraction to a current need

Each resource, field, mode, and execution path must serve a stated goal, current
use case, or interoperability boundary. Delete or defer speculative flexibility.

**Bad**

> Add a `placementStrategy` interface so future schedulers can support unknown
> placement models.

**Good**

> The scheduler selects one region from the account's allowed regions. Additional
> placement strategies are outside this proposal.

### Clarify before expanding the contract

When a term or flow is unclear, first explain its owner, behavior, boundary, or a
representative example. Add normative fields only when another component must
rely on them.

**Bad**

> Readers may wonder how freshness works, so add `refreshEpoch`, `refreshSource`,
> and `refreshPolicy`.

**Good**

> Authorization uses membership read when the request is admitted. Membership
> changes affect the next request; an admitted request keeps its decision.

## Normative prose

### State the selected design positively

Describe what the system does. Keep correction history and rejected alternatives
out of normative sections. Put durable exclusions in Non-goals and useful
comparisons in Alternatives. Mention absent or rejected inputs only when they
explain a meaningful security boundary, migration, or operational failure. Do
not use `V1 Decision` callouts.

**Bad**

> V1 Decision: We will not use push delivery, callbacks, or webhooks.

**Good**

```markdown
## Proposal

Workers poll the queue every ten seconds.

## Non-goals

Push delivery is outside this proposal.
```

### Open with the governing invariant

Lead each section with its rule. Follow with the mechanism, rationale, default,
precedence, failure, and consequence only when relevant.

**Bad**

> Accounts have many settings and may be created in several regions. After
> considering those details, the billing region is fixed.

**Good**

> Each account has exactly one billing region. The region is selected at account
> creation and cannot change; requests for another region are rejected.

### Use precise contract language

Use `must`, `cannot`, `exactly one`, `inherits`, and `is rejected` when the design
requires those semantics. Avoid fuzzy substitutes for required behavior.

**Bad**

> The service generally tries to keep one leader.

**Good**

> A shard has exactly one active leader. A second leader claim is rejected.

## Ownership and interfaces

### Make ownership and boundaries explicit

Name who owns each resource, decision, credential, and side effect. State what
crosses each component or trust boundary and what happens when the receiving
side is unavailable.

**Bad**

> The platform validates and sends the request.

**Good**

> The API authenticates the caller and stores the job. The scheduler selects a
> worker. The worker holds the provider credential and sends the provider
> request. If no worker is ready, the job remains pending.

### Give each contract one owner and each path one route

Separate admission, policy, credential, dispatch, and external-call ownership
when they differ. Do not create fallback or duplicate-authority paths unless the
design requires and defines them.

**Bad**

> Both the API and worker may evaluate policy, and either may call the provider.

**Good**

> The API evaluates request policy and records an authorized job. The worker
> holds the provider credential and calls the provider only for authorized jobs.

### Justify every retained interface and field

For each field, name its purpose, producer, consumer, and interoperability need.
Remove fields reserved only for hypothetical flexibility.

**Bad**

> `metadata: object` is reserved for future integrations.

**Good**

> The gateway produces `tenant_id`; the policy service consumes it to select the
> tenant policy. Requests without `tenant_id` are rejected.

### Keep reusable component specifications application-neutral

Use neutral examples to prove reusable contracts. Put customer-, provider-, or
application-specific workflows in implementation or use-case documents.

**Bad**

> The queue always creates Acme payroll reports in Workday.

**Good**

> A client submits a job with an operation and parameters. The selected adapter
> translates the job for its external system.

### Put defaults, alternatives, and failure together

State the selected default, how an explicit alternative is chosen, and what
happens when it fails. Do not scatter those facts across unrelated sections.

**Bad**

> Managed mode and operator mode are supported.

**Good**

> Managed mode is the default and creates a namespace. Operator mode uses a
> pre-provisioned namespace. If that namespace is missing, creation fails; the
> service does not fall back to managed mode.

## Structure and evidence

### Use the smallest useful document shape

A substantial specification usually progresses through Summary, Motivation,
Goals and non-goals, Proposal, Implementation plan, Risks or alternatives, and
an end-to-end walkthrough. Omit sections that do not clarify the decision.

**Bad**

> Include every template heading, with `N/A` under Migration, Prior art, Security,
> and Rollout.

**Good**

> A focused protocol change includes Summary, Non-goals, Protocol, Failure
> behavior, and Rollout because those sections contain the complete decision.

### Use representative examples as contract evidence

Show the smallest request, response, interface, configuration, or pseudocode
fragment that exposes an important seam. Do not dump full provider schemas or
invent behavior absent from the prose.

**Bad**

> Include a four-page payload catalogue with optional fields no component uses.

**Good**

> `POST /jobs { "operation": "export" }` returns
> `202 { "job_id": "job_123", "state": "pending" }`. The worker advances
> `state` after it accepts the job.

### Prove success and denial or failure

A multi-actor walkthrough should expose authorization, validation, persistence,
dispatch, observable success, and at least one denial or failure path.

**Bad**

> The API creates the job and the worker runs it.

**Good**

> Create job -> authorize caller -> validate operation -> persist job -> dispatch
> worker -> persist succeeded state -> caller observes succeeded. Unauthorized
> caller -> `PERMISSION_DENIED` -> no job is persisted or dispatched.

### Treat diagrams as semantic claims

Apply the core diagram grammar. Make containment, trust, deployment, and call
ownership agree with the prose. Split an oversized diagram by reader journey.

**Bad**

> Draw `tenant boundary` as an arrow pointing at an unlabeled service.

**Good**

> Nest the API and database inside a region labeled `Tenant boundary`; label the
> interaction `API -> database: persist job`.

### Phase implementation by dependency

Define independently useful outcomes, then state their dependency and ordering
constraints. Do not hide the dependency graph in a chronological checklist.

**Bad**

> Phase 1: schemas and UI. Phase 2: policy and logs. Phase 3: more UI.

**Good**

> Phase 1 introduces jobs and persistence. Phase 2 adds policy enforcement and
> depends on Phase 1. Audit logging also depends on Phase 1 but may proceed in
> parallel with Phase 2.

## Decisions and reviews

### Ask concrete decision questions

Ask one choice in plain language. Name the competing outcomes and why the answer
changes the design.

**Bad**

> How should elasticity work?

**Good**

> Should the controller create capacity automatically, or fail until an operator
> adds capacity? Automatic creation requires cloud credentials.

### Review consistency, simplicity, then style

First verify that prose, interfaces, examples, tables, and diagrams describe one
design. Then delete abstractions not required by a current need. Apply prose
style last. Apply the core self-contained finding format after these passes.

**Bad**

> The terminology could be smoother.

**Good**

> The prose assigns authorization to the API, but the sequence diagram assigns it
> to the worker. This creates two policy owners. Show API authorization before
> persistence and dispatch in the diagram.

## Final checklist

- The selected design and the goal it serves are explicit.
- Every abstraction maps to a current goal, use case, or interoperability seam.
- Each resource, decision, credential, side effect, and execution path has one
  authoritative owner.
- Boundaries name what enters, what leaves, and what happens on failure.
- Defaults, precedence, denial, failure, and deferred scope are stated where
  relevant.
- Every retained interface and field has a necessary producer, consumer, and
  purpose.
- Examples and diagrams prove the prose rather than redefine it.
- At least one denial or failure path is covered for a multi-actor lifecycle.
- Normative sections describe supported behavior; exclusions explain meaningful
  security, migration, or operational boundaries.
- Incidental implementation mechanics have been removed.

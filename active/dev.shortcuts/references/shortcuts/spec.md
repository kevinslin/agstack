---
name: spec
description: Draft a spec, run parallel simplification and correctness reviews, then obtain user direction.
---

Shortcut: Spec

Arguments:

- `request`: the feature, investigation, validation, or design request to turn
  into a spec.

Instructions:

Perform these steps in order against one canonical spec:

1. Resolve the requested outcome, scope, constraints, spec type, and
   destination. Ask a focused question before drafting only if a material
   requirement or destination cannot be determined.
2. Use `$specy` to create or update the spec and record its exact path.
3. Start two independent read-only reviewer subagents concurrently against the
   same unchanged spec and original request:
   - Run `$dev.review simplify-spec` to find the narrowest complete 80/20
     implementation and defer speculative requirements, abstractions, and edge
     cases.
   - Run `$dev.review spec` to check correctness, source evidence, approved
     scope, contracts, security, ownership, and implementation readiness.
   - Each subagent is the reviewer pass: apply its selected review workflow
     directly without redispatching `trigger:spec` or starting nested loops.
     Neither reviewer may edit the spec.
4. Merge both sets of findings, preserving explicit requirements and existing
   security, correctness, and ownership invariants when recommendations
   conflict. Present the spec path, proposed simplifications, correctness
   findings, material tradeoffs, and deferred work.
5. Ask the user to approve the combined direction or provide course
   corrections, then stop and wait for their reply. Do not update the spec with
   review findings before this checkpoint.
6. After the user responds, apply approved changes once to the same spec without
   reintroducing rejected complexity or expanding the approved scope.
7. Run a targeted follow-up `$dev.review spec` check only if the approved
   changes materially alter contracts or security-sensitive behavior. Limit it
   to the changed surfaces; do not repeat both full reviews.
8. Report the final spec path, significant changes, unresolved findings, and
   remaining open questions.

A reviewer pass does not complete this shortcut while its user checkpoint or a
later stage remains unfinished.

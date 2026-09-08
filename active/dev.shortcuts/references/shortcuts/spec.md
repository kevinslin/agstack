---
name: spec
description: Draft a spec, run independent reviews, and enforce a fresh simplification gate.
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
2. Use `$specy` to create or update the spec and record its exact path. This
   shortcut owns the feature-spec simplification gate; do not run it twice.
3. Start two independent read-only reviewer subagents concurrently against the
   same unchanged spec and original request:
   - Run `$dev.review simplify-spec` to find the narrowest complete 80/20
     implementation and defer speculative requirements, abstractions, and edge
     cases. Require its structured verdict for the exact reviewed spec digest.
   - Run `$dev.review spec` to check correctness, source evidence, approved
     scope, contracts, security, ownership, and implementation readiness.
   - Each subagent is the reviewer pass: apply its selected review workflow
     directly without redispatching `trigger:spec` or starting nested loops.
     Neither reviewer may edit the spec.
4. Save the simplification review's structured JSON outside the repository and
   run the [simplification validator](../../../specy/scripts/validate_spec_simplification.py)
   with `--spec <spec> --review <review.json> --phase review`. A correctness
   finding, missing remove/defer analysis, unsupported no-change claim, stale
   digest, or unjustified oversized final document does not satisfy this gate.
   An oversized draft may proceed only when its review proposes shortening it.
5. Merge both sets of findings, preserving explicit requirements and existing
   security, correctness, and ownership invariants when recommendations
   conflict. Present the spec path, proposed simplifications, correctness
   findings, material tradeoffs, and deferred work. For each proposed
   simplification, explain what changes, why the narrower approach is
   sufficient, which requirements or invariants it preserves, and any
   meaningful tradeoff. Do not offer unexplained recommendations.
6. Ask the user to approve the combined direction or provide course
   corrections, then stop and wait for their reply. Do not update the spec with
   review findings before this checkpoint.
7. After the user responds, apply approved changes once to the same spec without
   reintroducing rejected complexity or expanding the approved scope.
8. If the spec changed, obtain a focused new `$dev.review simplify-spec`
   verdict for its current digest. A verdict of `changes-proposed` blocks final
   completion; explicit user-approved deferrals must use `user-deferred` and
   record the actual user decision. Run a targeted `$dev.review spec` check
   only if the approved
   changes materially alter contracts or security-sensitive behavior. Limit it
   to the changed surfaces; do not repeat both full reviews.
9. Run the simplification validator again with `--phase final`. Never report
   completion when the current document lacks a fresh passing verdict, when
   simplification proposals remain unresolved, or when a spec over 150 lines
   lacks a concrete justification.
10. Report the final spec path, significant changes, unresolved findings, and
   remaining open questions.

A reviewer pass does not complete this shortcut while its user checkpoint or a
later stage remains unfinished.

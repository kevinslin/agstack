---
name: spec
description: Draft a spec, simplify it, obtain user direction, then run a full spec review.
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
3. Run `$dev.review simplify-spec` against that spec and the original request.
   Apply accepted simplifications directly to the same spec, preserving the
   requested outcome and existing security, correctness, and ownership
   invariants. Prefer the narrowest complete 80/20 implementation and defer
   speculative requirements, abstractions, and edge cases.
4. Present the simplified spec path, proposed implementation, material
   tradeoffs, and deferred work. Ask the user to approve the direction or
   provide course corrections, then stop and wait for their reply. Do not run
   the final review before this checkpoint.
5. After the user approves or supplies course corrections, update the same spec
   as needed and run `$dev.review spec` against its final direction.
6. Apply accepted review findings without reintroducing rejected complexity or
   expanding the approved scope. Report the final spec path, significant
   changes, unresolved findings, and remaining open questions.

Keep the simplification and full spec reviews as separate ordered stages. A
review does not complete this shortcut while its user checkpoint or a later
stage remains unfinished.

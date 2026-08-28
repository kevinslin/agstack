# Spec Simplification Workflow

Use this workflow when a user asks whether a spec or proposed implementation can
be radically simplified. Optimize for an 80/20 solution: narrowly accomplish the
current goal, preserve real invariants, and add complexity only when a concrete
requirement needs it.

## Review Question

Ask explicitly: **Can we radically simplify this implementation while still
achieving the requested outcome?**

Do not optimize for hypothetical future requirements, exhaustive edge-case
coverage, generic extensibility, or the most comprehensive possible design.

## Authorization Checklist

Complete this checklist before editing a specification or starting a fixer pass:

- [ ] Determine whether the user explicitly authorized changes to the artifact.
      Treat `$dev.review simplify spec` and other review requests as review-only.
- [ ] Present the proposed simplifications and their relevant tradeoffs first.
- [ ] Ask whether to apply those changes and wait for the user's explicit
      approval, unless the current request already explicitly says to edit,
      rewrite, update, or apply the changes.
- [ ] Confirm the approved artifact and scope before making any changes.
- [ ] Keep automatic `trigger:loop` routing read-only until approval; it never
      authorizes edits or a fixer pass by itself.

If authorization is missing or unclear, stop after the review and ask the user.

## Workflow

1. State retained capabilities, acceptance outcomes, ownership boundaries,
   security or correctness invariants, and explicit non-goals from the latest
   user decisions and authoritative requirements before proposing deletions.
   Distinguish these contracts from replaceable implementation mechanisms. Keep
   every requested capability; dropping one is not simplification.
2. Describe the smallest end-to-end implementation that satisfies those
   constraints using existing code, data, public dependency contracts, and
   control flow, with one source of truth and lifecycle-aligned ownership.
3. Challenge every proposed abstraction, helper, configuration option, public
   API, persistence model, state machine, compatibility path, background job,
   retry policy, migration, rollout phase, and observability mechanism. Remove
   it unless the current goal or an existing invariant concretely requires it.
   For each removal, inspect actual consumers, including integration setup,
   and explain why it is unnecessary or where its required behavior remains
   provided. Absence of callers does not override an explicitly required
   capability.
4. Keep edge cases only when they are reachable, materially affect the requested
   outcome, or protect an existing safety or ownership boundary. Defer
   speculative cases until a real consumer, failure, or requirement appears.
5. Prefer direct implementation over frameworks, existing seams over new
   coordination, and outcome-focused tests over exhaustive implementation-detail
   coverage. When deleting or consolidating tests, name the distinct acceptance
   outcomes and their retained or replacement coverage. Do not replace required
   real-system evidence with mocks. Scale proof and operational machinery to
   actual risk.
6. State what remains deferred, why that tradeoff is acceptable now, and which
   concrete future signal would justify adding the omitted complexity. Present
   alternatives that drop retained capabilities separately as scope changes
   requiring explicit user approval, not as capability-preserving
   `remove_or_defer` findings. Rejecting those alternatives must not block
   completion of the original scope.

## Output

- **Keep:** retained capabilities, acceptance outcomes, and security,
  correctness, or ownership invariants that must not be weakened.
- **Smallest viable implementation:** the narrow approach and why it meets the
  current goal.
- **Remove or defer:** unnecessary requirements, components, edge cases, tests,
  and operational work.
- **Tradeoffs:** relevant limitations and the real conditions that would make a
  more complete solution necessary.

Do not rewrite the spec or implementation unless the user authorizes edits. Do
not classify omitted future-proofing as a blocker when the approved scope and
existing invariants do not require it.

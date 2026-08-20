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

## Workflow

1. Identify the requested outcome, acceptance criteria, ownership boundaries,
   existing security or correctness invariants, and explicit non-goals.
2. Describe the smallest end-to-end implementation that satisfies those
   constraints using existing code, data, contracts, and control flow.
3. Challenge every proposed abstraction, helper, configuration option, public
   API, persistence model, state machine, compatibility path, background job,
   retry policy, migration, rollout phase, and observability mechanism. Remove
   it unless the current goal or an existing invariant concretely requires it.
4. Keep edge cases only when they are reachable, materially affect the requested
   outcome, or protect an existing safety or ownership boundary. Defer
   speculative cases until a real consumer, failure, or requirement appears.
5. Prefer direct implementation over frameworks, existing seams over new
   coordination, and outcome-focused tests over exhaustive implementation-detail
   coverage. Scale proof and operational machinery to actual risk.
6. State what remains deferred, why that tradeoff is acceptable now, and which
   concrete future signal would justify adding the omitted complexity.

## Output

- **Smallest viable implementation:** the narrow approach and why it meets the
  current goal.
- **Remove or defer:** unnecessary requirements, components, edge cases, tests,
  and operational work.
- **Keep:** explicit acceptance criteria and existing security, correctness, or
  ownership invariants that must not be weakened.
- **Tradeoffs:** relevant limitations and the real conditions that would make a
  more complete solution necessary.

Do not rewrite the spec or implementation unless the user authorizes edits. Do
not classify omitted future-proofing as a blocker when the approved scope and
existing invariants do not require it.

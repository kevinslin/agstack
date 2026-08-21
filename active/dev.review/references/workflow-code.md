# Code Review Workflow

Use this workflow to review code with a bias toward simplicity and correctness.

## Steps

1. Check correctness and logic.
   - Identify bugs, edge cases, race conditions, or incorrect behavior.
   - Call out violated invariants or implicit contracts.
   - For authorization behavior, identify the actor, effective permissions, exact resource, and expected allow or deny outcome.
2. Check assumptions and documentation.
   - Cross-check against existing documentation, comments, and expected behavior.
   - Highlight assumptions that are undocumented, outdated, or unsafe.
   - Verify contracts, documentation, generated artifacts, and tests describe the current implementation rather than retired behavior.
3. Check complexity and design.
   - Identify unnecessary abstractions, indirection, or branching.
   - Propose concrete simplifications such as deletion, inlining, or narrower scope.
   - Prefer one canonical implementation over parallel operations, alternate representations, or fallback paths.
   - Keep one authoritative configuration or contract per behavior, and align
     resource ownership with its actual creator, consumer, and lifecycle.
   - Keep independent concepts such as consumer identity, implementation
     selection, and authorization identity in separate contracts.
   - Inspect public dependency exports before accepting local SDK-shaped types.
     Prefer existing concrete types or a narrowly named extension; preserve
     wire-format compatibility and stricter application-owned validation.
   - Give each invariant one authoritative validation boundary; prefer storage constraints for persisted invariants and flag repeated checks in application layers.
4. Check for dead code and stale surface.
   - Look for unreachable branches, obsolete compatibility shims, abandoned helpers, duplicate implementations, unused parameters, stale feature flags, and outdated docs/tests/config left behind by the change.
   - Verify likely dead code with call-site, import/export, route, config, CLI, migration, or serialization searches before recommending deletion.
   - Establish whether an interface or persisted format has actual consumers or an explicit compatibility requirement before preserving an older implementation.
   - When compatibility is not required, remove superseded APIs, helpers, formats, fixtures, and error cases instead of introducing bridges or dual behavior.
   - Prefer concrete deletion follow-ups: file/symbol to remove and contracts, generated artifacts, documentation, or tests to update.
5. Review test value and clarity.
   - Test application-defined behavior and invariants at the boundary responsible for enforcing them.
   - Preserve every explicitly approved capability and existing security,
     ownership, isolation, credential, and immutability invariant; removing one
     is not a valid simplification.
   - Do not test framework guarantees, infrastructure inventories, exact tool versions, or incidental implementation details unless the application explicitly owns that requirement.
   - Avoid repeating equivalent cases across test layers; keep comprehensive coverage where it most directly verifies application behavior.
   - Remove low-value tests added on the branch, especially tests that verify their own monkeypatched behavior.
   - When possible, elevate them to higher-level tests that verify outcomes and are not coupled to implementation.
   - When a test outcome is not obvious, require a short comment identifying the relevant rule, missing input, invalid value, or security boundary.
6. Check failure modes and risk.
   - Describe how the code could fail in production through inputs, scale, or partial failure.
   - Note regressions and compatibility risks when real consumers or an explicit support requirement make them relevant.
7. Sketch a simpler rewrite when useful.
   - Prefer clarity and robustness over flexibility.
8. Create or update a flow doc when the review needs one.
   - Use `$specy` under `$ROOT_DIR/prs/`.
   - Capture PR context, key files touched, execution/data flow, major risks, and open questions.
   - Use a stable PR-based filename when possible, for example `<pr-number>-<slug>.md`.
9. For PR review loops, verify the remote gate before handoff.
   - Confirm the current PR head SHA after every push or amend.
   - Inspect current checks, actionable comments/reviews, and unresolved non-outdated review threads.
   - Do not report the loop as finished while required checks are failed/pending or review items remain.
   - In the handoff, include head SHA, failing/pending check count, unresolved thread count, and any blocker that still needs user action.

## Severity Guidance

Clearly label severity for each issue: blocker, major, minor, or nit.

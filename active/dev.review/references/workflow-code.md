# Code Review Workflow

Use this workflow to review code with a bias toward simplicity and correctness.

## Steps

1. Check correctness and logic.
   - Identify bugs, edge cases, race conditions, or incorrect behavior.
   - Call out violated invariants or implicit contracts.
   - Before calling an invariant a blocker, trace it to the user's latest
     explicit decision, an authoritative current contract, or an actual
     enforcement boundary. Distinguish the required outcome from a stronger
     implementation mechanism that the product does not require.
   - Verify existing queue serialization, database constraints, locks, leases,
     and ownership boundaries before claiming a race or missing enforcement.
   - For authorization behavior, identify the actor, effective permissions, exact resource, and expected allow or deny outcome.
2. Check assumptions and documentation.
   - Cross-check against existing documentation, comments, and expected behavior.
   - Highlight assumptions that are undocumented, outdated, or unsafe.
   - Verify contracts, documentation, generated artifacts, and tests describe the current implementation rather than retired behavior.
   - Verify active specifications follow the latest approved user decisions and
     temporary security compromises have nearby TODOs naming their replacement.
3. Check complexity and design.
   - Complete the mandatory Simplicity Audit checklist below against the
     current, post-fix diff before finishing the review.
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
   - Complete the mandatory Test Audit checklist below for every added or
     modified test before finishing the review.
   - Classify every added or modified test as `keep`, `merge`, or `delete`
     based on the distinct production behavior it proves.
   - Test application-defined behavior and invariants at the boundary responsible for enforcing them.
   - Preserve every explicitly approved capability and existing security,
     ownership, isolation, credential, and immutability invariant; removing one
     is not a valid simplification.
   - Do not test framework guarantees, infrastructure inventories, exact tool versions, or incidental implementation details unless the application explicitly owns that requirement.
   - Avoid repeating equivalent cases across test layers; keep comprehensive coverage where it most directly verifies application behavior.
   - Remove low-value tests added on the branch, especially tests that verify their own monkeypatched behavior.
   - Delete a lower-fidelity duplicate when a real application or integration
     test already proves the same invariant; first move any unique assertion
     into the retained stronger test.
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

## Mandatory Simplicity Audit

Include a `Simplicity Audit` section in every code-review response. Replace
`[ ]` with `[x]` only after inspecting concrete evidence; cite the relevant
production file and line, actual consumer, dependency contract, or diff.

- [ ] Identified the approved outcome, smallest complete execution path, and
  security, ownership, compatibility, and acceptance boundaries that must stay.
- [ ] Named the single authoritative owner for each introduced identity,
  mutable state, configuration value, authorization decision, and lifecycle.
- [ ] Compared development, production, bootstrap, request handling, and
  persistence paths; flagged parallel operations and duplicate ownership.
- [ ] Justified each new public API, adapter, helper, validation boundary,
  compatibility path, and coordination mechanism with a current consumer or
  concrete required invariant.
- [ ] Checked existing dependency exports, application routes, and storage
  constraints before accepting locally recreated interfaces or guarantees.
- [ ] Distinguished required generated artifacts and dependency changes from
  avoidable generator, lockfile, documentation, and fixture churn.
- [ ] Proposed concrete deletion or consolidation with file references, or
  explained why the smallest safe alternative cannot meet the approved scope.
- [ ] Rechecked the final post-fix diff instead of relying on a review of an
  earlier implementation or pre-fix architecture.

Leave unverifiable items unchecked, explain the evidence gap, and do not claim a
clean review while the audit is incomplete. Classify materially avoidable
duplicate authority, competing sources of truth, parallel implementations
without a required consumer, and substantial implementation-coupled test or
generator machinery as major when a concrete smaller alternative preserves all
approved capabilities and existing security, ownership, and supported
compatibility boundaries. Do not classify preference, necessary infrastructure,
or a genuinely required compatibility contract as a simplification defect.

## Mandatory Test Audit

Include a `Test Audit` section in every code-review response. Copy this
checklist and replace `[ ]` with `[x]` only after inspecting concrete evidence;
cite the relevant test or production file and line, command, or observed
outcome beside each checked item.

- [ ] Inspected every added or modified test and identified its production
  behavior and observable outcome.
- [ ] Assigned each added or modified test a `keep`, `merge`, or `delete`
  disposition with its distinct invariant and the strongest existing proof.
- [ ] Verified the exercised route, request, ownership, lifecycle state, and
  response exist in the actual application.
- [ ] Identified each mock, monkeypatch, fixture, or adapter and confirmed
  assertions exercise product behavior rather than behavior introduced by the
  substitute.
- [ ] Verified security, authorization, persistence, or lifecycle assertions
  at the real boundary responsible for enforcing them.
- [ ] Removed or consolidated duplicate coverage, implementation-coupled
  checks, framework-guarantee tests, and tests that merely validate their own
  setup when edits are authorized; otherwise reported each as an unresolved
  major finding.
- [ ] Preserved user-requested end-to-end proof and meaningful security,
  authorization, ownership, persistence, and supported-compatibility coverage.
- [ ] Confirmed deleted tests have no unique production outcome, kept the
  stronger surviving test, and reran the relevant remaining coverage.
- [ ] Distinguished real infrastructure or runtime execution from fixtures,
  rendering-only checks, skipped cases, and unavailable dependencies.
- [ ] Verified every test or end-to-end outcome explicitly requested by the
  user actually passed at its requested application or infrastructure boundary.
- [ ] Confirmed non-obvious integration setup and assertions explain the
  business rule or security boundary being verified.

Include a compact `Test Disposition` section naming each added or modified test
and its decision:

- `keep`: identifies a distinct approved behavior or security invariant and the
  real boundary proving it.
- `merge`: moves a useful unique assertion into the stronger existing test,
  then removes the duplicate.
- `delete`: proves only fixture behavior, framework guarantees, incidental
  implementation, an unreachable branch, or an outcome already covered better.

If any item cannot be verified, leave it unchecked, explain the evidence gap,
and report the affected test by file and line. Treat a fabricated production
path, self-validating mock, or branch-added test with no distinct production
outcome as a major finding even when the suite passes. In an edit-authorized
review loop, delete or merge the test and rerun the surviving relevant proof;
in a review-only request, report the major finding without editing. Never
remove explicitly requested end-to-end proof, unique security coverage, or
unrelated pre-existing tests outside the approved change. Do not approve or
describe the review as complete while an unjustified test remains, required
audit evidence is missing, or an explicitly requested test has not passed. If
the change contains no added or modified tests, write `Test Audit: no added or
modified tests` and still report any explicitly requested acceptance test.

## Severity Guidance

Clearly label severity for each issue: blocker, major, minor, or nit.

# Feature Spec: Fast Tracked-Task Handoff

**Date:** 2026-07-16
**Status:** Completed

---

## TL;DR

- Shorten the parent-side task-creation path by using the JSON returned by existing write commands as verification and removing redundant `show`, `read_thread`, and assistant-backfill work.
- Preserve the version-2 ledger contract: do not add `register --initial-prompt`, change schema version 2, or weaken parent-lineage and initial-user-rollout guarantees.
- Prefer create-without-prompt, then register, then prompt; keep the current one-shot creation path as a bounded fallback using `record-turn --turn-id bootstrap --json`.
- Prove the change with contract tests and a live lifecycle trace; keep multi-sample clean/fork timing as an explicit follow-up rather than treating either single trace as a latency SLO.

---

## Goal and Scope

### Goal

Reduce the time from receiving a real Codex child thread ID to returning a tracked deep link. The normal path must stop waiting on child inspection or completion while still proving that the version-2 ledger contains the child, immutable parent lineage, the creation rollout, and a race-safe initial user rollout when bootstrap is required.

### In Scope

- Rewrite the `agtask` skill workflow so successful write-command JSON is the source of verification.
- Remove `show --id <id> --json` from the normal post-creation path.
- Prohibit normal-path `read_thread` calls and assistant bootstrap/backfill.
- Publish the real deep link as soon as a real child ID exists, with tracking state stated separately until registration commits.
- Keep title assignment after successful registration and outside the tracking-readiness decision.
- Use the existing `record-turn` bootstrap path only for the initial user rollout when the real hook may have raced registration or has not yet become observable.
- Update skill contract tests, active architecture documentation, and the generated `agtask` package.
- Capture repeatable call-count and ledger evidence; leave broader clean/fork timing sampling as a non-blocking follow-up.

### Out of Scope

- Changing the SQLite schema, schema version, database path, rollout fields, role vocabulary, or unique indexes.
- Adding `--initial-prompt` to `register`, adding a combined register-and-turn command, or restoring v1 session/activity output.
- Implementing new Codex app-server `thread/start` or `turn/start` tools.
- Persisting or globally caching CWD-to-project mappings. Exact-CWD resolution belongs at the Codex app boundary and needs its own cache ownership and invalidation design.
- Waiting for child completion, monitoring the child, or reconstructing a missed assistant result unless the user explicitly requests monitoring.
- Cleaning up historical duplicate activities from the v1 database.

---

## Context

### Background

The original timing analysis observed one clean task whose child began work about 1.5 seconds after Codex created the thread, while ledger registration committed about 7.5 seconds after creation. The `Stop` hook recorded the final result about 107 milliseconds after child completion, but a later parent-side snapshot created a redundant assistant activity. That trace supports removing redundant orchestration; it does not establish a general latency distribution or prove that SQLite can never contribute to cold-start or contention latency.

The original short-term pseudocode proposed `register --initial-prompt --json`. The completed version-2 ledger contract supersedes that command shape: `register` has no initial-prompt option, event identity is explicit in `rollout`, and `record-turn` owns symmetric reconciliation between the reserved `bootstrap` event and the real hook turn ID. This spec keeps the optimization but maps it onto the current contract.

### Current State

- The skill already prefers two-phase clean creation and always uses prompt-free fork creation when the app surface supports those operations.
- `register --json` commits and returns the complete thread object plus current `rollouts`; a following `show --json` reopens the same database and returns the same shape.
- The skill nevertheless requires a separate `show` after creation and may inspect hook visibility before deciding whether to backfill the fork's initial user rollout.
- `record-turn --json` also returns the complete thread object after committing. A matching real-hook event and bootstrap event converge to one rollout regardless of arrival order.
- The `Stop` hook is the canonical assistant-rollout writer. Parent-side child inspection is not required to capture the normal assistant result.

### Context

- [Thread and rollout ledger schema](../02-thread-rollout-ledger-schema.md): authoritative version-2 data, idempotency, lineage, bootstrap, CLI, and JSON contract.
- [Architecture](../../ARCHITECTURE.md): current clean/fork sequences, hook mapping, and source/runtime ownership.
- [Skill workflow](../../../skills/agtask/SKILL.md): orchestration contract to simplify and the user-visible handoff shape.
- [CLI implementation](../../../skills/agtask/scripts/agtask): existing `register`, `record-turn`, `thread_dict`, and hook behavior reused unchanged.
- [CLI tests](../../../tests/test_cli.py): current JSON-shape, bootstrap-ordering, conflict, and lifecycle coverage.
- [Skill contract tests](../../../tests/test_skill_contract.py): executable assertions for the orchestration instructions.
- Original timing analysis supplied with the delegated task: empirical motivation and pre-version-2 proposal; intentionally not a repository source of truth.

### Constraints

- The repository remains canonical; the installed skill is generated through the existing scoped `skillz` workflow.
- A created Codex thread and a successfully tracked thread are distinct states. User-facing output must not claim tracking before `register` commits.
- A deep link can be published for a real child before registration, but it must be labeled `tracking pending` until a write-command result proves tracking.
- `parent_thread_id` is required for every skill-created clean or fork child and remains immutable.
- Hook failures remain fail-open. Explicit CLI writes and verification remain fail-closed with exact errors.
- Normal creation does not wait for the assistant result. This keeps child runtime off the handoff critical path.
- Dynamic shell values remain individually quoted; no prompt text is interpolated into an unsafe command string.

---

## Approach and Touchpoints

### Proposed Approach

Use the result of the last required ledger write as the verification snapshot.

For a prompt-free clean or fork surface:

1. Create the empty child and obtain its real ID.
2. Immediately emit a commentary update with its deep link labeled `created; tracking pending`.
3. Run `register --status todo --json` with the child ID, invoking parent ID, title, and summary.
4. Validate the returned object for exact ID, parent, title, summary, `todo` status, and one `thread.created` rollout. Tracking is now verified.
5. Send the appropriate clean or guarded fork prompt so child execution does not wait on title assignment.
6. After prompt submission succeeds, run one unconditional `record-turn --role user --turn-id bootstrap --content <complete-prompt> --json`. Pass the byte-identical prompt submitted to Codex and omit `--summary` so the CLI and real hook apply the same normalization.
7. Validate exactly one total initial user rollout whose message equals the CLI-normalized prompt. When no later assistant rollout exists, require `active` status and the same prompt-derived `description`. When a fast `Stop` hook has already written a later assistant rollout, require its description and accept the authoritative returned `active`/`blocked` status. Do not recompute status from the normalized stored message: the CLI derives it from raw assistant content before normalization. Symmetric reconciliation makes this safe whether the hook or bootstrap wins the race.
8. Attempt title assignment, then repeat the link in the final handoff with the strongest verified state. Return without a normal-path `show`, `read_thread`, child-completion poll, or assistant backfill.

For a one-shot clean surface:

1. Create the child with `Task:\n<task>` and obtain its real ID.
2. Immediately emit a commentary update with its deep link labeled `created; tracking pending`.
3. Run `register --status active --json` and validate the returned identity, lineage, and creation rollout.
4. Run the same initial-user `record-turn ... bootstrap ... --json` and validate its returned snapshot, including any later assistant-owned description and status.
5. Set the title and return without child reads or assistant backfill.

`record-turn` is intentionally separate from `register`. Reintroducing the conceptual `--initial-prompt` option would contradict the current CLI contract and enlarge the short-term change without improving the ledger model. The extra local write preserves the initial-user invariant; the removed app read and database `show` are the latency-relevant savings.

### Integration Points / Touchpoints

- [`skills/agtask/SKILL.md`](../../../skills/agtask/SKILL.md): define exact ordering, command-result verification, partial states, and prohibited normal-path calls.
- [`tests/test_skill_contract.py`](../../../tests/test_skill_contract.py): assert the fast-path ordering and absence of redundant reads/assistant backfill.
- [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md): update clean and fork sequences, readiness semantics, and bootstrap timing.
- [`tests/test_cli.py`](../../../tests/test_cli.py): add or refine assertions only where needed to make the reused write-result and reconciliation contracts explicit.
- `dist/agtask.skill`: regenerate after source and tests pass; do not hand-edit the package.

### Resolved Ambiguities / Decisions

- **Readiness definition:** `created` means a real child ID exists; `tracked` means registration is proven against the exact invariant; `prompt accepted` means the create/send operation succeeded; `initial rollout verified` means the post-turn snapshot contains exactly one total initial user rollout with the canonical normalized message; `completed` is a later hook-owned child state.
- **Link timing:** Emit one commentary update as soon as the real ID exists, before registration, and explicitly label it `created; tracking pending`. Repeat the link in the final handoff with the strongest verified state.
- **Verification source:** Never reread state solely to verify the immediately preceding write. Use the JSON returned by `register` or `record-turn`.
- **Ambiguous registration recovery:** When registration returns malformed JSON or has an ambiguous process failure, allow one targeted `show --json` read. Continue when that snapshot proves the exact registration invariant; retry the identical registration once only when the read proves the child is untracked. Otherwise return registration partial with the real link and exact errors.
- **Initial user event:** Keep it. The current schema's symmetric bootstrap reconciliation replaces the outdated `register --initial-prompt` proposal.
- **Bootstrap policy:** After a successful prompt submission, issue exactly one user bootstrap write without first reading hook state. Pass the same complete prompt and omit `--summary`; the write then inserts, promotes, or no-ops against the identically normalized real event.
- **Assistant event:** The `Stop` hook is the only normal-path writer. Do not inspect the child and do not synthesize an assistant rollout.
- **Fast assistant race:** If real user and assistant hooks both commit before bootstrap verification, the bootstrap no-op correctly returns the assistant-owned latest description and status. Require one canonical initial user rollout, but accept that stronger later lifecycle state. The returned `active`/`blocked` status is authoritative because the stored assistant message has already been normalized and cannot reproduce the raw-prefix decision.
- **Title:** Attempt title assignment after tracking is verified. A title error is reported independently and does not turn a verified ledger row into a registration failure.
- **Concurrent title contract:** Preserve the separately requested rule that removes every leading emoji grapheme and its immediately following whitespace from the resolved child title while preserving emoji elsewhere. This includes repeated prefixes such as `⭐ 🚀 agtask/topic` becoming `agtask/topic`; `agtask/⭐-topic` remains unchanged.
- **Ambiguous user-write recovery:** When `record-turn` fails, times out, or returns malformed JSON after prompt acceptance, retry the identical idempotent command once. If the retry is still ambiguous, allow one targeted `show --json` error-path read. Return verified only if that snapshot proves the exact invariant; otherwise report `tracked; prompt accepted; initial rollout unverified` with the exact write and recovery errors.
- **Project lookup caching:** Defer it. One invocation creates one child, so a per-invocation cache has no value, while a persistent cache needs an owner, freshness contract, and invalidation signal that this repository does not have.
- **Two-phase app work:** Reuse a prompt-free surface when available, but do not implement new app-server methods in this short-term spec.

### Existing Contract Snapshot

| Surface | Current owner / source of truth | Current contract | Current consumers |
| --- | --- | --- | --- |
| Registration write | `command_register()` | `register ... --status todo|active --json`; returns a full thread object with `rollouts`; no `--initial-prompt` | Skill orchestration and CLI tests |
| Initial turn write | `command_record_turn()` | `record-turn ... --role user|assistant --turn-id ... --json`; returns the post-commit thread object | Hooks, skill fallback, CLI tests |
| Bootstrap reconciliation | `record_turn()` and schema spec 02 | Same normalized user event converges across real-first or bootstrap-first ordering | One-shot and prompt-send race repair |
| Verification read | Current skill | Always runs `show --id <id> --json` after creation | Parent handoff only |
| Assistant capture | `Stop` hook | Writes one assistant rollout keyed by the real Codex turn ID | Ledger history and status transitions |
| Link/title handoff | Current skill | Publishes link and sets title during creation, then returns after full `show` verification | User-facing task creation |

### Target Decision Table

| Input facts / state | Target output | Notes |
| --- | --- | --- |
| Creation returns a pending client/worktree ID, not a real thread ID | Queued result with pending ID; no registration attempt | Existing queued contract remains unchanged |
| Real child ID exists but registration has not completed | Publish link as `created; tracking pending` | Do not claim tracked state |
| `register --json` succeeds and matches ID/parent/title/summary plus `thread.created` | `tracked` | Returned write result replaces `show` |
| Registration returns malformed JSON or its process outcome is ambiguous | Run one targeted `show --json`; retry registration once only if the read proves the child is untracked | Never blindly repeat a possibly committed state change |
| Registration returns a definitive validation, lineage, or compatibility error | Registration-partial result with real link and exact error | Do not retry or hide the child |
| Prompt-free child is tracked but prompt submission fails | `tracked; prompt not accepted`, status remains `todo`, no bootstrap write | Prevent a synthetic user event for a rejected prompt |
| Prompt submission succeeds; real user hook has not committed | Bootstrap `record-turn` inserts one user rollout and activates the thread | Final write response is the verification snapshot |
| Prompt submission succeeds; matching real user hook committed first | Bootstrap `record-turn` is a no-op and returns the existing real rollout | Symmetric reconciliation preserves one event |
| Bootstrap committed before matching real user hook | Later hook promotes bootstrap to the real turn ID | No parent read is required |
| Matching real user and assistant hooks commit before bootstrap verification | Bootstrap is a no-op; exactly one user rollout remains and the later assistant description/status is authoritative | Do not reject or overwrite stronger lifecycle state |
| Bootstrap write fails, times out, or returns malformed JSON after prompt acceptance | Retry the identical write once; if still ambiguous, run one targeted `show --json` | Error-path recovery is allowed because commit state is unknown |
| Recovery cannot prove exactly one canonical initial user rollout | `tracked; prompt accepted; initial rollout unverified` plus exact errors | Do not overstate verification or synthesize an assistant event |
| Title update fails after tracking | Return tracked result plus title warning | Tracking and title states are independent |
| Child completes after registration | `Stop` hook records assistant rollout | Parent does not wait or backfill |
| Child completes before one-shot registration | Handoff may lack the first assistant rollout | Accepted short-term fallback risk; prefer prompt-free creation and register first |
| User explicitly asks to monitor | Enter the separate monitoring workflow | Monitoring is not part of normal creation readiness |

### Minimal Model Check

- **New fields/types/states:** None in SQLite, CLI JSON, or hook payloads. The skill adds user-facing readiness labels only: `tracking pending`, `tracked`, `prompt accepted`, `prompt not accepted`, `initial rollout unverified`, and `registration partial`.
- **Existing fields/types reused:** `thread.id`, `parent_thread_id`, title, description, status, `rollouts`, `thread.created`, and the reserved `bootstrap` turn ID.
- **Derived values intentionally not stored:** Readiness labels, deep links, creation mode, title-attempt outcome, project lookup cache entries, call timings, and child completion state.
- **Consumers:** The parent agent consumes write-command JSON to classify handoff; hooks and SessionStart continue consuming the unchanged ledger.
- **Simpler alternative considered:** Trusting `register` alone would be faster but would weaken the required initial-user-rollout guarantee on one-shot creation. Adding `--initial-prompt` would combine writes but contradicts the established version-2 CLI contract. Reusing `record-turn` with the original prompt and the CLI's normalizer is the smallest compatible solution.

---

## Acceptance Criteria

- [x] Normal clean and fork creation never call `show` or `read_thread` solely to verify a write that already returned JSON.
- [x] One commentary update makes the real deep link available as soon as the child ID exists and labels it `created; tracking pending`; the final handoff repeats the link with the strongest verified state.
- [x] Every skill-created child that reaches `tracked` has the exact invoking `parent_thread_id` and one `thread.created` rollout.
- [x] Every successfully submitted initial prompt that reaches `initial rollout verified` has exactly one total initial user rollout whose message equals the CLI-normalized prompt, independent of real-hook/bootstrap arrival order; `active` plus prompt description is required only before any later assistant rollout.
- [x] Normal creation never waits for child completion and never writes an assistant bootstrap/backfill; assistant completion remains owned by the `Stop` hook.
- [x] Prompt-send, registration, title, queued-creation, and partial-success failures are reported as distinct states without overstating success.
- [x] The version-2 schema, database path, CLI vocabulary, JSON field names, unique-event semantics, and hard-cut migration policy remain unchanged.
- [x] The normal fast path contains no more than one child-create operation, one registration write, one prompt-send operation when separate, one user bootstrap write, and one title mutation; it contains no synchronous child-state read.

---

## Phases and Dependencies

### Phase 1: Encode the fast-path contract

- [x] Rewrite the clean, one-shot fallback, and fork sequences in `skills/agtask/SKILL.md` with the exact state and ordering rules from this spec.
- [x] Replace the existing `show`-based verification section with write-result validation for `register` and `record-turn`.
- [x] State that link publication may precede tracking only with a `tracking pending` label.
- [x] Remove hook-visibility polling, normal-path `read_thread`, and all assistant-bootstrap instructions.
- [x] Keep user bootstrap unconditional after successful prompt submission where an initial-turn proof is required, relying on symmetric reconciliation instead of a read-before-write decision.
- [x] Add the targeted registration-recovery read, proof-gated retry, and registration-partial classification for ambiguous register outcomes.
- [x] Add the bounded identical retry, targeted error-path read, and `initial rollout unverified` classification for an ambiguous user-write result.

### Phase 2: Lock the workflow with tests

- [x] Extend `tests/test_skill_contract.py` to assert create/register/prompt/bootstrap ordering for prompt-free and one-shot flows.
- [x] Assert that normal-path text does not require `show --id`, `read_thread`, assistant bootstrap, or child-completion inspection.
- [x] Assert that the skill validates version-2 `rollouts`, `parent_thread_id`, `thread.created`, and exactly one CLI-normalized initial user rollout from write-command JSON.
- [x] Add a focused assistant-before-bootstrap CLI case and a focused leading-emoji title contract assertion.
- [x] Add a focused CLI assertion that both `register --json` and `record-turn --json` return complete post-commit thread snapshots.
- [x] Preserve the existing assertion that `register --help` has no `--initial-prompt` option.

### Phase 3: Align documentation and generated output

- [x] Update `docs/ARCHITECTURE.md` sequence diagrams and prose to show write-result verification and no post-create read.
- [x] Keep spec 02 unchanged as the completed schema record; link this spec for the later orchestration refinement.
- [x] Regenerate `dist/agtask.skill` through the canonical packaging workflow.
- [x] Run scoped skill synchronization and verify source/runtime byte equality without modifying unrelated installed skills.

### Phase 4: Prove lifecycle and handoff behavior

- [x] Run automated tests before live task creation.
- [x] Run one standalone project-local prompt-free lifecycle proof from registration through bootstrap reconciliation, real-hook promotion, assistant capture, and finalization closure.
- [x] Verify parent lineage, exactly one creation rollout, exactly one canonical initial user rollout, and hook-owned assistant capture against exact ledger rows.
- [x] Retain the bundled harness log and structured lifecycle snapshot under `.integ/proof` as reproducible proof artifacts.
- [ ] Collect a multi-sample clean/fork timing benchmark, including a live one-shot branch if the active surface can force it safely. This is a performance follow-up, not a correctness blocker.

### Phase Dependencies

- Phase 1 depends on the completed version-2 contract in spec 02.
- Phase 2 depends on the exact wording and branch states chosen in Phase 1.
- Phase 3 follows source and test changes so generated artifacts are not edited manually.
- Phase 4 requires the canonical runtime skill and hooks to be installed and enabled, plus a Codex surface capable of clean and fork creation.
- A forced one-shot proof may be omitted only when the active Codex surface cannot expose that path; the implementation must still retain automated contract coverage for it.

---

## Validation and Completion

Automated validation:

- Run `python3 -m unittest discover -s tests -v`.
- Run the focused skill contract tests and confirm the fast-path ordering assertions.
- Exercise CLI fixtures for bootstrap-first, real-first, replay, mismatch, and concurrent retry behavior.
- Inspect the built `dist/agtask.skill` and installed runtime for byte equality with canonical source.
- Search active source and documentation for prohibited normal-path patterns: `show --id` in creation verification, `read_thread` in task creation, assistant `bootstrap`, v1 `activities`, and `register --initial-prompt`.

### Implementation Evidence

- `python3 -m unittest discover -s tests -v` passed all 24 tests, including prompt-free, one-shot, fork-ordering, ambiguous-result recovery, assistant-before-bootstrap, leading-emoji title, and default-pinning contract coverage.
- Standalone project-local integration proof 7 passed with child `019f6c53-eb33-7631-b7af-674865b2557d` and real turn `019f6c53-ed0b-7ea1-9343-0dc600528a1c`. The snapshot embeds suite 3 / scenario v3 metadata and proves the invoking parent ID, exact registration snapshot, one `thread.created` rollout, bootstrap-to-real user-event promotion, hook-owned assistant output, unchanged checkpoint prefixes, and final `done` closure rows.
- Canonical source, packaged `SKILL.md`, and installed runtime `SKILL.md` have the same SHA-256: `457db57b0c731a700796a5cb04d23b2af1a537670ec7774c24ee92f815ad5f08`. The generated archive SHA-256 is `0e8159eed06ea5034dde864d66b74f369706f11889c53e049d2ecb77d9956f17`.
- The active proof surface exercised the prompt-free clean path. One-shot and fork ordering are covered by executable contract tests; deterministic live one-shot/fork sampling remains the performance follow-up below.
- No multi-sample latency benchmark was run, so this implementation makes no median, slowest-case, or SLO claim. The verified structural change removes normal-path `show`, child `read_thread`, and completion waiting.

Manual validation:

- Confirm the link is usable immediately after real-ID creation and is labeled accurately before registration.
- Confirm a successful registration result contains exact child ID, parent ID, title, normalized summary, expected status, and one `thread.created` rollout.
- Force an ambiguous registration result and confirm a targeted read happens before any proof-gated retry or registration-partial report.
- Confirm the final user `record-turn` result contains exactly one initial user rollout whether the hook or bootstrap wins.
- Confirm assistant-before-bootstrap preserves exactly one user rollout and returns the later assistant-owned description and status.
- Force an ambiguous or malformed bootstrap result and confirm one identical retry, at most one targeted recovery read, and accurate verified-versus-unverified classification.
- Confirm prompt-send failure leaves a prompt-free tracked child at `todo` and writes no user rollout.
- Confirm title failure is reported without losing or downgrading a verified tracked result.
- Confirm normal handoff returns before assistant completion and the later `Stop` hook supplies the assistant rollout without parent backfill.

### Completion Criteria

- [x] Skill source, contract tests, architecture documentation, package, and installed runtime describe and execute the same fast-path contract.
- [x] Automated and live validation evidence is recorded and reviewed, including partial-state cases and exact ledger rows.
- [x] Timing claims in the implementation handoff distinguish measured results from projections and include sample count and environment.
- [x] Any app-server two-phase or project-cache follow-up is captured separately rather than expanded into this short-term change.

---

## Open Items and Risks

### Open Items

- [x] The active proof surface exercised prompt-free clean creation. One-shot fallback and fork ordering are automated-only in this implementation pass.
- [ ] Run a separate multi-sample timing study if quantitative handoff latency is needed; include clean, fork, and one-shot samples only where the surface can force each branch safely.

### Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
| --- | --- | --- | --- |
| One-shot child completes before registration, so the fail-open `Stop` hook misses the first assistant result | Med | Low | Register immediately before title or any read; prefer prompt-free creation; treat assistant recovery as a separate monitored workflow rather than normal-path backfill |
| A bootstrap write races the real user hook and creates duplicate user rollouts | High | Low | Reuse the spec-02 symmetric reconciliation contract and validate real-first/bootstrap-first live and in tests |
| Publishing the link before registration overstates success | High | Med | Label it `tracking pending`; only `register` JSON can promote the state to `tracked` |
| Removing `show` hides a malformed write response or weakens verification | High | Low | Validate the complete post-commit object returned by the write against explicit invariants and fail closed on missing or conflicting fields |
| A user bootstrap write commits but its process result is lost or malformed | High | Low | Retry the identical idempotent write once, then use one targeted error-path read and return an explicit unverified partial state if proof remains unavailable |
| Title mutation fails after the task is tracked | Low | Med | Keep title outside readiness, report the warning with the stable deep link and task ID, and allow a later title retry |
| Hooks are disabled or fail, so later assistant state is absent | Med | Low | Keep hook installation as an operational prerequisite and verify it in live acceptance; do not make normal creation wait on completion |
| Timing improvement is overstated from one warm trace | Med | High | Report structural call-count reduction plus multi-sample median/slowest measurements; avoid an unsupported fixed SLO |
| Project-ID caching returns a stale or wrong project | High | Med | Do not add caching in this spec; continue exact-CWD resolution and defer ownership/invalidation design to the app boundary |

### Simplifications and Assumptions

- Local CLI writes are retained even when they add a small amount of work because they preserve ledger invariants without a new command or schema change.
- Bootstrap receives the same complete prompt submitted to Codex and omits `--summary`, so both the explicit write and hook use the CLI's `summary_source()` and `normalized_message()` path.
- The user benefits more from an early accurate link and bounded tracking proof than from waiting for child completion.
- Normal creation is an orchestration workflow implemented by skill instructions and app/CLI calls, not a new long-running service.

---

## Outputs

- Archived feature record: `docs/specs/.archive/03-fast-tracked-task-handoff.md`
- Implementation sources: `skills/agtask/SKILL.md`, `tests/test_skill_contract.py`, `tests/test_cli.py`, `docs/ARCHITECTURE.md`
- Generated artifact: `dist/agtask.skill`
- Validation: standalone local skill `.integ/proof/7`, scenario suite 3, `lifecycle-create-directive-fin` v3
- PR created from this implementation: none

## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-07-16 14:33: Created the implementation-ready short-term handoff spec and reconciled the original timing proposal with the version-2 ledger contract (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - 3b555f807195bc9d7cdb7294e32227bdc418d47f)
- 2026-07-16 14:46: Implemented the fast path, preserved leading-emoji title normalization, synchronized the package and runtime, and recorded passing unit and live lifecycle evidence (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - 8471cd87ca2620fe8f03ae9d682ec76d22b14401)
- 2026-07-16 14:51: Corrected assistant-race validation to preserve raw-content-derived status, strengthened emoji-prefix assertions, and reran package/runtime sync plus external proof 7 (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - 8471cd87ca2620fe8f03ae9d682ec76d22b14401)
- 2026-07-16 14:57: Marked the implementation complete after restoring and passing the versioned project-local integration harness, then prepared the spec for archival (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - cb4da7b83b2b8624286f873f59477e786773a1a0)
- 2026-07-16 15:00: Aligned the versioned in-repo scenario manifest with the canonical external harness, recorded passing proof 9, and finalized archival evidence (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - cb4da7b83b2b8624286f873f59477e786773a1a0)
- 2026-07-16 15:01: Embedded suite and scenario metadata in canonical proof 10 and reconciled the archived evidence record (019f6c32-911e-7ff0-8a3f-8a5e795b6219 - cb4da7b83b2b8624286f873f59477e786773a1a0)
- 2026-07-16 15:08: Replaced the obsolete external/global integration convention with a dependency-free standalone local skill, bundled its runner and assertions, and recorded passing local proof 7 (019f690b-df2b-75b2-9139-835f220ae4ac - 470e6bf1d75174a61c3ff7222a0db7fbd47de3da)

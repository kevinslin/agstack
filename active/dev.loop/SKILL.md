---
name: dev.loop
description: Drive a development task through planning, execution, verification, and publishing.
dependencies:
- dev.review
- dev.shortcuts
- specy
---

# Dev Loop

## Setup
Do this only once per repo.
Ensure the `.agents/` folder is ignored in the repo (for example, add `.agents/` to `.gitignore`)

## Usage
User will ask you to run dev.loop. This is usually with either an existing design spec or a stated goal.  

If user gives you an existing spec - go straight to step 2 (Gather Context). Otherwise, start at step 1 (Plan).

If the task is straightforward, you can skip creating a spec and go straight to step 3.

If the user asks you to "check in after creating the spec" or uses similar wording, treat that as a pause point before implementation, not as permission to skip the immediate post-spec gather-context work. Unless the user explicitly says to stop before review, still complete the required spec review, ambiguity/gap analysis, and recommendation fold-in from step 2 before checking in.

In addition to running the whole dev.loop, users can also invoke an individual phase of the dev.loop by referring to it (eg. re-run the "verify" phase). An individually requested Verify phase never pushes; a full dev.loop run continues through the separate Push phase unless the user explicitly instructs not to push.

Whenever practical - use one or more subagents to run any given phase to preserve context

## Workflow Phases

### 1. Plan
- Use $specy to create a feature spec 
- Bias toward answering plan questions yourself; only ask the user when blocked or when user tells you to check with them.
- Ensure the plan includes explicit tests (prefer integration tests).
- List every test or observable outcome the user explicitly requested, the real
  execution boundary it must exercise, and its required infrastructure.
- Honor explicit autonomy and workflow preferences. Ask substantive product
  questions when needed, but do not introduce approval checkpoints for actions
  already authorized; never treat autonomy as permission to exceed task scope.
- Capture the plan prefix from the plan filename: `{YYYY-MM-DD}-{title-in-kebab-case}`.

### 2. Gather Context
- Trace the existing end-to-end lifecycle, including initialization and runtime.
  Identify unmet requested outcomes and unresolved assumptions before introducing
  another mechanism.
- Preflight infrastructure needed for explicitly requested integration proof
  before declaring the task executable. Identify unavailable clusters, runtime
  images, credentials, services, or host capabilities early.
- Record an acceptance-proof matrix mapping each requested outcome to its real
  test command, production boundary, prerequisites, and current status.
- Explicitly answer:
  - What ambiguities or gaps are still left?
  - Are there missing flow docs that, once created, would resolve those ambiguities?
- If there are questions for the user, ask them before continuing.
- If flow docs are missing, propose which flow docs should be generated (title, scope, and why each one resolves a specific gap).
- Summarize this phase in three sections:
  - `Ambiguities/Gaps`
  - `Questions for User`
  - `Proposed Flow Docs`
- After creating the spec, spawn subagent to critical review design doc with $dev.review skill and provide recommendations
- Apply correctness fixes and simplifications within the approved contract.
  Present changes to that contract as product decisions before applying them.
- If the user asked for a post-spec check-in, perform that check-in only after the review feedback and ambiguity summary are incorporated, unless they explicitly asked to stop earlier.

### 3. Execute
- Create a new branch for implementation unless given explicit instructions not to. If user explicitly asks for worktree, create worktree. If a plan branch exists, branch off it to keep the plan commit(s).
- Follow the plan steps in order and check off each task as it is completed in the plan file.
- Use red/green TDD.
- For each phase or milestone, run `@shortcut:precommit-process.md` then `@shortcut:commit-code.md` to commit that phase separately.
- **Always commit after each phase** (do not wait for user prompting). If precommit fails, fix issues and re-run before committing. If no precommit script exists, run the plan’s tests then commit.
- Maintain progress artifacts under `%ROOT_DIR/.agents/progress` (create the folder if it does not exist):
  - `%ROOT_DIR/.agents/progress/{prefix}-progress.md` for status updates, decisions, and blockers.
  - `%ROOT_DIR/.agents/progress/{prefix}-learnings.md` for mistakes, lessons, and adjustments.

### 4. Polish
- Gather session changes by reviewing changed files in the current worktree.
- Identify behavior changes, CLI/API changes, config changes, and workflow changes that need documentation.
- Update `README.md` so relevant behavior changes are documented.
- If `DESIGN.md` exists, update sections affected by the implementation.
- Confirm each meaningful change is reflected in docs, keeping updates specific and accurate.
- If flow docs exist, update relevant flow docs with meaningful changes, including config updates and sudocode details when significant logic changes.

### 5. Verify
- Run the tests specified in the plan and ensure they pass.
- Check features against validation plan and ensure existing tests pass
- Run every test the user explicitly requested and record its actual outcome.
  A skipped, failed, unavailable, or substitute test does not satisfy that
  acceptance criterion, even when the remaining suite is green.
- Confirm proof exercises the requested real boundary: rendered manifests are
  not a deployment, fixture processes are not production runtimes, and local
  execution is not a live cluster. Report the exact blocker when proof cannot
  be obtained; do not describe the requested verification as complete.
- If there are unstaged changes relevant to your current work, create a scoped local commit. Do not invoke `trigger:commit-code` here because it updates an existing PR after committing.
- Do not push, create or update a PR, or run post-push CI or review during Verify.

### 6. Push
- Do not treat push as optional due to caution, preference, uncertainty, “waiting for review,” or because the implementation already appears done. Only skip push when the user says so explicitly.
- Hard completion gate for any full dev.loop run with code changes:
  - do not send a final handoff until the branch is pushed and a PR URL exists
  - NEVER skip `trigger:push-pr` during Push unless the user explicitly instructs not to push.
  - open the PR as ready for review by default; never make it a draft PR unless the user explicitly asks for a draft
  - include the PR URL in the final handoff
  - if push or PR creation fails, report the exact command error and what retry was attempted, and treat the run as incomplete
- If the user asks a status question such as `did you push a pr?` and the truthful answer is `no`, do not stop after answering. Resume Push immediately and run `trigger:push-pr` unless the user explicitly told you not to push.
- Ensure the PR body includes manual testing steps with checkboxes.
- After push succeeds, spawn two subagents:
  - spawn `worker` subagent to verify CI for the pushed branch is green via `trigger:check-ci`.
  - spawn `a-review` subagent for critical review using the $dev.review skill 
- Wait for both subagents to complete. Address review feedback from coding agents and humans; apply fixes, re-run tests, push, and re-check CI.
- Notify the user when the work is ready.

## Important Reminders
- unless you require user input, don't stop until you finish EVERY phase of the dev.loop
- Verify is local-only; the separate Push phase includes push, CI check, and review. These are required for a full dev.loop run by default and are NEVER optional unless the user explicitly instructs not to push.
- When Push creates a PR, it should be a ready PR by default. Draft PRs require explicit user instruction.
- A dev.loop run that ends without a pushed branch and PR should be treated as incomplete unless the user explicitly said not to push.
- A final answer for a code-changing dev.loop run must include the PR URL, or explicitly state that the run is incomplete because push/PR creation failed. Never end a dev.loop run with only local branch or commit status.
- A passing aggregate suite never overrides an explicitly requested test that
  did not run or pass; name every outstanding acceptance-proof gap in the
  final handoff.

## Phase Overrides
Users can substitute any phase in the dev loop by mentioning they would like to override a particular phase with another set of instrctions. 

Example:
```
## Dev Loop Overrides
Override the following phases of the devloop

### Goal
Use dev.prd to create the goal

### Verify
Make sure that the acceptance criteria from dev.prd have been carried out
```

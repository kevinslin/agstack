---
name: fin
description: Finalize completed PR or local checkout work, or close a local review branch with nocheck. Use when explicitly invoked.
dependencies:
- ag-learn
- dev.llm-session
- dev.shortcuts
- dev.worktrees
- mem
- specy
---

# fin

Use this skill at the end of a task before the final user-facing report.
Linear follow-up is best effort: attempt it when available, but never block
finalization or mark it partial solely because Linear work could not be completed.

## Context Selection

Run `fin [context] [target]`.

- `gh`: finalize from a GitHub PR context. Use this when the task should land by merging the current remote PR or when the matching PR already merged and only cleanup/final verification remains. The original `fin` workflow maps to this context.
- `local`: finalize from a local checkout. Use this when the task should land directly from local git state without depending on GitHub PR state.
- `nocheck`: close the task's local branch and linked worktree without checking or changing any remote state. Use explicitly after reviewing someone else's code when the local review checkout is no longer needed; no landing or merge proof is required.
- Route explicit `nocheck` directly to the `nocheck` workflow below, before detached-HEAD handling, PR-target inference, or context auto-detection. Return after that workflow; every subsequent landing workflow, guardrail, and done checklist applies only to `gh` / `local`.
- `[target]`: optional for `gh` only. Accept a PR number, PR URL, or branch name. Examples: `fin gh 85117`, `fin gh https://github.com/owner/repo/pull/85117`.
- If the current checkout is detached `HEAD`, treat that as a preflight issue, not a valid finalization state. Create a short-lived local branch from the current commit before auto-detecting context, checking mergeability, or attempting worktree cleanup.
- If the argument is `gh`, `local`, or `nocheck`, respect it throughout the flow. Do not silently switch later just because repo state would make the other path easier. Never auto-detect `nocheck`.
- If `gh` has an explicit `[target]`, lock that PR target before current-branch detection. Use the target PR as the source of truth for state, mergeability, comments, checks, spec matching, merge, and automation cleanup.
- If the user omits `[target]` but the immediately preceding active heartbeat or delayed-merge instruction names exactly one PR and the user asks to merge, finalize, ignore a waiting period, or ignore a proof gate, treat that PR as an explicit `gh` target after one live PR-state check. Report the target source as `heartbeat automation`.
- If the user omits `[target]` but the immediately preceding task in the same thread completed or repaired exactly one PR, such as after `trigger:fix-pr`, `trigger:fix-pr-conflict`, or a PR-specific babysit/CI run, treat that PR as an explicit `gh` target after one live PR-state check. Report the target source as `active task context`. If the current checkout points at another branch or PR, mention the mismatch and ignore the unrelated checkout for PR state, spec archival, merge, automation, and cleanup decisions unless it blocks local cleanup.
- If an explicit `gh` target does not match the current branch, do not silently fall back to the current branch's PR. Either run the remote-PR finalization path for that explicit target, or stop with a target mismatch before any spec archival, branch cleanup, or merge.
- If the argument is omitted, detect the context from the current branch before any archival or landing work:
  - Choose `gh` when the current branch has an open or already-merged PR that corresponds to the branch being finalized.
  - Choose `local` when the current branch has no matching PR and the work should land directly from local git state.
- Treat heartbeat-derived or active-task-derived PR targets as explicit `gh` targets, not as current-branch auto-detection.
- If the argument is present but not one of `gh` / `local` / `nocheck`, stop and ask the user which context to use.
- Report whether the finalization context was explicitly provided or auto-detected.
- Before reporting any PR status or blocker, print one target identity line: `Target: PR #<number>, branch <headRefName>, source=<current checkout|explicit user PR|heartbeat automation|active task context>`. When multiple PRs have been mentioned in the session, prefix every PR-specific state claim with the PR number.

## `nocheck` Context Workflow

An explicit `fin nocheck` authorizes deletion of the exact disposable local
branch even when its commits are not merged. It does not authorize discarding
uncommitted work or deleting a remote branch. A request to add or explain this
context does not itself invoke cleanup.

1. Lock the local target from the current task's recorded review checkout and
   branch, or the current checkout when no separate task checkout exists. Read
   local Git state to confirm the repository, absolute worktree path, branch,
   and full HEAD OID. Report `Target: local branch <branch>, worktree <path>,
   context=nocheck (explicit)`. If the task's checkout differs from the shell's
   checkout, use the task's target and preserve the unrelated checkout. Stop on
   ambiguity, detached HEAD, or identity drift; do not create a temporary branch.
   For a branch checked out nowhere, inspect its local ref from a retained
   checkout and skip worktree-only checks. A missing path still registered as a
   worktree is a blocker; do not prune it to make cleanup pass.
2. Use local state only. Do not query GitHub, PRs, CI, reviews, downstream PRs,
   mergeability, or the remote default branch. Do not fetch, pull, push, merge,
   rebase, delete remote refs, or run `check_default_branch.py` or
   `$dev.worktrees cleanup-landed`. Set `GIT_NO_LAZY_FETCH=1` for Git commands so
   a partial clone cannot fetch missing objects implicitly; missing local data
   is a blocker. Do not run network-capable hooks or fall back to a landing flow.
3. Read repository preservation guidance and any matching `~/.fin.yaml` entry
   using the normalized primary checkout root. Apply local file-preservation
   instructions before removal; skip landing, deployment, and remote hooks.
   Stop when malformed or ambiguous config could hide preservation requirements.
   Inspect tracked, untracked, and ignored files with
   `git -C <target> status --short --untracked-files=all --ignored`. Preserve
   review notes, specs, credentials, and other wanted artifacts outside the
   target without overwriting existing files or exposing secrets, and verify
   the copies. A dirty tracked or untracked state blocks
   removal until separately resolved; do not stash, reset, clean, or force-remove
   it. Ignored files may be removed with the worktree only when known to be
   disposable generated output; preserve unknown files instead.
4. Protect the primary checkout directory, locked worktrees, unrelated branches,
   and local trunk branches (`main`, `master`, and any other default/trunk branch
   identified by local repository guidance or cached `refs/remotes/origin/HEAD`).
   Cached refs are local evidence only; do not refresh them or require an origin
   remote to exist. If the target might be a trunk branch, stop for clarification.
   Record a retained checkout outside the target before removing a linked
   worktree. If the target is in the primary checkout, keep that directory and
   switch to an existing, locally identified safe branch without force or remote
   guessing (`git switch --no-guess <retained-branch>`). Stop if a safe switch
   would require fetching or changing unrelated work.
5. Immediately recheck the target branch's full OID and, for a linked worktree,
   its branch, HEAD OID, registration, lock state, and file-preservation
   conditions. From the retained checkout,
   remove only the clean linked target using the ordinary removal path in
   `$dev.worktrees`: `git -C <retained> worktree remove <absolute-target-path>`.
   Never use `--force`, recursive path deletion, or global prune. Skip removal
   for a primary checkout or a branch already checked out nowhere.
6. Recheck the local branch OID and confirm no worktree has it checked out.
   Delete only that branch with `git -C <retained> branch -D -- <branch>`.
   This explicit `nocheck` authorization replaces the merged-branch requirement
   for this step only; do not fabricate a landed commit or weaken the `gh` /
   `local` cleanup gates. If the branch moved, stop and preserve it.
7. Verify the branch is absent and, for linked-worktree cleanup, both the target
   path and its worktree registration are absent. If only removal succeeded,
   report partial local cleanup and preserve the recorded branch/OID for a retry.
   Report the local cleanup result, retained checkout, and preserved artifact
   paths, followed by `Remote state was not checked or changed.` Do not claim a
   PR landed or a remote branch was deleted. Skip spec archival, issue completion,
   automation changes, retrospective publishing, and the landing checklist below.

## Shared Workflow (`gh` / `local` only)

1. Confirm finalization preconditions
- Use this flow only when the requested scope is complete.
- If work is partial or blocked, do not archive specs and do not present the task as finished.
- Resolve the repository's origin main branch before any spec archival, landing, merge, or cleanup. In this skill, `main` means the default branch of the repository addressed by `origin`; do not assume the literal branch name is `main`.
  - For `gh`, query the target repository's authoritative default branch and the locked PR's `baseRefName`.
  - For `local`, resolve and verify the default branch associated with `origin`, using the remote provider when available or `refs/remotes/origin/HEAD` as a fallback. If the origin main branch cannot be determined unambiguously, stop.
  - Compare canonical short branch names. When a local fallback returns `refs/remotes/origin/<name>` or `origin/<name>`, retain the raw result as evidence and pass only `<name>` to the gate.
  - Pass the two resolved names through the mandatory machine gate before any spec archival, landing, merge, cleanup, or full-finalization wording:

    ```bash
    python3 ./scripts/check_default_branch.py \
      --context gh \
      --repository-default-branch "<resolved-origin-main>" \
      --target-base-ref "<locked-target-base-ref>"
    ```

    Resolve `./scripts/check_default_branch.py` relative to this `SKILL.md`, replace the quoted placeholders with the resolved values, and use `--context local` for local finalization. Do not replace this command with a manual comparison or a same-named repository script.
  - Continue only when the command exits `0` and its JSON reports `status: "pass"`, `matches: true`, and every `allow` field as `true`. Retain that JSON as finalization evidence. Treat a nonzero exit, malformed output, or any other result as a hard blocker.
  - Rerun the gate if the locked target, repository default branch, or target base ref changes. The latest passing record is the only valid authorization for the finishing actions.
  - A mismatch blocks intermediate, stacked, release, and feature branches. Use the script's retarget-or-create-PR message in the report.
  - If the PR already merged into a non-main branch, the gate still fails: stop before archival or cleanup, report that it did not land in origin's main branch, and do not describe it as fully finalized.
- Before archiving any spec or attempting to land the change, determine the current branch, whether it is attached to a linked worktree, and where the non-worktree `main` checkout lives.
- Read repository guidance for ignored-file preservation and verification
  boundaries even when no `~/.fin.yaml` exists. Treat checked-in product specs
  as deliverables, not disposable task artifacts, unless their own workflow
  explicitly requires archival.
- Check `~/.fin.yaml` for repo-specific finalization instructions before landing or cleanup. If the file exists, parse entries shaped as `workspace: [{path: ..., instructions: ...}]`.
- If `~/.fin.yaml` exists but cannot be parsed, do not treat the parse failure as "no hooks". Report the parser error separately and inspect the raw file. Continue only when the raw content is clearly non-executable, unambiguous context; if it might contain commands, hooks, destructive instructions, or ambiguous cleanup requirements, stop before spec archival, landing cleanup, or linked-worktree removal and report the malformed config as the blocker.
- Match `workspace[].path` against the normalized non-worktree checkout root for the branch's repository, not against a transient linked worktree path. Resolve symlinks and trailing slashes before comparing.
- If a matching `~/.fin.yaml` workspace entry exists, record its `instructions` and apply them after the PR merge / already-merged confirmation or local landing succeeds, but before removing any linked worktree. This preserves ignored or untracked files that may need to be copied out of the soon-to-be-removed worktree.
- Also treat matching `~/.fin.yaml` instructions as routing context for active spec discovery. If the instructions mention a `$specy`, `$mem`, or `.mem` artifact root, derive candidate docs roots from that instruction before falling back to the default docs root.
- If `~/.fin.yaml` is missing or no workspace entry matches the non-worktree checkout root, state that no repo-specific final hooks applied and continue.
- If the checkout is detached `HEAD`, create a temporary local branch from the current commit first. Prefer the repo's normal task-branch prefix when one exists, otherwise use a short `codex/` branch name derived from the task.
- After converting detached `HEAD` into a named branch, lock that branch identity for the rest of the run. Do not continue finalization from anonymous detached state.
- When the user omitted the context, lock the detected context once and use it for the rest of the run. Do not re-detect after archiving or mid-landing.
- When the user provided, or the heartbeat handoff or active task context implied, an explicit PR target, lock that PR number, head branch, and target source once. Do not replace it with the current checkout's PR because the current checkout is different or easier to operate from.
- In `gh` mode, apply the downstream pull request protection below to the locked repository and exact PR head branch before merging, enabling auto-merge, or deleting its remote branch.
- Do not silently switch contexts after selection. If the user requested `gh`, do not fall back to local-only landing. If the user requested `local`, do not silently land via PR merge just because a PR exists.
- For `gh` without an explicit target, identify the current PR and check its state before testing mergeability or attempting any merge command.
- For `gh` with an explicit target, identify that target PR directly with GitHub before consulting current-branch PR state. If the current checkout points at another PR, report the mismatch in the target identity line and ignore the other PR unless it blocks local cleanup.
- For `gh`, identify any active PR babysit/watch automation for the target PR or branch when automation state is visible. Record its id so it can be updated or deleted after the PR lands.
- For `gh`, entering `auto-merge pending` itself authorizes the monitoring needed to finish `$fin`. Do not require a second user request before creating a heartbeat or falling back to a foreground watch. Monitoring never waives the locked target identity, checks, reviews, conflicts, or any other blocker.
- If the task includes a requested external notification after green CI, such as Slack or another chat notice, track that notification as a separate finalization gate from PR mergeability and CI. Check notification prerequisites when feasible, such as required local credential files or configured CLIs, and record any missing prerequisite as a notification blocker, not as a CI failure.
- If the target PR is already merged into the verified origin main branch, treat the PR landing precondition as satisfied and skip mergeability repair. Continue with any matching spec archival, worktree cleanup, local `main` refresh, and retrospective.
- For `gh`, when the target PR is still open, confirm it is mergeable against the verified origin main branch.
  - If GraphQL or `gh pr view` reports `UNKNOWN`/indeterminate mergeability while checks and reviews otherwise look green, poll the REST pull-request endpoint once or twice for `mergeable` and `mergeable_state` before invoking conflict repair. Treat REST `mergeable: true` with `mergeable_state: clean` as the mergeability confirmation. If repeated REST results remain `null`/unknown, record the state as bounded-indeterminate and allow the merge attempt to continue when the exact PR head identity is known and there is no positive evidence of conflicts or unmergeability. Treat the repository merge operation as the authoritative final mergeability check.
- For `local`, confirm the current branch is mergeable into the verified local origin main branch.
- If the `gh` flow is blocked only by base-branch conflicts, run `trigger:fix-pr-conflict` against the locked target PR and let it try to restore a clean merge state.
- If the `gh` flow is blocked by broader PR issues, or conflict repair needs a fuller pass, run `trigger:fix-pr` against the locked target PR.
- If the `local` flow is blocked only by trunk drift, run `trigger:sync-branch` or otherwise rebase the current branch onto the merge target before retrying the check.
- Continue after mergeability is confirmed, the matching PR is already merged, or a `gh` target meets the bounded-indeterminate conditions above. If repair cannot clear positive evidence of conflicts or unmergeability, stop and report the blockage instead of archiving the spec or landing the change.

### Explicit Blocker Override

- When finalization stops on named non-conflict blockers and the user explicitly says to merge or land while ignoring those blockers, treat that response as an auditable override limited to the blockers already reported for the locked target.
- Restate the target identity and the exact waived blockers before proceeding. Do not infer an override from a generic approval, an earlier broad permission, silence, or a request that does not clearly authorize landing.
- An override may waive failing or pending checks, review/proof/approval gates, waiting periods, and incomplete-spec landing gates. It does not waive a missing or failed default-branch gate, a non-main merge target, an unmergeable/conflicting target, a target mismatch, unknown commit identity, dirty-worktree preservation, malformed or failed final hooks, missing repository permission, or post-merge verification and cleanup.
- Keep incomplete specs and milestones active and unarchived. Do not mark them complete merely to satisfy the normal archival-before-landing order. Record the spec exception in the final report.
- In `gh` context, re-confirm the exact PR head identity and require no positive evidence of conflicts or unmergeability, then use a repository-supported administrator or maintainer override merge. If merge commits are disallowed, retry once with the supported squash method. An indeterminate mergeability value alone does not prohibit the override; never use the override to merge a conflicting or explicitly unmergeable head.
- Preserve the waived state in the final report: who authorized it, which blockers were ignored, whether an administrator merge was used, and which spec artifacts intentionally remained active.

### Downstream Pull Request Protection

- Before merging or enabling auto-merge, lock the target PR's exact repository, head branch, and base branch. Discover open PRs that depend on that head branch with `gh pr list --repo <owner/repo> --state open --base <head-branch> --limit 1000 --json number,url,headRefName,baseRefName`.
- Read the repository's automatic branch deletion policy with `gh api repos/<owner/repo> --jq '.delete_branch_on_merge'`. Treat a failed, incomplete, or ambiguous dependent-PR or deletion-policy lookup as a blocker; never assume a branch is safe to delete.
- If no open PR uses the locked head branch as its base, proceed with normal merge and remote branch cleanup.
- If dependent PRs exist and `delete_branch_on_merge` is `false`, merge without `--delete-branch`, preserve the remote head branch, and report the dependent PR numbers and retained branch. The parent's local branch or worktree may still be cleaned up after normal landing proof.
- If dependent PRs exist and `delete_branch_on_merge` is `true`, stop before merging or enabling auto-merge: repository policy would remove their base even without `--delete-branch`. Ask whether to retarget every dependent PR to the parent's verified base, or leave the parent unmerged.
- Retarget a downstream PR only with explicit user authorization. Run `gh pr edit <dependent-number> --repo <owner/repo> --base <parent-base>` for each authorized dependent, then repeat the exact-base discovery and require zero remaining open dependents before merging or enabling auto-merge.
- Immediately before any later explicit remote branch deletion, repeat the exact-base dependent-PR query. Delete only when it succeeds and returns zero open dependents; otherwise retain the remote branch and report the open PRs or lookup blocker.
- Do not change repository settings, close a downstream PR, or infer retargeting approval from a general request to merge, finalize, or clean up.

### PR Automation Lookup

- Resolve matching automation by exact automation id first, then by the locked repository, PR number, and head branch. Classify ordinary babysit/watch automation separately from a `fin: auto-merge ...` heartbeat; the latter is owned exclusively by the auto-merge lifecycle in step 4.
- Bound the automation service lookup to one request and at most 30 seconds of waiting. Do not let an unavailable automation service stall finalization indefinitely.
- If the service lookup errors or times out, search `${CODEX_HOME:-$HOME/.codex}/automations` for the exact automation id, PR number, or head branch. Treat this as read-only fallback evidence; never delete automation files directly.
- When the fallback finds a persisted ordinary babysit/watch automation, retry one service lookup/delete operation using its exact id. For a `fin: auto-merge ...` heartbeat, retry lookup or update only; never delete it through this generic cleanup path. If the allowed operation still fails, report automation cleanup as blocked with the id and error.
- When neither the bounded service lookup nor the exact registry search finds a match, report that no matching persisted automation was present and name the evidence used. Distinguish this from a service-only lookup failure.

### Linear Issue Lookup (Best Effort)

- Read `~/.agents/profile` directly. Treat the profile as work only when it contains a trimmed, non-comment line exactly equal to `name=work`. For a non-work profile, skip Linear unless the user or current task context explicitly identifies a Linear issue to finish.
- If the profile or active thread id is unavailable, skip Linear with a brief reason and continue finalization.
- For a work profile, resolve the active Codex thread id from the current app/session context, using `dev.llm-session` when needed. Use the installed `linear:linear` connector skill and its connected Linear tools; do not use `linear-cli` or a browser fallback.
- Let `thread_link` be the exact deep link `codex://threads/<thread-id>`. Search with `list_issues(query=thread_link, assignee="me", includeArchived=true)` first. If that produces no exact match, run one unscoped `list_issues(query=thread_link, includeArchived=true)` search and follow its pagination until exhausted. If the connector cannot exhaust the candidate set, treat lookup as ambiguous instead of guessing.
- Treat search results only as candidates because Linear search is fuzzy. Keep bulk connector payloads out of the transcript: parse them in the tool-composition layer and emit only candidate ids needed for verification. For every candidate whose complete description is unavailable or marked truncated, call `get_issue` before comparison. Retain only issues whose complete description contains `thread_link` exactly, and expose only each exact match's id, team, status, status type, and URL.
- Accept only an exact `thread_link` match or an issue the user explicitly identified as the ticket for this task. Do not infer linkage from a search hit, similar title, branch name, PR number, assignee, or project.
- Treat statuses with type `backlog`, `unstarted`, or `started` as pending. Treat `completed` and `canceled` issues as terminal and leave them unchanged.
- When exactly one linked pending issue exists, lock its issue id and team for the rest of the run. When no linked pending issue exists, record that Linear completion is not applicable and continue.
- When more than one linked pending issue exists, do not update any of them. Record the matching issue ids as a non-blocking ambiguity note and continue finalization without guessing.
- If the connector is unavailable, unauthenticated, errors, times out, or returns an ambiguous result, skip the remaining Linear work and report the reason briefly. Do not wait for reauthentication, require the user to repair Linear, or retry through another client. Continue landing, cleanup, retrospective, and completion reporting.

2. Resolve the active spec
- Build an ordered list of candidate docs roots:
  - First, use `DOCS_ROOT` when it is configured.
  - Next, if the matching `~/.fin.yaml` instructions mention an absolute artifact root for `$specy`, `$mem`, or notes, use that configured root directly. Do not infer or append `/main`; aggregate `$mem` roots already name the complete managed root.
  - Finally, default to `./docs`.
- Only use candidate roots that exist or whose parent exists and is clearly the intended workspace artifact root. Report the selected spec root when a matching spec is found.
- Follow `specy`'s layout rule for each candidate root: active specs live directly under `$DOCS_ROOT/specs/`.
- Only treat files directly under a candidate `$DOCS_ROOT/specs/` as active specs. Ignore files already under `$DOCS_ROOT/specs/.archive/`.
- Also support folder specs when the workspace uses a folder schema such as `specs`: an active spec folder lives directly under a candidate `$DOCS_ROOT/specs/<spec-slug>/`, with optional sidecars such as `milestones/`, `flows/`, `reports/`, `cook/`, `checklist.md`, or `data/`. Treat the folder as the active spec unit.
- If the completed work is a milestone or sidecar inside an active folder spec,
  do not archive the parent folder unless the parent spec itself is complete. If
  sibling milestones remain, record that the milestone landed and leave the
  parent folder spec active.
- If multiple active specs exist across candidate roots, archive only the one that directly matches the completed task and leave unrelated active specs untouched.
- If no active spec exists for this task, state that explicitly and continue.

3. Mark the spec complete and archive it
- Update the active spec so its status clearly reflects completion before moving it. For folder specs, update the folder's `spec.md`.
- For a completed milestone or sidecar inside an otherwise active folder spec,
  mark or report only that milestone as complete when the file has a clear
  status field or checklist. Do not move the parent folder into `.archive/`
  until the whole folder spec is complete.
- Preserve the existing filename for single-file specs and the existing folder name for folder specs.
- Move the completed spec to `$DOCS_ROOT/specs/.archive/`, creating the directory if needed. For folder specs, move the whole folder so sidecars such as `checklist.md` and `data/` stay with the completed spec.
- Follow `specy`'s convention exactly: when a single-file spec is complete, move it to `$DOCS_ROOT/specs/.archive/` and keep the same filename.
- Do not delete completed specs.

### Deterministic Local Cleanup

- Use `$dev.worktrees cleanup-landed` as the only executor for destructive local worktree and local-branch cleanup during `fin gh` / `fin local`. The explicit `nocheck` workflow owns its separate ordinary removal path. Do not reproduce the landed executor's reset, clean, removal, orphan recovery, or branch deletion steps manually.
- Before invoking it:
  1. confirm the PR or local change actually landed;
  2. run every matching `~/.fin.yaml` final hook;
  3. refresh or verify the local base ref and prove it contains the landed commit;
  4. inventory ignored or untracked files required by repository guidance,
     including `.env` files and root or nested `node_modules`; preserve them in
     the retained checkout without exposing secrets, overwriting existing
     content, or installing dependencies; and
  5. record the exact target worktree path, branch or detached state, and expected pre-cleanup HEAD.
- When checking preserved dependency graphs, invoke installed tools directly if
  package-manager scripts might reconcile workspace state or install packages.
  Stop before cleanup if required preservation or safe verification fails.
- Pass the exact full commit OIDs, refreshed local base branch, target identity, and actual merge mode to `$dev.worktrees cleanup-landed`.
- Require its dry run to report `ready` or `noop`, then rerun the exact command in execute mode.
- Treat `blocked`, `partial`, a nonzero exit, identity drift, or failed postconditions as a finalization blocker. Preserve its journal and rerun the exact command after resolving the blocker.
- Require final status `complete` or `noop`, with the target path, worktree registration, and local branch absent and the base still containing the landed commit.

## `gh` Context Workflow

4. Merge the PR
- Before running a merge command, check the target PR state with GitHub. If the PR is already `MERGED`, do not run `trigger:merge-pr`; record the merge commit or merged-at details when available and proceed as an already-landed PR.
- Before any merge command or auto-merge request for an open PR, complete Downstream Pull Request Protection using the locked repository and head branch. Pass `--delete-branch` only when its current exact-base query proves there are no open dependents.
- If the PR is not already merged and the target PR belongs to the current branch, run `trigger:merge-pr` immediately after the matching spec has been marked complete and archived.
- If the PR is not already merged and the explicit target PR does not belong to the current branch, use a target-aware remote merge for that PR, such as `gh pr merge <target>`, after the matching spec has been marked complete and archived. Do not use current-branch merge shortcuts for a different PR.
- Under an explicit blocker override, skip the archival prerequisite only for incomplete matching specs, leave them active, and use the target-aware override merge defined above.
- Treat the merge as part of finalization, not a follow-up option.
- If direct merge is rejected because repository policy requires auto-merge, and checks/reviews are otherwise green, enable repository-supported auto-merge for the locked target PR instead of treating the rejection as a terminal merge failure.
- After any successful auto-merge enablement, query the target PR for `autoMergeRequest`, `state`, `mergedAt`, `mergeCommit`, `mergeStateStatus`, and status checks.
- Treat `autoMergeRequest` present with the PR still `OPEN` as `auto-merge pending`, not as `blocked`, while checks remain green and no explicit cancellation or failing required check is present.
- Treat `auto-merge pending` as a nonterminal `$fin` state. Do not describe finalization as partial or complete, close or archive the task, send a terminal notification, run post-merge cleanup, or return a terminal final report while the locked PR remains in this state.
- As soon as the first live query confirms `auto-merge pending`, create or update exactly one dedicated thread heartbeat named `fin: auto-merge <owner>/<repo>#<number>` before beginning any bounded foreground polling. Reuse an existing exact match instead of creating duplicates. Use the first-class `automation_update` app tool: search the available tools for that exact capability when it is not already loaded. Do not infer that automation is unavailable merely because `${CODEX_HOME:-$HOME/.codex}/automations` is absent or has no matching entry, and do not substitute a standalone cron automation.
- Require the heartbeat to target the same `$fin` task so it can resume the deferred workflow. Store the locked repository, PR number and URL, base and head branches, exact head SHA, merge method, `autoMergeRequest.enabledAt`, the deferred `fin` stage, and instructions to query live state and resume at step 5 only after verified merge. Schedule its next wake promptly and keep it active while the same head remains safely pending.
- After heartbeat creation, the current wake may continue polling the locked PR for a bounded window. If the PR becomes `MERGED`, verify `mergedAt` and `mergeCommit` and continue with normal post-merge work. Otherwise report only a nonterminal monitoring handoff with the heartbeat id and next wake; keep `$fin` active and do not call the handoff partial finalization.
- On every heartbeat wake, query the locked PR live for `autoMergeRequest`, `state`, `mergedAt`, `mergeCommit`, `mergeStateStatus`, head SHA, and required checks. While the same head remains `OPEN` with auto-merge present and no terminal blocker, keep the heartbeat active, report `auto-merge pending`, and leave post-merge cleanup, Linear completion, and full-finalization wording deferred.
- When a heartbeat wake observes live `MERGED` state with non-empty `mergedAt` and `mergeCommit`, mark the heartbeat as post-merge/resuming and resume this workflow at step 5 in the same wake. Do not delete the heartbeat yet. Delete it only after steps 5-9 reach a terminal post-merge outcome, including exact reporting of any post-merge blocker, so a merge cannot strand unfinished refresh, cleanup, Linear, or retrospective work. If the auto-merge request is removed or cancelled before merge, the head changes unexpectedly, a required check fails, or conflicts appear, pause the heartbeat as blocked without cleanup and report the exact evidence.
- If the `automation_update` capability is genuinely absent after tool discovery, or heartbeat creation/update fails, continue automatically with a foreground watch instead of ending the run. No additional user request is required. Report the automation error as monitoring evidence, but do not treat heartbeat unavailability as a terminal or partial-finalization condition. Retain the locked repository, PR number, head branch, and exact head SHA; poll the same PR live with no more than 60 seconds between checks; and publish one concise progress update at least every 60 seconds.
- During a foreground watch, query `autoMergeRequest`, `state`, `mergedAt`, `mergeCommit`, `mergeStateStatus`, head SHA, and required checks on every poll. Continue until the locked head is `MERGED` with non-empty `mergedAt` and `mergeCommit`, then resume at step 5. Stop only for a terminal blocker: the auto-merge request is removed or cancelled, the head identity changes, a required check fails, conflicts or unmergeability appear, or live polling can no longer continue. Report the exact blocker and preserve deferred cleanup. Never infer or use an administrator, approval, or blocker override from a request to watch.
- Treat auto-merge as blocked only when GitHub reports the auto-merge request was removed/cancelled, a required check fails, conflicts appear, or the PR is otherwise no longer mergeable.
- If the merge command reports that the local branch cannot be deleted because it is still attached to a linked worktree, check whether the remote PR actually merged before treating the step as failed.
- If `gh pr merge --delete-branch` fails only in its implicit post-merge branch switch and pull, such as `error: cannot pull with rebase: You have unstaged changes` on a checkout with unrelated dirty files, do not treat that as a merge failure and do not stash or discard the dirty files. Confirm the PR is `MERGED` remotely, then complete the step-5 refresh with `git fetch <remote> <base>` followed by `git merge --ff-only <remote>/<base>`; a fast-forward is safe alongside dirty files the landed commits do not touch. The pre-refresh working tree may transiently look as if the landed feature was reverted; that is the stale local base, not lost work.
- When the PR merged remotely but local branch deletion failed only because of the linked worktree attachment, treat that as a successful merge followed by incomplete cleanup and continue with the deterministic cleanup script from a retained checkout.
- If there is no matching PR to merge, state that explicitly instead of claiming the task fully landed.
- For an explicit target PR that is not checked out locally, skip local branch/worktree cleanup unless the target branch is present in a local worktree or the user explicitly requested cleanup. It is acceptable to merge the remote PR, refresh local `main`, delete matching ordinary babysit/watch automation, and report that no local target checkout cleanup was applicable. Retain any `fin` auto-merge heartbeat until the terminal post-merge outcome.

5. Refresh and verify the local base ref
- Before destructive cleanup, run any matching repo-specific final hooks from `~/.fin.yaml`. If a hook fails, stop and preserve the worktree and branch.
- After the PR merges, or after confirming it was already merged, update the local base ref before cleanup. Run this refresh from a retained checkout, never from the soon-to-be-removed worktree.
- If the target PR was explicit, heartbeat-derived, or active-task-derived and the non-worktree checkout is on an unrelated active branch, prefer a non-switching base-ref refresh before checking out `main`: run `git fetch <remote> <base>:<base>` only when `<base>` is not checked out in any worktree, then confirm containment with `git merge-base --is-ancestor <mergeCommit> <base>`.
- If the non-switching base-ref refresh is rejected because `<base>` is checked out elsewhere or the ref cannot fast-forward, fall back to the normal checkout-and-pull path when that is safe. Otherwise, stop with a local-main refresh blocker.
- Do not use the non-switching base-ref refresh for `local` landing flows that need to merge the completed local branch into `main`.
- Check out `main` if needed and if the non-switching base-ref refresh path was not used.
- For the normal checkout path, pull or otherwise fast-forward `main` to `origin/main`.
- Confirm the local `main` HEAD, or the refreshed local base ref when the non-switching path was used, contains the PR merge commit before any local worktree or branch deletion.
- Delete or cancel any ordinary PR babysit/watch automation that was tracking the now-merged PR. Explicitly exclude the `fin: auto-merge ...` heartbeat: keep it in post-merge/resuming state until steps 5-9 reach a terminal post-merge outcome, then delete it through the step-4 heartbeat lifecycle. If an allowed automation operation fails, report the exact blocker instead of leaving silent stale state behind.
- If local base refresh fails because the retained checkout has unrelated dirty changes, use the non-switching path when safe. Otherwise stop before cleanup and report a partial terminal state: PR landed, worktree and local branch preserved, automation cleanup completed if safe, and local base not verified.
- If the local `main` refresh fails for any other reason, stop and report the exact git error instead of claiming the task is fully finalized.

6. Run deterministic local cleanup
- If the PR head branch has a linked worktree, invoke `$dev.worktrees cleanup-landed` with that exact path, PR head branch, PR head SHA, refreshed base ref, merge commit, and actual merge mode.
- If the local PR branch exists but is checked out nowhere, invoke `$dev.worktrees cleanup-landed` in branch-only mode with the same branch/head/base/landing proof.
- If an explicit target PR has no matching local worktree or local branch, report that local cleanup is not applicable; do not manufacture a path or delete a similarly named branch.
- If `gh pr merge --delete-branch` already removed the remote branch but could not remove a linked local branch, do not retry the merge. The cleanup script owns the remaining local transaction.
- Remote branch verification or deletion remains a separate GitHub/Git transport step. Do not add network mutations to the local cleanup script.
- Preserve a remote branch that remains the base of an open downstream PR even when its local branch and worktree have been safely removed.

## `local` Context Workflow

4. Land the change from the local checkout
- Do not require a GitHub PR for this flow.
- Before merging, make sure the current branch is committed and clean. If it is not, use `trigger:commit-code` first.
- Perform the landing merge from the non-worktree `main` checkout when possible, not from an attached feature worktree.
- Fetch and reconcile `main` before merging when the repo has a remote, but do not discard the completed work while doing so.
- Merge the completed branch into local `main`. Use a non-fast-forward merge unless the user explicitly requested a different merge style.
- If the completed work is already on `main`, do not fabricate a merge commit; instead verify that `main` already contains the intended change set and continue.
- If a remote is configured and pushing `main` is appropriate for the repo, push the updated `main` after the local merge. If the flow is intentionally local-only, state that explicitly in the report.

5. Verify the local base and run final hooks
- After the local merge succeeds, confirm the local base points at the landed result before destructive cleanup.
- Check out `main` if needed.
- Confirm the local `main` HEAD includes the merge commit or direct commit that landed the completed work.
- If the flow included pushing `main`, confirm the pushed remote ref contains the landed commit too.
- Run any matching repo-specific final hooks from `~/.fin.yaml`. If verification or a hook fails, preserve the worktree and branch and report the exact blocker.

6. Run deterministic local cleanup
- If the completed branch has a linked worktree, invoke `$dev.worktrees cleanup-landed` with its exact path, branch, recorded head, local base ref, landed commit, and actual merge mode.
- If the completed local branch exists but is checked out nowhere, invoke `$dev.worktrees cleanup-landed` in branch-only mode.
- The script deletes only the proven local branch. If a corresponding remote branch still exists and repository policy permits cleanup, delete it separately only after local base verification and successful local cleanup.
- If neither a matching linked worktree nor local branch exists, require a cleanup dry run to report `noop` or state that no local cleanup was applicable.

## Linear Completion (Best Effort)

7. Attempt to complete the linked Linear issue
- Run this step only after the selected landing flow and its required local `main` refresh or verification have completed. Do not complete the issue while a PR is merely auto-merge pending or while finalization is in a partial local-cleanup state.
- If the user explicitly instructed that the linked issue remain open, preserve it and report that override.
- For the single locked pending issue, list the issue team's current statuses through the Linear connector and resolve a status whose type is `completed` live. Prefer the case-insensitive name `Done` when multiple completed statuses exist; if no unique destination can be resolved, leave the issue unchanged and report the ambiguity.
- Update the locked issue to the resolved completed status, then read it back and verify the issue id, team, and status type `completed` before claiming success.
- If the update result is ambiguous, read the locked issue once before retrying. Never create an issue during `fin`, never complete an issue that was not locked during lookup, and never bulk-complete multiple matches.
- If no linked pending issue was found, state that no Linear update was needed. If a linked issue was already completed or canceled, state that it was terminal and unchanged.
- If lookup, status resolution, update, or read-back verification fails or times out, leave the issue unchanged or unverified and continue finalization. Report `Linear follow-up skipped` or `Linear update unverified`, with the issue id when known and the reason. A Linear failure alone does not make finalization blocked or partial; never claim an unverified issue update succeeded.

## Retrospective And Reporting

8. Run the retrospective
- Run `$ag-learn` after the task lands in the requested context, after any matching spec has been archived, and after any matching repo-specific final hooks from `~/.fin.yaml` have completed.
- For `gh`, run it after the PR merge or already-merged confirmation, repo-specific final hooks, local base containment proof, and deterministic cleanup complete when applicable.
- For `local`, run it after the local merge, repo-specific final hooks, local base verification, and deterministic cleanup complete when applicable.
- Review the saved learning note and extract 2-3 high-signal learnings.
- Present these as proposed learnings for follow-up, not mandatory extra scope.
- If `ag-learn` finds no meaningful improvement opportunities, say that explicitly.

9. Report the finished state
- State which context ran: `gh` or `local`.
- State whether that context was explicitly requested, implied by heartbeat or active task context, or auto-detected from current-branch PR state.
- State the default-branch gate's `status`, `repository_default_branch`, `target_base_ref`, and `matches` fields. For a missing or failed gate, report the blocker and retarget-or-create-PR guidance instead of a finished state.
- For `gh`, state the target identity line with PR number, branch, and source before reporting mergeability, checks, blockers, merge, or cleanup. If another PR was also present in the current checkout, explicitly state that it was not the finalization target.
- State whether the mergeability check passed directly, was skipped because the PR was already merged, continued as bounded-indeterminate, or required `fix-pr-conflict` / `fix-pr` / `sync-branch` / manual repair.
- State whether a spec was archived and include the source and destination paths when applicable.
- If an explicit blocker override was used, state the authorizing user instruction, the exact waived blockers, the override merge method, and every incomplete spec or milestone intentionally left active.
- For `gh`, state whether the PR was already merged and `merge-pr` was skipped, or whether `merge-pr` ran successfully, including whether the remote merge succeeded directly or required separate post-merge worktree cleanup because local branch deletion failed.
- If a remote branch was retained for downstream PRs, name the branch and dependent PR numbers; if explicitly authorized retargeting was performed, report each dependent PR and its verified new base.
- For `gh`, if auto-merge was enabled but the PR has not merged yet, report `auto-merge pending`, include the PR URL, head SHA, auto-merge method, `autoMergeRequest.enabledAt` when available, heartbeat automation id and next check when creation succeeded, and explicitly state that local cleanup requiring merged proof was deferred.
- If the automatic foreground-watch fallback was used, state that persistent heartbeat automation was unavailable, identify the locked PR, branch, and head SHA, and report whether the watch observed verified merge or stopped on a terminal blocker. After verified merge, report the normal refresh, containment proof, cleanup, Linear, and retrospective results rather than leaving the run in `auto-merge pending`.
- For `local`, state whether the branch landed via local merge, was already on `main`, or was blocked before landing.
- State the deterministic cleanup script's final `status`, whether the worktree path and registration are absent, whether the local branch was deleted, and whether cleanup was not applicable. Do not claim or report global prune as a normal step.
- For `gh`, state separately whether any ordinary PR babysit/watch automation was found and deleted, already absent, or blocked, and whether the `fin` auto-merge heartbeat remained through post-merge work and was deleted after the terminal outcome.
- If branch deletion required squash/rebase merge proof, state the PR head SHA, merge commit, and local `main` containment check used as the cleanup proof.
- State whether the local `main` checkout or base ref was updated or verified successfully, identify the resulting `main` tip when relevant, and say whether the normal checkout path or non-switching base-ref path was used.
- State any requested external notification result separately from CI and merge state. If notification delivery is blocked by missing credentials, unavailable CLIs, or channel configuration, say that directly without describing the PR as not green.
- If the remote PR landed but local `main` refresh was blocked by unrelated dirty changes, call that out as `partial local cleanup`: include the merge commit, the dirty-main error, which cleanup steps did complete, and which local branch or verification step was intentionally deferred.
- State whether `~/.fin.yaml` was checked, whether it parsed successfully, whether a workspace entry matched the non-worktree checkout root, and whether the matched repo-specific final hooks completed or were skipped.
- If `local` pushed `main`, state whether the push succeeded. If it intentionally remained local-only, say that explicitly.
- State the best-effort Linear result: linked issue id and verified completed status, no linked pending issue, already-terminal issue left unchanged, explicit keep-open override, or a brief skipped/unverified follow-up note. Keep the finalization outcome based on landing, required verification, and cleanup.
- Summarize the proposed learnings as a numbered list so each item can be referenced later.
- Mention where `ag-learn` saved the learning note.
- Keep the final report internally consistent with the chosen context: completed task, completed spec archival, requested landing path, reconciled or verified `main`, completed retrospective.

## Guardrails

These landing guardrails apply to `gh` / `local`; `nocheck` uses its local-only
workflow and returns before this section.

- Do not move a spec into `.archive` unless the task is actually complete.
- Do not archive unrelated active specs.
- Never archive, merge, clean up, or claim full finalization without a current passing `./scripts/check_default_branch.py` record. Never merge or finalize a PR whose base is not the repository's origin main branch.
- Do not try to finalize directly from detached `HEAD`; create a named branch first.
- Do not archive a spec or land the change before the local branch is confirmed mergeable, the GitHub PR is confirmed mergeable, the matching PR is already merged, or the GitHub PR meets the bounded-indeterminate conditions in the shared workflow.
- Do not silently switch from `gh` to `local` or from `local` to `gh`.
- Do not ask the user to choose `gh` vs `local` when the argument is omitted and branch PR state clearly determines the context.
- Do not choose `gh` from a no-argument invocation unless the PR belongs to the current branch being finalized, or a heartbeat-derived or active-task-derived PR target has been locked after live PR verification.
- Do not run `trigger:merge-pr` when GitHub reports the matching PR is already `MERGED`; use the existing merged state and continue finalization from there.
- Never delete a remote branch used as the base of an open downstream PR, or merge/enable auto-merge with such dependents while repository automatic branch deletion is enabled.
- Never silently retarget dependent PRs, alter repository deletion settings, or treat failed downstream-PR discovery as proof that branch deletion is safe.
- If `gh` repair via `fix-pr-conflict` or `fix-pr` cannot clear positive evidence of conflicts or unmergeability, stop and report the blockage instead of continuing the finalization flow. A bounded-indeterminate state without such evidence is not a repair failure.
- If `local` repair via branch sync or rebase cannot restore a mergeable state, stop and report the blockage instead of continuing the finalization flow.
- Do not run `merge-pr` in `gh` mode before the matching spec is marked complete and archived, unless an explicit blocker override authorizes landing a mergeable or bounded-indeterminate PR while leaving that incomplete spec active and unarchived.
- Do not require a PR in `local` mode.
- Do not classify a green PR as terminally blocked only because GitHub still reports `OPEN`/`BLOCKED` shortly after auto-merge was successfully enabled. Use the explicit `auto-merge pending` state unless the auto-merge request disappears, checks fail, or conflicts appear.
- Do not leave an unattended auto-merge-pending PR without exactly one active heartbeat. Do not infer automation unavailability from a missing local registry, and do not resolve or delete the heartbeat merely because auto-merge was enabled, remains pending, or has just merged. If heartbeat creation fails or the capability is absent after discovery, the same `$fin` run must watch in the foreground automatically until verified merge or a real terminal blocker; never end merely to ask the user to request monitoring again.
- During a foreground watch, do not change the locked PR, branch, or exact head SHA; exceed 60 seconds between concise progress updates; stop while the same head remains safely auto-merge pending; or treat the watch request as authorization for an administrator, approval, or blocker override.
- Do not treat `gh pr merge --delete-branch` local branch-deletion failures caused only by linked worktree attachment as a failed merge when the remote PR already landed.
- Do not leave a merged linked worktree behind when the branch is meant to be fully finalized.
- Do not remove unrelated named worktrees or branches during cleanup. The cleanup script requires the exact registered branch and HEAD, or an explicit detached flag plus exact HEAD; path naming alone is never cleanup authority.
- Do not leave an ordinary PR babysit/watch automation active after its PR has merged. Delete or cancel it during finalization and report any deletion blocker. Do not apply this rule to the `fin: auto-merge ...` heartbeat, which must remain until steps 5-9 reach a terminal post-merge outcome.
- Do not force-delete a squash/rebase-merged local branch based only on GitHub PR state. Refresh the local base first and pass the exact contained landed commit, expected branch head, and `squash` or `rebase` mode to the cleanup script.
- If the local base cannot be refreshed safely because the retained checkout has unrelated changes, preserve the worktree and branch. Do not run cleanup until base containment succeeds.
- Do not run the cleanup script with `--execute` before every matching repo-specific final hook succeeds.
- Do not manually run reset, clean, worktree removal, recursive path deletion, local branch deletion, or global worktree prune as a substitute for the cleanup script.
- Do not delete or rewrite a cleanup journal. When a transaction stops in `blocked` or `partial`, preserve it and rerun the exact command after resolving the reported blocker.
- Do not add remote branch deletion or any other network mutation to the local cleanup script.
- Do not match `~/.fin.yaml` workspace paths against temporary linked worktree roots; match the non-worktree checkout root for the branch's repository.
- Do not ignore a matching `~/.fin.yaml` workspace entry. If the additional instructions are ambiguous, destructive, or cannot be verified, stop and report the blocker before cleanup.
- Do not silently ignore malformed `~/.fin.yaml`; a parse failure is a finalization preflight issue unless raw content is clearly non-executable and unambiguous. Never delete a linked worktree while malformed fin config might contain unrun hooks or cleanup instructions.
- Do not invoke cleanup from inside the target worktree. Pass a retained checkout through `--repo`; the script enforces this boundary.
- Do not report final success while local `main` or the safely refreshed local base ref still points behind the landed result unless the user explicitly says not to refresh or verify it.
- Do not reclassify a green PR or passing CI as blocked because a Slack/chat/desktop notification could not be sent. Report notification failures as auxiliary notification blockers with the missing prerequisite.
- Do not complete a Linear issue before landing and local-main verification succeed, from title/branch/PR similarity alone, or when more than one pending issue matches the active thread.
- Never block finalization or report it as partial solely because Linear lookup or completion failed, was unavailable, or remained ambiguous or unverified. Report the Linear limitation separately and claim issue completion only after verified read-back.
- Do not invent a parallel spec layout; use the `specy` convention already present in the workspace.
- Do not archive an active parent folder spec just because a milestone sidecar
  inside it landed; leave the parent active while sibling milestones remain.
- Do not archive only `spec.md` when the active spec uses a folder schema. Move the entire spec folder so checklist, data, and other sidecars remain attached.
- Do not suppress `ag-learn` output just because the task was straightforward; run it and report either the proposals or the explicit no-learning result.

## Done Checklist

For `nocheck`, use step 7 of its workflow instead. This checklist covers landing
through `gh` / `local`.

- `fin` was run with either an explicit `gh` / `local` argument, a heartbeat-derived or active-task-derived PR target, or no argument and a context auto-detected from current-branch PR state.
- The repository's origin main branch was resolved authoritatively before mutation, and `./scripts/check_default_branch.py` returned exit `0` with `status: "pass"`, `matches: true`, and every `allow` field set to `true` for the exact PR base or local merge target. The JSON record was retained; a missing, malformed, or failed gate stopped finalization.
- In `gh` mode, any explicit PR number, PR URL, branch target, heartbeat-derived PR target, or active-task-derived PR target was locked before current-branch PR detection and reused for every PR-state, mergeability, merge, automation, and cleanup decision.
- Every PR status or blocker report included a target identity line with PR number, branch, and source; when multiple PRs were mentioned, every PR-specific claim was labeled with the PR number.
- If the run started from detached `HEAD`, it was converted into a named branch before context detection and landing.
- The chosen or detected context was locked once and respected throughout the flow.
- Current branch or PR was checked for mergeability against `main` or its base branch before spec archival, unless the matching PR was already merged; any detected conflicts were handled with `trigger:fix-pr-conflict`, `trigger:fix-pr`, `trigger:sync-branch`, or an equivalent local repair flow, and any bounded-indeterminate GitHub state recorded the exact head identity and absence of positive conflict evidence.
- Matching active spec, if any, is marked complete and moved to
  `$DOCS_ROOT/specs/.archive/`; folder specs were moved as whole folders only
  when the parent spec was complete, and milestone or sidecar completions inside
  still-active parent specs were recorded without archiving the parent.
- Unrelated active specs remain untouched.
- `~/.fin.yaml` was checked, parsed or explicitly handled as malformed, and any workspace entry matching the non-worktree checkout root was applied before linked-worktree removal.
- In `gh` mode, the matching PR was checked for an existing `MERGED` state before attempting merge; `trigger:merge-pr` has been run after archival only when the PR was not already merged, or the missing-PR condition was reported explicitly.
- For an open `gh` target, exact-head downstream PRs and `delete_branch_on_merge` were verified before merging or enabling auto-merge; dependent remote base branches were retained, or every explicitly authorized retarget was verified before deletion.
- An unattended auto-merge-pending handoff has exactly one active heartbeat for the locked PR. The heartbeat was not deleted on first merge observation; it was deleted only after live `MERGED`, `mergedAt`, and `mergeCommit` verification and a terminal post-merge outcome from steps 5-9.
- Any foreground watch was entered automatically only after persistent heartbeat automation was unavailable or failed, retained the locked PR number, branch, and exact head SHA, emitted concise progress at least every 60 seconds, and continued until verified `MERGED` or a reported terminal blocker. A verified merge resumed the normal refresh, containment proof, cleanup, Linear, and retrospective steps.
- Any explicit blocker override recorded the locked target, exact waived blockers, authorizing user instruction, override merge method, and intentionally unarchived incomplete specs.
- In `local` mode, the completed branch has been merged into local `main` or verified as already landed there.
- The local base was refreshed or verified to contain the landed commit before cleanup, and every matching final hook succeeded.
- Repository-required ignored files and dependency directories were preserved
  before cleanup, including when no final hook existed, and verification did
  not reconcile or install dependencies.
- When local cleanup was applicable, the deterministic cleanup script's dry run returned `ready` or `noop`; its execution returned `complete` or `noop` with path, registration, and local branch absent plus base-containment proof true. No global worktree prune was run, and unrelated worktrees and branches were left untouched.
- Any ordinary PR babysit/watch automation found for the merged PR was deleted or reported as blocked; service timeouts used the exact read-only registry fallback and did not silently imply absence. Any `fin` auto-merge heartbeat followed its separate step-4 lifecycle.
- Requested external notifications, if any, were attempted or explicitly skipped with a separate notification blocker; notification failures were not described as CI failures.
- For squash/rebase-merged PRs, local branch deletion used verified PR merge state plus local `main` containing the PR merge commit, not branch ancestry alone.
- The local `main` checkout was checked for concurrent tracked or untracked changes immediately before refresh, then refreshed or verified to include the landed work before the task was reported complete; otherwise the required partial local cleanup state was reported.
- Best-effort Linear follow-up was attempted when available; a verified update, no-op, terminal state, keep-open override, or skipped/unverified result was reported briefly. Unfinished Linear work did not block an otherwise completed finalization.
- `$ag-learn` has been run.
- The final report states whether the context was explicit, implied by heartbeat or active task context, or auto-detected.
- The final report includes the archived spec path change when applicable.
- The final report states the landing result for the chosen context.
- The final report states the local `main` refresh or verification result.
- The final report includes proposed learnings and the saved learning-note path.

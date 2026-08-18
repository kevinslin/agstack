---
name: merge-pr
description: merge a remote pr
---

Instructions:

Create a to-do list with the following items then perform all of them:

If the user says to keep the current worktree, branch, or checkout for post-merge work, treat that as an explicit cleanup override:

- Merge the remote PR only.
- Do not switch the current worktree to `main`.
- Do not remove any local worktree.
- Do not delete the local branch.
- Do not use `--delete-branch` unless the user separately asks to delete the remote branch.
- You may `git fetch origin main` after the merge to refresh `origin/main`, but leave the current checkout in place.

1. Determine whether the current branch has an open remote PR.
   - If a remote PR exists, run `trigger:merge-pr-basic`, including its mandatory exact-base downstream-PR and repository automatic-deletion checks.
   - Preserve the remote head branch whenever an open downstream PR still uses it as its base; local branch/worktree cleanup does not authorize remote deletion.
   - If no remote PR exists, merge the current local branch into local `main` instead.
   - Before a local-only merge, make sure the current branch is committed and clean. If it is not, use `trigger:commit-code` first.
   - Perform the local-only merge from the non-worktree main checkout when possible, not from an attached feature worktree.
   - Use a non-fast-forward merge unless the user explicitly requested a different merge style.

2. Switch back to the main branch locally if you are not on it. Pull from the remote or otherwise reconcile the branch to current remote state.
   - If step 1 used a local-only merge, do not discard that merge while reconciling `main`.
   - If step 1 merged a remote PR, do not inspect whether local `main` has unpublished commits before this step.
   - Push local `main` changes after reconciliation when a remote is configured and pushing is appropriate for the repo.

3. Clean up the merged branch aggressively.
   - Skip this entire cleanup section when the user explicitly asked to keep the current worktree, branch, or checkout for post-merge work.
   - Treat remote merge and branch cleanup as separate checks for linked-worktree branches; do not assume `gh pr merge --delete-branch` completed every local and remote cleanup step just because the PR merged.
   - If `merge-pr-basic` returns a local branch-deletion failure caused only by `branch ... used by worktree`, verify whether the PR already merged before deciding that step 1 failed.
   - When the PR already merged, continue directly into cleanup instead of retrying the merge command.
   - If the merged branch is attached to any worktree, remove those worktrees first.
   - If the current session is still on the merged branch worktree, still remove that worktree as part of cleanup; do not treat the active attachment as a reason to keep the branch.
   - After removing worktrees, run `git worktree prune`.
   - Delete the local branch once no worktree still points at it.
   - After local cleanup, verify whether the remote branch still exists. Immediately before any explicit deletion, repeat `gh pr list --repo <owner/repo> --state open --base <head-branch> --limit 1000 --json number,url,headRefName,baseRefName`.
   - Delete the remote branch only when that fresh exact-base query succeeds and returns zero open downstream PRs. If any remain, or dependency discovery fails, retain the branch and report its dependent PR numbers or the lookup blocker.
   - If step 1 used the local-only merge fallback and there is no remote PR, do not fail branch cleanup just because there was nothing remote to delete.

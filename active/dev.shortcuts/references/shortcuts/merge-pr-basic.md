---
name: merge-pr-basic
description: merge a pr
---

Instructions:

Create a to-do list with the following items then perform all of them:

1. Check if there are any unstaged commits. If so, use trigger:commit-code to commit unstaged changes.

2. Check if there is a remote PR open for the current branch. Make sure that all pending checks have passed. If a remote PR is not available, throw an error.

3. Protect open downstream PRs before merging or deleting the current PR's exact head branch.
   - Lock the parent PR's exact repository, head branch, and base branch from live GitHub state.
   - Query `gh pr list --repo <owner/repo> --state open --base <head-branch> --limit 1000 --json number,url,headRefName,baseRefName` and inspect `gh api repos/<owner/repo> --jq '.delete_branch_on_merge'`.
   - Treat an errored, incomplete, or ambiguous dependency or deletion-policy lookup as a blocker. Do not merge or delete the branch until safe behavior can be verified.
   - When open downstream PRs exist and repository automatic deletion is disabled, merge without `--delete-branch`, retain the remote head branch, and report the dependent PR numbers. Local cleanup may still proceed independently.
   - When open downstream PRs exist and repository automatic deletion is enabled, stop before merging: GitHub would delete their base even without `--delete-branch`. Ask for explicit approval to retarget each dependent PR to the parent's verified base, or leave the parent unmerged.
   - Only after explicit retargeting approval, run `gh pr edit <dependent-number> --repo <owner/repo> --base <parent-base>` for each dependent PR, then repeat the exact-base query and require zero remaining open dependents before merging.

4. If a remote PR exists, merge it remotely (use `gh` if available). No need to wait for pending checks since we already did that in step 2.
   - Delete the remote branch after merge only when current dependency discovery proves no open PR uses it as its base.
   - Never pass `--delete-branch` while a downstream PR remains. Preserve its remote base branch even when the parent PR's local branch or worktree can be removed.
   - If the user asked to keep the current worktree, branch, or checkout for post-merge work, do not pass `--delete-branch`; merge the PR only and leave local cleanup to the user or a later explicit request.
   - Use the repository-supported merge method. If `gh pr merge --merge` fails because merge commits are not allowed, retry once with `--squash` when squash merge is supported by the repository.
   - If `gh pr merge --delete-branch` reports that the local branch cannot be deleted because it is used by a linked worktree, immediately check whether the PR state is already `MERGED`.
   - If `gh pr merge` reports a local checkout or worktree error after attempting the remote merge, immediately check whether the PR state is already `MERGED`. Examples include `fatal: '<branch>' is already used by worktree`.
   - When the PR is already merged, treat the command result as merge success plus incomplete local cleanup. Do not retry the merge; hand cleanup back to `merge-pr` so it can remove the worktree, prune, and delete the branch explicitly.
   - Only treat the step as a true merge failure when the PR did not merge remotely.

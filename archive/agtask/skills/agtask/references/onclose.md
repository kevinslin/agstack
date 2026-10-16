# Default OnPreClose

Finalize the current task's Git state before agtask marks it done. This policy
runs inside the task being closed. It must not remove the current worktree.

1. Confirm the requested task scope is complete. If it is partial or blocked,
   stop and do not continue to the committing close call.
2. Inspect the current directory and Git state. When the task is not in a Git
   repository, treat Git finalization as not applicable and continue.
3. Lock the current worktree path, branch or detached state, and full HEAD OID.
   Follow repository instructions before changing Git state.
4. Keep the enclosing close workflow's project merge lease live. Heartbeat
   before each push or merge and after any long-running check. If ownership is
   lost, stop before further Git mutations; a stale task must never commit the
   ledger close with an old fencing token.
5. If detached HEAD contains changes or commits that need landing, create a
   correctly named task branch before committing or pushing.
6. Commit only changes attributable to this task. If the checkout is shared or
   contains ambiguous unrelated changes, stop rather than committing them.
7. When the current branch has a matching open pull request, push the exact
   task head, require the repository's checks and mergeability gates, merge it,
   and verify the remote base contains the landed result. Treat an already
   merged matching pull request as landed after live verification.
8. When no matching pull request exists, reconcile the local default branch in
   a retained checkout, merge the completed task branch, and verify containment.
   Push the updated default branch only when a remote is configured and the
   repository's instructions permit direct push. Otherwise report that the
   result intentionally remains local.
9. Do not run `git worktree remove`, recursive deletion, `git worktree prune`,
   branch deletion, destructive reset, or clean. Worktree cleanup is outside
   the close lifecycle.
10. Continue the agtask close workflow only after landing and containment are
   verified. On any ambiguous or failed Git operation, report the exact blocker
   and leave the task non-done so OnPreClose can be retried.

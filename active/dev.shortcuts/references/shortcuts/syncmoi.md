---
name: syncmoi
description: reconcile both chezmoi sources, notify on conflicts, and push both repositories
---

Instructions:

1. Inspect both managed sources and their actual Git repositories:
   - Agents source: `$HOME/agents/config`; Git repository: `$HOME/agents`.
   - Mackup source: `$HOME/code/Mackup`; Git repository: `$HOME/code/Mackup`. Its `.chezmoiroot` selects the `home` source subtree.
   - Always pass `chezmoi --source "$CHEZMOI_SOURCE"`; never use bare `chezmoi apply`, change the default source, or assume either repository's branch name.
2. For each source, inspect `chezmoi --source "$CHEZMOI_SOURCE" status` and `diff`, existing Git changes, the current branch and upstream, managed target ownership, and any existing merge or rebase before modifying anything. Preserve unrelated worktree changes and never expose credentials or secret values.
3. Fetch each repository's configured upstream through normal Git transport. Compare the existing source, the fetched incoming source, and each changed local managed target before deciding which version should win.
4. Capture local-only changes to managed non-template files with `chezmoi --source "$CHEZMOI_SOURCE" re-add "$TARGET"`. Never blindly re-add every target: existing source edits or fetched changes might otherwise be overwritten. `re-add` does not update `.tmpl` files; update a template only when its intent is unambiguous and its template expressions can be preserved.
5. Record the current Git commit, then stage and commit only reviewed managed-source changes required for reconciliation. Integrate upstream source changes without resetting, force-pushing, silently stashing, or discarding unrelated edits.
6. Reuse `$HOME/code/devtools/tools/gitsync/scripts/chezmoi-post-sync` for its existing backup, three-way merge, target-application, and deduplicated Slack-notification behavior. Set `GITSYNC_REPO_PATH` to the Git repository, `GITSYNC_OLD_HEAD` to the recorded pre-integration commit, and `GITSYNC_NEW_HEAD` to the current commit. Keep the agents reconciler's existing state directory, but set `CHEZMOI_POST_SYNC_STATE_DIR` to a separate repository-specific directory for Mackup; never mix commit histories or pending-conflict state.
7. Re-add safely retained or merged local non-template targets after reconciliation, commit any resulting reviewed managed-source changes, and apply any remaining incoming-only changes to specific targets with `chezmoi --source "$CHEZMOI_SOURCE" apply -- "$TARGET"`. Recheck source-scoped chezmoi status, target contents, Git conflict state, and unrelated worktree changes.
8. If overlapping edits, template ambiguity, binary/encrypted content, conflicting source ownership, failed Git integration, or another unsafe condition prevents reconciliation, preserve all source and target data and invoke `$slack-notify` with a concise plaintext message naming the repository, affected targets, and blocker. If notification fails, report only its non-secret error. Stop without pushing either repository.
9. Only after both repositories reconcile successfully, push each current branch to its configured upstream through normal Git transport. Verify both pushes independently and report both repositories, branches, and resulting commits; never force-push.

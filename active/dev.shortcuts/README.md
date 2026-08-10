These shortcuts are copied over from Joshua's Levy's amazing [speculate framework](https://github.com/jlevy/speculate). Currently experimenting with turning them into a skill.

The shortcut set also includes repo maintenance flows such as `sync-branch` for rebasing the current branch onto the remote default branch from `git remote show` and resolving conflicts, plus `sync-branch-push` to run that sync and then force-push the branch.

Use `trigger:doit` to implement a requested change, verify it, commit the scoped changes, and push the current branch.

Use `trigger:syncmoi` to reconcile local and upstream changes for the agents and Mackup chezmoi sources, notify Kevin on unsafe conflicts, and push both repositories after successful reconciliation.

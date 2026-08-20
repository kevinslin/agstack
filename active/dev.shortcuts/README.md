These shortcuts are copied over from Joshua's Levy's amazing [speculate framework](https://github.com/jlevy/speculate). Currently experimenting with turning them into a skill.

The shortcut set also includes repo maintenance flows such as `sync-branch` for rebasing the current branch onto the remote default branch from `git remote show` and resolving conflicts, plus `sync-branch-push` to run that sync and then force-push the branch.

Use `trigger:doit` to implement a requested change, verify it, commit the scoped changes, and push the current branch.

Use `trigger:spec` to draft a spec, run independent simplification and
correctness reviews in parallel, and then pause for user course correction
before applying approved changes.

`trigger:merge-pr-basic` and `trigger:merge-pr` check for open stacked PRs and
repository-level automatic branch deletion before merging. They retain any
remote branch that remains another PR's base and require explicit approval
before retargeting dependent PRs.

Use `trigger:syncmoi` to reconcile local and upstream changes for the agents and Mackup chezmoi sources, notify Kevin on unsafe conflicts, and push both repositories after successful reconciliation.

`trigger:loop` always runs a reviewer pass and parent classification. It runs
fixer passes only when the user explicitly invoked `trigger:loop`, requested a
review-and-fix workflow, or otherwise authorized edits; automatic routing from
a plain review stops with unresolved findings instead of changing files.

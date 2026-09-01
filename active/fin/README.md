# fin

[Skill instructions](./SKILL.md) for three explicit contexts:

- `fin gh`: merge a completed GitHub PR and verify landing and cleanup.
- `fin local`: land completed local work on the repository's default branch.
- `fin nocheck`: close a disposable local review branch and linked worktree
  without checking or changing remote state. Local identity and file-preservation
  checks still apply; uncommitted work is preserved.

With no context, `fin` selects `gh` or `local`. `nocheck` requires an explicit
invocation and does not merge code or require a merged PR.

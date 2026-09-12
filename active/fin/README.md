# fin

[Skill instructions](./SKILL.md) for finalization and local review cleanup:

- `fin gh`: merge a completed GitHub PR and verify landing and cleanup.
- `fin force [target]`: run GitHub finalization with explicit authorization to
  bypass missing required approvals only, using existing repository permissions.
- `fin local`: land completed local work on the repository's default branch.
- `fin nocheck`: close a disposable local review branch and linked worktree
  without checking or changing remote state. Local identity and file-preservation
  checks still apply; uncommitted work is preserved.

With no context, `fin` selects `gh` or `local`. `force` and `nocheck` require
explicit invocation. `nocheck` does not merge code or require a merged PR.

For `gh` and `local`, linked Linear issue follow-up is best effort. Missing
access, authentication failures, timeouts, ambiguous matches, and failed updates
are reported as skipped or unverified follow-up; they do not block finalization
or make an otherwise completed task partial. Issue updates still require an
exact task match, successful landing, and verified read-back before claiming
completion.

Ordinary `fin` and `fin gh` no longer automatically bypass missing approvals.
Use `fin force 85117` or `fin force https://github.com/owner/repo/pull/85117`;
a branch name is also accepted. `fin force` without a target uses normal GitHub
target inference and stops if no PR resolves.

Force requires successful known required checks for the exact PR head and all
other merge gates to pass. It cannot waive failed, pending, missing, or unknown
checks, conflicts, changes-requested reviews, unresolved threads, incomplete
scope, or downstream branch protection. Repository no-bypass rules, including
RIPP, still apply. It never changes rules, permissions, bypass lists, or auth and
stops on GitHub rejection. The report records the target, head, waived approval
requirement, and actual outcome; normal post-merge verification and cleanup
remain required. Other blocker overrides require separate explicit authorization.

Run local contract and default-branch gate tests (no live merge):

```bash
python3 -m unittest discover -s active/fin/scripts/tests
```

Run this command from the repository root. The force tests validate the skill's
instruction contract; GitHub permission enforcement is not exercised locally.

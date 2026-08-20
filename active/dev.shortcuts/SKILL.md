---
name: dev.shortcuts
description: Route any request containing literal `trigger:` before ordinary skill
  dispatch. Read at thread start and whenever `trigger` appears.
dependencies:
- agtask
- babysit-pr
- branch
- dev.review
- slack-notify
- spec-simulate
- specy
---

## Mandatory Trigger Gate

1. Before ordinary intent or skill routing, scan the user request for the literal `trigger:` token.
2. When present, resolve and load the exact matching shortcut before invoking any dependency or semantically related skill.
3. When a shortcut matches, announce `Using [shortcut name]`.
4. Treat the shortcut as the end-to-end contract. A wrapped skill's success does not complete the shortcut while later shortcut steps remain.
5. If the user later questions a trigger's outcome, re-read the matched shortcut and compare every required action before explaining or correcting the result.
6. When absent, do not invoke shortcuts.

## Context
Shortcuts are a small self-contained workflow that can be triggered via `trigger:<shortcut-name>`, for example `trigger:merge-pr`.

ALWAYS use the shortcut when user mentions `trigger:<shortcut>`. Read the shortcut file and follow literally.

## Shortcut Location
Shortcuts can be in the following locations:

1. Under the skill-bundled `./references/shortcuts/` directory next to this `SKILL.md` (runtime mirror is typically `~/.codex/skills/dev.shortcuts/references/shortcuts/`).
2. Inlined in agent instructions under `## Shortcuts`. Shortcut is header text. Can be followed by a space with argument hints enclosed in `[arg_name]`
Examples
```
## Shortcuts

### Foo [arg1] [arg2]
Invokes a foo with [arg1] and [arg2]
```

## Available Bundled Shortcuts
This section is an inline index of the shortcut files bundled in `./references/shortcuts/`.
The file under `./references/shortcuts/[shortcut].md` remains the executable source of truth.

| Shortcut | Summary |
| --- | --- |
| `auto-merge` | Run `push-pr`, then `merge-pr-basic`. |
| `check-ci` | Watch PR checks and classify Buildkite failures before reporting status. |
| `checkout-worktree` | Use `arbor checkout` from the main checkout with an explicit worktree path, then verify cleanup. |
| `close` | Close the tracked task, then archive its Codex thread. |
| `commit-code` | Run the canonical precommit flow, commit cleanly, and update the PR if one exists. |
| `create-spec` | Create a spec with `specy`, then run looped `dev.review` and `spec-simulate` passes on it. |
| `doit` | Implement the requested change, verify it, commit scoped changes, and push the current branch. |
| `fix-pr-conflict` | Rebase the current PR branch onto its base branch, resolve conflicts, and force-push. |
| `fix-pr` | Check out a PR, address review feedback, resolve review threads, and rerun CI. |
| `inline-shortcut` | Inline one or more shortcut definitions into another skill. |
| `loop` | Run review instructions with a reviewer subagent and a fixer subagent until major findings are cleared or a blocker stops progress. |
| `merge-pr-basic` | Merge the current remote PR after passing checks while preserving branches used by open downstream PRs. |
| `merge-pr` | Merge a remote PR or local branch, reconcile `main`, and clean up only branches not needed by downstream PRs. |
| `plan-and-review` | Draft a feature spec with `specy`, review it with `dev.review`, then fold accepted feedback back into the spec. |
| `prepare` | Stash local changes, switch to local `master` or `main`, and pull latest from `origin`. |
| `precommit-process` | Run the canonical pre-commit review and validation workflow before committing. |
| `promote-shortcut-to-skill` | Convert a shortcut into a standalone skill and replace old shortcut references. |
| `push-code` | Commit if needed, then push the current branch using repo-specific push guardrails. |
| `push-pr` | Commit if needed, push the branch, create a ready-for-review PR, then watch and fix CI as needed. |
| `rebase-and-fix` | Rebase the current branch onto a provided branch, fix PR conflicts, push, and check CI. |
| `review` | Create a new worktree for a PR link, run `dev.review`, and add a flow doc for the PR logic. |
| `review-spec` | Run looped `dev.review` and `spec-simulate` passes against an existing spec. |
| `spec` | Draft a spec, run parallel simplification and correctness reviews, then pause for user direction. |
| `sync-branch-push` | Rebase the current branch onto the remote default branch from `git remote show`, then force-push upstream with lease. |
| `sync-branch` | Rebase the current branch onto the remote default branch from `git remote show` and resolve conflicts if needed. |
| `syncmoi` | Reconcile both chezmoi sources, notify Slack on unsafe conflicts, and push both repositories. |

## Maintenance
Keep the inline shortcut index above synchronized with the bundled shortcut files.

Whenever a file in `./references/shortcuts/` is added, removed, renamed, or materially changed, update the `Available Bundled Shortcuts` section in this `SKILL.md` in the same change.

This sync rule applies to:

- Shortcut names and trigger text
- One-line shortcut summaries
- Chaining guidance or examples in this `SKILL.md` that mention affected shortcuts

## Shortcut Trigger and Usage
Only `trigger:<shortcut-name>` invokes a shortcut. When present, resolve it in this order:

1. Exact file match in this skill's `./references/shortcuts/[shortcut].md`
2. Exact inlined match under `## Shortcuts` in active instructions

If the user asks to promote a shortcut to a skill, use `trigger:promote-shortcut-to-skill`.

If a shortcut doesn’t resolve, quickly scan the most relevant skill for similarly-named shortcuts before doing broader repo-wide searches.

## Shortcut Chaining
This involves using multiple shortcuts in sequence. Shortcut chaining is denoted by [shortcut1] -> [shortcut2]

Example:
`trigger:precommit-process -> trigger:create-pr`

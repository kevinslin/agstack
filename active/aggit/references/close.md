# `aggit close`

Close the current branch checkout conservatively. Verify any exact tracking
pull request is merged, then remove the checkout only when it is a clean linked
worktree. Retain the local branch unless the user separately asks to delete it.

## Inputs

- Target checkout: default to the repository containing the current working
  directory; accept an explicit linked-worktree path.

## Workflow

1. Resolve the target repository root, attached branch, Git common directory,
   and complete `git worktree list --porcelain` record. Stop on detached
   `HEAD`, a missing registration, or ambiguous identity.
2. Inspect the target with
   `git status --porcelain=v1 --untracked-files=all`. If it is dirty, stop,
   show the affected paths, and ask for next steps. Never force removal.
3. Determine whether the repository provider exposes a pull request whose head
   is the exact current branch. For GitHub, query live state with `gh` and
   retain the PR number, URL, head branch, base branch, state, and merge time.
   Do not infer a tracking PR from a similar title or branch.
4. Handle the PR result:
   - Exactly one matching PR: require live state `MERGED` and a non-null merge
     time. Stop for open, closed-unmerged, unknown, or unavailable state.
   - Multiple matching PRs: stop and ask the user to identify the tracking PR.
   - No matching PR: report that no tracking PR was found and continue without
     claiming the branch was merged.
   - Provider/authentication failure: stop if it prevents determining whether
     a tracking PR exists.
5. Identify whether the target is the primary checkout or a linked worktree
   from the porcelain worktree records.
6. For the primary checkout, do not remove it. Report that worktree cleanup is
   not applicable.
7. For a linked worktree:
   - Resolve a retained checkout for the same Git common directory.
   - Recheck target identity and cleanliness immediately before removal.
   - Run from the retained checkout:

     ```bash
     git worktree remove "<absolute-target-path>"
     ```

   - Never pass `--force`.
8. Verify a removed linked worktree is absent both from the filesystem and
   `git worktree list --porcelain`. If either remains, report partial cleanup.
9. Do not delete the local branch, remote branch, or unrelated worktree unless
   the user explicitly requests that separate action.

## Output

Report:

- repository, branch, and target path;
- tracking PR result and merge evidence, or that no tracking PR was found;
- whether the target was primary or linked;
- worktree removal result and post-removal verification; and
- `Branch retained: yes` unless a separately authorized branch deletion ran.

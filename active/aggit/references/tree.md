# `aggit tree`

Create one new branch and linked worktree based on the fresh `origin` branch
established by `./references/preflight.md`.

## Inputs

- New branch name: required. Derive it only when repository naming rules make
  the result unambiguous.
- Worktree path: optional. Default to
  `~/.worktrees/<repository-name>/<new-branch>`.
- Base branch and repository: optional; default according to the preflight
  workflow.

## Workflow

1. Complete the `preflight` route and retain the resolved repository, base
   branch, and fetched `origin/<base>` commit.
2. Validate the new branch with
   `git check-ref-format --branch "<new-branch>"`.
3. Check local refs, remote-tracking refs, and `git worktree list --porcelain`
   for the exact branch. Stop rather than reuse or repoint an existing branch.
4. Resolve the target worktree path to an absolute path. Require the target not
   to exist and not to appear in the worktree registry. Create only its parent
   directory when needed.
5. Create the linked worktree and branch:

   ```bash
   git worktree add --no-track -b "<new-branch>" \
     "<absolute-worktree-path>" "origin/<base>"
   ```

6. Verify all of the following:
   - the path is registered as a worktree;
   - its `HEAD` is attached to the exact new branch;
   - its starting commit equals the fetched `origin/<base>` commit; and
   - its working tree is clean, including untracked files.
7. Do not push, configure an upstream, or remove any other worktree. If
   creation fails after partial state appears, preserve that state and report
   it instead of force-cleaning it.

## Output

Report the repository, branch, absolute worktree path, base ref, exact starting
commit, clean status, and whether an upstream was configured.

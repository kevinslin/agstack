# `aggit branch`

Create and switch the current checkout to one new local branch based on the
fresh `origin` branch established by `./references/preflight.md`.

## Inputs

- New branch name: required. Derive it from the user's request only when the
  repository's naming convention makes the result unambiguous.
- Base branch: optional; default according to the preflight workflow.
- Repository: optional; default according to the preflight workflow.

## Workflow

1. Complete the `preflight` route and retain the resolved repository, current
   branch, base branch, and fetched `origin/<base>` commit.
2. Validate the new branch with
   `git check-ref-format --branch "<new-branch>"`.
3. Check local refs, remote-tracking refs, and `git worktree list --porcelain`
   for the exact branch. If it already exists or is checked out elsewhere,
   stop and ask whether the user intends to reuse it. Do not repoint it.
4. Create the branch without assigning `origin/<base>` as its upstream:

   ```bash
   git switch --no-track -c "<new-branch>" "origin/<base>"
   ```

5. Verify that `HEAD` is attached to the exact new branch, its starting commit
   equals the fetched `origin/<base>` commit, and the checkout remains clean.
6. Do not push the branch or configure an upstream unless the user asks.

## Output

Report the repository, previous branch, new branch, exact starting commit,
base ref, clean status, and whether an upstream was configured.

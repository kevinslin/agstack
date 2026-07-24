# `aggit preflight`

Verify that the current branch is safe to build from, then fetch the latest
selected branch from `origin`. Do not merge, rebase, switch branches, or modify
working-tree files.

## Inputs

- Repository: default to the repository containing the current working
  directory; accept an explicit repository path.
- Base branch: accept an explicit branch name; otherwise use `origin`'s
  default branch.

## Workflow

1. Resolve the repository root with `git rev-parse --show-toplevel`. Stop if the
   directory is not a non-bare Git working tree.
2. Resolve the attached current branch with
   `git symbolic-ref --quiet --short HEAD`. Stop on detached `HEAD`.
3. Inspect tracked, untracked, staged, and unstaged state with
   `git status --porcelain=v1 --untracked-files=all`.
4. If any output is present, stop before all network or mutation commands.
   Summarize the affected paths and ask the user whether to commit, stash,
   discard, or take another action. Do not choose or perform one implicitly.
5. Confirm that a remote named `origin` exists. Respect repository-specific
   transport and authentication requirements; never rewrite the remote unless
   the user or repository instructions require it.
6. Resolve the base branch:
   - Use the explicit base when provided.
   - Otherwise resolve `refs/remotes/origin/HEAD`.
   - If that symbolic ref is absent, query `origin`'s advertised `HEAD`
     without changing local refs and extract its exact branch.
   - Stop if the result is missing or ambiguous. Never assume `main` or
     `master`.
7. Validate the short base name and fetch only that branch into its remote
   tracking ref:

   ```bash
   git check-ref-format --branch "<base>"
   git fetch origin "+refs/heads/<base>:refs/remotes/origin/<base>"
   ```

8. Verify `origin/<base>^{commit}` resolves, then rerun the porcelain status
   check. Stop if the working tree is no longer clean.

## Output

Report:

- repository root and current branch;
- resolved base as `origin/<base>`;
- clean status before and after fetch;
- previous and fetched remote-tracking commit IDs when both are available; and
- `Ready: yes` only after every check passes.

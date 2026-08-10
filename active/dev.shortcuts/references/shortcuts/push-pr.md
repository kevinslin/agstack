---
name: push-pr
description: push a pr
dependencies: [babysit-pr]
---

Instructions:
1. Before pushing or creating the PR, inspect the current repo for PR body,
   proof, or format instructions. Read the nearest applicable `AGENTS.md`,
   `.github/pull_request_template.md`, and any repo-local skill or maintainer
   guidance that matches `PR body`, `PR create`, `Real behavior proof`, or
   `proof format`. Treat mandatory PR-format/proof requirements as pre-push
   blockers, and make the PR body satisfy them before continuing.
2. if there are unstaged changes -> invoke:commit-code
3. push code
4. verify the PR base branch from repo metadata (do not assume `main`/`master`), then create a ready-for-review PR using a body file (do NOT inline markdown in shell arguments). NEVER create a draft PR, pass `--draft`, or leave an existing PR in draft; if the current branch already has a draft PR, mark it ready with `gh pr ready` before continuing. Keep the one-line summary in `--title` only; start the body at a section header instead of repeating a title-like line. Example:
```bash
cat > /tmp/pr_body.md << 'EOF'
## Context
[what this change does]

## Testing
[description of tests]
EOF

BASE_BRANCH="$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || true)"
if [ -z "$BASE_BRANCH" ]; then
  BASE_BRANCH="$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')"
fi
if [ -z "$BASE_BRANCH" ]; then
  echo "Unable to determine default base branch" >&2
  exit 1
fi

PR_URL="$(gh pr create \
  --base "$BASE_BRANCH" \
  --title "[feat|enhance|chore|fix|docs]: [description of change]" \
  --body-file /tmp/pr_body.md)"
if [ "$(gh pr view "$PR_URL" --json isDraft --jq '.isDraft')" != "false" ]; then
  echo "Draft pull requests are forbidden" >&2
  exit 1
fi
CURRENT_DIR="$(basename "$PWD")"
PR_URL_FILE="${LOOPS_PR_ARTIFACT_FILE:-/tmp/${CURRENT_DIR}-devloop-pr}"
printf '%s\n' "$PR_URL" > "$PR_URL_FILE"
echo "Wrote PR URL to $PR_URL_FILE"
```
5. invoke $babysit-pr skill
6. notify if everything passes

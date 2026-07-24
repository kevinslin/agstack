---
name: push-code
description: push code with repo-specific push guardrails
---

Instructions:
1. If there are unstaged changes, invoke `trigger:commit-code`.
2. Determine the current repository root with `git rev-parse --show-toplevel`.
3. If the repository root is `/Users/kevinlin/code/openai`, require an SSH remote and push through the repository's configured real Git transport. Do not use GitHub API branch/ref mutation as a push fallback.
4. For other repositories, push the current branch with the repository's normal Git transport.

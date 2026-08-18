#!/usr/bin/env python3
"""Regression coverage for stacked pull request merge safeguards."""

from __future__ import annotations

import unittest
from pathlib import Path


ACTIVE_SKILLS = Path(__file__).resolve().parents[3]
FIN_SKILL = ACTIVE_SKILLS / "fin" / "SKILL.md"
SHORTCUTS = ACTIVE_SKILLS / "dev.shortcuts" / "references" / "shortcuts"
MERGE_BASIC = SHORTCUTS / "merge-pr-basic.md"
MERGE_CLEANUP = SHORTCUTS / "merge-pr.md"

DEPENDENT_PR_QUERY = (
    "gh pr list --repo <owner/repo> --state open --base <head-branch> "
    "--limit 1000 --json number,url,headRefName,baseRefName"
)


class StackedPullRequestProtectionTests(unittest.TestCase):
    def test_merge_gates_check_dependents_and_repository_deletion_policy(self) -> None:
        for document in (FIN_SKILL, MERGE_BASIC):
            with self.subTest(document=document.name):
                content = document.read_text(encoding="utf-8")

                self.assertIn(DEPENDENT_PR_QUERY, content)
                self.assertIn("delete_branch_on_merge", content)
                self.assertIn("without `--delete-branch`", content)
                self.assertIn("explicit", content.lower())
                self.assertIn("gh pr edit <dependent-number>", content)

    def test_fin_checks_downstream_pull_requests_before_merge_stage(self) -> None:
        content = FIN_SKILL.read_text(encoding="utf-8")

        self.assertLess(
            content.index("### Downstream Pull Request Protection"),
            content.index("4. Merge the PR"),
        )
        self.assertIn("before merging or enabling auto-merge", content)

    def test_shortcut_checks_downstream_pull_requests_before_merging(self) -> None:
        content = MERGE_BASIC.read_text(encoding="utf-8")

        self.assertLess(
            content.index("3. Protect open downstream PRs"),
            content.index("4. If a remote PR exists, merge it remotely"),
        )

    def test_later_branch_cleanup_rechecks_open_downstream_pull_requests(self) -> None:
        content = MERGE_CLEANUP.read_text(encoding="utf-8")

        self.assertIn(DEPENDENT_PR_QUERY, content)
        self.assertIn("Immediately before any explicit deletion", content)
        self.assertIn("returns zero open downstream PRs", content)
        self.assertIn("retain the branch", content)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Instruction-contract tests; do not merge PRs or simulate GitHub enforcement."""

from pathlib import Path
import unittest


SKILL = (Path(__file__).resolve().parents[2] / "SKILL.md").read_text()
ROUTING = SKILL.split("## Context Selection\n", 1)[1].split("## `nocheck`", 1)[0]
FORCE = SKILL.split("### `force`: Missing Required-Approval Bypass\n", 1)[1].split(
    "### Explicit Blocker Override", 1
)[0]
OVERRIDE = SKILL.split("### Explicit Blocker Override\n", 1)[1].split(
    "### Downstream Pull Request Protection", 1
)[0]
MERGE = SKILL.split("4. Merge the PR\n", 1)[1].split("5. ", 1)[0]


class ForceContractTests(unittest.TestCase):
    def test_force_routes_to_github_before_detection_and_uses_its_gate(self):
        for rule in (
            "Route `fin force [target]` to `context=gh` with `force=true` before context auto-detection",
            "Pass `--context gh` to the default-branch gate",
            "Never auto-detect `force` or fall back to `local` when no PR resolves",
            "With no target, `fin force` uses the normal `gh` inference order",
            "optional for `gh` and `force`",
            "PR number, PR URL, or branch name",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, ROUTING)

    def test_default_and_non_github_paths_do_not_gain_force_authority(self):
        self.assertIn("Set `force=false` for ordinary `fin` and `fin gh`", ROUTING)
        self.assertIn("a request to add, edit, or explain this command does not invoke finalization", ROUTING)
        self.assertIn("Do not carry force authorization to another target or later invocation", ROUTING)
        self.assertIn("lock the full head SHA on the first live read of the resolved PR", ROUTING)
        self.assertIn("reject combined contexts such as `fin local force` or `fin nocheck force` before any action", ROUTING)
        self.assertIn("Ordinary `fin` / `fin gh` must not bypass missing approvals without a separately authorized Explicit Blocker Override", FORCE)
        self.assertIn("With `force=false`, report missing required approvals as a blocker", MERGE)
        self.assertNotIn("Automatic Required-Review Bypass", SKILL)

    def test_bypass_is_approval_only_and_head_bound(self):
        for rule in (
            "caller already has permission",
            "code-owner or last-push approval when supported",
            "only remaining merge blocker",
            "Stop on target or head drift",
            "passing default-branch gate",
            "successful known required checks for that exact head",
            "If no approval is missing, use the normal merge path without `--admin`",
            "--match-head-commit <full-head-sha>",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, FORCE)

    def test_force_rejects_unknown_failed_or_additional_blockers(self):
        for rule in (
            "Unknown required-check requirements or missing, pending, or failing checks block force",
            "Confirm no merge conflicts, changes-requested reviews, unresolved review threads, or other merge blockers",
            "Unknown review state or indeterminate mergeability blocks force",
            "completion and incomplete-scope gates",
            "downstream pull request protection (including automatic branch deletion policy)",
            "file preservation, final hooks, and cleanup",
            "Permission denial or policy prohibitions remain blockers",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, FORCE)

    def test_repository_policy_and_rejection_are_terminal_for_bypass(self):
        self.assertIn("RIPP auto-merge-only / no-admin-bypass rules", FORCE)
        self.assertIn("Never change repository rules, permission grants, bypass lists, or authentication", FORCE)
        self.assertIn("If GitHub rejects the bypass, stop", FORCE)
        self.assertIn("do not broaden or retry the override", FORCE)
        self.assertIn("`force` alone is not this authorization", OVERRIDE)
        self.assertIn("Repository no-bypass rules, including RIPP, still apply", OVERRIDE)

    def test_force_checks_precede_shortcuts_and_preserve_completion_evidence(self):
        self.assertLess(MERGE.index("if `force=true`"), MERGE.index("run `trigger:merge-pr` immediately"))
        self.assertIn("After spec completion and archival, use its target-aware command instead", MERGE)
        self.assertIn("do not fall through to an admin shortcut", MERGE)
        self.assertIn("Verify the actual merged state before cleanup", FORCE)
        self.assertIn("exact target and head, waived approval requirement, merge method, and actual merge outcome", FORCE)


if __name__ == "__main__":
    unittest.main()

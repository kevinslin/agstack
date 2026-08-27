"""Real-Git integration coverage for conservative finished-task cleanup."""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "clean_branches.py"
MODULE_SPEC = importlib.util.spec_from_file_location("agcleanup_clean_branches", SCRIPT_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
cleanup = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = cleanup
MODULE_SPEC.loader.exec_module(cleanup)


class CleanBranchesIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repository"
        self.worktree = self.root / "finished-worktree"
        self.database = self.root / "state.sqlite"
        self.branch = "codex/finished-task"
        self.day = date.today()
        self.run_git(self.root, "init", "-b", "main", str(self.repository))
        self.run_git(self.repository, "config", "user.name", "Cleanup Test")
        self.run_git(self.repository, "config", "user.email", "cleanup@example.invalid")
        self.run_git(self.repository, "commit", "--allow-empty", "-m", "initial")
        self.run_git(
            self.repository, "worktree", "add", "-b", self.branch, str(self.worktree)
        )
        self.run_git(self.worktree, "commit", "--allow-empty", "-m", "finished task")
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "CREATE TABLE threads (id TEXT PRIMARY KEY, cwd TEXT, git_branch TEXT, "
                "archived INTEGER, created_at INTEGER, updated_at INTEGER, archived_at INTEGER)"
            )
            connection.commit()
        finally:
            connection.close()

    def run_git(self, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(directory), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def task(
        self,
        identifier: str = "finished-task",
        *,
        branch: str | None = None,
        cwd: Path | None = None,
        archived: bool = True,
        timestamp: int | None = None,
        archive_timestamp: int | None = None,
    ) -> None:
        current = int(datetime.now().timestamp()) if timestamp is None else timestamp
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    str(self.worktree if cwd is None else cwd),
                    self.branch if branch is None else branch,
                    archived,
                    current,
                    current,
                    (current if archive_timestamp is None else archive_timestamp)
                    if archived
                    else None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def merge(self) -> None:
        self.run_git(self.repository, "merge", "--no-ff", self.branch, "-m", "land task")

    def cleanup(self, *, completed: set[str] | None = None, dry_run: bool = False) -> dict:
        output = io.StringIO()
        result = cleanup.run_cleanup(
            database=self.database,
            target_day=self.day,
            completed_ids=set() if completed is None else completed,
            dry_run=dry_run,
            stream=output,
        )
        report = json.loads(output.getvalue())
        self.assertEqual(result, 1 if report["failures"] else 0)
        return report

    def assert_branch_exists(self) -> None:
        self.run_git(self.repository, "rev-parse", "--verify", f"refs/heads/{self.branch}")

    def test_removes_clean_merged_archived_task_worktree_and_branch(self) -> None:
        self.merge()
        self.task()

        report = self.cleanup()

        self.assertEqual(report["branches_cleaned"], [self.branch], report)
        self.assertEqual(report["worktrees_removed"], [str(self.worktree)])
        self.assertFalse(self.worktree.exists())
        self.assertNotIn(self.branch, self.run_git(self.repository, "branch", "--list").stdout)

    def test_removes_only_explicitly_verified_completed_unarchived_task(self) -> None:
        self.merge()
        self.task(archived=False)

        report = self.cleanup(completed={"finished-task"})

        self.assertEqual(report["branches_cleaned"], [self.branch], report)

    def test_ignores_unverified_unarchived_task(self) -> None:
        self.merge()
        self.task(archived=False)

        report = self.cleanup()

        self.assertEqual(report["tasks_discovered"], 0)
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_branch_referenced_by_another_unverified_task(self) -> None:
        self.merge()
        self.task()
        self.task("possibly-active", archived=False)

        report = self.cleanup()

        self.assertIn("unverified or active", report["uncertain"][0]["reason"])
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_unmerged_branch(self) -> None:
        self.task()

        report = self.cleanup()

        self.assertIn("not proven merged", report["uncertain"][0]["reason"])
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_dirty_worktree(self) -> None:
        self.merge()
        self.task()
        (self.worktree / "important-untracked-note.md").touch()

        report = self.cleanup()

        self.assertIn("tracked or untracked", report["uncertain"][0]["reason"])
        self.assertTrue((self.worktree / "important-untracked-note.md").exists())
        self.assert_branch_exists()

    def test_preserves_locked_worktree(self) -> None:
        self.merge()
        self.task()
        self.run_git(self.repository, "worktree", "lock", str(self.worktree))

        report = self.cleanup()

        self.assertEqual(report["uncertain"][0]["reason"], "worktree is locked")
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_protected_default_branch(self) -> None:
        self.task(branch="main", cwd=self.repository)

        report = self.cleanup()

        self.assertEqual(report["protected"][0]["reason"], "protected default branch")
        self.assertTrue(self.repository.exists())

    def test_preserves_current_primary_checkout(self) -> None:
        self.run_git(self.repository, "checkout", "-b", "codex/primary-task")
        self.task(branch="codex/primary-task", cwd=self.repository)

        report = self.cleanup()

        self.assertIn("primary worktree", report["protected"][0]["reason"])
        self.assertTrue(self.repository.exists())

    def test_dry_run_reports_eligible_without_mutation(self) -> None:
        self.merge()
        self.task()

        report = self.cleanup(dry_run=True)

        self.assertEqual(report["eligible"][0]["branch"], self.branch)
        self.assertEqual(report["branches_cleaned"], [])
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_archived_task_from_another_day(self) -> None:
        self.merge()
        yesterday = int(datetime.now().timestamp()) - 172800
        self.task(timestamp=yesterday)

        report = self.cleanup()

        self.assertEqual(report["tasks_discovered"], 0)
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_old_archived_task_updated_today(self) -> None:
        self.merge()
        yesterday = int(datetime.now().timestamp()) - 172800
        self.task(archive_timestamp=yesterday)

        report = self.cleanup()

        self.assertEqual(report["tasks_discovered"], 0)
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_preserves_branch_when_task_starts_during_final_revalidation(self) -> None:
        self.merge()
        self.task()
        original_inspect = cleanup.inspect
        inspection_count = 0

        def inspect_and_start_task(*args, **kwargs):
            nonlocal inspection_count
            result = original_inspect(*args, **kwargs)
            inspection_count += 1
            if inspection_count == 1:
                self.task("started-during-cleanup", archived=False)
            return result

        with mock.patch.object(cleanup, "inspect", side_effect=inspect_and_start_task):
            report = self.cleanup()

        self.assertIn("unverified or active", report["uncertain"][0]["reason"])
        self.assertTrue(self.worktree.exists())
        self.assert_branch_exists()

    def test_deduplicates_multiple_archived_tasks_for_one_branch(self) -> None:
        self.merge()
        self.task("finished-one")
        self.task("finished-two")

        report = self.cleanup()

        self.assertEqual(report["tasks_discovered"], 2)
        self.assertEqual(report["branches_cleaned"], [self.branch], report)


if __name__ == "__main__":
    unittest.main()

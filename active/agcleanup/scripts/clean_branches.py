#!/usr/bin/env python3
"""Conservatively remove landed worktrees owned by finished local Codex tasks."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, TextIO


MAX_TASKS = 500
PROTECTED_BRANCHES = frozenset({"main", "master", "trunk", "develop"})


@dataclass(frozen=True)
class Task:
    identifier: str
    cwd: Path
    branch: str
    archived: bool


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None
    locked: bool


def git(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def worktrees(directory: Path) -> list[Worktree]:
    result = git(directory, "worktree", "list", "--porcelain")
    if result.returncode:
        raise ValueError(result.stderr.strip() or "worktree inventory failed")
    found: list[Worktree] = []
    for block in result.stdout.strip().split("\n\n"):
        location: Path | None = None
        branch: str | None = None
        locked = False
        for line in block.splitlines():
            if line.startswith("worktree "):
                location = Path(line.removeprefix("worktree ")).resolve()
            elif line.startswith("branch refs/heads/"):
                branch = line.removeprefix("branch refs/heads/")
            elif line == "locked" or line.startswith("locked "):
                locked = True
        if location is not None:
            found.append(Worktree(location, branch, locked))
    if not found:
        raise ValueError("Git did not return a primary worktree")
    return found


def trusted_base(directory: Path, branch: str) -> str | None:
    head = git(directory, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    refs: list[str] = []
    if head.returncode == 0 and head.stdout.strip():
        refs.append(head.stdout.strip())
    refs.extend(
        ref
        for name in ("main", "master", "trunk")
        for ref in (f"refs/heads/{name}", f"refs/remotes/origin/{name}")
    )
    for ref in dict.fromkeys(refs):
        if ref == f"refs/heads/{branch}":
            continue
        if git(directory, "rev-parse", "--verify", f"{ref}^{{commit}}").returncode == 0:
            return ref
    return None


def day_bounds(target_day: date) -> tuple[int, int]:
    timezone = datetime.now().astimezone().tzinfo
    start = datetime.combine(target_day, time.min, timezone)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def load_tasks(
    database: Path, target_day: date, completed_ids: set[str]
) -> tuple[list[Task], dict[str, set[str]], bool]:
    start, end = day_bounds(target_day)
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        selected = connection.execute(
            """
            SELECT id, cwd, git_branch, archived
            FROM threads
            WHERE git_branch IS NOT NULL AND git_branch != ''
              AND (
                (archived = 1 AND archived_at >= ? AND archived_at < ?)
                OR (archived = 0 AND (updated_at >= ? AND updated_at < ?))
              )
            ORDER BY archived DESC, updated_at DESC, id
            LIMIT ?
            """,
            (start, end, start, end, MAX_TASKS + 1),
        ).fetchall()
        truncated = len(selected) > MAX_TASKS
        tasks = [
            Task(row["id"], Path(row["cwd"]), row["git_branch"], bool(row["archived"]))
            for row in selected[:MAX_TASKS]
            if row["archived"] or row["id"] in completed_ids
        ]
        branches = {task.branch for task in tasks}
        unverified: dict[str, set[str]] = {branch: set() for branch in branches}
        if branches:
            placeholders = ",".join("?" for _ in branches)
            for row in connection.execute(
                f"SELECT id, git_branch FROM threads "
                f"WHERE archived = 0 AND git_branch IN ({placeholders})",
                tuple(branches),
            ):
                if row["id"] not in completed_ids:
                    unverified[row["git_branch"]].add(row["id"])
    finally:
        connection.close()
    return tasks, unverified, truncated


def inspect(task: Task, unverified: set[str], current_directory: Path) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "thread_id": task.identifier,
        "branch": task.branch,
        "task_cwd": str(task.cwd),
        "task_archived": task.archived,
    }
    if task.branch in PROTECTED_BRANCHES:
        return candidate | {"outcome": "protected", "reason": "protected default branch"}
    if unverified:
        return candidate | {
            "outcome": "uncertain",
            "reason": "branch is referenced by unverified or active tasks",
            "unverified_thread_count": len(unverified),
            "unverified_thread_ids": sorted(unverified)[:10],
            "unverified_thread_ids_truncated": len(unverified) > 10,
        }
    if not task.cwd.is_absolute() or not task.cwd.is_dir():
        return candidate | {"outcome": "uncertain", "reason": "task checkout is inaccessible"}
    repository_result = git(task.cwd, "rev-parse", "--show-toplevel")
    if repository_result.returncode:
        return candidate | {"outcome": "uncertain", "reason": "task checkout is not a local Git repository"}
    checkout = Path(repository_result.stdout.strip()).resolve()
    registered = worktrees(checkout)
    repository = registered[0].path
    candidate["repository"] = str(repository)
    matches = [entry for entry in registered if entry.branch == task.branch]
    if len(matches) != 1:
        reason = "no exact registered linked worktree" if not matches else "branch has ambiguous worktrees"
        return candidate | {"outcome": "uncertain", "reason": reason}
    target = matches[0]
    candidate["worktree"] = str(target.path)
    if target.path == registered[0].path:
        return candidate | {"outcome": "protected", "reason": "branch is checked out in the primary worktree"}
    if target.locked:
        return candidate | {"outcome": "uncertain", "reason": "worktree is locked"}
    if target.path == current_directory or target.path in current_directory.parents:
        return candidate | {"outcome": "protected", "reason": "worktree contains the current working directory"}
    if not target.path.is_absolute() or target.path in {Path("/"), Path.home().resolve()}:
        return candidate | {"outcome": "protected", "reason": "worktree path is unsafe"}
    if not target.path.is_dir():
        return candidate | {"outcome": "uncertain", "reason": "registered worktree is inaccessible"}
    actual_branch = git(target.path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if actual_branch.returncode or actual_branch.stdout.strip() != task.branch:
        return candidate | {"outcome": "uncertain", "reason": "worktree branch identity does not match"}
    status = git(target.path, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode:
        return candidate | {"outcome": "uncertain", "reason": "worktree cleanliness could not be verified"}
    if status.stdout.strip():
        return candidate | {"outcome": "uncertain", "reason": "worktree contains tracked or untracked changes"}
    base = trusted_base(repository, task.branch)
    if base is None:
        return candidate | {"outcome": "uncertain", "reason": "trusted default-branch reference is unavailable"}
    candidate["base_ref"] = base
    branch_ref = f"refs/heads/{task.branch}"
    ancestry = git(repository, "merge-base", "--is-ancestor", branch_ref, base)
    if ancestry.returncode:
        return candidate | {"outcome": "uncertain", "reason": "branch is not proven merged into the default branch"}
    return candidate | {"outcome": "eligible"}


def run_cleanup(
    *,
    database: Path,
    target_day: date,
    completed_ids: set[str],
    dry_run: bool = False,
    stream: TextIO | None = None,
) -> int:
    output = sys.stdout if stream is None else stream
    report: dict[str, Any] = {
        "date": target_day.isoformat(),
        "scope": "local",
        "dry_run": dry_run,
        "completed_thread_ids_verified": len(completed_ids),
        "tasks_discovered": 0,
        "branches_cleaned": [],
        "worktrees_removed": [],
        "eligible": [],
        "uncertain": [],
        "protected": [],
        "failures": [],
        "candidate_coverage_partial": False,
    }
    try:
        tasks, unverified, truncated = load_tasks(database, target_day, completed_ids)
        report["tasks_discovered"] = len(tasks)
        report["candidate_coverage_partial"] = truncated
        seen: set[tuple[str, str]] = set()
        current_directory = Path.cwd().resolve()
        for task in tasks:
            key = (str(task.cwd), task.branch)
            if key in seen:
                continue
            seen.add(key)
            try:
                result = inspect(task, unverified.get(task.branch, set()), current_directory)
                outcome = result["outcome"]
                if outcome != "eligible":
                    report[outcome].append(result)
                    continue
                if dry_run:
                    report["eligible"].append(result)
                    continue
                current_tasks, current_unverified, current_truncated = load_tasks(
                    database, target_day, completed_ids
                )
                report["candidate_coverage_partial"] |= current_truncated
                current_task = next(
                    (candidate for candidate in current_tasks if candidate.identifier == task.identifier),
                    None,
                )
                if current_task != task:
                    report["uncertain"].append(
                        result | {"outcome": "uncertain", "reason": "task lifecycle changed during revalidation"}
                    )
                    continue
                revalidated = inspect(
                    current_task, current_unverified.get(task.branch, set()), current_directory
                )
                if revalidated["outcome"] != "eligible":
                    report[revalidated["outcome"]].append(revalidated)
                    continue
                if revalidated != result:
                    report["uncertain"].append(
                        result | {"outcome": "uncertain", "reason": "worktree state changed during revalidation"}
                    )
                    continue
                repository = Path(result["repository"])
                removal = git(repository, "worktree", "remove", result["worktree"])
                if removal.returncode:
                    report["failures"].append(result | {"error": removal.stderr.strip()})
                    continue
                report["worktrees_removed"].append(result["worktree"])
                deletion = git(repository, "branch", "-d", "--", task.branch)
                if deletion.returncode:
                    report["failures"].append(
                        result | {"error": deletion.stderr.strip(), "worktree_removed": True}
                    )
                    continue
                report["branches_cleaned"].append(task.branch)
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                report["failures"].append(
                    {"thread_id": task.identifier, "branch": task.branch, "error": str(error)}
                )
    except (OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        report["failures"].append({"error": str(error)})
    report["status"] = "failed" if report["failures"] else "success"
    print(json.dumps(report, sort_keys=True), file=output)
    return 1 if report["failures"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--completed-thread-id", action="append", default=[])
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--state-db",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "state_5.sqlite",
    )
    arguments = parser.parse_args()
    return run_cleanup(
        database=arguments.state_db,
        target_day=arguments.date,
        completed_ids=set(arguments.completed_thread_id),
        dry_run=arguments.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Tests for bounded Codex rollout activity collection."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
workspace_rollouts = importlib.import_module("workspace_rollouts")


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class WorkspaceRolloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.codex_home = Path(self._tmp.name)
        self.sessions = self.codex_home / "sessions"
        self.archived = self.codex_home / "archived_sessions"
        self.sessions.mkdir()
        self.archived.mkdir()
        self.start = utc("2026-08-28T00:00:00Z")
        self.end = utc("2026-08-29T00:00:00Z")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_rollout(self, root: Path, name: str, records: list[dict[str, Any]]) -> Path:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def session_meta(
        self,
        *,
        task_id: str = "owner-session",
        cwd: str = "/initial",
        source: Any = "vscode",
    ) -> dict[str, Any]:
        return {
            "type": "session_meta",
            "timestamp": "2026-08-28T12:00:00Z",
            "payload": {
                "id": task_id,
                "session_id": "thread-session",
                "timestamp": "2026-08-28T12:00:00Z",
                "cwd": cwd,
                "source": source,
            },
        }

    def task_started(self, turn_id: str, when: str) -> dict[str, Any]:
        return {
            "type": "event_msg",
            "timestamp": when,
            "payload": {"type": "task_started", "turn_id": turn_id, "started_at": utc(when).timestamp()},
        }

    def turn_context(self, turn_id: str, cwd: str) -> dict[str, Any]:
        return {"type": "turn_context", "timestamp": "2026-08-28T12:00:01Z", "payload": {"turn_id": turn_id, "cwd": cwd}}

    def user_message(
        self,
        text: str,
        *,
        turn_id: str,
        message_id: str = "message-1",
        create_time: str = "2026-08-28T12:00:02Z",
    ) -> dict[str, Any]:
        return {
            "type": "response_item",
            "timestamp": "2026-08-28T12:00:03Z",
            "payload": {
                "type": "message",
                "role": "user",
                "id": message_id,
                "content": [{"type": "input_text", "text": text}],
                "internal_chat_message_metadata_passthrough": {
                    "turn_id": turn_id,
                    "create_time": utc(create_time).timestamp(),
                },
            },
        }

    def collect(self) -> tuple[list[dict[str, Any]], list[str]]:
        return workspace_rollouts.collect_work(self.codex_home, self.start, self.end)

    def test_old_rollout_file_uses_recent_native_turn_time_first_owner_and_per_turn_cwd(self) -> None:
        path = self.write_rollout(
            self.sessions,
            "2026/08/14/rollout-2026-08-14T09-00-00-owner-session.jsonl",
            [
                self.session_meta(task_id="first-owner", cwd="/meta-cwd"),
                self.session_meta(task_id="copied-parent", cwd="/wrong-cwd"),
                self.task_started("turn-a", "2026-08-28T12:00:00Z"),
                self.turn_context("turn-a", "/repo/current"),
                self.user_message("Investigate the workspace rollout collector", turn_id="turn-a"),
            ],
        )
        old_timestamp = utc("2026-08-14T09:00:00Z").timestamp()
        os.utime(path, (old_timestamp, old_timestamp))

        activities, warnings = self.collect()

        self.assertEqual(warnings, [])
        self.assertEqual(len(activities), 1)
        self.assertEqual(
            activities[0],
            {
                "task_id": "first-owner",
                "path": str(path),
                "line": 5,
                "occurred_at": "2026-08-28T12:00:02+00:00",
                "cwd": "/repo/current",
                "text": "Investigate the workspace rollout collector",
            },
        )

    def test_reads_archived_sessions_and_keeps_brief_followup_with_task_context(self) -> None:
        self.write_rollout(
            self.archived,
            "rollout-2026-08-28T13-00-00-archived.jsonl",
            [
                self.session_meta(task_id="archived-owner", cwd="/repo"),
                self.task_started("turn-a", "2026-08-28T13:00:00Z"),
                self.turn_context("turn-a", "/repo"),
                self.user_message("Review the mem workspace build spec", turn_id="turn-a", message_id="message-a"),
                self.task_started("turn-b", "2026-08-28T13:10:00Z"),
                self.turn_context("turn-b", "/repo"),
                self.user_message("also check archived sessions", turn_id="turn-b", message_id="message-b", create_time="2026-08-28T13:10:01Z"),
            ],
        )

        activities, warnings = self.collect()

        self.assertEqual(warnings, [])
        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[1]["task_id"], "archived-owner")
        self.assertEqual(activities[1]["cwd"], "/repo")
        self.assertEqual(
            activities[1]["text"],
            "Task context: Review the mem workspace build spec\nFollow-up: also check archived sessions",
        )

    def test_excludes_delegated_subagents_automation_generated_prompts_and_non_user_items(self) -> None:
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T14-00-00-subagent.jsonl",
            [
                self.session_meta(source={"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}}),
                self.task_started("turn-a", "2026-08-28T14:00:00Z"),
                self.user_message("Do delegated work", turn_id="turn-a"),
            ],
        )
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T14-05-00-automation.jsonl",
            [
                self.session_meta(task_id="automation", source={"automation": {"name": "mem-workspace-build"}}),
                self.task_started("turn-a", "2026-08-28T14:05:00Z"),
                self.user_message("Scheduled task", turn_id="turn-a"),
            ],
        )
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T14-10-00-generated.jsonl",
            [
                self.session_meta(task_id="root"),
                self.task_started("turn-a", "2026-08-28T14:10:00Z"),
                self.user_message("mem workspace build: produce constrained JSON output-schema", turn_id="turn-a"),
                self.task_started("turn-b", "2026-08-28T14:11:00Z"),
                self.user_message(
                    "# AGENTS.md instructions\n\n<INSTRUCTIONS>\nrepo rules\n</INSTRUCTIONS>",
                    turn_id="turn-b",
                    message_id="generated-agents",
                    create_time="2026-08-28T14:11:01Z",
                ),
                self.task_started("turn-c", "2026-08-28T14:12:00Z"),
                self.user_message(
                    "<codex_delegation><source_thread_id>parent</source_thread_id><input>Task: collect workspace</input></codex_delegation>",
                    turn_id="turn-c",
                    message_id="generated-delegation",
                    create_time="2026-08-28T14:12:01Z",
                ),
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": "assistant output"}},
                {"type": "response_item", "payload": {"type": "function_call_output", "content": "tool output"}},
            ],
        )

        activities, warnings = self.collect()

        self.assertEqual(warnings, [])
        self.assertEqual(activities, [])

    def test_strips_stacked_injected_context_without_dropping_user_request(self) -> None:
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T14-30-00-wrapper.jsonl",
            [
                self.session_meta(task_id="wrapped-owner"),
                self.task_started("turn-a", "2026-08-28T14:30:00Z"),
                self.user_message(
                    (
                        "<recommended_plugins>\nplugin list\n</recommended_plugins>"
                        "# AGENTS.md instructions\n\n<INSTRUCTIONS>\nrepo rules\n</INSTRUCTIONS>"
                        "<environment_context>\nworkspace metadata\n</environment_context>"
                        "Continue the workspace rollout implementation."
                    ),
                    turn_id="turn-a",
                ),
            ],
        )

        activities, warnings = self.collect()

        self.assertEqual(warnings, [])
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["text"], "Continue the workspace rollout implementation.")

    def test_deduplicates_copied_user_fork_history_and_filters_by_native_create_time(self) -> None:
        copied_old = self.user_message(
            "Old native request copied into a recent fork",
            turn_id="turn-old",
            message_id="copied-old",
            create_time="2026-08-20T10:00:00Z",
        )
        copied_old["timestamp"] = "2026-08-28T15:00:03Z"
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T15-00-00-fork.jsonl",
            [
                self.session_meta(task_id="fork-owner"),
                self.task_started("turn-old", "2026-08-28T15:00:00Z"),
                copied_old,
                self.task_started("turn-a", "2026-08-28T15:10:00Z"),
                self.user_message("Native fork request", turn_id="turn-a", message_id="same-user-message", create_time="2026-08-28T15:10:01Z"),
            ],
        )
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T15-20-00-parent-copy.jsonl",
            [
                self.session_meta(task_id="parent-owner"),
                self.task_started("turn-b", "2026-08-28T15:20:00Z"),
                self.user_message("Native fork request", turn_id="turn-b", message_id="same-user-message", create_time="2026-08-28T15:10:01Z"),
            ],
        )

        activities, warnings = self.collect()

        self.assertEqual(warnings, [])
        self.assertEqual([activity["text"] for activity in activities], ["Native fork request"])

    def test_missing_root_warns_and_empty_home_without_roots_fails(self) -> None:
        self.archived.rmdir()
        self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T16-00-00-owner.jsonl",
            [
                self.session_meta(),
                self.task_started("turn-a", "2026-08-28T16:00:00Z"),
                self.user_message("Collect active sessions", turn_id="turn-a"),
            ],
        )

        activities, warnings = self.collect()

        self.assertEqual(len(activities), 1)
        self.assertIn(f"missing rollout root: {self.archived}", warnings)

        empty_home = self.codex_home / "empty"
        empty_home.mkdir()
        with self.assertRaisesRegex(RuntimeError, "no readable rollout roots"):
            workspace_rollouts.collect_work(empty_home, self.start, self.end)

    def test_root_enumeration_failures_do_not_count_as_successful_scans(self) -> None:
        with mock.patch.object(workspace_rollouts, "_iter_rollout_files", side_effect=OSError("permission denied")):
            with self.assertRaisesRegex(RuntimeError, "no readable rollout roots"):
                self.collect()

    def test_all_stat_failures_fail_collection_clearly(self) -> None:
        path = self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T17-00-00-owner.jsonl",
            [
                self.session_meta(),
                self.task_started("turn-a", "2026-08-28T17:00:00Z"),
                self.user_message("Collect active sessions", turn_id="turn-a"),
            ],
        )

        original_stat = Path.stat

        def fail_rollout_stat(target: Path, *args: Any, **kwargs: Any) -> os.stat_result:
            if target == path:
                raise OSError("stat denied")
            return original_stat(target, *args, **kwargs)

        with mock.patch.object(workspace_rollouts, "_iter_rollout_files", return_value=iter([path])):
            with mock.patch.object(Path, "stat", fail_rollout_stat):
                with self.assertRaisesRegex(RuntimeError, "all rollout files failed"):
                    self.collect()

    def test_rollout_file_cap_warns_for_full_store_and_prefers_newest_candidates(self) -> None:
        oldest = self.write_rollout(
            self.sessions,
            "rollout-2026-08-27T18-00-00-old.jsonl",
            [
                self.session_meta(task_id="oldest-owner"),
                self.task_started("turn-oldest", "2026-08-28T18:00:00Z"),
                self.user_message("Oldest modified rollout", turn_id="turn-oldest", message_id="oldest-message"),
            ],
        )
        middle = self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T18-05-00-middle.jsonl",
            [
                self.session_meta(task_id="middle-owner"),
                self.task_started("turn-middle", "2026-08-28T18:05:00Z"),
                self.user_message("Middle modified rollout", turn_id="turn-middle", message_id="middle-message"),
            ],
        )
        newest = self.write_rollout(
            self.sessions,
            "rollout-2026-08-28T18-10-00-newest.jsonl",
            [
                self.session_meta(task_id="newest-owner"),
                self.task_started("turn-new", "2026-08-28T18:10:00Z"),
                self.user_message("Newest modified rollout", turn_id="turn-new", message_id="newest-message"),
            ],
        )
        os.utime(oldest, (utc("2026-08-20T18:00:00Z").timestamp(), utc("2026-08-20T18:00:00Z").timestamp()))
        os.utime(middle, (utc("2026-08-28T18:05:00Z").timestamp(), utc("2026-08-28T18:05:00Z").timestamp()))
        os.utime(newest, (utc("2026-08-28T18:10:00Z").timestamp(), utc("2026-08-28T18:10:00Z").timestamp()))

        with mock.patch.object(workspace_rollouts, "MAX_ROLLOUT_FILES", 2):
            activities, warnings = self.collect()

        self.assertEqual([activity["text"] for activity in activities], ["Middle modified rollout", "Newest modified rollout"])
        self.assertEqual([activity["task_id"] for activity in activities], ["middle-owner", "newest-owner"])
        self.assertEqual(
            warnings,
            [f"partial scan: {self.sessions} has 3 rollout files; scanned newest 2"],
        )

    def test_requires_timezone_aware_window(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            workspace_rollouts.collect_work(
                self.codex_home,
                datetime(2026, 8, 28),
                datetime(2026, 8, 29, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()

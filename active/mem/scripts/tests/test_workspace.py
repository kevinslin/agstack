#!/usr/bin/env python3
"""Process-level workspace index builder coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SCRIPT_DIR / "mem.py"
sys.path.insert(0, str(SCRIPT_DIR))

import base_index


FAKE_CODEX = '''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
packet = json.loads(prompt.split("Collected evidence:\\n", 1)[1])
capture = os.environ.get("WORKSPACE_TEST_CAPTURE")
if capture:
    pathlib.Path(capture).write_text(json.dumps({"args": args, "packet": packet,
        "schema": json.loads(pathlib.Path(args[args.index("--output-schema") + 1]).read_text())}))
mode = os.environ.get("WORKSPACE_TEST_MODE", "success")
projects = []
if packet["activity"]:
    source_id = packet["activity"][0]["id"]
    repo_ids = [repo["id"] for repo in packet["resources"]["repos"]]
    if mode == "invented":
        repo_ids = ["repo:missing"]
    relevant = []
    if packet["resources"]["relevant"]:
        relevant.append({"id": packet["resources"]["relevant"][0]["id"],
                         "reason": "Design note for the selected project."})
    projects.append({
        "name": "Workspace Builder",
        "description": "Build the mem workspace index.",
        "aliases": ["mem workspace"],
        "priority": 1,
        "priority_reason": "The latest task implements the builder.",
        "base_ids": [base["id"] for base in packet["resources"]["bases"]],
        "repo_ids": repo_ids,
        "relevant": relevant,
        "source_ids": [source_id],
    })
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps({"projects": projects}))
print(json.dumps({"type": "turn.completed"}))
'''


class WorkspaceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve(strict=False)
        self.home = self.root / "home"
        self.codex_home = self.root / "codex"
        self.bin = self.root / "bin"
        self.repo = self.root / "repo"
        self.notes = self.repo / "notes"
        self.subdir = self.repo / "src" / "tool"
        self.output_path = self.home / ".mem" / "workspace" / "index.json"
        self.capture = self.root / "capture.json"
        self.home.mkdir()
        self.codex_home.mkdir()
        self.bin.mkdir()
        (self.codex_home / "sessions").mkdir()
        (self.codex_home / "archived_sessions").mkdir()
        self.notes.mkdir(parents=True)
        self.subdir.mkdir(parents=True)
        codex = self.bin / "codex"
        codex.write_text(FAKE_CODEX, encoding="utf-8")
        codex.chmod(0o755)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "CODEX_HOME": str(self.codex_home),
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "TZ": "UTC",
            "WORKSPACE_TEST_CAPTURE": str(self.capture),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_workspace(
        self,
        *args: str,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "build", *args],
            text=True,
            capture_output=True,
            check=False,
            env=env or self.env,
            cwd=cwd or self.root,
        )

    def write_configured_repo(self) -> Path:
        (self.notes / "design.md").write_text("# Design\n", encoding="utf-8")
        config = self.repo / ".mem.yaml"
        config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                bases:
                  - name: repo
                    description: Repository notes.
                    root: {self.repo}
                    managed_root: notes
                    path_style: directory
                    schemas:
                      - name: project
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", str(self.repo)], text=True, capture_output=True, check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "config",
                "remote.origin.url",
                "https://token:secret@example.com/acme/repo.git",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        base_index.build_index(
            {
                "managed_root": str(self.notes),
                "index_path": str(self.notes / ".mem.index.json"),
                "path_style": "directory",
            }
        )
        return config

    def write_rollout(self, *, text: str = "Implement the workspace index builder.") -> Path:
        path = self.codex_home / "sessions" / "rollout-2026-08-30T20-00-00-owner.jsonl"
        created = time.time() - 60
        records: list[dict[str, Any]] = [
            {
                "type": "session_meta",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"id": "owner-task", "session_id": "session", "cwd": str(self.repo), "source": "test"},
            },
            {
                "type": "event_msg",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"type": "task_started", "turn_id": "turn-a", "started_at": created},
            },
            {
                "type": "turn_context",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"turn_id": "turn-a", "cwd": str(self.subdir)},
            },
            {
                "type": "response_item",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "type": "message",
                    "role": "user",
                    "id": "message-a",
                    "content": [{"type": "input_text", "text": text}],
                    "internal_chat_message_metadata_passthrough": {
                        "turn_id": "turn-a",
                        "create_time": created,
                    },
                },
            },
        ]
        path.write_text(
            "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def test_empty_build_publishes_valid_snapshot_without_runner(self) -> None:
        result = self.run_workspace("--pretty")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["path"], str(self.output_path))
        self.assertEqual(summary["project_count"], 0)
        self.assertFalse(summary["partial"])
        self.assertFalse(self.capture.exists())
        snapshot = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["projects"], [])
        self.assertEqual(snapshot["window"]["timezone"], "UTC")
        self.assertEqual(self.output_path.stat().st_mode & 0o777, 0o600)

    def test_build_hydrates_model_project_from_collected_resource_ids(self) -> None:
        config = self.write_configured_repo()
        rollout = self.write_rollout()
        index_before = (self.notes / ".mem.index.json").read_bytes()

        result = self.run_workspace()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((self.notes / ".mem.index.json").read_bytes(), index_before)
        snapshot = json.loads(self.output_path.read_text(encoding="utf-8"))
        project = snapshot["projects"][0]
        self.assertEqual(
            project["bases"],
            [{"config_path": str(config.resolve()), "name": "repo", "root": str(self.repo.resolve())}],
        )
        self.assertEqual(
            project["repos"],
            [{"name": "repo", "path": str(self.repo.resolve()), "remote": "https://example.com/acme/repo.git"}],
        )
        self.assertEqual(project["relevant"][0]["path"], str((self.notes / "design.md").resolve()))
        self.assertEqual(project["sources"], [{"task_id": "owner-task", "path": str(rollout), "line": 4}])
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertEqual(
            set(captured["packet"]),
            {"generated_at", "window", "activity", "resources", "warnings", "instructions"},
        )
        self.assertEqual(captured["schema"]["required"], ["projects"])
        self.assertIn("description", captured["schema"]["properties"]["projects"]["items"]["required"])

    def test_current_caller_base_and_repo_are_candidate_resources(self) -> None:
        historical_config = self.write_configured_repo()
        rollout = self.write_rollout()
        caller = self.root / "caller"
        caller_notes = caller / "notes"
        caller_notes.mkdir(parents=True)
        (caller_notes / "design.md").write_text("# Caller Design\n", encoding="utf-8")
        caller_config = caller / ".mem.yaml"
        caller_config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                bases:
                  - name: caller
                    description: Caller project notes.
                    root: {caller}
                    managed_root: notes
                    path_style: directory
                    schemas:
                      - name: project
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", str(caller)], text=True, capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(caller), "config", "remote.origin.url", "git@example.com:acme/caller.git"],
            text=True,
            capture_output=True,
            check=True,
        )
        base_index.build_index(
            {
                "managed_root": str(caller_notes),
                "index_path": str(caller_notes / ".mem.index.json"),
                "path_style": "directory",
            }
        )
        historical_index = (self.notes / ".mem.index.json").read_bytes()
        caller_index = (caller_notes / ".mem.index.json").read_bytes()

        result = self.run_workspace(cwd=caller)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((self.notes / ".mem.index.json").read_bytes(), historical_index)
        self.assertEqual((caller_notes / ".mem.index.json").read_bytes(), caller_index)
        snapshot = json.loads(self.output_path.read_text(encoding="utf-8"))
        project = snapshot["projects"][0]
        self.assertEqual(
            sorted(project["bases"], key=lambda item: item["name"]),
            [
                {"config_path": str(caller_config.resolve()), "name": "caller", "root": str(caller.resolve())},
                {"config_path": str(historical_config.resolve()), "name": "repo", "root": str(self.repo.resolve())},
            ],
        )
        self.assertEqual(
            sorted((repo["name"], repo["path"], repo["remote"]) for repo in project["repos"]),
            [
                ("caller", str(caller.resolve()), "git@example.com:acme/caller.git"),
                ("repo", str(self.repo.resolve()), "https://example.com/acme/repo.git"),
            ],
        )
        self.assertEqual(project["sources"], [{"task_id": "owner-task", "path": str(rollout), "line": 4}])

    def test_long_activity_text_warns_partial_and_truncates_runner_packet(self) -> None:
        self.write_configured_repo()
        self.write_rollout(text="x" * 2000)

        result = self.run_workspace()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("warning: partial text: truncated collected activity", result.stderr)
        self.assertTrue(json.loads(result.stdout)["partial"])
        captured = json.loads(self.capture.read_text(encoding="utf-8"))
        self.assertLessEqual(len(captured["packet"]["activity"][0]["text"]), 1200)

    def test_unknown_model_candidate_id_preserves_previous_index(self) -> None:
        self.write_configured_repo()
        self.write_rollout()
        self.output_path.parent.mkdir(parents=True)
        self.output_path.write_text('{"previous": true}\n', encoding="utf-8")
        env = {**self.env, "WORKSPACE_TEST_MODE": "invented"}

        result = self.run_workspace(env=env)

        self.assertEqual(result.returncode, 1)
        self.assertIn("error: validation:", result.stderr)
        self.assertIn("repo:missing", result.stderr)
        self.assertEqual(self.output_path.read_text(encoding="utf-8"), '{"previous": true}\n')

    def test_collection_failure_preserves_previous_index(self) -> None:
        for root in (self.codex_home / "sessions", self.codex_home / "archived_sessions"):
            root.rmdir()
        self.output_path.parent.mkdir(parents=True)
        self.output_path.write_text('{"previous": true}\n', encoding="utf-8")

        result = self.run_workspace()

        self.assertEqual(result.returncode, 1)
        self.assertIn("error: collection:", result.stderr)
        self.assertEqual(self.output_path.read_text(encoding="utf-8"), '{"previous": true}\n')

    def test_publish_rejects_output_symlink_without_overwriting_target(self) -> None:
        target = self.root / "target.json"
        target.write_text('{"target": true}\n', encoding="utf-8")
        self.output_path.parent.mkdir(parents=True)
        self.output_path.symlink_to(target)

        result = self.run_workspace()

        self.assertEqual(result.returncode, 1)
        self.assertIn("error: publish:", result.stderr)
        self.assertIn("unsafe output path", result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), '{"target": true}\n')


if __name__ == "__main__":
    unittest.main()

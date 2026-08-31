#!/usr/bin/env python3
"""Process-level workspace lookup coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TEST_DIR.parents[0] / "mem.py"


class WorkspaceLookupCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve(strict=False)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.index_path = self.home / ".mem" / "workspace" / "index.json"
        self.config_path = self.root / ".mem.yaml"
        self.base_index_path = self.root / "notes" / ".mem.index.json"
        self.codex_marker = self.root / "codex-called"
        self.home.mkdir()
        self.bin.mkdir()
        self.index_path.parent.mkdir(parents=True)
        self.base_index_path.parent.mkdir()
        self.config_path.write_text("version: 2\nbases: []\n", encoding="utf-8")
        self.base_index_path.write_text('{"document_count":0}\n', encoding="utf-8")
        codex = self.bin / "codex"
        codex.write_text(
            textwrap.dedent(
                f"""
                #!/bin/sh
                touch {self.codex_marker}
                exit 23
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        codex.chmod(0o755)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_mem(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            text=True,
            capture_output=True,
            check=False,
            env=self.env,
            cwd=self.root,
        )

    def write_index(self, projects: list[dict[str, Any]]) -> None:
        payload = {
            "generated_at": "2026-08-31T12:00:00+00:00",
            "window": {
                "start": "2026-08-24T12:00:00+00:00",
                "end": "2026-08-31T12:00:00+00:00",
                "timezone": "UTC",
            },
            "partial": False,
            "log_path": "logs/workspace-20260831T120000Z-test.log",
            "projects": projects,
        }
        self.index_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def project(
        self,
        name: str,
        *,
        aliases: list[str],
        priority: int,
        description: str,
        priority_reason: str,
        repo: Path,
        relevant_path: Path,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "aliases": aliases,
            "priority": priority,
            "priority_reason": priority_reason,
            "bases": [
                {
                    "config_path": str(self.config_path),
                    "name": "notes",
                    "root": str(repo),
                }
            ],
            "repos": [
                {
                    "name": repo.name,
                    "path": str(repo),
                    "remote": None,
                }
            ],
            "relevant": [
                {
                    "name": relevant_path.stem,
                    "path": str(relevant_path),
                    "reason": f"{name} uses {relevant_path.name}.",
                }
            ],
            "sources": [
                {
                    "task_id": f"{name.casefold().replace(' ', '-')}-task",
                    "path": str(self.root / "rollouts" / f"{name}.jsonl"),
                    "lines": [8, 13],
                }
            ],
        }

    def fixture_projects(self) -> tuple[Path, list[dict[str, Any]]]:
        shared_repo = self.root / "repos" / "shared"
        agmem_doc = shared_repo / "specs" / "03-agent-workspace-files" / "spec.md"
        claw_doc = shared_repo / "docs" / "claw" / "design.md"
        other_repo = self.root / "repos" / "other"
        parser_doc = other_repo / "notes" / "parser.md"
        return shared_repo, [
            self.project(
                "OpenClaw Enterprise",
                aliases=["claw ent"],
                priority=1,
                description="Enterprise driver work.",
                priority_reason="Cluster driver follow-up.",
                repo=shared_repo,
                relevant_path=claw_doc,
            ),
            self.project(
                "Build context for agents",
                aliases=["agmem", "mem workspace"],
                priority=2,
                description="Workspace lookup and snapshot builder.",
                priority_reason="Parser lookup code repeated parser parser parser evidence.",
                repo=shared_repo,
                relevant_path=agmem_doc,
            ),
            self.project(
                "Parser Maintenance",
                aliases=["parser"],
                priority=3,
                description="Parser parser parser parser maintenance.",
                priority_reason="Parser parser parser parser cleanup.",
                repo=other_repo,
                relevant_path=parser_doc,
            ),
        ]

    def test_exact_alias_uses_compact_projection_and_sources_are_opt_in(self) -> None:
        self.write_index(self.fixture_projects()[1])

        compact = self.run_mem("workspace", "lookup", "--query", "AGMEM")

        self.assertEqual(compact.returncode, 0, msg=compact.stderr)
        payload = json.loads(compact.stdout)
        self.assertEqual(payload["status"], "matched")
        self.assertEqual(payload["index_path"], str(self.index_path))
        self.assertEqual(payload["snapshot"]["generated_at"], "2026-08-31T12:00:00+00:00")
        self.assertEqual([project["name"] for project in payload["projects"]], ["Build context for agents"])
        self.assertEqual(
            set(payload["projects"][0]),
            {"name", "description", "aliases", "priority"},
        )

        sourced = self.run_mem("workspace", "lookup", "--query", "AGMEM", "--include-sources", "--pretty")

        self.assertEqual(sourced.returncode, 0, msg=sourced.stderr)
        project = json.loads(sourced.stdout)["projects"][0]
        self.assertIn("bases", project)
        self.assertIn("repos", project)
        self.assertEqual(project["sources"][0]["lines"], [8, 13])
        self.assertEqual(project["relevant"][0]["name"], "specs/03-agent-workspace-files/spec.md")

    def test_shared_repo_path_query_returns_all_matching_projects(self) -> None:
        shared_repo, projects = self.fixture_projects()
        self.write_index(projects)

        result = self.run_mem("workspace", "lookup", "--query", str(shared_repo), "--details")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [project["name"] for project in payload["projects"]],
            ["OpenClaw Enterprise", "Build context for agents"],
        )

    def test_relevance_sorts_before_priority_after_exact_matching(self) -> None:
        self.write_index(self.fixture_projects()[1])

        result = self.run_mem("workspace", "lookup", "--query", "parser")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [project["name"] for project in payload["projects"]],
            ["Parser Maintenance", "Build context for agents"],
        )

    def test_no_query_lists_all_projects_by_priority(self) -> None:
        self.write_index(list(reversed(self.fixture_projects()[1])))

        result = self.run_mem("workspace", "lookup")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            [project["name"] for project in payload["projects"]],
            ["OpenClaw Enterprise", "Build context for agents", "Parser Maintenance"],
        )

    def test_empty_missing_and_malformed_indexes_are_clear(self) -> None:
        empty_payload = {
            "generated_at": "2026-08-31T12:00:00+00:00",
            "window": {
                "start": "2026-08-24T12:00:00+00:00",
                "end": "2026-08-31T12:00:00+00:00",
                "timezone": "UTC",
            },
            "partial": False,
            "log_path": "logs/workspace-20260831T120000Z-test.log",
            "projects": [],
        }
        self.index_path.write_text(json.dumps(empty_payload) + "\n", encoding="utf-8")

        empty = self.run_mem("workspace", "lookup", "--query", "missing")

        self.assertEqual(empty.returncode, 0, msg=empty.stderr)
        self.assertEqual(json.loads(empty.stdout)["status"], "no_matches")

        self.index_path.unlink()
        missing = self.run_mem("workspace", "lookup")

        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stdout, "")
        self.assertIn("workspace index does not exist", missing.stderr)

        self.index_path.write_text("{bad json\n", encoding="utf-8")
        malformed = self.run_mem("workspace", "lookup")

        self.assertEqual(malformed.returncode, 1)
        self.assertIn("workspace index is malformed JSON", malformed.stderr)

    def test_lookup_is_read_only_and_does_not_call_codex(self) -> None:
        self.write_index(self.fixture_projects()[1])
        index_before = self.index_path.read_bytes()
        config_before = self.config_path.read_bytes()
        base_index_before = self.base_index_path.read_bytes()

        result = self.run_mem("workspace", "lookup", "--query", "workspace", "--include-sources")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.index_path.read_bytes(), index_before)
        self.assertEqual(self.config_path.read_bytes(), config_before)
        self.assertEqual(self.base_index_path.read_bytes(), base_index_before)
        self.assertFalse(self.codex_marker.exists())

    def test_malformed_project_shape_is_rejected(self) -> None:
        self.write_index(self.fixture_projects()[1])
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        del payload["projects"][0]["sources"][0]["lines"]
        payload["projects"][0]["sources"][0]["line"] = 8
        self.index_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        result = self.run_mem("workspace", "lookup")

        self.assertEqual(result.returncode, 1)
        self.assertIn("projects[0].sources[0] has invalid fields", result.stderr)


if __name__ == "__main__":
    unittest.main()

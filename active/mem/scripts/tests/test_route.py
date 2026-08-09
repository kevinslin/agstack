#!/usr/bin/env python3
"""Integration tests for deterministic memory-base routing."""

from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TEST_DIR.parents[0] / "route.py"


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = self.root / ".mem.yaml"
        self.dendron_base = self.root / "dendron"
        self.oai_base = self.root / "oai"
        self.claw_base = self.root / "claw"
        self.dendron_base.mkdir()
        self.oai_base.mkdir()
        self.claw_base.mkdir()
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                bases:
                  - name: dendron
                    description: General knowledge base.
                    root: {self.dendron_base}
                    match:
                      cwd_globs: ["{self.dendron_base}", "{self.dendron_base}/**"]
                      source_globs: ["{self.dendron_base}", "{self.dendron_base}/**"]
                    schemas:
                      - name: global-core
                  - name: oai
                    aliases: [oai/monorepo, openai-monorepo]
                    description: OpenAI engineering knowledge base.
                    root: {self.oai_base}
                    match:
                      cwd_globs: ["{self.oai_base}", "{self.oai_base}/**"]
                      source_globs: ["{self.oai_base}", "{self.oai_base}/**"]
                    schemas:
                      - name: global-core
                  - name: claw
                    aliases: [claw/main]
                    description: OpenClaw engineering knowledge base.
                    root: {self.claw_base}
                    match:
                      cwd_globs: ["{self.claw_base}", "{self.claw_base}/**"]
                      source_globs: ["{self.claw_base}", "{self.claw_base}/**"]
                    schemas:
                      - name: global-core
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_router(self, query: str, *args: str) -> dict[str, object]:
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--config",
                str(self.config),
                "--query",
                query,
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return json.loads(result.stdout)

    def test_query_selects_general_knowledge_base(self) -> None:
        result = self.run_router("Record this in the general knowledge base.")

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["tier"], "query")
        self.assertEqual(result["selected"]["name"], "dendron")

    def test_explicit_target_wins(self) -> None:
        result = self.run_router(
            "Save this OpenAI guide.",
            "--target",
            "dendron",
            "--cwd",
            str(self.oai_base),
            "--source",
            str(self.claw_base / "src"),
        )

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["tier"], "explicit")
        self.assertEqual(result["selected"]["name"], "dendron")
        self.assertEqual(result["selected"]["reasons"], ["explicit base name"])

    def test_same_root_alias_selects_aggregate(self) -> None:
        result = self.run_router("Save a guide.", "--target", "oai/monorepo")

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["tier"], "explicit")
        self.assertEqual(result["selected"]["name"], "oai")
        self.assertEqual(result["selected"]["reasons"], ["explicit alias:oai/monorepo"])

    def test_source_ownership_beats_query(self) -> None:
        result = self.run_router(
            "Save this in the OpenAI knowledge base.",
            "--source",
            str(self.claw_base / "src" / "gateway.py"),
        )

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["tier"], "ownership")
        self.assertEqual(result["selected"]["name"], "claw")

    def test_cwd_ownership_beats_query(self) -> None:
        result = self.run_router(
            "Record this in the general knowledge base.",
            "--cwd",
            str(self.oai_base),
        )

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["tier"], "ownership")
        self.assertEqual(result["selected"]["name"], "oai")

    def test_conflicting_source_and_cwd_ownership_is_ambiguous(self) -> None:
        result = self.run_router(
            "Save this in OpenAI.",
            "--cwd",
            str(self.oai_base),
            "--source",
            str(self.claw_base / "src"),
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["tier"], "ownership")
        self.assertIsNone(result["selected"])

    def test_unknown_explicit_target_does_not_fall_back(self) -> None:
        result = self.run_router("OpenAI guide", "--target", "oai/clawcmd")

        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["tier"], "explicit")
        self.assertIsNone(result["selected"])
        for base in (self.dendron_base, self.oai_base, self.claw_base):
            self.assertFalse((base / ".mem.index.json").exists())

    def test_explicit_target_initializes_only_selected_base(self) -> None:
        (self.claw_base / "gateway.md").write_text("gateway\n", encoding="utf-8")

        result = self.run_router("gateway guide", "--target", "claw")

        self.assertTrue((self.claw_base / ".mem.index.json").is_file())
        self.assertFalse((self.dendron_base / ".mem.index.json").exists())
        self.assertFalse((self.oai_base / ".mem.index.json").exists())
        self.assertNotEqual(result["selected"]["index"]["status"], "not_loaded")

    def test_ownership_initializes_only_selected_base(self) -> None:
        result = self.run_router("gateway", "--cwd", str(self.oai_base))

        self.assertEqual(result["tier"], "ownership")
        self.assertTrue((self.oai_base / ".mem.index.json").is_file())
        self.assertFalse((self.dendron_base / ".mem.index.json").exists())
        self.assertFalse((self.claw_base / ".mem.index.json").exists())

    def test_existing_index_is_loaded_without_rebuilding(self) -> None:
        first = self.run_router("gateway", "--target", "claw")
        index_path = self.claw_base / ".mem.index.json"
        original = index_path.read_bytes()

        second = self.run_router("gateway", "--target", "claw")

        self.assertEqual(first["selected"]["index"]["status"], "generated")
        self.assertEqual(second["selected"]["index"]["status"], "loaded")
        self.assertEqual(index_path.read_bytes(), original)

    def test_query_initializes_candidates_and_uses_index_signals(self) -> None:
        directory = self.claw_base / "gateway" / "runbooks"
        directory.mkdir(parents=True)
        (directory / "deploy.md").write_text("deployment\n", encoding="utf-8")

        result = self.run_router("gateway runbook")

        self.assertEqual(result["tier"], "query")
        self.assertEqual(result["selected"]["name"], "claw")
        self.assertIn("index-topic:gateway", result["selected"]["reasons"])
        self.assertIn("index-artifact:runbook", result["selected"]["reasons"])
        self.assertEqual(result["selected"]["score"], 80)
        for base in (self.dendron_base, self.oai_base, self.claw_base):
            self.assertTrue((base / ".mem.index.json").is_file())

    def test_invalid_index_is_not_repaired_and_keeps_configured_signals(self) -> None:
        malformed = self.claw_base / ".mem.index.json"
        malformed.write_text("{malformed", encoding="utf-8")

        result = self.run_router("OpenClaw engineering knowledge")

        self.assertEqual(result["selected"]["name"], "claw")
        self.assertEqual(result["selected"]["index"]["status"], "invalid")
        self.assertEqual(malformed.read_text(encoding="utf-8"), "{malformed")

    def test_failed_index_build_does_not_block_explicit_selection(self) -> None:
        self.claw_base.rmdir()

        result = self.run_router(
            "OpenClaw engineering knowledge",
            "--target",
            "claw",
            "--allow-missing-roots",
        )

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selected"]["name"], "claw")
        self.assertEqual(result["selected"]["index"]["status"], "build_failed")

    def test_weak_signal_is_ambiguous(self) -> None:
        result = self.run_router("Save this for later.")

        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["selected"])


if __name__ == "__main__":
    unittest.main()

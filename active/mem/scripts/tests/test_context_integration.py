#!/usr/bin/env python3
"""Process-level integration tests for read-only project context lookup."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
MEM_PATH = TEST_DIR.parents[0] / "mem.py"


class ContextLookupIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.alpha_root = self.root / "alpha"
        self.beta_root = self.root / "beta"
        self.alpha_root.mkdir()
        self.beta_root.mkdir()
        (self.alpha_root / "notes").mkdir()
        (self.beta_root / "notes").mkdir()
        self.alpha_source = self.root / "src-alpha"
        self.beta_source = self.root / "src-beta"
        self.alpha_source.mkdir()
        self.beta_source.mkdir()
        self.config = self.root / "mem.yaml"
        self.write_config()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self) -> None:
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: alpha
                    aliases: [primary]
                    description: Alpha engineering knowledge.
                    root: {self.alpha_root}
                    managed_root: notes
                    path_style: directory
                    match:
                      source_globs: ["{self.alpha_source}", "{self.alpha_source}/**"]
                    schemas:
                      - name: global-core
                  - name: beta
                    description: Beta engineering knowledge.
                    root: {self.beta_root}
                    managed_root: notes
                    path_style: directory
                    match:
                      source_globs: ["{self.beta_source}", "{self.beta_source}/**"]
                    schemas:
                      - name: code
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def run_context(
        self,
        query: str,
        *args: str,
        config: Path | None = None,
        cwd: Path | None = None,
        home: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "python3",
            str(MEM_PATH),
            "context",
            "lookup",
            "--query",
            query,
            "--cwd",
            str(cwd or self.workspace),
            "--home",
            str(home or self.home),
        ]
        if config is not None:
            command.extend(["--config", str(config)])
        command.extend(args)
        return subprocess.run(command, text=True, capture_output=True, check=False)

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        self.assertTrue(result.stdout, msg=result.stderr)
        return json.loads(result.stdout)

    def tree_digest(self, root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            digest.update(str(path.relative_to(root)).encode())
            if path.is_file() and not path.is_symlink():
                digest.update(path.read_bytes())
                digest.update(str(path.stat().st_mtime_ns).encode())
        return digest.hexdigest()

    def test_managed_filename_heading_and_body_matches(self) -> None:
        (self.alpha_root / "notes" / "context-compass.md").write_text(
            "# Context Compass\n\nThe managed body contains orbit needle.\n",
            encoding="utf-8",
        )

        result = self.run_context(
            "orbit needle",
            "--config",
            str(self.config),
            "--target",
            "alpha",
            "--source",
            str(self.alpha_source),
        )
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(data["mode"], "context_lookup")
        self.assertEqual(data["status"], "matched")
        self.assertEqual(data["query"], "orbit needle")
        self.assertEqual(data["sources"], [str(self.alpha_source.resolve())])
        self.assertEqual(data["config_paths"], [str(self.config.resolve())])
        self.assertEqual(data["route"]["tier"], "explicit")
        self.assertEqual(data["selected_bases"][0]["name"], "alpha")
        self.assertEqual(data["selected_bases"][0]["schemas"][0]["name"], "global-core")
        self.assertTrue(data["selected_bases"][0]["schemas"][0]["path"].endswith("global-core/schema.yaml"))
        self.assertEqual(data["managed_matches"][0]["relative_path"], "context-compass.md")
        self.assertEqual(data["managed_matches"][0]["match_type"], "body")
        self.assertFalse(data["fallback_used"])
        self.assertEqual(data["source_matches"], [])

    def test_repeatable_sources_are_searched_on_fallback(self) -> None:
        first = self.alpha_source / "first.py"
        second = self.alpha_source / "second.py"
        first.write_text("nothing relevant here\n", encoding="utf-8")
        second.write_text("SOURCE_FALLBACK_NEEDLE = True\n", encoding="utf-8")

        result = self.run_context(
            "source_fallback_needle",
            "--config",
            str(self.config),
            "--source",
            str(first),
            "--source",
            str(second),
        )
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(data["sources"], [str(first.resolve()), str(second.resolve())])
        self.assertEqual(data["managed_matches"], [])
        self.assertTrue(data["fallback_used"])
        self.assertEqual(data["source_matches"][0]["path"], str(second.resolve()))
        self.assertGreaterEqual(data["search_stats"]["source_files_scanned"], 2)

    def test_explicit_target_overrides_source_ownership(self) -> None:
        (self.beta_root / "notes" / "chosen.md").write_text(
            "# Explicit target\n\nchosen-base-needle\n", encoding="utf-8"
        )

        result = self.run_context(
            "chosen-base-needle",
            "--config",
            str(self.config),
            "--target",
            "beta",
            "--source",
            str(self.alpha_source),
        )
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(data["selected_bases"][0]["name"], "beta")
        self.assertEqual(data["route"]["tier"], "explicit")
        self.assertEqual(data["managed_matches"][0]["base"], "beta")

    def test_ambiguous_route_requires_allow_multiple(self) -> None:
        result = self.run_context(
            "shared context",
            "--config",
            str(self.config),
            "--source",
            str(self.alpha_source),
            "--source",
            str(self.beta_source),
        )
        data = self.payload(result)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "ambiguous")
        self.assertEqual(data["selected_bases"], [])
        self.assertEqual(
            [candidate["name"] for candidate in data["route"]["candidates"]],
            ["alpha", "beta"],
        )

    def test_allow_multiple_reads_all_owned_bases(self) -> None:
        (self.alpha_root / "notes" / "shared-alpha.md").write_text(
            "# Shared\n\nmulti-base-needle alpha\n", encoding="utf-8"
        )
        (self.beta_root / "notes" / "shared-beta.md").write_text(
            "# Shared\n\nmulti-base-needle beta\n", encoding="utf-8"
        )

        result = self.run_context(
            "multi-base-needle",
            "--config",
            str(self.config),
            "--source",
            str(self.alpha_source),
            "--source",
            str(self.beta_source),
            "--allow-multiple",
        )
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual([base["name"] for base in data["selected_bases"]], ["alpha", "beta"])
        self.assertEqual(
            [match["base"] for match in data["managed_matches"]], ["alpha", "beta"]
        )

    def test_missing_config_is_successful(self) -> None:
        missing_source = self.root / "does-not-exist"
        result = self.run_context("anything", "--source", str(missing_source))
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(data["status"], "missing_config")
        self.assertEqual(data["config_paths"], [])
        self.assertEqual(data["sources"], [str(missing_source.absolute())])
        self.assertEqual(data["selected_bases"], [])
        self.assertFalse(data["fallback_used"])

    def test_source_path_must_exist_and_not_be_a_symlink(self) -> None:
        missing = self.root / "missing"
        result = self.run_context(
            "anything", "--config", str(self.config), "--source", str(missing)
        )
        data = self.payload(result)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data["status"], "invalid_source")
        self.assertEqual(data["sources"], [str(missing.absolute())])
        self.assertIn(str(missing), data["error"])

        target = self.root / "target.txt"
        target.write_text("anything\n", encoding="utf-8")
        link = self.root / "link.txt"
        os.symlink(target, link)
        linked = self.run_context(
            "anything", "--config", str(self.config), "--source", str(link)
        )
        self.assertEqual(self.payload(linked)["status"], "invalid_source")

    def test_lookup_does_not_change_managed_or_source_files(self) -> None:
        (self.alpha_root / "notes" / "durable.md").write_text(
            "# Durable\n\nread-only-needle\n", encoding="utf-8"
        )
        (self.alpha_source / "runtime.py").write_text(
            "READ_ONLY_NEEDLE = 1\n", encoding="utf-8"
        )
        before_managed = self.tree_digest(self.alpha_root)
        before_source = self.tree_digest(self.alpha_source)

        result = self.run_context(
            "read-only-needle",
            "--config",
            str(self.config),
            "--source",
            str(self.alpha_source),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(before_managed, self.tree_digest(self.alpha_root))
        self.assertEqual(before_source, self.tree_digest(self.alpha_source))

    def test_fallback_skips_symlinks_binary_oversize_and_hidden_directories(self) -> None:
        hidden = self.alpha_source / ".git"
        hidden.mkdir()
        (hidden / "hidden.txt").write_text("safety-needle\n", encoding="utf-8")
        (self.alpha_source / "binary.dat").write_bytes(b"safety-needle\0")
        (self.alpha_source / "oversize.txt").write_bytes(b"x" * 1_000_001)
        outside = self.root / "outside.txt"
        outside.write_text("safety-needle\n", encoding="utf-8")
        os.symlink(outside, self.alpha_source / "escape.txt")

        result = self.run_context(
            "safety-needle",
            "--config",
            str(self.config),
            "--source",
            str(self.alpha_source),
        )
        data = self.payload(result)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(data["status"], "no_matches")
        self.assertEqual(data["source_matches"], [])
        self.assertGreaterEqual(data["search_stats"]["hidden_directories_skipped"], 1)
        self.assertGreaterEqual(data["search_stats"]["files_skipped_binary"], 1)
        self.assertGreaterEqual(data["search_stats"]["files_skipped_oversize"], 1)
        self.assertGreaterEqual(data["search_stats"]["symlinks_skipped"], 1)


if __name__ == "__main__":
    unittest.main()

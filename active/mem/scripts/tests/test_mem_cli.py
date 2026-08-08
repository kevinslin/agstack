#!/usr/bin/env python3
"""Integration tests for the unified mem CLI."""

from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TEST_DIR.parents[0] / "mem.py"


class MemCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.base = self.root / "kb"
        self.base.mkdir()
        self.config = self.root / ".mem.yaml"
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: docs
                    description: Durable documentation.
                    root: {self.base}
                    path_style: directory
                    schemas:
                      - name: global-core
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_mem(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT_PATH), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_managed_materialization_uses_base_root_and_path_style(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--root-relative",
            "team",
            "--var",
            "cook=configure-service",
            "--include",
            "cook/configure-service",
            "--skip-existing",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self.base / "team" / "cook" / "configure-service.md").is_file())

    def test_managed_materialization_uses_configured_managed_root(self) -> None:
        notes = self.base / "notes"
        notes.mkdir()
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: dendron
                    description: General knowledge base.
                    root: {self.base}
                    managed_root: notes
                    path_style: dotted
                    schemas:
                      - name: global-core
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "dendron",
            "--var",
            "cook=configure-service",
            "--include",
            "cook/configure-service",
            "--skip-existing",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((notes / "cook.configure-service.md").is_file())
        self.assertFalse((self.base / "cook.configure-service.md").exists())

    def test_explicit_out_requires_unmanaged(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--out",
            str(self.root / "out"),
            "--include",
            "ref/example",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit --out requires --unmanaged", result.stderr)

    def test_managed_root_relative_cannot_escape_base(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--root-relative",
            "../outside",
            "--include",
            "ref/example",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("resolves outside the selected managed root", result.stderr)

    def test_managed_materialization_rejects_unconfigured_schema(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "tool",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--include",
            "pkg/example",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not configured for base", result.stderr)

    def test_managed_materialization_rejects_manual_schema_path(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--schema-path",
            str(self.root / "other-schema.yaml"),
            "--include",
            "ref/example",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("derives --schema-path", result.stderr)

    def test_managed_materialization_uses_configured_schema_path(self) -> None:
        schema_dir = self.root / "custom-schema"
        schema_dir.mkdir()
        schema_path = schema_dir / "schema.yaml"
        schema_path.write_text(
            textwrap.dedent(
                """
                version: 1.0
                output:
                  file_extension: md
                schema:
                  custom:
                    template: custom
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (schema_dir / "custom.md.jinja").write_text("# Custom\n", encoding="utf-8")
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: docs
                    description: Durable documentation.
                    root: {self.base}
                    path_style: directory
                    schemas:
                      - name: custom
                        path: {schema_path}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = self.run_mem(
            "schema",
            "materialize",
            "custom",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--include",
            "custom",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((self.base / "custom.md").read_text(encoding="utf-8"), "# Custom\n")


if __name__ == "__main__":
    unittest.main()

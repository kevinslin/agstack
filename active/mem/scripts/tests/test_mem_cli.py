#!/usr/bin/env python3
"""Integration tests for the unified mem CLI."""

from __future__ import annotations

import json
import subprocess
import sys
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
                version: 2
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

    def configure_pkg_schema(self, *, schema_root: str | None, path_style: str = "directory") -> None:
        root_line = f"\n                        root: {schema_root}" if schema_root is not None else ""
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                bases:
                  - name: docs
                    description: Durable package documentation.
                    root: {self.base}
                    path_style: {path_style}
                    schemas:
                      - name: pkg{root_line}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def materialize_pkg(self, include: str) -> subprocess.CompletedProcess[str]:
        return self.run_mem(
            "schema",
            "materialize",
            "pkg",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--var",
            "package=clawcmd",
            "--var",
            "cook=configure-service",
            "--include",
            include,
        )

    def test_pkg_schema_preserves_legacy_mount_when_root_is_omitted(self) -> None:
        self.configure_pkg_schema(schema_root=None)

        result = self.materialize_pkg("pkg/clawcmd/cook/configure-service")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self.base / "pkg" / "clawcmd" / "cook" / "configure-service.md").is_file())

    def test_pkg_schema_supports_inline_root(self) -> None:
        self.configure_pkg_schema(schema_root=".")

        result = self.materialize_pkg("clawcmd/cook/configure-service")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self.base / "clawcmd" / "cook" / "configure-service.md").is_file())
        self.assertFalse((self.base / "pkg").exists())

    def test_pattern_root_materializes_inline_pkg_schema_under_project(self) -> None:
        project = self.root / "proj.2025"
        session_directory = project / "src" / "service"
        session_directory.mkdir(parents=True)
        self.config.write_text(
            textwrap.dedent(
                """
                version: 2
                bases:
                  - name: docs
                    description: Project package documentation.
                    root_pattern: proj*
                    path_style: directory
                    schemas:
                      - name: pkg
                        root: .
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = self.run_mem(
            "schema",
            "materialize",
            "pkg",
            "--config",
            str(self.config),
            "--cwd",
            str(session_directory),
            "--base",
            "docs",
            "--var",
            "package=clawcmd",
            "--var",
            "cook=configure-service",
            "--include",
            "clawcmd/cook/configure-service",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((project / "clawcmd" / "cook" / "configure-service.md").is_file())
        self.assertFalse((project / "pkg").exists())

    def test_pkg_schema_supports_nested_custom_root(self) -> None:
        self.configure_pkg_schema(schema_root="projects/packages")

        result = self.materialize_pkg("projects/packages/clawcmd/cook/configure-service")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(
            (self.base / "projects" / "packages" / "clawcmd" / "cook" / "configure-service.md").is_file()
        )

    def test_pkg_schema_custom_root_preserves_dotted_path_style(self) -> None:
        self.configure_pkg_schema(schema_root="projects/packages", path_style="dotted")

        result = self.materialize_pkg("projects.packages.clawcmd.cook.configure-service")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((self.base / "projects.packages.clawcmd.cook.configure-service.md").is_file())

    def test_managed_materialization_rejects_manual_mount_root(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--mount-root",
            "outside",
            "--include",
            "outside/cook/example",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("derives --mount-root", result.stderr)

    def test_managed_materialization_uses_configured_managed_root(self) -> None:
        notes = self.base / "notes"
        notes.mkdir()
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 2
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
        self.assertTrue((notes / ".mem.index.json").is_file())

    def test_managed_materialization_refreshes_base_index(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--var",
            "cook=example",
            "--include",
            "cook/example",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("cook/example.md", result.stdout)
        index = json.loads((self.base / ".mem.index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["document_count"], 1)

    def test_managed_skip_existing_preserves_unchanged_index(self) -> None:
        arguments = (
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--var",
            "cook=example",
            "--include",
            "cook/example",
            "--skip-existing",
        )
        first = self.run_mem(*arguments)
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        index_path = self.base / ".mem.index.json"
        original_stat = index_path.stat()
        original_content = index_path.read_bytes()

        second = self.run_mem(*arguments)

        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertEqual(second.stdout, "")
        self.assertEqual(index_path.read_bytes(), original_content)
        self.assertEqual(index_path.stat().st_mtime_ns, original_stat.st_mtime_ns)

    def test_doctor_migration_is_dispatched_through_unified_cli(self) -> None:
        self.config.write_text(
            self.config.read_text(encoding="utf-8").replace("version: 2", "version: 1"),
            encoding="utf-8",
        )

        result = self.run_mem("doctor", "--migrate", "--config", str(self.config))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "doctor_migrate")
        self.assertEqual(payload["results"][0]["status"], "migrated")
        self.assertIn("version: 2", self.config.read_text(encoding="utf-8"))

    def test_failed_managed_materialization_preserves_child_failure(self) -> None:
        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--include",
            "missing/not-a-schema-node",
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: schema 'global-core' produced no files\n")
        self.assertFalse((self.base / ".mem.index.json").exists())
        self.assertNotIn("index_refresh_failed", result.stderr)

    def test_refresh_warning_preserves_configuration_controls_and_replays(self) -> None:
        controls_root = self.root / "configuration controls with spaces"
        controls_root.mkdir()
        config_path = controls_root / "explicit config.yaml"
        config_path.write_text(self.config.read_text(encoding="utf-8"), encoding="utf-8")
        cwd_path = controls_root / "working directory"
        home_path = controls_root / "home directory"
        cwd_path.mkdir()
        home_path.mkdir()
        index_path = self.base / ".mem.index.json"
        index_path.mkdir()

        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(config_path),
            "--cwd",
            str(cwd_path),
            "--home",
            str(home_path),
            "--base",
            "docs",
            "--var",
            "cook=example",
            "--include",
            "cook/example",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout,
            f"{(self.base / 'cook' / 'example.md').resolve(strict=False)}\n",
        )
        self.assertTrue((self.base / "cook" / "example.md").is_file())
        warning_lines = [line for line in result.stderr.splitlines() if line.startswith("{")]
        self.assertEqual(len(warning_lines), 1, msg=result.stderr)
        warning = json.loads(warning_lines[0])
        self.assertEqual(
            set(warning),
            {"level", "code", "base", "index_path", "error", "repair_argv"},
        )
        self.assertEqual(warning["level"], "warning")
        self.assertEqual(warning["code"], "index_refresh_failed")
        self.assertEqual(warning["base"], "docs")
        self.assertEqual(warning["index_path"], str(index_path.resolve(strict=False)))
        self.assertTrue(warning["error"])
        self.assertEqual(
            warning["repair_argv"],
            [
                "mem",
                "index",
                "build",
                "--base",
                "docs",
                "--config",
                str(config_path),
                "--cwd",
                str(cwd_path),
                "--home",
                str(home_path),
            ],
        )

        index_path.rmdir()
        repaired = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *warning["repair_argv"][1:]],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(repaired.returncode, 0, msg=repaired.stderr)
        self.assertEqual(json.loads(repaired.stdout)["results"][0]["base"], "docs")

    def test_refresh_warning_omits_unsupplied_configuration_controls(self) -> None:
        index_path = self.base / ".mem.index.json"
        index_path.mkdir()

        result = self.run_mem(
            "schema",
            "materialize",
            "global-core",
            "--config",
            str(self.config),
            "--base",
            "docs",
            "--var",
            "cook=example",
            "--include",
            "cook/example",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        warning = json.loads(result.stderr.splitlines()[-1])
        self.assertEqual(
            warning["repair_argv"],
            ["mem", "index", "build", "--base", "docs", "--config", str(self.config)],
        )

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
                version: 2
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

#!/usr/bin/env python3
"""Integration tests for the mem config loader."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TEST_DIR.parents[0] / "load_config.py"


class LoadConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = self.root / ".mem.yaml"
        self.base = self.root / "kb"
        self.base.mkdir()
        self.schema_file = self.root / "schema.yaml"
        self.schema_file.write_text("version: 1.0\nschema: {}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, text: str) -> None:
        self.config.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")

    def run_loader(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(SCRIPT_PATH), "--config", str(self.config), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_explicit_path_style_is_normalized(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                path_style: dotted
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["bases"][0]["description"], "Durable documentation notes.")
        self.assertEqual(data["bases"][0]["path_style"], "dotted")
        self.assertEqual(data["bases"][0]["schemas"], [{"name": "tool"}])

    def test_schema_path_is_normalized(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: local
                    path: {self.schema_file}
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(
            data["bases"][0]["schemas"],
            [{"name": "local", "path": str(self.schema_file.resolve())}],
        )

    def test_scalar_schema_is_rejected(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas: [tool]
            """
        )

        result = self.run_loader()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bases[0].schemas[0] must be a mapping", result.stderr)

    def test_relative_schema_path_is_rejected(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: local
                    path: schema.yaml
            """
        )

        result = self.run_loader()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bases[0].schemas[0].path must be an absolute path", result.stderr)

    def test_missing_description_is_rejected(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bases[0].description must be a non-empty string", result.stderr)

    def test_invalid_path_style_is_rejected(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                path_style: flat
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bases[0].path_style must be one of: directory, dotted", result.stderr)

    def test_missing_path_style_infers_dotted_from_existing_base(self) -> None:
        (self.base / "pkg.example.md").write_text("# Example\n", encoding="utf-8")
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["bases"][0]["path_style"], "dotted")

    def test_missing_path_style_infers_directory_from_existing_base(self) -> None:
        nested = self.base / "dev" / "qa"
        nested.mkdir(parents=True)
        (nested / "crabbox.md").write_text("# Crabbox\n", encoding="utf-8")
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: code
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["bases"][0]["path_style"], "directory")

    def test_optional_routing_metadata_is_normalized(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                aliases: [documentation, durable-docs]
                priority: 25
                match:
                  topics: [configuration]
                  artifact_kinds: [guide, runbook]
                  source_globs: ["src/docs/**"]
                  cwd_globs: ["*/docs"]
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        base = json.loads(result.stdout)["bases"][0]
        self.assertEqual(base["aliases"], ["documentation", "durable-docs"])
        self.assertEqual(base["priority"], 25)
        self.assertEqual(base["match"]["topics"], ["configuration"])

    def test_audit_defaults_are_exposed(self) -> None:
        self.write_config(
            f"""
            version: 1
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader("--home", str(self.root / "home"))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(
            data["audit"],
            {
                "enabled": False,
                "trace_root": str((self.root / "home" / ".config" / "mem" / "traces").resolve()),
            },
        )

    def test_audit_is_normalized(self) -> None:
        trace_root = self.root / "custom-traces"
        self.write_config(
            f"""
            version: 1
            audit:
              enabled: true
              trace_root: {trace_root}
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["audit"],
            {"enabled": True, "trace_root": str(trace_root.resolve())},
        )

    def test_relative_audit_trace_root_is_resolved_from_config(self) -> None:
        self.write_config(
            f"""
            version: 1
            audit:
              trace_root: traces
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["audit"],
            {"enabled": False, "trace_root": str((self.root / "traces").resolve())},
        )

    def test_audit_trace_root_expands_home_environment_variable(self) -> None:
        self.write_config(
            f"""
            version: 1
            audit:
              trace_root: $HOME/.config/mem/custom-traces
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )

        result = self.run_loader()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["audit"]["trace_root"],
            str((Path.home() / ".config" / "mem" / "custom-traces").resolve()),
        )

    def test_invalid_audit_fields_are_rejected(self) -> None:
        for audit, message in (
            ("true", "audit must be a mapping"),
            ("{enabled: 1}", "audit.enabled must be a boolean"),
            ("{trace_root: ''}", "audit.trace_root must be a non-empty string"),
            ("{unknown: true}", "audit has unsupported key(s): unknown"),
        ):
            with self.subTest(audit=audit):
                self.write_config(
                    f"""
                    version: 1
                    audit: {audit}
                    bases:
                      - name: docs
                        description: Durable documentation notes.
                        root: {self.base}
                        schemas:
                          - name: tool
                    """
                )

                result = self.run_loader()

                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_audit_trace_root_rejects_unresolved_environment_variable(self) -> None:
        self.write_config(
            f"""
            version: 1
            audit:
              enabled: true
              trace_root: $MEM_AUDIT_ROOT_THAT_IS_NOT_SET/traces
            bases:
              - name: docs
                description: Durable documentation notes.
                root: {self.base}
                schemas:
                  - name: tool
            """
        )
        env = os.environ.copy()
        env.pop("MEM_AUDIT_ROOT_THAT_IS_NOT_SET", None)

        result = subprocess.run(
            ["python3", str(SCRIPT_PATH), "--config", str(self.config)],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains an unresolved environment variable", result.stderr)

    def test_nearest_ancestor_and_home_configs_are_merged(self) -> None:
        project = self.root / "project"
        nested = project / "one" / "two"
        home = self.root / "home"
        project_base = self.root / "project-kb"
        home_base = self.root / "home-kb"
        nested.mkdir(parents=True)
        home.mkdir()
        project_base.mkdir()
        home_base.mkdir()
        (project / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: project
                    description: Project notes.
                    root: {project_base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (home / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: global
                    description: Global notes.
                    root: {home_base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--cwd",
                str(nested),
                "--home",
                str(home),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([base["name"] for base in data["bases"]], ["project", "global"])
        self.assertEqual(
            data["config_paths"],
            [
                str((project / ".mem.yaml").resolve()),
                str((home / ".mem.yaml").resolve()),
            ],
        )

    def test_nearest_config_overrides_duplicate_home_base(self) -> None:
        project = self.root / "project"
        home = self.root / "home"
        local_base = self.root / "local-kb"
        global_base = self.root / "global-kb"
        project.mkdir()
        home.mkdir()
        local_base.mkdir()
        global_base.mkdir()
        for config_path, description, root in (
            (project / ".mem.yaml", "Local docs.", local_base),
            (home / ".mem.yaml", "Global docs.", global_base),
        ):
            config_path.write_text(
                textwrap.dedent(
                    f"""
                    version: 1
                    bases:
                      - name: docs
                        description: {description}
                        root: {root}
                        schemas:
                          - name: tool
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--cwd",
                str(project),
                "--home",
                str(home),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        base = json.loads(result.stdout)["bases"][0]
        self.assertEqual(base["description"], "Local docs.")
        self.assertEqual(base["root"], str(local_base.resolve()))

    def test_home_audit_is_inherited_when_nearest_does_not_declare_it(self) -> None:
        project = self.root / "project"
        home = self.root / "home"
        project.mkdir()
        home.mkdir()
        (project / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                bases:
                  - name: project
                    description: Project notes.
                    root: {self.base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (home / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                audit:
                  enabled: true
                  trace_root: {self.root / "home-traces"}
                bases:
                  - name: home
                    description: Home notes.
                    root: {self.base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--cwd",
                str(project),
                "--home",
                str(home),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["audit"],
            {"enabled": True, "trace_root": str((self.root / "home-traces").resolve())},
        )

    def test_nearest_declared_audit_owns_entire_mapping(self) -> None:
        project = self.root / "project"
        home = self.root / "home"
        project.mkdir()
        home.mkdir()
        (project / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                audit:
                  enabled: true
                bases:
                  - name: project
                    description: Project notes.
                    root: {self.base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (home / ".mem.yaml").write_text(
            textwrap.dedent(
                f"""
                version: 1
                audit:
                  trace_root: {self.root / "home-traces"}
                bases:
                  - name: home
                    description: Home notes.
                    root: {self.base}
                    schemas:
                      - name: tool
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--cwd",
                str(project),
                "--home",
                str(home),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["audit"],
            {
                "enabled": True,
                "trace_root": str((home / ".config" / "mem" / "traces").resolve()),
            },
        )


if __name__ == "__main__":
    unittest.main()

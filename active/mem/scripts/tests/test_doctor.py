#!/usr/bin/env python3
"""Focused tests for atomic memory-configuration schema migration."""

from __future__ import annotations

import importlib
import io
import json
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = SCRIPTS_DIR / "doctor.py"
sys.path.insert(0, str(SCRIPTS_DIR))
DOCTOR = importlib.import_module("doctor")


class DoctorMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.project = self.root / "project"
        self.home = self.root / "home"
        self.project.mkdir()
        self.home.mkdir()
        self.project_base = self.root / "project-kb"
        self.home_base = self.root / "home-kb"
        self.project_base.mkdir()
        self.home_base.mkdir()
        self.project_config = self.project / ".mem.yaml"
        self.home_config = self.home / ".mem.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(self, path: Path, text: str) -> None:
        path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")

    def config_text(
        self,
        *,
        version: str = "1",
        name: str = "project",
        root: Path | None = None,
        match: str = "topics: [routing]",
    ) -> str:
        match_yaml = textwrap.indent(textwrap.dedent(match).strip(), "      ")
        return (
            f"version: {version}\n"
            "bases:\n"
            f"  - name: {name}\n"
            f"    description: {name} notes.\n"
            f"    root: {root or self.project_base}\n"
            "    match:\n"
            f"{match_yaml}\n"
            "    schemas:\n"
            "      - name: tool\n"
        )

    def run_doctor(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(SCRIPT_PATH),
                "--migrate",
                "--cwd",
                str(self.project),
                "--home",
                str(self.home),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_migration_preserves_supported_configuration_and_permissions(self) -> None:
        managed = self.project_base / "notes"
        managed.mkdir()
        second = self.root / "second-kb"
        second.mkdir()
        self.write_config(
            self.project_config,
            f"""
            version: 1
            audit:
              enabled: true
              trace_root: traces
            bases:
              - name: project
                aliases: [workspace]
                description: Project knowledge.
                root: {self.project_base}
                managed_root: notes
                path_style: dotted
                priority: 25
                skill: mem
                match:
                  topics: [discarded, ignored]
                  artifact_kinds: [guide]
                  cwd_globs: ["*/project"]
                  source_globs: ["src/**"]
                schemas:
                  - name: tool
              - name: secondary
                description: Secondary knowledge.
                root: {second}
                match:
                  topics: [secondary]
                  artifact_kinds: [reference]
                schemas:
                  - name: reference
            """,
        )
        self.project_config.chmod(0o640)

        result = self.run_doctor("--pretty")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "doctor_migrate")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["config_paths"], [str(self.project_config)])
        self.assertEqual(
            payload["results"],
            [
                {
                    "config_path": str(self.project_config),
                    "from_version": 1,
                    "to_version": 2,
                    "removed_fields": 4,
                    "status": "migrated",
                }
            ],
        )
        migrated = DOCTOR.load_config.yaml.safe_load(self.project_config.read_text())
        self.assertEqual(migrated["version"], 2)
        self.assertEqual(migrated["audit"], {"enabled": True, "trace_root": "traces"})
        primary, secondary = migrated["bases"]
        self.assertEqual(primary["name"], "project")
        self.assertEqual(primary["aliases"], ["workspace"])
        self.assertEqual(primary["description"], "Project knowledge.")
        self.assertEqual(primary["root"], str(self.project_base))
        self.assertEqual(primary["managed_root"], "notes")
        self.assertEqual(primary["path_style"], "dotted")
        self.assertEqual(primary["priority"], 25)
        self.assertEqual(primary["skill"], "mem")
        self.assertEqual(
            primary["match"],
            {"cwd_globs": ["*/project"], "source_globs": ["src/**"]},
        )
        self.assertEqual(primary["schemas"], [{"name": "tool"}])
        self.assertEqual(secondary["name"], "secondary")
        self.assertNotIn("match", secondary)
        self.assertEqual(stat.S_IMODE(self.project_config.stat().st_mode), 0o640)
        self.assertEqual(list(self.project.iterdir()), [self.project_config])
        self.assertFalse((managed / ".mem.index.json").exists())

    def test_mixed_configs_preserve_discovery_order_and_rerun_is_idempotent(self) -> None:
        self.write_config(self.project_config, self.config_text())
        current = self.config_text(
            version="2",
            name="global",
            root=self.home_base,
            match='cwd_globs: ["*/home"]',
        )
        self.home_config.write_text(current, encoding="utf-8")
        original_home_stat = self.home_config.stat()

        first = self.run_doctor()

        self.assertEqual(first.returncode, 0, msg=first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["config_paths"], [str(self.project_config), str(self.home_config)])
        self.assertEqual(
            [result["status"] for result in payload["results"]],
            ["migrated", "unchanged"],
        )
        self.assertEqual(self.home_config.read_text(encoding="utf-8"), current)
        self.assertEqual(self.home_config.stat().st_ino, original_home_stat.st_ino)
        self.assertEqual(self.home_config.stat().st_mtime_ns, original_home_stat.st_mtime_ns)
        first_project_stat = self.project_config.stat()

        second = self.run_doctor()

        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertEqual(
            [result["status"] for result in json.loads(second.stdout)["results"]],
            ["unchanged", "unchanged"],
        )
        self.assertEqual(self.project_config.stat().st_ino, first_project_stat.st_ino)
        self.assertEqual(self.project_config.stat().st_mtime_ns, first_project_stat.st_mtime_ns)

    def test_explicit_config_does_not_discover_or_change_home_config(self) -> None:
        self.write_config(self.project_config, self.config_text())
        self.write_config(
            self.home_config,
            self.config_text(name="global", root=self.home_base),
        )
        original_home = self.home_config.read_bytes()

        result = self.run_doctor("--config", str(self.project_config))

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(result.stdout)["config_paths"], [str(self.project_config)])
        self.assertEqual(self.home_config.read_bytes(), original_home)

    def test_empty_legacy_match_is_removed_without_counting_mapping_itself(self) -> None:
        self.write_config(self.project_config, self.config_text(match="{}"))
        content = self.project_config.read_text().replace(
            "    match:\n      {}\n",
            "    match: {}\n",
        )
        self.project_config.write_text(content, encoding="utf-8")

        result = self.run_doctor()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["removed_fields"], 0)
        migrated = DOCTOR.load_config.yaml.safe_load(self.project_config.read_text())
        self.assertNotIn("match", migrated["bases"][0])

    def test_invalid_versions_fail_before_writing_any_discovered_config(self) -> None:
        for version in ("true", "null", "1.0", "3", "'2'"):
            with self.subTest(version=version):
                self.write_config(self.project_config, self.config_text())
                self.write_config(
                    self.home_config,
                    self.config_text(version=version, name="global", root=self.home_base),
                )
                originals = (self.project_config.read_bytes(), self.home_config.read_bytes())

                result = self.run_doctor()

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("version must be integer 1 or 2", result.stderr)
                self.assertEqual(
                    (self.project_config.read_bytes(), self.home_config.read_bytes()),
                    originals,
                )

    def test_missing_version_fails_before_writing(self) -> None:
        self.write_config(self.project_config, self.config_text().replace("version: 1\n", ""))
        original = self.project_config.read_bytes()

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.project_config.read_bytes(), original)

    def test_malformed_yaml_and_nonmapping_fail_before_writing(self) -> None:
        for content, error in (
            ("version: [\n", "invalid YAML"),
            ("- one\n- two\n", "config must be a YAML mapping"),
        ):
            with self.subTest(content=content):
                self.project_config.write_text(content, encoding="utf-8")

                result = self.run_doctor()

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn(error, result.stderr)
                self.assertEqual(self.project_config.read_text(encoding="utf-8"), content)

    def test_nonmapping_match_fails_before_writing(self) -> None:
        content = self.config_text().replace(
            "    match:\n      topics: [routing]\n",
            "    match: true\n",
        )
        self.project_config.write_text(content, encoding="utf-8")

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("match must be a mapping", result.stderr)
        self.assertEqual(self.project_config.read_text(encoding="utf-8"), content)

    def test_invalid_current_version_is_not_repaired_and_prevents_all_writes(self) -> None:
        self.write_config(self.project_config, self.config_text())
        self.write_config(
            self.home_config,
            self.config_text(version="2", name="global", root=self.home_base),
        )
        originals = (self.project_config.read_bytes(), self.home_config.read_bytes())

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsupported key(s): topics", result.stderr)
        self.assertEqual(
            (self.project_config.read_bytes(), self.home_config.read_bytes()),
            originals,
        )

    def test_unknown_legacy_match_fields_are_not_silently_removed(self) -> None:
        self.write_config(
            self.project_config,
            self.config_text(match="topics: [routing]\nunknown: [bad]"),
        )
        original = self.project_config.read_bytes()

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsupported key(s): unknown", result.stderr)
        self.assertEqual(self.project_config.read_bytes(), original)

    def test_merged_alias_collision_is_prevalidated_before_any_write(self) -> None:
        project = self.config_text().replace(
            "    description:",
            "    aliases: [shared]\n    description:",
        )
        home = self.config_text(name="global", root=self.home_base).replace(
            "    description:",
            "    aliases: [shared]\n    description:",
        )
        self.write_config(self.project_config, project)
        self.write_config(self.home_config, home)
        originals = (self.project_config.read_bytes(), self.home_config.read_bytes())

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("base name/alias collision: shared", result.stderr)
        self.assertEqual(
            (self.project_config.read_bytes(), self.home_config.read_bytes()),
            originals,
        )

    def test_missing_base_root_is_prevalidated_before_writing(self) -> None:
        self.write_config(self.project_config, self.config_text(root=self.root / "missing"))
        original = self.project_config.read_bytes()

        result = self.run_doctor()

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("root does not exist", result.stderr)
        self.assertEqual(self.project_config.read_bytes(), original)

    def test_write_failure_is_reported_and_remaining_configs_are_processed(self) -> None:
        self.write_config(self.project_config, self.config_text())
        self.write_config(self.home_config, self.config_text(name="global", root=self.home_base))
        original_write = DOCTOR.write_config_atomically

        def fail_first(path: Path, data: dict[str, object]) -> None:
            if path == self.project_config:
                raise OSError("simulated atomic replacement failure")
            original_write(path, data)

        output = io.StringIO()
        errors = io.StringIO()
        with (
            mock.patch.object(DOCTOR, "write_config_atomically", side_effect=fail_first),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            exit_code = DOCTOR.main(
                ["--migrate", "--cwd", str(self.project), "--home", str(self.home)]
            )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertEqual(
            [result["status"] for result in payload["results"]],
            ["error", "migrated"],
        )
        self.assertIn("simulated atomic replacement failure", payload["results"][0]["error"])
        self.assertEqual(
            DOCTOR.load_config.yaml.safe_load(self.project_config.read_text())["version"],
            1,
        )
        self.assertEqual(
            DOCTOR.load_config.yaml.safe_load(self.home_config.read_text())["version"],
            2,
        )

        rerun = self.run_doctor()

        self.assertEqual(rerun.returncode, 0, msg=rerun.stderr)
        self.assertEqual(
            [result["status"] for result in json.loads(rerun.stdout)["results"]],
            ["migrated", "unchanged"],
        )

    def test_final_strict_reload_failure_returns_structured_error_after_write(self) -> None:
        self.write_config(self.project_config, self.config_text())
        output = io.StringIO()
        with (
            mock.patch.object(DOCTOR.load_config, "load_config", side_effect=SystemExit(1)),
            redirect_stdout(output),
        ):
            exit_code = DOCTOR.main(
                ["--migrate", "--cwd", str(self.project), "--home", str(self.home)]
            )

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertIn("final strict configuration reload failed", payload["error"])
        self.assertEqual(payload["results"][0]["status"], "migrated")
        self.assertEqual(
            DOCTOR.load_config.yaml.safe_load(self.project_config.read_text())["version"],
            2,
        )

    def test_missing_migrate_flag_and_missing_config_return_argument_error(self) -> None:
        missing_flag = subprocess.run(
            ["python3", str(SCRIPT_PATH)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(missing_flag.returncode, 2)
        self.assertEqual(missing_flag.stdout, "")

        missing_config = self.run_doctor("--config", str(self.root / "missing.yaml"))
        self.assertEqual(missing_config.returncode, 2)
        self.assertEqual(missing_config.stdout, "")
        self.assertIn("config does not exist", missing_config.stderr)

    def test_existing_pattern_root_uses_requested_cwd_during_validation(self) -> None:
        self.write_config(
            self.project_config,
            """
            version: 2
            bases:
              - name: project
                description: Project knowledge.
                root_pattern: project
                schemas:
                  - name: tool
                    root: .
            """,
        )

        result = self.run_doctor()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(result.stdout)["results"][0]["status"], "unchanged")


if __name__ == "__main__":
    unittest.main()

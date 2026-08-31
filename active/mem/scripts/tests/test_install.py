#!/usr/bin/env python3
"""Process-level tests for installing and invoking the mem launcher."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parents[0]
INSTALL_PATH = SCRIPT_DIR / "install.py"


class MemInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bin_dir = (self.root / "bin dir with spaces").resolve(strict=False)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_install(
        self,
        *,
        install_path: Path = INSTALL_PATH,
        bin_dir: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(install_path),
                "--bin-dir",
                str(bin_dir or self.bin_dir),
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def env_with_bin(self, bin_dir: Path | None = None) -> dict[str, str]:
        env = os.environ.copy()
        selected = bin_dir or self.bin_dir
        env["PATH"] = f"{selected}{os.pathsep}{env.get('PATH', '')}"
        return env

    def copy_minimal_scripts_to_spaced_path(self) -> Path:
        scripts = self.root / "skill root with spaces" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("install.py", "mem.py", "load_config.py"):
            shutil.copy2(SCRIPT_DIR / name, scripts / name)
        return scripts / "install.py"

    def test_install_then_invokes_mem_from_caller_cwd_with_spaced_paths(self) -> None:
        install_path = self.copy_minimal_scripts_to_spaced_path()
        project = self.root / "caller project with spaces"
        nested = project / "src" / "tool"
        notes = project / "notes"
        home = self.root / "home"
        nested.mkdir(parents=True)
        notes.mkdir()
        home.mkdir()
        config = project / ".mem.yaml"
        config.write_text(
            textwrap.dedent(
                """
                version: 2
                bases:
                  - name: docs
                    description: Local docs.
                    root: .
                    managed_root: notes
                    schemas:
                      - name: global-core
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        runtime_env = self.env_with_bin()
        runtime_env["HOME"] = str(home)

        installed = self.run_install(install_path=install_path, env={**os.environ, "PATH": ""})

        self.assertEqual(installed.returncode, 0, msg=installed.stderr)
        launcher = self.bin_dir / "mem"
        self.assertTrue(launcher.is_file())
        self.assertIn(f"installed: {launcher}", installed.stdout)
        self.assertIn(f"PATH does not include: {self.bin_dir}", installed.stdout)
        self.assertIn(f"export PATH={shlex.quote(str(self.bin_dir))}:$PATH", installed.stdout)

        help_result = subprocess.run(
            ["mem", "--help"],
            text=True,
            capture_output=True,
            check=False,
            cwd=nested,
            env=runtime_env,
        )
        self.assertEqual(help_result.returncode, 0, msg=help_result.stderr)
        self.assertIn("mem config show", help_result.stdout)
        self.assertNotIn("mem.py config show", help_result.stdout)

        shown = subprocess.run(
            ["mem", "config", "show"],
            text=True,
            capture_output=True,
            check=False,
            cwd=nested,
            env=runtime_env,
        )

        self.assertEqual(shown.returncode, 0, msg=shown.stderr)
        payload = json.loads(shown.stdout)
        self.assertEqual(payload["config_paths"], [str(config.resolve())])
        self.assertEqual(payload["bases"][0]["root"], str(project.resolve()))
        self.assertEqual(payload["bases"][0]["managed_root"], str(notes.resolve()))

        failed = subprocess.run(
            ["mem", "missing-command"],
            text=True,
            capture_output=True,
            check=False,
            cwd=nested,
            env=runtime_env,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertIn("unknown command: missing-command", failed.stderr)

    def test_repeated_install_updates_owned_launcher_without_path_hint_when_visible(self) -> None:
        env = self.env_with_bin()
        first = self.run_install(env=env)
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        launcher = self.bin_dir / "mem"
        first_source = launcher.read_text(encoding="utf-8")
        self.assertEqual(first.stdout, f"installed: {launcher}\n")
        self.assertIn(shlex.quote(str(Path(sys.executable).expanduser())), first_source)
        self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR)

        second = self.run_install(env=env)

        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertEqual(second.stdout, f"installed: {launcher}\n")
        self.assertEqual(launcher.read_text(encoding="utf-8"), first_source)

    def test_unrelated_file_collision_is_preserved(self) -> None:
        self.bin_dir.mkdir()
        launcher = self.bin_dir / "mem"
        launcher.write_text("#!/bin/sh\necho unrelated\n", encoding="utf-8")
        launcher.chmod(0o755)

        result = self.run_install()

        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite unrelated existing path", result.stderr)
        self.assertEqual(launcher.read_text(encoding="utf-8"), "#!/bin/sh\necho unrelated\n")

    def test_symlink_collision_is_preserved(self) -> None:
        self.bin_dir.mkdir()
        target = self.root / "target"
        target.write_text("target\n", encoding="utf-8")
        launcher = self.bin_dir / "mem"
        launcher.symlink_to(target)

        result = self.run_install()

        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite unrelated existing path", result.stderr)
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(launcher.resolve(), target.resolve())
        self.assertEqual(target.read_text(encoding="utf-8"), "target\n")

    def test_non_utf8_file_collision_is_preserved(self) -> None:
        self.bin_dir.mkdir()
        launcher = self.bin_dir / "mem"
        launcher.write_bytes(b"\xff\xfeunrelated")
        launcher.chmod(0o755)

        result = self.run_install()

        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing to overwrite unrelated existing path", result.stderr)
        self.assertEqual(launcher.read_bytes(), b"\xff\xfeunrelated")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression coverage for the secrets credential-loading helper."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "secrets"


class SecretsScriptTests(unittest.TestCase):
    def test_run_uses_current_dotenvx_integration_disable_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            secrets_directory = temporary_path / "secrets"
            secrets_directory.mkdir()
            env_file = secrets_directory / ".env.slack"
            env_file.write_text("EXAMPLE=fixture\n", encoding="utf-8")

            executable_directory = temporary_path / "bin"
            executable_directory.mkdir()
            dotenvx = executable_directory / "dotenvx"
            dotenvx.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="utf-8"
            )
            dotenvx.chmod(0o755)

            environment = os.environ.copy()
            environment["SECRETS_HOME"] = str(secrets_directory)
            environment["PATH"] = (
                str(executable_directory) + os.pathsep + environment["PATH"]
            )

            result = subprocess.run(
                [str(SCRIPT_PATH), "slack", "--", "example-command", "argument"],
                capture_output=True,
                check=False,
                env=environment,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    "run",
                    "--no-armor",
                    "--no-native",
                    "--no-1password",
                    "--no-bitwarden",
                    "-f",
                    str(env_file),
                    "--",
                    "example-command",
                    "argument",
                ],
            )
            self.assertNotIn("--no-ops", result.stdout)


if __name__ == "__main__":
    unittest.main()

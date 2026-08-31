#!/usr/bin/env python3
"""Process-level coverage for managed memory-base index CLI contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "mem.py"
RESULT_FIELDS = {
    "base",
    "index_path",
    "status",
    "document_count",
    "source_fingerprint",
    "changed",
}


class IndexCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.first = self.root / "first"
        self.second = self.root / "second"
        self.first.mkdir()
        self.second.mkdir()
        (self.first / "guide.md").write_text("# Guide\n", encoding="utf-8")
        self.config = self.root / ".mem.yaml"
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                bases:
                  - name: first
                    description: First managed documentation.
                    root: {self.first}
                    aliases: [one]
                    schemas:
                      - name: global-core
                  - name: second
                    description: Second managed documentation.
                    root: {self.second}
                    schemas:
                      - name: global-core
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_index(self, mode: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "index", mode, *args, "--config", str(self.config)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_build_show_and_check_one_base(self) -> None:
        built = self.run_index("build", "--base", "one")
        self.assertEqual(built.returncode, 0, msg=built.stderr)
        payload = json.loads(built.stdout)
        self.assertEqual(payload["mode"], "index_build")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["config_paths"], [str(self.config.resolve())])
        result = payload["results"][0]
        self.assertTrue(RESULT_FIELDS.issubset(result))
        self.assertEqual(result["base"], "first")
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["document_count"], 1)
        self.assertTrue(result["changed"])

        shown = self.run_index("show", "--base", "one")
        self.assertEqual(shown.returncode, 0, msg=shown.stderr)
        shown_payload = json.loads(shown.stdout)
        self.assertEqual(shown_payload["mode"], "index_show")
        self.assertEqual(shown_payload["results"][0]["status"], "loaded")
        self.assertEqual(shown_payload["results"][0]["index"]["document_count"], 1)
        self.assertFalse(shown_payload["results"][0]["changed"])

        checked = self.run_index("check", "--base", "first")
        self.assertEqual(checked.returncode, 0, msg=checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["results"][0]["status"], "current")

        unchanged = self.run_index("build", "--base", "first")
        self.assertEqual(unchanged.returncode, 0, msg=unchanged.stderr)
        result = json.loads(unchanged.stdout)["results"][0]
        self.assertEqual(result["status"], "unchanged")
        self.assertFalse(result["changed"])

    def test_build_all_preserves_config_order_and_continues_after_error(self) -> None:
        (self.first / ".mem.index.json").mkdir()

        result = self.run_index("build", "--all")

        self.assertEqual(result.returncode, 1, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual([entry["base"] for entry in payload["results"]], ["first", "second"])
        self.assertEqual([entry["status"] for entry in payload["results"]], ["error", "created"])
        self.assertTrue((self.second / ".mem.index.json").is_file())

    def test_check_all_reports_current_missing_and_stale(self) -> None:
        self.assertEqual(self.run_index("build", "--base", "first").returncode, 0)

        missing = self.run_index("check", "--all")
        self.assertEqual(missing.returncode, 1, msg=missing.stderr)
        self.assertEqual(
            [result["status"] for result in json.loads(missing.stdout)["results"]],
            ["current", "missing"],
        )

        self.assertEqual(self.run_index("build", "--base", "second").returncode, 0)
        (self.first / "new.md").write_text("# New\n", encoding="utf-8")
        stale = self.run_index("check", "--all")
        self.assertEqual(stale.returncode, 1, msg=stale.stderr)
        self.assertEqual(
            [result["status"] for result in json.loads(stale.stdout)["results"]],
            ["stale", "current"],
        )

    def test_show_missing_is_structured(self) -> None:
        result = self.run_index("show", "--base", "first")

        self.assertEqual(result.returncode, 1, msg=result.stderr)
        entry = json.loads(result.stdout)["results"][0]
        self.assertEqual(entry["status"], "missing")
        self.assertIsNone(entry["document_count"])
        self.assertIsNone(entry["source_fingerprint"])
        self.assertFalse(entry["changed"])

    def test_show_and_check_report_malformed_index_then_build_repairs(self) -> None:
        (self.first / ".mem.index.json").write_text("not json\n", encoding="utf-8")

        for mode in ("show", "check"):
            with self.subTest(mode=mode):
                result = self.run_index(mode, "--base", "first")
                self.assertEqual(result.returncode, 1, msg=result.stderr)
                self.assertEqual(json.loads(result.stdout)["results"][0]["status"], "invalid")

        repaired = self.run_index("build", "--base", "first")
        self.assertEqual(repaired.returncode, 0, msg=repaired.stderr)
        self.assertEqual(json.loads(repaired.stdout)["results"][0]["status"], "updated")

    def test_build_updates_changed_paths(self) -> None:
        self.assertEqual(self.run_index("build", "--base", "first").returncode, 0)
        (self.first / "new.md").write_text("# New\n", encoding="utf-8")

        result = self.run_index("build", "--base", "first")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        entry = json.loads(result.stdout)["results"][0]
        self.assertEqual(entry["status"], "updated")
        self.assertEqual(entry["document_count"], 2)
        self.assertTrue(entry["changed"])

    def test_unsupported_index_is_invalid_to_read_but_cannot_be_repaired(self) -> None:
        self.assertEqual(self.run_index("build", "--base", "first").returncode, 0)
        index_path = self.first / ".mem.index.json"
        unsupported = json.loads(index_path.read_text(encoding="utf-8"))
        unsupported["version"] = 999
        index_path.write_text(json.dumps(unsupported) + "\n", encoding="utf-8")

        for mode, expected_status in (
            ("show", "invalid"),
            ("check", "invalid"),
            ("build", "error"),
        ):
            with self.subTest(mode=mode):
                result = self.run_index(mode, "--base", "first")
                self.assertEqual(result.returncode, 1, msg=result.stderr)
                self.assertEqual(json.loads(result.stdout)["results"][0]["status"], expected_status)

    def test_configuration_failure_exits_two_without_structured_results(self) -> None:
        self.config.write_text("version: 1\nbases: []\n", encoding="utf-8")

        result = self.run_index("build", "--base", "first")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("error:", result.stderr)

    def test_invalid_arguments_and_unknown_base_exit_two(self) -> None:
        for mode, args in (
            ("build", ()),
            ("build", ("--base", "first", "--all")),
            ("show", ("--all",)),
            ("check", ("--base", "missing")),
            ("build", ("--base", "first", "--allow-missing-roots")),
        ):
            with self.subTest(mode=mode, args=args):
                result = self.run_index(mode, *args)
                self.assertEqual(result.returncode, 2, msg=result.stderr)
                self.assertFalse(result.stdout)
                if "usage:" in result.stderr:
                    self.assertIn("usage: mem index", result.stderr)

    def test_symlink_index_is_rejected_before_per_base_work(self) -> None:
        target = self.root / "outside.json"
        target.write_text("{}\n", encoding="utf-8")
        (self.first / ".mem.index.json").symlink_to(target)

        result = self.run_index("build", "--all")

        self.assertEqual(result.returncode, 2, msg=result.stderr)
        self.assertFalse(result.stdout)
        self.assertFalse((self.second / ".mem.index.json").exists())

    def test_pretty_json_output(self) -> None:
        result = self.run_index("build", "--base", "first", "--pretty")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('\n  "mode":', result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "ok")


if __name__ == "__main__":
    unittest.main()

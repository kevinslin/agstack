#!/usr/bin/env python3
"""End-to-end tests for read-only context lookup audit tracing."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
MEM_PATH = TEST_DIR.parents[0] / "mem.py"
SCRIPT_DIR = MEM_PATH.parent
sys.path.insert(0, str(SCRIPT_DIR))
context_module = importlib.import_module("context")
SESSION_ID = "019fa5de-c89c-7402-ad74-2978a02a04ad"


class ContextLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.base = self.root / "knowledge"
        self.base.mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        self.trace_root = self.root / "traces"
        self.schema = self.root / "schema.yaml"
        self.schema.write_text(
            textwrap.dedent(
                """
                version: 1.0
                schema:
                  pkg:
                    description: Package gateway authentication knowledge.
                    children:
                      ref:
                        description: Authentication reference material.
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.config = self.root / ".mem.yaml"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_config(
        self,
        *,
        enabled: bool,
        bases: list[tuple[str, Path]] | None = None,
        trace_root: Path | None = None,
    ) -> None:
        configured_bases = bases or [("docs", self.base)]
        base_yaml = "\n".join(
            textwrap.dedent(
                f"""
                  - name: {name}
                    description: Durable package documentation.
                    root: {root}
                    path_style: directory
                    schemas:
                      - name: pkg
                        path: {self.schema}
                """
            ).rstrip()
            for name, root in configured_bases
        )
        chosen_root = trace_root or self.trace_root
        self.config.write_text(
            f"version: 2\naudit:\n  enabled: {str(enabled).lower()}\n"
            f"  trace_root: {chosen_root}\nbases:\n{base_yaml}\n",
            encoding="utf-8",
        )

    def run_lookup(
        self,
        query: str,
        *extra: str,
        session_id: str | None = SESSION_ID,
        secret: str | None = None,
        process_cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("CODEX_THREAD_ID", None)
        if session_id is not None:
            env["CODEX_THREAD_ID"] = session_id
        if secret is not None:
            env["UNRELATED_SECRET"] = secret
        return subprocess.run(
            [
                "python3",
                str(MEM_PATH),
                "context",
                "lookup",
                "--query",
                query,
                "--config",
                str(self.config),
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
            env=env,
            cwd=process_cwd,
        )

    def trace_files(self) -> list[Path]:
        return sorted(self.trace_root.glob(f"[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]/{SESSION_ID}.jsonl"))

    def records(self) -> list[dict[str, object]]:
        files = self.trace_files()
        self.assertEqual(len(files), 1)
        return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line]

    def test_disabled_lookup_creates_no_trace_and_does_not_require_session(self) -> None:
        self.write_config(enabled=False)
        (self.base / "authentication.md").write_text("gateway authentication\n", encoding="utf-8")

        result = self.run_lookup("gateway authentication", session_id=None)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "matched")
        self.assertFalse(self.trace_root.exists())

    def test_empty_query_is_rejected_without_searching(self) -> None:
        self.write_config(enabled=True)
        (self.base / "would-match.md").write_text("anything\n", encoding="utf-8")

        result = self.run_lookup("   ", "--target", "docs")

        self.assertEqual(result.returncode, 2)
        self.assertIn("query must not be empty", result.stderr)
        record = self.records()[0]
        self.assertEqual(record["status"], "error")
        self.assertEqual([op["name"] for op in record["operations"]], ["load_config"])
        self.assertEqual(record["matched_paths"], [])

    def test_enabled_lookup_records_actual_command_hierarchy_and_timings(self) -> None:
        self.write_config(enabled=True)
        match = self.base / "authentication.md"
        match.write_text("gateway authentication\n", encoding="utf-8")
        secret = "must-not-appear-in-trace"

        result = self.run_lookup("gateway authentication", "--target", "docs", secret=secret)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        record = self.records()[0]
        self.assertEqual(record["query"], "gateway authentication")
        self.assertEqual(record["status"], "matched")
        self.assertEqual(record["matched_paths"], [str(match.resolve())])
        self.assertEqual([op["name"] for op in record["operations"]], [
            "load_config",
            "build_index",
            "route",
            "resolve_schemas",
            "search_managed",
        ])
        command = record["commands"][0]
        self.assertEqual(Path(command["argv"][0]).name, "python3")
        self.assertEqual(command["argv"][1], str(MEM_PATH))
        self.assertIn("'gateway authentication'", command["command"])
        self.assertNotIn("context.py", command["command"])
        self.assertNotIn(secret, json.dumps(record))
        self.assertEqual(record["selection"]["tier"], "explicit")
        self.assertEqual(record["hierarchy"][0]["path"], str(self.base.resolve()))
        self.assertIn("sharing query terms", record["hierarchy"][0]["reason"])
        for timing in [record, command, *record["operations"]]:
            self.assertGreaterEqual(timing["duration_ms"], 0)
            self.assertIsNotNone(datetime.fromisoformat(timing["started_at"]).tzinfo)
            self.assertIsNotNone(datetime.fromisoformat(timing["finished_at"]).tzinfo)

    def test_source_fallback_is_recorded_only_when_it_runs(self) -> None:
        self.write_config(enabled=True)
        source_match = self.source / "gateway.py"
        source_match.write_text("authenticate gateway request\n", encoding="utf-8")

        result = self.run_lookup(
            "gateway authenticate",
            "--target",
            "docs",
            "--source",
            str(self.source),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        record = self.records()[0]
        self.assertEqual(record["status"], "matched")
        self.assertEqual(record["matched_paths"], [str(source_match.resolve())])
        self.assertTrue(record["fallback"]["used"])
        self.assertEqual(record["fallback"]["paths"], [str(self.source.resolve())])
        self.assertEqual(record["operations"][-1]["name"], "search_source")
        self.assertEqual(record["hierarchy"][-1]["schema"], "source")

    def test_source_search_streams_text_and_skips_large_or_binary_bodies(self) -> None:
        self.write_config(enabled=True)
        text_match = self.source / "small.txt"
        text_match.write_text("needle phrase\n", encoding="utf-8")
        (self.source / "large.dat").write_text(
            "needle phrase\n" + "x" * (2 * 1024 * 1024),
            encoding="utf-8",
        )
        (self.source / "binary.dat").write_bytes(b"needle phrase\x00payload")

        result = self.run_lookup(
            "needle phrase",
            "--target",
            "docs",
            "--source",
            str(self.source),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(self.records()[0]["matched_paths"], [str(text_match.resolve())])

    def test_source_search_rejects_file_replaced_by_symlink_before_open(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("outside secret\n", encoding="utf-8")
        victim = self.source / "victim.txt"
        victim.write_text("safe text\n", encoding="utf-8")
        original_open = context_module.os.open
        replaced = False

        def replace_then_open(
            path: str | Path,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal replaced
            if dir_fd is not None and os.fspath(path) == victim.name and not replaced:
                victim.unlink()
                victim.symlink_to(outside)
                replaced = True
            if dir_fd is None:
                return original_open(path, flags, mode)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(context_module.os, "open", side_effect=replace_then_open):
            matches = context_module.search_scope(self.source, "outside secret")

        self.assertTrue(replaced)
        self.assertEqual(matches, [])

    def test_source_search_rejects_directory_replaced_by_symlink_before_open(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("outside secret\n", encoding="utf-8")
        nested = self.source / "nested"
        nested.mkdir()
        (nested / "safe.txt").write_text("safe text\n", encoding="utf-8")
        original_open = context_module.os.open
        replaced = False

        def replace_then_open(
            path: str | Path,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal replaced
            if dir_fd is not None and os.fspath(path) == nested.name and not replaced:
                (nested / "safe.txt").unlink()
                nested.rmdir()
                nested.symlink_to(outside, target_is_directory=True)
                replaced = True
            if dir_fd is None:
                return original_open(path, flags, mode)
            return original_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch.object(context_module.os, "open", side_effect=replace_then_open):
            matches = context_module.search_scope(self.source, "outside secret")

        self.assertTrue(replaced)
        self.assertEqual(matches, [])

    def test_ambiguous_lookup_records_status_without_search_stages(self) -> None:
        other = self.root / "other"
        other.mkdir()
        self.write_config(enabled=True, bases=[("docs", self.base), ("other", other)])

        result = self.run_lookup("unrelated")

        self.assertEqual(result.returncode, 2, msg=result.stderr)
        record = self.records()[0]
        self.assertEqual(record["status"], "ambiguous")
        self.assertEqual(record["hierarchy"], [])
        self.assertEqual(
            [op["name"] for op in record["operations"]],
            ["load_config", "build_index", "build_index", "route"],
        )

    def test_every_repeatable_source_scope_can_influence_routing(self) -> None:
        other = self.root / "other"
        other.mkdir()
        first_source = self.root / "first-source"
        first_source.mkdir()
        second_source = self.root / "second-source"
        second_source.mkdir()
        self.config.write_text(
            textwrap.dedent(
                f"""
                version: 2
                audit:
                  enabled: true
                  trace_root: {self.trace_root}
                bases:
                  - name: docs
                    description: Durable package documentation.
                    root: {self.base}
                    schemas:
                      - name: pkg
                        path: {self.schema}
                  - name: other
                    description: Durable package documentation.
                    root: {other}
                    match:
                      source_globs: ["second-source"]
                    schemas:
                      - name: pkg
                        path: {self.schema}
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        result = self.run_lookup(
            "not present",
            "--source",
            "first-source",
            "--source",
            "second-source",
            process_cwd=self.root,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["selection"]["bases"], ["other"], msg=result.stdout)
        self.assertEqual(output["status"], "no_matches")
        record = self.records()[0]
        self.assertEqual(record["selection"]["bases"], ["other"])
        self.assertIn("source:second-source", record["selection"]["reasons"])

    def test_failed_fallback_records_real_error_status(self) -> None:
        self.write_config(enabled=True)
        missing = self.root / "missing-source"

        result = self.run_lookup(
            "not present",
            "--target",
            "docs",
            "--source",
            str(self.source),
            "--source",
            str(missing),
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("source path does not exist", result.stderr)
        record = self.records()[0]
        self.assertEqual(record["status"], "error")
        self.assertEqual([operation["name"] for operation in record["operations"]], ["load_config"])
        self.assertEqual(record["fallback"]["paths"], [str(self.source.resolve())])
        self.assertEqual(record["hierarchy"], [])

    def test_missing_or_unsafe_session_fails_before_search(self) -> None:
        self.write_config(enabled=True)
        (self.base / "would-match.md").write_text("gateway authentication\n", encoding="utf-8")

        for session_id in (None, "../not-a-session"):
            with self.subTest(session_id=session_id):
                result = self.run_lookup("gateway authentication", session_id=session_id)
                self.assertEqual(result.returncode, 2)
                self.assertIn("audit session ID", result.stderr)

        self.assertFalse(self.trace_root.exists())

    def test_duplicate_and_distinct_logical_lookups_are_merged_correctly(self) -> None:
        self.write_config(enabled=True)
        (self.base / "authentication.md").write_text("gateway authentication tokens\n", encoding="utf-8")

        first = self.run_lookup("gateway authentication", "--target", "docs")
        second = self.run_lookup("gateway authentication", "--target", "docs")
        distinct = self.run_lookup("authentication tokens", "--target", "docs")

        self.assertEqual((first.returncode, second.returncode, distinct.returncode), (0, 0, 0))
        records = self.records()
        self.assertEqual(len(records), 2)
        repeated = next(record for record in records if record["query"] == "gateway authentication")
        self.assertEqual(repeated["occurrence_count"], 2)
        self.assertEqual(len(repeated["attempts"]), 2)
        self.assertEqual(
            repeated["duration_ms"],
            sum(attempt["duration_ms"] for attempt in repeated["attempts"]),
        )
        first_operations = [operation["name"] for operation in repeated["attempts"][0]["operation_timings"]]
        second_operations = [operation["name"] for operation in repeated["attempts"][1]["operation_timings"]]
        self.assertEqual(first_operations.count("build_index"), 1)
        self.assertNotIn("load_index", first_operations)
        self.assertEqual(second_operations.count("load_index"), 1)
        self.assertNotIn("build_index", second_operations)

    def test_unwritable_trace_destination_fails_closed(self) -> None:
        bad_root = self.root / "trace-file"
        bad_root.write_text("not a directory\n", encoding="utf-8")
        self.write_config(enabled=True, trace_root=bad_root)
        (self.base / "authentication.md").write_text("gateway authentication\n", encoding="utf-8")

        result = self.run_lookup("gateway authentication", "--target", "docs")

        self.assertEqual(result.returncode, 2)
        self.assertIn("audit trace failed", result.stderr)
        self.assertEqual(bad_root.read_text(encoding="utf-8"), "not a directory\n")


if __name__ == "__main__":
    unittest.main()

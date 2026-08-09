#!/usr/bin/env python3
"""Secure, exhaustive integration coverage for managed memory-base indexes."""

from __future__ import annotations

import fcntl
import importlib
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
base_index = importlib.import_module("base_index")
routing_signals = importlib.import_module("routing_signals")


def _concurrent_build(root: str, results: multiprocessing.Queue) -> None:
    try:
        result = base_index.build_index({"managed_root": root, "path_style": "directory"})
        results.put((result["status"], result["source_fingerprint"]))
    except Exception as exc:  # pragma: no cover - surfaced to the parent process
        results.put(("error", str(exc)))


class RoutingSignalTests(unittest.TestCase):
    def test_labels_use_casefolded_ascii_tokens_and_reject_numeric_labels(self) -> None:
        self.assertEqual(routing_signals.normalized_words("Claw-CMD_auth 2"), ["claw", "cmd", "auth", "2"])
        self.assertEqual(routing_signals.normalize_label("  Claw-CMD_auth 2 "), "claw cmd auth 2")
        self.assertEqual(routing_signals.normalize_label("2026.08.08"), "")
        self.assertEqual(routing_signals.normalize_label("---"), "")

    def test_alias_table_preserves_cookbook_expansion_and_plural_aliases(self) -> None:
        self.assertEqual(routing_signals.ARTIFACT_ALIASES["cook"], ("cookbook", "guide"))
        self.assertEqual(routing_signals.ARTIFACT_ALIASES["references"], ("reference",))
        self.assertIn("runbooks", routing_signals.ARTIFACT_WORDS)


class BaseIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.base = {"name": "example", "managed_root": str(self.root), "path_style": "directory"}
        self.index_path = self.root / ".mem.index.json"

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def write(self, path: str, body: str = "secret body never belongs in the index") -> Path:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body, encoding="utf-8")
        return destination

    def test_directory_hierarchy_counts_metadata_and_body_exclusion(self) -> None:
        self.write("pkg/clawcmd/ref/auth.md")
        self.write("pkg/clawcmd/cook/setup.md")
        self.write("pkg/gateway/specs/current.md")
        self.write("research/report.md")
        self.write("2026/08.md")
        result = base_index.build_index(self.base)

        self.assertEqual(result["status"], "created")
        self.assertTrue(result["changed"])
        self.assertEqual(result["document_count"], 5)
        self.assertEqual(result["index_path"], str(self.index_path))
        self.assertEqual(result["index"]["metadata"]["topics"], ["clawcmd", "gateway", "pkg"])
        self.assertEqual(result["index"]["metadata"]["artifact_kinds"], ["report", "research"])
        self.assertEqual(
            result["index"]["hierarchy"],
            [
                {"path": "2026", "document_count": 1, "children": [{"path": "2026/08", "document_count": 1}]},
                {
                    "path": "pkg",
                    "document_count": 3,
                    "children": [
                        {"path": "pkg/clawcmd", "document_count": 2},
                        {"path": "pkg/gateway", "document_count": 1},
                    ],
                },
                {
                    "path": "research",
                    "document_count": 1,
                    "children": [{"path": "research/report", "document_count": 1}],
                },
            ],
        )
        raw = self.index_path.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        self.assertNotIn("secret body", raw)
        self.assertNotIn(str(self.root), raw)

    def test_directory_and_dotted_paths_have_equivalent_logical_metadata(self) -> None:
        self.write("pkg/clawcmd/auth.md")
        self.write("cook/setup.md")
        directory = base_index.build_index(self.base)["index"]

        with tempfile.TemporaryDirectory() as dotted_root:
            root = Path(dotted_root)
            (root / "pkg.clawcmd.auth.md").write_text("body", encoding="utf-8")
            (root / "cook.setup.md").write_text("body", encoding="utf-8")
            dotted = base_index.build_index(
                {"managed_root": dotted_root, "path_style": "dotted"}
            )["index"]

        self.assertEqual(directory["hierarchy"], dotted["hierarchy"])
        self.assertEqual(directory["metadata"], dotted["metadata"])
        self.assertEqual(directory["metadata"]["artifact_kinds"], ["cookbook", "guide"])
        self.assertIn("setup", directory["metadata"]["topics"])

    def test_build_is_idempotent_and_body_edits_do_not_change_fingerprint(self) -> None:
        document = self.write("pkg/clawcmd.md", "old content")
        first = base_index.build_index(self.base)
        original = self.index_path.read_bytes()
        document.write_text("new content entirely", encoding="utf-8")
        second = base_index.build_index(self.base)

        self.assertEqual(second["status"], "unchanged")
        self.assertFalse(second["changed"])
        self.assertEqual(second["source_fingerprint"], first["source_fingerprint"])
        self.assertEqual(self.index_path.read_bytes(), original)
        self.assertEqual(second["index"]["generated_at"], first["index"]["generated_at"])

    def test_add_rename_and_remove_mark_indexes_stale_until_rebuilt(self) -> None:
        first_document = self.write("pkg/first.md")
        first = base_index.build_index(self.base)
        self.assertEqual(base_index.check_index(self.base)["status"], "current")

        second_document = self.write("pkg/second.md")
        self.assertEqual(base_index.check_index(self.base)["status"], "stale")
        second = base_index.build_index(self.base)
        self.assertEqual(second["status"], "updated")
        self.assertNotEqual(second["source_fingerprint"], first["source_fingerprint"])

        renamed = first_document.with_name("renamed.md")
        first_document.rename(renamed)
        self.assertEqual(base_index.check_index(self.base)["status"], "stale")
        base_index.build_index(self.base)

        second_document.unlink()
        self.assertEqual(base_index.check_index(self.base)["status"], "stale")
        self.assertEqual(base_index.build_index(self.base)["document_count"], 1)

    def test_index_exceeds_existing_file_and_directory_lookup_caps(self) -> None:
        for index in range(2_105):
            self.write(f"area{index % 530:03d}/topic{index:04d}.md", "x")

        built = base_index.build_index(self.base)
        checked = base_index.check_index(self.base)

        self.assertEqual(built["document_count"], 2_105)
        self.assertEqual(len(built["index"]["hierarchy"]), 530)
        self.assertEqual(checked["status"], "current")
        self.assertEqual(checked["document_count"], 2_105)
        self.assertIn("topic2104", built["index"]["metadata"]["topics"])

    def test_hidden_generated_nonmarkdown_and_symlink_paths_are_excluded(self) -> None:
        included = self.write("visible/allowed.md")
        self.write(".hidden/secret.md")
        self.write("node_modules/dependency.md")
        self.write("build/generated.md")
        self.write("vendor/generated.md")
        self.write("visible/ignored.txt")
        (self.root / "linked-file.md").symlink_to(included)
        (self.root / "linked-directory").symlink_to(self.root / "visible", target_is_directory=True)

        result = base_index.build_index(self.base)

        self.assertEqual(result["document_count"], 1)
        self.assertEqual(result["index"]["metadata"]["topics"], ["allowed", "visible"])

    def test_scanner_does_not_open_document_bodies(self) -> None:
        self.write("visible/allowed.md", "super-secret-content")
        original_open = os.open

        def guarded_open(path: object, *args: object, **kwargs: object) -> int:
            if str(path).endswith(".md"):
                raise AssertionError("index scanner attempted to open a Markdown body")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(base_index.os, "open", side_effect=guarded_open):
            result = base_index.build_index(self.base)

        self.assertEqual(result["document_count"], 1)

    def test_missing_index_is_reported_and_initialized_once(self) -> None:
        self.write("pkg/clawcmd.md")
        self.assertEqual(base_index.check_index(self.base)["status"], "missing")
        with self.assertRaises(base_index.BaseIndexError) as raised:
            base_index.read_index(self.base)
        self.assertEqual(raised.exception.kind, "missing")

        status, index, generated = base_index.ensure_index(self.base)
        self.assertEqual((status, generated), ("generated", True))
        self.assertEqual(index["document_count"], 1)
        status, index, generated = base_index.ensure_index(self.base)
        self.assertEqual((status, generated), ("loaded", False))

    def test_malformed_regular_index_requires_explicit_repair(self) -> None:
        self.write("pkg/clawcmd.md")
        self.index_path.write_text("{malformed", encoding="utf-8")
        original = self.index_path.read_bytes()

        self.assertEqual(base_index.ensure_index(self.base), ("invalid", None, False))
        self.assertEqual(base_index.check_index(self.base)["status"], "invalid")
        self.assertEqual(self.index_path.read_bytes(), original)
        with self.assertRaises(base_index.BaseIndexError) as raised:
            base_index.read_index(self.base)
        self.assertEqual(raised.exception.kind, "invalid")

        repaired = base_index.build_index(self.base)
        self.assertEqual(repaired["status"], "updated")
        self.assertEqual(base_index.check_index(self.base)["status"], "current")

    def test_missing_version_is_repairable_but_unsupported_format_is_not(self) -> None:
        self.index_path.write_text('{"not_an_index": true}\n', encoding="utf-8")
        self.assertEqual(base_index.build_index(self.base)["status"], "updated")

        for unsupported in (99, 1.0, True, "1"):
            with self.subTest(version=unsupported):
                self.index_path.write_text(json.dumps({"version": unsupported}), encoding="utf-8")
                self.assertEqual(base_index.check_index(self.base)["status"], "invalid")
                self.assertEqual(base_index.ensure_index(self.base), ("invalid", None, False))
                with self.assertRaises(base_index.BaseIndexError) as raised:
                    base_index.build_index(self.base)
                self.assertEqual(raised.exception.kind, "unsupported")

    def test_validation_rejects_unexpected_and_absolute_hierarchy_paths(self) -> None:
        self.write("pkg/clawcmd.md")
        base_index.build_index(self.base)
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        payload["hierarchy"][0]["path"] = "/outside"
        self.index_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(base_index.check_index(self.base)["status"], "invalid")

        payload["hierarchy"][0]["path"] = "pkg"
        payload["body"] = "document contents must never be accepted"
        self.index_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(base_index.ensure_index(self.base), ("invalid", None, False))

    def test_symlink_index_target_is_never_read_or_replaced(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_text("do not replace", encoding="utf-8")
        self.index_path.symlink_to(outside)

        for operation in (base_index.read_index, base_index.check_index, base_index.build_index):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(base_index.BaseIndexError) as raised:
                    operation(self.base)
                self.assertEqual(raised.exception.kind, "unsafe")
        self.assertEqual(base_index.ensure_index(self.base), ("build_failed", None, False))
        self.assertEqual(outside.read_text(encoding="utf-8"), "do not replace")

    def test_symlink_managed_root_and_index_containment_escape_are_rejected(self) -> None:
        real = self.root / "real"
        real.mkdir()
        linked = self.root / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with self.assertRaises(base_index.BaseIndexError):
            base_index.build_index({"managed_root": str(linked), "path_style": "directory"})

        for unsafe_path in (
            self.root.parent / ".mem.index.json",
            self.root / "nested" / ".mem.index.json",
            self.root / ".." / ".mem.index.json",
        ):
            with self.subTest(index_path=str(unsafe_path)):
                with self.assertRaises(base_index.BaseIndexError) as raised:
                    base_index.build_index({**self.base, "index_path": str(unsafe_path)})
                self.assertEqual(raised.exception.kind, "unsafe")

    def test_failed_atomic_replacement_preserves_existing_index_and_cleans_temp(self) -> None:
        self.write("pkg/first.md")
        base_index.build_index(self.base)
        previous = self.index_path.read_bytes()
        self.write("pkg/second.md")

        with mock.patch.object(base_index.os, "replace", side_effect=OSError("replacement failed")):
            with self.assertRaisesRegex(base_index.BaseIndexError, "replacement failed"):
                base_index.build_index(self.base)

        self.assertEqual(self.index_path.read_bytes(), previous)
        self.assertEqual(list(self.root.glob(".mem.index.json.*")), [])

    def test_exclusive_lock_timeout_does_not_create_a_lock_artifact(self) -> None:
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            with mock.patch.object(base_index, "LOCK_TIMEOUT_SECONDS", 0.12):
                with self.assertRaisesRegex(base_index.BaseIndexError, "lock timed out"):
                    base_index.build_index(self.base)
                self.assertEqual(base_index.ensure_index(self.base), ("build_failed", None, False))
        finally:
            os.close(descriptor)

        self.assertEqual(list(self.root.iterdir()), [])

    def test_locks_are_independent_for_separate_managed_roots(self) -> None:
        other_root = self.root / "other"
        other_root.mkdir()
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            result = base_index.build_index(
                {"managed_root": str(other_root), "path_style": "directory"}
            )
        finally:
            os.close(descriptor)
        self.assertEqual(result["status"], "created")

    def test_concurrent_builds_produce_one_complete_deterministic_index(self) -> None:
        for index in range(30):
            self.write(f"pkg/topic{index:02d}.md")
        context = multiprocessing.get_context("fork")
        results = context.Queue()
        processes = [context.Process(target=_concurrent_build, args=(str(self.root), results)) for _ in range(4)]
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=10) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)

        self.assertEqual(sorted(status for status, _ in outcomes), ["created", "unchanged", "unchanged", "unchanged"])
        self.assertEqual(len({fingerprint for _, fingerprint in outcomes}), 1)
        self.assertEqual(base_index.read_index(self.base)["document_count"], 30)
        self.assertEqual(list(self.root.glob("*.lock")), [])


if __name__ == "__main__":
    unittest.main()

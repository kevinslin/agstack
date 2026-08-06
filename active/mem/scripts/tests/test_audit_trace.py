#!/usr/bin/env python3
"""Focused tests for secure mem audit trace persistence."""

from __future__ import annotations

import importlib
import json
import multiprocessing
import os
import re
import stat
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TEST_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
audit_trace = importlib.import_module("audit_trace")


SESSION_ID = "019fa5de-c89c-7402-ad74-2978a02a04ad"
PACIFIC = timezone(timedelta(hours=-7))


def make_record(
    *,
    query: str = "gateway authentication",
    started: datetime | None = None,
    duration_ms: int = 87,
    status: str = "matched",
    source_scopes: list[str] | None = None,
) -> dict[str, object]:
    started = started or datetime(2026, 8, 6, 9, 2, tzinfo=PACIFIC)
    finished = started + timedelta(milliseconds=duration_ms)
    started_at = audit_trace.timestamp_ms(started)
    finished_at = audit_trace.timestamp_ms(finished)
    command = {
        "argv": [
            "python3",
            "./scripts/mem.py",
            "context",
            "lookup",
            "--query",
            query,
            "--target",
            "claw",
        ],
        "command": "caller supplied text is normalized",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
    }
    operation = {
        "name": "route",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
    }
    attempt = {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "command_timings": [
            {
                "command_index": 0,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
            }
        ],
        "operation_timings": [operation.copy()],
        "status": status,
    }
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "query": query,
        "commands": [command],
        "operations": [operation],
        "attempts": [attempt],
        "hierarchy": [
            {
                "path": "/knowledge/pkg/clawgateway",
                "schema": "pkg",
                "decision": "searched",
                "reason": "The selected base contains the requested package.",
            }
        ],
        "selection": {
            "tier": "explicit",
            "bases": ["claw"],
            "reasons": ["explicit base name"],
        },
        "source_scopes": source_scopes or [],
        "fallback": {"used": False, "paths": [], "reason": "Managed match."},
        "status": status,
        "matched_paths": ["/knowledge/pkg/clawgateway/ref/authentication.md"],
    }


def concurrent_write(trace_root: str, index: int) -> None:
    record = make_record(
        started=datetime(2026, 8, 6, 9, 2, tzinfo=PACIFIC)
        + timedelta(seconds=index),
        duration_ms=index + 1,
        status=f"attempt-{index}",
    )
    audit_trace.AuditTraceWriter(trace_root, SESSION_ID).write(record)


class AuditTraceHelperTests(unittest.TestCase):
    def test_session_id_is_explicitly_validated_and_canonicalized(self) -> None:
        self.assertEqual(
            audit_trace.validate_session_id(SESSION_ID.upper()),
            SESSION_ID,
        )
        for invalid in ("", "../conversation", "not-a-uuid"):
            with self.subTest(invalid=invalid), self.assertRaises(audit_trace.AuditTraceError):
                audit_trace.validate_session_id(invalid)

    def test_timestamp_duration_and_shell_helpers(self) -> None:
        moment = datetime(2026, 8, 6, 9, 2, 0, 123456, tzinfo=PACIFIC)
        self.assertEqual(audit_trace.timestamp_ms(moment), "2026-08-06T09:02:00.123-07:00")
        self.assertEqual(audit_trace.elapsed_ms(10.0, 10.0874), 87)
        self.assertEqual(
            audit_trace.shell_quote_argv(["mem", "two words", "", "$TOKEN", "it's"]),
            "mem 'two words' '' '$TOKEN' 'it'\"'\"'s'",
        )
        with self.assertRaises(audit_trace.AuditTraceError):
            audit_trace.timestamp_ms(moment.replace(tzinfo=None))
        with self.assertRaises(audit_trace.AuditTraceError):
            audit_trace.elapsed_ms(2.0, 1.0)
        rollback = audit_trace.timing_snapshot(
            started_at=moment,
            finished_at=moment - timedelta(seconds=1),
            start_monotonic=10.0,
            finished_monotonic=10.005,
        )
        self.assertEqual(rollback["duration_ms"], 5)

    def test_fingerprint_is_canonical_and_covers_only_logical_lookup_fields(self) -> None:
        arguments = {
            "session_id": SESSION_ID,
            "query": "auth",
            "commands": [["mem", "lookup", "auth"]],
            "selected_bases": ["claw"],
            "hierarchy_paths": ["/knowledge/claw"],
            "source_scopes": ["codex/claw/**"],
        }
        first = audit_trace.canonical_lookup_id(**arguments)
        second = audit_trace.canonical_lookup_id(**dict(reversed(list(arguments.items()))))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")

        for field, replacement in (
            ("query", "different"),
            ("commands", [["mem", "lookup", "different"]]),
            ("selected_bases", ["other"]),
            ("hierarchy_paths", ["/knowledge/other"]),
            ("source_scopes", ["other/**"]),
        ):
            changed = dict(arguments)
            changed[field] = replacement
            with self.subTest(field=field):
                self.assertNotEqual(first, audit_trace.canonical_lookup_id(**changed))


class AuditTraceWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "traces"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def read_records(self, path: Path) -> list[dict[str, object]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_prepare_pins_first_local_date_and_secures_paths(self) -> None:
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        first_day = datetime(2026, 8, 6, 23, 59, tzinfo=PACIFIC)
        with writer.locked(now=first_day) as locked_writer:
            self.assertIs(locked_writer, writer)
            first_path = writer.trace_path
            self.assertEqual(
                first_path.relative_to(writer.trace_root),
                Path("2026/08/06") / f"{SESSION_ID}.jsonl",
            )
            self.assertTrue(first_path.is_file())

        next_day = first_day + timedelta(minutes=2)
        with audit_trace.AuditTraceWriter(self.root, SESSION_ID).locked(now=next_day) as second:
            self.assertEqual(second.trace_path, first_path)

        for directory in (
            self.root,
            self.root / ".locks",
            self.root / "2026",
            self.root / "2026" / "08",
            self.root / "2026" / "08" / "06",
        ):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(first_path.stat().st_mode), 0o600)
        lock_path = self.root / ".locks" / f"{SESSION_ID}.lock"
        self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o600)

        first_path.parent.chmod(0o755)
        first_path.chmod(0o644)
        with audit_trace.AuditTraceWriter(self.root, SESSION_ID).locked(now=next_day):
            pass
        self.assertEqual(stat.S_IMODE(first_path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(first_path.stat().st_mode), 0o600)

    def test_write_normalizes_command_and_merges_duplicate_attempts(self) -> None:
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        first = make_record(duration_ms=10, status="unmatched")
        second = make_record(
            started=datetime(2026, 8, 6, 9, 3, tzinfo=PACIFIC),
            duration_ms=20,
            status="matched",
        )
        path = writer.write(first)
        self.assertEqual(writer.write(second), path)

        records = self.read_records(path)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["occurrence_count"], 2)
        self.assertEqual(record["duration_ms"], 30)
        self.assertEqual(record["started_at"], first["started_at"])
        self.assertEqual(record["finished_at"], second["finished_at"])
        self.assertEqual(record["status"], "matched")
        self.assertEqual(len(record["attempts"]), 2)
        self.assertEqual(record["operations"], second["operations"])
        self.assertEqual(
            record["commands"][0]["command"],
            "python3 ./scripts/mem.py context lookup --query 'gateway authentication' --target claw",
        )

    def test_distinct_logical_lookups_are_separate_json_lines(self) -> None:
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        path = writer.write(make_record(query="authentication"))
        writer.write(make_record(query="authorization"))
        records = self.read_records(path)
        self.assertEqual([record["query"] for record in records], ["authentication", "authorization"])
        self.assertNotEqual(records[0]["lookup_id"], records[1]["lookup_id"])

    def test_concurrent_duplicate_writes_lose_no_attempts(self) -> None:
        context = multiprocessing.get_context("spawn")
        processes = [
            context.Process(target=concurrent_write, args=(str(self.root), index))
            for index in range(8)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=15)
            self.assertEqual(process.exitcode, 0)

        expected = self.root / "2026" / "08" / "06" / f"{SESSION_ID}.jsonl"
        records = self.read_records(expected)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["occurrence_count"], 8)
        self.assertEqual(len(records[0]["attempts"]), 8)
        self.assertEqual(records[0]["duration_ms"], sum(range(1, 9)))

    def test_containment_rejects_date_directory_symlink(self) -> None:
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        self.root.mkdir()
        (self.root / "2026").symlink_to(outside, target_is_directory=True)
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "outside trace root"):
            writer.prepare(now=datetime(2026, 8, 6, tzinfo=PACIFIC))
        self.assertFalse((outside / "08").exists())

    def test_invalid_session_fails_before_touching_trace_root(self) -> None:
        os.environ["CODEX_THREAD_ID"] = SESSION_ID
        try:
            with self.assertRaisesRegex(audit_trace.AuditTraceError, "valid UUID"):
                audit_trace.AuditTraceWriter(self.root, "../unsafe")
        finally:
            os.environ.pop("CODEX_THREAD_ID", None)
        self.assertFalse(self.root.exists())

    def test_malformed_existing_trace_is_an_explicit_prepare_error(self) -> None:
        path = self.root / "2026" / "08" / "06" / f"{SESSION_ID}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("not json\n", encoding="utf-8")
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "invalid JSON"):
            writer.prepare(now=datetime(2026, 8, 7, tzinfo=PACIFIC))

    def test_failed_atomic_replace_preserves_existing_trace(self) -> None:
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        path = writer.write(make_record(query="first"))
        original = path.read_bytes()
        with mock.patch.object(audit_trace.os, "replace", side_effect=OSError("denied")):
            with self.assertRaisesRegex(audit_trace.AuditTraceError, "atomically update"):
                writer.write(make_record(query="second"))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_record_validation_reports_unsafe_or_incomplete_data(self) -> None:
        record = make_record()
        record["started_at"] = "2026-08-06T09:02:00"
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "timezone-aware"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).write(record)

        record = make_record()
        record["attempts"][0]["command_timings"] = []
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "cover each command"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).write(record)

        record = make_record()
        del record["source_scopes"]
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "source_scopes is required"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).write(record)

        record = make_record()
        record["occurrence_count"] = True
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "nonnegative integer"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).write(record)

    def test_existing_record_version_and_fingerprint_are_revalidated(self) -> None:
        writer = audit_trace.AuditTraceWriter(self.root, SESSION_ID)
        path = writer.write(make_record())
        record = self.read_records(path)[0]
        record["version"] = 2
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "unsupported version"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).prepare()

        record["version"] = 1
        record["lookup_id"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(audit_trace.AuditTraceError, "canonical fingerprint"):
            audit_trace.AuditTraceWriter(self.root, SESSION_ID).prepare()

    def test_existing_record_aggregate_and_outcome_invariants_are_revalidated(self) -> None:
        mutations = (
            (
                lambda record: record.__setitem__("duration_ms", record["duration_ms"] + 1),
                "sum of attempt durations",
            ),
            (
                lambda record: record.__setitem__("started_at", "2026-08-06T08:00:00.000-07:00"),
                "first attempt start",
            ),
            (
                lambda record: record.__setitem__("finished_at", "2026-08-06T10:00:00.000-07:00"),
                "latest attempt finish",
            ),
            (
                lambda record: record.__setitem__("operations", []),
                "latest attempt",
            ),
            (
                lambda record: record.pop("fallback"),
                "fallback must be a mapping",
            ),
            (
                lambda record: record.__setitem__("status", "different"),
                "latest attempt status",
            ),
            (
                lambda record: record.__setitem__("matched_paths", "not-a-list"),
                "matched_paths must be a sequence",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                case_root = self.root / re.sub(r"[^a-z]+", "-", message).strip("-")
                writer = audit_trace.AuditTraceWriter(case_root, SESSION_ID)
                path = writer.write(make_record())
                record = self.read_records(path)[0]
                mutate(record)
                path.write_text(json.dumps(record) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(audit_trace.AuditTraceError, message):
                    audit_trace.AuditTraceWriter(case_root, SESSION_ID).prepare()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "agtask" / "scripts" / "agtask"


class ListFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.database = self.root / "ledger.db"
        self.environment = os.environ.copy()
        self.environment.update(
            {"AGTASK_DB": str(self.database), "HOME": str(self.home), "TZ": "UTC"}
        )
        self.environment.pop("AGTASK_BACKEND_MODE", None)
        self.run_cli("init")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(CLI), *arguments],
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode:
            self.fail(f"command failed: {arguments!r}\n{result.stderr}")
        return result

    def register(
        self,
        label: str,
        *,
        created: str,
        updated: str,
        status: str = "active",
    ) -> str:
        identifier = str(uuid.uuid4())
        self.run_cli(
            "register",
            "--id",
            identifier,
            "--session-id",
            label,
            "--kind",
            "main",
            "--project",
            "agtask",
            "--title",
            f"agtask/{label}",
            "--initial-prompt",
            "Test list filters.",
            "--description",
            "Test list filters.",
            "--status",
            "active",
        )
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE thread SET created=?, updated=?, status=? WHERE id=?",
                (created, updated, status, identifier),
            )
        return identifier

    def listed(self, *arguments: str) -> list[str]:
        rows = json.loads(self.run_cli("list", *arguments, "--json").stdout)
        return [row["id"] for row in rows]

    def test_created_today_selects_creation_day(self) -> None:
        today = dt.datetime.now(dt.timezone.utc).date()
        yesterday = today - dt.timedelta(days=1)
        included = self.register(
            "created-today",
            created=f"{today}T12:00:00.000Z",
            updated=f"{today}T13:00:00.000Z",
        )
        self.register(
            "created-yesterday",
            created=f"{yesterday}T12:00:00.000Z",
            updated=f"{today}T14:00:00.000Z",
        )

        self.assertEqual(self.listed("--filter", "created=today"), [included])

    def test_updated_today_includes_tasks_created_earlier(self) -> None:
        today = dt.datetime.now(dt.timezone.utc).date()
        yesterday = today - dt.timedelta(days=1)
        included = self.register(
            "updated-today",
            created=f"{yesterday}T12:00:00.000Z",
            updated=f"{today}T09:00:00.000Z",
        )
        self.register(
            "updated-yesterday",
            created=f"{yesterday}T11:00:00.000Z",
            updated=f"{yesterday}T13:00:00.000Z",
        )

        self.assertEqual(self.listed("--filter", "updated=today"), [included])

    def test_explicit_date_uses_local_day_and_excludes_upper_bound(self) -> None:
        self.environment["TZ"] = "America/Los_Angeles"
        self.register(
            "before-local-day",
            created="2026-08-12T06:59:59.999Z",
            updated="2026-08-12T06:59:59.999Z",
        )
        included = self.register(
            "inside-local-day",
            created="2026-08-12T07:00:00.000Z",
            updated="2026-08-12T07:00:00.000Z",
        )
        self.register(
            "after-local-day",
            created="2026-08-13T07:00:00.000Z",
            updated="2026-08-13T07:00:00.000Z",
        )

        self.assertEqual(self.listed("--filter", "created=2026-08-12"), [included])

    def test_repeated_filters_combine_with_status(self) -> None:
        included = self.register(
            "both",
            created="2026-08-11T12:00:00.000Z",
            updated="2026-08-12T12:00:00.000Z",
        )
        self.register(
            "wrong-created",
            created="2026-08-12T12:00:00.000Z",
            updated="2026-08-12T12:00:00.000Z",
        )
        self.register(
            "wrong-status",
            created="2026-08-11T12:00:00.000Z",
            updated="2026-08-12T13:00:00.000Z",
            status="blocked",
        )

        self.assertEqual(
            self.listed(
                "--status",
                "active",
                "--filter",
                "created=2026-08-11",
                "--filter",
                "updated=2026-08-12",
            ),
            [included],
        )

    def test_filter_is_applied_before_limit(self) -> None:
        included = self.register(
            "matching",
            created="2026-08-11T12:00:00.000Z",
            updated="2026-08-11T12:00:00.000Z",
        )
        self.register(
            "newer-nonmatching",
            created="2026-08-12T12:00:00.000Z",
            updated="2026-08-12T12:00:00.000Z",
        )

        self.assertEqual(
            self.listed("--filter", "created=2026-08-11", "--limit", "1"),
            [included],
        )

    def test_yesterday_is_supported(self) -> None:
        yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
        included = self.register(
            "yesterday",
            created=f"{yesterday}T12:00:00.000Z",
            updated=f"{yesterday}T12:00:00.000Z",
        )

        self.assertEqual(self.listed("--filter", "updated=yesterday"), [included])

    def test_invalid_filters_fail_before_query(self) -> None:
        for expression in (
            "closed=today",
            "created",
            "updated=tomorrow",
            "created=2026-02-30",
            "created=20260812",
        ):
            with self.subTest(expression=expression):
                result = self.run_cli("list", "--filter", expression, check=False)
                self.assertEqual(result.returncode, 2)
                self.assertIn("filter", result.stderr)


if __name__ == "__main__":
    unittest.main()

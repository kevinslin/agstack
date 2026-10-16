from __future__ import annotations

import concurrent.futures
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


def fixture_creation_id(label: str) -> str:
    try:
        parsed = uuid.UUID(label)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.version == 4 and str(parsed) == label:
        return label
    seed = uuid.uuid5(uuid.NAMESPACE_URL, f"agtask-test:{label}")
    return str(uuid.UUID(bytes=seed.bytes, version=4))


class CloseContractTest(unittest.TestCase):
    def run_cli(
        self,
        database: Path,
        home: Path,
        project: Path,
        *arguments: str,
    ) -> dict[str, object]:
        normalized_arguments = list(arguments)
        if "--id" in normalized_arguments:
            id_index = normalized_arguments.index("--id") + 1
            normalized_arguments[id_index] = fixture_creation_id(
                normalized_arguments[id_index]
            )
        environment = os.environ.copy()
        environment["AGTASK_DB"] = str(database)
        environment["HOME"] = str(home)
        result = subprocess.run(
            ["python3", str(CLI), *normalized_arguments, "--json"],
            cwd=project,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    def test_prepare_and_close_surface_prompts_at_their_lifecycle_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()
            database = root / "store" / "ledger.db"
            config = home / ".agtask.json"
            config.write_text(
                json.dumps(
                    {
                        "defaults": {},
                        "hooks": {
                            "OnPreClose": {"prompt": "Run close preparation."},
                            "OnPostClose": {"prompt": "Run close follow-up."},
                        },
                    }
                )
            )
            self.run_cli(database, home, project, "init")
            self.run_cli(
                database,
                home,
                project,
                "register",
                "--id",
                "thread-close",
                "--session-id",
                "thread-close",
                "--parent-session-id",
                "fixture-parent",
                "--kind",
                "child",
                "--project",
                "agtask",
                "--title",
                "close contract",
                "--initial-prompt",
                "Task:\nfixture",
                "--description",
                "fixture",
                "--status",
                "active",
            )

            prepared = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "thread-close",
                "--prepare",
            )
            self.assertEqual(prepared["status"], "merging")
            self.assertIsNone(prepared["closed"])
            self.assertEqual(prepared["merge_claim"]["state"], "claimed")
            token = prepared["merge_claim"]["token"]
            self.assertEqual(
                prepared["hook_prompts"],
                [
                    {
                        "event": "OnPreClose",
                        "prompt": "Run close preparation.",
                        "source": str(config.resolve()),
                    }
                ],
            )

            first = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "thread-close",
                "--merge-token",
                token,
            )
            self.assertEqual(first["status"], "done")
            self.assertEqual(
                first["hook_prompts"],
                [
                    {
                        "event": "OnPostClose",
                        "prompt": "Run close follow-up.",
                        "source": str(config.resolve()),
                    }
                ],
            )
            second = self.run_cli(
                database, home, project, "close", "--id", "thread-close"
            )
            self.assertEqual(second["hook_prompts"], [])

            config.write_text(
                json.dumps(
                    {
                        "defaults": {},
                        "hooks": {
                            "OnPreClose": {"prompt": ""},
                            "OnPostClose": {"prompt": ""},
                        },
                    }
                )
            )
            self.run_cli(
                database,
                home,
                project,
                "register",
                "--id",
                "disabled-pre-close",
                "--session-id",
                "disabled-pre-close",
                "--parent-session-id",
                "fixture-parent",
                "--kind",
                "child",
                "--project",
                "disabled",
                "--title",
                "disabled close hook",
                "--initial-prompt",
                "Task:\ndisabled",
                "--status",
                "active",
            )
            disabled = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "disabled-pre-close",
                "--prepare",
            )
            self.assertEqual(disabled["merge_claim"]["state"], "claimed")
            self.assertEqual(disabled["hook_prompts"], [])
            self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "disabled-pre-close",
                "--merge-token",
                disabled["merge_claim"]["token"],
            )

            with sqlite3.connect(database) as connection:
                status, closed = connection.execute(
                    "SELECT status,closed FROM thread WHERE id=?",
                    (fixture_creation_id("thread-close"),),
                ).fetchone()
                rollouts = connection.execute(
                    "SELECT role,message,created FROM rollout "
                    "WHERE thread_id=? ORDER BY id",
                    (fixture_creation_id("thread-close"),),
                ).fetchall()
            self.assertEqual(status, "done")
            self.assertIsNotNone(closed)
            self.assertEqual(
                [(role, message) for role, message, _created in rollouts],
                [
                    ("meta", "thread.created"),
                    ("meta", "status:active->merging"),
                    ("meta", "status:merging->done"),
                    ("meta", "finalization:completed"),
                ],
            )
            self.assertEqual([created for _role, _message, created in rollouts[2:]], [closed, closed])
            self.assertNotIn("Run close follow-up.", [message for _role, message, _created in rollouts])
            self.assertNotIn("Run close preparation.", [message for _role, message, _created in rollouts])

    def test_if_tracked_returns_untracked_without_creating_a_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()
            database = root / "missing" / "ledger.db"
            result = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "missing",
                "--if-tracked",
                "--prepare",
            )
            self.assertEqual(
                result,
                {
                    "hook_prompts": [],
                    "id": fixture_creation_id("missing"),
                    "status": "untracked",
                },
            )
            self.assertFalse(database.exists())

    def test_project_claims_are_atomic_leased_fenced_and_project_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            home = root / "home"
            project = root / "project"
            home.mkdir()
            project.mkdir()
            database = root / "store" / "ledger.db"
            self.run_cli(database, home, project, "init")

            def register(thread_id: str, project_name: str) -> None:
                self.run_cli(
                    database,
                    home,
                    project,
                    "register",
                    "--id",
                    thread_id,
                    "--session-id",
                    thread_id,
                    "--parent-session-id",
                    "fixture-parent",
                    "--kind",
                    "child",
                    "--project",
                    project_name,
                    "--title",
                    thread_id,
                    "--initial-prompt",
                    f"Task:\n{thread_id}",
                    "--status",
                    "active",
                )

            register("owner", "alpha")
            register("waiter", "alpha")
            register("parallel", "beta")
            register("concurrent-a", "gamma")
            register("concurrent-b", "gamma")
            register("cancel-blocked", "delta")
            register("cancel-expired", "epsilon")

            def prepare(thread_id: str) -> dict[str, object]:
                return self.run_cli(
                    database, home, project, "close", "--id", thread_id, "--prepare"
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                concurrent_results = list(
                    executor.map(prepare, ["concurrent-a", "concurrent-b"])
                )
            self.assertEqual(
                sorted(result["merge_claim"]["state"] for result in concurrent_results),
                ["claimed", "waiting"],
            )
            concurrent_owner = next(
                result
                for result in concurrent_results
                if result["merge_claim"]["state"] == "claimed"
            )
            self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                concurrent_owner["id"],
                "--cancel",
                "--merge-token",
                concurrent_owner["merge_claim"]["token"],
            )

            owner = self.run_cli(
                database, home, project, "close", "--id", "owner", "--prepare"
            )
            owner_token = owner["merge_claim"]["token"]
            repeated = self.run_cli(
                database, home, project, "close", "--id", "owner", "--prepare"
            )
            self.assertEqual(repeated["merge_claim"]["token"], owner_token)
            self.assertEqual(
                [row["message"] for row in repeated["rollouts"]].count(
                    "status:active->merging"
                ),
                1,
            )
            heartbeat = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "owner",
                "--heartbeat",
                "--merge-token",
                owner_token,
            )
            self.assertEqual(heartbeat["merge_claim"]["token"], owner_token)
            self.assertEqual(heartbeat["hook_prompts"], [])

            cancel_blocked = prepare("cancel-blocked")
            self.run_cli(
                database,
                home,
                project,
                "record-turn",
                "--id",
                "cancel-blocked",
                "--role",
                "assistant",
                "--turn-id",
                "blocked-pre-close",
                "--content",
                "Blocked: finalization needs user input.",
            )
            released_blocked = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "cancel-blocked",
                "--cancel",
                "--merge-token",
                cancel_blocked["merge_claim"]["token"],
            )
            self.assertEqual(released_blocked["status"], "blocked")

            cancel_expired = prepare("cancel-expired")
            expired_token = cancel_expired["merge_claim"]["token"]
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE project_merge_claim SET lease_expires=? "
                    "WHERE project='epsilon'",
                    ("2000-01-01T00:00:00.000Z",),
                )
                connection.commit()
            expired_heartbeat = subprocess.run(
                [
                    "python3",
                    str(CLI),
                    "close",
                    "--id",
                    fixture_creation_id("cancel-expired"),
                    "--heartbeat",
                    "--merge-token",
                    expired_token,
                    "--json",
                ],
                cwd=project,
                env=os.environ | {"AGTASK_DB": str(database), "HOME": str(home)},
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(expired_heartbeat.returncode, 0)
            self.assertIn("lease expired", expired_heartbeat.stderr)
            released_expired = self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "cancel-expired",
                "--cancel",
                "--merge-token",
                expired_token,
            )
            self.assertEqual(released_expired["status"], "active")

            unfenced_close = subprocess.run(
                [
                    "python3",
                    str(CLI),
                    "close",
                    "--id",
                    fixture_creation_id("owner"),
                    "--json",
                ],
                cwd=project,
                env=os.environ
                | {"AGTASK_DB": str(database), "HOME": str(home)},
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(unfenced_close.returncode, 0)
            self.assertIn("requires --merge-token", unfenced_close.stderr)
            self.run_cli(
                database,
                home,
                project,
                "record-turn",
                "--id",
                "owner",
                "--role",
                "user",
                "--turn-id",
                "pre-close-turn",
                "--content",
                "Task:\nowner",
            )
            after_pre_close = self.run_cli(
                database,
                home,
                project,
                "record-turn",
                "--id",
                "owner",
                "--role",
                "assistant",
                "--turn-id",
                "pre-close-turn",
                "--content",
                "Blocked: finalization failed.",
            )
            self.assertEqual(after_pre_close["status"], "merging")

            waiting = self.run_cli(
                database, home, project, "close", "--id", "waiter", "--prepare"
            )
            self.assertEqual(waiting["status"], "active")
            self.assertEqual(waiting["hook_prompts"], [])
            self.assertEqual(waiting["merge_claim"]["state"], "waiting")
            self.assertEqual(
                waiting["merge_claim"]["owner_thread_id"],
                fixture_creation_id("owner"),
            )
            self.assertGreaterEqual(waiting["merge_claim"]["retry_after_ms"], 750)
            self.assertLessEqual(waiting["merge_claim"]["retry_after_ms"], 1500)

            parallel = self.run_cli(
                database, home, project, "close", "--id", "parallel", "--prepare"
            )
            self.assertEqual(parallel["merge_claim"]["state"], "claimed")
            self.run_cli(
                database,
                home,
                project,
                "close",
                "--id",
                "parallel",
                "--cancel",
                "--merge-token",
                parallel["merge_claim"]["token"],
            )

            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE project_merge_claim SET lease_expires=? WHERE project='alpha'",
                    ("2000-01-01T00:00:00.000Z",),
                )
                connection.commit()
            takeover = self.run_cli(
                database, home, project, "close", "--id", "waiter", "--prepare"
            )
            self.assertEqual(takeover["merge_claim"]["state"], "claimed")
            self.assertEqual(takeover["status"], "merging")
            with sqlite3.connect(database) as connection:
                statuses = dict(connection.execute("SELECT id,status FROM thread"))
            self.assertEqual(statuses[fixture_creation_id("owner")], "blocked")
            self.assertEqual(statuses[fixture_creation_id("waiter")], "merging")

            stale = subprocess.run(
                [
                    "python3",
                    str(CLI),
                    "close",
                    "--id",
                    fixture_creation_id("owner"),
                    "--heartbeat",
                    "--merge-token",
                    owner_token,
                    "--json",
                ],
                cwd=project,
                env=os.environ
                | {"AGTASK_DB": str(database), "HOME": str(home)},
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("does not own the merge claim", stale.stderr)


if __name__ == "__main__":
    unittest.main()

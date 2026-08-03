from __future__ import annotations

import datetime as dt
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from urllib.parse import quote, urljoin, urlsplit


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


class DashboardIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db_path = self.root / "store" / "ledger.db"
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env["AGTASK_DB"] = str(self.db_path)
        self.env["HOME"] = str(self.home)
        self.run_cli("init", "--json")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        normalized_arguments = list(arguments)
        if "--id" in normalized_arguments:
            id_index = normalized_arguments.index("--id") + 1
            normalized_arguments[id_index] = fixture_creation_id(
                normalized_arguments[id_index]
            )
        result = subprocess.run(
            ["python3", str(CLI), *normalized_arguments],
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"command failed ({result.returncode}): {arguments}\n"
                f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
            )
        return result

    def register(
        self,
        thread_id: str,
        *,
        project: str,
        title: str,
        parent_session_id: str | None,
        status: str = "active",
    ) -> None:
        arguments = [
            "register",
            "--id",
            thread_id,
            "--session-id",
            thread_id,
            "--kind",
            "main" if parent_session_id is None else "child",
            "--project",
            project,
            "--title",
            title,
            "--initial-prompt",
            "Task:\ndashboard fixture",
            "--description",
            "dashboard fixture",
            "--status",
            status,
            "--json",
        ]
        if parent_session_id is not None:
            arguments[3:3] = ["--parent-session-id", parent_session_id]
        self.run_cli(*arguments)

    def close_thread(self, thread_id: str) -> None:
        prepared = json.loads(
            self.run_cli(
                "close", "--id", thread_id, "--prepare", "--json"
            ).stdout
        )
        self.run_cli(
            "close",
            "--id",
            thread_id,
            "--merge-token",
            prepared["merge_claim"]["token"],
        )

    def seed_dashboard(self) -> None:
        self.register(
            "root-todo",
            project="alpha",
            title="Ship API",
            parent_session_id=None,
            status="todo",
        )
        self.register(
            "alpha-active",
            project="alpha",
            title="Polish Dashboard",
            parent_session_id="root-todo",
        )
        self.register(
            "beta-blocked",
            project="beta",
            title="Investigate dashboard latency",
            parent_session_id="parent-beta",
        )
        self.register(
            "beta-done",
            project="beta",
            title="Publish notes",
            parent_session_id="parent-beta",
        )
        self.run_cli("status", "--id", "beta-blocked", "--status", "blocked")
        self.close_thread("beta-done")
        attachment = self.root / "dashboard task.md"
        attachment.write_text("Dashboard task file.\n")
        self.run_cli("attach", str(attachment), "--id", "alpha-active")
        connection = sqlite3.connect(self.db_path)
        try:
            timestamps = {
                "root-todo": ("2026-01-01T00:00:00.000Z", "2026-01-01T01:00:00.000Z", None),
                "alpha-active": ("2026-01-02T00:00:00.000Z", "2026-01-04T00:00:00.000Z", None),
                "beta-blocked": ("2026-01-03T00:00:00.000Z", "2026-01-05T00:00:00.000Z", None),
                "beta-done": (
                    "2026-01-04T00:00:00.000Z",
                    "2026-01-06T00:00:00.000Z",
                    "2026-01-06T00:00:00.000Z",
                ),
            }
            connection.executemany(
                "UPDATE thread SET created=?,updated=?,closed=? WHERE id=?",
                [
                    (*values, fixture_creation_id(thread_id))
                    for thread_id, values in timestamps.items()
                ],
            )
            connection.commit()
        finally:
            connection.close()

    def start_server(self, *arguments: str) -> tuple[subprocess.Popen[str], str]:
        process = subprocess.Popen(
            ["python3", str(CLI), "dashboard", "--no-open", *arguments],
            cwd=ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        url = process.stdout.readline().strip()
        if not url:
            stderr = process.stderr.read() if process.stderr is not None else ""
            process.kill()
            self.fail(f"dashboard did not publish a URL: {stderr}")
        self.addCleanup(self.stop_server, process)
        return process, url

    @staticmethod
    def stop_server(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    def request(
        self,
        url: str,
        *,
        path: str | None = None,
        method: str = "GET",
        host: str | None = None,
        body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        parsed = urlsplit(url)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        request_path = path if path is not None else parsed.path
        request_headers = dict(headers or {})
        if host is not None:
            request_headers["Host"] = host
        connection.request(method, request_path, body=body, headers=request_headers)
        response = connection.getresponse()
        body = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, response_headers, body

    def test_json_snapshot_groups_filters_sorts_and_exposes_global_facets(self) -> None:
        self.seed_dashboard()
        result = self.run_cli(
            "dashboard",
            "--json",
            "--project",
            "alpha",
            "--status",
            "active",
            "--search",
            "DASHBOARD",
            "--sort",
            "created",
            "--direction",
            "asc",
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["total_count"], 4)
        self.assertEqual(payload["visible_count"], 1)
        self.assertEqual(payload["filters"]["projects"], ["alpha"])
        self.assertEqual(payload["filters"]["statuses"], ["active"])
        self.assertEqual(payload["search"], "DASHBOARD")
        self.assertEqual(payload["sort"], {"field": "created", "direction": "asc"})
        self.assertEqual([group["status"] for group in payload["groups"]], ["active"])
        self.assertEqual(
            payload["groups"][0]["threads"][0]["id"],
            fixture_creation_id("alpha-active"),
        )
        self.assertEqual(
            set(payload["groups"][0]["threads"][0]),
            {
                "id",
                "session_id",
                "parent_session_id",
                "project",
                "title",
                "created",
                "updated",
                "closed",
                "status",
                "files",
            },
        )
        self.assertEqual(
            payload["facets"]["projects"],
            [{"value": "alpha", "count": 2}, {"value": "beta", "count": 2}],
        )
        self.assertIn({"value": None, "count": 1}, payload["facets"]["parents"])
        self.assertEqual(
            [item["value"] for item in payload["facets"]["statuses"]],
            ["todo", "active", "blocked", "merging", "done", "drop"],
        )

    def test_json_sort_keeps_null_closed_values_last_and_uses_stable_ties(self) -> None:
        self.seed_dashboard()
        self.register(
            "active-a",
            project="alpha",
            title="Active tie A",
            parent_session_id="root-todo",
        )
        self.register(
            "active-b",
            project="alpha",
            title="Active tie B",
            parent_session_id="root-todo",
        )
        self.register(
            "done-early",
            project="beta",
            title="Done early",
            parent_session_id="parent-beta",
        )
        self.close_thread("done-early")
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "UPDATE thread SET created=?,updated=? WHERE id IN (?,?)",
                (
                    "2026-01-03T00:00:00.000Z",
                    "2026-01-04T00:00:00.000Z",
                    fixture_creation_id("active-a"),
                    fixture_creation_id("active-b"),
                ),
            )
            connection.execute(
                "UPDATE thread SET created=?,updated=?,closed=? WHERE id=?",
                (
                    "2026-01-03T00:00:00.000Z",
                    "2026-01-05T00:00:00.000Z",
                    "2026-01-05T00:00:00.000Z",
                    fixture_creation_id("done-early"),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        payload = json.loads(
            self.run_cli(
                "dashboard", "--json", "--sort", "closed", "--direction", "asc"
            ).stdout
        )
        groups = {group["status"]: group["threads"] for group in payload["groups"]}
        self.assertEqual(
            [thread["id"] for thread in groups["active"]],
            [
                fixture_creation_id("active-a"),
                fixture_creation_id("active-b"),
                fixture_creation_id("alpha-active"),
            ],
        )
        self.assertEqual(
            [thread["id"] for thread in groups["done"]],
            [fixture_creation_id("done-early"), fixture_creation_id("beta-done")],
        )
        descending = json.loads(
            self.run_cli(
                "dashboard", "--json", "--sort", "closed", "--direction", "desc"
            ).stdout
        )
        done = next(group for group in descending["groups"] if group["status"] == "done")
        self.assertEqual(
            [thread["id"] for thread in done["threads"]],
            [fixture_creation_id("beta-done"), fixture_creation_id("done-early")],
        )

    def test_filters_or_within_dimensions_and_searches_titles_only_with_casefold(self) -> None:
        self.seed_dashboard()
        self.register(
            "unicode-active",
            project="gamma",
            title="Straße Dashboard",
            parent_session_id="parent-gamma",
        )
        combined = json.loads(
            self.run_cli(
                "dashboard",
                "--json",
                "--project",
                "alpha",
                "--project",
                "beta",
                "--parent-session-id",
                "parent-beta",
                "--root-parent",
                "--status",
                "todo",
                "--status",
                "blocked",
            ).stdout
        )
        self.assertEqual(combined["visible_count"], 2)
        self.assertEqual(
            {thread["id"] for group in combined["groups"] for thread in group["threads"]},
            {
                fixture_creation_id("root-todo"),
                fixture_creation_id("beta-blocked"),
            },
        )
        unicode_match = json.loads(
            self.run_cli("dashboard", "--json", "--search", "STRASSE").stdout
        )
        self.assertEqual(unicode_match["visible_count"], 1)
        description_only = json.loads(
            self.run_cli("dashboard", "--json", "--search", "fixture").stdout
        )
        self.assertEqual(description_only["visible_count"], 0)
        empty_selected_group = json.loads(
            self.run_cli(
                "dashboard", "--json", "--project", "missing", "--status", "done"
            ).stdout
        )
        self.assertEqual(empty_selected_group["filters"]["projects"], ["missing"])
        self.assertEqual(empty_selected_group["groups"], [{"status": "done", "count": 0, "threads": []}])

    def test_today_saved_view_uses_local_calendar_day_and_excludes_terminal_tasks(self) -> None:
        self.seed_dashboard()
        local_today = dt.datetime.now().astimezone().date()

        def utc_stamp(day: dt.date, hour: int = 12) -> str:
            return (
                dt.datetime.combine(day, dt.time(hour=hour))
                .astimezone()
                .astimezone(dt.timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z")
            )

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE thread SET created=? WHERE id=?",
                (utc_stamp(local_today), fixture_creation_id("alpha-active")),
            )
            connection.execute(
                "UPDATE thread SET created=? WHERE id=?",
                (utc_stamp(local_today), fixture_creation_id("beta-done")),
            )
            connection.execute(
                "UPDATE thread SET created=? WHERE id=?",
                (
                    utc_stamp(local_today - dt.timedelta(days=1)),
                    fixture_creation_id("beta-blocked"),
                ),
            )
            connection.commit()

        _process, url = self.start_server()
        parsed = urlsplit(url)
        status, _headers, body = self.request(
            url, path=parsed.path + "api/dashboard?view=today"
        )
        self.assertEqual(status, 200, body.decode("utf-8", errors="replace"))
        payload = json.loads(body)
        self.assertEqual(payload["selected_view"], "today")
        self.assertEqual(
            payload["views"],
            [
                {
                    "id": "today",
                    "name": "Today",
                    "filters": {
                        "created": "today",
                        "exclude_statuses": ["done", "drop"],
                    },
                    "created": payload["views"][0]["created"],
                    "updated": payload["views"][0]["updated"],
                }
            ],
        )
        self.assertEqual(
            [
                thread["session_id"]
                for group in payload["groups"]
                for thread in group["threads"]
            ],
            ["alpha-active"],
        )
        self.assertEqual(
            [group["status"] for group in payload["groups"]],
            ["todo", "active", "blocked", "merging"],
        )

    def test_dashboard_rejects_conflicting_output_modes(self) -> None:
        result = self.run_cli("dashboard", "--json", "--no-open", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be used together", result.stderr)

    def test_server_serves_tokenized_assets_and_dashboard_api(self) -> None:
        self.seed_dashboard()
        _process, url = self.start_server("--project", "beta")
        parsed = urlsplit(url)
        token_root = parsed.path

        status, headers, body = self.request(url)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["referrer-policy"], "no-referrer")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertIn(b"agtask dashboard", body)
        self.assertIn(b'id="filter-trigger"', body)
        self.assertIn(b'id="filter-menu"', body)
        self.assertIn(b'id="active-filters"', body)
        self.assertIn(b'id="add-filter"', body)
        self.assertIn(b'id="status-modal"', body)
        self.assertIn(b'id="status-options"', body)
        self.assertIn(b'aria-controls="filter-menu"', body)
        self.assertNotIn(b"Publish notes", body)

        status, headers, body = self.request(url, path=token_root + "app.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertIn(b"textContent", body)
        self.assertNotIn(b"innerHTML", body)
        self.assertIn(b"data-task-id", body)
        self.assertIn(b"location.assign", body)
        self.assertIn(b"tasks/~${encodeURIComponent(sessionId)}", body)
        self.assertIn(b"codex://threads/${encodeURIComponent(sessionId)}", body)
        self.assertIn(b"FILTER_DEFS", body)
        self.assertIn(b"menuKeydown", body)
        self.assertIn(b"STATUS_OPTIONS", body)
        self.assertIn(b"/status", body)
        self.assertNotIn(b"Publish notes", body)

        status, headers, body = self.request(
            url, path=token_root + "api/dashboard?project=beta&sort=updated&direction=desc"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        payload = json.loads(body)
        self.assertEqual(payload["visible_count"], 2)

        status, _headers, _body = self.request(url, path="/")
        self.assertEqual(status, 404)
        status, _headers, _body = self.request(url, method="POST")
        self.assertEqual(status, 405)
        status, _headers, _body = self.request(url, method="TRACE")
        self.assertEqual(status, 405)
        status, _headers, _body = self.request(url, method="POST", host="localhost")
        self.assertEqual(status, 404)

        status, head_headers, head_body = self.request(url, method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(head_body, b"")
        self.assertGreater(int(head_headers["content-length"]), 0)

    def test_task_detail_page_and_api_include_description_properties_and_newest_rollouts(self) -> None:
        self.seed_dashboard()
        self.register(".", project="dots", title="Dot task", parent_session_id="root-todo")
        self.register("..", project="dots", title="Dot dot task", parent_session_id="root-todo")
        self.run_cli(
            "append-rollout",
            "--id",
            "alpha-active",
            "--turn-id",
            "user-detail",
            "--role",
            "user",
            "--message",
            "First timeline entry",
        )
        self.run_cli(
            "append-rollout",
            "--id",
            "alpha-active",
            "--turn-id",
            "assistant-detail",
            "--role",
            "assistant",
            "--message",
            "Newest timeline entry",
        )
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "UPDATE rollout SET created=? WHERE thread_id=? AND turn_id=?",
                (
                    "2099-01-07T00:00:00.000Z",
                    fixture_creation_id("alpha-active"),
                    "user-detail",
                ),
            )
            connection.execute(
                "UPDATE rollout SET created=? WHERE thread_id=? AND turn_id=?",
                (
                    "2099-01-08T00:00:00.000Z",
                    fixture_creation_id("alpha-active"),
                    "assistant-detail",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        _process, url = self.start_server()
        parsed = urlsplit(url)
        task_path = parsed.path + "tasks/~" + quote("alpha-active", safe="")

        status, headers, body = self.request(url, path=task_path)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertIn(b'id="task-title"', body)
        self.assertIn(b'id="task-description"', body)
        self.assertIn(b'id="timeline"', body)
        self.assertIn(b'id="task-session-id"', body)
        self.assertIn(b'id="task-session-id" class="session-link"', body)
        self.assertIn(b'id="task-files"', body)
        self.assertNotIn(b"Polish Dashboard", body)
        status, _headers, _body = self.request(
            url, path=task_path + "?view=today"
        )
        self.assertEqual(status, 200)
        detail_url = f"http://{parsed.netloc}{task_path}"
        self.assertEqual(urlsplit(urljoin(detail_url, "../app.css")).path, parsed.path + "app.css")
        self.assertEqual(urlsplit(urljoin(detail_url, "../task.js")).path, parsed.path + "task.js")
        self.assertEqual(
            urlsplit(urljoin(detail_url, "../api/tasks/~alpha-active")).path,
            parsed.path + "api/tasks/~alpha-active",
        )

        status, headers, body = self.request(url, path=parsed.path + "task.js")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/javascript; charset=utf-8")
        self.assertIn(b"textContent", body)
        self.assertIn(b"codex://threads/", body)
        self.assertIn(b"file-badge", body)
        self.assertIn(b"encodeURIComponent(task.session_id)", body)
        self.assertNotIn(b"innerHTML", body)
        task_script = body

        status, headers, body = self.request(
            url,
            path=parsed.path + "api/tasks/~" + quote("alpha-active", safe=""),
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        detail = json.loads(body)
        self.assertEqual(
            set(detail),
            {
                "id",
                "session_id",
                "parent_session_id",
                "title",
                "description",
                "created",
                "updated",
                "rollouts",
                "files",
            },
        )
        self.assertEqual(detail["id"], fixture_creation_id("alpha-active"))
        self.assertEqual(detail["title"], "Polish Dashboard")
        self.assertEqual(detail["description"], "dashboard fixture")
        self.assertEqual(len(detail["files"]), 1)
        self.assertEqual(detail["files"][0]["name"], "dashboard task.md")
        self.assertTrue(detail["files"][0]["url"].startswith("vscode://file/"))
        self.assertEqual(
            [rollout["message"] for rollout in detail["rollouts"][:2]],
            ["Newest timeline entry", "First timeline entry"],
        )
        self.assertEqual(
            set(detail["rollouts"][0]), {"created", "role", "message"}
        )

        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the detail client harness")
        assert node is not None
        result = subprocess.run(
            [node, str(ROOT / "tests" / "task_detail_client.test.js")],
            cwd=ROOT,
            input=json.dumps(
                {"source": task_script.decode("utf-8"), "detail": detail}
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"detail client harness failed\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("task detail client passed", result.stdout)

        status, _headers, body = self.request(
            url, path=parsed.path + "api/tasks/~."
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], fixture_creation_id("."))
        status, _headers, body = self.request(
            url, path=parsed.path + "api/tasks/~.."
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], fixture_creation_id(".."))

        status, _headers, body = self.request(
            url, path=parsed.path + "api/tasks/~not-tracked"
        )
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "task not found"})

    def test_served_client_filter_interactions_and_query_synchronization(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(
            node, "Node.js is required for the dashboard client interaction harness"
        )
        assert node is not None
        self.seed_dashboard()
        _process, url = self.start_server()
        parsed = urlsplit(url)
        status, _headers, script = self.request(url, path=parsed.path + "app.js")
        self.assertEqual(status, 200)
        status, _headers, snapshot = self.request(
            url, path=parsed.path + "api/dashboard"
        )
        self.assertEqual(status, 200)

        result = subprocess.run(
            [node, str(ROOT / "tests" / "dashboard_client.test.js")],
            cwd=ROOT,
            input=json.dumps(
                {
                    "source": script.decode("utf-8"),
                    "snapshot": json.loads(snapshot),
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"client interaction harness failed\nstdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("dashboard client interactions passed", result.stdout)

    def test_bulk_status_api_is_atomic_and_expected_status_guarded(self) -> None:
        self.seed_dashboard()
        _process, url = self.start_server()
        parsed = urlsplit(url)
        status_path = parsed.path + "api/tasks/status"
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://{parsed.netloc}",
        }

        status, _response_headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body=json.dumps(
                {
                    "tasks": [
                        {"session_id": "root-todo", "expected_status": "todo"},
                        {
                            "session_id": "alpha-active",
                            "expected_status": "blocked",
                        },
                    ],
                    "status": "done",
                }
            ),
            headers=headers,
        )
        self.assertEqual(status, 409)
        self.assertEqual(
            json.loads(body),
            {
                "error": (
                    "task status changed from blocked to active; "
                    "refresh and try again"
                )
            },
        )
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT session_id,status,closed FROM thread "
                    "WHERE session_id IN ('root-todo','alpha-active') "
                    "ORDER BY session_id"
                ).fetchall(),
                [("alpha-active", "active", None), ("root-todo", "todo", None)],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM rollout WHERE thread_id IN (?,?) "
                    "AND message LIKE 'status:%'",
                    (
                        fixture_creation_id("root-todo"),
                        fixture_creation_id("alpha-active"),
                    ),
                ).fetchone()[0],
                0,
            )

        status, response_headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body=json.dumps(
                {
                    "tasks": [
                        {"session_id": "root-todo", "expected_status": "todo"},
                        {
                            "session_id": "alpha-active",
                            "expected_status": "active",
                        },
                    ],
                    "status": "done",
                }
            ),
            headers=headers,
        )
        self.assertEqual(status, 200, body.decode("utf-8", errors="replace"))
        self.assertEqual(
            response_headers["content-type"], "application/json; charset=utf-8"
        )
        result = json.loads(body)
        self.assertEqual(set(result), {"changed", "tasks"})
        self.assertTrue(result["changed"])
        self.assertEqual(
            [task["session_id"] for task in result["tasks"]],
            ["root-todo", "alpha-active"],
        )
        self.assertEqual([task["status"] for task in result["tasks"]], ["done", "done"])
        self.assertTrue(
            all(task["closed"] == task["updated"] for task in result["tasks"])
        )
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT session_id,status,closed IS updated FROM thread "
                    "WHERE session_id IN ('root-todo','alpha-active') "
                    "ORDER BY session_id"
                ).fetchall(),
                [("alpha-active", "done", 1), ("root-todo", "done", 1)],
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM rollout WHERE thread_id IN (?,?) "
                    "AND message IN ('status:todo->done','status:active->done')",
                    (
                        fixture_creation_id("root-todo"),
                        fixture_creation_id("alpha-active"),
                    ),
                ).fetchone()[0],
                2,
            )

    def test_status_api_updates_ledger_without_dispatching_close_hooks(self) -> None:
        self.seed_dashboard()
        (self.home / ".agtask.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "OnPreClose": {"prompt": "dashboard must not dispatch pre-close"},
                        "OnPostClose": {"prompt": "dashboard must not dispatch post-close"},
                    }
                }
            )
        )
        _process, url = self.start_server()
        parsed = urlsplit(url)
        status_path = parsed.path + "api/tasks/~alpha-active/status"
        origin = f"http://{parsed.netloc}"

        status, headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body=json.dumps({"expected_status": "active", "status": "blocked"}),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 200, body.decode("utf-8", errors="replace"))
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        result = json.loads(body)
        self.assertTrue(result["changed"])
        self.assertEqual(result["task"]["session_id"], "alpha-active")
        self.assertEqual(result["task"]["status"], "blocked")
        self.assertIsNone(result["task"]["closed"])

        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            thread = connection.execute(
                "SELECT id,status,updated,closed FROM thread WHERE session_id=?",
                ("alpha-active",),
            ).fetchone()
            assert thread is not None
            transitions = connection.execute(
                "SELECT created,message FROM rollout "
                "WHERE thread_id=? AND message LIKE 'status:%' ORDER BY id",
                (thread["id"],),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(thread["status"], "blocked")
        self.assertIsNone(thread["closed"])
        self.assertEqual(
            [(row["created"], row["message"]) for row in transitions],
            [(thread["updated"], "status:active->blocked")],
        )

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"blocked","status":"blocked"}',
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Origin": origin,
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["changed"])

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"active","status":"todo"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 409)
        self.assertEqual(
            json.loads(body),
            {
                "error": (
                    "task status changed from active to blocked; "
                    "refresh and try again"
                )
            },
        )
        connection = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT status,updated FROM thread WHERE session_id=?",
                    ("alpha-active",),
                ).fetchone(),
                ("blocked", thread["updated"]),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM rollout "
                    "WHERE thread_id=? AND message LIKE 'status:%'",
                    (thread["id"],),
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

        status, _headers, body = self.request(
            url,
            path=parsed.path + "api/tasks/~beta-done/status",
            method="PATCH",
            body='{"expected_status":"done","status":"active"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 409)
        self.assertEqual(
            json.loads(body), {"error": "done threads must be reopened explicitly"}
        )

        prepared = json.loads(
            self.run_cli(
                "close", "--id", "root-todo", "--prepare", "--json"
            ).stdout
        )
        self.assertEqual(
            prepared["hook_prompts"],
            [
                {
                    "event": "OnPreClose",
                    "prompt": "dashboard must not dispatch pre-close",
                    "source": str((self.home / ".agtask.json").resolve()),
                }
            ],
        )
        status, _headers, body = self.request(
            url,
            path=parsed.path + "api/tasks/~root-todo/status",
            method="PATCH",
            body='{"expected_status":"merging","status":"active"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 409)
        self.assertEqual(
            json.loads(body),
            {"error": "merging threads must be closed or released explicitly"},
        )
        self.run_cli(
            "close",
            "--id",
            "root-todo",
            "--merge-token",
            prepared["merge_claim"]["token"],
            "--cancel",
        )

        status, _headers, body = self.request(
            url,
            path=parsed.path + "api/tasks/~root-todo/status",
            method="PATCH",
            body='{"expected_status":"todo","status":"done"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 200)
        completed = json.loads(body)
        self.assertEqual(set(completed), {"changed", "task"})
        self.assertTrue(completed["changed"])
        self.assertEqual(completed["task"]["status"], "done")
        self.assertEqual(completed["task"]["closed"], completed["task"]["updated"])
        self.assertNotIn("hook_prompts", completed)
        with sqlite3.connect(self.db_path) as connection:
            root_id = fixture_creation_id("root-todo")
            self.assertEqual(
                connection.execute(
                    "SELECT message FROM rollout WHERE thread_id=? "
                    "AND message LIKE 'status:%' ORDER BY id DESC LIMIT 1",
                    (root_id,),
                ).fetchone()[0],
                "status:todo->done",
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM rollout WHERE thread_id=? "
                    "AND message='finalization:completed'",
                    (root_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM project_merge_claim WHERE owner_thread_id=?",
                    (root_id,),
                ).fetchone()[0],
                0,
            )

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body=(
                '{"expected_status":"blocked","status":"active",'
                '"status":"todo"}'
            ),
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {"error": "invalid JSON body"})

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"blocked","status":"active"}',
            headers={"Content-Type": "text/plain", "Origin": origin},
        )
        self.assertEqual(status, 415)
        self.assertEqual(json.loads(body), {"error": "content type must be application/json"})

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"blocked","status":"active"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body), {"error": "invalid origin"})

        status, _headers, body = self.request(
            url,
            path=parsed.path + "api/tasks/~missing/status",
            method="PATCH",
            body='{"expected_status":"active","status":"blocked"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "task not found"})

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"blocked","status":"drop"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 200)
        dropped = json.loads(body)
        self.assertTrue(dropped["changed"])
        self.assertEqual(dropped["task"]["status"], "drop")
        self.assertEqual(dropped["task"]["updated"], dropped["task"]["closed"])
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT message FROM rollout WHERE thread_id=? ORDER BY id DESC LIMIT 1",
                    (thread["id"],),
                ).fetchone()[0],
                "status:blocked->drop",
            )

        status, _headers, body = self.request(
            url,
            path=status_path,
            method="PATCH",
            body='{"expected_status":"drop","status":"active"}',
            headers={"Content-Type": "application/json", "Origin": origin},
        )
        self.assertEqual(status, 409)
        self.assertEqual(
            json.loads(body), {"error": "dropped threads must be reopened explicitly"}
        )

    def test_server_rejects_bad_host_and_invalid_query(self) -> None:
        self.seed_dashboard()
        _process, url = self.start_server()
        parsed = urlsplit(url)

        status, _headers, _body = self.request(url, host="localhost")
        self.assertEqual(status, 404)
        status, _headers, body = self.request(
            url, path=parsed.path + "api/dashboard?sort=created&sort=updated"
        )
        self.assertEqual(status, 400)
        self.assertIn(b"duplicate query parameter", body)
        status, _headers, _body = self.request(
            url, path=parsed.path + "api/dashboard?project=%ZZ"
        )
        self.assertEqual(status, 400)
        status, _headers, body = self.request(
            url, path=parsed.path + "api/dashboard?view=missing"
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {"error": "unknown saved view: missing"})

    def test_dashboard_reads_do_not_mutate_and_return_503_after_ledger_disappears(self) -> None:
        self.seed_dashboard()
        connection = sqlite3.connect(self.db_path)
        try:
            before_threads = connection.execute("SELECT * FROM thread ORDER BY id").fetchall()
            before_rollouts = connection.execute("SELECT * FROM rollout ORDER BY id").fetchall()
            before_version = connection.execute("PRAGMA user_version").fetchone()[0]
        finally:
            connection.close()

        self.run_cli("dashboard", "--json")
        process, url = self.start_server()
        parsed = urlsplit(url)
        self.request(url, path=parsed.path + "api/dashboard")
        self.stop_server(process)

        connection = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(connection.execute("SELECT * FROM thread ORDER BY id").fetchall(), before_threads)
            self.assertEqual(connection.execute("SELECT * FROM rollout ORDER BY id").fetchall(), before_rollouts)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], before_version)
        finally:
            connection.close()

        _process, url = self.start_server()
        parsed = urlsplit(url)
        self.db_path.rename(self.db_path.with_suffix(".moved"))
        status, headers, body = self.request(url, path=parsed.path + "api/dashboard")
        self.assertEqual(status, 503, body.decode("utf-8", errors="replace"))
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body), {"error": "dashboard data unavailable"})

    def test_browser_launch_failure_warns_but_server_remains_available(self) -> None:
        self.seed_dashboard()
        environment = self.env | {"BROWSER": "/usr/bin/false", "PATH": "/nonexistent"}
        process = subprocess.Popen(
            [sys.executable, str(CLI), "dashboard"],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        url = process.stdout.readline().strip()
        self.assertTrue(url.startswith("http://127.0.0.1:"))
        status, _headers, _body = self.request(url)
        self.assertEqual(status, 200)
        process.send_signal(signal.SIGINT)
        _stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0)
        self.assertIn("browser did not open", stderr)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Run the live agtask create, directive, and finalization lifecycle."""

from __future__ import annotations

import argparse
import html
import http.client
import json
import os
from pathlib import Path
import queue
import selectors
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Callable
from urllib.parse import quote, urlsplit


TITLE = "agtask/integ-lifecycle"
MAIN_TITLE = "⭐ agtask"
MAIN_DESCRIPTION = "Dispatch the integration lifecycle child."
MAIN_INITIAL_PROMPT = f"Task:\n{MAIN_DESCRIPTION}"
DIRECTIVE = "Reply with exactly INTEG_LIFECYCLE_READY"
PRE_CLOSE_DIRECTIVE = "Reply with exactly INTEG_PRE_CLOSE_READY"
POST_CLOSE_DIRECTIVE = "Reply with exactly INTEG_POST_CLOSE_READY"
CONFIG_TITLE = "agtask/integ-configured-title"
EXPLICIT_TITLE = "agtask/integ-explicit-title"
BOOTSTRAP_PROTOCOL_TITLE = "agtask/integ-materialized-title"
BOOTSTRAP_CUSTOM_SECTION_ID = "515c42ed-d59b-4559-a33e-b1d0612af20b"
BOOTSTRAP_TRUE_TRAILER = """<agtask-bootstrap version="1">
{"pin":true,"title":"agtask/integ-materialized-title"}
</agtask-bootstrap>"""
BOOTSTRAP_FALSE_TRAILER = """<agtask-bootstrap version="1">
{"pin":false,"title":"agtask/integ-configured-title"}
</agtask-bootstrap>"""
PROJECT = "agtask"
SCENARIO_SUITE_VERSION = 20
ADD_SCENARIO_NAME = "current-task-add"
ADD_SCENARIO_VERSION = 1
MAIN_SCENARIO_NAME = "main-dispatch-lineage"
MAIN_SCENARIO_VERSION = 6
CONFIG_SCENARIO_NAME = "layered-config-prompt-hooks"
CONFIG_SCENARIO_VERSION = 5
BOOTSTRAP_SCENARIO_NAME = "bootstrap-arguments-v1"
BOOTSTRAP_SCENARIO_VERSION = 4
CREATION_BOOTSTRAP_SCENARIO_NAME = "creation-bootstrap-v2"
CREATION_BOOTSTRAP_SCENARIO_VERSION = 4
LIFECYCLE_SCENARIO_NAME = "lifecycle-create-directive-close-hooks"
LIFECYCLE_SCENARIO_VERSION = 13
DASHBOARD_SCENARIO_NAME = "dashboard-html"
DASHBOARD_SCENARIO_VERSION = 16
RENAME_SCENARIO_NAME = "current-task-rename"
RENAME_SCENARIO_VERSION = 2
AUDIT_SCENARIO_NAME = "archived-session-audit"
AUDIT_SCENARIO_VERSION = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--proof-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    return parser.parse_args()


def resolve_codex() -> Path:
    candidates = [
        os.environ.get("CODEX_BIN"),
        "/Applications/ChatGPT (Alpha).app/Contents/Resources/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
        shutil.which("codex"),
    ]
    for value in candidates:
        if value and Path(value).is_file():
            return Path(value)
    raise RuntimeError("set CODEX_BIN to a local Codex binary")


def resolve_cli() -> Path:
    value = os.environ.get("AGTASK_CLI")
    if value:
        candidate = Path(value).expanduser()
    else:
        candidate = Path.home() / ".codex/skills/agtask/scripts/agtask"
    if not candidate.is_file():
        raise RuntimeError(f"installed agtask CLI not found: {candidate}")
    return candidate


def configure_database(proof_dir: Path) -> Path:
    """Keep direct lifecycle runs isolated unless the caller opts into a ledger."""
    override = os.environ.get("AGTASK_DB")
    database = Path(override).expanduser() if override else proof_dir / "ledger.db"
    database = database.resolve()
    os.environ["AGTASK_DB"] = str(database)
    return database


def query_thread(database: Path, thread_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id,session_id,parent_session_id,kind,project,title,description,status,closed "
            "FROM thread WHERE id=?",
            (thread_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def query_rollouts(database: Path, thread_id: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id,created,thread_id,turn_id,role,message "
                "FROM rollout WHERE thread_id=? ORDER BY id",
                (thread_id,),
            )
        ]
    finally:
        connection.close()


def query_thread_by_session(database: Path, session_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id,session_id,parent_session_id,kind,project,title,description,status,closed "
            "FROM thread WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def query_merge_claim(database: Path, project: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT project,owner_thread_id,token,acquired,heartbeat,lease_expires,prior_status "
            "FROM project_merge_claim WHERE project=?",
            (project,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def run_cli(
    cli: Path,
    *arguments: str,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(cli), *arguments, "--json"],
        cwd=cwd,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def run_hook(
    cli: Path,
    payload: dict[str, Any],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> str:
    result = subprocess.run(
        [sys.executable, str(cli), "hook"],
        cwd=cwd,
        env=environment,
        input=json.dumps(payload),
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def source_revision(source: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def scenario_metadata(source: Path) -> dict[str, Any]:
    path = source / ".agents/skills/integ/references/scenarios.md"
    content = path.read_text()
    require(
        f"Suite version: {SCENARIO_SUITE_VERSION}" in content,
        "scenario manifest suite version does not match the harness",
    )
    scenarios = {
        ADD_SCENARIO_NAME: ADD_SCENARIO_VERSION,
        MAIN_SCENARIO_NAME: MAIN_SCENARIO_VERSION,
        CONFIG_SCENARIO_NAME: CONFIG_SCENARIO_VERSION,
        BOOTSTRAP_SCENARIO_NAME: BOOTSTRAP_SCENARIO_VERSION,
        CREATION_BOOTSTRAP_SCENARIO_NAME: CREATION_BOOTSTRAP_SCENARIO_VERSION,
        LIFECYCLE_SCENARIO_NAME: LIFECYCLE_SCENARIO_VERSION,
        DASHBOARD_SCENARIO_NAME: DASHBOARD_SCENARIO_VERSION,
        RENAME_SCENARIO_NAME: RENAME_SCENARIO_VERSION,
        AUDIT_SCENARIO_NAME: AUDIT_SCENARIO_VERSION,
    }
    for name, version in scenarios.items():
        section = content.split(f"## {name}", 1)
        require(len(section) == 2, f"scenario manifest is missing {name}")
        body = section[1].split("\n## ", 1)[0]
        require(
            f"Scenario version: {version}" in body,
            f"scenario manifest version does not match the harness: {name}",
        )
    return {
        "path": str(path),
        "suite_version": SCENARIO_SUITE_VERSION,
        "scenarios": scenarios,
    }


def query_known_rows(
    database: Path, main_thread_id: str, child_thread_id: str
) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return {
            "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
            "threads": [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM thread WHERE id IN (?,?) ORDER BY id",
                    (main_thread_id, child_thread_id),
                )
            ],
            "rollouts": [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM rollout WHERE thread_id IN (?,?) ORDER BY id",
                    (main_thread_id, child_thread_id),
                )
            ],
        }
    finally:
        connection.close()


def dashboard_http_get(parsed_url: Any, path: str) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        parsed_url.hostname, parsed_url.port, timeout=5
    )
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, headers, body


def dashboard_http_patch(
    parsed_url: Any, path: str, payload: dict[str, str]
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        parsed_url.hostname, parsed_url.port, timeout=5
    )
    body = json.dumps(payload, separators=(",", ":"))
    connection.request(
        "PATCH",
        path,
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://{parsed_url.netloc}",
        },
    )
    response = connection.getresponse()
    response_body = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, headers, response_body


def dashboard_http_post_attachment(
    parsed_url: Any,
    path: str,
    *,
    filename: str,
    content: bytes,
) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(
        parsed_url.hostname, parsed_url.port, timeout=5
    )
    connection.request(
        "POST",
        path,
        body=content,
        headers={
            "Content-Type": "text/markdown; charset=utf-8",
            "Origin": f"http://{parsed_url.netloc}",
            "X-AgTask-Filename": quote(filename, safe=""),
        },
    )
    response = connection.getresponse()
    response_body = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, headers, response_body


def verify_dashboard(
    cli: Path,
    database: Path,
    main_thread_id: str,
    parent_session_id: str,
    thread_id: str,
    session_id: str,
    title: str,
    closed_thread: dict[str, Any],
) -> dict[str, Any]:
    attachment_path = database.parent / "dashboard-task.md"
    attachment_path.write_text("Dashboard integration attachment.\n")
    attachment_result = run_cli(
        cli,
        "attach",
        str(attachment_path),
        "--id",
        thread_id,
    )
    require(
        attachment_result["attachment"]["path"] == str(attachment_path.resolve())
        and attachment_result["status"] == "done",
        "dashboard attachment did not copy the finalized task status",
    )
    before = query_known_rows(database, main_thread_id, thread_id)
    status_fixture_id = str(uuid.uuid4())
    status_fixture_session_id = f"dashboard-status-{status_fixture_id[:8]}"
    status_fixture = run_cli(
        cli,
        "register",
        "--id",
        status_fixture_id,
        "--session-id",
        status_fixture_session_id,
        "--kind",
        "main",
        "--project",
        PROJECT,
        "--title",
        f"agtask/integ-dashboard-status-{status_fixture_id[:8]}",
        "--initial-prompt",
        "Verify the dashboard status mutation contract.",
        "--status",
        "active",
    )
    require(
        status_fixture["status"] == "active",
        "dashboard status fixture did not start active",
    )
    bulk_fixture_id = str(uuid.uuid4())
    bulk_fixture_session_id = f"dashboard-bulk-{bulk_fixture_id[:8]}"
    bulk_fixture = run_cli(
        cli,
        "register",
        "--id",
        bulk_fixture_id,
        "--session-id",
        bulk_fixture_session_id,
        "--kind",
        "main",
        "--project",
        PROJECT,
        "--title",
        f"agtask/integ-dashboard-bulk-{bulk_fixture_id[:8]}",
        "--initial-prompt",
        "Verify the dashboard bulk mutation contract.",
        "--status",
        "active",
    )
    require(
        bulk_fixture["status"] == "active",
        "dashboard bulk fixture did not start active",
    )
    upload_fixture_id = str(uuid.uuid4())
    upload_fixture_session_id = f"dashboard-upload-{upload_fixture_id[:8]}"
    upload_fixture = run_cli(
        cli,
        "register",
        "--id",
        upload_fixture_id,
        "--session-id",
        upload_fixture_session_id,
        "--kind",
        "main",
        "--project",
        PROJECT,
        "--title",
        f"agtask/integ-dashboard-upload-{upload_fixture_id[:8]}",
        "--initial-prompt",
        "Verify the dashboard managed attachment contract.",
        "--status",
        "active",
    )
    require(
        upload_fixture["status"] == "active",
        "dashboard upload fixture did not start active",
    )
    snapshot = run_cli(
        cli,
        "dashboard",
        "--project",
        PROJECT,
        "--parent-session-id",
        parent_session_id,
        "--search",
        title,
    )
    require(
        [group["status"] for group in snapshot["groups"]]
        == ["todo", "active", "blocked", "merging", "done", "drop"],
        "dashboard default groups are not in canonical status order",
    )
    require(snapshot["visible_count"] == 1, "dashboard did not isolate the live child")
    done_threads = snapshot["groups"][4]["threads"]
    require(len(done_threads) == 1, "dashboard done group does not contain one child")
    projection = done_threads[0]
    require(
        set(projection)
        == {
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
        "dashboard child projection has unexpected fields",
    )
    require(projection["id"] == thread_id, "dashboard returned the wrong child")
    require(projection["session_id"] == session_id, "dashboard session mismatch")
    require(
        projection["parent_session_id"] == parent_session_id,
        "dashboard parent mismatch",
    )
    require(projection["project"] == PROJECT, "dashboard project mismatch")
    require(projection["title"] == title, "dashboard title mismatch")
    require(projection["status"] == "done", "dashboard child is not done")
    require(
        projection["files"] == [attachment_result["attachment"]],
        "dashboard child attachment projection mismatch",
    )
    require(projection["closed"] == closed_thread["closed"], "dashboard close time mismatch")
    require(
        snapshot["filters"]
        == {
            "projects": [PROJECT],
            "parent_session_ids": [parent_session_id],
            "include_root": False,
            "statuses": [],
        },
        "dashboard filter state mismatch",
    )
    require(snapshot["search"] == title, "dashboard search state mismatch")
    identity_search = session_id[:8].upper()
    identity_search_snapshot = run_cli(
        cli,
        "dashboard",
        "--project",
        PROJECT,
        "--search",
        identity_search,
    )
    require(
        identity_search_snapshot["visible_count"] == 1
        and identity_search_snapshot["groups"][4]["threads"] == [projection]
        and identity_search_snapshot["search"] == identity_search,
        "dashboard partial Codex session ID search mismatch",
    )
    require(
        snapshot["sort"] == {"field": "updated", "direction": "desc"},
        "dashboard default sort mismatch",
    )
    require(
        any(item == {"value": PROJECT, "count": item["count"]} for item in snapshot["facets"]["projects"]),
        "dashboard project facet is missing",
    )
    require(
        any(item["value"] == parent_session_id for item in snapshot["facets"]["parents"]),
        "dashboard parent facet is missing",
    )
    require(
        [item["value"] for item in snapshot["facets"]["statuses"]]
        == ["todo", "active", "blocked", "merging", "done", "drop"],
        "dashboard status facets are not canonical",
    )
    done_filter_snapshot = run_cli(
        cli,
        "dashboard",
        "--project",
        PROJECT,
        "--parent-session-id",
        parent_session_id,
        "--status",
        "done",
        "--search",
        title,
    )
    require(
        [group["status"] for group in done_filter_snapshot["groups"]] == ["done"]
        and done_filter_snapshot["groups"][0]["threads"] == [projection],
        "dashboard status filter mismatch",
    )

    process = subprocess.Popen(
        [
            sys.executable,
            str(cli),
            "dashboard",
            "--no-open",
            "--project",
            PROJECT,
            "--parent-session-id",
            parent_session_id,
            "--search",
            title,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    ready = selector.select(timeout=5)
    require(bool(ready), "dashboard server did not publish its URL")
    url = process.stdout.readline().strip()
    parsed = urlsplit(url)
    route_parts = [part for part in parsed.path.split("/") if part]
    require(parsed.scheme == "http", "dashboard URL is not HTTP")
    require(parsed.hostname == "127.0.0.1", "dashboard did not bind numeric loopback")
    require(bool(parsed.port), "dashboard URL is missing its ephemeral port")
    require(len(route_parts) == 1 and len(route_parts[0]) >= 32, "dashboard token path is not opaque")
    root = parsed.path
    responses: dict[str, dict[str, Any]] = {}
    encoded_session_id = "~" + quote(session_id, safe="")
    detail_snapshot: dict[str, Any] | None = None
    status_update_snapshot: dict[str, Any] | None = None
    status_transition_snapshot: dict[str, str] | None = None
    managed_attachment_snapshot: dict[str, Any] | None = None
    try:
        for name, path, media_type in (
            ("html", root, "text/html; charset=utf-8"),
            ("css", root + "app.css", "text/css; charset=utf-8"),
            ("javascript", root + "app.js", "text/javascript; charset=utf-8"),
            ("detail_html", root + "tasks/" + encoded_session_id, "text/html; charset=utf-8"),
            ("detail_javascript", root + "task.js", "text/javascript; charset=utf-8"),
            ("api", root + "api/dashboard?" + parsed.query, "application/json; charset=utf-8"),
            ("detail_api", root + "api/tasks/" + encoded_session_id, "application/json; charset=utf-8"),
        ):
            status, headers, body = dashboard_http_get(parsed, path)
            require(status == 200, f"dashboard {name} route returned {status}")
            require(headers.get("content-type") == media_type, f"dashboard {name} media type mismatch")
            require(headers.get("cache-control") == "no-store", f"dashboard {name} cache policy mismatch")
            require(headers.get("referrer-policy") == "no-referrer", f"dashboard {name} referrer policy mismatch")
            require(headers.get("x-content-type-options") == "nosniff", f"dashboard {name} nosniff policy mismatch")
            if name == "html":
                require("default-src 'none'" in headers.get("content-security-policy", ""), "dashboard CSP missing")
                require(
                    all(
                        marker in body
                        for marker in (
                            b"Task search",
                            b"Refresh",
                            b'id="filter-trigger"',
                            b'id="filter-menu"',
                            b'id="active-filters"',
                            b'id="add-filter"',
                            b'id="status-modal"',
                            b'id="status-options"',
                            b'id="attachment-picker"',
                        )
                    ),
                    "dashboard filter controls missing",
                )
            if name == "detail_html":
                require(
                    all(
                        marker in body
                        for marker in (
                            b'id="task-title"',
                            b'id="task-description"',
                            b'id="timeline"',
                            b'id="task-created"',
                            b'id="task-updated"',
                            b'id="task-session-id"',
                            b'id="task-files"',
                            b'class="session-link"',
                            b'href="../app.css"',
                            b'src="../task.js"',
                        )
                    ),
                    "dashboard task detail structure is missing",
                )
            if name == "javascript":
                require(
                    b"data-task-id" in body
                    and b"location.assign" in body
                    and b"tasks/~${encodeURIComponent(sessionId)}" in body
                    and b"codex://threads/${encodeURIComponent(sessionId)}" in body
                    and b"FILTER_DEFS" in body
                    and b"menuKeydown" in body
                    and b"STATUS_OPTIONS" in body
                    and b'value:"done"' in body
                    and b'value:"drop"' in body
                    and b"expected_status" in body
                    and b"selection-toggle" in body
                    and b'key==="j"' in body
                    and b'key==="x"' in body
                    and b'key==="a"' in body
                    and b'"api/tasks/status"' in body
                    and b'/attachments`' in body
                    and b'"X-AgTask-Filename"' in body
                    and b"file-badge" in body
                    and b"taskIdentityCell" in body
                    and b"navigator.clipboard.writeText" in body
                    and b'"Task ID"' in body
                    and b'"Codex SHA"' in body
                    and b"/status" in body,
                    "dashboard client interactions or task-row links are missing",
                )
            if name == "detail_javascript":
                require(
                    b"../api/tasks/~${encodeURIComponent(sessionId)}" in body
                    and b"task-description" in body
                    and b"timelineItem" in body
                    and b"codex://threads/${encodeURIComponent(task.session_id)}" in body
                    and b"fileBadge" in body
                    and b"textContent" in body
                    and b"innerHTML" not in body,
                    "dashboard task detail client behavior is missing",
                )
            if name in {"html", "css", "javascript", "detail_html", "detail_javascript"}:
                require(title.encode() not in body and session_id.encode() not in body, "task data leaked into static dashboard assets")
            if name == "api":
                require(json.loads(body) == snapshot, "dashboard HTTP and CLI snapshots differ")
            if name == "detail_api":
                detail_snapshot = json.loads(body)
                require(
                    set(detail_snapshot)
                    == {
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
                    "dashboard task detail projection has unexpected fields",
                )
                require(detail_snapshot["id"] == thread_id, "dashboard detail task mismatch")
                require(
                    detail_snapshot["session_id"] == session_id,
                    "dashboard detail session mismatch",
                )
                require(
                    detail_snapshot["parent_session_id"] == parent_session_id,
                    "dashboard detail parent mismatch",
                )
                require(detail_snapshot["title"] == title, "dashboard detail title mismatch")
                require(
                    detail_snapshot["files"] == [attachment_result["attachment"]],
                    "dashboard detail attachment projection mismatch",
                )
                require(
                    detail_snapshot["description"] == closed_thread["description"],
                    "dashboard detail description mismatch",
                )
                expected_rollouts = [
                    {"created": row["created"], "role": row["role"], "message": row["message"]}
                    for row in sorted(
                        query_rollouts(database, thread_id),
                        key=lambda row: (row["created"], row["id"]),
                        reverse=True,
                    )
                ]
                require(
                    detail_snapshot["rollouts"] == expected_rollouts,
                    "dashboard detail rollouts are not newest first",
                )
            responses[name] = {
                "status": status,
                "content_type": headers["content-type"],
                "cache_control": headers["cache-control"],
                "referrer_policy": headers["referrer-policy"],
                "nosniff": headers["x-content-type-options"],
                "content_length": len(body),
            }

        upload_path = (
            root
            + "api/tasks/~"
            + quote(upload_fixture_session_id, safe="")
            + "/attachments"
        )
        upload_status, upload_headers, upload_body = dashboard_http_post_attachment(
            parsed,
            upload_path,
            filename="dashboard managed.md",
            content=b"# Managed dashboard attachment\n",
        )
        require(upload_status == 201, "dashboard attachment upload did not succeed")
        require(
            upload_headers.get("content-type") == "application/json; charset=utf-8",
            "dashboard attachment upload media type mismatch",
        )
        upload_result = json.loads(upload_body)
        require(
            upload_result["attached"] is True
            and upload_result["attachment"]["name"] == "dashboard managed.md",
            "dashboard attachment upload result mismatch",
        )
        managed_path = Path(upload_result["attachment"]["path"])
        managed_root = database.parent / "attachments"
        require(
            managed_path.is_relative_to(managed_root)
            and managed_path.is_file()
            and managed_path.stat().st_mode & 0o777 == 0o600,
            "dashboard managed attachment path or mode mismatch",
        )
        require(
            all(
                directory.stat().st_mode & 0o777 == 0o700
                for directory in (managed_root, managed_path.parent.parent, managed_path.parent)
            ),
            "dashboard managed attachment directory mode mismatch",
        )
        require(
            managed_path.read_text()
            == "---\nstatus: active\n"
            f"source: codex://threads/{quote(upload_fixture_session_id, safe='')}\n"
            "---\n# Managed dashboard attachment\n",
            "dashboard managed attachment frontmatter mismatch",
        )
        connection = sqlite3.connect(database)
        try:
            stored_paths = [
                row[0]
                for row in connection.execute(
                    "SELECT path FROM attachment WHERE thread_id=? ORDER BY id",
                    (upload_fixture_id,),
                )
            ]
        finally:
            connection.close()
        require(
            stored_paths == [str(managed_path)],
            "dashboard managed attachment ledger evidence mismatch",
        )
        before_rejection = set(managed_root.rglob("*"))
        rejected_status, _rejected_headers, _rejected_body = (
            dashboard_http_post_attachment(
                parsed,
                upload_path,
                filename="../escape.md",
                content=b"must not persist\n",
            )
        )
        require(rejected_status == 400, "dashboard unsafe attachment was not rejected")
        connection = sqlite3.connect(database)
        try:
            attachment_count = connection.execute(
                "SELECT count(*) FROM attachment WHERE thread_id=?",
                (upload_fixture_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        require(
            attachment_count == 1 and set(managed_root.rglob("*")) == before_rejection,
            "dashboard rejected attachment left a row or managed path",
        )
        managed_attachment_snapshot = {
            "status": upload_status,
            "name": upload_result["attachment"]["name"],
            "file_mode": "0600",
            "directory_mode": "0700",
            "unsafe_name_rejected": True,
        }
        responses["attachment_upload"] = {
            "status": upload_status,
            "content_type": upload_headers["content-type"],
            "cache_control": upload_headers["cache-control"],
            "referrer_policy": upload_headers["referrer-policy"],
            "nosniff": upload_headers["x-content-type-options"],
            "content_length": len(upload_body),
        }

        status_path = (
            root
            + "api/tasks/~"
            + quote(status_fixture_session_id, safe="")
            + "/status"
        )
        status, headers, body = dashboard_http_patch(
            parsed,
            status_path,
            {"expected_status": "active", "status": "blocked"},
        )
        require(status == 200, f"dashboard status update returned {status}")
        require(
            headers.get("content-type") == "application/json; charset=utf-8",
            "dashboard status update media type mismatch",
        )
        status_update_snapshot = json.loads(body)
        require(
            set(status_update_snapshot) == {"changed", "task"}
            and status_update_snapshot["changed"] is True,
            "dashboard status update result mismatch",
        )
        status_projection = status_update_snapshot["task"]
        require(
            set(status_projection)
            == {
                "id",
                "session_id",
                "parent_session_id",
                "project",
                "title",
                "created",
                "updated",
                "closed",
                "status",
            },
            "dashboard status projection has unexpected fields",
        )
        require(
            status_projection["id"] == status_fixture_id
            and status_projection["session_id"] == status_fixture_session_id
            and status_projection["status"] == "blocked"
            and status_projection["closed"] is None,
            "dashboard status fixture projection mismatch",
        )
        status_rollouts = [
            row
            for row in query_rollouts(database, status_fixture_id)
            if row["message"].startswith("status:")
        ]
        require(
            len(status_rollouts) == 1
            and status_rollouts[0]["role"] == "meta"
            and status_rollouts[0]["message"] == "status:active->blocked"
            and status_rollouts[0]["created"] == status_projection["updated"],
            "dashboard status transition event mismatch",
        )
        status_transition_snapshot = {
            "created": status_rollouts[0]["created"],
            "role": status_rollouts[0]["role"],
            "message": status_rollouts[0]["message"],
        }
        stale_status, _stale_headers, stale_body = dashboard_http_patch(
            parsed,
            status_path,
            {"expected_status": "active", "status": "todo"},
        )
        require(
            stale_status == 409
            and "refresh and try again"
            in json.loads(stale_body).get("error", ""),
            "dashboard stale status update was not rejected",
        )
        require(
            query_thread(database, status_fixture_id)["status"] == "blocked"
            and len(
                [
                    row
                    for row in query_rollouts(database, status_fixture_id)
                    if row["message"].startswith("status:")
                ]
            )
            == 1,
            "dashboard stale status update changed the fixture",
        )
        bulk_path = root + "api/tasks/status"
        bulk_conflict_status, _bulk_conflict_headers, bulk_conflict_body = (
            dashboard_http_patch(
                parsed,
                bulk_path,
                {
                    "tasks": [
                        {
                            "session_id": status_fixture_session_id,
                            "expected_status": "blocked",
                        },
                        {
                            "session_id": bulk_fixture_session_id,
                            "expected_status": "blocked",
                        },
                    ],
                    "status": "done",
                },
            )
        )
        require(
            bulk_conflict_status == 409
            and "refresh and try again"
            in json.loads(bulk_conflict_body).get("error", ""),
            "dashboard bulk stale status was not rejected",
        )
        require(
            query_thread(database, status_fixture_id)["status"] == "blocked"
            and query_thread(database, bulk_fixture_id)["status"] == "active",
            "dashboard bulk conflict partially changed its fixtures",
        )
        done_status, done_headers, done_body = dashboard_http_patch(
            parsed,
            bulk_path,
            {
                "tasks": [
                    {
                        "session_id": status_fixture_session_id,
                        "expected_status": "blocked",
                    },
                    {
                        "session_id": bulk_fixture_session_id,
                        "expected_status": "active",
                    },
                ],
                "status": "done",
            },
        )
        done_snapshot = json.loads(done_body)
        require(
            done_status == 200
            and set(done_snapshot) == {"changed", "tasks"}
            and done_snapshot["changed"] is True
            and [task["session_id"] for task in done_snapshot["tasks"]]
            == [status_fixture_session_id, bulk_fixture_session_id]
            and all(
                task["status"] == "done"
                and task["closed"] == task["updated"]
                for task in done_snapshot["tasks"]
            ),
            "dashboard bulk Done completion transition mismatch",
        )
        done_rollouts = [
            row
            for row in query_rollouts(database, status_fixture_id)
            if row["message"].startswith("status:")
        ]
        require(
            [row["message"] for row in done_rollouts]
            == ["status:active->blocked", "status:blocked->done"],
            "dashboard Done transition evidence mismatch",
        )
        bulk_rollouts = [
            row
            for row in query_rollouts(database, bulk_fixture_id)
            if row["message"].startswith("status:")
        ]
        require(
            [row["message"] for row in bulk_rollouts] == ["status:active->done"],
            "dashboard bulk fixture transition evidence mismatch",
        )
        require(
            not any(
                row["message"] == "finalization:completed"
                for fixture_id in (status_fixture_id, bulk_fixture_id)
                for row in query_rollouts(database, fixture_id)
            ),
            "dashboard Done dispatched close finalization evidence",
        )
        require(
            query_merge_claim(database, PROJECT) is None,
            "dashboard Done created a project merge claim",
        )
        responses["status_update"] = {
            "status": status,
            "content_type": headers["content-type"],
            "cache_control": headers["cache-control"],
            "referrer_policy": headers["referrer-policy"],
            "nosniff": headers["x-content-type-options"],
            "content_length": len(body),
        }
        responses["bulk_status_update"] = {
            "status": done_status,
            "content_type": done_headers["content-type"],
            "cache_control": done_headers["cache-control"],
            "referrer_policy": done_headers["referrer-policy"],
            "nosniff": done_headers["x-content-type-options"],
            "content_length": len(done_body),
            "stale_conflict": True,
        }
    finally:
        selector.close()
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()
    require(process.returncode == 0, "dashboard server did not stop cleanly")
    after = query_known_rows(database, main_thread_id, thread_id)
    require(after == before, "dashboard changed known ledger rows or schema version")
    status_fixture_after = query_thread(database, status_fixture_id)
    require(
        status_fixture_after is not None
        and status_fixture_after["status"] == "done"
        and status_fixture_after["closed"] == status_fixture_after["updated"],
        "dashboard status fixture did not retain the expected transition",
    )
    bulk_fixture_after = query_thread(database, bulk_fixture_id)
    require(
        bulk_fixture_after is not None
        and bulk_fixture_after["status"] == "done"
        and bulk_fixture_after["closed"] == bulk_fixture_after["updated"],
        "dashboard bulk fixture did not retain the expected transition",
    )
    upload_fixture_after = query_thread(database, upload_fixture_id)
    require(
        upload_fixture_after is not None and upload_fixture_after["status"] == "active",
        "dashboard upload fixture changed lifecycle status",
    )
    return {
        "scenario": DASHBOARD_SCENARIO_NAME,
        "scenario_version": DASHBOARD_SCENARIO_VERSION,
        "origin": {"scheme": "http", "host": "127.0.0.1", "ephemeral_port": True},
        "route": {"opaque_token": True, "token_retained": False},
        "responses": responses,
        "snapshot": snapshot,
        "status_filter_snapshot": done_filter_snapshot,
        "detail_snapshot": detail_snapshot,
        "attachment": attachment_result["attachment"],
        "managed_attachment": managed_attachment_snapshot,
        "status_update": {
            "result": status_update_snapshot,
            "stale_conflict": True,
            "transition_rollout_count": len(done_rollouts),
            "transition": status_transition_snapshot,
            "done_result": done_snapshot,
            "transitions": [
                {
                    "created": row["created"],
                    "role": row["role"],
                    "message": row["message"],
                }
                for row in done_rollouts
            ],
        },
        "clean_shutdown": True,
        "known_rows_unchanged": True,
        "schema_version": after["schema_version"],
    }


def verify_layered_configuration(cli: Path, proof_dir: Path) -> dict[str, Any]:
    fixture = proof_dir / "config-fixture"
    home = fixture / "home"
    project = fixture / "project"
    home.mkdir(parents=True, exist_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    home_path = home / ".agtask.json"
    project_path = project / ".agtask.json"
    home_document = {
        "defaults": {
            "mode": "fork",
            "kind": "main",
            "project": "home-project",
            "worktree": True,
            "model": "home-model",
            "pin": False,
        },
        "hooks": {
            "OnCreate": {"prompt": "home create"},
            "OnPreClose": {"prompt": "home pre close"},
            "OnPostClose": {"prompt": "home post close"},
        },
    }
    project_document = {
        "defaults": {"project": "project-default", "model": "project-model"},
        "hooks": {"OnCreate": {"prompt": "project create"}},
    }
    home_path.write_text(json.dumps(home_document, indent=2) + "\n")
    project_path.write_text(json.dumps(project_document, indent=2) + "\n")
    environment = os.environ.copy()
    environment["HOME"] = str(home)

    merged = run_cli(cli, "config", cwd=project, environment=environment)
    expected_defaults = {
        "mode": "fork",
        "kind": "main",
        "project": "project-default",
        "worktree": True,
        "model": "project-model",
        "pin": False,
    }
    require(merged["defaults"] == expected_defaults, "layered defaults did not merge")
    require(
        merged["hooks"]
        == {
            "OnCreate": {"prompt": "project create"},
            "OnPreClose": {"prompt": "home pre close"},
            "OnPostClose": {"prompt": "home post close"},
        },
        "layered hooks did not merge by event",
    )
    require(
        merged["sources"] == [str(home_path.resolve()), str(project_path.resolve())],
        "configuration sources are not low-to-high precedence",
    )
    resolved = run_cli(
        cli,
        "resolve-create",
        "--title",
        CONFIG_TITLE,
        cwd=project,
        environment=environment,
    )
    require(resolved["mode"] == "fork", "home mode default was not applied")
    require(resolved["kind"] == "main", "home kind default was not applied")
    require(resolved["project"] == "project-default", "project default did not win")
    require(resolved["worktree"] is True, "boolean worktree default was not applied")
    require(resolved["model"] == "project-model", "project model did not win")
    require(resolved["pin"] is False, "boolean pin default was not applied")
    require(resolved["environment"] == {"type": "worktree"}, "environment mismatch")
    require(resolved["include_model"] is True, "include_model mismatch")
    require(
        resolved["title"] == CONFIG_TITLE
        and resolved["bootstrap_args"]
        == {"pin": False, "title": CONFIG_TITLE}
        and resolved["bootstrap_trailer"] == BOOTSTRAP_FALSE_TRAILER,
        "configured bootstrap arguments mismatch",
    )
    require(
        resolved["hook_prompts"]
        == [
            {
                "event": "OnCreate",
                "prompt": "project create",
                "source": str(project_path.resolve()),
            }
        ],
        "resolved OnCreate prompt did not use the project source",
    )
    explicit = run_cli(
        cli,
        "resolve-create",
        "--mode",
        "clean",
        "--kind",
        "child",
        "--project",
        "explicit",
        "--parent-session-id",
        "integ-parent",
        "--title",
        EXPLICIT_TITLE,
        "--worktree",
        "false",
        "--model",
        "inherit",
        "--pin",
        "true",
        cwd=project,
        environment=environment,
    )
    require(explicit["mode"] == "clean", "explicit mode did not win")
    require(explicit["kind"] == "child", "explicit kind did not win")
    require(explicit["project"] == "explicit", "explicit project did not win")
    require(explicit["worktree"] is False, "explicit worktree did not win")
    require(explicit["model"] == "inherit", "explicit model did not win")
    require(explicit["pin"] is True, "explicit pin did not win")
    require(explicit["environment"] == {"type": "local"}, "explicit environment mismatch")
    require(explicit["include_model"] is False, "explicit include_model mismatch")
    explicit_id = explicit.get("id")
    require(
        isinstance(explicit_id, str)
        and uuid.UUID(explicit_id).version == 4
        and str(uuid.UUID(explicit_id)) == explicit_id,
        "explicit creation ID is not a canonical UUIDv4",
    )
    require(
        explicit["title"] == EXPLICIT_TITLE
        and explicit["bootstrap_args"]
        == {
            "id": explicit_id,
            "parent_session_id": "integ-parent",
            "pin": True,
            "project": "explicit",
            "title": EXPLICIT_TITLE,
        }
        and explicit["bootstrap_trailer"]
        == (
            '<agtask-bootstrap version="2">\n'
            f'{{"id":"{explicit_id}","parent_session_id":"integ-parent",'
            '"pin":true,"project":"explicit","title":"agtask/integ-explicit-title"}\n'
            '</agtask-bootstrap>'
        ),
        "explicit bootstrap arguments mismatch",
    )
    return {
        "home_path": str(home_path.resolve()),
        "project_path": str(project_path.resolve()),
        "home_document": home_document,
        "project_document": project_document,
        "merged": merged,
        "resolved": resolved,
        "explicit": explicit,
    }


def verify_bootstrap_protocol(
    cli: Path,
    database: Path,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    def counts() -> dict[str, int]:
        connection = sqlite3.connect(database)
        try:
            return {
                "schema_version": connection.execute("PRAGMA user_version").fetchone()[0],
                "threads": connection.execute("SELECT count(*) FROM thread").fetchone()[0],
                "rollouts": connection.execute("SELECT count(*) FROM rollout").fetchone()[0],
            }
        finally:
            connection.close()

    def hook(prompt: str, *, event: str = "UserPromptSubmit") -> subprocess.CompletedProcess[str]:
        payload: dict[str, Any] = {
            "hook_event_name": event,
            "session_id": "integ-materialized-child",
        }
        if event == "UserPromptSubmit":
            payload.update({"turn_id": "integ-bootstrap-turn", "prompt": prompt})
        else:
            payload.update({"source": "startup", "prompt": prompt})
        return subprocess.run(
            [sys.executable, str(cli), "hook"],
            cwd=cwd,
            env=environment,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )

    before = counts()
    valid_prompt = "Task:\nBootstrap protocol proof.\n\n" + BOOTSTRAP_TRUE_TRAILER
    valid = hook(valid_prompt)
    repeat = hook(valid_prompt)
    require(valid.returncode == repeat.returncode == 0, "valid bootstrap hook failed")
    require(valid.stderr == repeat.stderr == "", "valid bootstrap hook wrote stderr")
    require(valid.stdout == repeat.stdout, "bootstrap handler is not deterministic")
    valid_document = json.loads(valid.stdout)
    require(
        valid_document.get("hookSpecificOutput", {}).get("hookEventName")
        == "UserPromptSubmit",
        "bootstrap hook did not return structured UserPromptSubmit output",
    )
    valid_context = valid_document["hookSpecificOutput"].get("additionalContext", "")
    require(
        "codex_app__move_thread_to_sidebar_section" in valid_context
        and "codex_app__set_thread_pinned" in valid_context
        and valid_context.index("codex_app__move_thread_to_sidebar_section")
        < valid_context.index("codex_app__set_thread_pinned")
        and '"sectionId":"pinned"' in valid_context
        and "codex_app__set_thread_title" in valid_context
        and '"threadId":"integ-materialized-child"' in valid_context
        and f'"title":"{BOOTSTRAP_PROTOCOL_TITLE}"' in valid_context
        and "idempotent" in valid_context
        and "failed: <exact error>" in valid_context
        and "continue the actual task" in valid_context,
        "valid bootstrap action contract mismatch",
    )
    pin_false = hook(valid_prompt.replace('"pin":true', '"pin":false'))
    require(pin_false.returncode == 0 and pin_false.stderr == "", "pin=false hook failed")
    pin_false_context = json.loads(pin_false.stdout)["hookSpecificOutput"][
        "additionalContext"
    ]
    require(
        "codex_app__move_thread_to_sidebar_section" not in pin_false_context
        and "codex_app__set_thread_pinned" not in pin_false_context
        and "codex_app__set_thread_title" in pin_false_context,
        "pin=false did not preserve the title action",
    )
    ignored = {
        "wrong-type": valid_prompt.replace("true", '\"true\"'),
        "integer-not-bool": valid_prompt.replace("true", "1"),
        "duplicate-key": valid_prompt.replace(
            '{"pin":true,"title":"agtask/integ-materialized-title"}',
            '{"pin":true,"pin":false,"title":"agtask/integ-materialized-title"}',
        ),
        "unknown-key": valid_prompt.replace(
            '{"pin":true,"title":"agtask/integ-materialized-title"}',
            '{"command":"ignored","pin":true,"title":"agtask/integ-materialized-title"}',
        ),
        "title-wrong-type": valid_prompt.replace(
            '"title":"agtask/integ-materialized-title"', '"title":true'
        ),
        "title-empty": valid_prompt.replace(
            '"title":"agtask/integ-materialized-title"', '"title":""'
        ),
        "noncanonical": valid_prompt.replace(
            '{"pin":true,"title":"agtask/integ-materialized-title"}',
            '{"pin": true,"title":"agtask/integ-materialized-title"}',
        ),
        "wrong-version": valid_prompt.replace('version="1"', 'version="2"'),
        "lookalike": "Task:\nargs: {\"pin\": true}",
        "not-final": valid_prompt + "\nTask text after metadata.",
        "session-start": valid_prompt,
    }
    ignored_results: dict[str, dict[str, Any]] = {}
    for name, prompt in ignored.items():
        process = hook(prompt, event="SessionStart" if name == "session-start" else "UserPromptSubmit")
        require(process.returncode == 0, f"ignored bootstrap case failed: {name}")
        require(process.stdout == process.stderr == "", f"ignored bootstrap case emitted output: {name}")
        ignored_results[name] = {"returncode": process.returncode, "output_empty": True}
    after = counts()
    require(after == before, "bootstrap protocol probe mutated the ledger")
    return {
        "scenario": BOOTSTRAP_SCENARIO_NAME,
        "scenario_version": BOOTSTRAP_SCENARIO_VERSION,
        "valid_output": valid_document,
        "pin_false_output": json.loads(pin_false.stdout),
        "repeat_equal": True,
        "ignored": ignored_results,
        "ledger_unchanged": True,
        "ledger_counts": after,
    }


def verify_creation_identity_regression(
    cli: Path,
    database: Path,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    creation_id = "1d7e4ef1-0c28-4a3d-93b1-779c7fe52bd8"
    real_session_id = "019f6e67-dbc6-7111-b791-43d223817140"
    copied_session_id = "019f6e67-e372-7d03-bd30-4afcbe485556"
    parent_session_id = "019f6e68-19d6-7e10-a449-506a0de88117"
    title = "Implement per-project merge queue"
    description = "Implement a simple per-project merge queue for agtask."
    cache_miss = run_cli(
        cli,
        "section-cache",
        "get",
        "--session-id",
        parent_session_id,
        cwd=cwd,
        environment=environment,
    )
    require(cache_miss.get("state") == "miss", "new main session unexpectedly had cached sidebar placement")
    cache_stored = run_cli(
        cli,
        "section-cache",
        "set",
        "--session-id",
        parent_session_id,
        "--host-id",
        "local",
        "--section-id",
        BOOTSTRAP_CUSTOM_SECTION_ID,
        "--section-name",
        "proj/clawpilot",
        cwd=cwd,
        environment=environment,
    )
    require(
        cache_stored.get("state") == "stored"
        and cache_stored.get("entry", {}).get("section_id") == BOOTSTRAP_CUSTOM_SECTION_ID,
        "main session custom section was not cached",
    )
    cache_hit = run_cli(
        cli,
        "section-cache",
        "get",
        "--session-id",
        parent_session_id,
        cwd=cwd,
        environment=environment,
    )
    require(
        cache_hit.get("state") == "hit"
        and cache_hit.get("entry", {}).get("section_id") == BOOTSTRAP_CUSTOM_SECTION_ID
        and (database.parent / "sidebar-sections.json").is_file(),
        "section cache did not reuse the proof-local ledger directory",
    )
    trailer = (
        '<agtask-bootstrap version="2">\n'
        + json.dumps(
            {
                "id": creation_id,
                "parent_session_id": parent_session_id,
                "pin": True,
                "project": "agtask-regression",
                "section_id": BOOTSTRAP_CUSTOM_SECTION_ID,
                "title": title,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n</agtask-bootstrap>"
    )
    real_prompt = description + "\n\n" + trailer
    copied_payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": copied_session_id,
        "turn_id": "observed-title-generator-turn",
        "prompt": "You are a helpful assistant.\n\n" + trailer,
    }
    copied_output = run_hook(
        cli, copied_payload, cwd=cwd, environment=environment
    )
    require(bool(copied_output), "first copied bootstrap did not register")
    run_hook(
        cli,
        {
            "hook_event_name": "Stop",
            "session_id": copied_session_id,
            "turn_id": "observed-title-generator-turn",
            "last_assistant_message": (
                '{"title":"Implement merge queue",'
                '"description":"Implement a per-project merge queue"}'
            ),
        },
        cwd=cwd,
        environment=environment,
    )

    real_payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": real_session_id,
        "turn_id": "observed-real-turn",
        "prompt": real_prompt,
    }
    real_hook_output = run_hook(
        cli, real_payload, cwd=cwd, environment=environment
    )
    require(
        real_hook_output == "",
        "conflicting real hook unexpectedly replaced the copied binding",
    )

    parent_registration = run_cli(
        cli,
        "register",
        "--id",
        creation_id,
        "--session-id",
        real_session_id,
        "--parent-session-id",
        parent_session_id,
        "--kind",
        "child",
        "--project",
        "agtask-regression",
        "--title",
        title,
        "--initial-prompt",
        real_prompt,
        "--status",
        "active",
        "--authoritative-session",
        cwd=cwd,
        environment=environment,
    )
    require(
        parent_registration.get("session_rebound_from") == copied_session_id,
        "authoritative registration did not report the copied session",
    )
    fallback = run_cli(
        cli,
        "record-turn",
        "--id",
        creation_id,
        "--role",
        "user",
        "--turn-id",
        "bootstrap",
        "--content",
        real_prompt,
        cwd=cwd,
        environment=environment,
    )
    thread = query_thread(database, creation_id)
    rollouts = query_rollouts(database, creation_id)
    require(thread is not None, "authoritative creation session was not registered")
    require(
        thread["session_id"] == real_session_id
        and thread["parent_session_id"] == parent_session_id
        and thread["description"] == description,
        "creation identity bound to the wrong session or metadata",
    )
    require(
        query_thread_by_session(database, copied_session_id) is None,
        "copied title-generator session remained bound after reconciliation",
    )
    require(
        [(row["role"], row["turn_id"], row["message"]) for row in rollouts]
        == [
            ("meta", "thread.created", "thread.created"),
            ("user", "bootstrap", description),
        ],
        "authoritative reconciliation retained copied helper history",
    )
    copied_document = json.loads(copied_output)
    context = copied_document["hookSpecificOutput"]["additionalContext"]
    require(
        f'"threadId":"{copied_session_id}"' in context
        and "codex_app__move_thread_to_sidebar_section" in context
        and "codex_app__set_thread_pinned" in context
        and f'"sectionId":"{BOOTSTRAP_CUSTOM_SECTION_ID}"' in context,
        "copied first-writer proof did not target its own session",
    )
    return {
        "scenario": CREATION_BOOTSTRAP_SCENARIO_NAME,
        "scenario_version": CREATION_BOOTSTRAP_SCENARIO_VERSION,
        "creation_id": creation_id,
        "real_session_id": real_session_id,
        "copied_session_id": copied_session_id,
        "real_hook_output_empty": True,
        "session_rebound_from": parent_registration["session_rebound_from"],
        "parent_registration": parent_registration,
        "fallback": fallback,
        "thread": thread,
        "rollouts": rollouts,
    }


def verify_archived_session_audit(
    cli: Path,
    proof_dir: Path,
    cwd: Path,
    environment: dict[str, str],
    skill_text: str,
) -> dict[str, Any]:
    audit_database = proof_dir / "audit-ledger.db"
    audit_environment = environment.copy()
    audit_environment["AGTASK_DB"] = str(audit_database)
    fixtures = (
        (
            "88487bca-11c6-4a7b-b82c-fdbecc3d0aed",
            "audit-session-archived",
            "Archived audit fixture",
        ),
        (
            "de0801c8-475b-4919-bf02-23931a94f3f6",
            "audit-session-current",
            "Current audit fixture",
        ),
        (
            "ecbeb21f-3607-42f3-8467-b2727369e8d1",
            "audit-session-missing",
            "Missing audit fixture",
        ),
        (
            "01d760de-5e23-424d-9b88-10d447a5be6d",
            "audit-session-error",
            "Failed audit fixture",
        ),
        (
            "f0bc165f-15af-492f-8a23-2230d1bfca8d",
            "audit-session-blocked",
            "Blocked audit fixture",
        ),
    )
    for task_id, session_id, title in fixtures:
        run_cli(
            cli,
            "register",
            "--id",
            task_id,
            "--session-id",
            session_id,
            "--kind",
            "main",
            "--project",
            "agtask-audit",
            "--title",
            title,
            "--initial-prompt",
            f"Task:\n{title}",
            "--description",
            title,
            "--status",
            "active",
            cwd=cwd,
            environment=audit_environment,
        )
    run_cli(
        cli,
        "status",
        "--id",
        fixtures[-1][0],
        "--status",
        "blocked",
        cwd=cwd,
        environment=audit_environment,
    )

    discovery = run_cli(
        cli, "audit", cwd=cwd, environment=audit_environment
    )
    expected_auditable_sessions = {fixture[1] for fixture in fixtures}
    require(
        discovery["phase"] == "lookup_required"
        and discovery["applied"] is False
        and discovery["plan_token"] is None,
        "audit discovery was not read-only lookup_required",
    )
    require(
        {task["session_id"] for task in discovery["active_tasks"]}
        == expected_auditable_sessions
        and {
            request["session_id"] for request in discovery["lookup_requests"]
        }
        == expected_auditable_sessions,
        "audit discovery did not request exactly the auditable real sessions",
    )

    observations = json.dumps(
        {
            "schema_version": 1,
            "sessions": [
                {"session_id": fixtures[0][1], "state": "archived"},
                {"session_id": fixtures[1][1], "state": "not_archived"},
                {"session_id": fixtures[2][1], "state": "missing"},
                {
                    "session_id": fixtures[3][1],
                    "state": "error",
                    "detail": "integration lookup unavailable",
                },
                {"session_id": fixtures[4][1], "state": "archived"},
                {"session_id": "audit-session-old", "state": "archived"},
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    before_plan = {
        task_id: query_thread(audit_database, task_id) for task_id, _, _ in fixtures
    }
    plan = run_cli(
        cli,
        "audit",
        "--observations-json",
        observations,
        cwd=cwd,
        environment=audit_environment,
    )
    after_plan = {
        task_id: query_thread(audit_database, task_id) for task_id, _, _ in fixtures
    }
    require(before_plan == after_plan, "audit planning changed ledger state")
    require(
        plan["phase"] == "confirmation_required"
        and plan["applied"] is False
        and [task["session_id"] for task in plan["affected_tasks"]]
        == [fixtures[0][1], fixtures[4][1]]
        and {
            (item["session_id"], item["lookup_state"])
            for item in plan["unresolved"]
        }
        == {(fixtures[2][1], "missing"), (fixtures[3][1], "error")}
        and plan["ignored_observations"] == ["audit-session-old"]
        and isinstance(plan["plan_token"], str)
        and len(plan["plan_token"]) == 64,
        "audit plan did not separate affected, unresolved, and ignored sessions",
    )
    require(
        "ask for explicit confirmation" in skill_text
        and "Do not treat silence, unavailable confirmation" in skill_text,
        "audit skill workflow does not enforce explicit confirmation",
    )

    applied = run_cli(
        cli,
        "audit",
        "--observations-json",
        observations,
        "--apply",
        plan["plan_token"],
        cwd=cwd,
        environment=audit_environment,
    )
    archived_thread = query_thread(audit_database, fixtures[0][0])
    archived_rollouts = query_rollouts(audit_database, fixtures[0][0])
    blocked_archived_thread = query_thread(audit_database, fixtures[4][0])
    blocked_archived_rollouts = query_rollouts(audit_database, fixtures[4][0])
    require(
        applied["phase"] == "complete"
        and applied["applied"] is True
        and archived_thread is not None
        and archived_thread["status"] == "done"
        and bool(archived_thread["closed"]),
        "confirmed audit did not archive the exact active candidate",
    )
    require(
        [row["message"] for row in archived_rollouts]
        == [
            "thread.created",
            "status:active->done",
            "archival:codex-thread-archived",
        ],
        "confirmed audit did not append the archive lifecycle evidence",
    )
    require(
        query_thread(audit_database, fixtures[1][0])["status"] == "active"
        and query_thread(audit_database, fixtures[2][0])["status"] == "active"
        and query_thread(audit_database, fixtures[3][0])["status"] == "active"
        and blocked_archived_thread is not None
        and blocked_archived_thread["status"] == "done"
        and bool(blocked_archived_thread["closed"]),
        "audit did not preserve unresolved tasks or close the blocked archive",
    )
    require(
        [row["message"] for row in blocked_archived_rollouts]
        == [
            "thread.created",
            "status:active->blocked",
            "status:blocked->done",
            "archival:codex-thread-archived",
        ],
        "confirmed audit did not retain blocked archive lifecycle evidence",
    )

    rerun = run_cli(
        cli,
        "audit",
        "--observations-json",
        observations,
        cwd=cwd,
        environment=audit_environment,
    )
    require(
        rerun["phase"] == "complete"
        and rerun["applied"] is False
        and rerun["affected_tasks"] == []
        and rerun["plan_token"] is None,
        "archive audit was not safe to rerun",
    )
    return {
        "scenario": AUDIT_SCENARIO_NAME,
        "scenario_version": AUDIT_SCENARIO_VERSION,
        "database": str(audit_database),
        "discovery": discovery,
        "plan": plan,
        "applied": applied,
        "archived_thread": archived_thread,
        "archived_rollouts": archived_rollouts,
        "blocked_archived_thread": blocked_archived_thread,
        "blocked_archived_rollouts": blocked_archived_rollouts,
        "rerun": rerun,
    }


def verify_current_task_add(
    cli: Path,
    proof_dir: Path,
    cwd: Path,
    environment: dict[str, str],
    workflow_text: str,
) -> dict[str, Any]:
    add_database = proof_dir / "add-ledger.db"
    add_environment = environment.copy()
    add_environment["AGTASK_DB"] = str(add_database)
    session_id = "add-session-current"
    project = "agtask-add"
    title = "Preserved current Codex title"
    initial_prompt = (
        "Implement direct current-task registration.\n"
        "Preserve this exact oldest prompt as CLI input."
    )
    expected_description = "Implement direct current-task registration."

    workflow_contract = {
        "reads_current_task": "`read_thread` for that exact task" in workflow_text,
        "omits_outputs": "`includeOutputs: false`" in workflow_text,
        "paginates_oldest": "`page.nextCursor`" in workflow_text
        and "oldest page" in workflow_text,
        "preserves_title": "returned `thread.title`" in workflow_text
        and "Do not derive or replace the title" in workflow_text,
        "exact_oldest_prompt": "exact `text` value" in workflow_text
        and "do not summarize" in workflow_text,
        "no_app_mutation": "does not create, fork,\nrename, pin, archive, or message"
        in workflow_text,
        "invokes_add": "python3 ./scripts/agtask add <project>" in workflow_text,
        "consumes_oncreate_here": "Consume each returned `OnCreate` prompt"
        in workflow_text
        and "current task" in workflow_text,
    }
    require(
        all(workflow_contract.values()),
        "canonical add workflow does not enforce current-task registration",
    )

    arguments = (
        "add",
        project,
        "--session-id",
        session_id,
        "--title",
        title,
        "--initial-prompt",
        initial_prompt,
    )
    created = run_cli(
        cli,
        *arguments,
        cwd=cwd,
        environment=add_environment,
    )
    parsed_id = uuid.UUID(created["id"])
    require(
        parsed_id.version == 4 and str(parsed_id) == created["id"],
        "add did not generate a canonical UUIDv4 logical ID",
    )
    require(
        created["session_id"] == session_id
        and created["parent_session_id"] is None
        and created["kind"] == "main"
        and created["project"] == project
        and created["title"] == title
        and created["description"] == expected_description
        and created["status"] == "active",
        "add created the wrong current-task snapshot",
    )
    require(
        [
            (row["role"], row["turn_id"], row["message"])
            for row in created["rollouts"]
        ]
        == [("meta", "thread.created", "thread.created")],
        "add did not create exactly one registration rollout",
    )

    retried = run_cli(
        cli,
        *arguments,
        cwd=cwd,
        environment=add_environment,
    )
    require(retried["id"] == created["id"], "add retry changed the logical ID")
    require(
        retried["rollouts"] == created["rollouts"],
        "add retry changed rollout history",
    )
    require(retried["hook_prompts"] == [], "add retry repeated OnCreate")

    conflict_errors: dict[str, str] = {}
    for label, conflict_arguments in {
        "project": (
            "add",
            "other-project",
            "--session-id",
            session_id,
            "--title",
            title,
            "--initial-prompt",
            initial_prompt,
        ),
        "title": (
            "add",
            project,
            "--session-id",
            session_id,
            "--title",
            "Changed current title",
            "--initial-prompt",
            initial_prompt,
        ),
        "description": (
            "add",
            project,
            "--session-id",
            session_id,
            "--title",
            title,
            "--initial-prompt",
            "A different oldest prompt.",
        ),
    }.items():
        completed = subprocess.run(
            [sys.executable, str(cli), *conflict_arguments, "--json"],
            cwd=cwd,
            env=add_environment,
            check=False,
            text=True,
            capture_output=True,
        )
        require(completed.returncode == 1, f"add accepted a {label} conflict")
        require(
            f"{label} conflict" in completed.stderr,
            f"add did not identify the {label} conflict",
        )
        conflict_errors[label] = completed.stderr.strip()

    child_id = "8e20f397-3f63-4924-81f5-74160dc73a72"
    child_session_id = "add-existing-child"
    child = run_cli(
        cli,
        "register",
        "--id",
        child_id,
        "--session-id",
        child_session_id,
        "--parent-session-id",
        "add-parent",
        "--kind",
        "child",
        "--project",
        project,
        "--title",
        "Existing child",
        "--initial-prompt",
        "Track an existing child.",
        cwd=cwd,
        environment=add_environment,
    )
    child_add = subprocess.run(
        [
            sys.executable,
            str(cli),
            "add",
            project,
            "--session-id",
            child_session_id,
            "--title",
            child["title"],
            "--initial-prompt",
            "Track an existing child.",
            "--json",
        ],
        cwd=cwd,
        env=add_environment,
        check=False,
        text=True,
        capture_output=True,
    )
    require(child_add.returncode == 1, "add accepted an existing child session")
    require(
        "cannot add existing child thread" in child_add.stderr,
        "add did not identify the existing child session",
    )
    final_thread = query_thread_by_session(add_database, session_id)
    require(final_thread is not None, "added current task disappeared")
    require(
        final_thread["id"] == created["id"]
        and final_thread["session_id"] == session_id
        and final_thread["parent_session_id"] is None
        and final_thread["kind"] == "main"
        and final_thread["project"] == project
        and final_thread["title"] == title
        and final_thread["description"] == expected_description
        and final_thread["status"] == "active"
        and final_thread["closed"] is None,
        "add conflict mutated the current task",
    )
    final_rollouts = query_rollouts(add_database, created["id"])
    require(
        final_rollouts == list(reversed(created["rollouts"])),
        "add conflict mutated rollout history",
    )

    return {
        "scenario": ADD_SCENARIO_NAME,
        "scenario_version": ADD_SCENARIO_VERSION,
        "database": str(add_database),
        "workflow_contract": workflow_contract,
        "created": created,
        "retried": retried,
        "conflict_errors": conflict_errors,
        "child_error": child_add.stderr.strip(),
        "final_thread": final_thread,
        "final_rollouts": final_rollouts,
    }


def verify_current_task_rename(
    cli: Path,
    proof_dir: Path,
    cwd: Path,
    environment: dict[str, str],
    workflow_text: str,
) -> dict[str, Any]:
    rename_database = proof_dir / "rename-ledger.db"
    rename_environment = environment.copy()
    rename_environment["AGTASK_DB"] = str(rename_database)
    task_id = "4d5af44d-cc27-4e28-ad52-b34a98a9934a"
    session_id = "rename-session-current"
    old_title = "agtask/rename-old"
    new_title = "agtask/rename-new"
    failed_title = "agtask/rename-app-failure"
    concurrent_title = "agtask/rename-concurrent"
    stale_title = "agtask/rename-stale"

    workflow_contract = {
        "current_session_only": "Rename only the current Codex task" in workflow_text
        and "not permission to rename another tracked task" in workflow_text,
        "validates_title": "nonempty, one-line" in workflow_text
        and "no surrounding whitespace" in workflow_text,
        "read_only_plan": "This first invocation is read-only" in workflow_text,
        "exact_returned_action": "Never synthesize or edit the action" in workflow_text,
        "app_before_apply": "Only after the app action succeeds" in workflow_text
        and "do not run the CLI rename" in workflow_text,
        "token_fenced_apply": "--apply <plan-token>" in workflow_text
        and "recomputes the token" in workflow_text,
        "rereads_after_failure": "If apply fails" in workflow_text
        and "immediately re-read" in workflow_text,
        "compensates_current_title": "row's *current* ledger title" in workflow_text
        and "Do not blindly restore" in workflow_text,
        "old_title_is_fallback": "only as the fallback" in workflow_text,
        "reports_divergence": "`title divergence`" in workflow_text
        and "re-read and compensation errors" in workflow_text,
    }
    require(
        all(workflow_contract.values()),
        "canonical rename workflow does not enforce the cross-store failure contract",
    )

    registered = run_cli(
        cli,
        "register",
        "--id",
        task_id,
        "--session-id",
        session_id,
        "--kind",
        "main",
        "--project",
        "agtask-rename",
        "--title",
        old_title,
        "--initial-prompt",
        "Task:\nExercise current-task rename.",
        "--description",
        "Exercise current-task rename.",
        "--status",
        "active",
        cwd=cwd,
        environment=rename_environment,
    )
    before = run_cli(
        cli,
        "show",
        "--session-id",
        session_id,
        cwd=cwd,
        environment=rename_environment,
    )
    require(
        registered["session_id"] == session_id
        and before["title"] == old_title,
        "rename fixture did not resolve the exact tracked current session",
    )

    operation_log: list[str] = []
    app_calls: list[dict[str, Any]] = []
    app_title = old_title

    def plan_title(title: str, label: str) -> dict[str, Any]:
        operation_log.append(f"plan:{label}")
        result = run_cli(
            cli,
            "rename",
            "--session-id",
            session_id,
            "--title",
            title,
            cwd=cwd,
            environment=rename_environment,
        )
        require(
            result["phase"] == "app_action_required"
            and result["plan_version"] == 2
            and result["applied"] is False
            and result["id"] == task_id
            and result["session_id"] == session_id
            and result["requested_title"] == title
            and isinstance(result["plan_token"], str)
            and len(result["plan_token"]) == 64,
            f"rename plan is malformed: {label}",
        )
        return result

    def fake_app_call(
        action: dict[str, Any], *, label: str, succeeds: bool
    ) -> bool:
        nonlocal app_title
        require(
            set(action) == {"tool", "arguments"}
            and action["tool"] == "codex_app__set_thread_title"
            and action["arguments"].get("threadId") == session_id
            and isinstance(action["arguments"].get("title"), str),
            f"rename plan emitted an invalid app action: {label}",
        )
        outcome = "succeeded" if succeeds else "failed"
        operation_log.append(f"app:{label}:{outcome}")
        app_calls.append(
            {
                "label": label,
                "outcome": outcome,
                "action": action,
            }
        )
        if succeeds:
            app_title = action["arguments"]["title"]
        return succeeds

    def apply_after_success(
        plan: dict[str, Any], *, label: str
    ) -> dict[str, Any]:
        require(
            app_calls
            and app_calls[-1]["outcome"] == "succeeded"
            and app_calls[-1]["action"] == plan["app_action"],
            f"rename apply did not follow its successful app action: {label}",
        )
        operation_log.append(f"apply:{label}")
        return run_cli(
            cli,
            "rename",
            "--session-id",
            session_id,
            "--title",
            plan["requested_title"],
            "--apply",
            plan["plan_token"],
            cwd=cwd,
            environment=rename_environment,
        )

    failed_plan = plan_title(failed_title, "app-failure")
    require(
        query_thread_by_session(rename_database, session_id)["title"] == old_title,
        "rename planning changed the ledger before the app action",
    )
    app_failed = fake_app_call(
        failed_plan["app_action"], label="app-failure", succeeds=False
    )
    require(not app_failed, "fake app failure unexpectedly succeeded")
    after_app_failure = run_cli(
        cli,
        "show",
        "--session-id",
        session_id,
        cwd=cwd,
        environment=rename_environment,
    )
    require(
        after_app_failure == before
        and not any(entry == "apply:app-failure" for entry in operation_log),
        "app failure applied or otherwise changed the ledger",
    )

    plan = plan_title(new_title, "success")
    repeated_plan = plan_title(new_title, "success-repeat")
    require(
        plan == repeated_plan and plan["current_title"] == old_title,
        "unchanged rename planning was not deterministic",
    )
    require(
        run_cli(
            cli,
            "show",
            "--session-id",
            session_id,
            cwd=cwd,
            environment=rename_environment,
        )
        == before,
        "rename planning mutated the ledger",
    )
    require(
        fake_app_call(plan["app_action"], label="success", succeeds=True),
        "fake app success failed",
    )
    renamed_result = apply_after_success(plan, label="success")
    renamed = renamed_result["thread"]
    rename_events = [
        row
        for row in renamed["rollouts"]
        if row["role"] == "meta" and row["message"] == "title:renamed"
    ]
    require(
        renamed_result["phase"] == "complete"
        and renamed_result["applied"] is True
        and renamed_result["changed"] is True
        and renamed["title"] == app_title
        and renamed["updated"] > before["updated"]
        and len(rename_events) == 1
        and rename_events[0]["created"] == renamed["updated"],
        "successful rename did not atomically update title, timestamp, and history",
    )
    require(
        run_cli(
            cli,
            "search",
            new_title,
            cwd=cwd,
            environment=rename_environment,
        )[0]["id"]
        == task_id
        and run_cli(
            cli,
            "search",
            old_title,
            cwd=cwd,
            environment=rename_environment,
        )
        == [],
        "successful rename did not refresh the FTS projection",
    )

    same_title_plan = plan_title(new_title, "same-title")
    require(
        same_title_plan["app_action"]["arguments"]["title"] == new_title,
        "same-title planning suppressed the idempotent app action",
    )
    require(
        fake_app_call(
            same_title_plan["app_action"], label="same-title", succeeds=True
        ),
        "same-title fake app call failed",
    )
    idempotent = apply_after_success(same_title_plan, label="same-title")
    require(
        idempotent["applied"] is True
        and idempotent["changed"] is False
        and idempotent["thread"]["updated"] == renamed["updated"]
        and idempotent["thread"]["rollouts"] == renamed["rollouts"],
        "idempotent rename changed timestamp or history",
    )
    invalid = subprocess.run(
        [
            sys.executable,
            str(cli),
            "rename",
            "--session-id",
            session_id,
            "--title",
            " invalid title ",
            "--json",
        ],
        cwd=cwd,
        env=rename_environment,
        check=False,
        text=True,
        capture_output=True,
    )
    after_invalid = run_cli(
        cli,
        "show",
        "--session-id",
        session_id,
        cwd=cwd,
        environment=rename_environment,
    )
    require(
        invalid.returncode != 0
        and "title must not contain surrounding whitespace" in invalid.stderr
        and after_invalid == idempotent["thread"],
        "invalid rename changed the ledger",
    )

    stale_plan = plan_title(stale_title, "stale")
    concurrent_plan = plan_title(concurrent_title, "concurrent")
    require(
        stale_plan["current_title"] == concurrent_plan["current_title"] == new_title,
        "overlapping rename plans did not start from the same row",
    )
    require(
        fake_app_call(stale_plan["app_action"], label="stale", succeeds=True),
        "stale fake app call failed",
    )
    require(
        fake_app_call(
            concurrent_plan["app_action"], label="concurrent", succeeds=True
        ),
        "concurrent fake app call failed",
    )
    concurrent_result = apply_after_success(concurrent_plan, label="concurrent")
    concurrent = concurrent_result["thread"]
    operation_log.append("apply:stale")
    stale = subprocess.run(
        [
            sys.executable,
            str(cli),
            "rename",
            "--session-id",
            session_id,
            "--title",
            stale_title,
            "--apply",
            stale_plan["plan_token"],
            "--json",
        ],
        cwd=cwd,
        env=rename_environment,
        check=False,
        text=True,
        capture_output=True,
    )
    require(
        stale.returncode != 0 and "stale rename plan" in stale.stderr,
        "stale rename token was not rejected",
    )
    current = run_cli(
        cli,
        "show",
        "--session-id",
        session_id,
        cwd=cwd,
        environment=rename_environment,
    )
    compensation_action = {
        "tool": "codex_app__set_thread_title",
        "arguments": {
            "threadId": session_id,
            "title": current["title"],
        },
    }
    require(
        fake_app_call(
            compensation_action, label="compensation", succeeds=True
        ),
        "compensation fake app call failed",
    )
    require(
        current == concurrent
        and current["title"] == concurrent_title
        and app_title == current["title"],
        "stale rename compensation did not converge on the current ledger title",
    )
    require(
        len(
            [
                row
                for row in current["rollouts"]
                if row["role"] == "meta" and row["message"] == "title:renamed"
            ]
        )
        == 2,
        "stale rename appended ledger history after the concurrent winner",
    )
    expected_order = (
        "plan:app-failure",
        "app:app-failure:failed",
        "plan:success",
        "app:success:succeeded",
        "apply:success",
        "app:stale:succeeded",
        "app:concurrent:succeeded",
        "apply:concurrent",
        "apply:stale",
        "app:compensation:succeeded",
    )
    require(
        all(
            operation_log.index(first) < operation_log.index(second)
            for first, second in zip(expected_order, expected_order[1:])
        ),
        "rename app/apply/compensation operations ran out of order",
    )
    return {
        "scenario": RENAME_SCENARIO_NAME,
        "scenario_version": RENAME_SCENARIO_VERSION,
        "database": str(rename_database),
        "workflow_contract": workflow_contract,
        "operation_log": operation_log,
        "app_calls": app_calls,
        "registered": registered,
        "failed_plan": failed_plan,
        "after_app_failure": after_app_failure,
        "plan": plan,
        "renamed": renamed_result,
        "idempotent": idempotent,
        "invalid_error": invalid.stderr.strip(),
        "stale_error": stale.stderr.strip(),
        "compensation_target": current["title"],
        "final_thread": current,
        "rename_events": [
            row
            for row in current["rollouts"]
            if row["role"] == "meta" and row["message"] == "title:renamed"
        ],
    }


def main() -> int:
    args = parse_args()
    source = args.source.expanduser().resolve()
    proof_dir = args.proof_dir.expanduser().resolve()
    proof_dir.mkdir(parents=True, exist_ok=True)
    parent_session_id = (
        os.environ.get("INTEG_PARENT_THREAD_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or os.environ.get("SESSION_ID")
    )
    if not parent_session_id:
        raise RuntimeError(
            "set INTEG_PARENT_THREAD_ID to the invoking Codex session ID"
        )
    main_thread_id = str(uuid.uuid4())
    child_thread_id = str(uuid.uuid4())

    codex = resolve_codex()
    cli = resolve_cli()
    database = configure_database(proof_dir)
    live_home = proof_dir / "live-home"
    live_project = proof_dir / "live-project"
    live_home.mkdir(parents=True, exist_ok=True)
    live_project.mkdir(parents=True, exist_ok=True)
    live_home_config = live_home / ".agtask.json"
    live_project_config = live_project / ".agtask.json"
    title = f"{TITLE}-{proof_dir.name}"
    live_trailer = (
        '<agtask-bootstrap version="2">\n'
        + json.dumps(
            {
                "id": child_thread_id,
                "parent_session_id": parent_session_id,
                "pin": False,
                "project": PROJECT,
                "title": title,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n</agtask-bootstrap>"
    )
    live_prompt = DIRECTIVE + "\n\n" + live_trailer
    live_delegated_prompt = f"""<codex_delegation>
  <source_thread_id>{html.escape(parent_session_id, quote=False)}</source_thread_id>
  <input>{html.escape(live_prompt, quote=False)}
</input>
</codex_delegation>"""
    live_home_config.write_text(
        json.dumps(
            {
                "defaults": {},
                "hooks": {
                    "OnPreClose": {"prompt": PRE_CLOSE_DIRECTIVE},
                    "OnPostClose": {"prompt": POST_CLOSE_DIRECTIVE},
                },
            },
            indent=2,
        )
        + "\n"
    )
    live_project_config.write_text(
        json.dumps(
            {
                "defaults": {"project": PROJECT},
                "hooks": {"OnCreate": {"prompt": DIRECTIVE}},
            },
            indent=2,
        )
        + "\n"
    )
    live_environment = os.environ.copy()
    live_environment["HOME"] = str(live_home)
    live_environment["AGTASK_DB"] = str(database)
    source_skill = source / "skills/agtask/SKILL.md"
    source_cli = source / "skills/agtask/scripts/agtask"
    installed_skill = cli.parent.parent / "SKILL.md"
    require(source_skill.is_file(), f"source agtask skill not found: {source_skill}")
    require(source_cli.is_file(), f"source agtask CLI not found: {source_cli}")
    require(
        installed_skill.is_file(), f"installed agtask skill not found: {installed_skill}"
    )
    require(
        installed_skill.read_bytes() == source_skill.read_bytes(),
        "installed agtask SKILL.md differs from the current source checkout",
    )
    require(
        cli.read_bytes() == source_cli.read_bytes(),
        "installed agtask CLI differs from the current source checkout",
    )
    source_references = source_skill.parent / "references"
    installed_references = installed_skill.parent / "references"
    for reference_name in (
        "add.md",
        "create.md",
        "audit.md",
        "rename.md",
        "close.md",
        "onclose.md",
    ):
        source_reference = source_references / reference_name
        installed_reference = installed_references / reference_name
        require(
            source_reference.is_file(),
            f"source agtask reference not found: {source_reference}",
        )
        require(
            installed_reference.is_file(),
            f"installed agtask reference not found: {installed_reference}",
        )
        require(
            installed_reference.read_bytes() == source_reference.read_bytes(),
            f"installed agtask reference differs from source: {reference_name}",
        )
    creation_workflow_text = (source_references / "create.md").read_text()
    add_workflow_text = (source_references / "add.md").read_text()
    audit_workflow_text = (source_references / "audit.md").read_text()
    rename_workflow_text = (source_references / "rename.md").read_text()
    main_contract = {
        "scenario": MAIN_SCENARIO_NAME,
        "scenario_version": MAIN_SCENARIO_VERSION,
        "targets_invoking_session": "invoking session ID as\n   the Codex target"
        in creation_workflow_text,
        "preserves_logical_id": "resolver's `id` as the logical task ID"
        in creation_workflow_text,
        "prohibits_new_thread": "do not call `create_thread`, `fork_thread`, or"
        in creation_workflow_text
        and "`send_message_to_thread`" in creation_workflow_text,
        "pins_invoking_thread": "Apply the resolved pin input to the invoking thread"
        in creation_workflow_text,
        "derives_description_from_initial_prompt": "as `--initial-prompt`"
        in creation_workflow_text
        and "sole source of\n  the task description" in creation_workflow_text,
        "default_title": MAIN_TITLE,
    }
    require(
        all(
            main_contract[key]
            for key in (
                "targets_invoking_session",
                "preserves_logical_id",
                "prohibits_new_thread",
                "pins_invoking_thread",
                "derives_description_from_initial_prompt",
            )
        ),
        "canonical skill does not enforce current-thread main designation",
    )
    app_environment = os.environ.copy()
    app_environment["AGTASK_DB"] = str(proof_dir / "host-hooks-unused.db")
    process = subprocess.Popen(
        [str(codex), "app-server", "--stdio"],
        cwd=source,
        env=app_environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    app_output: queue.Queue[tuple[str, str]] = queue.Queue()

    def read_app_stream(kind: str, stream: Any) -> None:
        for line in stream:
            app_output.put((kind, line))

    for kind, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        threading.Thread(
            target=read_app_stream,
            args=(kind, stream),
            daemon=True,
        ).start()
    messages: list[dict[str, Any]] = []
    stderr: list[str] = []
    session_id: str | None = None
    merge_token: str | None = None
    result: dict[str, Any] = {
        "source": str(source),
        "source_revision": source_revision(source),
        "main_thread_id": main_thread_id,
        "parent_session_id": parent_session_id,
        "thread_id": child_thread_id,
        "database": str(database),
        "codex": str(codex),
        "cli": str(cli),
        "scenario_manifest": scenario_metadata(source),
        "main_contract": main_contract,
    }
    result["configuration"] = verify_layered_configuration(cli, proof_dir)
    result["live_configuration"] = {
        "home": str(live_home_config.resolve()),
        "project": str(live_project_config.resolve()),
    }
    main_result = run_cli(
        cli,
        "register",
        "--id",
        main_thread_id,
        "--session-id",
        parent_session_id,
        "--kind",
        "main",
        "--project",
        PROJECT,
        "--title",
        MAIN_TITLE,
        "--initial-prompt",
        MAIN_INITIAL_PROMPT,
        "--description",
        MAIN_DESCRIPTION,
        "--status",
        "active",
        cwd=live_project,
        environment=live_environment,
    )
    require(main_result["id"] == main_thread_id, "main JSON has the wrong task ID")
    require(
        main_result["session_id"] == parent_session_id,
        "main JSON has the wrong session ID",
    )
    require(main_result["parent_session_id"] is None, "main thread has a parent")
    require(main_result["kind"] == "main", "main JSON has the wrong kind")
    require(main_result["project"] == PROJECT, "main JSON has the wrong project")
    require(main_result["title"] == MAIN_TITLE, "main JSON has the wrong default title")
    result["main"] = main_result
    result["bootstrap_protocol"] = verify_bootstrap_protocol(
        cli,
        database,
        live_project,
        live_environment,
    )
    result["creation_identity_regression"] = verify_creation_identity_regression(
        cli,
        database,
        live_project,
        live_environment,
    )
    result["current_task_add"] = verify_current_task_add(
        cli,
        proof_dir,
        live_project,
        live_environment,
        add_workflow_text,
    )
    result["archived_session_audit"] = verify_archived_session_audit(
        cli,
        proof_dir,
        live_project,
        live_environment,
        audit_workflow_text,
    )
    result["current_task_rename"] = verify_current_task_rename(
        cli,
        proof_dir,
        live_project,
        live_environment,
        rename_workflow_text,
    )

    def send(message: dict[str, Any]) -> None:
        try:
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except BrokenPipeError as error:
            process.wait(timeout=5)
            remaining_stderr = process.stderr.read().strip()
            raise RuntimeError(
                f"app-server closed stdin before request; exit={process.returncode}; "
                f"stderr={remaining_stderr or '<empty>'}"
            ) from error

    def pump_until(predicate: Callable[[], bool], deadline: float) -> None:
        while time.monotonic() < deadline:
            if predicate():
                return
            try:
                kind, line = app_output.get(timeout=0.25)
            except queue.Empty:
                kind = line = ""
            if kind == "stderr":
                stderr.append(line.rstrip())
            elif kind == "stdout":
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    stderr.append("non-JSON stdout: " + line.rstrip())
            if process.poll() is not None and not predicate():
                raise RuntimeError(f"app-server exited with {process.returncode}")
        raise TimeoutError("timed out waiting for lifecycle condition")

    def response(request_id: int) -> dict[str, Any] | None:
        return next(
            (message for message in messages if message.get("id") == request_id),
            None,
        )

    def turn_completed(turn_id: str) -> bool:
        return any(
            message.get("method") == "turn/completed"
            and message.get("params", {}).get("turn", {}).get("id") == turn_id
            for message in messages
        )

    def assistant_message_since(start_index: int) -> str:
        values = [
            message.get("params", {}).get("item", {}).get("text")
            for message in messages[start_index:]
            if message.get("method") == "item/completed"
            and message.get("params", {}).get("item", {}).get("type")
            in {"agentMessage", "agent_message"}
        ]
        text_values = [value for value in values if isinstance(value, str)]
        require(bool(text_values), "app-server turn did not emit an assistant message")
        return text_values[-1]

    try:
        deadline = time.monotonic() + args.timeout
        send(
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "agtask_integ",
                        "title": "agtask integration harness",
                        "version": "1.0.0",
                    }
                },
            }
        )
        pump_until(lambda: response(0) is not None, deadline)
        send({"method": "initialized", "params": {}})
        send(
            {
                "method": "thread/start",
                "id": 1,
                "params": {"cwd": str(source)},
            }
        )
        pump_until(lambda: response(1) is not None, deadline)
        start_response = response(1) or {}
        if "error" in start_response:
            raise RuntimeError(f"thread/start failed: {start_response['error']}")
        session_id = start_response.get("result", {}).get("thread", {}).get("id")
        require(isinstance(session_id, str) and bool(session_id), "missing session ID")
        result["session_id"] = session_id

        directive_message_start = len(messages)
        send(
            {
                "method": "turn/start",
                "id": 2,
                "params": {
                    "threadId": session_id,
                    "input": [
                        {
                            "type": "text",
                            "text": live_delegated_prompt,
                        }
                    ],
                },
            }
        )
        pump_until(lambda: response(2) is not None, deadline)
        turn_response = response(2) or {}
        if "error" in turn_response:
            raise RuntimeError(f"turn/start failed: {turn_response['error']}")
        turn_id = turn_response.get("result", {}).get("turn", {}).get("id")
        require(isinstance(turn_id, str) and bool(turn_id), "missing turn ID")
        result["turn_id"] = turn_id
        hook_output = run_hook(
            cli,
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": turn_id,
                "prompt": live_delegated_prompt,
            },
            cwd=live_project,
            environment=live_environment,
        )
        hook_document = json.loads(hook_output)
        hook_context = hook_document["hookSpecificOutput"]["additionalContext"]
        require(
            "codex_app__set_thread_title" in hook_context
            and "codex_app__set_thread_pinned" not in hook_context,
            "creation bootstrap did not render the expected child actions",
        )
        created_thread = query_thread(database, child_thread_id)
        created_rollouts = query_rollouts(database, child_thread_id)
        require(created_thread is not None, "creation hook did not register the thread")
        require(
            created_thread["id"] == child_thread_id
            and created_thread["session_id"] == session_id
            and created_thread["parent_session_id"] == parent_session_id
            and created_thread["kind"] == "child"
            and created_thread["project"] == PROJECT
            and created_thread["title"] == title,
            "creation hook registered the wrong identity",
        )
        require(
            created_thread["description"] == DIRECTIVE
            and created_thread["status"] == "active"
            and created_thread["closed"] is None,
            "creation hook registered the wrong initial state",
        )
        require(
            [(row["role"], row["turn_id"], row["message"]) for row in created_rollouts]
            == [
                ("meta", "thread.created", "thread.created"),
                ("user", turn_id, DIRECTIVE),
            ],
            "creation hook did not atomically retain the real first user turn",
        )
        result["hook_first"] = {
            "scenario": CREATION_BOOTSTRAP_SCENARIO_NAME,
            "scenario_version": CREATION_BOOTSTRAP_SCENARIO_VERSION,
            "hook_output": hook_document,
            "transport": "codex_delegation with one XML entity layer",
            "thread": created_thread,
            "rollouts": created_rollouts,
        }

        register_result = run_cli(
            cli,
            "register",
            "--id",
            child_thread_id,
            "--session-id",
            session_id,
            "--parent-session-id",
            parent_session_id,
            "--kind",
            "child",
            "--project",
            PROJECT,
            "--title",
            title,
            "--initial-prompt",
            live_delegated_prompt,
            "--description",
            DIRECTIVE,
            "--status",
            "active",
            cwd=live_project,
            environment=live_environment,
        )
        require(register_result["hook_prompts"] == [], "register retry repeated OnCreate")
        require(
            register_result["rollouts"] == list(reversed(created_rollouts)),
            "register retry changed hook-first rollout history",
        )

        bootstrap_result = run_cli(
            cli,
            "record-turn",
            "--id",
            child_thread_id,
            "--role",
            "user",
            "--turn-id",
            "bootstrap",
            "--content",
            live_delegated_prompt,
            cwd=live_project,
            environment=live_environment,
        )
        bootstrap_user_rows = [
            row for row in bootstrap_result["rollouts"] if row["role"] == "user"
        ]
        require(
            len(bootstrap_user_rows) == 1
            and bootstrap_user_rows[0]["message"] == DIRECTIVE,
            "bootstrap JSON does not prove exactly one normalized user rollout",
        )
        require(
            bootstrap_result["description"] == DIRECTIVE,
            "bootstrap JSON did not preserve the initial-prompt description",
        )
        require(bootstrap_result["status"] == "active", "bootstrap JSON is not active")
        require(
            bootstrap_result["rollouts"] == list(reversed(created_rollouts)),
            "bootstrap fallback duplicated the hook-owned first turn",
        )
        result["parent_reconciliation"] = {
            "register_result": register_result,
            "bootstrap_result": bootstrap_result,
        }

        pump_until(lambda: turn_completed(turn_id), deadline)
        directive_assistant = assistant_message_since(directive_message_start)
        directive_lines = [line.strip() for line in directive_assistant.splitlines() if line.strip()]
        require(
            bool(directive_lines)
            and directive_lines[0] == "INTEG_LIFECYCLE_READY"
            and all(
                line.startswith(("Title:", "Pin:")) for line in directive_lines[1:]
            ),
            "app-server returned the wrong directive response",
        )
        directive_summary = " ".join(directive_lines)
        run_hook(
            cli,
            {
                "hook_event_name": "Stop",
                "session_id": session_id,
                "turn_id": turn_id,
                "last_assistant_message": directive_assistant,
            },
            cwd=live_project,
            environment=live_environment,
        )

        def directive_persisted() -> bool:
            rows = query_rollouts(database, child_thread_id)
            roles = {
                row["role"]
                for row in rows
                if row["turn_id"] == turn_id
                and row["role"] in {"user", "assistant"}
            }
            return roles == {"user", "assistant"}

        pump_until(directive_persisted, deadline)
        directive_thread = query_thread(database, child_thread_id)
        directive_rollouts = query_rollouts(database, child_thread_id)
        require(directive_thread is not None, "thread vanished after directive")
        require(directive_thread["status"] == "active", "directive did not activate thread")
        require(
            directive_thread["description"] == DIRECTIVE,
            "assistant directive response replaced the initial-prompt description",
        )
        turn_rows = [row for row in directive_rollouts if row["turn_id"] == turn_id]
        require(
            [(row["role"], row["message"]) for row in turn_rows]
            == [
                ("user", DIRECTIVE),
                ("assistant", directive_summary),
            ],
            "directive rollouts do not match user and assistant results",
        )
        require(
            directive_rollouts[: len(created_rollouts)] == created_rollouts,
            "directive checkpoint changed the creation rollout history",
        )
        require(
            sum(
                row["role"] == "meta" and row["message"] == "status:todo->active"
                for row in directive_rollouts
            )
            == 0,
            "hook-first active registration created a synthetic todo transition",
        )
        result["directive"] = {
            "thread": directive_thread,
            "rollouts": directive_rollouts,
        }

        prepared = run_cli(
            cli,
            "close",
            "--session-id",
            session_id,
            "--prepare",
            "--if-tracked",
            cwd=live_project,
            environment=live_environment,
        )
        prepared_thread = query_thread(database, child_thread_id)
        prepared_rollouts = query_rollouts(database, child_thread_id)
        prepared_claim = query_merge_claim(database, PROJECT)
        require(
            prepared_thread == directive_thread | {"status": "merging"},
            "close preparation did not project merging ownership",
        )
        require(
            prepared_rollouts[: len(directive_rollouts)] == directive_rollouts
            and len(prepared_rollouts) == len(directive_rollouts) + 1
            and prepared_rollouts[-1]["role"] == "meta"
            and prepared_rollouts[-1]["message"] == "status:active->merging",
            "close preparation did not append the merge transition",
        )
        require(
            prepared["merge_claim"]["state"] == "claimed"
            and prepared["merge_claim"]["owner_thread_id"] == child_thread_id
            and isinstance(prepared["merge_claim"].get("token"), str)
            and bool(prepared["merge_claim"]["token"]),
            "close preparation did not return an owned fencing token",
        )
        merge_token = prepared["merge_claim"]["token"]
        require(
            prepared_claim is not None
            and prepared_claim["owner_thread_id"] == child_thread_id
            and prepared_claim["token"] == merge_token
            and prepared_claim["prior_status"] == "active",
            "SQLite does not contain the prepared project claim",
        )
        require(
            prepared["hook_prompts"]
            == [
                {
                    "event": "OnPreClose",
                    "prompt": PRE_CLOSE_DIRECTIVE,
                    "source": str(live_home_config.resolve()),
                }
            ],
            "close preparation did not surface the configured OnPreClose prompt",
        )
        result["prepare_close"] = {
            "command_result": prepared
            | {"merge_claim": prepared["merge_claim"] | {"token": "[redacted]"}},
            "thread": prepared_thread,
            "rollouts": prepared_rollouts,
        }
        pre_close_message_start = len(messages)
        send(
            {
                "method": "turn/start",
                "id": 3,
                "params": {
                    "threadId": session_id,
                    "input": [
                        {
                            "type": "text",
                            "text": prepared["hook_prompts"][0]["prompt"],
                        }
                    ],
                },
            }
        )
        pump_until(lambda: response(3) is not None, deadline)
        pre_close_turn_response = response(3) or {}
        if "error" in pre_close_turn_response:
            raise RuntimeError(
                f"OnPreClose turn/start failed: {pre_close_turn_response['error']}"
            )
        pre_close_turn_id = (
            pre_close_turn_response.get("result", {}).get("turn", {}).get("id")
        )
        require(
            isinstance(pre_close_turn_id, str) and bool(pre_close_turn_id),
            "missing OnPreClose turn ID",
        )
        run_hook(
            cli,
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": pre_close_turn_id,
                "prompt": PRE_CLOSE_DIRECTIVE,
            },
            cwd=live_project,
            environment=live_environment,
        )
        pump_until(lambda: turn_completed(pre_close_turn_id), deadline)
        pre_close_assistant = assistant_message_since(pre_close_message_start)
        require(
            pre_close_assistant == "INTEG_PRE_CLOSE_READY",
            "app-server returned the wrong OnPreClose response",
        )
        run_hook(
            cli,
            {
                "hook_event_name": "Stop",
                "session_id": session_id,
                "turn_id": pre_close_turn_id,
                "last_assistant_message": pre_close_assistant,
            },
            cwd=live_project,
            environment=live_environment,
        )

        def pre_close_directive_persisted() -> bool:
            rows = query_rollouts(database, child_thread_id)
            roles = {
                row["role"]
                for row in rows
                if row["turn_id"] == pre_close_turn_id
                and row["role"] in {"user", "assistant"}
            }
            return roles == {"user", "assistant"}

        pump_until(pre_close_directive_persisted, deadline)
        pre_close_thread = query_thread(database, child_thread_id)
        pre_close_rollouts = query_rollouts(database, child_thread_id)
        require(pre_close_thread is not None, "thread vanished after OnPreClose delivery")
        require(
            pre_close_thread["status"] == "merging"
            and pre_close_thread["closed"] is None,
            "OnPreClose delivery changed the thread lifecycle",
        )
        require(
            pre_close_rollouts[: len(prepared_rollouts)] == prepared_rollouts,
            "OnPreClose delivery changed the prepared rollout history",
        )
        pre_close_rows = [
            row for row in pre_close_rollouts if row["turn_id"] == pre_close_turn_id
        ]
        require(
            [(row["role"], row["message"]) for row in pre_close_rows]
            == [
                ("user", PRE_CLOSE_DIRECTIVE),
                ("assistant", "INTEG_PRE_CLOSE_READY"),
            ],
            "OnPreClose orchestration did not produce the expected agent turn",
        )
        result["pre_close_delivery"] = {
            "turn_id": pre_close_turn_id,
            "thread": pre_close_thread,
            "rollouts": pre_close_rollouts,
        }

        heartbeat = run_cli(
            cli,
            "close",
            "--id",
            child_thread_id,
            "--heartbeat",
            "--merge-token",
            merge_token,
            cwd=live_project,
            environment=live_environment,
        )
        heartbeat_claim = query_merge_claim(database, PROJECT)
        require(
            heartbeat["status"] == "merging"
            and heartbeat["hook_prompts"] == []
            and heartbeat["merge_claim"]["state"] == "claimed"
            and heartbeat["merge_claim"]["token"] == merge_token,
            "merge heartbeat did not preserve ownership",
        )
        require(
            heartbeat_claim is not None
            and heartbeat_claim["token"] == merge_token
            and heartbeat_claim["heartbeat"] >= prepared_claim["heartbeat"],
            "merge heartbeat did not renew the SQLite claim",
        )

        closed = run_cli(
            cli,
            "close",
            "--session-id",
            session_id,
            "--if-tracked",
            "--merge-token",
            merge_token,
            cwd=live_project,
            environment=live_environment,
        )
        closed_thread = query_thread(database, child_thread_id)
        closed_rollouts = query_rollouts(database, child_thread_id)
        require(closed_thread is not None, "thread vanished after close")
        require(closed_thread["status"] == "done", "close did not mark thread done")
        require(bool(closed_thread["closed"]), "close did not set closed")
        require(
            closed_thread["description"] == DIRECTIVE,
            "close checkpoint changed the initial-prompt description",
        )
        require(
            closed_rollouts[: len(pre_close_rollouts)] == pre_close_rollouts,
            "close changed rollout rows that existed before finalization",
        )
        close_rows = [
            row
            for row in closed_rollouts
            if row["created"] == closed_thread["closed"]
            and row["role"] == "meta"
            and row["message"]
            in {"status:merging->done", "finalization:completed"}
        ]
        require(
            [row["message"] for row in close_rows]
            == ["status:merging->done", "finalization:completed"],
            "close rollouts do not match the canonical pair",
        )
        require(
            len({row["turn_id"] for row in close_rows}) == 2
            and all(row["turn_id"] for row in close_rows),
            "close rollouts do not have distinct nonempty event IDs",
        )
        require(
            min(row["id"] for row in close_rows)
            > max(row["id"] for row in pre_close_rollouts),
            "close rollout IDs are not newer than pre-close history",
        )
        require(
            len(closed_rollouts) == len(pre_close_rollouts) + 2,
            "close appended an unexpected number of rollout rows",
        )
        require(
            query_merge_claim(database, PROJECT) is None,
            "close did not delete the project merge claim",
        )
        require(
            closed["hook_prompts"]
            == [
                {
                    "event": "OnPostClose",
                    "prompt": POST_CLOSE_DIRECTIVE,
                    "source": str(live_home_config.resolve()),
                }
            ],
            "close JSON did not surface the configured OnPostClose prompt",
        )
        require(
            all(row["message"] != POST_CLOSE_DIRECTIVE for row in closed_rollouts),
            "OnPostClose prompt was persisted as a rollout",
        )
        result["close"] = {
            "command_result": closed,
            "thread": closed_thread,
            "close_rollouts": close_rows,
            "rollouts": closed_rollouts,
        }
        post_close_message_start = len(messages)
        send(
            {
                "method": "turn/start",
                "id": 4,
                "params": {
                    "threadId": session_id,
                    "input": [
                        {
                            "type": "text",
                            "text": closed["hook_prompts"][0]["prompt"],
                        }
                    ],
                },
            }
        )
        pump_until(lambda: response(4) is not None, deadline)
        post_close_turn_response = response(4) or {}
        if "error" in post_close_turn_response:
            raise RuntimeError(
                f"OnPostClose turn/start failed: {post_close_turn_response['error']}"
            )
        post_close_turn_id = (
            post_close_turn_response.get("result", {}).get("turn", {}).get("id")
        )
        require(
            isinstance(post_close_turn_id, str) and bool(post_close_turn_id),
            "missing OnPostClose turn ID",
        )
        run_hook(
            cli,
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": post_close_turn_id,
                "prompt": POST_CLOSE_DIRECTIVE,
            },
            cwd=live_project,
            environment=live_environment,
        )
        pump_until(lambda: turn_completed(post_close_turn_id), deadline)
        post_close_assistant = assistant_message_since(post_close_message_start)
        require(
            post_close_assistant == "INTEG_POST_CLOSE_READY",
            "app-server returned the wrong OnPostClose response",
        )
        run_hook(
            cli,
            {
                "hook_event_name": "Stop",
                "session_id": session_id,
                "turn_id": post_close_turn_id,
                "last_assistant_message": post_close_assistant,
            },
            cwd=live_project,
            environment=live_environment,
        )

        def post_close_directive_persisted() -> bool:
            rows = query_rollouts(database, child_thread_id)
            roles = {
                row["role"]
                for row in rows
                if row["turn_id"] == post_close_turn_id
                and row["role"] in {"user", "assistant"}
            }
            return roles == {"user", "assistant"}

        pump_until(post_close_directive_persisted, deadline)
        delivered_thread = query_thread(database, child_thread_id)
        delivered_rollouts = query_rollouts(database, child_thread_id)
        require(delivered_thread is not None, "thread vanished after OnPostClose delivery")
        require(
            delivered_thread["status"] == "done"
            and delivered_thread["closed"] == closed_thread["closed"],
            "OnPostClose delivery changed the completed thread lifecycle",
        )
        require(
            delivered_thread["description"] == DIRECTIVE,
            "OnPostClose delivery replaced the initial-prompt description",
        )
        require(
            delivered_rollouts[: len(closed_rollouts)] == closed_rollouts,
            "OnPostClose delivery changed the finalized rollout history",
        )
        delivered_rows = [
            row for row in delivered_rollouts if row["turn_id"] == post_close_turn_id
        ]
        require(
            [(row["role"], row["message"]) for row in delivered_rows]
            == [
                ("user", POST_CLOSE_DIRECTIVE),
                ("assistant", "INTEG_POST_CLOSE_READY"),
            ],
            "OnPostClose orchestration did not produce the expected agent turn",
        )
        result["post_close_delivery"] = {
            "turn_id": post_close_turn_id,
            "thread": delivered_thread,
            "rollouts": delivered_rollouts,
        }
        result["dashboard"] = verify_dashboard(
            cli,
            database,
            main_thread_id,
            parent_session_id,
            child_thread_id,
            session_id,
            title,
            delivered_thread,
        )
        result["status"] = "passed"
        result["stderr_tail"] = stderr[-20:]
        (proof_dir / "lifecycle.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        if process.poll() is not None:
            remainder = process.stderr.read()
            if remainder:
                stderr.extend(remainder.splitlines())
        result["status"] = "failed"
        result["error"] = str(error)
        result["stderr_tail"] = stderr[-20:]
        (proof_dir / "lifecycle.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        if session_id and merge_token and query_merge_claim(database, PROJECT):
            try:
                run_cli(
                    cli,
                    "close",
                    "--session-id",
                    session_id,
                    "--cancel",
                    "--merge-token",
                    merge_token,
                    cwd=live_project,
                    environment=live_environment,
                )
            except Exception:
                pass
        raise
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"test_lifecycle: {error}", file=sys.stderr)
        raise SystemExit(1)

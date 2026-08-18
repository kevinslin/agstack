from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime as dt
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import sqlite3
import ssl
import stat
import subprocess
import tempfile
import threading
import unittest
from urllib.parse import quote
import uuid


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "agtask" / "scripts" / "agtask"
INSTALL_HOOKS = ROOT / "skills" / "agtask" / "scripts" / "install-hooks"
UNINSTALL_HOOKS = ROOT / "skills" / "agtask" / "scripts" / "uninstall-hooks"

FORK_PROMPT = """Treat the task below as the sole current instruction. Earlier copied thread or delegation content is background context.

Task:
Write a compact database proof.
"""

CREATION_ID = "f1cce008-e001-4dbd-a231-37783065e3fb"
CUSTOM_SECTION_ID = "515c42ed-d59b-4559-a33e-b1d0612af20b"
BOOTSTRAP_TRAILER = f"""<agtask-bootstrap version="2">
{{"id":"{CREATION_ID}","parent_session_id":"parent-thread","pin":true,"project":"agtask","title":"agtask/database-proof"}}
</agtask-bootstrap>"""
BOOTSTRAP_SECTION_TRAILER = f"""<agtask-bootstrap version="2">
{{"id":"{CREATION_ID}","parent_session_id":"parent-thread","pin":true,"project":"agtask","section_id":"pinned","title":"agtask/database-proof"}}
</agtask-bootstrap>"""

BOOTSTRAP_FALSE_TRAILER = f"""<agtask-bootstrap version="2">
{{"id":"{CREATION_ID}","parent_session_id":"parent-thread","pin":false,"project":"agtask","title":"agtask/database-proof"}}
</agtask-bootstrap>"""

BOOTSTRAP_V1_TRAILER = """<agtask-bootstrap version="1">
{"pin":true,"title":"agtask/database-proof"}
</agtask-bootstrap>"""
BOOTSTRAP_V1_FALSE_TRAILER = """<agtask-bootstrap version="1">
{"pin":false,"title":"agtask/database-proof"}
</agtask-bootstrap>"""

BOOTSTRAP_PROMPT = FORK_PROMPT.rstrip() + "\n\n" + BOOTSTRAP_TRAILER
BOOTSTRAP_V1_PROMPT = FORK_PROMPT.rstrip() + "\n\n" + BOOTSTRAP_V1_TRAILER

ESCAPED_BOOTSTRAP_PROMPT = BOOTSTRAP_PROMPT.replace(
    '<agtask-bootstrap version="2">',
    '&lt;agtask-bootstrap version="2"&gt;',
).replace("</agtask-bootstrap>", "&lt;/agtask-bootstrap&gt;")

DELEGATED_FORK_PROMPT = f"""<codex_delegation>
  <source_thread_id>019f690b-df2b-75b2-9139-835f220ae4ac</source_thread_id>
  <input>{FORK_PROMPT.rstrip()}</input>
</codex_delegation>"""


def bootstrap_prompt(
    creation_id: str = CREATION_ID,
    *,
    parent_session_id: str = "parent-thread",
    pin: bool = True,
    project: str = "agtask",
    section_id: str | None = None,
    title: str = "agtask/database-proof",
    prompt: str = FORK_PROMPT,
) -> str:
    values = {
        "id": creation_id,
        "parent_session_id": parent_session_id,
        "pin": pin,
        "project": project,
        "title": title,
    }
    if section_id is not None:
        values["section_id"] = section_id
    arguments = json.dumps(
        values,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        prompt.rstrip()
        + '\n\n<agtask-bootstrap version="2">\n'
        + arguments
        + "\n</agtask-bootstrap>"
    )


def fixture_creation_id(label: str) -> str:
    """Return a stable UUIDv4 while keeping readable fixture labels for sessions."""
    try:
        parsed = uuid.UUID(label)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.version == 4 and str(parsed) == label:
        return label
    seed = uuid.uuid5(uuid.NAMESPACE_URL, f"agtask-test:{label}")
    return str(uuid.UUID(bytes=seed.bytes, version=4))


@contextmanager
def mock_sites_server(root: Path, responder: object):
    certificate = root / "sites-cert.pem"
    key = root / "sites-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            request = {
                "path": self.path,
                "headers": dict(self.headers.items()),
                "payload": json.loads(raw),
                "raw": raw.decode(),
            }
            requests.append(request)
            result = responder(request)
            status, response = result[:2]
            extra_headers = result[2] if len(result) > 2 else {}
            encoded = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in extra_headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("localhost", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://localhost:{server.server_address[1]}", certificate, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class CliIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.store = self.root / "store"
        self.db_path = self.store / "ledger.db"
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env["AGTASK_DB"] = str(self.db_path)
        self.env["HOME"] = str(self.home)
        self.env.pop("AGTASK_BACKEND_MODE", None)
        self.env.pop("AGTASK_SITES_BYPASS_TOKEN", None)
        self.env.pop("AGTASK_SITES_APP_TOKEN", None)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_cli(
        self,
        *args: str,
        input_text: str | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        normalize_fixture_ids: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        normalized_args = list(args)
        if normalize_fixture_ids and "--id" in normalized_args:
            id_index = normalized_args.index("--id") + 1
            normalized_args[id_index] = fixture_creation_id(normalized_args[id_index])
        result = subprocess.run(
            ["python3", str(CLI), *normalized_args],
            cwd=cwd or ROOT,
            input=input_text,
            text=True,
            capture_output=True,
            env=env or self.env,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"command failed ({result.returncode}): {args}\n"
                f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
            )
        return result

    def write_config(self, root: Path, document: object) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        path = root / ".agtask.json"
        path.write_text(json.dumps(document))
        return path

    def hook(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return self.run_cli("hook", input_text=json.dumps(payload))

    def hook_context(self, result: subprocess.CompletedProcess[str]) -> str:
        output = json.loads(result.stdout)
        self.assertEqual(
            output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit"
        )
        return output["hookSpecificOutput"]["additionalContext"]

    def test_guardian_review_hooks_are_ignored_using_hook_metadata(self) -> None:
        logical_id = fixture_creation_id("guardian-hook-filter")
        session_id = "tracked-session"
        self.register(
            logical_id,
            session_id=session_id,
            title="agtask/guardian-hook-filter",
        )
        before = self.show(logical_id)

        preferred_model = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "guardian-preferred-model",
                "model": "codex-auto-review",
                "permission_mode": "bypassPermissions",
                "prompt": (
                    "The following is the Codex agent history added since your "
                    "last approval assessment."
                ),
            }
        )
        self.assertEqual((preferred_model.stdout, preferred_model.stderr), ("", ""))
        self.assertEqual(self.show(logical_id), before)

        guardian_transcript = self.root / "guardian-review.jsonl"
        guardian_transcript.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "source": {"subagent": {"other": "guardian"}},
                    },
                }
            )
            + "\n"
        )
        fallback_model = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "guardian-fallback-model",
                "model": "parent-model",
                "permission_mode": "bypassPermissions",
                "transcript_path": str(guardian_transcript),
                "prompt": (
                    "The following is the Codex agent history whose request "
                    "action you are assessing."
                ),
            }
        )
        self.assertEqual((fallback_model.stdout, fallback_model.stderr), ("", ""))
        self.assertEqual(self.show(logical_id), before)

        guardian_stop = self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": session_id,
                "turn_id": "guardian-stop",
                "model": "parent-model",
                "permission_mode": "bypassPermissions",
                "transcript_path": str(guardian_transcript),
                "last_assistant_message": '{"outcome":"allow"}',
            }
        )
        self.assertEqual((guardian_stop.stdout, guardian_stop.stderr), ("", ""))
        self.assertEqual(self.show(logical_id), before)

        ordinary_subagent_transcript = self.root / "ordinary-subagent.jsonl"
        ordinary_subagent_transcript.write_text(
            json.dumps(
                {
                    "type": "session_meta",
                    "payload": {
                        "source": {"subagent": {"other": "explorer"}},
                    },
                }
            )
            + "\n"
        )
        ordinary = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "ordinary-subagent-turn",
                "model": "parent-model",
                "permission_mode": "bypassPermissions",
                "transcript_path": str(ordinary_subagent_transcript),
                "prompt": "Write a compact database proof.",
            }
        )
        self.assertIn("Tracked agtask thread", self.hook_context(ordinary))
        state = self.show(logical_id)
        self.assertEqual(
            [
                (row["turn_id"], row["message"])
                for row in state["rollouts"]
                if row["role"] == "user"
            ],
            [("ordinary-subagent-turn", "Write a compact database proof.")],
        )

    def connect(self, path: Path | None = None) -> sqlite3.Connection:
        connection = sqlite3.connect(path or self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def register(
        self,
        thread_id: str = "thread-1",
        *,
        session_id: str | None = None,
        parent_session_id: str | None = "parent-thread",
        kind: str = "child",
        project: str = "agtask",
        title: str | None = None,
        status: str = "active",
        initial_prompt: str = FORK_PROMPT,
        description: str = "Write a compact database proof.",
        authoritative_session: bool = False,
    ) -> dict[str, object]:
        session_id = session_id or thread_id
        args = [
            "register",
            "--id",
            fixture_creation_id(thread_id),
            "--session-id",
            session_id,
            "--kind",
            kind,
            "--project",
            project,
            "--title",
            title or f"agtask/{thread_id}",
            "--initial-prompt",
            initial_prompt,
            "--description",
            description,
            "--status",
            status,
            "--json",
        ]
        if parent_session_id is not None:
            args[3:3] = ["--parent-session-id", parent_session_id]
        if authoritative_session:
            args.append("--authoritative-session")
        return json.loads(self.run_cli(*args).stdout)

    def show(self, thread_id: str = "thread-1") -> dict[str, object]:
        return json.loads(
            self.run_cli("show", "--id", fixture_creation_id(thread_id), "--json").stdout
        )

    def close_thread(self, thread_id: str = "thread-1") -> dict[str, object]:
        logical_id = fixture_creation_id(thread_id)
        prepared = json.loads(
            self.run_cli("close", "--id", logical_id, "--prepare", "--json").stdout
        )
        return json.loads(
            self.run_cli(
                "close",
                "--id",
                logical_id,
                "--merge-token",
                prepared["merge_claim"]["token"],
                "--json",
            ).stdout
        )

    def test_section_cache_round_trip_uses_database_directory_and_secure_modes(self) -> None:
        session_id = "019f81f5-06bc-73e1-b339-7442491fd833"
        missing = json.loads(
            self.run_cli("section-cache", "get", "--session-id", session_id, "--json").stdout
        )
        self.assertEqual(missing, {"state": "miss", "session_id": session_id})
        self.assertFalse(self.store.exists())

        stored = json.loads(
            self.run_cli(
                "section-cache",
                "set",
                "--session-id",
                session_id,
                "--host-id",
                "local",
                "--section-id",
                CUSTOM_SECTION_ID,
                "--section-name",
                "proj/clawpilot",
                "--json",
            ).stdout
        )
        cache_path = self.store / "sidebar-sections.json"
        lock_path = self.store / "sidebar-sections.json.lock"
        self.assertEqual(stored["state"], "stored")
        self.assertEqual(stored["entry"]["section_id"], CUSTOM_SECTION_ID)
        self.assertEqual(stored["entry"]["section_name"], "proj/clawpilot")
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(cache_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(lock_path.stat().st_mode), 0o600)
        self.assertFalse(self.db_path.exists())

        hit = json.loads(
            self.run_cli("section-cache", "get", "--session-id", session_id, "--json").stdout
        )
        self.assertEqual(hit, {"state": "hit", "session_id": session_id, "entry": stored["entry"]})
        document = json.loads(cache_path.read_text())
        self.assertEqual(document, {"version": 1, "sessions": {session_id: stored["entry"]}})

    def test_section_cache_stale_invalidate_and_preserves_other_sessions(self) -> None:
        session_id = "019f81f5-06bc-73e1-b339-7442491fd833"
        other_id = "019fd897-1cfe-75c3-9ed0-dc6a7d59e0cd"
        for identity, section_id in ((session_id, CUSTOM_SECTION_ID), (other_id, "pinned")):
            self.run_cli(
                "section-cache", "set", "--session-id", identity,
                "--host-id", "local", "--section-id", section_id, "--json",
            )
        cache_path = self.store / "sidebar-sections.json"
        document = json.loads(cache_path.read_text())
        document["sessions"][session_id]["observed_at"] = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=6)
        ).isoformat().replace("+00:00", "Z")
        cache_path.write_text(json.dumps(document))

        stale = json.loads(
            self.run_cli("section-cache", "get", "--session-id", session_id, "--json").stdout
        )
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(stale["entry"]["section_id"], CUSTOM_SECTION_ID)
        invalidated = json.loads(
            self.run_cli(
                "section-cache", "invalidate", "--session-id", session_id, "--json"
            ).stdout
        )
        self.assertEqual(invalidated, {"state": "invalidated", "session_id": session_id})
        remaining = json.loads(cache_path.read_text())
        self.assertEqual(set(remaining["sessions"]), {other_id})
        repeated = json.loads(
            self.run_cli(
                "section-cache", "invalidate", "--session-id", session_id, "--json"
            ).stdout
        )
        self.assertEqual(repeated, {"state": "miss", "session_id": session_id})

    def test_section_cache_rejects_unsafe_files_and_invalid_identities(self) -> None:
        session_id = "019f81f5-06bc-73e1-b339-7442491fd833"
        self.run_cli(
            "section-cache", "set", "--session-id", session_id,
            "--host-id", "local", "--section-id", "pinned", "--json",
        )
        cache_path = self.store / "sidebar-sections.json"
        cache_path.chmod(0o644)
        unsafe = json.loads(
            self.run_cli("section-cache", "get", "--session-id", session_id, "--json").stdout
        )
        self.assertEqual(unsafe, {"state": "miss", "session_id": session_id})
        refused = self.run_cli(
            "section-cache", "set", "--session-id", session_id,
            "--host-id", "local", "--section-id", "pinned", "--json", check=False,
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("unsafe section cache file", refused.stderr)
        cache_path.chmod(0o600)

        for invalid_section in ("", " pinned", "pinned ", "threads", "not-a-uuid"):
            with self.subTest(section_id=invalid_section):
                invalid = self.run_cli(
                    "section-cache", "set", "--session-id", session_id,
                    "--host-id", "local", "--section-id", invalid_section,
                    "--json", check=False,
                )
                self.assertNotEqual(invalid.returncode, 0)

        external = self.root / "external.json"
        external.write_text("{}")
        cache_path.unlink()
        cache_path.symlink_to(external)
        symlink = json.loads(
            self.run_cli("section-cache", "get", "--session-id", session_id, "--json").stdout
        )
        self.assertEqual(symlink, {"state": "miss", "session_id": session_id})
        self.assertEqual(external.read_text(), "{}")

    def test_section_cache_concurrent_writes_preserve_every_session(self) -> None:
        session_ids = [f"019f81f5-06bc-73e1-b339-{index:012d}" for index in range(8)]

        def store(session_id: str) -> subprocess.CompletedProcess[str]:
            return self.run_cli(
                "section-cache", "set", "--session-id", session_id,
                "--host-id", "local", "--section-id", CUSTOM_SECTION_ID,
                "--json",
            )

        with ThreadPoolExecutor(max_workers=len(session_ids)) as executor:
            list(executor.map(store, session_ids))
        document = json.loads((self.store / "sidebar-sections.json").read_text())
        self.assertEqual(set(document["sessions"]), set(session_ids))

    def test_resolve_create_validates_and_carries_sidebar_section_only_when_pinned(self) -> None:
        result = json.loads(
            self.run_cli(
                "resolve-create", "--title", "agtask/database-proof",
                "--parent-session-id", "parent-thread",
                "--section-id", CUSTOM_SECTION_ID, "--json",
            ).stdout
        )
        self.assertEqual(result["bootstrap_args"]["section_id"], CUSTOM_SECTION_ID)
        self.assertIn(f'"section_id":"{CUSTOM_SECTION_ID}"', result["bootstrap_trailer"])

        nopin = json.loads(
            self.run_cli(
                "resolve-create", "--title", "agtask/database-proof",
                "--parent-session-id", "parent-thread",
                "--section-id", CUSTOM_SECTION_ID, "--nopin", "--json",
            ).stdout
        )
        self.assertNotIn("section_id", nopin["bootstrap_args"])
        self.assertFalse(self.store.exists())

        for invalid_section in ("", " pinned", "pinned ", "not-a-uuid"):
            with self.subTest(section_id=invalid_section):
                invalid = self.run_cli(
                    "resolve-create", "--title", "agtask/database-proof",
                    "--parent-session-id", "parent-thread",
                    "--section-id", invalid_section, "--json", check=False,
                )
                self.assertNotEqual(invalid.returncode, 0)

    def test_resolve_create_normalizes_execution_inputs_without_opening_ledger(self) -> None:
        cases = [
            (
                (
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    "--parent-session-id",
                    "parent-thread",
                    "--json",
                ),
                {
                    "environment": {"type": "local"},
                    "bootstrap_args": {
                        "parent_session_id": "parent-thread",
                        "pin": True,
                        "project": "agtask",
                        "section_id": "pinned",
                        "title": "agtask/database-proof",
                    },
                    "bootstrap_trailer": BOOTSTRAP_SECTION_TRAILER,
                    "include_model": False,
                    "hook_prompts": [],
                    "kind": "child",
                    "mode": "clean",
                    "model": "inherit",
                    "pin": True,
                    "project": "agtask",
                    "title": "agtask/database-proof",
                    "worktree": False,
                },
            ),
            (
                (
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    "--mode",
                    "clean",
                    "--worktree",
                    "true",
                    "--parent-session-id",
                    "parent-thread",
                    "--json",
                ),
                {
                    "environment": {"type": "worktree"},
                    "bootstrap_args": {
                        "parent_session_id": "parent-thread",
                        "pin": True,
                        "project": "agtask",
                        "section_id": "pinned",
                        "title": "agtask/database-proof",
                    },
                    "bootstrap_trailer": BOOTSTRAP_SECTION_TRAILER,
                    "include_model": False,
                    "hook_prompts": [],
                    "kind": "child",
                    "mode": "clean",
                    "model": "inherit",
                    "pin": True,
                    "project": "agtask",
                    "title": "agtask/database-proof",
                    "worktree": True,
                },
            ),
            (
                (
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    "--mode",
                    "fork",
                    "--parent-session-id",
                    "parent-thread",
                    "--json",
                ),
                {
                    "environment": {"type": "same-directory"},
                    "bootstrap_args": {
                        "parent_session_id": "parent-thread",
                        "pin": True,
                        "project": "agtask",
                        "section_id": "pinned",
                        "title": "agtask/database-proof",
                    },
                    "bootstrap_trailer": BOOTSTRAP_SECTION_TRAILER,
                    "include_model": False,
                    "hook_prompts": [],
                    "kind": "child",
                    "mode": "fork",
                    "model": "inherit",
                    "pin": True,
                    "project": "agtask",
                    "title": "agtask/database-proof",
                    "worktree": False,
                },
            ),
            (
                (
                    "resolve-create",
                    "--mode",
                    "fork",
                    "--worktree",
                    "true",
                    "--model",
                    "gpt-5.6-sol",
                    "--pin",
                    "false",
                    "--kind",
                    "main",
                    "--project",
                    "custom-project",
                    "--title",
                    "agtask/database-proof",
                    "--json",
                ),
                {
                    "environment": {"type": "worktree"},
                    "bootstrap_args": {
                        "pin": False,
                        "title": "agtask/database-proof",
                    },
                    "bootstrap_trailer": BOOTSTRAP_V1_FALSE_TRAILER,
                    "include_model": True,
                    "hook_prompts": [],
                    "kind": "main",
                    "mode": "fork",
                    "model": "gpt-5.6-sol",
                    "pin": False,
                    "project": "custom-project",
                    "title": "agtask/database-proof",
                    "worktree": True,
                },
            ),
            (
                (
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    "--nopin",
                    "--parent-session-id",
                    "parent-thread",
                    "--json",
                ),
                {
                    "environment": {"type": "local"},
                    "bootstrap_args": {
                        "parent_session_id": "parent-thread",
                        "pin": False,
                        "project": "agtask",
                        "title": "agtask/database-proof",
                    },
                    "bootstrap_trailer": BOOTSTRAP_FALSE_TRAILER,
                    "include_model": False,
                    "hook_prompts": [],
                    "kind": "child",
                    "mode": "clean",
                    "model": "inherit",
                    "pin": False,
                    "project": "agtask",
                    "title": "agtask/database-proof",
                    "worktree": False,
                },
            ),
        ]
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                actual = json.loads(self.run_cli(*arguments).stdout)
                creation_id = actual["id"]
                self.assertEqual(str(__import__("uuid").UUID(creation_id)), creation_id)
                expected["id"] = creation_id
                if actual["kind"] == "child":
                    expected["bootstrap_args"]["id"] = creation_id
                    expected["bootstrap_trailer"] = expected["bootstrap_trailer"].replace(
                        CREATION_ID, creation_id
                    )
                self.assertEqual(actual, expected)
        self.assertFalse(self.db_path.exists())

    def test_resolve_create_builds_exact_clean_creation_plan(self) -> None:
        result = json.loads(
            self.run_cli(
                "resolve-create",
                "--mode",
                "clean",
                "--title",
                "agtask/database-proof",
                "--parent-session-id",
                "parent-thread",
                "--project",
                "agtask",
                "--task",
                "Write a compact database proof.",
                "--project-id",
                "saved-project-id",
                "--model",
                "gpt-5.6-sol",
                "--thinking",
                "high",
                "--json",
            ).stdout
        )
        creation_id = result["id"]
        trailer = BOOTSTRAP_SECTION_TRAILER.replace(CREATION_ID, creation_id)
        prompt = "Task:\nWrite a compact database proof.\n\n" + trailer
        self.assertEqual(result["thinking"], "high")
        self.assertTrue(result["include_thinking"])
        self.assertEqual(
            result["creation_plan"],
            {
                "version": 1,
                "next_tool": {
                    "name": "create_thread",
                    "arguments": {
                        "prompt": prompt,
                        "model": "gpt-5.6-sol",
                        "thinking": "high",
                        "target": {
                            "type": "project",
                            "projectId": "saved-project-id",
                            "environment": {"type": "local"},
                        },
                    },
                },
            },
        )
        self.assertFalse(self.db_path.exists())

    def test_resolve_create_plan_preserves_resolved_task_bytes(self) -> None:
        result = json.loads(
            self.run_cli(
                "resolve-create",
                "--mode",
                "clean",
                "--title",
                "agtask/database-proof",
                "--parent-session-id",
                "parent-thread",
                "--task",
                "  Write a compact database proof.\n",
                "--project-id",
                "saved-project-id",
                "--json",
            ).stdout
        )
        creation_id = result["id"]
        trailer = BOOTSTRAP_SECTION_TRAILER.replace(CREATION_ID, creation_id)
        prompt = "Task:\n  Write a compact database proof.\n\n\n" + trailer
        self.assertEqual(result["thinking"], "inherit")
        self.assertFalse(result["include_thinking"])
        self.assertEqual(
            result["creation_plan"]["next_tool"]["arguments"]["prompt"],
            prompt,
        )
        self.assertFalse(self.db_path.exists())

    def test_resolve_create_plan_appends_configured_oncreate_prompt(self) -> None:
        config = self.write_config(
            self.root,
            {"hooks": {"OnCreate": {"prompt": "Run the project preflight."}}},
        )
        result = json.loads(
            self.run_cli(
                "resolve-create",
                "--mode",
                "clean",
                "--title",
                "agtask/database-proof",
                "--parent-session-id",
                "parent-thread",
                "--project",
                "agtask",
                "--task",
                "Write a compact database proof.",
                "--project-id",
                "saved-project-id",
                "--json",
                cwd=self.root,
            ).stdout
        )
        creation_id = result["id"]
        trailer = BOOTSTRAP_SECTION_TRAILER.replace(CREATION_ID, creation_id)
        self.assertEqual(
            result["creation_plan"]["next_tool"]["arguments"]["prompt"],
            "Task:\nWrite a compact database proof."
            "\n\nConfigured OnCreate prompt:\nRun the project preflight."
            "\n\n"
            + trailer,
        )
        self.assertEqual(result["hook_prompts"][0]["source"], str(config.resolve()))
        self.assertFalse(self.db_path.exists())

    def test_bootstrap_protocol_is_exact_typed_allowlisted_and_fail_open(self) -> None:
        incomplete_v2 = BOOTSTRAP_PROMPT.replace(
            '"parent_session_id":"parent-thread",', ""
        )
        ignored = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "incomplete-child",
                "turn_id": "first-turn",
                "prompt": incomplete_v2,
            }
        )
        self.assertEqual((ignored.stdout, ignored.stderr), ("", ""))
        self.assertFalse(self.db_path.exists())

        legacy = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "legacy-action-only",
                "turn_id": "first-turn",
                "prompt": BOOTSTRAP_V1_PROMPT,
            }
        )
        legacy_context = self.hook_context(legacy)
        self.assertIn("codex_app__set_thread_pinned", legacy_context)
        self.assertIn("codex_app__set_thread_title", legacy_context)
        self.assertFalse(self.db_path.exists())

        valid = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "materialized-child",
                    "turn_id": "first-turn",
                    "prompt": BOOTSTRAP_PROMPT,
                }
            ),
        )
        valid_context = self.hook_context(valid)
        self.assertIn("validated deterministic agtask bootstrap action", valid_context)
        self.assertIn("codex_app__set_thread_pinned", valid_context)
        self.assertIn("codex_app__set_thread_title", valid_context)
        self.assertIn('"threadId":"materialized-child"', valid_context)
        self.assertIn('"title":"agtask/database-proof"', valid_context)
        self.assertIn("model-mediated", valid_context)
        self.assertIn("continue the actual task", valid_context)
        state = self.show(CREATION_ID)
        self.assertEqual(state["session_id"], "materialized-child")
        self.assertEqual(state["parent_session_id"], "parent-thread")
        self.assertEqual(state["kind"], "child")
        self.assertEqual(state["project"], "agtask")
        self.assertEqual(state["title"], "agtask/database-proof")
        self.assertEqual(state["description"], "Write a compact database proof.")
        self.assertEqual(state["status"], "active")
        self.assertEqual(
            [(row["turn_id"], row["role"], row["message"]) for row in reversed(state["rollouts"])],
            [
                ("thread.created", "meta", "thread.created"),
                ("first-turn", "user", "Write a compact database proof."),
            ],
        )
        parent_retry = self.register(
            CREATION_ID,
            session_id="materialized-child",
            title="agtask/database-proof",
            initial_prompt=BOOTSTRAP_PROMPT,
            status="active",
        )
        self.assertEqual(parent_retry["hook_prompts"], [])
        parent_fallback = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                CREATION_ID,
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                BOOTSTRAP_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(parent_fallback["rollouts"], state["rollouts"])
        repeated = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "materialized-child",
                    "turn_id": "first-turn",
                    "prompt": BOOTSTRAP_PROMPT,
                }
            ),
        )
        self.assertEqual(repeated.stdout, valid.stdout)

        conflicting_prompt = BOOTSTRAP_PROMPT.replace(
            '"title":"agtask/database-proof"',
            '"title":"agtask/conflicting-title"',
        )
        conflicting = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "materialized-child",
                "turn_id": "conflicting-turn",
                "prompt": conflicting_prompt,
            }
        )
        self.assertEqual((conflicting.stdout, conflicting.stderr), ("", ""))
        self.assertEqual(self.show(CREATION_ID), state)

        wrapped_id = "d882bc31-b5ed-4af9-9955-c7abe464f16c"
        wrapped_prompt = bootstrap_prompt(wrapped_id)
        wrapped = f"""<codex_delegation>
  <source_thread_id>parent</source_thread_id>
  <input>{html.escape(wrapped_prompt, quote=False)}
</input>
</codex_delegation>"""
        wrapped_result = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "wrapped-child",
                    "turn_id": "first-turn",
                    "prompt": wrapped,
                }
            ),
        )
        self.assertIn('"threadId":"wrapped-child"', self.hook_context(wrapped_result))
        wrapped_state = self.show(wrapped_id)
        self.assertEqual(wrapped_state["description"], "Write a compact database proof.")
        self.assertEqual(
            [row["turn_id"] for row in wrapped_state["rollouts"] if row["role"] == "user"],
            ["first-turn"],
        )
        self.assertNotIn("agtask-bootstrap", json.dumps(wrapped_state))

        entity_task = "Preserve R&D, <tag>, and literal &lt;."
        entity_arguments = {
            "id": "ef10627b-35b1-4246-a169-b01e2b33a625",
            "parent_session_id": "parent&R",
            "pin": True,
            "project": "R&D <core> &lt;",
            "title": "agtask/R&D <tag> &lt;",
        }
        entity_prompt = (
            FORK_PROMPT.replace("Write a compact database proof.", entity_task).rstrip()
            + "\n\n<agtask-bootstrap version=\"2\">\n"
            + json.dumps(entity_arguments, separators=(",", ":"), sort_keys=True)
            + "\n</agtask-bootstrap>"
        )
        entity_wrapped = f"""<codex_delegation>
  <source_thread_id>parent&amp;R</source_thread_id>
  <input>{html.escape(entity_prompt, quote=False)}
</input>
</codex_delegation>"""
        entity_result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "entity-child",
                "turn_id": "entity-turn",
                "prompt": entity_wrapped,
            }
        )
        entity_context = self.hook_context(entity_result)
        self.assertIn('"title":"agtask/R&D <tag> &lt;"', entity_context)
        entity_state = self.show(entity_arguments["id"])
        self.assertEqual(entity_state["parent_session_id"], "parent&R")
        self.assertEqual(entity_state["project"], "R&D <core> &lt;")
        self.assertEqual(entity_state["title"], "agtask/R&D <tag> &lt;")
        self.assertEqual(entity_state["description"], entity_task)
        self.assertEqual(
            [row["message"] for row in entity_state["rollouts"] if row["role"] == "user"],
            [entity_task],
        )

        escaped_wrapped_id = "a40e4b2b-cb6e-4d0e-8f87-32e1d0cf6b18"
        escaped_wrapped_prompt = bootstrap_prompt(escaped_wrapped_id)
        escaped_wrapped = f"""<codex_delegation>
  <source_thread_id>parent</source_thread_id>
  <input>{html.escape(escaped_wrapped_prompt, quote=False)}
</input>
</codex_delegation>"""
        escaped_wrapped_result = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "escaped-wrapped-child",
                    "turn_id": "first-turn",
                    "prompt": escaped_wrapped,
                }
            ),
        )
        escaped_wrapped_context = self.hook_context(escaped_wrapped_result)
        self.assertIn("codex_app__set_thread_pinned", escaped_wrapped_context)
        self.assertIn("codex_app__set_thread_title", escaped_wrapped_context)
        self.assertIn(
            '"threadId":"escaped-wrapped-child"', escaped_wrapped_context
        )

        escaped_unwrapped = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "escaped-unwrapped-child",
                    "turn_id": "first-turn",
                    "prompt": ESCAPED_BOOTSTRAP_PROMPT,
                }
            ),
        )
        self.assertEqual(
            (escaped_unwrapped.stdout, escaped_unwrapped.stderr), ("", "")
        )

        escaped_noncanonical = escaped_wrapped.replace(
            '"pin":true',
            '"pin": true',
        )
        escaped_noncanonical_result = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "escaped-noncanonical-child",
                    "turn_id": "first-turn",
                    "prompt": escaped_noncanonical,
                }
            ),
        )
        self.assertEqual(
            (escaped_noncanonical_result.stdout, escaped_noncanonical_result.stderr),
            ("", ""),
        )

        invalid_prompts: dict[str, tuple[str, str | None]] = {}
        for name in (
            "wrong-type",
            "integer-not-bool",
            "duplicate-key",
            "unknown-key",
            "title-wrong-type",
            "title-empty",
            "wrong-version",
            "noncanonical-json",
            "not-final",
            "trailing-newline",
            "missing-id",
            "malformed-id",
            "non-v4-id",
            "noncanonical-id",
        ):
            creation_id = fixture_creation_id(f"invalid-bootstrap:{name}")
            invalid_prompts[name] = (bootstrap_prompt(creation_id), creation_id)
        invalid_prompts["wrong-type"] = (
            invalid_prompts["wrong-type"][0].replace("true", '"true"'),
            invalid_prompts["wrong-type"][1],
        )
        invalid_prompts["integer-not-bool"] = (
            invalid_prompts["integer-not-bool"][0].replace("true", "1"),
            invalid_prompts["integer-not-bool"][1],
        )
        invalid_prompts["duplicate-key"] = (
            invalid_prompts["duplicate-key"][0].replace(
                '"pin":true', '"pin":true,"pin":false'
            ),
            invalid_prompts["duplicate-key"][1],
        )
        invalid_prompts["unknown-key"] = (
            invalid_prompts["unknown-key"][0].replace(
                '{"id"', '{"command":"touch /tmp/nope","id"'
            ),
            invalid_prompts["unknown-key"][1],
        )
        invalid_prompts["title-wrong-type"] = (
            invalid_prompts["title-wrong-type"][0].replace(
                '"title":"agtask/database-proof"', '"title":true'
            ),
            invalid_prompts["title-wrong-type"][1],
        )
        invalid_prompts["title-empty"] = (
            invalid_prompts["title-empty"][0].replace(
                '"title":"agtask/database-proof"', '"title":""'
            ),
            invalid_prompts["title-empty"][1],
        )
        invalid_prompts["wrong-version"] = (
            invalid_prompts["wrong-version"][0].replace(
                'version="2"', 'version="3"'
            ),
            invalid_prompts["wrong-version"][1],
        )
        invalid_prompts["noncanonical-json"] = (
            invalid_prompts["noncanonical-json"][0].replace(
                '"pin":true', '"pin": true'
            ),
            invalid_prompts["noncanonical-json"][1],
        )
        invalid_prompts["not-final"] = (
            invalid_prompts["not-final"][0] + "\nordinary task text",
            invalid_prompts["not-final"][1],
        )
        invalid_prompts["trailing-newline"] = (
            invalid_prompts["trailing-newline"][0] + "\n",
            invalid_prompts["trailing-newline"][1],
        )
        missing_id = invalid_prompts["missing-id"][1]
        assert missing_id is not None
        invalid_prompts["missing-id"] = (
            invalid_prompts["missing-id"][0].replace(f'"id":"{missing_id}",', ""),
            missing_id,
        )
        for name, bad_id in (
            ("malformed-id", "not-a-uuid"),
            ("non-v4-id", "11111111-1111-1111-8111-111111111111"),
        ):
            valid_id = invalid_prompts[name][1]
            assert valid_id is not None
            invalid_prompts[name] = (
                invalid_prompts[name][0].replace(valid_id, bad_id),
                valid_id,
            )
        noncanonical_id = invalid_prompts["noncanonical-id"][1]
        assert noncanonical_id is not None
        invalid_prompts["noncanonical-id"] = (
            invalid_prompts["noncanonical-id"][0].replace(
                noncanonical_id, noncanonical_id.upper()
            ),
            noncanonical_id,
        )
        invalid_prompts["lookalike"] = (
            FORK_PROMPT + "args: {\"pin\": true}",
            None,
        )
        for name, (prompt, creation_id) in invalid_prompts.items():
            with self.subTest(name=name):
                session_id = f"untracked-{name}"
                with self.connect() as connection:
                    before = connection.execute("SELECT count(*) FROM thread").fetchone()[0]
                ignored = self.run_cli(
                    "hook",
                    input_text=json.dumps(
                        {
                            "hook_event_name": "UserPromptSubmit",
                            "session_id": session_id,
                            "turn_id": name,
                            "prompt": prompt,
                        }
                    ),
                )
                self.assertEqual((ignored.stdout, ignored.stderr), ("", ""))
                with self.connect() as connection:
                    self.assertEqual(
                        connection.execute("SELECT count(*) FROM thread").fetchone()[0],
                        before,
                    )
                    self.assertIsNone(
                        connection.execute(
                            "SELECT 1 FROM thread WHERE session_id=?", (session_id,)
                        ).fetchone()
                    )
                    if creation_id is not None:
                        self.assertIsNone(
                            connection.execute(
                                "SELECT 1 FROM thread WHERE id=?", (creation_id,)
                            ).fetchone()
                        )

        false_action = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "untracked",
                    "turn_id": "pin-false",
                    "prompt": BOOTSTRAP_V1_PROMPT.replace("true", "false"),
                }
            ),
        )
        false_context = self.hook_context(false_action)
        self.assertNotIn("codex_app__set_thread_pinned", false_context)
        self.assertIn("codex_app__set_thread_title", false_context)
        self.assertEqual(false_action.stderr, "")

        session_start = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "SessionStart",
                    "session_id": "untracked",
                    "source": "startup",
                    "prompt": BOOTSTRAP_PROMPT,
                }
            ),
        )
        self.assertEqual((session_start.stdout, session_start.stderr), ("", ""))

    def test_concurrent_first_hooks_initialize_once_without_losing_prompts(self) -> None:
        def submit(index: int) -> subprocess.CompletedProcess[str]:
            return self.hook(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": f"concurrent-child-{index}",
                    "turn_id": f"first-turn-{index}",
                    "prompt": BOOTSTRAP_PROMPT,
                }
            )

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(submit, range(6)))

        self.assertTrue(all(result.returncode == 0 for result in results))
        self.assertTrue(all(result.stderr == "" for result in results))
        self.assertEqual(sum("hookSpecificOutput" in result.stdout for result in results), 1)
        state = self.show(CREATION_ID)
        self.assertIn(state["session_id"], {f"concurrent-child-{index}" for index in range(6)})
        self.assertEqual(len(state["rollouts"]), 2)
        with self.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM thread").fetchone()[0], 1)

    def test_concurrent_distinct_bootstrap_ids_all_register(self) -> None:
        ids = [str(uuid.uuid4()) for _ in range(6)]

        def submit(index: int) -> subprocess.CompletedProcess[str]:
            return self.hook(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": f"distinct-child-{index}",
                    "turn_id": f"first-turn-{index}",
                    "prompt": bootstrap_prompt(ids[index]),
                }
            )

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(submit, range(6)))
        self.assertTrue(all("hookSpecificOutput" in result.stdout for result in results))
        with self.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM thread").fetchone()[0], 6)

    def test_title_generator_copy_cannot_claim_real_child_bootstrap(self) -> None:
        logical_id = "40fcb625-55d4-4673-b1f2-a36fa273fc6d"
        real_session_id = "019f6e67-dbc6-7111-b791-43d223817140"
        title_session_id = "019f6e67-e372-7d03-bd30-4afcbe485556"
        real_prompt = "Implement a simple per-project merge queue for agtask."
        prompt = bootstrap_prompt(
            logical_id,
            title="agtask/merge-queue",
            prompt=real_prompt,
        )
        real = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": real_session_id,
                "turn_id": "real-turn",
                "prompt": prompt,
            }
        )
        self.assertIn(f'"threadId":"{real_session_id}"', self.hook_context(real))

        copied = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": title_session_id,
                "turn_id": "title-turn",
                "prompt": bootstrap_prompt(
                    logical_id,
                    title="agtask/merge-queue",
                    prompt="You are a helpful assistant.",
                ),
            }
        )
        self.assertEqual((copied.stdout, copied.stderr), ("", ""))
        state = self.show(logical_id)
        self.assertEqual(state["session_id"], real_session_id)
        self.assertEqual(state["description"], real_prompt)
        self.assertEqual(
            [(row["role"], row["turn_id"]) for row in reversed(state["rollouts"])],
            [("meta", "thread.created"), ("user", "real-turn")],
        )

        retry = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": real_session_id,
                "turn_id": "real-turn",
                "prompt": prompt,
            }
        )
        self.assertIn(f'"threadId":"{real_session_id}"', self.hook_context(retry))
        self.assertEqual(self.show(logical_id), state)

    def test_parent_rebinds_title_generator_shadow_to_authoritative_session(
        self,
    ) -> None:
        logical_id = fixture_creation_id("authoritative-session-rebind")
        title_session_id = "title-generator-shadow"
        real_session_id = "real-created-session"
        title = "agtask/authoritative-rebind"
        shadow_prompt = bootstrap_prompt(
            logical_id,
            title=title,
            prompt="You are a helpful assistant.",
        )
        real_prompt = bootstrap_prompt(
            logical_id,
            title=title,
            prompt="Summarize the work completed yesterday.",
        )
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": title_session_id,
                "turn_id": "title-turn",
                "prompt": shadow_prompt,
            }
        )
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": title_session_id,
                "turn_id": "title-turn",
                "last_assistant_message": (
                    '{"title":"Summarize yesterday","description":"Summarize recent work"}'
                ),
            }
        )

        result = self.register(
            logical_id,
            session_id=real_session_id,
            title=title,
            initial_prompt=real_prompt,
            description="Summarize the work completed yesterday.",
            authoritative_session=True,
        )

        self.assertEqual(result["session_id"], real_session_id)
        self.assertEqual(result["session_rebound_from"], title_session_id)
        self.assertEqual(
            result["description"], "Summarize the work completed yesterday."
        )
        self.assertEqual(result["status"], "active")
        self.assertEqual(
            [(row["role"], row["turn_id"]) for row in result["rollouts"]],
            [("meta", "thread.created")],
        )

        reconciled = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                logical_id,
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                real_prompt,
                "--json",
            ).stdout
        )
        self.assertEqual(
            [(row["role"], row["turn_id"]) for row in reconciled["rollouts"]],
            [("user", "bootstrap"), ("meta", "thread.created")],
        )

        ignored_old_stop = self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": title_session_id,
                "turn_id": "late-title-turn",
                "last_assistant_message": "This must not attach to the real task.",
            }
        )
        self.assertEqual((ignored_old_stop.stdout, ignored_old_stop.stderr), ("", ""))
        self.assertEqual(self.show(logical_id), reconciled)

    def test_authoritative_session_rebind_preserves_conflict_guards(self) -> None:
        logical_id = fixture_creation_id("authoritative-session-conflicts")
        shadow_session_id = "shadow-session"
        title = "agtask/authoritative-conflicts"
        shadow_prompt = bootstrap_prompt(
            logical_id,
            title=title,
            prompt="You are a helpful assistant.",
        )
        real_prompt = bootstrap_prompt(
            logical_id,
            title=title,
            prompt="Summarize the work completed yesterday.",
        )
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": shadow_session_id,
                "turn_id": "shadow-turn",
                "prompt": shadow_prompt,
            }
        )
        before = self.show(logical_id)

        strict = self.run_cli(
            "register",
            "--id",
            logical_id,
            "--session-id",
            "real-session",
            "--parent-session-id",
            "parent-thread",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            title,
            "--initial-prompt",
            real_prompt,
            "--status",
            "active",
            "--json",
            check=False,
        )
        self.assertEqual(strict.returncode, 1)
        self.assertIn("id conflict", strict.stderr)
        self.assertEqual(self.show(logical_id), before)

        mismatched_title = self.run_cli(
            "register",
            "--id",
            logical_id,
            "--session-id",
            "real-session",
            "--parent-session-id",
            "parent-thread",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "agtask/different-title",
            "--initial-prompt",
            real_prompt,
            "--status",
            "active",
            "--authoritative-session",
            "--json",
            check=False,
        )
        self.assertEqual(mismatched_title.returncode, 1)
        self.assertIn("title conflict", mismatched_title.stderr)
        self.assertEqual(self.show(logical_id), before)

        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": shadow_session_id,
                "turn_id": "second-shadow-turn",
                "prompt": "Continue working on the helper session.",
            }
        )
        non_provisional = self.run_cli(
            "register",
            "--id",
            logical_id,
            "--session-id",
            "real-session",
            "--parent-session-id",
            "parent-thread",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            title,
            "--initial-prompt",
            real_prompt,
            "--status",
            "active",
            "--authoritative-session",
            "--json",
            check=False,
        )
        self.assertEqual(non_provisional.returncode, 1)
        self.assertIn("unexpected rollout history", non_provisional.stderr)
        self.assertEqual(self.show(logical_id)["session_id"], shadow_session_id)

    def test_exact_bootstrap_retry_preserves_blocked_state_without_writes(self) -> None:
        logical_id = fixture_creation_id("blocked-bootstrap-retry")
        session_id = "blocked-bootstrap-session"
        prompt = bootstrap_prompt(logical_id)
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "first-turn",
                "prompt": prompt,
            }
        )
        self.run_cli(
            "status",
            "--session-id",
            session_id,
            "--status",
            "blocked",
            "--json",
        )
        before = self.show(logical_id)

        retry = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "first-turn",
                "prompt": prompt,
            }
        )

        self.assertIn(f'"threadId":"{session_id}"', self.hook_context(retry))
        self.assertEqual(self.show(logical_id), before)
        self.assertEqual(before["status"], "blocked")
        self.assertEqual(
            [
                row["message"]
                for row in before["rollouts"]
                if row["message"].startswith("status:")
            ],
            ["status:active->blocked"],
        )
        parent_retry = self.register(
            logical_id,
            session_id=session_id,
            title="agtask/database-proof",
            initial_prompt=prompt,
            status="active",
        )
        self.assertEqual(parent_retry["status"], "blocked")
        self.assertEqual(
            {key: value for key, value in parent_retry.items() if key != "hook_prompts"},
            before,
        )

    def test_done_exact_bootstrap_pair_records_follow_up_and_emits_actions(self) -> None:
        logical_id = fixture_creation_id("done-bootstrap-follow-up")
        session_id = "done-bootstrap-session"
        prompt = bootstrap_prompt(logical_id)
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "initial-turn",
                "prompt": prompt,
            }
        )
        closed = self.close_thread(logical_id)
        self.assertEqual(closed["status"], "done")
        closed_at = closed["closed"]

        follow_up = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "done-follow-up-turn",
                "prompt": prompt,
            }
        )

        context = self.hook_context(follow_up)
        self.assertIn(f'"threadId":"{session_id}"', context)
        self.assertIn("Status: done", context)
        state = self.show(logical_id)
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["closed"], closed_at)
        self.assertEqual(
            [row["turn_id"] for row in state["rollouts"] if row["role"] == "user"],
            ["done-follow-up-turn", "initial-turn"],
        )

    def test_valid_bootstrap_identity_conflicts_are_silent_and_write_nothing(self) -> None:
        first_id = fixture_creation_id("identity-matrix-first")
        second_id = fixture_creation_id("identity-matrix-second")
        unclaimed_id = fixture_creation_id("identity-matrix-unclaimed")
        first_session = "identity-matrix-first-session"
        second_session = "identity-matrix-second-session"
        for logical_id, session_id in (
            (first_id, first_session),
            (second_id, second_session),
        ):
            self.hook(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": session_id,
                    "turn_id": f"create-{session_id}",
                    "prompt": bootstrap_prompt(logical_id),
                }
            )

        cases = (
            ("tracked-session-owned-id", first_session, second_id),
            ("tracked-session-unclaimed-id", first_session, unclaimed_id),
            ("untracked-session-claimed-id", "identity-matrix-copy", first_id),
            ("same-pair-metadata-conflict", first_session, first_id),
        )
        for name, session_id, logical_id in cases:
            with self.subTest(name=name):
                prompt = bootstrap_prompt(logical_id)
                if name == "same-pair-metadata-conflict":
                    prompt = bootstrap_prompt(logical_id, project="different-project")
                with self.connect() as connection:
                    before_threads = connection.execute(
                        "SELECT * FROM thread ORDER BY id"
                    ).fetchall()
                    before_rollouts = connection.execute(
                        "SELECT * FROM rollout ORDER BY id"
                    ).fetchall()
                result = self.hook(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": session_id,
                        "turn_id": f"conflict-{name}",
                        "prompt": prompt,
                    }
                )
                self.assertEqual((result.stdout, result.stderr), ("", ""))
                with self.connect() as connection:
                    self.assertEqual(
                        connection.execute("SELECT * FROM thread ORDER BY id").fetchall(),
                        before_threads,
                    )
                    self.assertEqual(
                        connection.execute("SELECT * FROM rollout ORDER BY id").fetchall(),
                        before_rollouts,
                    )

    def test_creation_bootstrap_converges_for_parent_first_orderings(self) -> None:
        self.run_cli("init")
        for thread_id, logical_id, bootstrap_first, initial_status in (
            ("register-first", "877040b4-e061-493f-99ae-ea26be185b08", False, "active"),
            ("bootstrap-first", "e84bf34a-df91-4cf8-83fc-cd06442b79db", True, "active"),
            ("two-phase-todo", "979db832-df35-4338-9dd5-863265fc2b44", False, "todo"),
        ):
            with self.subTest(
                thread_id=thread_id,
                bootstrap_first=bootstrap_first,
                initial_status=initial_status,
            ):
                self.register(
                    logical_id,
                    session_id=thread_id,
                    title="agtask/database-proof",
                    status=initial_status,
                    initial_prompt=bootstrap_prompt(logical_id),
                )
                if bootstrap_first:
                    self.run_cli(
                        "record-turn",
                        "--id",
                        logical_id,
                        "--role",
                        "user",
                        "--turn-id",
                        "bootstrap",
                        "--content",
                        bootstrap_prompt(logical_id),
                    )
                self.hook(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": thread_id,
                        "turn_id": f"real-{thread_id}",
                        "prompt": bootstrap_prompt(logical_id),
                    }
                )
                state = self.show(logical_id)
                self.assertEqual(state["status"], "active")
                self.assertEqual(
                    [
                        (row["turn_id"], row["message"])
                        for row in state["rollouts"]
                        if row["role"] == "user"
                    ],
                    [(f"real-{thread_id}", "Write a compact database proof.")],
                )
                self.assertEqual(
                    len(
                        [
                            row
                            for row in state["rollouts"]
                            if row["message"] == "thread.created"
                        ]
                    ),
                    1,
                )
                status_rows = [
                    row
                    for row in state["rollouts"]
                    if row["message"] == "status:todo->active"
                ]
                self.assertEqual(len(status_rows), 1 if initial_status == "todo" else 0)

    def test_bootstrap_metadata_is_excluded_from_summaries_and_reconciliation(self) -> None:
        self.run_cli("init")
        self.register(
            CREATION_ID,
            session_id="thread-1",
            title="agtask/database-proof",
            status="todo",
        )
        bootstrap = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                CREATION_ID,
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                BOOTSTRAP_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(bootstrap["description"], "Write a compact database proof.")
        self.assertNotIn("agtask-bootstrap", json.dumps(bootstrap))

        prompt_result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-1",
                "turn_id": "real-first-turn",
                "prompt": BOOTSTRAP_PROMPT,
            }
        )
        self.assertIn("codex_app__move_thread_to_sidebar_section", prompt_result.stdout)
        self.assertIn("codex_app__set_thread_pinned", prompt_result.stdout)
        context = self.hook_context(prompt_result)
        self.assertLess(
            context.index("codex_app__move_thread_to_sidebar_section"),
            context.index("codex_app__set_thread_pinned"),
        )
        self.assertIn('"sectionId":"pinned"', context)
        self.assertIn("codex_app__set_thread_title", prompt_result.stdout)
        state = self.show(CREATION_ID)
        user_rows = [row for row in state["rollouts"] if row["role"] == "user"]
        self.assertEqual(
            [(row["turn_id"], row["message"]) for row in user_rows],
            [("real-first-turn", "Write a compact database proof.")],
        )
        self.assertEqual(state["description"], "Write a compact database proof.")
        self.assertNotIn("agtask-bootstrap", json.dumps(state))

    def test_custom_section_bootstrap_prefers_move_and_describes_legacy_fallback(self) -> None:
        session_id = "019fd897-1cfe-75c3-9ed0-dc6a7d59e0cd"
        prompt = bootstrap_prompt(section_id=CUSTOM_SECTION_ID)
        result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "turn_id": "custom-section-first-turn",
                "prompt": prompt,
            }
        )
        context = self.hook_context(result)
        self.assertIn(
            f'"sectionId":"{CUSTOM_SECTION_ID}","threadId":"{session_id}"',
            context,
        )
        self.assertLess(
            context.index("codex_app__move_thread_to_sidebar_section"),
            context.index("codex_app__set_thread_pinned"),
        )
        self.assertIn("global only; custom section unavailable", context)
        self.assertIn("idempotent", context)
        self.assertIn("failed: <exact error>", context)
        self.assertIn("continue the actual task", context)

    def test_legacy_v1_bootstrap_defaults_to_pinned_sidebar_section(self) -> None:
        self.run_cli("init")
        self.register("legacy-v1", session_id="legacy-v1", status="todo")
        result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "legacy-v1",
                "turn_id": "legacy-v1-turn",
                "prompt": BOOTSTRAP_V1_PROMPT,
            }
        )
        context = self.hook_context(result)
        self.assertIn('"sectionId":"pinned","threadId":"legacy-v1"', context)
        self.assertIn("codex_app__set_thread_pinned", context)

    def test_invalid_section_bootstrap_never_emits_placement_actions(self) -> None:
        self.register("invalid-section", session_id="invalid-section", status="todo")
        prompt = bootstrap_prompt(
            fixture_creation_id("invalid-section"), section_id="not-a-uuid"
        )
        result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "invalid-section",
                "turn_id": "invalid-section-turn",
                "prompt": prompt,
            }
        )
        self.assertNotIn("codex_app__move_thread_to_sidebar_section", result.stdout)
        self.assertNotIn("codex_app__set_thread_pinned", result.stdout)

    def test_escaped_delegated_bootstrap_is_excluded_from_summary(self) -> None:
        self.run_cli("init")
        prompt = f"""<codex_delegation>
  <source_thread_id>parent</source_thread_id>
  <input>{ESCAPED_BOOTSTRAP_PROMPT}
</input>
</codex_delegation>"""

        result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-1",
                "turn_id": "escaped-first-turn",
                "prompt": prompt,
            }
        )

        self.assertIn("codex_app__set_thread_pinned", result.stdout)
        self.assertIn("codex_app__set_thread_title", result.stdout)
        state = self.show(CREATION_ID)
        self.assertEqual(state["description"], "Write a compact database proof.")
        self.assertNotIn("agtask-bootstrap", json.dumps(state))

        self.register("invalid-escaped", status="todo")
        self.run_cli(
            "record-turn",
            "--id",
            "invalid-escaped",
            "--role",
            "user",
            "--turn-id",
            "initial-turn",
            "--content",
            FORK_PROMPT,
        )
        invalid_task = "Task:\nWrite proof"
        invalid_trailer = ESCAPED_BOOTSTRAP_PROMPT[
            ESCAPED_BOOTSTRAP_PROMPT.index("&lt;agtask-bootstrap") :
        ].replace(
            '"pin":true',
            '"pin": true',
        )
        invalid_prompt = f"""<codex_delegation>
  <source_thread_id>parent</source_thread_id>
  <input>{invalid_task}

{invalid_trailer}
</input>
</codex_delegation>"""
        invalid_result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "invalid-escaped",
                "turn_id": "invalid-escaped-turn",
                "prompt": invalid_prompt,
            }
        )

        self.assertNotIn("codex_app__set_thread_pinned", invalid_result.stdout)
        self.assertNotIn("codex_app__set_thread_title", invalid_result.stdout)
        invalid_state = self.show("invalid-escaped")
        self.assertEqual(
            invalid_state["description"], "Write a compact database proof."
        )
        invalid_user_rows = [
            row for row in invalid_state["rollouts"] if row["role"] == "user"
        ]
        self.assertEqual(len(invalid_user_rows), 2)
        self.assertIn("agtask-bootstrap", invalid_user_rows[0]["message"])

    def test_resolve_create_rejects_conflicting_or_empty_inputs(self) -> None:
        cases = [
            (
                ("resolve-create", "--worktree", "true", "--worktree", "false"),
                "conflicting worktree values: true, false",
            ),
            (
                ("resolve-create", "--model", "gpt-5.6-sol", "--model", "inherit"),
                "conflicting model values: gpt-5.6-sol, inherit",
            ),
            (
                ("resolve-create", "--pin", "true", "--nopin"),
                "conflicting pin values: true, false",
            ),
            (
                ("resolve-create", "--kind", "main", "--kind", "child"),
                "conflicting kind values: main, child",
            ),
            (
                ("resolve-create", "--project", "one", "--project", "two"),
                "conflicting project values: one, two",
            ),
            (("resolve-create", "--model", ""), "model must not be empty"),
            (("resolve-create", "--project", ""), "project must not be empty"),
            (
                ("resolve-create", "--project", " padded "),
                "project must not contain surrounding whitespace",
            ),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    *arguments[1:],
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
        for title, message in [
            ("", "bootstrap title must not be empty"),
            (" padded ", "bootstrap title must not contain surrounding whitespace"),
            ("two\nlines", "bootstrap title must be one line"),
        ]:
            with self.subTest(title=title):
                result = self.run_cli(
                    "resolve-create", "--title", title, check=False
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
        self.assertFalse(self.db_path.exists())

    def test_resolve_create_rejects_incomplete_or_invalid_creation_plans(self) -> None:
        cases = [
            (
                (
                    "--mode",
                    "clean",
                    "--parent-session-id",
                    "parent-thread",
                    "--task",
                    "Write a compact database proof.",
                ),
                "clean creation with --task requires --project-id",
            ),
            (
                (
                    "--mode",
                    "clean",
                    "--parent-session-id",
                    "parent-thread",
                    "--task",
                    "Write a compact database proof.",
                    "--project-id",
                    " padded ",
                ),
                "project_id must not contain surrounding whitespace",
            ),
            (
                (
                    "--kind",
                    "main",
                    "--task",
                    "Write a compact database proof.",
                ),
                "--task is only valid for child creation",
            ),
            (
                (
                    "--mode",
                    "fork",
                    "--parent-session-id",
                    "parent-thread",
                    "--task",
                    "Write a compact database proof.",
                ),
                "--task is only supported for clean child creation",
            ),
            (
                (
                    "--parent-session-id",
                    "parent-thread",
                    "--project-id",
                    "saved-project-id",
                ),
                "--project-id and --thinking require --task",
            ),
            (
                ("--parent-session-id", "parent-thread", "--thinking", "high"),
                "--project-id and --thinking require --task",
            ),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(
                    "resolve-create",
                    "--title",
                    "agtask/database-proof",
                    *arguments,
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
        self.assertFalse(self.db_path.exists())

    def test_configuration_merges_home_then_project_and_cli_wins(self) -> None:
        project = self.root / "project"
        home_config = self.write_config(
            self.home,
            {
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
                    "OnPreClose": {"prompt": "home prepare"},
                    "OnPostClose": {"prompt": "home close"},
                },
            },
        )
        project_config = self.write_config(
            project,
            {
                "defaults": {"project": "local-project", "model": "local-model"},
                "hooks": {"OnCreate": {"prompt": "local create"}},
            },
        )

        configuration = json.loads(
            self.run_cli("config", "--json", cwd=project).stdout
        )
        self.assertEqual(
            configuration["sources"],
            [str(home_config.resolve()), str(project_config.resolve())],
        )
        self.assertEqual(
            configuration["precedence"],
            [str(home_config.resolve()), str(project_config.resolve())],
        )
        self.assertEqual(
            configuration["defaults"],
            {
                "mode": "fork",
                "kind": "main",
                "project": "local-project",
                "worktree": True,
                "model": "local-model",
                "pin": False,
            },
        )
        self.assertEqual(
            configuration["hooks"],
            {
                "OnCreate": {"prompt": "local create"},
                "OnPreClose": {"prompt": "home prepare"},
                "OnPostClose": {"prompt": "home close"},
            },
        )

        resolved = json.loads(
            self.run_cli(
                "resolve-create",
                "--title",
                "agtask/configured-title",
                "--json",
                cwd=project,
            ).stdout
        )
        resolved_id = resolved.pop("id")
        self.assertEqual(str(uuid.UUID(resolved_id)), resolved_id)
        self.assertEqual(
            resolved,
            {
                "bootstrap_args": {
                    "pin": False,
                    "title": "agtask/configured-title",
                },
                "bootstrap_trailer": """<agtask-bootstrap version="1">
{"pin":false,"title":"agtask/configured-title"}
</agtask-bootstrap>""",
                "environment": {"type": "worktree"},
                "include_model": True,
                "hook_prompts": [
                    {
                        "event": "OnCreate",
                        "prompt": "local create",
                        "source": str(project_config.resolve()),
                    }
                ],
                "kind": "main",
                "mode": "fork",
                "model": "local-model",
                "pin": False,
                "project": "local-project",
                "title": "agtask/configured-title",
                "worktree": True,
            },
        )
        explicit = json.loads(
            self.run_cli(
                "resolve-create",
                "--mode",
                "clean",
                "--kind",
                "child",
                "--project",
                "explicit",
                "--title",
                "agtask/explicit-title",
                "--parent-session-id",
                "parent-thread",
                "--worktree",
                "false",
                "--model",
                "inherit",
                "--pin",
                "true",
                "--json",
                cwd=project,
            ).stdout
        )
        explicit_id = explicit["id"]
        self.assertEqual(str(uuid.UUID(explicit_id)), explicit_id)
        self.assertEqual(
            explicit,
            {
                "bootstrap_args": {
                    "id": explicit_id,
                    "parent_session_id": "parent-thread",
                    "pin": True,
                    "project": "explicit",
                    "section_id": "pinned",
                    "title": "agtask/explicit-title",
                },
                "bootstrap_trailer": """<agtask-bootstrap version="2">
{"id":"%s","parent_session_id":"parent-thread","pin":true,"project":"explicit","section_id":"pinned","title":"agtask/explicit-title"}
</agtask-bootstrap>""".replace("%s", explicit_id),
                "environment": {"type": "local"},
                "include_model": False,
                "hook_prompts": [
                    {
                        "event": "OnCreate",
                        "prompt": "local create",
                        "source": str(project_config.resolve()),
                    }
                ],
                "kind": "child",
                "mode": "clean",
                "model": "inherit",
                "pin": True,
                "project": "explicit",
                "title": "agtask/explicit-title",
                "worktree": False,
                "id": explicit_id,
            },
        )
        project_config.write_text(
            json.dumps(
                {
                    "defaults": {},
                    "hooks": {"OnCreate": {"prompt": ""}},
                }
            )
        )
        disabled = json.loads(
            self.run_cli(
                "resolve-create",
                "--title",
                "agtask/disabled-prompt",
                "--json",
                cwd=project,
            ).stdout
        )
        self.assertEqual(disabled["hook_prompts"], [])
        self.assertFalse(self.db_path.exists())

    def test_backend_configuration_merges_home_and_project(self) -> None:
        project = self.root / "backend-project"
        self.write_config(
            self.home,
            {
                "defaults": {"mode": "fork"},
                "backend": {
                    "mode": "local",
                    "sites": {
                        "profile": "home-profile",
                        "url": "https://example.openai.chatgpt.site",
                        "project_id": "appgprj_home",
                        "credential_ref": "keychain:agtask/home",
                    },
                },
            },
        )
        self.write_config(
            project,
            {
                "backend": {
                    "mode": "sites",
                    "sites": {"profile": "project-profile"},
                }
            },
        )

        configuration = json.loads(
            self.run_cli("config", "--json", cwd=project).stdout
        )
        self.assertEqual(configuration["defaults"]["mode"], "fork")
        self.assertEqual(
            configuration["backend"],
            {
                "mode": "sites",
                "sites": {
                    "profile": "project-profile",
                    "url": "https://example.openai.chatgpt.site",
                    "project_id": "appgprj_home",
                    "credential_ref": "keychain:agtask/home",
                },
            },
        )
        self.assertFalse(self.db_path.exists())

    def test_backend_configuration_preserves_unconfigured_json_shape(self) -> None:
        configuration = json.loads(self.run_cli("config", "--json").stdout)
        self.assertEqual(
            set(configuration), {"defaults", "hooks", "sources", "precedence"}
        )
        self.assertNotIn("backend", configuration)

    def test_backend_configuration_validates_nested_sites_values(self) -> None:
        project = self.root / "invalid-backend-project"
        cases = [
            ({"backend": None}, "backend must be an object"),
            ({"backend": "sites"}, "backend must be an object"),
            ({"backend": {"unexpected": True}}, "unknown configuration backend key"),
            ({"backend": {"mode": "fork"}}, "backend.mode must be local or sites"),
            ({"backend": {"mode": None}}, "backend.mode must be local or sites"),
            ({"backend": {"sites": []}}, "backend.sites must be an object"),
            (
                {"backend": {"sites": {"token": "secret"}}},
                "unknown configuration backend.sites key",
            ),
            (
                {"backend": {"sites": {"profile": ""}}},
                "backend.sites.profile must be a nonempty string",
            ),
            (
                {"backend": {"sites": {"project_id": 123}}},
                "backend.sites.project_id must be a nonempty string",
            ),
            (
                {"backend": {"sites": {"credential_ref": " padded "}}},
                "backend.sites.credential_ref must be a nonempty string",
            ),
            (
                {"backend": {"sites": {"url": "http://example.com"}}},
                "backend.sites.url must be an HTTPS URL",
            ),
            (
                {"backend": {"sites": {"url": "https://token@example.com"}}},
                "backend.sites.url must be an HTTPS URL",
            ),
            (
                {"backend": {"sites": {"url": "https://example.com/?token=x"}}},
                "backend.sites.url must be an HTTPS URL",
            ),
        ]
        for document, message in cases:
            with self.subTest(document=document):
                self.write_config(project, document)
                result = self.run_cli("config", "--json", cwd=project, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
        self.assertFalse(self.db_path.exists())

    def test_backend_mode_precedence_and_creation_mode_are_independent(self) -> None:
        self.write_config(
            self.home,
            {"backend": {"mode": "sites"}, "defaults": {"mode": "fork"}},
        )

        configured_sites = self.run_cli("init", "--json", check=False)
        self.assertEqual(configured_sites.returncode, 1)
        self.assertIn("Sites backend is selected", configured_sites.stderr)
        self.assertFalse(self.db_path.exists())

        environment_local = self.env | {"AGTASK_BACKEND_MODE": "local"}
        initialized = json.loads(
            self.run_cli("init", "--json", env=environment_local).stdout
        )
        self.assertEqual(initialized["database"], str(self.db_path))

        explicit_sites = self.run_cli(
            "--mode", "sites", "list", "--json", env=environment_local, check=False
        )
        self.assertEqual(explicit_sites.returncode, 1)
        self.assertIn("cannot use the local ledger", explicit_sites.stderr)

        environment_sites = self.env | {"AGTASK_BACKEND_MODE": "sites"}
        explicit_local = json.loads(
            self.run_cli(
                "--mode",
                "local",
                "resolve-create",
                "--mode",
                "clean",
                "--kind",
                "main",
                "--title",
                "agtask/backend-mode",
                "--json",
                env=environment_sites,
            ).stdout
        )
        self.assertEqual(explicit_local["mode"], "clean")
        self.assertNotIn("backend_mode", explicit_local)

        invalid_environment = self.env | {"AGTASK_BACKEND_MODE": "fork"}
        invalid = self.run_cli("config", "--json", env=invalid_environment, check=False)
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("AGTASK_BACKEND_MODE must be local or sites", invalid.stderr)

        override_invalid_environment = self.run_cli(
            "--mode", "local", "config", "--json", env=invalid_environment
        )
        self.assertEqual(override_invalid_environment.returncode, 0)

    def test_sites_backend_refuses_task_operations_without_local_fallback(self) -> None:
        self.write_config(self.home, {"backend": {"mode": "sites"}})
        cases = [
            ("init", "--json"),
            ("list", "--json"),
            ("dashboard", "--json"),
            (
                "register",
                "--id",
                "sites-task",
                "--session-id",
                "sites-session",
                "--kind",
                "main",
                "--project",
                "sites-project",
                "--title",
                "blocked",
                "--json",
            ),
        ]
        for arguments in cases:
            with self.subTest(command=arguments[0]):
                result = self.run_cli(*arguments, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn("cannot use the local ledger", result.stderr)
                self.assertFalse(self.db_path.exists())

        creation = json.loads(
            self.run_cli(
                "resolve-create", "--kind", "main", "--title", "planned", "--json"
            ).stdout
        )
        self.assertEqual(creation["title"], "planned")
        self.assertFalse(self.db_path.exists())

        cache = json.loads(
            self.run_cli("section-cache", "get", "--session-id", "sites-session", "--json").stdout
        )
        self.assertEqual(cache["state"], "miss")
        self.assertFalse(self.db_path.exists())

    def test_sites_backend_hook_fails_open_without_touching_local_ledger(self) -> None:
        self.write_config(self.home, {"backend": {"mode": "sites"}})
        project = self.root / "hook-project"
        self.write_config(project, {"backend": {"mode": "local"}})
        plan = json.loads(
            self.run_cli(
                "--mode",
                "local",
                "resolve-create",
                "--parent-session-id",
                "parent-session",
                "--title",
                "agtask/sites-hook",
                "--json",
            ).stdout
        )
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "sites-hook-session",
            "turn_id": "sites-hook-turn",
            "prompt": "Task:\nDo not create a local task.\n\n"
            + plan["bootstrap_trailer"],
        }

        sites_hook = self.run_cli("hook", input_text=json.dumps(payload), cwd=project)
        self.assertEqual(sites_hook.returncode, 0)
        self.assertEqual(sites_hook.stdout, "")
        self.assertEqual(sites_hook.stderr, "")
        self.assertFalse(self.db_path.exists())

        local_hook = self.run_cli(
            "--mode", "local", "hook", input_text=json.dumps(payload), cwd=project
        )
        self.assertEqual(local_hook.returncode, 0)
        self.assertTrue(self.db_path.exists())

    def test_sites_client_authenticates_remote_operations_without_local_database(self) -> None:
        thread_id = fixture_creation_id("remote-sites-task")
        threads: dict[str, dict[str, object]] = {}

        def respond(request: dict[str, object]) -> tuple[int, object]:
            operation = str(request["path"]).rsplit("/", 1)[-1]
            payload = request["payload"]
            self.assertIsInstance(payload, dict)
            if operation == "register":
                task = {
                    "id": payload["id"],
                    "session_id": payload["session_id"],
                    "parent_session_id": payload.get("parent_session_id"),
                    "kind": payload["kind"],
                    "project": payload["project"],
                    "title": payload["title"],
                    "description": payload.get("description", ""),
                    "status": payload["status"],
                    "rollouts": [],
                    "files": [],
                    "created": "2026-08-09T00:00:00Z",
                    "updated": "2026-08-09T00:00:00Z",
                    "closed": None,
                    "task_created": True,
                }
                threads[str(task["session_id"])] = task
                return 200, task
            if operation == "list":
                return 200, list(threads.values())
            task = threads.get(str(payload.get("session_id")))
            if task is None:
                task = next(
                    (entry for entry in threads.values() if entry["id"] == payload.get("id")),
                    None,
                )
            if task is None:
                return 404, {"error": "not found"}
            if operation == "record-turn":
                task["rollouts"].insert(
                    0,
                    {
                        "role": payload["role"],
                        "turn_id": payload["turn_id"],
                        "message": payload["content"],
                    },
                )
            return 200, task

        with mock_sites_server(self.root, respond) as (url, certificate, requests):
            credentials = self.root / "credentials.json"
            credentials.write_text(
                json.dumps({"bypass_token": "platform-secret", "app_token": "app-secret"})
            )
            credentials.chmod(0o600)
            self.write_config(
                self.home,
                {
                    "backend": {
                        "mode": "sites",
                        "sites": {
                            "url": url,
                            "credential_ref": f"file:{credentials}",
                        },
                    },
                    "hooks": {"OnCreate": {"prompt": "Run hosted setup."}},
                },
            )
            environment = self.env | {"SSL_CERT_FILE": str(certificate)}
            full_prompt = "Task:\n" + "x" * 300 + " NEVER_SEND_FULL_PROMPT"
            registered = json.loads(
                self.run_cli(
                    "register",
                    "--id",
                    thread_id,
                    "--session-id",
                    "sites-session",
                    "--kind",
                    "main",
                    "--project",
                    "agtask",
                    "--title",
                    "Hosted task",
                    "--initial-prompt",
                    full_prompt,
                    "--json",
                    env=environment,
                ).stdout
            )
            self.assertEqual(registered["id"], thread_id)
            self.assertEqual(registered["created"], "2026-08-09T00:00:00Z")
            self.assertNotIn("task_created", registered)
            self.assertEqual(
                registered["hook_prompts"],
                [
                    {
                        "event": "OnCreate",
                        "prompt": "Run hosted setup.",
                        "source": str((self.home / ".agtask.json").resolve()),
                    }
                ],
            )
            first = requests[0]
            self.assertEqual(first["path"], "/api/agtask/v1/operations/register")
            headers = {key.lower(): value for key, value in first["headers"].items()}
            self.assertEqual(headers["oai-sites-authorization"], "Bearer platform-secret")
            self.assertEqual(headers["authorization"], "Bearer app-secret")
            self.assertRegex(headers["idempotency-key"], r"^[0-9a-f]{64}$")
            self.assertNotIn("NEVER_SEND_FULL_PROMPT", first["raw"])
            self.assertLessEqual(len(first["payload"]["initial_prompt"]), 240)
            self.assertEqual(
                first["payload"]["initial_prompt"], first["payload"]["description"]
            )

            listed = json.loads(self.run_cli("list", "--json", env=environment).stdout)
            self.assertEqual([task["id"] for task in listed], [thread_id])
            shown = json.loads(
                self.run_cli(
                    "show", "--session-id", "sites-session", "--json", env=environment
                ).stdout
            )
            self.assertEqual(shown["title"], "Hosted task")
            recorded = json.loads(
                self.run_cli(
                    "record-turn",
                    "--session-id",
                    "sites-session",
                    "--role",
                    "assistant",
                    "--turn-id",
                    "turn-1",
                    "--content",
                    "Blocked: " + "y" * 300 + " NEVER_SEND_ASSISTANT",
                    "--json",
                    env=environment,
                ).stdout
            )
            self.assertEqual(recorded["rollouts"][0]["role"], "assistant")
            self.assertNotIn("NEVER_SEND_ASSISTANT", requests[-1]["raw"])
            self.assertLessEqual(len(requests[-1]["payload"]["content"]), 240)
            first_key = {
                key.lower(): value for key, value in requests[-1]["headers"].items()
            }["idempotency-key"]
            self.run_cli(
                "record-turn",
                "--session-id",
                "sites-session",
                "--role",
                "assistant",
                "--turn-id",
                "turn-1",
                "--content",
                "Blocked: " + "y" * 300 + " NEVER_SEND_ASSISTANT",
                "--json",
                env=environment,
            )
            retry_key = {
                key.lower(): value for key, value in requests[-1]["headers"].items()
            }["idempotency-key"]
            self.assertEqual(first_key, retry_key)
            self.assertFalse(self.db_path.exists())

    def test_sites_client_rejects_insecure_credentials_and_redacts_server_errors(self) -> None:
        credentials = self.root / "credentials.json"
        credentials.write_text(
            json.dumps({"bypass_token": "private-bypass", "app_token": "private-app"})
        )
        credentials.chmod(0o644)
        self.write_config(
            self.home,
            {
                "backend": {
                    "mode": "sites",
                    "sites": {
                        "url": "https://example.openai.chatgpt.site",
                        "credential_ref": f"file:{credentials}",
                    },
                }
            },
        )
        insecure = self.run_cli("list", "--json", check=False)
        self.assertEqual(insecure.returncode, 1)
        self.assertIn("permissions 0600", insecure.stderr)
        self.assertNotIn("private-bypass", insecure.stderr)
        self.assertFalse(self.db_path.exists())

        credentials.chmod(0o600)
        link = self.root / "credentials-link.json"
        link.symlink_to(credentials)
        self.write_config(
            self.home,
            {
                "backend": {
                    "mode": "sites",
                    "sites": {
                        "url": "https://example.openai.chatgpt.site",
                        "credential_ref": f"file:{link}",
                    },
                }
            },
        )
        symlink = self.run_cli("list", "--json", check=False)
        self.assertEqual(symlink.returncode, 1)
        self.assertIn("cannot be read safely", symlink.stderr)

        def reject(request: dict[str, object]) -> tuple[int, object]:
            return 403, {"error": "private-bypass private-app confidential-server-error"}

        with mock_sites_server(self.root, reject) as (url, certificate, requests):
            self.write_config(
                self.home,
                {
                    "backend": {
                        "mode": "sites",
                        "sites": {
                            "url": url,
                            "credential_ref": f"file:{credentials}",
                        },
                    }
                },
            )
            result = self.run_cli(
                "list",
                "--json",
                env=self.env | {"SSL_CERT_FILE": str(certificate)},
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("HTTP 403", result.stderr)
            for secret in ("private-bypass", "private-app", "confidential-server-error"):
                self.assertNotIn(secret, result.stderr)
            self.assertEqual(len(requests), 1)
            self.assertFalse(self.db_path.exists())

    def test_sites_client_remote_hooks_register_and_record_without_local_database(self) -> None:
        task_id = fixture_creation_id("sites-hook-task")

        def respond(request: dict[str, object]) -> tuple[int, object]:
            payload = request["payload"]
            task = {
                "id": task_id,
                "session_id": "remote-hook-session",
                "title": "agtask/remote-hook",
                "description": "Track a hosted task.",
                "status": "active",
                "rollouts": [],
                "files": [],
            }
            if str(request["path"]).endswith("/record-turn"):
                task["rollouts"] = [
                    {
                        "role": payload["role"],
                        "turn_id": payload["turn_id"],
                        "message": payload["content"],
                    }
                ]
            return 200, task

        with mock_sites_server(self.root, respond) as (url, certificate, requests):
            self.write_config(
                self.home, {"backend": {"mode": "sites", "sites": {"url": url}}}
            )
            environment = self.env | {
                "SSL_CERT_FILE": str(certificate),
                "AGTASK_SITES_BYPASS_TOKEN": "environment-bypass",
                "AGTASK_SITES_APP_TOKEN": "environment-app",
            }
            prompt = bootstrap_prompt(
                task_id,
                parent_session_id="remote-parent",
                title="agtask/remote-hook",
                prompt="Task:\nTrack a hosted task.",
            )
            hook = self.run_cli(
                "hook",
                input_text=json.dumps(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": "remote-hook-session",
                        "turn_id": "hook-turn-1",
                        "prompt": prompt,
                    }
                ),
                env=environment,
            )
            self.assertIn("Tracked agtask thread: agtask/remote-hook", self.hook_context(hook))
            self.assertEqual(
                [str(request["path"]).rsplit("/", 1)[-1] for request in requests],
                ["register", "record-turn"],
            )
            self.assertNotIn("<agtask-bootstrap", requests[0]["raw"])
            self.assertNotIn("<agtask-bootstrap", requests[1]["raw"])

            stop = self.run_cli(
                "hook",
                input_text=json.dumps(
                    {
                        "hook_event_name": "Stop",
                        "session_id": "remote-hook-session",
                        "turn_id": "hook-turn-1",
                        "last_assistant_message": "Blocked: awaiting hosted review.",
                    }
                ),
                env=environment,
            )
            self.assertEqual(stop.stdout, "")
            self.assertEqual(requests[-1]["payload"]["role"], "assistant")
            self.assertFalse(self.db_path.exists())

    def test_sites_client_never_follows_authenticated_redirects(self) -> None:
        def redirect(request: dict[str, object]) -> tuple[int, object, dict[str, str]]:
            return 302, {"error": "redirect"}, {"Location": "https://localhost/stolen"}

        with mock_sites_server(self.root, redirect) as (url, certificate, requests):
            self.write_config(
                self.home, {"backend": {"mode": "sites", "sites": {"url": url}}}
            )
            environment = self.env | {
                "SSL_CERT_FILE": str(certificate),
                "AGTASK_SITES_BYPASS_TOKEN": "redirect-bypass-secret",
                "AGTASK_SITES_APP_TOKEN": "redirect-app-secret",
            }
            result = self.run_cli("list", "--json", env=environment, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn("HTTP 302", result.stderr)
            self.assertEqual(len(requests), 1)
            self.assertNotIn("redirect-bypass-secret", result.stderr)
            self.assertNotIn("redirect-app-secret", result.stderr)
            self.assertFalse(self.db_path.exists())

    def test_sites_client_dashboard_opens_hosted_url_without_local_server(self) -> None:
        url = "https://agtask.example.openai.chatgpt.site"
        self.write_config(
            self.home, {"backend": {"mode": "sites", "sites": {"url": url}}}
        )
        result = self.run_cli("dashboard", "--no-open")
        self.assertEqual(result.stdout.strip(), url)
        self.assertFalse(self.db_path.exists())

        invalid = self.run_cli("dashboard", "--json", "--no-open", check=False)
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("cannot be used together", invalid.stderr)

        missing_secret = self.run_cli(
            "list",
            "--json",
            env=self.env | {"AGTASK_SITES_BYPASS_TOKEN": "missing-app-token"},
            check=False,
        )
        self.assertEqual(missing_secret.returncode, 1)
        self.assertIn("requires both", missing_secret.stderr)
        self.assertNotIn("missing-app-token", missing_secret.stderr)
        self.assertFalse(self.db_path.exists())

    def test_hook_backend_refuses_project_sites_without_explicit_local_override(self) -> None:
        self.write_config(self.home, {"backend": {"mode": "local"}})
        project = self.root / "incidental-hook-project"
        self.write_config(project, {"backend": {"mode": "sites"}})
        plan = json.loads(
            self.run_cli(
                "--mode",
                "local",
                "resolve-create",
                "--parent-session-id",
                "parent-session",
                "--title",
                "agtask/local-hook",
                "--json",
                cwd=project,
            ).stdout
        )
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "local-hook-session",
            "turn_id": "local-hook-turn",
            "prompt": "Task:\nCreate the local task.\n\n"
            + plan["bootstrap_trailer"],
        }

        result = self.run_cli("hook", input_text=json.dumps(payload), cwd=project)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.db_path.exists())

        environment_override = self.run_cli(
            "hook",
            input_text=json.dumps(payload),
            cwd=project,
            env=self.env | {"AGTASK_BACKEND_MODE": "local"},
        )
        self.assertEqual(environment_override.returncode, 0)
        self.assertTrue(self.db_path.exists())

    def test_lifecycle_prompts_are_structured_at_prepare_and_post_close_boundaries(self) -> None:
        project = self.root / "prompt-project"
        local_config = self.write_config(
            project,
            {
                "defaults": {},
                "hooks": {
                    "OnCreate": {"prompt": "Run create setup."},
                    "OnPreClose": {"prompt": "Prepare close."},
                    "OnPostClose": {"prompt": "Report close."},
                },
            },
        )
        self.run_cli("init", cwd=project)
        created = json.loads(
            self.run_cli(
                "register",
                "--id",
                "prompt-thread",
                "--session-id",
                "prompt-thread",
                "--parent-session-id",
                "parent",
                "--kind",
                "child",
                "--project",
                "agtask",
                "--title",
                "prompt thread",
                "--initial-prompt",
                "Task:\nprompt lifecycle",
                "--description",
                "prompt lifecycle",
                "--status",
                "todo",
                "--json",
                cwd=project,
            ).stdout
        )
        self.assertEqual(
            created["hook_prompts"],
            [
                {
                    "event": "OnCreate",
                    "prompt": "Run create setup.",
                    "source": str(local_config.resolve()),
                }
            ],
        )
        self.assertEqual(
            [(row["role"], row["message"]) for row in created["rollouts"]],
            [("meta", "thread.created")],
        )
        repeated = json.loads(
            self.run_cli(
                "register",
                "--id",
                "prompt-thread",
                "--session-id",
                "prompt-thread",
                "--parent-session-id",
                "parent",
                "--kind",
                "child",
                "--project",
                "agtask",
                "--title",
                "prompt thread",
                "--initial-prompt",
                "Task:\nprompt lifecycle",
                "--description",
                "prompt lifecycle",
                "--status",
                "todo",
                "--json",
                cwd=project,
            ).stdout
        )
        self.assertEqual(repeated["hook_prompts"], [])

        prepared = json.loads(
            self.run_cli(
                "close", "--id", "prompt-thread", "--prepare", "--json", cwd=project
            ).stdout
        )
        self.assertEqual(prepared["status"], "merging")
        self.assertIsNone(prepared["closed"])
        self.assertEqual(
            prepared["hook_prompts"],
            [
                {
                    "event": "OnPreClose",
                    "prompt": "Prepare close.",
                    "source": str(local_config.resolve()),
                }
            ],
        )
        self.assertEqual(
            [row["message"] for row in reversed(prepared["rollouts"])],
            ["thread.created", "status:todo->merging"],
        )

        closed = json.loads(
            self.run_cli(
                "close",
                "--id",
                "prompt-thread",
                "--merge-token",
                prepared["merge_claim"]["token"],
                "--json",
                cwd=project,
            ).stdout
        )
        self.assertEqual(
            closed["hook_prompts"],
            [
                {
                    "event": "OnPostClose",
                    "prompt": "Report close.",
                    "source": str(local_config.resolve()),
                }
            ],
        )
        self.assertEqual(
            [row["message"] for row in reversed(closed["rollouts"])],
            [
                "thread.created",
                "status:todo->merging",
                "status:merging->done",
                "finalization:completed",
            ],
        )
        retried = json.loads(
            self.run_cli(
                "close", "--id", "prompt-thread", "--json", cwd=project
            ).stdout
        )
        self.assertEqual(retried["hook_prompts"], [])

    def test_init_creates_default_global_configuration_once(self) -> None:
        configuration = self.home / ".agtask.json"
        initialized = json.loads(self.run_cli("init", "--json").stdout)

        self.assertTrue(initialized["configuration_created"])
        self.assertEqual(initialized["configuration"], str(configuration))
        self.assertEqual(stat.S_IMODE(configuration.stat().st_mode), 0o600)
        self.assertEqual(
            json.loads(configuration.read_text()),
            {
                "defaults": {},
                "hooks": {
                    "OnCreate": {"prompt": ""},
                    "OnPreClose": {
                        "prompt": (
                            "Read and follow $agtask's bundled "
                            "./references/onclose.md OnPreClose workflow. "
                            "Finalize Git state without removing the current worktree."
                        )
                    },
                    "OnPostClose": {"prompt": ""},
                },
            },
        )

        configuration.write_text(
            json.dumps(
                {
                    "defaults": {"project": "preserved"},
                    "hooks": {"OnPreClose": {"prompt": "custom"}},
                }
            )
        )
        repeated = json.loads(self.run_cli("init", "--json").stdout)
        self.assertFalse(repeated["configuration_created"])
        self.assertEqual(
            json.loads(configuration.read_text()),
            {
                "defaults": {"project": "preserved"},
                "hooks": {"OnPreClose": {"prompt": "custom"}},
            },
        )

    def test_configuration_rejects_malformed_and_unknown_values(self) -> None:
        project = self.root / "bad-project"
        cases = [
            ("[]", "configuration must be a JSON object"),
            ('{"defaults":', "invalid JSON configuration"),
            ('{"unknown": {}}', "unknown configuration key"),
            ('{"defaults": {"pin": "yes"}}', "default pin must be a boolean"),
            ('{"hooks": {"OnCreate": {}}}', "OnCreate.prompt must be a string"),
            ('{"hooks": {"Typo": {"prompt": "x"}}}', "unknown configuration hook"),
        ]
        for content, message in cases:
            with self.subTest(content=content):
                project.mkdir(parents=True, exist_ok=True)
                (project / ".agtask.json").write_text(content)
                result = self.run_cli("config", "--json", cwd=project, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)

    def test_schema_permissions_and_immediate_reopen(self) -> None:
        result = self.run_cli("init", "--json")
        self.assertEqual(json.loads(result.stdout)["schema_version"], 8)
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.db_path.stat().st_mode), 0o600)

        # Regression: a clean WAL-mode ledger has no sidecars after init, but the
        # mandatory read-only preflight must still allow the next command.
        state = self.register()
        self.assertEqual(state["id"], fixture_creation_id("thread-1"))
        self.assertEqual(state["parent_session_id"], "parent-thread")

        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)
            objects = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%'"
                )
            }
            self.assertEqual(
                objects,
                {
                    "thread",
                    "thread_created_idx",
                    "thread_status_updated_idx",
                    "thread_parent_session_idx",
                    "thread_session_id_idx",
                    "thread_project_merging_idx",
                    "project_merge_claim",
                    "project_merge_claim_owner_idx",
                    "project_merge_claim_token_idx",
                    "rollout",
                    "rollout_thread_order_idx",
                    "rollout_turn_event_idx",
                    "rollout_meta_event_idx",
                    "thread_fts",
                    "thread_fts_data",
                    "thread_fts_idx",
                    "thread_fts_docsize",
                    "thread_fts_config",
                    "thread_ai",
                    "thread_ad",
                    "thread_au",
                    "attachment",
                    "attachment_thread_created_idx",
                    "views",
                },
            )
            self.assertEqual(
                [row[1] for row in connection.execute("PRAGMA table_info(thread)")],
                [
                    "id",
                    "session_id",
                    "parent_session_id",
                    "kind",
                    "project",
                    "title",
                    "description",
                    "created",
                    "updated",
                    "closed",
                    "status",
                ],
            )
            self.assertEqual(
                [row[1] for row in connection.execute("PRAGMA table_info(rollout)")],
                ["id", "created", "thread_id", "turn_id", "role", "message"],
            )
            self.assertEqual(
                [row[1] for row in connection.execute("PRAGMA table_info(views)")],
                ["id", "name", "filters", "created", "updated"],
            )
            today_view = connection.execute(
                "SELECT id,name,filters,created,updated FROM views WHERE id='today'"
            ).fetchone()
            self.assertIsNotNone(today_view)
            self.assertEqual(today_view[0:3], ("today", "Today", '{"created":"today","exclude_statuses":["done","drop"]}'))
            self.assertEqual(today_view[3], today_view[4])
            foreign_key = connection.execute("PRAGMA foreign_key_list(rollout)").fetchone()
            self.assertEqual(
                tuple(foreign_key[2:8]),
                ("thread", "thread_id", "id", "NO ACTION", "CASCADE", "NONE"),
            )
            thread_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='thread'"
            ).fetchone()[0]
            self.assertIn("parent_session_id <> session_id", thread_sql)
            self.assertIn("kind = 'main' AND parent_session_id IS NULL", thread_sql)
            self.assertIn("kind = 'child' AND parent_session_id IS NOT NULL", thread_sql)
            self.assertIn("status IN ('done', 'drop') AND closed IS NOT NULL", thread_sql)
            turn_index_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='rollout_turn_event_idx'"
            ).fetchone()[0]
            self.assertIn("UNIQUE INDEX", turn_index_sql)
            self.assertIn("role IN ('user', 'assistant')", turn_index_sql)

        with self.connect() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO thread VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "bad",
                        "bad-session",
                        "parent",
                        "child",
                        "agtask",
                        "bad",
                        "bad",
                        "now",
                        "now",
                        "now",
                        "active",
                    ),
                )
            invalid_topologies = [
                ("main-with-parent", "parent", "main", "agtask"),
                ("child-without-parent", None, "child", "agtask"),
                ("child-without-project", "parent", "child", ""),
            ]
            for thread_id, parent_session_id, kind, project in invalid_topologies:
                with self.subTest(thread_id=thread_id):
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(
                            "INSERT INTO thread VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                thread_id,
                                f"{thread_id}-session",
                                parent_session_id,
                                kind,
                                project,
                                "bad",
                                "bad",
                                "now",
                                "now",
                                None,
                                "active",
                            ),
                        )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO rollout(created,thread_id,turn_id,role,message) "
                    "VALUES ('now','thread-1','bad','system','bad')"
                )

    def test_attach_markdown_task_targets_new_child_instead_of_parent(self) -> None:
        self.run_cli("init")
        self.register(
            "parent",
            session_id="parent-session",
            parent_session_id=None,
            kind="main",
            title="Pilot coordination",
        )
        child = self.register(
            "note-child",
            session_id="child-session",
            parent_session_id="parent-session",
            title="Pilot coordination/investigate-claw",
            initial_prompt="Investigate the instructions in the Markdown note.",
            description="Investigate the instructions in the Markdown note.",
        )
        notes = self.root / "notes"
        notes.mkdir()
        note = notes / "pilot task.md"
        note.write_text(
            "---\n"
            "title: Investigate claw\n"
            "---\n"
            "Inspect the live tenant and report evidence.\n"
        )

        attached = json.loads(
            self.run_cli(
                "attach",
                note.name,
                "--session-id",
                "child-session",
                "--json",
                cwd=notes,
            ).stdout
        )

        self.assertEqual(attached["id"], child["id"])
        self.assertEqual(attached["session_id"], "child-session")
        self.assertEqual(attached["attachment"]["path"], str(note.resolve()))
        self.assertEqual(len(attached["files"]), 1)
        self.assertEqual(self.show("parent")["files"], [])
        self.assertEqual(
            note.read_text(),
            "---\n"
            "title: Investigate claw\n"
            "status: active\n"
            "source: codex://threads/child-session\n"
            "---\n"
            "Inspect the live tenant and report evidence.\n",
        )

    def test_attach_updates_frontmatter_and_tracks_file_idempotently(self) -> None:
        self.run_cli("init")
        self.register()
        self.run_cli(
            "status", "--id", "thread-1", "--status", "blocked", "--json"
        )
        notes = self.root / "notes"
        notes.mkdir()
        note = notes / "task note.md"
        note.write_text(
            "---\n"
            "title: Existing note\n"
            "status: old\n"
            "source: old-source\n"
            "---\n"
            "Body stays intact.\n"
        )
        note.chmod(0o640)

        attached = json.loads(
            self.run_cli(
                "attach",
                note.name,
                "--id",
                "thread-1",
                "--json",
                cwd=notes,
            ).stdout
        )

        self.assertTrue(attached["attached"])
        self.assertTrue(attached["file_changed"])
        resolved_note = note.resolve()
        self.assertEqual(attached["attachment"]["path"], str(resolved_note))
        self.assertEqual(attached["attachment"]["name"], note.name)
        self.assertEqual(
            attached["attachment"]["url"],
            f"vscode://file{quote(str(resolved_note), safe='/:')}",
        )
        self.assertEqual(attached["files"], [attached["attachment"]])
        self.assertEqual(stat.S_IMODE(note.stat().st_mode), 0o640)
        self.assertEqual(
            note.read_text(),
            "---\n"
            "title: Existing note\n"
            "status: blocked\n"
            "source: codex://threads/thread-1\n"
            "---\n"
            "Body stays intact.\n",
        )
        self.assertEqual(
            [row["message"] for row in attached["rollouts"]].count("attachment:added"),
            1,
        )

        repeated = json.loads(
            self.run_cli(
                "attach",
                str(note),
                "--session-id",
                "thread-1",
                "--json",
            ).stdout
        )
        self.assertFalse(repeated["attached"])
        self.assertFalse(repeated["file_changed"])
        self.assertEqual(
            [row["message"] for row in repeated["rollouts"]].count("attachment:added"),
            1,
        )

        plain = notes / "plain.md"
        plain.write_text("Plain body.\n")
        plain_result = json.loads(
            self.run_cli(
                "attach", str(plain), "--id", "thread-1", "--json"
            ).stdout
        )
        self.assertTrue(plain_result["attached"])
        self.assertEqual(
            plain.read_text(),
            "---\n"
            "status: blocked\n"
            "source: codex://threads/thread-1\n"
            "---\n"
            "Plain body.\n",
        )

        malformed = notes / "malformed.md"
        malformed.write_text("---\ntitle: no closing delimiter\n")
        before = malformed.read_bytes()
        rejected = self.run_cli(
            "attach",
            str(malformed),
            "--id",
            "thread-1",
            check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("unterminated YAML frontmatter", rejected.stderr)
        self.assertEqual(malformed.read_bytes(), before)
        with self.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM attachment WHERE path=?",
                    (str(malformed.resolve()),),
                ).fetchone()[0],
                0,
            )

    def test_empty_version_zero_initializes_and_default_path_ignores_v1(self) -> None:
        self.store.mkdir(mode=0o700)
        sqlite3.connect(self.db_path).close()
        self.db_path.chmod(0o600)
        self.run_cli("init")
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)

        home = self.root / "home"
        old_dir = home / ".llm" / "thread"
        old_dir.mkdir(parents=True, mode=0o700)
        old_database = old_dir / "thread.db"
        old_database.write_bytes(b"historical-v1-bytes")
        before = old_database.read_bytes()
        env = self.env.copy()
        env.pop("AGTASK_DB")
        env["HOME"] = str(home)
        initialized = json.loads(self.run_cli("init", "--json", env=env).stdout)
        self.assertEqual(
            initialized["database"], str(home / ".llm" / "agtask" / "ledger.db")
        )
        self.assertEqual(old_database.read_bytes(), before)

    def test_incompatible_ledger_refusal_preserves_bytes_mode_and_directory(self) -> None:
        cases: list[tuple[str, bytes | None, int | None]] = [
            ("v1", None, 1),
            ("v2", None, 2),
            ("drifted-v3", None, 3),
            ("drifted-v4", None, 4),
            ("drifted-v5", None, 5),
            ("unversioned-objects", None, 0),
            ("newer", None, 8),
            ("malformed", b"not a sqlite database", None),
        ]
        for name, raw_bytes, version in cases:
            with self.subTest(name=name):
                case_dir = self.root / name
                case_dir.mkdir(mode=0o700)
                path = case_dir / "ledger.db"
                if raw_bytes is not None:
                    path.write_bytes(raw_bytes)
                else:
                    with sqlite3.connect(path) as connection:
                        if name == "v1":
                            connection.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
                        elif name == "v2":
                            connection.execute("CREATE TABLE thread (id TEXT PRIMARY KEY)")
                        elif name in {"drifted-v3", "drifted-v4", "drifted-v5"}:
                            connection.execute("CREATE TABLE thread (id TEXT PRIMARY KEY)")
                        elif name == "unversioned-objects":
                            connection.execute("CREATE TABLE unexpected (value TEXT)")
                        connection.execute(f"PRAGMA user_version={version}")
                path.chmod(0o640)
                env = self.env | {"AGTASK_DB": str(path)}
                before_bytes = path.read_bytes()
                before_mode = stat.S_IMODE(path.stat().st_mode)
                before_entries = sorted(item.name for item in case_dir.iterdir())

                result = self.run_cli("init", env=env, check=False)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("incompatible ledger", result.stderr)
                self.assertIn("move it aside", result.stderr)
                self.assertEqual(path.read_bytes(), before_bytes)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), before_mode)
                self.assertEqual(
                    sorted(item.name for item in case_dir.iterdir()), before_entries
                )

    def test_exact_v5_ledger_migrates_to_v8_without_losing_data(self) -> None:
        runtime = runpy.run_path(str(CLI))
        self.store.mkdir(mode=0o700)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(runtime["V5_THREAD_DDL"])
            for statement in runtime["V6_DDL"][1:]:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO thread("
                "id,session_id,parent_session_id,kind,project,title,description,"
                "created,updated,closed,status"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fixture_creation_id("v5-thread"),
                    "v5-session",
                    "v5-parent",
                    "child",
                    "agtask",
                    "V5 task",
                    "preserve me",
                    "2026-01-01T00:00:00.000Z",
                    "2026-01-02T00:00:00.000Z",
                    None,
                    "active",
                ),
            )
            connection.execute(
                "INSERT INTO rollout(created,thread_id,turn_id,role,message) "
                "VALUES (?,?,?,?,?)",
                (
                    "2026-01-02T00:00:00.000Z",
                    fixture_creation_id("v5-thread"),
                    "v5-turn",
                    "user",
                    "preserve rollout",
                ),
            )
            connection.execute("PRAGMA user_version=5")
        self.db_path.chmod(0o600)

        migrated = json.loads(
            self.run_cli(
                "show",
                "--id",
                "v5-thread",
                "--json",
            ).stdout
        )

        self.assertEqual(migrated["description"], "preserve me")
        self.assertEqual(migrated["rollouts"][0]["message"], "preserve rollout")
        search = json.loads(self.run_cli("search", "V5 task", "--json").stdout)
        self.assertEqual([row["id"] for row in search], [fixture_creation_id("v5-thread")])
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            thread_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name='thread'"
            ).fetchone()[0]
            self.assertIn("'drop'", thread_sql)
        dropped = json.loads(
            self.run_cli(
                "status",
                "--id",
                "v5-thread",
                "--status",
                "drop",
                "--json",
            ).stdout
        )
        self.assertEqual(dropped["status"], "drop")
        self.assertIsNotNone(dropped["closed"])

    def test_exact_v6_ledger_migrates_to_v8(self) -> None:
        runtime = runpy.run_path(str(CLI))
        self.store.mkdir(mode=0o700)
        with sqlite3.connect(self.db_path) as connection:
            for statement in runtime["V6_DDL"]:
                connection.execute(statement)
            connection.execute("PRAGMA user_version=6")
        self.db_path.chmod(0o600)

        initialized = json.loads(self.run_cli("init", "--json").stdout)

        self.assertEqual(initialized["schema_version"], 8)
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual(
                [
                    row[1]
                    for row in connection.execute("PRAGMA table_info(attachment)")
                ],
                ["id", "created", "thread_id", "path"],
            )
            self.assertEqual(
                connection.execute("SELECT name FROM views WHERE id='today'").fetchone()[0],
                "Today",
            )

    def test_exact_v7_ledger_migrates_to_v8_and_seeds_today_view(self) -> None:
        runtime = runpy.run_path(str(CLI))
        self.store.mkdir(mode=0o700)
        with sqlite3.connect(self.db_path) as connection:
            for statement in (*runtime["V6_DDL"], *runtime["ATTACHMENT_DDL"]):
                connection.execute(statement)
            connection.execute("PRAGMA user_version=7")
        self.db_path.chmod(0o600)

        initialized = json.loads(self.run_cli("init", "--json").stdout)

        self.assertEqual(initialized["schema_version"], 8)
        with self.connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 8)
            self.assertEqual(
                [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT id,name,filters FROM views ORDER BY id"
                    )
                ],
                [
                    (
                        "today",
                        "Today",
                        '{"created":"today","exclude_statuses":["done","drop"]}',
                    )
                ],
            )

    def test_kind_project_and_parent_lineage_are_immutable(self) -> None:
        self.run_cli("init")
        main = self.register(
            "main", parent_session_id=None, kind="main", project="agtask"
        )
        self.assertIsNone(main["parent_session_id"])
        self.assertEqual(main["kind"], "main")
        self.assertEqual(main["project"], "agtask")
        preserved = self.register(
            "main", parent_session_id=None, kind="main", project="agtask"
        )
        self.assertEqual(preserved["updated"], main["updated"])

        main_with_parent = self.run_cli(
            "register",
            "--id",
            "other-main",
            "--session-id",
            "other-main",
            "--parent-session-id",
            "parent",
            "--kind",
            "main",
            "--project",
            "agtask",
            "--title",
            "main",
            "--description",
            "main",
            check=False,
        )
        self.assertEqual(main_with_parent.returncode, 1)
        self.assertIn("main thread must not have parent_session_id", main_with_parent.stderr)

        child_without_parent = self.run_cli(
            "register",
            "--id",
            "orphan",
            "--session-id",
            "orphan",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "orphan",
            "--description",
            "orphan",
            check=False,
        )
        self.assertEqual(child_without_parent.returncode, 1)
        self.assertIn("child thread requires parent_session_id", child_without_parent.stderr)

        original = self.register("child", parent_session_id="parent-a")
        self.assertEqual(original["parent_session_id"], "parent-a")
        self.assertEqual(original["kind"], "child")
        self.assertEqual(original["project"], "agtask")
        identical = self.register("child", parent_session_id="parent-a")
        self.assertEqual(identical["parent_session_id"], "parent-a")
        self.assertEqual(identical["updated"], original["updated"])
        self.assertEqual(len(identical["rollouts"]), len(original["rollouts"]))
        changed = self.run_cli(
            "register",
            "--id",
            "child",
            "--session-id",
            "child",
            "--parent-session-id",
            "parent-a",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "changed title",
            "--initial-prompt",
            FORK_PROMPT,
            "--description",
            "Write a compact database proof.",
            "--status",
            "active",
            "--json",
            check=False,
        )
        self.assertEqual(changed.returncode, 1)
        self.assertIn("title conflict", changed.stderr)
        current = self.show("child")
        self.assertEqual(current, {key: value for key, value in identical.items() if key != "hook_prompts"})
        description_conflict = self.run_cli(
            "register",
            "--id",
            "child",
            "--session-id",
            "child",
            "--parent-session-id",
            "parent-a",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "changed title",
            "--initial-prompt",
            "Task:\nChanged description.",
            "--description",
            "Changed description.",
            "--status",
            "active",
            check=False,
        )
        self.assertEqual(description_conflict.returncode, 1)
        self.assertIn("description conflict", description_conflict.stderr)
        self.assertEqual(
            self.show("child")["description"], "Write a compact database proof."
        )
        conflict = self.run_cli(
            "register",
            "--id",
            "child",
            "--session-id",
            "child",
            "--parent-session-id",
            "parent-b",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "child",
            "--description",
            "child",
            "--status",
            "active",
            check=False,
        )
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("parent_session_id conflict", conflict.stderr)
        self.assertEqual(self.show("child")["parent_session_id"], "parent-a")

        project_conflict = self.run_cli(
            "register",
            "--id",
            "child",
            "--session-id",
            "child",
            "--parent-session-id",
            "parent-a",
            "--kind",
            "child",
            "--project",
            "other-project",
            "--title",
            "child",
            "--description",
            "child",
            check=False,
        )
        self.assertEqual(project_conflict.returncode, 1)
        self.assertIn("project conflict", project_conflict.stderr)
        self.assertEqual(self.show("child")["project"], "agtask")

        self_parent = self.run_cli(
            "register",
            "--id",
            "same",
            "--parent-session-id",
            fixture_creation_id("same"),
            "--session-id",
            fixture_creation_id("same"),
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "same",
            "--description",
            "same",
            check=False,
        )
        self.assertNotEqual(self_parent.returncode, 0)
        self.assertIn("cannot name itself", self_parent.stderr)

        empty_parent = self.run_cli(
            "register",
            "--id",
            "empty-parent",
            "--session-id",
            "empty-parent",
            "--parent-session-id",
            "",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "empty parent",
            "--description",
            "empty parent",
            check=False,
        )
        self.assertEqual(empty_parent.returncode, 1)
        self.assertIn("parent_session_id must not be empty", empty_parent.stderr)

    def test_register_requires_canonical_uuidv4_and_human_output_names_identities(
        self,
    ) -> None:
        self.run_cli("init")
        invalid_ids = (
            "readable-but-not-a-uuid",
            "11111111-1111-1111-8111-111111111111",
            "F1CCE008-E001-4DBD-A231-37783065E3FB",
            "f1cce008e0014dbda23137783065e3fb",
        )
        for invalid_id in invalid_ids:
            with self.subTest(invalid_id=invalid_id):
                result = self.run_cli(
                    "register",
                    "--id",
                    invalid_id,
                    "--session-id",
                    f"session-{invalid_id}",
                    "--parent-session-id",
                    "parent-session",
                    "--kind",
                    "child",
                    "--project",
                    "agtask",
                    "--title",
                    "invalid id",
                    "--initial-prompt",
                    FORK_PROMPT,
                    check=False,
                    normalize_fixture_ids=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn("id must be a canonical UUIDv4", result.stderr)

        logical_id = fixture_creation_id("human-output")
        self.register(
            logical_id,
            session_id="human-output-session",
            parent_session_id="human-output-parent",
        )
        shown = self.run_cli("show", "--session-id", "human-output-session")
        self.assertIn(f"Task ID: {logical_id}", shown.stdout)
        self.assertIn("Session ID: human-output-session", shown.stdout)
        self.assertIn("Parent session ID: human-output-parent", shown.stdout)

    def test_add_registers_current_task_and_reconciles_exact_session_retry(
        self,
    ) -> None:
        self.write_config(
            self.home,
            {"hooks": {"OnCreate": {"prompt": "consume current-task setup"}}},
        )
        arguments = (
            "add",
            "agtask",
            "--session-id",
            "current-session",
            "--title",
            "Preserved Codex title",
            "--initial-prompt",
            "Build the add-current-task workflow.\nKeep its description stable.",
            "--json",
        )

        created = json.loads(self.run_cli(*arguments).stdout)
        self.assertEqual(str(uuid.UUID(created["id"])), created["id"])
        self.assertEqual(uuid.UUID(created["id"]).version, 4)
        self.assertEqual(created["session_id"], "current-session")
        self.assertIsNone(created["parent_session_id"])
        self.assertEqual(created["kind"], "main")
        self.assertEqual(created["project"], "agtask")
        self.assertEqual(created["title"], "Preserved Codex title")
        self.assertEqual(
            created["description"], "Build the add-current-task workflow."
        )
        self.assertEqual(created["status"], "active")
        self.assertEqual(
            created["hook_prompts"],
            [
                {
                    "event": "OnCreate",
                    "prompt": "consume current-task setup",
                    "source": str((self.home / ".agtask.json").resolve()),
                }
            ],
        )
        self.assertEqual(
            [
                (row["turn_id"], row["role"], row["message"])
                for row in created["rollouts"]
            ],
            [("thread.created", "meta", "thread.created")],
        )

        retried = json.loads(self.run_cli(*arguments).stdout)
        self.assertEqual(retried["id"], created["id"])
        self.assertEqual(retried["created"], created["created"])
        self.assertEqual(retried["rollouts"], created["rollouts"])
        self.assertEqual(retried["hook_prompts"], [])

        initial_prompt = (
            "Build the add-current-task workflow.\nKeep its description stable."
        )
        for replacement, error in (
            (("agtask-other", "Preserved Codex title", initial_prompt), "project conflict"),
            (("agtask", "Changed title", initial_prompt), "title conflict"),
            (
                ("agtask", "Preserved Codex title", "Different oldest prompt."),
                "description conflict",
            ),
        ):
            project, title, prompt = replacement
            result = self.run_cli(
                "add",
                project,
                "--session-id",
                "current-session",
                "--title",
                title,
                "--initial-prompt",
                prompt,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(error, result.stderr)
        self.assertEqual(
            self.show(created["id"]),
            {k: v for k, v in created.items() if k != "hook_prompts"},
        )

    def test_add_rejects_invalid_identity_metadata_and_existing_child(self) -> None:
        cases = (
            (("", "session", "title"), "project must not be empty"),
            (
                (" padded ", "session", "title"),
                "project must not contain surrounding whitespace",
            ),
            (("project", "", "title"), "session_id must not be empty"),
            (
                ("project", " padded ", "title"),
                "session_id must not contain surrounding whitespace",
            ),
            (("project", "session", ""), "title must not be empty"),
            (
                ("project", "session", " padded "),
                "title must not contain surrounding whitespace",
            ),
            (("project", "session", "two\nlines"), "title must be one line"),
        )
        for (project, session_id, title), error in cases:
            with self.subTest(error=error):
                result = self.run_cli(
                    "add",
                    project,
                    "--session-id",
                    session_id,
                    "--title",
                    title,
                    "--initial-prompt",
                    "Track this task.",
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(error, result.stderr)

        child = self.register(
            "existing-child",
            session_id="existing-child-session",
            parent_session_id="parent-session",
        )
        result = self.run_cli(
            "add",
            "agtask",
            "--session-id",
            child["session_id"],
            "--title",
            child["title"],
            "--initial-prompt",
            FORK_PROMPT,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot add existing child thread", result.stderr)
        self.assertEqual(
            self.show(child["id"]),
            {k: v for k, v in child.items() if k != "hook_prompts"},
        )

    def test_full_hook_lifecycle_json_search_and_context(self) -> None:
        self.run_cli("init")
        initial = self.register(status="todo")
        self.assertEqual(initial["id"], fixture_creation_id("thread-1"))
        self.assertEqual(initial["session_id"], "thread-1")
        self.assertEqual(initial["parent_session_id"], "parent-thread")
        self.assertEqual(initial["kind"], "child")
        self.assertEqual(initial["project"], "agtask")
        self.assertEqual(initial["title"], "agtask/thread-1")
        self.assertEqual(initial["description"], "Write a compact database proof.")
        self.assertEqual(initial["status"], "todo")
        self.assertEqual(
            set(initial),
            {
                "id",
                "session_id",
                "parent_session_id",
                "kind",
                "project",
                "title",
                "description",
                "created",
                "updated",
                "closed",
                "status",
                "rollouts",
                "files",
                "hook_prompts",
            },
        )
        self.assertEqual(
            [(row["turn_id"], row["role"], row["message"]) for row in initial["rollouts"]],
            [("thread.created", "meta", "thread.created")],
        )

        bootstrap = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "thread-1",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(bootstrap["status"], "active")
        self.assertEqual(bootstrap["description"], "Write a compact database proof.")
        self.assertEqual(
            [row["turn_id"] for row in bootstrap["rollouts"] if row["role"] == "user"],
            ["bootstrap"],
        )
        prompt_result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-1",
                "turn_id": "turn-user-1",
                "prompt": FORK_PROMPT,
            }
        )
        self.assertIn("Tracked agtask thread", prompt_result.stdout)
        self.assertIn("user: Write a compact database proof.", prompt_result.stdout)
        self.assertIn("Outcome contract:", prompt_result.stdout)
        self.assertNotIn("turn-user-1", prompt_result.stdout)

        blocked = {
            "hook_event_name": "Stop",
            "session_id": "thread-1",
            "turn_id": "turn-assistant-1",
            "last_assistant_message": "Blocked: waiting for a required value.",
        }
        self.hook(blocked)
        self.hook(blocked)
        state = self.show()
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["description"], "Write a compact database proof.")
        self.assertEqual(
            len(
                [
                    entry
                    for entry in state["rollouts"]
                    if entry["role"] == "assistant"
                    and entry["turn_id"] == "turn-assistant-1"
                ]
            ),
            1,
        )

        delegated_result = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-1",
                "turn_id": "turn-user-2",
                "prompt": DELEGATED_FORK_PROMPT,
            }
        )
        self.assertIn("Status: active", delegated_result.stdout)
        state = self.show()
        self.assertEqual(state["description"], "Write a compact database proof.")
        self.assertNotIn("codex_delegation", state["description"])

        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "thread-1",
                "turn_id": "turn-assistant-2",
                "last_assistant_message": "Yes. Completed the compact database proof.",
            }
        )
        self.assertEqual(
            self.show()["description"], "Write a compact database proof."
        )
        compact = {
            "hook_event_name": "PostCompact",
            "session_id": "thread-1",
            "turn_id": "turn-compact-1",
            "trigger": "auto",
        }
        self.hook(compact)
        self.hook(compact)
        context = self.hook(
            {
                "hook_event_name": "SessionStart",
                "session_id": "thread-1",
                "source": "compact",
            }
        ).stdout
        self.assertIn("meta: compaction:auto", context)
        self.assertNotIn("compact:turn-compact-1:auto", context)

        search = json.loads(self.run_cli("search", "database", "--json").stdout)
        self.assertEqual(
            [row["id"] for row in search], [fixture_creation_id("thread-1")]
        )
        listed = json.loads(self.run_cli("list", "--status", "active", "--json").stdout)
        self.assertEqual(
            [row["id"] for row in listed], [fixture_creation_id("thread-1")]
        )

        state = self.show()
        compact_rows = [
            row
            for row in state["rollouts"]
            if row["turn_id"] == "compact:turn-compact-1:auto"
        ]
        self.assertEqual(len(compact_rows), 1)
        self.assertEqual(compact_rows[0]["message"], "compaction:auto")
        for rollout in state["rollouts"]:
            self.assertEqual(
                set(rollout),
                {"id", "created", "thread_id", "turn_id", "role", "message"},
            )
            self.assertEqual(rollout["thread_id"], fixture_creation_id("thread-1"))
        self.assertNotIn("activities", state)

    def test_rename_plans_read_only_then_applies_atomically(self) -> None:
        self.run_cli("init")
        initial = self.register(title="agtask/old-title")

        plan = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/new-title",
                "--json",
            ).stdout
        )
        self.assertEqual(plan["phase"], "app_action_required")
        self.assertEqual(plan["plan_version"], 2)
        self.assertFalse(plan["applied"])
        self.assertEqual(plan["id"], fixture_creation_id("thread-1"))
        self.assertEqual(plan["session_id"], "thread-1")
        self.assertEqual(plan["current_title"], "agtask/old-title")
        self.assertEqual(plan["requested_title"], "agtask/new-title")
        self.assertEqual(plan["updated"], initial["updated"])
        self.assertRegex(plan["plan_token"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            plan["app_action"],
            {
                "tool": "codex_app__set_thread_title",
                "arguments": {
                    "threadId": "thread-1",
                    "title": "agtask/new-title",
                },
            },
        )
        self.assertEqual(
            self.show(),
            {key: value for key, value in initial.items() if key != "hook_prompts"},
        )

        activity = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                fixture_creation_id("thread-1"),
                "--role",
                "assistant",
                "--turn-id",
                "unrelated-turn",
                "--content",
                "Unrelated task activity.",
                "--json",
            ).stdout
        )
        self.assertGreater(activity["updated"], plan["updated"])

        renamed_result = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/new-title",
                "--apply",
                plan["plan_token"],
                "--json",
            ).stdout
        )
        self.assertEqual(renamed_result["phase"], "complete")
        self.assertEqual(renamed_result["plan_version"], 2)
        self.assertTrue(renamed_result["applied"])
        self.assertTrue(renamed_result["changed"])
        renamed = renamed_result["thread"]
        self.assertEqual(renamed["title"], "agtask/new-title")
        self.assertGreater(renamed["updated"], initial["updated"])
        rename_events = [
            row
            for row in renamed["rollouts"]
            if row["role"] == "meta" and row["message"] == "title:renamed"
        ]
        self.assertEqual(len(rename_events), 1)
        self.assertEqual(rename_events[0]["created"], renamed["updated"])
        self.assertEqual(
            json.loads(self.run_cli("search", "new-title", "--json").stdout)[0][
                "id"
            ],
            fixture_creation_id("thread-1"),
        )
        self.assertEqual(
            json.loads(self.run_cli("search", "old-title", "--json").stdout), []
        )

        repeated = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/new-title",
                "--json",
            ).stdout
        )
        self.assertEqual(repeated["phase"], "app_action_required")
        self.assertEqual(
            repeated["app_action"]["arguments"]["title"], "agtask/new-title"
        )
        self.assertEqual(self.show(), renamed)
        repeated_apply = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/new-title",
                "--apply",
                repeated["plan_token"],
                "--json",
            ).stdout
        )
        self.assertTrue(repeated_apply["applied"])
        self.assertFalse(repeated_apply["changed"])
        self.assertEqual(repeated_apply["thread"]["updated"], renamed["updated"])
        self.assertEqual(repeated_apply["thread"]["rollouts"], renamed["rollouts"])

    def test_rename_rejects_stale_plans_or_invalid_titles_without_writing(self) -> None:
        self.run_cli("init")
        self.register(title="agtask/original")

        stale_plan = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/stale",
                "--json",
            ).stdout
        )
        concurrent_plan = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/concurrent",
                "--json",
            ).stdout
        )
        wrong_title = self.run_cli(
            "rename",
            "--session-id",
            "thread-1",
            "--title",
            "agtask/different-request",
            "--apply",
            stale_plan["plan_token"],
            "--json",
            check=False,
        )
        self.assertEqual(wrong_title.returncode, 1)
        self.assertIn("stale rename plan", wrong_title.stderr)
        self.assertEqual(self.show()["title"], "agtask/original")
        concurrent = json.loads(
            self.run_cli(
                "rename",
                "--session-id",
                "thread-1",
                "--title",
                "agtask/concurrent",
                "--apply",
                concurrent_plan["plan_token"],
                "--json",
            ).stdout
        )["thread"]
        stale = self.run_cli(
            "rename",
            "--session-id",
            "thread-1",
            "--title",
            "agtask/stale",
            "--apply",
            stale_plan["plan_token"],
            "--json",
            check=False,
        )
        self.assertEqual(stale.returncode, 1)
        self.assertIn("stale rename plan", stale.stderr)
        self.assertEqual(self.show(), concurrent)

        for title, message in (
            ("", "title must not be empty"),
            (" padded ", "title must not contain surrounding whitespace"),
            ("two\nlines", "title must be one line"),
            ("two\rlines", "title must be one line"),
        ):
            with self.subTest(title=title):
                invalid = self.run_cli(
                    "rename",
                    "--session-id",
                    "thread-1",
                    "--title",
                    title,
                    check=False,
                )
                self.assertEqual(invalid.returncode, 1)
                self.assertIn(message, invalid.stderr)
                self.assertEqual(self.show(), concurrent)

        logical_selector = self.run_cli(
            "rename",
            "--id",
            "thread-1",
            "--title",
            "agtask/not-allowed",
            check=False,
        )
        self.assertEqual(logical_selector.returncode, 2)
        self.assertIn("required: --session-id", logical_selector.stderr)
        self.assertNotIn("[--id", logical_selector.stderr)
        self.assertEqual(self.show(), concurrent)

    def test_initial_prompt_description_is_immutable_for_one_shot_and_stop_races(
        self,
    ) -> None:
        self.run_cli("init")
        missing_prompt = self.run_cli(
            "register",
            "--id",
            "missing-prompt",
            "--session-id",
            "missing-prompt",
            "--parent-session-id",
            "parent-thread",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "missing prompt",
            "--description",
            "Write a compact database proof.",
            check=False,
        )
        self.assertEqual(missing_prompt.returncode, 1)
        self.assertIn("--initial-prompt is required", missing_prompt.stderr)

        incompatible = self.run_cli(
            "register",
            "--id",
            "incompatible",
            "--session-id",
            "incompatible",
            "--parent-session-id",
            "parent-thread",
            "--kind",
            "child",
            "--project",
            "agtask",
            "--title",
            "incompatible prompt",
            "--initial-prompt",
            FORK_PROMPT,
            "--description",
            "A different description.",
            check=False,
        )
        self.assertEqual(incompatible.returncode, 1)
        self.assertIn(
            "conflicts with the normalized --initial-prompt", incompatible.stderr
        )

        self.register("one-shot-yes", status="active")
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "one-shot-yes",
                "turn_id": "assistant-first",
                "last_assistant_message": "Yes. The requested work is complete.",
            }
        )
        one_shot = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "one-shot-yes",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(one_shot["description"], "Write a compact database proof.")
        self.assertEqual(one_shot["status"], "active")
        self.assertEqual(
            [(row["role"], row["message"]) for row in reversed(one_shot["rollouts"])],
            [
                ("meta", "thread.created"),
                ("assistant", "Yes."),
                ("user", "Write a compact database proof."),
            ],
        )

        self.register("stop-before-bootstrap", status="todo")
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "stop-before-bootstrap",
                "turn_id": "assistant-first",
                "last_assistant_message": "Blocked: waiting for required input.",
            }
        )
        stop_race = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "stop-before-bootstrap",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(stop_race["status"], "blocked")
        self.assertEqual(
            stop_race["description"], "Write a compact database proof."
        )

        self.register("stop-before-real-user", status="todo")
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "stop-before-real-user",
                "turn_id": "assistant-first",
                "last_assistant_message": "Blocked: waiting for required input.",
            }
        )
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "stop-before-real-user",
                "turn_id": "real-user",
                "prompt": FORK_PROMPT,
            }
        )
        real_user_race = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "stop-before-real-user",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(real_user_race["status"], "blocked")
        self.assertEqual(
            real_user_race["description"], "Write a compact database proof."
        )
        self.assertEqual(
            [
                row["turn_id"]
                for row in real_user_race["rollouts"]
                if row["role"] == "user"
            ],
            ["real-user"],
        )

        bad_bootstrap = self.run_cli(
            "record-turn",
            "--id",
            "stop-before-bootstrap",
            "--role",
            "user",
            "--turn-id",
            "bootstrap",
            "--content",
            "Task:\nA different creation prompt.",
            check=False,
        )
        self.assertEqual(bad_bootstrap.returncode, 1)
        self.assertIn("initial prompt description conflict", bad_bootstrap.stderr)

        self.register(
            "main-follow-up", parent_session_id=None, kind="main", status="active"
        )
        main_follow_up = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "main-follow-up",
                "turn_id": "later-main-turn",
                "prompt": "A later main-task instruction.",
            }
        )
        self.assertIn(
            "Task description: Write a compact database proof.",
            main_follow_up.stdout,
        )
        main_state = self.show("main-follow-up")
        self.assertEqual(main_state["description"], "Write a compact database proof.")
        self.assertIn(
            "A later main-task instruction.",
            [row["message"] for row in main_state["rollouts"]],
        )

        self.register("preexisting-row")
        with self.connect() as connection:
            connection.execute(
                "UPDATE thread SET description=? WHERE id=?",
                ("Legacy stored description.", fixture_creation_id("preexisting-row")),
            )
        self.run_cli("init")
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "preexisting-row",
                "turn_id": "post-upgrade-assistant",
                "last_assistant_message": "Yes. Keep the legacy data intact.",
            }
        )
        legacy_state = self.show("preexisting-row")
        self.assertEqual(legacy_state["description"], "Legacy stored description.")
        self.assertIn(
            "Yes.",
            [row["message"] for row in legacy_state["rollouts"]],
        )

    def test_bootstrap_reconciliation_is_symmetric_and_preserves_mismatches(self) -> None:
        self.run_cli("init")
        for role in ("user", "assistant"):
            with self.subTest(role=role, order="bootstrap-first"):
                thread_id = f"{role}-bootstrap-first"
                message = f"Matching {role} summary."
                if role == "user":
                    self.register(
                        thread_id, initial_prompt=message, description=message
                    )
                else:
                    self.register(thread_id)
                self.run_cli(
                    "record-turn",
                    "--id",
                    thread_id,
                    "--role",
                    role,
                    "--turn-id",
                    "bootstrap",
                    "--content",
                    message,
                )
                self.run_cli(
                    "record-turn",
                    "--id",
                    thread_id,
                    "--role",
                    role,
                    "--turn-id",
                    "real-turn",
                    "--content",
                    message,
                )
                rows = [row for row in self.show(thread_id)["rollouts"] if row["role"] == role]
                self.assertEqual([(row["turn_id"], row["message"]) for row in rows], [("real-turn", message)])

            with self.subTest(role=role, order="real-first"):
                thread_id = f"{role}-real-first"
                message = f"Matching real-first {role} summary."
                if role == "user":
                    self.register(
                        thread_id, initial_prompt=message, description=message
                    )
                else:
                    self.register(thread_id)
                for turn_id in ("real-turn", "bootstrap", "bootstrap"):
                    self.run_cli(
                        "record-turn",
                        "--id",
                        thread_id,
                        "--role",
                        role,
                        "--turn-id",
                        turn_id,
                        "--content",
                        message,
                    )
                rows = [row for row in self.show(thread_id)["rollouts"] if row["role"] == role]
                self.assertEqual([(row["turn_id"], row["message"]) for row in rows], [("real-turn", message)])

            with self.subTest(role=role, mismatch=True):
                thread_id = f"{role}-mismatch"
                if role == "user":
                    self.register(
                        thread_id,
                        initial_prompt="Bootstrap summary.",
                        description="Bootstrap summary.",
                    )
                else:
                    self.register(thread_id)
                self.run_cli(
                    "record-turn",
                    "--id",
                    thread_id,
                    "--role",
                    role,
                    "--turn-id",
                    "bootstrap",
                    "--content",
                    "Bootstrap summary.",
                )
                self.run_cli(
                    "record-turn",
                    "--id",
                    thread_id,
                    "--role",
                    role,
                    "--turn-id",
                    "real-turn",
                    "--content",
                    "Different real summary.",
                )
                rows = [row for row in self.show(thread_id)["rollouts"] if row["role"] == role]
                self.assertEqual({row["turn_id"] for row in rows}, {"bootstrap", "real-turn"})

        self.register(
            "user-after-assistant",
            initial_prompt="Initial user summary.",
            description="Initial user summary.",
        )
        self.run_cli(
            "record-turn",
            "--id",
            "user-after-assistant",
            "--role",
            "user",
            "--turn-id",
            "bootstrap",
            "--content",
            "Initial user summary.",
        )
        self.run_cli(
            "record-turn",
            "--id",
            "user-after-assistant",
            "--role",
            "assistant",
            "--turn-id",
            "assistant-turn",
            "--content",
            "Assistant already followed.",
        )
        self.run_cli(
            "record-turn",
            "--id",
            "user-after-assistant",
            "--role",
            "user",
            "--turn-id",
            "real-user",
            "--content",
            "Initial user summary.",
        )
        user_rows = [
            row
            for row in self.show("user-after-assistant")["rollouts"]
            if row["role"] == "user"
        ]
        self.assertEqual({row["turn_id"] for row in user_rows}, {"bootstrap", "real-user"})

        self.register("assistant-before-bootstrap")
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "assistant-before-bootstrap",
                "turn_id": "real-user",
                "prompt": FORK_PROMPT,
            }
        )
        assistant_message = "Blocked: completed before parent bootstrap verification."
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "assistant-before-bootstrap",
                "turn_id": "real-assistant",
                "last_assistant_message": assistant_message,
            }
        )
        bootstrap_result = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "assistant-before-bootstrap",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(bootstrap_result["status"], "blocked")
        self.assertEqual(
            bootstrap_result["description"], "Write a compact database proof."
        )
        self.assertEqual(
            [
                row["turn_id"]
                for row in bootstrap_result["rollouts"]
                if row["role"] == "user"
            ],
            ["real-user"],
        )

        self.register("normalized-assistant-status")
        self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "normalized-assistant-status",
                "turn_id": "real-user",
                "prompt": FORK_PROMPT,
            }
        )
        self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "normalized-assistant-status",
                "turn_id": "real-assistant",
                "last_assistant_message": "# Blocked: waiting for input.",
            }
        )
        normalized_result = json.loads(
            self.run_cli(
                "record-turn",
                "--id",
                "normalized-assistant-status",
                "--role",
                "user",
                "--turn-id",
                "bootstrap",
                "--content",
                FORK_PROMPT,
                "--json",
            ).stdout
        )
        self.assertEqual(
            normalized_result["description"], "Write a compact database proof."
        )
        self.assertEqual(normalized_result["status"], "active")
        self.assertEqual(
            len([row for row in normalized_result["rollouts"] if row["role"] == "user"]),
            1,
        )

    def test_event_conflicts_concurrent_retries_and_cli_vocabulary(self) -> None:
        self.run_cli("init")
        self.register(
            initial_prompt="Concurrent retry summary.",
            description="Concurrent retry summary.",
        )
        append_args = (
            "append-rollout",
            "--id",
            "thread-1",
            "--turn-id",
            "manual-event",
            "--role",
            "meta",
            "--message",
            "manual checkpoint",
        )
        self.run_cli(*append_args)
        self.run_cli(*append_args)
        conflict = self.run_cli(
            *append_args[:-1], "different checkpoint", check=False
        )
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("rollout event conflict", conflict.stderr)

        user_args = (
            "record-turn",
            "--id",
            "thread-1",
            "--role",
            "user",
            "--turn-id",
            "concurrent-turn",
            "--content",
            "Concurrent retry summary.",
        )
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(lambda _unused: self.run_cli(*user_args), range(6)))
        self.assertTrue(all(result.returncode == 0 for result in results))
        rows = [
            row
            for row in self.show()["rollouts"]
            if row["role"] == "user" and row["turn_id"] == "concurrent-turn"
        ]
        self.assertEqual(len(rows), 1)

        direct_conflict = self.run_cli(
            "record-turn",
            "--id",
            "thread-1",
            "--role",
            "user",
            "--turn-id",
            "concurrent-turn",
            "--content",
            "Conflicting retry summary.",
            check=False,
        )
        self.assertNotEqual(direct_conflict.returncode, 0)
        hook_conflict = self.hook(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-1",
                "turn_id": "concurrent-turn",
                "prompt": "Hook conflict summary.",
            }
        )
        self.assertEqual(hook_conflict.returncode, 0)
        self.assertEqual(hook_conflict.stdout, "")
        self.assertEqual(hook_conflict.stderr, "")
        rows = [
            row
            for row in self.show()["rollouts"]
            if row["role"] == "user" and row["turn_id"] == "concurrent-turn"
        ]
        self.assertEqual([row["message"] for row in rows], ["Concurrent retry summary."])

        long_markdown = "# Heading\n" + "🙂" * 300
        self.run_cli(
            "append-rollout",
            "--id",
            "thread-1",
            "--turn-id",
            "normalized-meta",
            "--role",
            "meta",
            "--message",
            long_markdown,
        )
        normalized = next(
            row["message"]
            for row in self.show()["rollouts"]
            if row["turn_id"] == "normalized-meta"
        )
        self.assertNotIn("\n", normalized)
        self.assertFalse(normalized.startswith("#"))
        self.assertEqual(len(normalized), 240)
        self.assertTrue(normalized.endswith("…"))

        help_text = self.run_cli("--help").stdout
        self.assertIn("append-rollout", help_text)
        self.assertIn("audit", help_text)
        self.assertIn("dashboard", help_text)
        self.assertIn("rename", help_text)
        self.assertNotIn("activity", help_text)
        register_help = self.run_cli("register", "--help").stdout
        self.assertIn("--parent-session-id", register_help)
        self.assertIn("--kind", register_help)
        self.assertIn("--project", register_help)
        self.assertIn("--initial-prompt", register_help)
        rename_help = self.run_cli("rename", "--help").stdout
        self.assertIn("--session-id", rename_help)
        self.assertIn("--title", rename_help)
        self.assertIn("--apply", rename_help)
        self.assertNotIn("--id", rename_help)
        self.assertNotIn("--expected-title", rename_help)

    def test_state_transitions_and_finalization_are_state_aware(self) -> None:
        self.run_cli("init")
        self.register()
        self.run_cli("status", "--id", "thread-1", "--status", "blocked")
        first = self.show()
        first_updated = first["updated"]
        self.run_cli("status", "--id", "thread-1", "--status", "blocked")
        repeated = self.show()
        self.assertEqual(repeated["updated"], first_updated)
        self.run_cli("status", "--id", "thread-1", "--status", "active")
        self.run_cli("status", "--id", "thread-1", "--status", "blocked")
        blocked_events = [
            row
            for row in self.show()["rollouts"]
            if row["message"] == "status:active->blocked"
        ]
        self.assertEqual(len(blocked_events), 2)
        self.assertEqual(len({row["turn_id"] for row in blocked_events}), 2)

        self.run_cli("status", "--id", "thread-1", "--status", "drop")
        dropped = self.show()
        self.assertEqual(dropped["status"], "drop")
        self.assertEqual(dropped["updated"], dropped["closed"])
        dropped_at = dropped["closed"]
        self.run_cli(
            "record-turn",
            "--id",
            "thread-1",
            "--role",
            "assistant",
            "--turn-id",
            "after-drop",
            "--content",
            "This ordinary turn must not resume abandoned work.",
        )
        after_drop_turn = self.show()
        self.assertEqual(after_drop_turn["status"], "drop")
        self.assertEqual(after_drop_turn["closed"], dropped_at)
        prepared = json.loads(
            self.run_cli(
                "close", "--id", "thread-1", "--prepare", "--json"
            ).stdout
        )
        self.assertEqual(prepared["merge_claim"]["state"], "not_applicable")
        rejected = self.run_cli(
            "status",
            "--id",
            "thread-1",
            "--status",
            "active",
            check=False,
        )
        self.assertIn("dropped threads must be reopened explicitly", rejected.stderr)
        self.run_cli("reopen", "--id", "thread-1")
        self.assertEqual(self.show()["rollouts"][0]["message"], "status:drop->active")

        first_close = self.close_thread()
        self.assertEqual(first_close["status"], "done")
        self.assertIsNotNone(first_close["closed"])
        self.run_cli("close", "--id", "thread-1")
        after_retry = self.show()
        self.assertEqual(after_retry["closed"], first_close["closed"])
        finalizations = [
            row
            for row in after_retry["rollouts"]
            if row["message"] == "finalization:completed"
        ]
        self.assertEqual(len(finalizations), 1)

        self.run_cli("reopen", "--id", "thread-1")
        reopened = self.show()
        self.assertEqual(reopened["status"], "active")
        self.assertIsNone(reopened["closed"])
        self.close_thread()
        finalizations = [
            row
            for row in self.show()["rollouts"]
            if row["message"] == "finalization:completed"
        ]
        self.assertEqual(len(finalizations), 2)
        self.assertEqual(len({row["turn_id"] for row in finalizations}), 2)

    def test_audit_requires_observations_and_exact_confirmation_before_archiving(
        self,
    ) -> None:
        self.run_cli("init")
        self.register(
            "audit-archived",
            session_id="session-archived",
            title="archived candidate",
        )
        self.register(
            "audit-current",
            session_id="session-current",
            title="current task",
        )
        self.register(
            "audit-missing",
            session_id="session-missing",
            title="missing task",
        )
        self.register(
            "audit-failed",
            session_id="session-failed",
            title="failed lookup",
        )
        blocked = self.register(
            "audit-blocked",
            session_id="session-blocked",
            title="blocked task",
        )
        self.run_cli(
            "status",
            "--id",
            str(blocked["id"]),
            "--status",
            "blocked",
        )

        discovery = json.loads(self.run_cli("audit", "--json").stdout)
        self.assertEqual(discovery["phase"], "lookup_required")
        self.assertFalse(discovery["applied"])
        self.assertIsNone(discovery["plan_token"])
        self.assertEqual(
            {task["session_id"] for task in discovery["active_tasks"]},
            {
                "session-archived",
                "session-blocked",
                "session-current",
                "session-missing",
                "session-failed",
            },
        )
        self.assertEqual(
            discovery["lookup_requests"],
            [
                {"session_id": task["session_id"]}
                for task in discovery["active_tasks"]
            ],
        )

        observations = json.dumps(
            {
                "schema_version": 1,
                "sessions": [
                    {"session_id": "session-archived", "state": "archived"},
                    {"session_id": "session-current", "state": "not_archived"},
                    {"session_id": "session-missing", "state": "missing"},
                    {
                        "session_id": "session-failed",
                        "state": "error",
                        "detail": "remote host unavailable",
                    },
                    {"session_id": "session-blocked", "state": "archived"},
                    {"session_id": "already-closed", "state": "archived"},
                ],
            },
            separators=(",", ":"),
        )
        plan = json.loads(
            self.run_cli(
                "audit", "--observations-json", observations, "--json"
            ).stdout
        )
        self.assertEqual(plan["phase"], "confirmation_required")
        self.assertFalse(plan["applied"])
        self.assertRegex(plan["plan_token"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [task["session_id"] for task in plan["affected_tasks"]],
            ["session-archived", "session-blocked"],
        )
        self.assertEqual(
            [(item["session_id"], item["lookup_state"]) for item in plan["unresolved"]],
            [
                ("session-failed", "error"),
                ("session-missing", "missing"),
            ],
        )
        self.assertEqual(plan["unresolved"][0]["detail"], "remote host unavailable")
        self.assertEqual(plan["ignored_observations"], ["already-closed"])
        self.assertEqual(self.show("audit-archived")["status"], "active")

        rejected = self.run_cli(
            "audit",
            "--observations-json",
            observations,
            "--apply",
            "0" * 64,
            "--json",
            check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("audit plan changed", rejected.stderr)
        self.assertEqual(self.show("audit-archived")["status"], "active")

        self.run_cli(
            "status",
            "--id",
            fixture_creation_id("audit-current"),
            "--status",
            "blocked",
        )
        stale = self.run_cli(
            "audit",
            "--observations-json",
            observations,
            "--apply",
            plan["plan_token"],
            "--json",
            check=False,
        )
        self.assertEqual(stale.returncode, 1)
        self.assertIn("audit plan changed", stale.stderr)
        self.assertEqual(self.show("audit-archived")["status"], "active")
        self.run_cli(
            "status",
            "--id",
            fixture_creation_id("audit-current"),
            "--status",
            "active",
        )
        refreshed_plan = json.loads(
            self.run_cli(
                "audit", "--observations-json", observations, "--json"
            ).stdout
        )
        self.assertNotEqual(refreshed_plan["plan_token"], plan["plan_token"])

        applied = json.loads(
            self.run_cli(
                "audit",
                "--observations-json",
                observations,
                "--apply",
                refreshed_plan["plan_token"],
                "--json",
            ).stdout
        )
        self.assertEqual(applied["phase"], "complete")
        self.assertTrue(applied["applied"])
        self.assertEqual(
            [task["session_id"] for task in applied["affected_tasks"]],
            ["session-archived", "session-blocked"],
        )
        archived_state = self.show("audit-archived")
        self.assertEqual(archived_state["status"], "done")
        self.assertIsNotNone(archived_state["closed"])
        self.assertEqual(
            [row["message"] for row in reversed(archived_state["rollouts"])],
            [
                "thread.created",
                "status:active->done",
                "archival:codex-thread-archived",
            ],
        )
        self.assertEqual(self.show("audit-current")["status"], "active")
        self.assertEqual(self.show("audit-missing")["status"], "active")
        self.assertEqual(self.show("audit-failed")["status"], "active")
        blocked_archived_state = self.show("audit-blocked")
        self.assertEqual(blocked_archived_state["status"], "done")
        self.assertIsNotNone(blocked_archived_state["closed"])
        self.assertEqual(
            [row["message"] for row in reversed(blocked_archived_state["rollouts"])],
            [
                "thread.created",
                "status:active->blocked",
                "status:blocked->done",
                "archival:codex-thread-archived",
            ],
        )

        rerun = json.loads(
            self.run_cli(
                "audit", "--observations-json", observations, "--json"
            ).stdout
        )
        self.assertEqual(rerun["phase"], "complete")
        self.assertFalse(rerun["applied"])
        self.assertEqual(rerun["affected_tasks"], [])
        self.assertIsNone(rerun["plan_token"])
        self.assertIn("session-archived", rerun["ignored_observations"])
        self.assertEqual(
            len(
                [
                    row
                    for row in self.show("audit-archived")["rollouts"]
                    if row["message"] == "archival:codex-thread-archived"
                ]
            ),
            1,
        )

    def test_audit_rejects_malformed_or_ambiguous_observations(self) -> None:
        self.run_cli("init")
        self.register("audit-invalid", session_id="session-invalid")
        cases = (
            (
                {"schema_version": 2, "sessions": []},
                "unsupported audit observations schema_version",
            ),
            (
                {"schema_version": True, "sessions": []},
                "unsupported audit observations schema_version",
            ),
            (
                '{"schema_version":1,"schema_version":1,"sessions":[]}',
                "duplicate audit JSON key",
            ),
            (
                {
                    "schema_version": 1,
                    "sessions": [
                        {"session_id": "session-invalid", "state": "unknown"}
                    ],
                },
                "unsupported archive lookup state",
            ),
            (
                {
                    "schema_version": 1,
                    "sessions": [
                        {"session_id": "session-invalid", "state": "archived"},
                        {"session_id": "session-invalid", "state": "not_archived"},
                    ],
                },
                "duplicate archive observation",
            ),
            (
                {
                    "schema_version": 1,
                    "sessions": [
                        {"session_id": "session-invalid", "state": "error"}
                    ],
                },
                "error archive observation requires detail",
            ),
        )
        for document, message in cases:
            with self.subTest(message=message):
                encoded = (
                    document
                    if isinstance(document, str)
                    else json.dumps(document, separators=(",", ":"))
                )
                result = self.run_cli(
                    "audit",
                    "--observations-json",
                    encoded,
                    "--json",
                    check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
                self.assertEqual(self.show("audit-invalid")["status"], "active")

    def test_untracked_unsafe_and_locked_hooks_fail_open(self) -> None:
        absent = self.root / "absent" / "ledger.db"
        missing_env = self.env | {"AGTASK_DB": str(absent)}
        result = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": "missing",
                    "turn_id": "turn",
                    "prompt": "Do nothing.",
                }
            ),
            env=missing_env,
        )
        self.assertEqual((result.stdout, result.stderr), ("", ""))
        self.assertFalse(absent.exists())
        close = self.run_cli(
            "close", "--id", "missing", "--if-tracked", "--json", env=missing_env
        )
        self.assertEqual(json.loads(close.stdout)["status"], "untracked")

        incompatible_dir = self.root / "incompatible"
        incompatible_dir.mkdir(mode=0o700)
        incompatible = incompatible_dir / "ledger.db"
        incompatible.write_bytes(b"not sqlite")
        incompatible.chmod(0o600)
        incompatible_env = self.env | {"AGTASK_DB": str(incompatible)}
        before = incompatible.read_bytes()
        result = self.run_cli(
            "hook",
            input_text=json.dumps(
                {
                    "hook_event_name": "Stop",
                    "session_id": "thread-1",
                    "turn_id": "incompatible-turn",
                    "last_assistant_message": "Fail open.",
                }
            ),
            env=incompatible_env,
        )
        self.assertEqual((result.stdout, result.stderr), ("", ""))
        self.assertEqual(incompatible.read_bytes(), before)
        self.assertEqual([item.name for item in incompatible_dir.iterdir()], ["ledger.db"])

        self.run_cli("init")
        self.register()
        result = self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "untracked",
                "turn_id": "turn",
                "last_assistant_message": "Ignore me.",
            }
        )
        self.assertEqual((result.stdout, result.stderr), ("", ""))

        self.db_path.chmod(0o640)
        result = self.hook(
            {
                "hook_event_name": "Stop",
                "session_id": "thread-1",
                "turn_id": "unsafe-turn",
                "last_assistant_message": "Cannot write with unsafe mode.",
            }
        )
        self.assertEqual((result.stdout, result.stderr), ("", ""))
        self.assertEqual(stat.S_IMODE(self.db_path.stat().st_mode), 0o640)
        self.run_cli("show", "--id", "thread-1")
        self.assertEqual(stat.S_IMODE(self.db_path.stat().st_mode), 0o600)

        connection = self.connect()
        connection.execute("BEGIN EXCLUSIVE")
        try:
            result = self.hook(
                {
                    "hook_event_name": "Stop",
                    "session_id": "thread-1",
                    "turn_id": "locked-turn",
                    "last_assistant_message": "This cannot be persisted while locked.",
                }
            )
        finally:
            connection.rollback()
            connection.close()
        self.assertEqual((result.stdout, result.stderr), ("", ""))
        self.assertFalse(
            any(row["turn_id"] == "locked-turn" for row in self.show()["rollouts"])
        )

        malformed = self.run_cli("hook", input_text="not-json", check=False)
        self.assertEqual(malformed.returncode, 0)
        self.assertEqual((malformed.stdout, malformed.stderr), ("", ""))

    def test_hook_installer_preserves_unrelated_handlers_and_mode(self) -> None:
        hooks_path = self.root / "hooks.json"
        hooks_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 existing.py",
                                        "timeout": 10,
                                    }
                                ]
                            },
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 /old/source/agtask/scripts/agtask hook",
                                        "timeout": 5,
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
            + "\n"
        )
        hooks_path.chmod(0o640)
        env = self.env | {"AGTASK_HOOKS_FILE": str(hooks_path)}

        first_install = subprocess.run(
            ["python3", str(INSTALL_HOOKS), "--json"],
            env=env,
            check=True,
            text=True,
            capture_output=True,
        )
        install_result = json.loads(first_install.stdout)
        self.assertEqual(install_result["trust"], "manual-review-required")
        self.assertIn("/hooks", install_result["trust_action"])
        installed = json.loads(hooks_path.read_text())
        self.assertEqual(stat.S_IMODE(hooks_path.stat().st_mode), 0o640)
        self.assertEqual(
            installed["hooks"]["SessionStart"][0]["hooks"][0]["command"],
            "python3 existing.py",
        )
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "PostCompact"):
            commands = [
                handler["command"]
                for group in installed["hooks"][event]
                for handler in group.get("hooks", [])
                if "command" in handler
            ]
            agtask_commands = [
                command
                for command in commands
                if command.endswith("/agtask/scripts/agtask hook")
            ]
            self.assertEqual(
                agtask_commands,
                [f"python3 {CLI} hook"],
            )
        self.assertIn("UserPromptSubmit", installed["hooks"])
        self.assertEqual(len(list(self.root.glob("hooks.json.agtask.*.bak"))), 1)

        subprocess.run(["python3", str(INSTALL_HOOKS)], env=env, check=True)
        self.assertEqual(len(list(self.root.glob("hooks.json.agtask.*.bak"))), 1)
        subprocess.run(["python3", str(UNINSTALL_HOOKS)], env=env, check=True)
        uninstalled = json.loads(hooks_path.read_text())
        self.assertNotIn("UserPromptSubmit", uninstalled["hooks"])
        self.assertEqual(
            uninstalled["hooks"]["SessionStart"][0]["hooks"][0]["command"],
            "python3 existing.py",
        )

        malformed = self.root / "malformed.json"
        malformed.write_text("{")
        malformed_env = self.env | {"AGTASK_HOOKS_FILE": str(malformed)}
        result = subprocess.run(
            ["python3", str(INSTALL_HOOKS)],
            env=malformed_env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(malformed.read_text(), "{")


if __name__ == "__main__":
    unittest.main()

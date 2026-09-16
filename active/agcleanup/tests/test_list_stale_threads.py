"""Coverage for the stale thread discovery helper."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "list_stale_threads.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "agcleanup_list_stale_threads", SCRIPT_PATH
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
list_stale_threads = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = list_stale_threads
MODULE_SPEC.loader.exec_module(list_stale_threads)


class FakeClient:
    def __init__(self, pages: list[dict[str, object]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, object]] = []

    def thread_list(self, params: dict[str, object]) -> dict[str, object]:
        self.calls.append(params)
        return self.pages.pop(0)


class CollectStaleThreadsTests(unittest.TestCase):
    def test_pages_until_terminal_cursor_and_filters_stale_threads(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [
                        {
                            "id": "older",
                            "updatedAt": 999,
                            "createdAt": 800,
                            "recencyAt": 999,
                            "name": None,
                            "cwd": "/tmp/older",
                            "status": {"type": "notLoaded"},
                            "source": "vscode",
                        },
                        {
                            "id": "old",
                            "updatedAt": 1_000,
                            "createdAt": 900,
                            "recencyAt": 1_000,
                            "name": "old",
                            "cwd": "/tmp/old",
                            "status": {"type": "notLoaded"},
                            "source": "vscode",
                        },
                    ],
                    "nextCursor": "cursor-2",
                },
                {
                    "data": [
                        {
                            "id": "fresh",
                            "updatedAt": 1_700,
                            "createdAt": 1_100,
                            "recencyAt": 1_700,
                            "name": "fresh",
                            "cwd": "/tmp/fresh",
                            "status": {"type": "notLoaded"},
                            "source": "vscode",
                        }
                    ],
                    "nextCursor": None,
                },
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=2_000,
            cutoff_age_seconds=1_000,
            page_size=2,
            max_pages=10,
        )

        self.assertTrue(result.exhaustive)
        self.assertEqual(result.pagesFetched, 2)
        self.assertEqual(result.examinedCount, 3)
        self.assertEqual(
            [thread.threadId for thread in result.staleThreads], ["older", "old"]
        )
        self.assertEqual(result.staleThreads[0].hostId, "local")
        self.assertEqual(result.staleThreads[0].kind, "codex")
        self.assertNotIn("cursor", client.calls[0])
        self.assertEqual(client.calls[0]["sortDirection"], "asc")
        self.assertIn("sourceKinds", client.calls[0])
        self.assertEqual(client.calls[0]["modelProviders"], [])
        self.assertEqual(client.calls[1]["cursor"], "cursor-2")

    def test_remote_host_id_qualifies_results(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [{"id": "remote-old", "updatedAt": 1}],
                    "nextCursor": None,
                }
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            host_id="remote-ssh-discovered:kdevbox-2",
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=10,
        )

        self.assertEqual(result.hostId, "remote-ssh-discovered:kdevbox-2")
        self.assertEqual(
            result.staleThreads[0].hostId, "remote-ssh-discovered:kdevbox-2"
        )

    def test_stops_at_page_cap_and_reports_next_cursor(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [{"id": "old", "updatedAt": 1}],
                    "nextCursor": "still-more",
                }
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=1,
        )

        self.assertFalse(result.exhaustive)
        self.assertEqual(result.incompleteReason, "stopped after 1 pages")
        self.assertEqual(result.nextCursor, "still-more")

    def test_can_continue_from_start_cursor(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [{"id": "old", "updatedAt": 1}],
                    "nextCursor": None,
                }
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=1,
            start_cursor="resume-here",
        )

        self.assertTrue(result.exhaustive)
        self.assertEqual(result.startCursor, "resume-here")
        self.assertEqual(client.calls[0]["cursor"], "resume-here")

    def test_deduplicates_threads_across_pages(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [{"id": "old", "updatedAt": 1}],
                    "nextCursor": "cursor-2",
                },
                {
                    "data": [{"id": "old", "updatedAt": 1}],
                    "nextCursor": None,
                },
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=10,
        )

        self.assertEqual(result.examinedCount, 1)
        self.assertEqual(result.duplicateCount, 1)
        self.assertEqual(result.staleCount, 1)

    def test_missing_next_cursor_is_non_exhaustive(self) -> None:
        client = FakeClient([{"data": [{"id": "old", "updatedAt": 1}]}])

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=10,
        )

        self.assertFalse(result.exhaustive)
        self.assertEqual(result.incompleteReason, "thread/list result omitted nextCursor")

    def test_malformed_entries_are_non_exhaustive(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [{"id": "missing-updated-at"}],
                    "nextCursor": None,
                }
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=50,
            max_pages=10,
        )

        self.assertFalse(result.exhaustive)
        self.assertEqual(
            result.incompleteReason, "thread/list returned malformed thread entries"
        )
        self.assertEqual(result.malformedCount, 1)

    def test_repeated_cursor_is_non_exhaustive(self) -> None:
        client = FakeClient(
            [
                {"data": [{"id": "one", "updatedAt": 3}], "nextCursor": "same"},
                {"data": [{"id": "two", "updatedAt": 2}], "nextCursor": "same"},
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=1,
            page_size=1,
            max_pages=10,
        )

        self.assertFalse(result.exhaustive)
        self.assertEqual(
            result.incompleteReason,
            "thread/list returned a repeated continuation cursor",
        )
        self.assertEqual(result.nextCursor, "same")

    def test_updated_window_stops_after_older_page(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [
                        {"id": "today", "updatedAt": 2_500},
                        {"id": "also-today", "updatedAt": 2_100},
                    ],
                    "nextCursor": "cursor-2",
                },
                {
                    "data": [
                        {"id": "yesterday", "updatedAt": 1_900},
                    ],
                    "nextCursor": "cursor-3",
                },
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=3_000,
            cutoff_age_seconds=1_000,
            page_size=2,
            max_pages=10,
            updated_since=2_000,
            updated_before=2_400,
        )

        self.assertTrue(result.exhaustive)
        self.assertEqual(result.mode, "updated_window")
        self.assertEqual([thread.threadId for thread in result.windowThreads], ["also-today"])
        self.assertEqual(result.windowCount, 1)
        self.assertEqual(result.staleCount, 0)
        self.assertEqual(client.calls[0]["sortDirection"], "desc")

    def test_stale_scan_stops_after_first_fresh_page_in_ascending_order(self) -> None:
        client = FakeClient(
            [
                {
                    "data": [
                        {"id": "old", "updatedAt": 4},
                        {"id": "fresh", "updatedAt": 6},
                    ],
                    "nextCursor": "newer-threads",
                }
            ]
        )

        result = list_stale_threads.collect_stale_threads(
            client,
            now=10,
            cutoff_age_seconds=5,
            page_size=50,
            max_pages=10,
        )

        self.assertTrue(result.exhaustive)
        self.assertIsNone(result.nextCursor)
        self.assertEqual([thread.threadId for thread in result.staleThreads], ["old"])

    def test_ssh_command_uses_existing_socket_guards(self) -> None:
        command = list_stale_threads.ssh_command(
            ssh_host="kdevbox-2",
            ssh_control_path=Path("/tmp/kdevbox.sock"),
            codex_bin="/usr/local/bin/codex",
        )

        self.assertEqual(command[:4], ["ssh", "-T", "-S", "/tmp/kdevbox.sock"])
        self.assertIn("ControlMaster=no", command)
        self.assertIn("ControlPersist=no", command)
        self.assertIn("ProxyCommand=false", command)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("ForwardAgent=no", command)
        self.assertEqual(
            command[-2:],
            [
                "kdevbox-2",
                "exec /usr/local/bin/codex app-server --stdio",
            ],
        )

    def test_ssh_command_rejects_option_like_host(self) -> None:
        with self.assertRaises(ValueError):
            list_stale_threads.ssh_command(
                ssh_host="-oProxyCommand=bad",
                ssh_control_path=Path("/tmp/kdevbox.sock"),
                codex_bin="/usr/local/bin/codex",
            )

    def test_cli_rejects_sweep_above_500_before_starting_client(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = list_stale_threads.main(["--limit", "50", "--max-pages", "11"])

        self.assertEqual(result, 2)
        self.assertIn("500-thread sweep cap", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

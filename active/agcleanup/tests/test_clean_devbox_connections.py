"""Safety coverage for orphaned DevBox websocket proxy/tunnel cleanup."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "clean_devbox_connections.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "agcleanup_clean_devbox_connections", SCRIPT_PATH
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
cleanup = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = cleanup
MODULE_SPEC.loader.exec_module(cleanup)


def process(
    process_id: int,
    parent_id: int,
    executable: str,
    *,
    user_id: int | None = None,
    command: str | None = None,
    started_at: str = "Fri Aug  7 09:01:02 2026",
) -> cleanup.Process:
    if command is None:
        command = (
            f"/usr/local/bin/{executable} _websocket-proxy --host devbox"
            if executable == cleanup.PROXY_EXECUTABLE
            else f"/usr/local/bin/{executable} client ws://devbox"
        )
    return cleanup.Process(
        pid=process_id,
        uid=os.getuid() if user_id is None else user_id,
        parent_pid=parent_id,
        executable=executable,
        command=command,
        started_at=started_at,
    )


class ProcessTable:
    def __init__(self, *entries: cleanup.Process) -> None:
        self.entries = {entry.pid: entry for entry in entries}
        self.signals: list[tuple[int, signal.Signals]] = []
        self.resist_term: set[int] = set()
        self.resist_kill: set[int] = set()
        self.after_signal = None

    def processes(self, process_id: int | None = None) -> dict[int, cleanup.Process]:
        if process_id is None:
            return dict(self.entries)
        entry = self.entries.get(process_id)
        return {} if entry is None else {process_id: entry}

    def kill(self, process_id: int, requested_signal: signal.Signals) -> None:
        self.signals.append((process_id, requested_signal))
        if process_id not in self.entries:
            raise ProcessLookupError(process_id)
        if requested_signal == signal.SIGTERM and process_id in self.resist_term:
            return
        if requested_signal == signal.SIGKILL and process_id in self.resist_kill:
            return
        del self.entries[process_id]
        for child_id, child in list(self.entries.items()):
            if child.parent_pid == process_id:
                self.entries[child_id] = replace(child, parent_pid=1)
        if self.after_signal is not None:
            self.after_signal(process_id, requested_signal)


class ParseProcessesTests(unittest.TestCase):
    def test_joins_independent_executable_and_start_identity_snapshots(self) -> None:
        actual = cleanup.parse_processes(
            "101 501 1 /Applications/My Tools/dbox-proxy _websocket-proxy\n",
            "101 /Applications/My Tools/dbox-proxy\n",
            "101 Fri Aug  7 09:01:02 2026\n",
        )

        self.assertEqual(actual[101].executable, "dbox-proxy")
        self.assertEqual(actual[101].started_at, "Fri Aug  7 09:01:02 2026")

    def test_requires_actual_executable_and_process_start_identity(self) -> None:
        actual = cleanup.parse_processes(
            "\n".join(
                [
                    "101 501 1 /usr/bin/dbox-proxy _websocket-proxy",
                    "102 501 1 /usr/bin/dbox-proxy _websocket-proxy",
                    "103 501 1 /usr/bin/dbox-proxy _websocket-proxy",
                    "bad pid row",
                ]
            ),
            "101 dbox-proxy\n102 dbox-proxy\ninvalid comm\n",
            "101 Fri Aug  7 09:01:02 2026\n103 Fri Aug  7 09:01:02 2026\n",
        )

        self.assertEqual(set(actual), {101})


class GroupMatchingTests(unittest.TestCase):
    def test_matches_only_same_user_orphan_with_direct_same_user_tunnel(self) -> None:
        current_user = os.getuid()
        snapshot = {
            entry.pid: entry
            for entry in [
                process(101, 1, "dbox-proxy"),
                process(201, 101, "wstunnel"),
                process(102, 77, "dbox-proxy"),
                process(202, 102, "wstunnel"),
                process(103, 1, "dbox-proxy", user_id=current_user + 1),
                process(203, 103, "wstunnel", user_id=current_user + 1),
                process(104, 1, "dbox-proxy"),
                process(204, 104, "wstunnel", user_id=current_user + 1),
                process(105, 1, "dbox-proxy", command="dbox-proxy ordinary-proxy"),
                process(205, 105, "wstunnel"),
                process(106, 1, "zsh", command="zsh dbox-proxy _websocket-proxy"),
                process(206, 106, "wstunnel"),
                process(107, 1, "dbox-proxy"),
                process(207, 107, "ssh"),
                process(208, 1, "wstunnel"),
            ]
        }

        self.assertEqual(
            cleanup.groups(snapshot),
            [cleanup.ProcessGroup(proxy_pid=101, tunnel_pids=(201,))],
        )
        self.assertEqual(cleanup.active_proxy_count(snapshot), 1)

    def test_orders_proxy_and_tunnel_groups_deterministically(self) -> None:
        snapshot = {
            entry.pid: entry
            for entry in [
                process(102, 1, "dbox-proxy"),
                process(204, 102, "wstunnel"),
                process(203, 102, "wstunnel"),
                process(101, 1, "dbox-proxy"),
                process(201, 101, "wstunnel"),
            ]
        }

        self.assertEqual(
            cleanup.groups(snapshot),
            [
                cleanup.ProcessGroup(proxy_pid=101, tunnel_pids=(201,)),
                cleanup.ProcessGroup(proxy_pid=102, tunnel_pids=(203, 204)),
            ],
        )


class RunCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = io.StringIO()
        self.orphan_proxy = process(101, 1, "dbox-proxy")
        self.orphan_tunnel = process(201, 101, "wstunnel")
        self.active_proxy = process(102, 77, "dbox-proxy")
        self.active_tunnel = process(202, 102, "wstunnel")

    def output(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def run_table(self, table: ProcessTable, *, dry_run: bool = False) -> int:
        with (
            mock.patch.object(cleanup, "processes", side_effect=table.processes),
            mock.patch.object(cleanup.os, "kill", side_effect=table.kill),
            mock.patch.object(cleanup.time, "sleep"),
        ):
            return cleanup.run_cleanup(dry_run=dry_run, stream=self.stream)

    def test_no_matching_pair_is_a_successful_no_op(self) -> None:
        table = ProcessTable(self.active_proxy, self.active_tunnel)

        result = self.run_table(table)

        self.assertEqual(result, 0)
        self.assertEqual(table.signals, [])
        self.assertEqual(self.output()[-1]["remaining_orphan_proxy_count"], 0)
        self.assertEqual(self.output()[-1]["active_proxy_count_before"], 1)
        self.assertEqual(self.output()[-1]["active_proxy_count_after"], 1)

    def test_dry_run_reports_pairs_without_signaling(self) -> None:
        table = ProcessTable(
            self.orphan_proxy,
            self.orphan_tunnel,
            self.active_proxy,
            self.active_tunnel,
        )

        result = self.run_table(table, dry_run=True)

        self.assertEqual(result, 0)
        self.assertEqual(table.signals, [])
        self.assertTrue(self.output()[-1]["dry_run"])
        self.assertEqual(self.output()[-1]["remaining_orphan_proxy_count"], 1)
        self.assertEqual(self.output()[-1]["remaining_orphan_tunnel_count"], 1)

    def test_terminates_children_before_parents_and_preserves_active_chains(self) -> None:
        table = ProcessTable(
            self.orphan_proxy,
            self.orphan_tunnel,
            self.active_proxy,
            self.active_tunnel,
        )

        result = self.run_table(table)

        self.assertEqual(result, 0)
        self.assertEqual(
            table.signals, [(201, signal.SIGTERM), (101, signal.SIGTERM)]
        )
        self.assertEqual(set(table.entries), {102, 202})
        self.assertEqual(self.output()[-1]["term_sent"], 2)
        self.assertEqual(self.output()[-1]["active_proxy_count_before"], 1)
        self.assertEqual(self.output()[-1]["active_proxy_count_after"], 1)

    def test_escalates_resistant_child_before_terminating_parent(self) -> None:
        table = ProcessTable(self.orphan_proxy, self.orphan_tunnel)
        table.resist_term.add(self.orphan_tunnel.pid)

        result = self.run_table(table)

        self.assertEqual(result, 0)
        self.assertEqual(
            table.signals,
            [
                (201, signal.SIGTERM),
                (201, signal.SIGKILL),
                (101, signal.SIGTERM),
            ],
        )
        self.assertEqual(self.output()[-1]["kill_sent"], 1)

    def test_escalates_only_parent_that_previously_received_term(self) -> None:
        table = ProcessTable(self.orphan_proxy, self.orphan_tunnel)
        table.resist_term.add(self.orphan_proxy.pid)

        result = self.run_table(table)

        self.assertEqual(result, 0)
        self.assertEqual(
            table.signals,
            [
                (201, signal.SIGTERM),
                (101, signal.SIGTERM),
                (101, signal.SIGKILL),
            ],
        )

    def test_never_terminates_parent_while_verified_child_survives(self) -> None:
        table = ProcessTable(self.orphan_proxy, self.orphan_tunnel)
        table.resist_term.add(self.orphan_tunnel.pid)
        table.resist_kill.add(self.orphan_tunnel.pid)

        result = self.run_table(table)

        self.assertEqual(result, 2)
        self.assertEqual(len(table.signals), cleanup.MAX_SWEEPS * 2)
        self.assertTrue(all(process_id == 201 for process_id, _ in table.signals))
        self.assertEqual(self.output()[-1]["remaining_orphan_proxy_count"], 1)

    def test_reused_proxy_pid_is_never_signaled(self) -> None:
        table = ProcessTable(self.orphan_proxy, self.orphan_tunnel)

        def replace_proxy(process_id: int, _: signal.Signals) -> None:
            if process_id == self.orphan_tunnel.pid:
                table.entries[self.orphan_proxy.pid] = replace(
                    self.orphan_proxy, started_at="Fri Aug  7 10:01:02 2026"
                )

        table.after_signal = replace_proxy

        result = self.run_table(table)

        self.assertEqual(result, 2)
        self.assertEqual(table.signals, [(201, signal.SIGTERM)])
        self.assertIn(self.orphan_proxy.pid, table.entries)

    def test_signal_errors_are_reported_and_cleanup_retries(self) -> None:
        table = ProcessTable(self.orphan_proxy, self.orphan_tunnel)
        original_kill = table.kill
        attempts = 0

        def reject_first_signal(process_id: int, requested_signal: signal.Signals) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("operation not permitted")
            original_kill(process_id, requested_signal)

        with (
            mock.patch.object(cleanup, "processes", side_effect=table.processes),
            mock.patch.object(cleanup.os, "kill", side_effect=reject_first_signal),
            mock.patch.object(cleanup.time, "sleep"),
        ):
            result = cleanup.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        self.assertEqual(self.output()[-1]["errors"][0]["pid"], 201)
        self.assertEqual(self.output()[-1]["errors"][0]["signal"], "SIGTERM")

    def test_active_proxy_count_change_fails_closed(self) -> None:
        table = ProcessTable(
            self.orphan_proxy,
            self.orphan_tunnel,
            self.active_proxy,
            self.active_tunnel,
        )

        def remove_active_proxy(process_id: int, _: signal.Signals) -> None:
            if process_id == self.orphan_proxy.pid:
                table.entries.pop(self.active_proxy.pid)

        table.after_signal = remove_active_proxy

        result = self.run_table(table)

        self.assertEqual(result, 2)
        self.assertEqual(self.output()[-1]["active_proxy_count_before"], 1)
        self.assertEqual(self.output()[-1]["active_proxy_count_after"], 0)
        self.assertEqual(
            self.output()[-1]["errors"][0]["kind"], "active_proxy_count_changed"
        )


class RevalidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected_proxy = process(101, 1, "dbox-proxy")
        self.expected_tunnel = process(201, 101, "wstunnel")

    def test_refuses_reused_proxy_pid_with_changed_start_time(self) -> None:
        replacement = replace(
            self.expected_proxy, started_at="Fri Aug  7 10:01:02 2026"
        )
        with (
            mock.patch.object(cleanup, "processes", return_value={101: replacement}),
            mock.patch.object(cleanup.os, "kill") as kill,
        ):
            actual = cleanup.signal_proxy(
                101, signal.SIGTERM, expected=self.expected_proxy
            )

        self.assertFalse(actual)
        kill.assert_not_called()

    def test_refuses_reused_child_pid_even_if_executable_still_matches(self) -> None:
        replacement = replace(
            self.expected_tunnel, started_at="Fri Aug  7 10:01:02 2026"
        )
        with (
            mock.patch.object(cleanup, "processes", return_value={201: replacement}),
            mock.patch.object(cleanup.os, "kill") as kill,
        ):
            actual = cleanup.signal_tunnel(
                201,
                101,
                signal.SIGTERM,
                expected_tunnel=self.expected_tunnel,
                expected_proxy=self.expected_proxy,
            )

        self.assertFalse(actual)
        kill.assert_not_called()

    def test_refuses_child_when_parent_is_now_active(self) -> None:
        active_parent = replace(self.expected_proxy, parent_pid=77)

        def current(process_id: int) -> dict[int, cleanup.Process]:
            entry = self.expected_tunnel if process_id == 201 else active_parent
            return {process_id: entry}

        with (
            mock.patch.object(cleanup, "processes", side_effect=current),
            mock.patch.object(cleanup.os, "kill") as kill,
        ):
            actual = cleanup.signal_tunnel(
                201,
                101,
                signal.SIGTERM,
                expected_tunnel=self.expected_tunnel,
                expected_proxy=self.expected_proxy,
            )

        self.assertFalse(actual)
        kill.assert_not_called()

    def test_reparented_tunnel_allows_only_prior_term_escalation(self) -> None:
        reparented = replace(self.expected_tunnel, parent_pid=1)
        with (
            mock.patch.object(cleanup, "processes", return_value={201: reparented}),
            mock.patch.object(cleanup.os, "kill") as kill,
        ):
            term_result = cleanup.signal_tunnel(
                201,
                101,
                signal.SIGTERM,
                expected_tunnel=self.expected_tunnel,
                expected_proxy=self.expected_proxy,
            )
            kill_result = cleanup.signal_tunnel(
                201,
                101,
                signal.SIGKILL,
                expected_tunnel=self.expected_tunnel,
                expected_proxy=self.expected_proxy,
            )

        self.assertFalse(term_result)
        self.assertTrue(kill_result)
        kill.assert_called_once_with(201, signal.SIGKILL)

    def test_global_process_enumeration_failure_is_not_silent(self) -> None:
        error = subprocess.CalledProcessError(1, ["/bin/ps"])
        with mock.patch.object(cleanup.subprocess, "check_output", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError):
                cleanup.processes()

    def test_vanished_pid_enumeration_is_a_safe_no_op(self) -> None:
        error = subprocess.CalledProcessError(1, ["/bin/ps"])
        with mock.patch.object(cleanup.subprocess, "check_output", side_effect=error):
            actual = cleanup.processes(101)

        self.assertEqual(actual, {})


if __name__ == "__main__":
    unittest.main()

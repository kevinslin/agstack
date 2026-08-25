"""Safety and cleanup coverage for the computer-history MCP reaper."""

from __future__ import annotations

import importlib.util
import io
import json
import signal
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "clean_mcps.py"
MODULE_SPEC = importlib.util.spec_from_file_location("agcleanup_clean_mcps", SCRIPT_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
clean_mcps = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = clean_mcps
MODULE_SPEC.loader.exec_module(clean_mcps)


class ParseProcessesTests(unittest.TestCase):
    def test_matches_absolute_executable_paths_containing_spaces(self) -> None:
        executable = str(clean_mcps.EXPECTED_EXECUTABLE)
        command = f"{executable} computer-history mcp"

        self.assertIn(" ", executable)

        actual = clean_mcps.parse_processes(
            f"101 501 42 {command}\n",
            f"101 {executable}\n",
            user_id=501,
            excluded_pids=set(),
        )

        self.assertEqual(actual, [clean_mcps.Process(pid=101, parent_pid=42)])

    def test_rejects_other_users_protected_processes_and_unrelated_commands(self) -> None:
        executable = str(clean_mcps.EXPECTED_EXECUTABLE)
        process_output = "\n".join(
            [
                f"101 501 42 {executable} computer-history mcp",
                f"102 777 42 {executable} computer-history mcp",
                f"103 501 42 {executable} computer-history mcp",
                f"104 501 42 {executable} computer-use mcp",
                f"105 501 42 {executable} computer-history mcp --extra",
                "106 501 42 codex-app-server computer-history mcp",
                "107 501 42 Codex Renderer computer-history mcp",
                f"108 501 42 /bin/sh -c {executable} computer-history mcp",
                "109 501 42 /Applications/My App/SkyComputerUseClient computer-history mcp",
                "110 501 42 SkyComputerUseClient computer-history mcp",
                "garbage line",
            ]
        )
        executable_output = "\n".join(
            [
                "101 SkyComputerUseClient",
                "102 SkyComputerUseClient",
                "103 SkyComputerUseClient",
                "104 SkyComputerUseClient",
                "105 SkyComputerUseClient",
                "106 codex-app-server",
                "107 Codex Renderer",
                "108 /bin/sh",
                "109 /Applications/My App/OtherExecutable",
                "110 SkyComputerUseClient",
            ]
        )

        actual = clean_mcps.parse_processes(
            process_output,
            executable_output,
            user_id=501,
            excluded_pids={103},
        )

        self.assertEqual(actual, [clean_mcps.Process(pid=101, parent_pid=42)])

    def test_results_are_sorted_and_require_both_process_snapshots(self) -> None:
        executable = str(clean_mcps.EXPECTED_EXECUTABLE)
        process_output = "\n".join(
            [
                f"202 501 9 {executable} computer-history mcp",
                f"201 501 9 {executable} computer-history mcp",
                f"203 501 9 {executable} computer-history mcp",
            ]
        )
        executable_output = "\n".join(
            ["202 SkyComputerUseClient", "201 SkyComputerUseClient"]
        )

        actual = clean_mcps.parse_processes(
            process_output,
            executable_output,
            user_id=501,
            excluded_pids=set(),
        )

        self.assertEqual([process.pid for process in actual], [201, 202])


class RunCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = io.StringIO()
        self.process = clean_mcps.Process(pid=101, parent_pid=1)

    def output(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def test_no_matches_is_a_successful_no_op(self) -> None:
        with (
            mock.patch.object(clean_mcps, "matching_processes", return_value=[]),
            mock.patch.object(clean_mcps.os, "kill") as kill,
            mock.patch.object(clean_mcps.time, "sleep") as sleep,
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        kill.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(self.output()[-1]["remaining_count"], 0)

    def test_dry_run_reports_matches_without_signaling(self) -> None:
        with (
            mock.patch.object(
                clean_mcps, "matching_processes", return_value=[self.process]
            ),
            mock.patch.object(clean_mcps.os, "kill") as kill,
        ):
            result = clean_mcps.run_cleanup(dry_run=True, stream=self.stream)

        self.assertEqual(result, 0)
        kill.assert_not_called()
        self.assertTrue(self.output()[-1]["dry_run"])
        self.assertEqual(self.output()[-1]["remaining_count"], 1)

    def test_active_or_uncertain_helpers_are_preserved_without_signaling(self) -> None:
        active = clean_mcps.Process(pid=102, parent_pid=42)
        with (
            mock.patch.object(clean_mcps, "matching_processes", return_value=[active]),
            mock.patch.object(clean_mcps.os, "kill") as kill,
            mock.patch.object(clean_mcps.time, "sleep") as sleep,
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        kill.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(self.output()[0]["eligible_count"], 0)
        self.assertEqual(self.output()[-1]["protected_count"], 1)
        self.assertEqual(self.output()[-1]["remaining_count"], 1)
        self.assertEqual(self.output()[-1]["remaining_eligible_count"], 0)

    def test_orphans_are_cleaned_while_active_helpers_remain_protected(self) -> None:
        active = clean_mcps.Process(pid=102, parent_pid=42)
        matching_results = [
            [self.process, active],
            [active],
            [active],
            *[[active] for _ in range(clean_mcps.QUIET_POLLS)],
            [active],
        ]
        with (
            mock.patch.object(
                clean_mcps, "matching_processes", side_effect=matching_results
            ),
            mock.patch.object(
                clean_mcps, "send_if_still_matching", return_value=True
            ) as send,
            mock.patch.object(clean_mcps.time, "sleep"),
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        send.assert_called_once_with(101, signal.SIGTERM)
        self.assertEqual(self.output()[-1]["term_sent"], 1)
        self.assertEqual(self.output()[-1]["protected_count"], 1)
        self.assertEqual(self.output()[-1]["remaining_count"], 1)
        self.assertEqual(self.output()[-1]["remaining_eligible_count"], 0)

    def test_term_resistant_helper_receives_kill(self) -> None:
        matching_results = [
            [self.process],
            *[[self.process] for _ in range(clean_mcps.GRACE_POLLS)],
            [],
            *[[] for _ in range(clean_mcps.QUIET_POLLS)],
            [],
        ]
        with (
            mock.patch.object(
                clean_mcps, "matching_processes", side_effect=matching_results
            ),
            mock.patch.object(
                clean_mcps, "send_if_still_matching", return_value=True
            ) as send,
            mock.patch.object(clean_mcps.time, "sleep"),
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        self.assertEqual(
            send.call_args_list,
            [mock.call(101, signal.SIGTERM), mock.call(101, signal.SIGKILL)],
        )
        self.assertEqual(self.output()[-1]["term_sent"], 1)
        self.assertEqual(self.output()[-1]["kill_sent"], 1)

    def test_respawned_helper_gets_term_in_later_sweep(self) -> None:
        respawned = clean_mcps.Process(pid=102, parent_pid=1)
        matching_results = [
            [self.process],
            [respawned],
            [respawned],
            [],
            [],
            *[[] for _ in range(clean_mcps.QUIET_POLLS)],
            [],
        ]
        with (
            mock.patch.object(
                clean_mcps, "matching_processes", side_effect=matching_results
            ),
            mock.patch.object(
                clean_mcps, "send_if_still_matching", return_value=True
            ) as send,
            mock.patch.object(clean_mcps.time, "sleep"),
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 0)
        self.assertEqual(
            send.call_args_list,
            [mock.call(101, signal.SIGTERM), mock.call(102, signal.SIGTERM)],
        )
        self.assertEqual(self.output()[-1]["term_sent"], 2)

    def test_persistent_helpers_fail_after_bounded_sweeps(self) -> None:
        with (
            mock.patch.object(
                clean_mcps, "matching_processes", return_value=[self.process]
            ),
            mock.patch.object(
                clean_mcps, "send_if_still_matching", return_value=True
            ) as send,
            mock.patch.object(clean_mcps.time, "sleep"),
        ):
            result = clean_mcps.run_cleanup(stream=self.stream)

        self.assertEqual(result, 2)
        self.assertEqual(send.call_count, clean_mcps.MAX_SWEEPS * 2)
        self.assertEqual(self.output()[-1]["remaining_count"], 1)

    def test_revalidates_pid_before_sending_signal(self) -> None:
        with (
            mock.patch.object(clean_mcps, "matching_processes", return_value=[]),
            mock.patch.object(clean_mcps.os, "kill") as kill,
        ):
            result = clean_mcps.send_if_still_matching(101, signal.SIGTERM)

        self.assertFalse(result)
        kill.assert_not_called()

    def test_revalidation_refuses_helper_that_has_an_active_parent(self) -> None:
        active = clean_mcps.Process(pid=101, parent_pid=42)
        with (
            mock.patch.object(clean_mcps, "matching_processes", return_value=[active]),
            mock.patch.object(clean_mcps.os, "kill") as kill,
        ):
            result = clean_mcps.send_if_still_matching(101, signal.SIGTERM)

        self.assertFalse(result)
        kill.assert_not_called()

    def test_global_process_enumeration_failure_is_not_silent(self) -> None:
        error = subprocess.CalledProcessError(1, ["/bin/ps"])

        with mock.patch.object(
            clean_mcps.subprocess, "check_output", side_effect=error
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                clean_mcps.matching_processes()

    def test_vanished_pid_enumeration_is_a_safe_no_op(self) -> None:
        error = subprocess.CalledProcessError(1, ["/bin/ps"])

        with mock.patch.object(
            clean_mcps.subprocess, "check_output", side_effect=error
        ):
            actual = clean_mcps.matching_processes(101)

        self.assertEqual(actual, [])


if __name__ == "__main__":
    unittest.main()

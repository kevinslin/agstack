#!/usr/bin/env python3
"""Safely reap the current user's Codex computer-history MCP helpers."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath
from typing import TextIO


EXECUTABLE_NAME = "SkyComputerUseClient"
CODEX_DIRECTORY = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
EXPECTED_EXECUTABLE = (
    CODEX_DIRECTORY
    / "computer-use"
    / "Codex Computer Use.app"
    / "Contents"
    / "SharedSupport"
    / "SkyComputerUseClient.app"
    / "Contents"
    / "MacOS"
    / EXECUTABLE_NAME
)
COMMAND_PATTERN = re.compile(
    rf"\A{re.escape(str(EXPECTED_EXECUTABLE))}"
    r"[ \t]+computer-history[ \t]+mcp[ \t]*\Z"
)
MAX_SWEEPS = 4
GRACE_POLLS = 5
QUIET_POLLS = 3
POLL_INTERVAL_SECONDS = 0.2


@dataclass(frozen=True)
class Process:
    pid: int
    parent_pid: int


def parse_processes(
    process_output: str,
    executable_output: str,
    *,
    user_id: int,
    excluded_pids: set[int],
) -> list[Process]:
    """Join ps command and executable snapshots without splitting executable paths."""
    executable_names: dict[int, str] = {}
    for line in executable_output.splitlines():
        columns = line.strip().split(None, 1)
        if len(columns) != 2:
            continue
        try:
            process_id = int(columns[0])
        except ValueError:
            continue
        executable_names[process_id] = PurePath(columns[1]).name

    matches: list[Process] = []
    for line in process_output.splitlines():
        columns = line.strip().split(None, 3)
        if len(columns) != 4:
            continue
        try:
            process_id, process_user_id, parent_id = map(int, columns[:3])
        except ValueError:
            continue
        if process_user_id != user_id or process_id in excluded_pids:
            continue
        if executable_names.get(process_id) != EXECUTABLE_NAME:
            continue
        if COMMAND_PATTERN.fullmatch(columns[3]) is None:
            continue
        matches.append(Process(pid=process_id, parent_pid=parent_id))

    return sorted(matches, key=lambda process: process.pid)


def matching_processes(process_id: int | None = None) -> list[Process]:
    """Identify exact current-user helpers from independent ps executable fields."""
    selector = ["-axo"] if process_id is None else ["-p", str(process_id), "-o"]
    try:
        process_output = subprocess.check_output(
            ["/bin/ps", "-ww", *selector, "pid=,uid=,ppid=,command="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        executable_output = subprocess.check_output(
            ["/bin/ps", "-ww", *selector, "pid=,comm="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        if process_id is not None:
            return []
        raise

    return parse_processes(
        process_output,
        executable_output,
        user_id=os.getuid(),
        excluded_pids={os.getpid(), os.getppid()},
    )


def send_if_still_matching(process_id: int, requested_signal: signal.Signals) -> bool:
    """Recheck ownership, executable, arguments, and orphan status before signaling."""
    if not any(
        process.pid == process_id and process.parent_pid == 1
        for process in matching_processes(process_id)
    ):
        return False
    try:
        os.kill(process_id, requested_signal)
    except ProcessLookupError:
        return False
    return True


def emit(payload: dict[str, object], stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True), file=stream, flush=True)


def run_cleanup(*, dry_run: bool = False, stream: TextIO | None = None) -> int:
    output = sys.stdout if stream is None else stream
    initial = matching_processes()
    eligible = [process for process in initial if process.parent_pid == 1]
    protected = [process for process in initial if process.parent_pid != 1]
    emit(
        {
            "phase": "before",
            "dry_run": dry_run,
            "count": len(initial),
            "eligible_count": len(eligible),
            "protected_count": len(protected),
            "processes": [asdict(process) for process in initial],
        },
        output,
    )

    term_sent = 0
    kill_sent = 0
    errors: list[dict[str, object]] = []

    if dry_run or not eligible:
        emit(
            {
                "phase": "after",
                "dry_run": dry_run,
                "initial_count": len(initial),
                "initial_eligible_count": len(eligible),
                "term_sent": term_sent,
                "kill_sent": kill_sent,
                "remaining_count": len(initial),
                "remaining_eligible_count": len(eligible),
                "protected_count": len(protected),
                "remaining": [asdict(process) for process in initial],
                "errors": errors,
            },
            output,
        )
        return 0

    current = eligible
    for sweep in range(1, MAX_SWEEPS + 1):
        if not current:
            break

        term_targets: set[int] = set()
        for process in current:
            try:
                if send_if_still_matching(process.pid, signal.SIGTERM):
                    term_targets.add(process.pid)
                    term_sent += 1
            except OSError as error:
                errors.append(
                    {"pid": process.pid, "signal": "SIGTERM", "error": str(error)}
                )

        survivors: list[Process] = []
        if term_targets:
            for _ in range(GRACE_POLLS):
                time.sleep(POLL_INTERVAL_SECONDS)
                observed = matching_processes()
                survivors = [
                    process
                    for process in observed
                    if process.pid in term_targets and process.parent_pid == 1
                ]
                if not survivors:
                    break

        if survivors:
            for process in survivors:
                try:
                    if send_if_still_matching(process.pid, signal.SIGKILL):
                        kill_sent += 1
                except OSError as error:
                    errors.append(
                        {"pid": process.pid, "signal": "SIGKILL", "error": str(error)}
                    )
            time.sleep(POLL_INTERVAL_SECONDS)

        observed = matching_processes()
        current = [process for process in observed if process.parent_pid == 1]
        emit(
            {
                "phase": "sweep",
                "sweep": sweep,
                "term_sent_total": term_sent,
                "kill_sent_total": kill_sent,
                "remaining_count": len(observed),
                "remaining_eligible_count": len(current),
                "protected_count": len(observed) - len(current),
            },
            output,
        )

        if not current:
            for _ in range(QUIET_POLLS):
                time.sleep(POLL_INTERVAL_SECONDS)
                observed = matching_processes()
                current = [
                    process for process in observed if process.parent_pid == 1
                ]
                if current:
                    break
            if not current:
                break

    final = matching_processes()
    remaining_eligible = [process for process in final if process.parent_pid == 1]
    emit(
        {
            "phase": "after",
            "dry_run": dry_run,
            "initial_count": len(initial),
            "initial_eligible_count": len(eligible),
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "remaining_count": len(final),
            "remaining_eligible_count": len(remaining_eligible),
            "protected_count": len(final) - len(remaining_eligible),
            "remaining": [asdict(process) for process in final],
            "errors": errors,
        },
        output,
    )
    return 0 if not remaining_eligible else 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="list exact matches without signaling"
    )
    arguments = parser.parse_args()
    raise SystemExit(run_cleanup(dry_run=arguments.dry_run))


if __name__ == "__main__":
    main()

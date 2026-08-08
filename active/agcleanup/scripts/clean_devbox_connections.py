#!/usr/bin/env python3
"""Safely reap orphaned current-user DevBox websocket proxy/tunnel pairs."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import PurePath
from typing import TextIO


PROXY_EXECUTABLE = "dbox-proxy"
TUNNEL_EXECUTABLE = "wstunnel"
PROXY_ARGUMENT = "_websocket-proxy"
MAX_SWEEPS = 3
GRACE_POLLS = 5
POLL_INTERVAL_SECONDS = 0.2


@dataclass(frozen=True)
class Process:
    pid: int
    uid: int
    parent_pid: int
    executable: str
    command: str
    started_at: str


@dataclass(frozen=True)
class ProcessGroup:
    proxy_pid: int
    tunnel_pids: tuple[int, ...]


def parse_processes(
    process_output: str, executable_output: str, start_time_output: str
) -> dict[int, Process]:
    """Join independent ps command, executable, and start-identity snapshots."""
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

    start_times: dict[int, str] = {}
    for line in start_time_output.splitlines():
        columns = line.strip().split(None, 1)
        if len(columns) != 2:
            continue
        try:
            start_times[int(columns[0])] = columns[1]
        except ValueError:
            continue

    found: dict[int, Process] = {}
    for line in process_output.splitlines():
        columns = line.strip().split(None, 3)
        if len(columns) != 4:
            continue
        try:
            process_id, user_id, parent_id = map(int, columns[:3])
        except ValueError:
            continue
        executable = executable_names.get(process_id)
        started_at = start_times.get(process_id)
        if executable is None or started_at is None:
            continue
        found[process_id] = Process(
            pid=process_id,
            uid=user_id,
            parent_pid=parent_id,
            executable=executable,
            command=columns[3],
            started_at=started_at,
        )

    return found


def processes(process_id: int | None = None) -> dict[int, Process]:
    """Read both actual executable identity and complete process arguments."""
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
        start_time_output = subprocess.check_output(
            ["/bin/ps", "-ww", *selector, "pid=,lstart="],
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except subprocess.CalledProcessError:
        if process_id is not None:
            return {}
        raise

    return parse_processes(process_output, executable_output, start_time_output)


def same_process(current: Process, expected: Process) -> bool:
    """Reject PID reuse while allowing a previously verified child to reparent."""
    return (
        current.pid == expected.pid
        and current.uid == expected.uid
        and current.executable == expected.executable
        and current.command == expected.command
        and current.started_at == expected.started_at
    )


def proxy(process: Process, *, user_id: int | None = None) -> bool:
    expected_user = os.getuid() if user_id is None else user_id
    return (
        process.uid == expected_user
        and process.executable == PROXY_EXECUTABLE
        and PROXY_ARGUMENT in process.command
    )


def tunnel(process: Process, *, user_id: int | None = None) -> bool:
    expected_user = os.getuid() if user_id is None else user_id
    return process.uid == expected_user and process.executable == TUNNEL_EXECUTABLE


def groups(
    snapshot: dict[int, Process], *, user_id: int | None = None
) -> list[ProcessGroup]:
    """Require an orphaned proxy and its direct same-user tunnel child."""
    children: dict[int, list[Process]] = {}
    for process in snapshot.values():
        children.setdefault(process.parent_pid, []).append(process)

    matching: list[ProcessGroup] = []
    for process in snapshot.values():
        if not proxy(process, user_id=user_id) or process.parent_pid != 1:
            continue
        tunnel_pids = sorted(
            child.pid
            for child in children.get(process.pid, [])
            if tunnel(child, user_id=user_id)
        )
        if tunnel_pids:
            matching.append(
                ProcessGroup(proxy_pid=process.pid, tunnel_pids=tuple(tunnel_pids))
            )

    return sorted(matching, key=lambda group: group.proxy_pid)


def active_proxy_count(snapshot: dict[int, Process]) -> int:
    return sum(
        1
        for process in snapshot.values()
        if proxy(process) and process.parent_pid != 1
    )


def remaining_groups(
    snapshot: dict[int, Process], targeted_proxy_pids: set[int]
) -> list[ProcessGroup]:
    """Keep tracking verified parents after their final tunnel child disappears."""
    remaining = {group.proxy_pid: group for group in groups(snapshot)}
    for proxy_pid in targeted_proxy_pids:
        process = snapshot.get(proxy_pid)
        if process is not None and proxy(process) and process.parent_pid == 1:
            remaining.setdefault(
                proxy_pid, ProcessGroup(proxy_pid=proxy_pid, tunnel_pids=())
            )
    return sorted(remaining.values(), key=lambda group: group.proxy_pid)


def signal_tunnel(
    process_id: int,
    owner_proxy: int,
    requested_signal: signal.Signals,
    *,
    expected_tunnel: Process,
    expected_proxy: Process,
) -> bool:
    """Revalidate child identity and its verified orphaned parent before signaling."""
    current = processes(process_id).get(process_id)
    if current is None or not same_process(current, expected_tunnel) or not tunnel(current):
        return False

    if current.parent_pid == owner_proxy:
        parent = processes(owner_proxy).get(owner_proxy)
        if (
            parent is None
            or not same_process(parent, expected_proxy)
            or not proxy(parent)
            or parent.parent_pid != 1
        ):
            return False
    elif current.parent_pid != 1 or requested_signal != signal.SIGKILL:
        return False

    try:
        os.kill(process_id, requested_signal)
    except ProcessLookupError:
        return False
    return True


def signal_proxy(
    process_id: int, requested_signal: signal.Signals, *, expected: Process
) -> bool:
    """Revalidate the orphaned, same-user actual proxy immediately before signaling."""
    current = processes(process_id).get(process_id)
    if (
        current is None
        or not same_process(current, expected)
        or not proxy(current)
        or current.parent_pid != 1
    ):
        return False
    try:
        os.kill(process_id, requested_signal)
    except ProcessLookupError:
        return False
    return True


def surviving_tunnels(
    targets: set[tuple[int, int]], verified_tunnels: dict[tuple[int, int], Process]
) -> set[tuple[int, int]]:
    survivors: set[tuple[int, int]] = set()
    for process_id, owner_proxy in targets:
        current = processes(process_id).get(process_id)
        if (
            current is not None
            and same_process(current, verified_tunnels[(process_id, owner_proxy)])
            and tunnel(current)
            and current.parent_pid in {owner_proxy, 1}
        ):
            survivors.add((process_id, owner_proxy))
    return survivors


def surviving_proxies(
    targets: set[int], verified_proxies: dict[int, Process]
) -> set[int]:
    survivors: set[int] = set()
    for process_id in targets:
        current = processes(process_id).get(process_id)
        if (
            current is not None
            and same_process(current, verified_proxies[process_id])
            and proxy(current)
            and current.parent_pid == 1
        ):
            survivors.add(process_id)
    return survivors


def emit(payload: dict[str, object], stream: TextIO) -> None:
    print(json.dumps(payload, sort_keys=True), file=stream, flush=True)


def run_cleanup(*, dry_run: bool = False, stream: TextIO | None = None) -> int:
    output = sys.stdout if stream is None else stream
    initial_snapshot = processes()
    initial_groups = groups(initial_snapshot)
    initial_tunnel_count = sum(len(group.tunnel_pids) for group in initial_groups)
    active_before = active_proxy_count(initial_snapshot)
    emit(
        {
            "phase": "before",
            "dry_run": dry_run,
            "orphan_proxy_count": len(initial_groups),
            "orphan_tunnel_count": initial_tunnel_count,
            "active_proxy_count": active_before,
            "groups": [asdict(group) for group in initial_groups],
        },
        output,
    )

    term_sent = 0
    kill_sent = 0
    errors: list[dict[str, object]] = []

    if dry_run or not initial_groups:
        emit(
            {
                "phase": "after",
                "dry_run": dry_run,
                "initial_orphan_proxy_count": len(initial_groups),
                "initial_orphan_tunnel_count": initial_tunnel_count,
                "term_sent": term_sent,
                "kill_sent": kill_sent,
                "remaining_orphan_proxy_count": len(initial_groups),
                "remaining_orphan_tunnel_count": initial_tunnel_count,
                "remaining": [asdict(group) for group in initial_groups],
                "active_proxy_count_before": active_before,
                "active_proxy_count_after": active_before,
                "errors": errors,
            },
            output,
        )
        return 0

    targeted_proxy_pids = {group.proxy_pid for group in initial_groups}
    verified_proxies = {
        group.proxy_pid: initial_snapshot[group.proxy_pid] for group in initial_groups
    }
    verified_tunnels = {
        (tunnel_pid, group.proxy_pid): initial_snapshot[tunnel_pid]
        for group in initial_groups
        for tunnel_pid in group.tunnel_pids
    }
    current_groups = initial_groups
    current_snapshot = initial_snapshot

    for sweep in range(1, MAX_SWEEPS + 1):
        if not current_groups:
            break

        targeted_proxy_pids.update(group.proxy_pid for group in current_groups)
        for group in current_groups:
            verified_proxies.setdefault(
                group.proxy_pid, current_snapshot[group.proxy_pid]
            )
            for tunnel_pid in group.tunnel_pids:
                verified_tunnels.setdefault(
                    (tunnel_pid, group.proxy_pid), current_snapshot[tunnel_pid]
                )
        child_targets = {
            (tunnel_pid, group.proxy_pid)
            for group in current_groups
            for tunnel_pid in group.tunnel_pids
        }
        term_children: set[tuple[int, int]] = set()

        for tunnel_pid, proxy_pid in sorted(child_targets):
            try:
                if signal_tunnel(
                    tunnel_pid,
                    proxy_pid,
                    signal.SIGTERM,
                    expected_tunnel=verified_tunnels[(tunnel_pid, proxy_pid)],
                    expected_proxy=verified_proxies[proxy_pid],
                ):
                    term_children.add((tunnel_pid, proxy_pid))
                    term_sent += 1
            except OSError as error:
                errors.append(
                    {"pid": tunnel_pid, "signal": "SIGTERM", "error": str(error)}
                )

        child_survivors = surviving_tunnels(child_targets, verified_tunnels)
        for _ in range(GRACE_POLLS):
            if not child_survivors:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
            child_survivors = surviving_tunnels(child_survivors, verified_tunnels)

        escalated_children = child_survivors.intersection(term_children)
        for tunnel_pid, proxy_pid in sorted(escalated_children):
            try:
                if signal_tunnel(
                    tunnel_pid,
                    proxy_pid,
                    signal.SIGKILL,
                    expected_tunnel=verified_tunnels[(tunnel_pid, proxy_pid)],
                    expected_proxy=verified_proxies[proxy_pid],
                ):
                    kill_sent += 1
            except OSError as error:
                errors.append(
                    {"pid": tunnel_pid, "signal": "SIGKILL", "error": str(error)}
                )

        if escalated_children:
            for _ in range(GRACE_POLLS):
                child_survivors = surviving_tunnels(child_survivors, verified_tunnels)
                if not child_survivors:
                    break
                time.sleep(POLL_INTERVAL_SECONDS)

        parents_with_children = {
            proxy_pid
            for _, proxy_pid in surviving_tunnels(child_targets, verified_tunnels)
        }
        fresh_snapshot = processes()
        for process in fresh_snapshot.values():
            if tunnel(process) and process.parent_pid in targeted_proxy_pids:
                parents_with_children.add(process.parent_pid)

        parent_targets = {
            group.proxy_pid
            for group in current_groups
            if group.proxy_pid not in parents_with_children
        }
        term_parents: set[int] = set()
        for proxy_pid in sorted(parent_targets):
            try:
                if signal_proxy(
                    proxy_pid, signal.SIGTERM, expected=verified_proxies[proxy_pid]
                ):
                    term_parents.add(proxy_pid)
                    term_sent += 1
            except OSError as error:
                errors.append(
                    {"pid": proxy_pid, "signal": "SIGTERM", "error": str(error)}
                )

        parent_survivors = surviving_proxies(term_parents, verified_proxies)
        for _ in range(GRACE_POLLS):
            if not parent_survivors:
                break
            time.sleep(POLL_INTERVAL_SECONDS)
            parent_survivors = surviving_proxies(parent_survivors, verified_proxies)

        for proxy_pid in sorted(parent_survivors):
            try:
                if signal_proxy(
                    proxy_pid, signal.SIGKILL, expected=verified_proxies[proxy_pid]
                ):
                    kill_sent += 1
            except OSError as error:
                errors.append(
                    {"pid": proxy_pid, "signal": "SIGKILL", "error": str(error)}
                )

        if parent_survivors:
            time.sleep(POLL_INTERVAL_SECONDS)

        current_snapshot = processes()
        current_groups = remaining_groups(current_snapshot, targeted_proxy_pids)
        emit(
            {
                "phase": "sweep",
                "sweep": sweep,
                "term_sent_total": term_sent,
                "kill_sent_total": kill_sent,
                "remaining_orphan_proxy_count": len(current_groups),
                "remaining_orphan_tunnel_count": sum(
                    len(group.tunnel_pids) for group in current_groups
                ),
            },
            output,
        )

    final_snapshot = processes()
    final_groups = remaining_groups(final_snapshot, targeted_proxy_pids)
    active_after = active_proxy_count(final_snapshot)
    if active_after != active_before:
        errors.append(
            {
                "kind": "active_proxy_count_changed",
                "before": active_before,
                "after": active_after,
            }
        )

    emit(
        {
            "phase": "after",
            "dry_run": dry_run,
            "initial_orphan_proxy_count": len(initial_groups),
            "initial_orphan_tunnel_count": initial_tunnel_count,
            "term_sent": term_sent,
            "kill_sent": kill_sent,
            "remaining_orphan_proxy_count": len(final_groups),
            "remaining_orphan_tunnel_count": sum(
                len(group.tunnel_pids) for group in final_groups
            ),
            "remaining": [asdict(group) for group in final_groups],
            "active_proxy_count_before": active_before,
            "active_proxy_count_after": active_after,
            "errors": errors,
        },
        output,
    )
    return 0 if not final_groups and active_after == active_before else 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="list verified pairs without signaling"
    )
    arguments = parser.parse_args()
    try:
        result = run_cleanup(dry_run=arguments.dry_run)
    except (subprocess.CalledProcessError, OSError) as error:
        emit({"phase": "error", "error": str(error)}, sys.stdout)
        result = 2
    raise SystemExit(result)


if __name__ == "__main__":
    main()

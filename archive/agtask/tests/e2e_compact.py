#!/usr/bin/env python3
"""Bounded manual proof for real app-server compaction hooks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import selectors
import sqlite3
import subprocess
import sys
import time
from typing import Any, Callable


def compact_count(database: Path, thread_id: str) -> int:
    # The proof observes a live WAL database while hooks are writing. A normal
    # connection participates in WAL visibility; a read-only connection cannot
    # open a checkpointed WAL database after its last -shm sidecar disappears.
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM rollout "
            "WHERE thread_id=? AND role='meta' AND ("
            "(turn_id LIKE 'compact:%:manual' AND message='compaction:manual') OR "
            "(turn_id LIKE 'compact:%:auto' AND message='compaction:auto'))",
            (thread_id,),
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def turn_rollouts(database: Path, thread_id: str, turn_id: str) -> list[dict[str, str]]:
    connection = sqlite3.connect(database)
    try:
        return [
            {"role": str(row[0]), "message": str(row[1])}
            for row in connection.execute(
                "SELECT role,message FROM rollout "
                "WHERE thread_id=? AND turn_id=? AND role IN ('user','assistant') "
                "ORDER BY id",
                (thread_id, turn_id),
            )
        ]
    finally:
        connection.close()


def logical_thread_id(database: Path, session_id: str) -> str:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute(
            "SELECT id FROM thread WHERE session_id=?", (session_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"session is not tracked: {session_id}")
        return str(row[0])
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    ledger_thread_id = logical_thread_id(args.database, args.session_id)
    before = compact_count(args.database, ledger_thread_id)
    process = subprocess.Popen(
        [str(args.codex), "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    messages: list[dict[str, Any]] = []
    errors: list[str] = []

    def send(message: dict[str, Any]) -> None:
        process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def pump_until(predicate: Callable[[], bool], deadline: float) -> None:
        while time.monotonic() < deadline:
            if predicate():
                return
            for key, _mask in selector.select(timeout=0.25):
                line = key.fileobj.readline()
                if not line:
                    continue
                if key.data == "stderr":
                    errors.append(line.rstrip())
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    errors.append("non-JSON stdout: " + line.rstrip())
            if process.poll() is not None and not predicate():
                raise RuntimeError(f"app-server exited early with {process.returncode}")
        raise TimeoutError("timed out waiting for app-server proof condition")

    def has_response(request_id: int) -> bool:
        return any(message.get("id") == request_id for message in messages)

    try:
        deadline = time.monotonic() + args.timeout
        send(
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "agtask_e2e",
                        "title": "agtask compaction proof",
                        "version": "1.0.0",
                    }
                },
            }
        )
        pump_until(lambda: has_response(0), deadline)
        send({"method": "initialized", "params": {}})
        send(
            {
                "method": "thread/resume",
                "id": 1,
                "params": {"threadId": args.session_id},
            }
        )
        pump_until(lambda: has_response(1), deadline)
        send(
            {
                "method": "thread/compact/start",
                "id": 2,
                "params": {"threadId": args.session_id},
            }
        )
        pump_until(lambda: has_response(2), deadline)
        pump_until(lambda: compact_count(args.database, ledger_thread_id) > before, deadline)

        send(
            {
                "method": "turn/start",
                "id": 3,
                "params": {
                    "threadId": args.session_id,
                    "input": [
                        {
                            "type": "text",
                            "text": (
                                "Report the tracked title and status restored after compaction, "
                                "then end with exactly REAL_COMPACT_READY."
                            ),
                        }
                    ],
                },
            }
        )
        pump_until(lambda: has_response(3), deadline)

        turn_response = next(message for message in messages if message.get("id") == 3)
        if "error" in turn_response:
            raise RuntimeError(f"turn/start failed: {turn_response['error']}")
        verification_turn_id = (
            turn_response.get("result", {}).get("turn", {}).get("id")
        )
        if not isinstance(verification_turn_id, str) or not verification_turn_id:
            raise RuntimeError("turn/start response did not contain a verification turn ID")

        def turn_completed() -> bool:
            return any(
                message.get("method") == "turn/completed"
                and message.get("params", {}).get("turn", {}).get("id")
                == verification_turn_id
                for message in messages
            )

        pump_until(turn_completed, deadline)
        pump_until(
            lambda: {
                rollout["role"]
                for rollout in turn_rollouts(
                    args.database, ledger_thread_id, verification_turn_id
                )
            }
            == {"user", "assistant"},
            deadline,
        )
        after = compact_count(args.database, ledger_thread_id)
        verification_rollouts = turn_rollouts(
            args.database, ledger_thread_id, verification_turn_id
        )
        assistant = [
            message.get("params", {}).get("item", {}).get("text")
            for message in messages
            if message.get("method") == "item/completed"
            and message.get("params", {}).get("item", {}).get("type")
            in {"agentMessage", "agent_message"}
        ]
        result = {
            "id": ledger_thread_id,
            "session_id": args.session_id,
            "compact_rollouts_before": before,
            "compact_rollouts_after": after,
            "verification_turn_id": verification_turn_id,
            "verification_rollouts": verification_rollouts,
            "assistant_messages": [value for value in assistant if isinstance(value, str)],
            "methods": [message.get("method") for message in messages if message.get("method")],
            "stderr_tail": errors[-10:],
        }
        print(json.dumps(result, indent=2))
        if after != before + 1:
            raise RuntimeError("real compaction did not append exactly one rollout")
        if [rollout["role"] for rollout in verification_rollouts] != [
            "user",
            "assistant",
        ]:
            raise RuntimeError(
                "post-compaction verification turn did not append user and assistant rollouts"
            )
        if not all(
            rollout["message"] and len(rollout["message"]) <= 240
            for rollout in verification_rollouts
        ):
            raise RuntimeError(
                "post-compaction verification rollouts did not contain bounded messages"
            )
        if not any("REAL_COMPACT_READY" in value for value in result["assistant_messages"]):
            raise RuntimeError("post-compaction turn did not return the expected proof marker")
        return 0
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
    except (OSError, RuntimeError, TimeoutError, sqlite3.Error) as error:
        print(f"e2e_compact: {error}", file=sys.stderr)
        raise SystemExit(1)

#!/usr/bin/env python3
"""List local Codex threads through the supported app-server cursor protocol."""

from __future__ import annotations

import argparse
import json
import queue
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, TextIO


DEFAULT_LIMIT = 50
DEFAULT_MAX_PAGES = 10
DEFAULT_AGE_SECONDS = 604800
DEFAULT_TIMEOUT_SECONDS = 180.0
SOURCE_KINDS = [
    "cli",
    "vscode",
    "exec",
    "appServer",
    "subAgent",
    "subAgentReview",
    "subAgentCompact",
    "subAgentThreadSpawn",
    "subAgentOther",
    "unknown",
]


class ProtocolError(RuntimeError):
    """Raised when the app-server protocol cannot be completed safely."""


class ThreadListClient(Protocol):
    def thread_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return one `thread/list` response result."""


@dataclass(frozen=True)
class ThreadSummary:
    hostId: str
    kind: str
    threadId: str
    updatedAt: int
    createdAt: int | None
    recencyAt: int | None
    name: str | None
    cwd: str | None
    status: Any
    source: Any


@dataclass(frozen=True)
class CollectionResult:
    hostId: str
    mode: str
    generatedAt: int
    startCursor: str | None
    cutoffTimestamp: int | None
    updatedSince: int | None
    updatedBefore: int | None
    pageLimit: int
    pageSize: int
    pagesFetched: int
    examinedCount: int
    duplicateCount: int
    malformedCount: int
    staleCount: int
    windowCount: int
    exhaustive: bool
    incompleteReason: str | None
    nextCursor: str | None
    staleThreads: list[ThreadSummary]
    windowThreads: list[ThreadSummary]


class AppServerJsonlClient:
    """Small JSONL client for `codex app-server --stdio`."""

    def __init__(
        self,
        *,
        command: list[str],
        host_id: str,
        timeout_seconds: float,
    ) -> None:
        self.host_id = host_id
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr: queue.Queue[str] = queue.Queue()
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self._process.stdout is not None
        assert self._process.stderr is not None
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, args=(self._process.stdout,), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, args=(self._process.stderr,), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        try:
            self._initialize()
        except Exception:
            self.close()
            raise

    @property
    def stderr_lines(self) -> list[str]:
        lines: list[str] = []
        while True:
            try:
                lines.append(self._stderr.get_nowait())
            except queue.Empty:
                return lines

    def close(self) -> None:
        if self._process.stdin is not None and not self._process.stdin.closed:
            self._process.stdin.close()
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)

    def thread_list(self, params: dict[str, Any]) -> dict[str, Any]:
        result = self._request("thread/list", params)
        if not isinstance(result, dict):
            raise ProtocolError("thread/list returned a non-object result")
        return result

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "agcleanup-list-stale-threads",
                    "title": None,
                    "version": "0",
                },
                "capabilities": {
                    "experimentalApi": True,
                    "requestAttestation": False,
                },
            },
        )
        self._notify("initialized")

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._write({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out after {self.timeout_seconds:g}s")
            try:
                message = self._messages.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                if self._process.poll() is not None:
                    stderr = "\n".join(self.stderr_lines)
                    detail = f": {stderr}" if stderr else ""
                    raise ProtocolError(
                        f"app-server exited before {method} response{detail}"
                    )
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise ProtocolError(f"{method} failed: {message['error']}")
            if "result" not in message:
                raise ProtocolError(f"{method} response omitted result")
            return message["result"]

    def _notify(self, method: str) -> None:
        self._write({"method": method})

    def _write(self, message: dict[str, Any]) -> None:
        if self._process.stdin is None or self._process.stdin.closed:
            raise ProtocolError("app-server stdin is closed")
        self._process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    def _read_stdout(self, stream: TextIO) -> None:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._messages.put({"method": "invalid-json", "line": line})
                continue
            if isinstance(message, dict):
                self._messages.put(message)

    def _read_stderr(self, stream: TextIO) -> None:
        for line in stream:
            stripped = line.strip()
            if stripped:
                self._stderr.put(stripped)


def local_command(codex_bin: str) -> list[str]:
    return [codex_bin, "app-server", "--stdio"]


def ssh_command(*, ssh_host: str, ssh_control_path: Path, codex_bin: str) -> list[str]:
    if ssh_host.startswith("-"):
        raise ValueError("ssh_host must not start with '-'")
    remote_command = shlex.join(["exec", codex_bin, "app-server", "--stdio"])
    return [
        "ssh",
        "-T",
        "-S",
        str(ssh_control_path),
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
        "-o",
        "ProxyCommand=false",
        "-o",
        "BatchMode=yes",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ConnectTimeout=10",
        ssh_host,
        remote_command,
    ]


def summarize_thread(raw_thread: dict[str, Any], *, host_id: str) -> ThreadSummary | None:
    thread_id = raw_thread.get("id")
    updated_at = raw_thread.get("updatedAt")
    if not isinstance(thread_id, str) or not isinstance(updated_at, int):
        return None
    created_at = raw_thread.get("createdAt")
    recency_at = raw_thread.get("recencyAt")
    return ThreadSummary(
        hostId=host_id,
        kind="codex",
        threadId=thread_id,
        updatedAt=updated_at,
        createdAt=created_at if isinstance(created_at, int) else None,
        recencyAt=recency_at if isinstance(recency_at, int) else None,
        name=raw_thread.get("name") if isinstance(raw_thread.get("name"), str) else None,
        cwd=raw_thread.get("cwd") if isinstance(raw_thread.get("cwd"), str) else None,
        status=raw_thread.get("status"),
        source=raw_thread.get("source"),
    )


def collect_stale_threads(
    client: ThreadListClient,
    *,
    host_id: str = "local",
    now: int,
    cutoff_age_seconds: int,
    page_size: int,
    max_pages: int,
    updated_since: int | None = None,
    updated_before: int | None = None,
    start_cursor: str | None = None,
) -> CollectionResult:
    mode = "updated_window" if updated_since is not None else "stale"
    cutoff = None if mode == "updated_window" else now - cutoff_age_seconds
    cursor: str | None = start_cursor
    pages_fetched = 0
    duplicate_count = 0
    malformed_count = 0
    seen_cursors: set[str] = {start_cursor} if start_cursor else set()
    seen_threads: set[str] = set()
    stale: list[ThreadSummary] = []
    window_threads: list[ThreadSummary] = []

    def finish(
        *,
        exhaustive: bool,
        incomplete_reason: str | None,
        next_cursor: str | None,
    ) -> CollectionResult:
        return CollectionResult(
            hostId=host_id,
            mode=mode,
            generatedAt=now,
            startCursor=start_cursor,
            cutoffTimestamp=cutoff,
            updatedSince=updated_since,
            updatedBefore=updated_before,
            pageLimit=max_pages,
            pageSize=page_size,
            pagesFetched=pages_fetched,
            examinedCount=len(seen_threads),
            duplicateCount=duplicate_count,
            malformedCount=malformed_count,
            staleCount=len(stale),
            windowCount=len(window_threads),
            exhaustive=exhaustive,
            incompleteReason=incomplete_reason,
            nextCursor=next_cursor,
            staleThreads=stale,
            windowThreads=window_threads,
        )

    while pages_fetched < max_pages:
        params: dict[str, Any] = {
            "limit": page_size,
            "archived": False,
            "sortKey": "updated_at",
            "sortDirection": "desc" if mode == "updated_window" else "asc",
            "sourceKinds": SOURCE_KINDS,
            "modelProviders": [],
        }
        if cursor is not None:
            params["cursor"] = cursor
        page = client.thread_list(params)
        pages_fetched += 1
        data = page.get("data")
        if not isinstance(data, list):
            raise ProtocolError("thread/list result omitted list data")

        page_updated_values: list[int] = []
        for raw_thread in data:
            if not isinstance(raw_thread, dict):
                malformed_count += 1
                continue
            summary = summarize_thread(raw_thread, host_id=host_id)
            if summary is None:
                malformed_count += 1
                continue
            page_updated_values.append(summary.updatedAt)
            if summary.threadId in seen_threads:
                duplicate_count += 1
                continue
            seen_threads.add(summary.threadId)
            if cutoff is not None and summary.updatedAt <= cutoff:
                stale.append(summary)
            if (
                updated_since is not None
                and summary.updatedAt >= updated_since
                and (updated_before is None or summary.updatedAt < updated_before)
            ):
                window_threads.append(summary)

        if "nextCursor" not in page:
            return finish(
                exhaustive=False,
                incomplete_reason="thread/list result omitted nextCursor",
                next_cursor=None,
            )
        if malformed_count:
            return finish(
                exhaustive=False,
                incomplete_reason="thread/list returned malformed thread entries",
                next_cursor=page.get("nextCursor")
                if isinstance(page.get("nextCursor"), str)
                else None,
            )
        next_cursor = page.get("nextCursor")
        if next_cursor is None:
            return finish(exhaustive=True, incomplete_reason=None, next_cursor=None)
        if not isinstance(next_cursor, str) or not next_cursor:
            return finish(
                exhaustive=False,
                incomplete_reason="thread/list returned a non-string continuation cursor",
                next_cursor=None,
            )
        if next_cursor in seen_cursors:
            return finish(
                exhaustive=False,
                incomplete_reason="thread/list returned a repeated continuation cursor",
                next_cursor=next_cursor,
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor

        if mode == "updated_window" and page_updated_values:
            oldest = min(page_updated_values)
            if updated_since is not None and oldest < updated_since:
                return finish(exhaustive=True, incomplete_reason=None, next_cursor=None)
        if mode == "stale" and cutoff is not None and page_updated_values:
            newest = max(page_updated_values)
            if newest > cutoff:
                return finish(exhaustive=True, incomplete_reason=None, next_cursor=None)

    return finish(
        exhaustive=False,
        incomplete_reason=f"stopped after {max_pages} pages",
        next_cursor=cursor,
    )


def result_to_json(result: CollectionResult) -> dict[str, Any]:
    payload = asdict(result)
    source = (
        "codex app-server thread/list"
        if result.hostId == "local"
        else "ssh existing-control-socket codex app-server thread/list"
    )
    payload["coverage"] = {
        "queriedHost": {
            "hostId": result.hostId,
            "source": source,
            "exhaustive": result.exhaustive,
            "incompleteReason": result.incompleteReason,
        }
    }
    if result.hostId == "local":
        payload["coverage"]["connectedRemote"] = {
            "source": None,
            "exhaustive": False,
            "incompleteReason": (
                "this invocation only reads the local app-server thread catalog; "
                "run one explicit existing-SSH-socket invocation per connected "
                "remote host or report connected-remote coverage as partial"
            ),
        }
    return payload


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List non-archived Codex threads using the official app-server "
            "thread/list cursor protocol."
        )
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument(
        "--ssh-host",
        default=None,
        help="Run codex on this host through an existing SSH control socket.",
    )
    parser.add_argument(
        "--ssh-control-path",
        default=None,
        help="Existing SSH control socket path. Required with --ssh-host.",
    )
    parser.add_argument(
        "--host-id",
        default="local",
        help="Host identity to stamp into emitted thread summaries.",
    )
    parser.add_argument("--limit", type=positive_int, default=DEFAULT_LIMIT)
    parser.add_argument("--max-pages", type=positive_int, default=DEFAULT_MAX_PAGES)
    parser.add_argument(
        "--cursor",
        default=None,
        help="Continue from a prior thread/list nextCursor for this same host and sort mode.",
    )
    parser.add_argument(
        "--cutoff-age-seconds", type=positive_int, default=DEFAULT_AGE_SECONDS
    )
    parser.add_argument(
        "--updated-since",
        type=int,
        default=None,
        help="Collect threads updated at or after this Unix timestamp.",
    )
    parser.add_argument(
        "--updated-before",
        type=int,
        default=None,
        help="With --updated-since, exclude threads updated at or after this timestamp.",
    )
    parser.add_argument(
        "--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    ssh_args = [args.ssh_host, args.ssh_control_path]
    if any(value is not None for value in ssh_args) and not all(
        value is not None for value in ssh_args
    ):
        print(
            "--ssh-host and --ssh-control-path must be provided together",
            file=sys.stderr,
        )
        return 2
    if args.host_id != "local" and args.ssh_host is None:
        print("--host-id other than local requires --ssh-host", file=sys.stderr)
        return 2
    if args.limit > DEFAULT_LIMIT:
        print(
            f"limit {args.limit} exceeds supported per-request maximum {DEFAULT_LIMIT}",
            file=sys.stderr,
        )
        return 2
    if args.limit * args.max_pages > DEFAULT_LIMIT * DEFAULT_MAX_PAGES:
        print(
            "limit multiplied by max-pages exceeds the 500-thread sweep cap",
            file=sys.stderr,
        )
        return 2
    if args.ssh_host is None:
        host_id = "local"
        command = local_command(args.codex_bin)
    else:
        if args.ssh_host.startswith("-"):
            print("--ssh-host must not start with '-'", file=sys.stderr)
            return 2
        control_path = Path(args.ssh_control_path)
        if not control_path.is_socket():
            print(
                f"SSH control path is not an existing socket: {control_path}",
                file=sys.stderr,
            )
            return 2
        if args.host_id == "local":
            print("--host-id must name the remote host with --ssh-host", file=sys.stderr)
            return 2
        host_id = args.host_id
        command = ssh_command(
            ssh_host=args.ssh_host,
            ssh_control_path=control_path,
            codex_bin=args.codex_bin,
        )
    client = AppServerJsonlClient(
        command=command, host_id=host_id, timeout_seconds=args.timeout_seconds
    )
    try:
        result = collect_stale_threads(
            client,
            host_id=host_id,
            now=int(time.time()),
            cutoff_age_seconds=args.cutoff_age_seconds,
            page_size=args.limit,
            max_pages=args.max_pages,
            updated_since=args.updated_since,
            updated_before=args.updated_before,
            start_cursor=args.cursor,
        )
        payload = result_to_json(result)
        stderr_lines = client.stderr_lines
        if stderr_lines:
            payload["appServerStderr"] = stderr_lines
        print(json.dumps(payload, sort_keys=True))
        return 0 if result.exhaustive else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Secure, conversation-scoped audit trace persistence for mem lookups."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import shlex
import stat
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


TRACE_VERSION = 1
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_RETRY_SECONDS = 0.05
_DATE_PART = re.compile(r"^[0-9]{2}$")
_YEAR_PART = re.compile(r"^[0-9]{4}$")
_MILLISECOND_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}(?:Z|[+-]\d{2}:\d{2})$"
)


class AuditTraceError(RuntimeError):
    """An explicit failure to safely prepare or update an audit trace."""


def validate_session_id(session_id: str) -> str:
    """Validate an explicitly supplied conversation UUID and return canonical text."""

    if not isinstance(session_id, str) or not session_id.strip():
        raise AuditTraceError("audit session ID is missing; expected a conversation UUID")
    try:
        parsed = uuid.UUID(session_id.strip())
    except (ValueError, AttributeError) as exc:
        raise AuditTraceError("audit session ID must be a valid UUID") from exc
    return str(parsed)


def timestamp_ms(value: datetime) -> str:
    """Return a timezone-aware ISO 8601 timestamp at millisecond precision."""

    if not isinstance(value, datetime):
        raise AuditTraceError("audit timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuditTraceError("audit timestamp must be timezone-aware")
    return value.isoformat(timespec="milliseconds")


def elapsed_ms(start_monotonic: float, finished_monotonic: float) -> int:
    """Convert a monotonic-clock interval to nonnegative whole milliseconds."""

    if isinstance(start_monotonic, bool) or isinstance(finished_monotonic, bool):
        raise AuditTraceError("audit monotonic timestamps must be numbers")
    try:
        elapsed = float(finished_monotonic) - float(start_monotonic)
    except (TypeError, ValueError) as exc:
        raise AuditTraceError("audit monotonic timestamps must be numbers") from exc
    if not math.isfinite(elapsed):
        raise AuditTraceError("audit monotonic timestamps must be finite")
    if elapsed < 0:
        raise AuditTraceError("audit monotonic finish precedes start")
    return int(round(elapsed * 1000))


def timing_snapshot(
    *,
    started_at: datetime,
    finished_at: datetime,
    start_monotonic: float,
    finished_monotonic: float,
) -> dict[str, str | int]:
    """Build the common timestamp/duration fields for a measured operation."""

    return {
        "started_at": timestamp_ms(started_at),
        "finished_at": timestamp_ms(finished_at),
        "duration_ms": elapsed_ms(start_monotonic, finished_monotonic),
    }


def shell_quote_argv(argv: Sequence[str]) -> str:
    """Render exact argv tokens as a safely quoted, replayable shell command."""

    if isinstance(argv, (str, bytes)) or not isinstance(argv, Sequence):
        raise AuditTraceError("audit command argv must be a sequence of strings")
    tokens = list(argv)
    if not tokens:
        raise AuditTraceError("audit command argv must not be empty")
    if any(not isinstance(token, str) for token in tokens):
        raise AuditTraceError("audit command argv must contain only strings")
    if any("\x00" in token for token in tokens):
        raise AuditTraceError("audit command argv must not contain NUL bytes")
    return shlex.join(tokens)


def _string_list(value: Sequence[str], field: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise AuditTraceError(f"{field} must be a sequence of strings")
    result = list(value)
    if any(not isinstance(item, str) for item in result):
        raise AuditTraceError(f"{field} must contain only strings")
    return result


def canonical_lookup_payload(
    *,
    session_id: str,
    query: str,
    commands: Sequence[Sequence[str]],
    selected_bases: Sequence[str] = (),
    hierarchy_paths: Sequence[str] = (),
    source_scopes: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the stable logical-lookup fields used by the SHA-256 fingerprint."""

    canonical_session_id = validate_session_id(session_id)
    if not isinstance(query, str):
        raise AuditTraceError("audit query must be a string")
    if isinstance(commands, (str, bytes)) or not isinstance(commands, Sequence):
        raise AuditTraceError("audit commands must be an ordered sequence of argv lists")
    normalized_commands = [
        _string_list(argv, f"audit commands[{index}]")
        for index, argv in enumerate(commands)
    ]
    return {
        "session_id": canonical_session_id,
        "query": query,
        "commands": normalized_commands,
        "selected_bases": _string_list(selected_bases, "audit selected bases"),
        "hierarchy_paths": _string_list(hierarchy_paths, "audit hierarchy paths"),
        "source_scopes": _string_list(source_scopes, "audit source scopes"),
    }


def canonical_lookup_id(
    *,
    session_id: str,
    query: str,
    commands: Sequence[Sequence[str]],
    selected_bases: Sequence[str] = (),
    hierarchy_paths: Sequence[str] = (),
    source_scopes: Sequence[str] = (),
) -> str:
    """Fingerprint one logical lookup using canonical UTF-8 JSON."""

    payload = canonical_lookup_payload(
        session_id=session_id,
        query=query,
        commands=commands,
        selected_bases=selected_bases,
        hierarchy_paths=hierarchy_paths,
        source_scopes=source_scopes,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _validate_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not _MILLISECOND_TIMESTAMP.fullmatch(value):
        raise AuditTraceError(
            f"{field} must be a timezone-aware ISO 8601 timestamp with milliseconds"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditTraceError(f"{field} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AuditTraceError(f"{field} must be timezone-aware")
    return parsed


def _validate_duration(value: Any, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AuditTraceError(f"{field} must be a nonnegative integer")


def _validate_timing(value: Any, field: str) -> None:
    if not isinstance(value, Mapping):
        raise AuditTraceError(f"{field} must be a mapping")
    _validate_timestamp(value.get("started_at"), f"{field}.started_at")
    _validate_timestamp(value.get("finished_at"), f"{field}.finished_at")
    _validate_duration(value.get("duration_ms"), f"{field}.duration_ms")


def _normalize_record(record: Mapping[str, Any], session_id: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise AuditTraceError("audit trace record must be a mapping")
    normalized = copy.deepcopy(dict(record))

    supplied_version = normalized.get("version")
    if supplied_version is not None and supplied_version != TRACE_VERSION:
        raise AuditTraceError(f"audit record.version must be {TRACE_VERSION}")

    _validate_timing(normalized, "audit record")

    query = normalized.get("query")
    if not isinstance(query, str):
        raise AuditTraceError("audit record.query must be a string")

    commands = normalized.get("commands")
    if not isinstance(commands, list) or not commands:
        raise AuditTraceError("audit record.commands must be a nonempty list")
    command_argvs: list[list[str]] = []
    for index, command in enumerate(commands):
        field = f"audit record.commands[{index}]"
        if not isinstance(command, Mapping):
            raise AuditTraceError(f"{field} must be a mapping")
        command_copy = copy.deepcopy(dict(command))
        argv = _string_list(command_copy.get("argv"), f"{field}.argv")
        if not argv:
            raise AuditTraceError(f"{field}.argv must not be empty")
        command_copy["command"] = shell_quote_argv(argv)
        _validate_timing(command_copy, field)
        commands[index] = command_copy
        command_argvs.append(argv)

    operations = normalized.get("operations")
    if not isinstance(operations, list):
        raise AuditTraceError("audit record.operations must be a list")
    for index, operation in enumerate(operations):
        field = f"audit record.operations[{index}]"
        if not isinstance(operation, Mapping) or not isinstance(operation.get("name"), str):
            raise AuditTraceError(f"{field} must have a string name")
        _validate_timing(operation, field)

    attempts = normalized.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise AuditTraceError("audit record.attempts must be a nonempty list")
    for attempt_index, attempt in enumerate(attempts):
        field = f"audit record.attempts[{attempt_index}]"
        if not isinstance(attempt, Mapping):
            raise AuditTraceError(f"{field} must be a mapping")
        _validate_timing(attempt, field)
        if not isinstance(attempt.get("status"), str):
            raise AuditTraceError(f"{field}.status must be a string")
        command_timings = attempt.get("command_timings")
        if not isinstance(command_timings, list):
            raise AuditTraceError(f"{field}.command_timings must be a list")
        for timing_index, command_timing in enumerate(command_timings):
            timing_field = f"{field}.command_timings[{timing_index}]"
            if not isinstance(command_timing, Mapping):
                raise AuditTraceError(f"{timing_field} must be a mapping")
            command_index = command_timing.get("command_index")
            if (
                not isinstance(command_index, int)
                or isinstance(command_index, bool)
                or command_index < 0
                or command_index >= len(commands)
            ):
                raise AuditTraceError(f"{timing_field}.command_index is out of range")
            _validate_timing(command_timing, timing_field)
        command_indexes = [timing["command_index"] for timing in command_timings]
        if command_indexes != list(range(len(commands))):
            raise AuditTraceError(
                f"{field}.command_timings must cover each command once in order"
            )
        operation_timings = attempt.get("operation_timings")
        if not isinstance(operation_timings, list):
            raise AuditTraceError(f"{field}.operation_timings must be a list")
        for timing_index, operation_timing in enumerate(operation_timings):
            timing_field = f"{field}.operation_timings[{timing_index}]"
            if (
                not isinstance(operation_timing, Mapping)
                or not isinstance(operation_timing.get("name"), str)
            ):
                raise AuditTraceError(f"{timing_field} must have a string name")
            _validate_timing(operation_timing, timing_field)

    if normalized["started_at"] != attempts[0]["started_at"]:
        raise AuditTraceError("audit record.started_at must equal the first attempt start")
    if normalized["finished_at"] != attempts[-1]["finished_at"]:
        raise AuditTraceError("audit record.finished_at must equal the latest attempt finish")
    attempt_duration = sum(attempt["duration_ms"] for attempt in attempts)
    if normalized["duration_ms"] != attempt_duration:
        raise AuditTraceError("audit record.duration_ms must equal the sum of attempt durations")
    if operations != attempts[-1]["operation_timings"]:
        raise AuditTraceError("audit record.operations must reflect the latest attempt")

    status = normalized.get("status")
    if not isinstance(status, str):
        raise AuditTraceError("audit record.status must be a string")
    if status != attempts[-1]["status"]:
        raise AuditTraceError("audit record.status must equal the latest attempt status")
    matched_paths = normalized.get("matched_paths")
    _string_list(matched_paths, "audit record.matched_paths")

    fallback = normalized.get("fallback")
    if not isinstance(fallback, Mapping):
        raise AuditTraceError("audit record.fallback must be a mapping")
    if not isinstance(fallback.get("used"), bool):
        raise AuditTraceError("audit record.fallback.used must be a boolean")
    _string_list(fallback.get("paths"), "audit record.fallback.paths")
    if not isinstance(fallback.get("reason"), str):
        raise AuditTraceError("audit record.fallback.reason must be a string")

    hierarchy = normalized.get("hierarchy")
    if not isinstance(hierarchy, list):
        raise AuditTraceError("audit record.hierarchy must be a list")
    hierarchy_paths: list[str] = []
    for index, entry in enumerate(hierarchy):
        field = f"audit record.hierarchy[{index}]"
        if not isinstance(entry, Mapping):
            raise AuditTraceError(f"{field} must be a mapping")
        for key in ("path", "schema", "decision", "reason"):
            if not isinstance(entry.get(key), str):
                raise AuditTraceError(f"{field}.{key} must be a string")
        hierarchy_paths.append(entry["path"])

    selection = normalized.get("selection", {})
    if not isinstance(selection, Mapping):
        raise AuditTraceError("audit record.selection must be a mapping")
    if not isinstance(selection.get("tier"), str):
        raise AuditTraceError("audit record.selection.tier must be a string")
    selected_bases = _string_list(selection.get("bases", []), "audit record.selection.bases")
    _string_list(selection.get("reasons"), "audit record.selection.reasons")
    if "source_scopes" not in normalized:
        raise AuditTraceError(
            "audit record.source_scopes is required for canonical fingerprinting"
        )
    source_scopes = _string_list(
        normalized["source_scopes"], "audit record.source_scopes"
    )

    expected_id = canonical_lookup_id(
        session_id=session_id,
        query=query,
        commands=command_argvs,
        selected_bases=selected_bases,
        hierarchy_paths=hierarchy_paths,
        source_scopes=source_scopes,
    )
    supplied_session = normalized.get("session_id")
    if supplied_session is not None and validate_session_id(supplied_session) != session_id:
        raise AuditTraceError("audit record session ID does not match the writer session")
    supplied_lookup = normalized.get("lookup_id")
    if supplied_lookup is not None and supplied_lookup != expected_id:
        raise AuditTraceError("audit record lookup ID does not match its canonical fingerprint")

    occurrence_count = normalized.get("occurrence_count", 1)
    _validate_duration(occurrence_count, "audit record.occurrence_count")
    if occurrence_count != len(attempts):
        raise AuditTraceError("audit record occurrence_count must equal the number of attempts")
    normalized["version"] = TRACE_VERSION
    normalized["session_id"] = session_id
    normalized["lookup_id"] = expected_id
    normalized["occurrence_count"] = occurrence_count
    return normalized


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class AuditTraceWriter:
    """Prepare, lock, and atomically merge one conversation's JSONL trace."""

    def __init__(self, trace_root: str | os.PathLike[str], session_id: str) -> None:
        self.session_id = validate_session_id(session_id)
        if not isinstance(trace_root, (str, os.PathLike)):
            raise AuditTraceError("audit trace root must be a path")
        root = Path(trace_root).expanduser()
        if not root.is_absolute():
            raise AuditTraceError("audit trace root must be an absolute path")
        self.trace_root = root.resolve(strict=False)
        if self.trace_root == Path(self.trace_root.anchor):
            raise AuditTraceError("audit trace root must not be a filesystem root")
        self._lock_fd: int | None = None
        self._trace_path: Path | None = None

    @property
    def trace_path(self) -> Path:
        if self._trace_path is None:
            raise AuditTraceError("audit trace has not been prepared")
        return self._trace_path

    def _ensure_directory(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        if not _is_relative_to(resolved, self.trace_root) and resolved != self.trace_root:
            raise AuditTraceError(f"audit directory resolves outside trace root: {path}")
        try:
            path.mkdir(mode=DIRECTORY_MODE, parents=False, exist_ok=True)
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AuditTraceError(f"audit directory is not a real directory: {path}")
            path.chmod(DIRECTORY_MODE)
        except AuditTraceError:
            raise
        except OSError as exc:
            raise AuditTraceError(f"could not create or secure audit directory {path}: {exc}") from exc

    def _ensure_root(self) -> None:
        try:
            self.trace_root.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
            metadata = self.trace_root.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AuditTraceError(
                    f"audit trace root is not a real directory: {self.trace_root}"
                )
            self.trace_root.chmod(DIRECTORY_MODE)
        except AuditTraceError:
            raise
        except OSError as exc:
            raise AuditTraceError(
                f"could not create or secure audit trace root {self.trace_root}: {exc}"
            ) from exc

    def _acquire_lock(self) -> None:
        lock_dir = self.trace_root / ".locks"
        self._ensure_directory(lock_dir)
        lock_path = lock_dir / f"{self.session_id}.lock"
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd: int | None = None
        try:
            fd = os.open(lock_path, flags, FILE_MODE)
            os.fchmod(fd, FILE_MODE)
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise AuditTraceError(f"audit lock is not a regular file: {lock_path}")
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise AuditTraceError(
                            f"timed out acquiring audit lock {lock_path}"
                        ) from exc
                    time.sleep(min(LOCK_RETRY_SECONDS, remaining))
        except (AuditTraceError, OSError) as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if isinstance(exc, AuditTraceError):
                raise
            raise AuditTraceError(f"could not acquire audit lock {lock_path}: {exc}") from exc
        if fd is None:  # pragma: no cover - guarded by successful os.open above
            raise AuditTraceError(f"could not acquire audit lock {lock_path}")
        self._lock_fd = fd

    def _assert_safe_trace_file(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        if not _is_relative_to(resolved, self.trace_root):
            raise AuditTraceError(f"audit trace file resolves outside trace root: {path}")
        current = resolved.parent
        while current != self.trace_root:
            if current == current.parent:
                raise AuditTraceError(f"audit trace file is not inside trace root: {path}")
            try:
                metadata = current.lstat()
            except OSError as exc:
                raise AuditTraceError(f"could not inspect audit trace directory {current}: {exc}") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise AuditTraceError(f"unsafe audit trace directory: {current}")
            try:
                current.chmod(DIRECTORY_MODE)
            except OSError as exc:
                raise AuditTraceError(
                    f"could not secure audit trace directory {current}: {exc}"
                ) from exc
            current = current.parent
        if path.exists() or path.is_symlink():
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise AuditTraceError(f"could not inspect audit trace file {path}: {exc}") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise AuditTraceError(f"audit trace is not a regular file: {path}")

    def _existing_trace_paths(self) -> list[Path]:
        matches: list[Path] = []
        try:
            for year in self.trace_root.iterdir():
                if not _YEAR_PART.fullmatch(year.name) or not year.is_dir():
                    continue
                for month in year.iterdir():
                    if not _DATE_PART.fullmatch(month.name) or not month.is_dir():
                        continue
                    for day in month.iterdir():
                        if not _DATE_PART.fullmatch(day.name) or not day.is_dir():
                            continue
                        try:
                            datetime(int(year.name), int(month.name), int(day.name))
                        except ValueError:
                            continue
                        candidate = day / f"{self.session_id}.jsonl"
                        if candidate.exists() or candidate.is_symlink():
                            self._assert_safe_trace_file(candidate)
                            matches.append(candidate)
        except OSError as exc:
            raise AuditTraceError(f"could not scan audit trace root: {exc}") from exc
        return sorted(matches)

    def _create_trace_file(self, path: Path) -> None:
        self._assert_safe_trace_file(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd: int | None = None
        try:
            fd = os.open(path, flags, FILE_MODE)
            os.fchmod(fd, FILE_MODE)
            os.fsync(fd)
            os.close(fd)
            fd = None
        except OSError as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise AuditTraceError(f"could not create audit trace file {path}: {exc}") from exc

    def _select_trace_path(self, now: datetime) -> Path:
        matches = self._existing_trace_paths()
        if len(matches) > 1:
            joined = ", ".join(str(path) for path in matches)
            raise AuditTraceError(f"conversation has multiple audit trace files: {joined}")
        if matches:
            path = matches[0]
            try:
                path.chmod(FILE_MODE)
            except OSError as exc:
                raise AuditTraceError(f"could not secure audit trace file {path}: {exc}") from exc
            return path

        if now.tzinfo is None or now.utcoffset() is None:
            raise AuditTraceError("audit trace date requires a timezone-aware datetime")
        date_parts = (f"{now.year:04d}", f"{now.month:02d}", f"{now.day:02d}")
        directory = self.trace_root
        for part in date_parts:
            directory /= part
            self._ensure_directory(directory)
        path = directory / f"{self.session_id}.jsonl"
        self._create_trace_file(path)
        return path

    def _read_records(self, path: Path) -> list[dict[str, Any]]:
        self._assert_safe_trace_file(path)
        records: list[dict[str, Any]] = []
        seen_lookup_ids: set[str] = set()
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise AuditTraceError(
                            f"invalid JSON in audit trace {path} at line {line_number}: {exc}"
                        ) from exc
                    if not isinstance(record, dict):
                        raise AuditTraceError(
                            f"audit trace {path} line {line_number} is not a JSON object"
                        )
                    if record.get("version") != TRACE_VERSION:
                        raise AuditTraceError(
                            f"audit trace {path} line {line_number} has unsupported version"
                        )
                    normalized = _normalize_record(record, self.session_id)
                    if normalized != record:
                        raise AuditTraceError(
                            f"audit trace {path} line {line_number} is not canonical"
                        )
                    lookup_id = normalized["lookup_id"]
                    if lookup_id in seen_lookup_ids:
                        raise AuditTraceError(
                            f"audit trace {path} contains duplicate lookup ID {lookup_id}"
                        )
                    seen_lookup_ids.add(lookup_id)
                    records.append(normalized)
        except AuditTraceError:
            raise
        except (OSError, UnicodeError) as exc:
            raise AuditTraceError(f"could not read audit trace {path}: {exc}") from exc
        return records

    def _probe_update(self, path: Path) -> None:
        probe = path.parent / f".{self.session_id}.{secrets.token_hex(8)}.probe"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd: int | None = None
        try:
            fd = os.open(probe, flags, FILE_MODE)
            os.fchmod(fd, FILE_MODE)
            os.fsync(fd)
            os.close(fd)
            fd = None
            probe.unlink()
        except OSError as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            raise AuditTraceError(f"audit trace destination is not writable {path}: {exc}") from exc

    def prepare(self, *, now: datetime | None = None) -> Path:
        """Acquire the conversation lock and preflight its stable trace file."""

        if self._lock_fd is not None:
            raise AuditTraceError("audit trace writer is already locked")
        current = now if now is not None else datetime.now().astimezone()
        self._ensure_root()
        self._acquire_lock()
        try:
            self._trace_path = self._select_trace_path(current)
            self._read_records(self._trace_path)
            self._probe_update(self._trace_path)
            return self._trace_path
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Release a prepared writer's conversation lock."""

        if self._lock_fd is None:
            return
        fd = self._lock_fd
        self._lock_fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    @contextmanager
    def locked(self, *, now: datetime | None = None) -> Iterator[AuditTraceWriter]:
        """Hold the conversation lock across lookup execution and trace writing."""

        self.prepare(now=now)
        try:
            yield self
        finally:
            self.close()

    def _merge_record(
        self, records: list[dict[str, Any]], incoming: dict[str, Any]
    ) -> list[dict[str, Any]]:
        for index, existing in enumerate(records):
            if existing.get("lookup_id") != incoming["lookup_id"]:
                continue
            existing_attempts = existing.get("attempts")
            if not isinstance(existing_attempts, list):
                raise AuditTraceError("existing audit record attempts are invalid")
            existing_count = existing.get("occurrence_count")
            existing_duration = existing.get("duration_ms")
            _validate_duration(existing_count, "existing audit record.occurrence_count")
            _validate_duration(existing_duration, "existing audit record.duration_ms")

            merged = incoming
            merged["started_at"] = existing.get("started_at")
            merged["duration_ms"] = existing_duration + incoming["duration_ms"]
            merged["occurrence_count"] = existing_count + incoming["occurrence_count"]
            merged["attempts"] = copy.deepcopy(existing_attempts) + incoming["attempts"]
            records[index] = merged
            return records
        records.append(incoming)
        return records

    def _atomic_replace(self, path: Path, records: list[dict[str, Any]]) -> None:
        self._assert_safe_trace_file(path)
        temp_path = path.parent / f".{self.session_id}.{secrets.token_hex(8)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd: int | None = None
        try:
            fd = os.open(temp_path, flags, FILE_MODE)
            os.fchmod(fd, FILE_MODE)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                for record in records:
                    json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            path.chmod(FILE_MODE)
            directory_flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                directory_flags |= os.O_DIRECTORY
            directory_fd = os.open(path.parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (OSError, TypeError, ValueError) as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AuditTraceError(f"could not atomically update audit trace {path}: {exc}") from exc

    def write(self, record: Mapping[str, Any]) -> Path:
        """Merge one completed lookup record and return its stable trace path."""

        if self._lock_fd is None:
            with self.locked():
                return self.write(record)
        incoming = _normalize_record(record, self.session_id)
        path = self.trace_path
        records = self._read_records(path)
        self._atomic_replace(path, self._merge_record(records, incoming))
        return path


def write_audit_trace(
    trace_root: str | os.PathLike[str],
    session_id: str,
    record: Mapping[str, Any],
) -> Path:
    """One-shot convenience wrapper for callers that do not need preflight locking."""

    return AuditTraceWriter(trace_root, session_id).write(record)

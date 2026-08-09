#!/usr/bin/env python3
"""Secure, uncapped, portable path-only indexes for managed memory bases."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from routing_signals import ARTIFACT_ALIASES, GENERIC_WORDS, normalize_label


INDEX_FILENAME = ".mem.index.json"
INDEX_VERSION = 1
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".svn",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
        "venv",
    }
)
INDEX_FIELDS = frozenset(
    {
        "version",
        "generated_at",
        "path_style",
        "source_fingerprint",
        "document_count",
        "metadata",
        "hierarchy",
    }
)
FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class BaseIndexError(Exception):
    """An index failure whose kind distinguishes malformed and unsafe states."""

    def __init__(self, message: str, *, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


def _paths(base: dict[str, Any]) -> tuple[Path, Path, str]:
    raw_root = base.get("managed_root", base.get("root"))
    if not isinstance(raw_root, (str, os.PathLike)):
        raise BaseIndexError("managed root is missing or invalid", kind="unsafe")
    root = Path(raw_root)
    if not root.is_absolute() or ".." in root.parts:
        raise BaseIndexError(f"unsafe managed root: {root}", kind="unsafe")
    expected = root / INDEX_FILENAME
    configured = base.get("index_path", expected)
    if not isinstance(configured, (str, os.PathLike)) or Path(configured) != expected:
        raise BaseIndexError(
            f"index path must be the derived in-root path: {expected}", kind="unsafe"
        )
    path_style = base.get("path_style", "directory")
    if path_style not in {"directory", "dotted"}:
        raise BaseIndexError(f"unsupported index path style: {path_style!r}", kind="unsafe")
    return root, expected, path_style


@contextmanager
def _locked_root(base: dict[str, Any], *, exclusive: bool) -> Iterator[tuple[int, Path, str]]:
    root, index_path, path_style = _paths(base)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise BaseIndexError("safe directory locks require O_DIRECTORY and O_NOFOLLOW")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise BaseIndexError(f"could not safely open managed root {root}: {exc}") from exc
    try:
        operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise BaseIndexError(f"could not lock managed root {root}: {exc}") from exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BaseIndexError(
                        f"lock timed out after {LOCK_TIMEOUT_SECONDS:g} seconds"
                    ) from exc
                time.sleep(min(LOCK_POLL_SECONDS, remaining))
        yield descriptor, index_path, path_style
    finally:
        os.close(descriptor)


def _index_descriptor(root_descriptor: int) -> int:
    try:
        metadata = os.stat(INDEX_FILENAME, dir_fd=root_descriptor, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise BaseIndexError("memory-base index is missing", kind="missing") from exc
    except OSError as exc:
        raise BaseIndexError(f"could not inspect memory-base index: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise BaseIndexError("index target must be a regular non-symlink file", kind="unsafe")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(INDEX_FILENAME, flags, dir_fd=root_descriptor)
        opened_metadata = os.fstat(descriptor)
    except OSError as exc:
        raise BaseIndexError(f"could not safely open memory-base index: {exc}", kind="unsafe") from exc
    if not stat.S_ISREG(opened_metadata.st_mode):
        os.close(descriptor)
        raise BaseIndexError("index target must be a regular non-symlink file", kind="unsafe")
    return descriptor


def _nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_logical_path(value: Any, *, depth: int) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/"):
        return False
    parts = value.split("/")
    return len(parts) == depth and all(part not in {"", ".", ".."} for part in parts)


def _sort_key(value: str) -> tuple[str, str]:
    return normalize_label(value), value


def _validate_index(payload: Any, path_style: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BaseIndexError("index content must be a JSON object", kind="invalid")
    if "version" not in payload:
        raise BaseIndexError("index format version is missing", kind="invalid")
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != INDEX_VERSION:
        raise BaseIndexError(f"unsupported index format version: {version!r}", kind="unsupported")
    if set(payload) != INDEX_FIELDS:
        raise BaseIndexError("index has missing or unexpected fields", kind="invalid")
    if payload["path_style"] != path_style:
        raise BaseIndexError("index path style does not match its configured base", kind="invalid")
    generated_at = payload["generated_at"]
    if not isinstance(generated_at, str):
        raise BaseIndexError("index generation timestamp is invalid", kind="invalid")
    try:
        if datetime.fromisoformat(generated_at).utcoffset() is None:
            raise ValueError("timestamp has no UTC offset")
    except ValueError as exc:
        raise BaseIndexError("index generation timestamp is invalid", kind="invalid") from exc
    fingerprint = payload["source_fingerprint"]
    if not isinstance(fingerprint, str) or not FINGERPRINT_PATTERN.fullmatch(fingerprint):
        raise BaseIndexError("index source fingerprint is invalid", kind="invalid")
    if not _nonnegative_integer(payload["document_count"]):
        raise BaseIndexError("index document count is invalid", kind="invalid")

    metadata = payload["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != {"topics", "artifact_kinds"}:
        raise BaseIndexError("index metadata has missing or unexpected fields", kind="invalid")
    for field in ("topics", "artifact_kinds"):
        values = metadata[field]
        if not isinstance(values, list) or any(
            not isinstance(value, str) or not value or normalize_label(value) != value
            for value in values
        ):
            raise BaseIndexError(f"index metadata {field} is invalid", kind="invalid")
        if values != sorted(set(values)):
            raise BaseIndexError(f"index metadata {field} is not sorted and unique", kind="invalid")
    valid_kinds = {kind for aliases in ARTIFACT_ALIASES.values() for kind in aliases}
    if not set(metadata["artifact_kinds"]).issubset(valid_kinds):
        raise BaseIndexError("index metadata contains an unsupported artifact kind", kind="invalid")

    hierarchy = payload["hierarchy"]
    if not isinstance(hierarchy, list):
        raise BaseIndexError("index hierarchy is invalid", kind="invalid")
    previous_parent: tuple[str, str] | None = None
    total = 0
    for node in hierarchy:
        if not isinstance(node, dict) or set(node) != {"path", "document_count", "children"}:
            raise BaseIndexError("index hierarchy parent is invalid", kind="invalid")
        path = node["path"]
        if not _valid_logical_path(path, depth=1) or not _nonnegative_integer(node["document_count"]):
            raise BaseIndexError("index hierarchy parent path or count is invalid", kind="invalid")
        key = _sort_key(path)
        if previous_parent is not None and key <= previous_parent:
            raise BaseIndexError("index hierarchy parents are not sorted and unique", kind="invalid")
        previous_parent = key
        children = node["children"]
        if not isinstance(children, list):
            raise BaseIndexError("index hierarchy children are invalid", kind="invalid")
        previous_child: tuple[str, str] | None = None
        child_total = 0
        for child in children:
            if not isinstance(child, dict) or set(child) != {"path", "document_count"}:
                raise BaseIndexError("index hierarchy child is invalid", kind="invalid")
            child_path = child["path"]
            if (
                not _valid_logical_path(child_path, depth=2)
                or not child_path.startswith(f"{path}/")
                or not _nonnegative_integer(child["document_count"])
            ):
                raise BaseIndexError("index hierarchy child path or count is invalid", kind="invalid")
            child_key = _sort_key(child_path.rsplit("/", 1)[1])
            if previous_child is not None and child_key <= previous_child:
                raise BaseIndexError("index hierarchy children are not sorted and unique", kind="invalid")
            previous_child = child_key
            child_total += child["document_count"]
        if child_total > node["document_count"]:
            raise BaseIndexError("index hierarchy child counts exceed parent count", kind="invalid")
        total += node["document_count"]
    if total != payload["document_count"]:
        raise BaseIndexError("index hierarchy counts do not match document count", kind="invalid")
    return payload


def _read_locked(root_descriptor: int, path_style: str) -> dict[str, Any]:
    descriptor = _index_descriptor(root_descriptor)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            try:
                payload = json.load(stream)
            except (json.JSONDecodeError, UnicodeError) as exc:
                raise BaseIndexError(f"index contains malformed JSON: {exc}", kind="invalid") from exc
    except OSError as exc:
        raise BaseIndexError(f"could not read memory-base index: {exc}") from exc
    return _validate_index(payload, path_style)


def _scan_paths(root_descriptor: int) -> list[str]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    paths: list[str] = []

    def visit(directory_descriptor: int, relative: str) -> None:
        try:
            with os.scandir(directory_descriptor) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError as exc:
            raise BaseIndexError(f"could not scan managed directory {relative or '.'}: {exc}") from exc
        for name in names:
            if name == INDEX_FILENAME:
                continue
            try:
                metadata = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            except OSError as exc:
                raise BaseIndexError(f"could not inspect managed path {name}: {exc}") from exc
            if stat.S_ISLNK(metadata.st_mode):
                continue
            path = f"{relative}/{name}" if relative else name
            if stat.S_ISDIR(metadata.st_mode):
                if name.startswith(".") or name in SKIP_DIRECTORIES:
                    continue
                try:
                    child_descriptor = os.open(name, flags, dir_fd=directory_descriptor)
                except OSError as exc:
                    raise BaseIndexError(f"could not safely open managed directory {path}: {exc}") from exc
                try:
                    visit(child_descriptor, path)
                finally:
                    os.close(child_descriptor)
            elif stat.S_ISREG(metadata.st_mode) and name.endswith(".md"):
                paths.append(path)
    visit(root_descriptor, "")
    return sorted(paths)


def _fingerprint(paths: list[str], path_style: str) -> str:
    encoded = json.dumps(
        {"version": INDEX_VERSION, "path_style": path_style, "paths": paths},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _logical_parts(relative: str, path_style: str) -> list[str]:
    parts = relative.split("/")
    stem = parts.pop().removesuffix(".md")
    if path_style == "dotted":
        parts.extend(component for component in stem.split(".") if component)
    elif stem:
        parts.append(stem)
    return parts


def _generate_index(paths: list[str], path_style: str, fingerprint: str) -> dict[str, Any]:
    parent_counts: dict[str, int] = defaultdict(int)
    child_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    topics: set[str] = set()
    artifact_kinds: set[str] = set()
    for relative in paths:
        components = _logical_parts(relative, path_style)
        if not components:
            raise BaseIndexError(f"Markdown path has no logical components: {relative}")
        parent = components[0]
        parent_counts[parent] += 1
        if len(components) > 1:
            child_counts[parent][components[1]] += 1
        for component in components[:2]:
            label = normalize_label(component)
            if not label:
                continue
            aliases = ARTIFACT_ALIASES.get(label)
            if aliases is not None:
                artifact_kinds.update(aliases)
            elif not all(word in GENERIC_WORDS for word in label.split()):
                topics.add(label)

    hierarchy = []
    for parent in sorted(parent_counts, key=_sort_key):
        children = [
            {"path": f"{parent}/{child}", "document_count": child_counts[parent][child]}
            for child in sorted(child_counts[parent], key=_sort_key)
        ]
        hierarchy.append(
            {"path": parent, "document_count": parent_counts[parent], "children": children}
        )
    return {
        "version": INDEX_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "path_style": path_style,
        "source_fingerprint": fingerprint,
        "document_count": len(paths),
        "metadata": {"topics": sorted(topics), "artifact_kinds": sorted(artifact_kinds)},
        "hierarchy": hierarchy,
    }


def index_summary(
    *, status: str, index_path: Path, index: dict[str, Any] | None, changed: bool = False
) -> dict[str, Any]:
    """Return the stable per-base result shape consumed by CLI integration."""

    return {
        "status": status,
        "index": index,
        "index_path": str(index_path),
        "document_count": index["document_count"] if index is not None else None,
        "source_fingerprint": index["source_fingerprint"] if index is not None else None,
        "changed": changed,
    }


def _atomic_write(root_descriptor: int, index_path: Path, payload: dict[str, Any]) -> None:
    content = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary_name: str | None = None
    try:
        temporary_name = f"{INDEX_FILENAME}.{secrets.token_hex(16)}.tmp"
        temporary_descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=root_descriptor,
        )
        with os.fdopen(temporary_descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Anchor replacement to the already locked root, not a re-resolved path.
        os.replace(
            temporary_name,
            INDEX_FILENAME,
            src_dir_fd=root_descriptor,
            dst_dir_fd=root_descriptor,
        )
        temporary_name = None
    except OSError as exc:
        raise BaseIndexError(f"could not atomically update memory-base index: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=root_descriptor)
            except OSError:
                pass


def _build_index(base: dict[str, Any], *, repair_invalid: bool) -> dict[str, Any]:
    with _locked_root(base, exclusive=True) as (descriptor, index_path, path_style):
        existing: dict[str, Any] | None = None
        exists = False
        try:
            existing = _read_locked(descriptor, path_style)
            exists = True
        except BaseIndexError as exc:
            if exc.kind == "missing":
                pass
            elif exc.kind == "invalid" and repair_invalid:
                exists = True
            else:
                raise
        paths = _scan_paths(descriptor)
        fingerprint = _fingerprint(paths, path_style)
        if existing is not None and existing["source_fingerprint"] == fingerprint:
            return index_summary(status="unchanged", index_path=index_path, index=existing)
        payload = _generate_index(paths, path_style, fingerprint)
        _validate_index(payload, path_style)
        _atomic_write(descriptor, index_path, payload)
        return index_summary(
            status="updated" if exists else "created",
            index_path=index_path,
            index=payload,
            changed=True,
        )


def build_index(base: dict[str, Any]) -> dict[str, Any]:
    """Build or safely repair an index under an exclusive managed-root lock."""

    return _build_index(base, repair_invalid=True)


def read_index(base: dict[str, Any]) -> dict[str, Any]:
    """Read and validate an existing index under a shared managed-root lock."""

    with _locked_root(base, exclusive=False) as (descriptor, _, path_style):
        return _read_locked(descriptor, path_style)


def check_index(base: dict[str, Any]) -> dict[str, Any]:
    """Validate and check an index against every eligible Markdown path."""

    with _locked_root(base, exclusive=False) as (descriptor, index_path, path_style):
        try:
            index = _read_locked(descriptor, path_style)
        except BaseIndexError as exc:
            if exc.kind in {"missing", "invalid", "unsupported"}:
                status = "invalid" if exc.kind == "unsupported" else exc.kind
                return index_summary(status=status, index_path=index_path, index=None)
            raise
        fingerprint = _fingerprint(_scan_paths(descriptor), path_style)
        return index_summary(
            status="current" if fingerprint == index["source_fingerprint"] else "stale",
            index_path=index_path,
            index=index,
        )


def ensure_index(base: dict[str, Any]) -> tuple[str, dict[str, Any] | None, bool]:
    """Load a valid index or initialize a missing one without repairing malformed data."""

    try:
        return "loaded", read_index(base), False
    except BaseIndexError as exc:
        if exc.kind in {"invalid", "unsupported"}:
            return "invalid", None, False
        if exc.kind != "missing":
            return "build_failed", None, False
    try:
        result = _build_index(base, repair_invalid=False)
    except BaseIndexError as exc:
        if exc.kind in {"invalid", "unsupported"}:
            return "invalid", None, False
        return "build_failed", None, False
    generated = bool(result["changed"])
    return ("generated" if generated else "loaded"), result["index"], generated

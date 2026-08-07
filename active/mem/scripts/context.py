#!/usr/bin/env python3
"""Read-only managed context lookup with optional conversation audit tracing."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, NoReturn

import yaml

from audit_trace import (
    AuditTraceError,
    AuditTraceWriter,
    elapsed_ms,
    shell_quote_argv,
    timestamp_ms,
)
from load_config import load_config
from route import route


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BUNDLED_SCHEMAS = SKILL_DIR / "references" / "schemas"
SESSION_ENV = "CODEX_THREAD_ID"
MAX_SEARCH_BYTES = 2 * 1024 * 1024
BINARY_SNIFF_BYTES = 8192


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


@dataclass
class OperationSpan:
    name: str
    started_at: datetime
    started_monotonic: float


class OperationRecorder:
    def __init__(self) -> None:
        self.operations: list[dict[str, Any]] = []

    def start(self, name: str) -> OperationSpan:
        return OperationSpan(name, datetime.now().astimezone(), time.monotonic())

    def finish(self, span: OperationSpan) -> None:
        finished_at = datetime.now().astimezone()
        self.operations.append(
            {
                "name": span.name,
                "started_at": timestamp_ms(span.started_at),
                "finished_at": timestamp_ms(finished_at),
                "duration_ms": elapsed_ms(span.started_monotonic, time.monotonic()),
            }
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="context_command", required=True)
    lookup = subparsers.add_parser("lookup", help="Search managed knowledge, then source scopes.")
    lookup.add_argument("--query", required=True, help="Context to find.")
    lookup.add_argument("--target", help="Explicit base name or alias.")
    lookup.add_argument(
        "--source",
        action="append",
        default=[],
        help="Scoped source path to search on fallback; may be repeated.",
    )
    lookup.add_argument("--artifact-kind", help="Optional routing artifact kind.")
    lookup.add_argument("--config", type=Path, help="Use only this .mem.yaml.")
    lookup.add_argument("--cwd", type=Path, default=Path.cwd())
    lookup.add_argument("--home", type=Path, default=Path.home())
    lookup.add_argument("--allow-missing-roots", action="store_true")
    lookup.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def schema_path(schema: dict[str, str]) -> Path:
    if "path" in schema:
        return Path(schema["path"])
    return BUNDLED_SCHEMAS / schema["name"] / "schema.yaml"


def _schema_descriptions(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        description = value.get("description")
        if isinstance(description, str) and description.strip():
            yield description.strip()
        for child in value.values():
            yield from _schema_descriptions(child)
    elif isinstance(value, list):
        for child in value:
            yield from _schema_descriptions(child)


def resolve_schemas(base: dict[str, Any], query: str) -> list[dict[str, Any]]:
    query_words = set(re.findall(r"[a-z0-9]+", query.casefold()))
    resolved: list[dict[str, Any]] = []
    for schema in base["schemas"]:
        path = schema_path(schema).resolve(strict=False)
        if not path.is_file():
            raise ValueError(f"schema {schema['name']!r} does not exist: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ValueError(f"could not resolve schema {schema['name']!r}: {exc}") from exc
        descriptions = list(_schema_descriptions(data))
        shared_words = sorted(
            query_words.intersection(
                word
                for description in descriptions
                for word in re.findall(r"[a-z0-9]+", description.casefold())
            )
        )
        resolved.append(
            {
                "name": schema["name"],
                "path": str(path),
                "shared_query_words": shared_words,
            }
        )
    return resolved


def _search_open_flags() -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure source search requires O_NOFOLLOW support")
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    return flags


def _walk_search_directory(
    directory_fd: int,
    directory_path: Path,
    flags: int,
) -> Iterator[tuple[Path, int, os.stat_result]]:
    try:
        with os.scandir(directory_fd) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError:
        return
    for name in names:
        child_fd: int | None = None
        try:
            child_fd = os.open(name, flags, dir_fd=directory_fd)
            metadata = os.fstat(child_fd)
        except OSError:
            if child_fd is not None:
                try:
                    os.close(child_fd)
                except OSError:
                    pass
            continue
        child_path = directory_path / name
        try:
            if stat.S_ISREG(metadata.st_mode):
                yield child_path, child_fd, metadata
            elif stat.S_ISDIR(metadata.st_mode):
                yield from _walk_search_directory(child_fd, child_path, flags)
        finally:
            try:
                os.close(child_fd)
            except OSError:
                pass


def _iter_search_files(scope: Path) -> Iterator[tuple[Path, int, os.stat_result]]:
    flags = _search_open_flags()
    try:
        root_fd = os.open(scope, flags)
    except OSError as exc:
        raise ValueError(f"could not open search scope {scope}: {exc}") from exc
    try:
        metadata = os.fstat(root_fd)
        if stat.S_ISREG(metadata.st_mode):
            yield scope, root_fd, metadata
        elif stat.S_ISDIR(metadata.st_mode):
            yield from _walk_search_directory(root_fd, scope, flags)
    finally:
        try:
            os.close(root_fd)
        except OSError:
            pass


def _is_probable_binary(fd: int) -> bool:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        return b"\x00" in os.read(fd, BINARY_SNIFF_BYTES)
    except OSError:
        return True
    finally:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass


def search_scope(scope: Path, query: str) -> list[str]:
    resolved_scope = scope.expanduser().resolve(strict=False)
    if not resolved_scope.exists():
        raise ValueError(f"search scope does not exist: {resolved_scope}")
    normalized_query = query.casefold().strip()
    query_words = [word for word in re.findall(r"[a-z0-9]+", normalized_query) if len(word) > 1]
    matches: list[str] = []
    for path, fd, metadata in _iter_search_files(resolved_scope):
        path_text = str(path).casefold()
        path_matches = normalized_query in path_text or (
            query_words and all(word in path_text for word in query_words)
        )
        if path_matches:
            matches.append(str(path))
            continue
        try:
            if metadata.st_size > MAX_SEARCH_BYTES or _is_probable_binary(fd):
                continue
            found_words: set[str] = set()
            phrase_match = False
            with os.fdopen(os.dup(fd), "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    normalized_line = line.casefold()
                    if normalized_query in normalized_line:
                        phrase_match = True
                        break
                    if query_words:
                        found_words.update(word for word in query_words if word in normalized_line)
        except OSError:
            continue
        if phrase_match or (query_words and all(word in found_words for word in query_words)):
            matches.append(str(path))
    return sorted(matches)


def selection_from_route(result: dict[str, Any], target: str | None) -> dict[str, Any]:
    selected = result.get("selected")
    if not selected:
        return {"tier": "none", "bases": [], "reasons": []}
    return {
        "tier": "explicit" if target else "routed",
        "bases": [selected["name"]],
        "reasons": list(selected.get("reasons", [])),
    }


def hierarchy_for_search(base: dict[str, Any], schemas: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for schema in schemas:
        shared_words = schema["shared_query_words"]
        if shared_words:
            evidence = ", ".join(shared_words)
            reason = (
                f"Configured schema {schema['name']!r} has node descriptions sharing "
                f"query terms ({evidence}); searched the selected managed root."
            )
        else:
            reason = (
                f"Configured schema {schema['name']!r} belongs to the selected base; "
                "searched the selected managed root without claiming a node inference."
            )
        entries.append(
            {
                "path": str(Path(base["root"]).resolve(strict=False)),
                "schema": schema["name"],
                "decision": "searched",
                "reason": reason,
            }
        )
    return entries


def _command_argv(explicit: list[str] | None) -> list[str]:
    if explicit is not None:
        return list(explicit)
    original = getattr(sys, "orig_argv", None)
    if isinstance(original, list) and original:
        return [str(value) for value in original]
    return [sys.executable, *sys.argv]


def _record(
    *,
    session_id: str,
    query: str,
    argv: list[str],
    started_at: datetime,
    started_monotonic: float,
    operations: list[dict[str, Any]],
    selection: dict[str, Any],
    hierarchy: list[dict[str, str]],
    fallback: dict[str, Any],
    status: str,
    matched_paths: list[str],
    source_scopes: list[str],
) -> dict[str, Any]:
    finished_at = datetime.now().astimezone()
    duration = elapsed_ms(started_monotonic, time.monotonic())
    started_text = timestamp_ms(started_at)
    finished_text = timestamp_ms(finished_at)
    command = {
        "argv": argv,
        "command": shell_quote_argv(argv),
        "started_at": started_text,
        "finished_at": finished_text,
        "duration_ms": duration,
    }
    attempt = {
        "started_at": started_text,
        "finished_at": finished_text,
        "duration_ms": duration,
        "command_timings": [
            {
                "command_index": 0,
                "started_at": started_text,
                "finished_at": finished_text,
                "duration_ms": duration,
            }
        ],
        "operation_timings": [dict(operation) for operation in operations],
        "status": status,
    }
    return {
        "version": 1,
        "started_at": started_text,
        "finished_at": finished_text,
        "duration_ms": duration,
        "session_id": session_id,
        "occurrence_count": 1,
        "query": query,
        "commands": [command],
        "operations": [dict(operation) for operation in operations],
        "attempts": [attempt],
        "selection": selection,
        "hierarchy": hierarchy,
        "fallback": fallback,
        "status": status,
        "matched_paths": matched_paths,
        "source_scopes": source_scopes,
    }


def lookup(
    args: argparse.Namespace,
    *,
    command_argv: list[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    started_at = datetime.now().astimezone()
    started_monotonic = time.monotonic()
    recorder = OperationRecorder()

    load_span = recorder.start("load_config")
    try:
        config = load_config(
            cwd=args.cwd,
            home=args.home,
            config=args.config,
            require_roots=not args.allow_missing_roots,
        )
    finally:
        recorder.finish(load_span)

    audit = config["audit"]
    audit_enabled = bool(audit["enabled"])
    session_id = os.environ.get(SESSION_ENV, "") if audit_enabled else ""
    source_scopes = [str(Path(source).expanduser().resolve(strict=False)) for source in args.source]
    argv = _command_argv(command_argv)
    writer = (
        AuditTraceWriter(Path(audit["trace_root"]), session_id)
        if audit_enabled
        else None
    )

    route_result: dict[str, Any] = {"status": "no_match", "selected": None, "candidates": []}
    selection: dict[str, Any] = {"tier": "none", "bases": [], "reasons": []}
    hierarchy: list[dict[str, str]] = []
    fallback: dict[str, Any] = {"used": False, "paths": [], "reason": "Lookup did not search source."}
    status = "error"
    matched_paths: list[str] = []
    error: str | None = None

    lock_context = writer.locked(now=started_at) if writer is not None else nullcontext()
    try:
        with lock_context:
            try:
                if not args.query.strip():
                    raise ValueError("query must not be empty")
                route_span = recorder.start("route")
                try:
                    route_result = route(
                        config,
                        query=args.query,
                        cwd=args.cwd,
                        source=[*args.source, *source_scopes],
                        artifact_kind=args.artifact_kind,
                        target=args.target,
                    )
                finally:
                    recorder.finish(route_span)
                selection = selection_from_route(route_result, args.target)

                if route_result["status"] == "ambiguous":
                    status = "ambiguous"
                    fallback = {
                        "used": False,
                        "paths": [],
                        "reason": "Routing was ambiguous, so no path was searched.",
                    }
                elif route_result["status"] != "selected":
                    status = "unmatched"
                    fallback = {
                        "used": False,
                        "paths": [],
                        "reason": "No base was selected, so no path was searched.",
                    }
                else:
                    selected_name = route_result["selected"]["name"]
                    base = next(base for base in config["bases"] if base["name"] == selected_name)

                    schema_span = recorder.start("resolve_schemas")
                    try:
                        schemas = resolve_schemas(base, args.query)
                    finally:
                        recorder.finish(schema_span)
                    hierarchy = hierarchy_for_search(base, schemas)

                    managed_span = recorder.start("search_managed")
                    try:
                        matched_paths = search_scope(Path(base["root"]), args.query)
                    finally:
                        recorder.finish(managed_span)

                    if matched_paths:
                        status = "matched"
                        fallback = {
                            "used": False,
                            "paths": [],
                            "reason": "Managed knowledge contained at least one matching file.",
                        }
                    elif source_scopes:
                        fallback = {
                            "used": True,
                            "paths": [],
                            "reason": "Managed knowledge had no match; searching explicit source scopes.",
                        }
                        source_span = recorder.start("search_source")
                        try:
                            source_matches: list[str] = []
                            for source in source_scopes:
                                source_matches.extend(search_scope(Path(source), args.query))
                                fallback["paths"].append(source)
                                hierarchy.append(
                                    {
                                        "path": source,
                                        "schema": "source",
                                        "decision": "searched",
                                        "reason": "Explicit source scope searched after managed knowledge had no match.",
                                    }
                                )
                            matched_paths = sorted(dict.fromkeys(source_matches))
                        finally:
                            recorder.finish(source_span)
                        fallback["reason"] = (
                            "Managed knowledge had no match; searched explicit source scopes."
                        )
                        status = "matched" if matched_paths else "unmatched"
                    else:
                        status = "unmatched"
                        fallback = {
                            "used": False,
                            "paths": [],
                            "reason": "Managed knowledge had no match and no source scopes were provided.",
                        }
            except (OSError, ValueError, KeyError, StopIteration) as exc:
                status = "error"
                error = str(exc)

            result = {
                "selection": selection,
                "hierarchy": hierarchy,
                "fallback": fallback,
                "status": status,
                "matched_paths": matched_paths,
                "candidates": route_result.get("candidates", []),
            }
            if writer is not None:
                writer.write(
                    _record(
                        session_id=session_id,
                        query=args.query,
                        argv=argv,
                        started_at=started_at,
                        started_monotonic=started_monotonic,
                        operations=recorder.operations,
                        selection=selection,
                        hierarchy=hierarchy,
                        fallback=fallback,
                        status=status,
                        matched_paths=matched_paths,
                        source_scopes=source_scopes,
                    )
                )
            return result, error
    except AuditTraceError as exc:
        raise AuditTraceError(f"audit trace failed: {exc}") from exc


def main(argv: list[str] | None = None, *, command_argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        result, error = lookup(args, command_argv=command_argv)
    except AuditTraceError as exc:
        fail(str(exc))
    if error is not None:
        fail(error)
    json.dump(result, sys.stdout, indent=2 if args.pretty else None)
    print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Perform a bounded, strictly read-only managed project-context lookup."""

from __future__ import annotations

import argparse
import contextlib
import io
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
from load_config import load_config, nearest_config
from route import IndexState, ensure_base_index, route


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_ROOT = SCRIPT_DIR.parent / "references" / "schemas"
MAX_FILES_PER_AREA = 2_000
MAX_DIRECTORIES_PER_AREA = 500
MAX_MATCHES_PER_AREA = 20
MAX_FILE_BYTES = 1_000_000
MAX_LINE_CHARS = 500
MAX_SOURCE_SCOPES = 20
SESSION_ENV = "CODEX_THREAD_ID"
SKIP_DIRECTORIES = {
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
    parser.add_argument("--query", required=True, help="Context text to find.")
    parser.add_argument("--target", help="Explicit base name or alias.")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Source file or directory for routing and fallback; repeat as needed.",
    )
    parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="Read every base in an otherwise ambiguous route.",
    )
    parser.add_argument("--artifact-kind", help="Optional routing artifact kind.")
    parser.add_argument("--config", type=Path, help="Use only this .mem.yaml.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def empty_stats() -> dict[str, Any]:
    return {
        "managed_roots_searched": 0,
        "managed_files_scanned": 0,
        "managed_directories_scanned": 0,
        "source_scopes_searched": 0,
        "source_files_scanned": 0,
        "source_directories_scanned": 0,
        "files_skipped_binary": 0,
        "files_skipped_oversize": 0,
        "symlinks_skipped": 0,
        "hidden_directories_skipped": 0,
        "read_errors": 0,
        "managed_search_truncated": False,
        "source_search_truncated": False,
        "limits": {
            "max_files_per_area": MAX_FILES_PER_AREA,
            "max_directories_per_area": MAX_DIRECTORIES_PER_AREA,
            "max_matches_per_area": MAX_MATCHES_PER_AREA,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_source_scopes": MAX_SOURCE_SCOPES,
        },
    }


def payload(query: str, sources: list[str]) -> dict[str, Any]:
    return {
        "mode": "context_lookup",
        "status": "pending",
        "query": query,
        "sources": sources,
        "config_paths": [],
        "route": None,
        "selected_bases": [],
        "managed_matches": [],
        "fallback_used": False,
        "source_matches": [],
        "search_stats": empty_stats(),
    }


def emit(result: dict[str, Any], *, pretty: bool, exit_code: int = 0) -> None:
    if exit_code and result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
    json.dump(result, sys.stdout, indent=2 if pretty else None, sort_keys=False)
    print()
    raise SystemExit(exit_code)


def validate_sources(raw_sources: list[str]) -> tuple[list[Path], str | None]:
    if len(raw_sources) > MAX_SOURCE_SCOPES:
        return [], f"at most {MAX_SOURCE_SCOPES} source scopes may be supplied"
    validated: list[Path] = []
    seen: set[str] = set()
    for raw_source in raw_sources:
        source = Path(raw_source).expanduser()
        if source.is_symlink():
            return validated, f"source path must not be a symlink: {source}"
        try:
            resolved = source.resolve(strict=True)
        except OSError:
            return validated, f"source path does not exist: {source}"
        if not resolved.is_file() and not resolved.is_dir():
            return validated, f"source path is not a regular file or directory: {resolved}"
        label = str(resolved)
        if label not in seen:
            validated.append(resolved)
            seen.add(label)
    return validated, None


def configured_paths(args: argparse.Namespace) -> list[Path]:
    if args.config is not None:
        path = args.config.expanduser().resolve(strict=False)
        return [path] if path.is_file() else []
    paths: list[Path] = []
    nearest = nearest_config(args.cwd)
    if nearest is not None:
        paths.append(nearest)
    home_config = args.home.expanduser().resolve(strict=False) / ".mem.yaml"
    if home_config.is_file() and home_config not in paths:
        paths.append(home_config)
    return paths


def load_config_safely(args: argparse.Namespace) -> tuple[dict[str, Any] | None, str | None]:
    errors = io.StringIO()
    try:
        with contextlib.redirect_stderr(errors):
            config = load_config(
                cwd=args.cwd,
                home=args.home,
                config=args.config,
            )
    except SystemExit:
        return None, errors.getvalue().strip().removeprefix("error: ")
    return config, None


def schema_path(schema: dict[str, str]) -> Path:
    if "path" in schema:
        return Path(schema["path"]).resolve(strict=False)
    return (SCHEMA_ROOT / schema["name"] / "schema.yaml").resolve(strict=False)


def selected_base_details(
    config: dict[str, Any],
    names: list[str],
    *,
    index_cache: dict[str, IndexState] | None = None,
    index_recorder: OperationRecorder | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    by_name = {base["name"]: base for base in config["bases"]}
    cache = index_cache if index_cache is not None else {}
    selected: list[dict[str, Any]] = []
    for name in names:
        base = by_name[name]
        seen_schemas: set[str] = set()
        schemas: list[dict[str, str]] = []
        for configured_schema in base["schemas"]:
            schema_name = configured_schema["name"]
            if schema_name in seen_schemas:
                return [], f"base {name!r} configures schema {schema_name!r} more than once"
            seen_schemas.add(schema_name)
            path = schema_path(configured_schema)
            if not path.is_file():
                return [], f"schema {schema_name!r} for base {name!r} does not exist: {path}"
            schema_details = {"name": schema_name, "path": str(path)}
            if "root" in configured_schema:
                schema_details["root"] = configured_schema["root"]
            schemas.append(schema_details)
        status, index, _ = ensure_base_index(base, cache=cache, recorder=index_recorder)
        selected.append(
            {
                "name": name,
                "root": base["root"],
                "managed_root": base["managed_root"],
                "path_style": base["path_style"],
                "config_path": base["config_path"],
                "schemas": schemas,
                "index": {
                    "status": status,
                    "generated_at": index.get("generated_at") if index is not None else None,
                    "source_fingerprint": index.get("source_fingerprint") if index is not None else None,
                    "metadata": index.get("metadata") if index is not None else None,
                    "hierarchy": index.get("hierarchy") if index is not None else None,
                },
            }
        )
    return selected, None


def iter_files(
    scope: Path,
    *,
    stats: dict[str, Any],
    area: str,
    seen: set[str] | None = None,
) -> Iterator[tuple[Path, int, os.stat_result]]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("secure source search requires O_NOFOLLOW support")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    for name in ("O_CLOEXEC", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)

    def walk(directory_fd: int, directory: Path) -> Iterator[tuple[Path, int, os.stat_result]]:
        directory_key = f"{area}_directories_scanned"
        if stats[directory_key] >= MAX_DIRECTORIES_PER_AREA:
            stats[f"{area}_search_truncated"] = True
            return
        stats[directory_key] += 1

        try:
            with os.scandir(directory_fd) as entries:
                names = sorted(entry.name for entry in entries)
        except OSError:
            stats["read_errors"] += 1
            return
        for name in names:
            if area == "managed" and name == ".mem.index.json":
                continue
            path = directory / name
            try:
                link_metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError:
                stats["read_errors"] += 1
                continue
            if stat.S_ISLNK(link_metadata.st_mode):
                stats["symlinks_skipped"] += 1
                continue
            if stat.S_ISDIR(link_metadata.st_mode) and (
                name.startswith(".") or name in SKIP_DIRECTORIES
            ):
                stats["hidden_directories_skipped"] += 1
                continue
            try:
                descriptor = os.open(name, flags, dir_fd=directory_fd)
                metadata = os.fstat(descriptor)
            except OSError:
                stats["read_errors"] += 1
                continue
            try:
                if stat.S_ISDIR(metadata.st_mode):
                    yield from walk(descriptor, path)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                label = str(path)
                if seen is not None and label in seen:
                    continue
                if seen is not None:
                    seen.add(label)
                yield path, descriptor, metadata
            finally:
                os.close(descriptor)

    try:
        root_fd = os.open(scope, flags)
        root_metadata = os.fstat(root_fd)
    except OSError as exc:
        raise ValueError(f"could not open search scope {scope}: {exc}") from exc
    try:
        if stat.S_ISREG(root_metadata.st_mode):
            label = str(scope)
            if seen is None or label not in seen:
                if seen is not None:
                    seen.add(label)
                yield scope, root_fd, root_metadata
        elif stat.S_ISDIR(root_metadata.st_mode):
            yield from walk(root_fd, scope)
    finally:
        os.close(root_fd)


def read_text(
    descriptor: int, metadata: os.stat_result, stats: dict[str, Any]
) -> str | None:
    try:
        if metadata.st_size > MAX_FILE_BYTES:
            stats["files_skipped_oversize"] += 1
            return None
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, MAX_FILE_BYTES + 1)
    except OSError:
        stats["read_errors"] += 1
        return None
    if len(raw) > MAX_FILE_BYTES:
        stats["files_skipped_oversize"] += 1
        return None
    if b"\0" in raw:
        stats["files_skipped_binary"] += 1
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        stats["files_skipped_binary"] += 1
        return None


def normalized_terms(query: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", query.casefold())


def matches_query(value: str, query: str, terms: list[str]) -> bool:
    lowered = value.casefold()
    return query.casefold() in lowered or bool(terms) and all(term in lowered for term in terms)


def find_match(path: Path, query: str, text: str) -> tuple[str, int | None, str | None] | None:
    terms = normalized_terms(query)
    if matches_query(path.name, query, terms):
        return "filename", None, None
    body_match: tuple[str, int, str] | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not matches_query(line, query, terms):
            continue
        line_text = line[:MAX_LINE_CHARS]
        if line.lstrip().startswith("#"):
            return "heading", line_number, line_text
        if body_match is None:
            body_match = ("body", line_number, line_text)
    return body_match


def search_scope(scope: Path, query: str) -> list[str]:
    """Compatibility helper for one secure bounded scope search."""
    resolved = scope.expanduser().resolve(strict=False)
    if not resolved.exists():
        raise ValueError(f"search scope does not exist: {resolved}")
    stats = empty_stats()
    matches: list[str] = []
    for path, descriptor, metadata in iter_files(resolved, stats=stats, area="source"):
        if stats["source_files_scanned"] >= MAX_FILES_PER_AREA:
            break
        stats["source_files_scanned"] += 1
        text = read_text(descriptor, metadata, stats)
        if text is not None and find_match(path, query, text) is not None:
            matches.append(str(path))
    return sorted(matches)


def search_managed(
    bases: list[dict[str, Any]], query: str, stats: dict[str, Any]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for base in bases:
        managed_root = Path(base["managed_root"])
        stats["managed_roots_searched"] += 1
        for path, descriptor, metadata in iter_files(
            managed_root, stats=stats, area="managed"
        ):
            if stats["managed_files_scanned"] >= MAX_FILES_PER_AREA:
                stats["managed_search_truncated"] = True
                return matches
            stats["managed_files_scanned"] += 1
            text = read_text(descriptor, metadata, stats)
            if text is None:
                continue
            match = find_match(path, query, text)
            if match is None:
                continue
            match_type, line, line_text = match
            matches.append(
                {
                    "base": base["name"],
                    "path": str(path),
                    "relative_path": str(path.relative_to(managed_root)),
                    "match_type": match_type,
                    "line": line,
                    "line_text": line_text,
                }
            )
            if len(matches) >= MAX_MATCHES_PER_AREA:
                stats["managed_search_truncated"] = True
                return matches
    return matches


def search_sources(
    sources: list[Path], query: str, stats: dict[str, Any]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        stats["source_scopes_searched"] += 1
        for path, descriptor, metadata in iter_files(
            source, stats=stats, area="source", seen=seen
        ):
            if stats["source_files_scanned"] >= MAX_FILES_PER_AREA:
                stats["source_search_truncated"] = True
                return matches
            stats["source_files_scanned"] += 1
            text = read_text(descriptor, metadata, stats)
            if text is None:
                continue
            match = find_match(path, query, text)
            if match is None:
                continue
            match_type, line, line_text = match
            matches.append(
                {
                    "path": str(path),
                    "scope": str(source),
                    "match_type": match_type,
                    "line": line,
                    "line_text": line_text,
                }
            )
            if len(matches) >= MAX_MATCHES_PER_AREA:
                stats["source_search_truncated"] = True
                return matches
    return matches


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


def hierarchy_for_selected(
    selected: list[dict[str, Any]], query: str
) -> list[dict[str, str]]:
    query_words = set(normalized_terms(query))
    hierarchy: list[dict[str, str]] = []
    for base in selected:
        for schema in base["schemas"]:
            descriptions: list[str] = []
            try:
                data = yaml.safe_load(Path(schema["path"]).read_text(encoding="utf-8"))
                descriptions = list(_schema_descriptions(data))
            except (OSError, UnicodeError, yaml.YAMLError):
                pass
            shared_words = sorted(
                query_words.intersection(
                    word
                    for description in descriptions
                    for word in normalized_terms(description)
                )
            )
            if shared_words:
                reason = (
                    f"Configured schema {schema['name']!r} has node descriptions sharing "
                    f"query terms ({', '.join(shared_words)}); searched the managed root."
                )
            else:
                reason = (
                    f"Configured schema {schema['name']!r} belongs to the selected base; "
                    "searched the managed root without claiming a node inference."
                )
            hierarchy.append(
                {
                    "path": base["managed_root"],
                    "schema": schema["name"],
                    "decision": "searched",
                    "reason": reason,
                }
            )
    return hierarchy


def selection_from_route(routing: dict[str, Any], selected_names: list[str]) -> dict[str, Any]:
    reasons = [
        reason
        for candidate in routing.get("candidates", [])
        if candidate.get("name") in selected_names
        for reason in candidate.get("reasons", [])
    ]
    tier = routing.get("tier", "none")
    return {
        "tier": "explicit" if tier == "explicit" else "routed" if selected_names else "none",
        "bases": selected_names,
        "reasons": reasons,
    }


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


def execute_lookup(
    args: argparse.Namespace,
    result: dict[str, Any],
    config: dict[str, Any],
    recorder: OperationRecorder,
) -> tuple[dict[str, Any], int]:
    query = result["query"]
    sources, source_error = validate_sources(args.source)
    if source_error:
        result.update(status="invalid_source", error=source_error)
        return result, 2
    result["sources"] = [str(source) for source in sources]
    if not query:
        result.update(status="invalid_query", error="query must not be empty")
        return result, 2

    index_cache: dict[str, IndexState] = {}
    route_span = recorder.start("route")
    try:
        routing = route(
            config,
            query=query,
            cwd=args.cwd,
            source=args.source,
            artifact_kind=args.artifact_kind,
            target=args.target,
            index_cache=index_cache,
            index_recorder=recorder,
        )
    finally:
        recorder.finish(route_span)
    result["route"] = routing
    if routing["status"] == "selected":
        selected_names = [routing["selected"]["name"]]
    elif routing["status"] == "ambiguous" and args.allow_multiple:
        selected_names = [candidate["name"] for candidate in routing["candidates"]]
    else:
        result["status"] = routing["status"]
        result["selection"] = selection_from_route(routing, [])
        result["candidates"] = routing.get("candidates", [])
        return result, 2

    schema_span = recorder.start("resolve_schemas")
    try:
        selected, schema_error = selected_base_details(
            config, selected_names, index_cache=index_cache, index_recorder=recorder
        )
    finally:
        recorder.finish(schema_span)
    if schema_error:
        result.update(status="invalid_schema", error=schema_error)
        return result, 2
    result["selected_bases"] = selected
    selected_by_name = {base["name"]: base for base in selected}
    for candidate in routing.get("candidates", []):
        selected_base = selected_by_name.get(candidate["name"])
        if selected_base is not None:
            candidate["index"]["status"] = selected_base["index"]["status"]
    result["selection"] = selection_from_route(routing, selected_names)
    result["hierarchy"] = hierarchy_for_selected(selected, query)
    result["candidates"] = routing.get("candidates", [])

    stats = result["search_stats"]
    managed_span = recorder.start("search_managed")
    try:
        managed_matches = search_managed(selected, query, stats)
    finally:
        recorder.finish(managed_span)
    result["managed_matches"] = managed_matches
    if managed_matches:
        result["status"] = "matched"
        result["matched_paths"] = [match["path"] for match in managed_matches]
        result["fallback"] = {
            "used": False,
            "paths": [],
            "reason": "Managed knowledge contained at least one matching file.",
        }
        return result, 0

    if sources:
        result["fallback_used"] = True
        source_span = recorder.start("search_source")
        try:
            result["source_matches"] = search_sources(sources, query, stats)
        finally:
            recorder.finish(source_span)
        for source in sources:
            result["hierarchy"].append(
                {
                    "path": str(source),
                    "schema": "source",
                    "decision": "searched",
                    "reason": "Explicit source scope searched after managed knowledge had no match.",
                }
            )
    matched_paths = [match["path"] for match in result["source_matches"]]
    result["matched_paths"] = matched_paths
    result["fallback"] = {
        "used": bool(sources),
        "paths": [str(source) for source in sources] if sources else [],
        "reason": (
            "Managed knowledge had no match; searched explicit source scopes."
            if sources
            else "Managed knowledge had no match and no source scopes were provided."
        ),
    }
    result["status"] = "matched" if matched_paths else "no_matches"
    return result, 0


def main(
    argv: list[str] | None = None, *, command_argv: list[str] | None = None
) -> None:
    args = parse_args(argv)
    query = args.query.strip()
    raw_sources = [str(Path(source).expanduser().absolute()) for source in args.source]
    result = payload(query, raw_sources)
    paths = configured_paths(args)
    result["config_paths"] = [str(path) for path in paths]
    if not paths:
        if args.config is not None:
            result.update(
                status="invalid_config",
                error=f"config does not exist: {args.config.expanduser().resolve(strict=False)}",
            )
            emit(result, pretty=args.pretty, exit_code=2)
        result["status"] = "missing_config"
        emit(result, pretty=args.pretty)

    started_at = datetime.now().astimezone()
    started_monotonic = time.monotonic()
    recorder = OperationRecorder()
    load_span = recorder.start("load_config")
    config, config_error = load_config_safely(args)
    recorder.finish(load_span)
    if config_error or config is None:
        result.update(status="invalid_config", error=config_error or "could not load config")
        emit(result, pretty=args.pretty, exit_code=2)
    result["config_paths"] = config["config_paths"]

    audit = config["audit"]
    audit_enabled = bool(audit["enabled"])
    session_id = os.environ.get(SESSION_ENV, "") if audit_enabled else ""
    try:
        writer = AuditTraceWriter(Path(audit["trace_root"]), session_id) if audit_enabled else None
        lock_context = writer.locked(now=started_at) if writer is not None else nullcontext()
        with lock_context:
            result, exit_code = execute_lookup(args, result, config, recorder)
            trace_status = {
                "no_matches": "unmatched",
                "no_match": "unmatched",
                "ambiguous": "ambiguous",
                "matched": "matched",
            }.get(result["status"], "error")
            selection = result.get("selection", {"tier": "none", "bases": [], "reasons": []})
            hierarchy = result.get("hierarchy", [])
            fallback = result.get(
                "fallback",
                {
                    "used": False,
                    "paths": [str(source) for source in validate_sources(args.source)[0]],
                    "reason": result.get("error", "Lookup did not search source."),
                },
            )
            matched_paths = result.get("matched_paths", [])
            if writer is not None:
                writer.write(
                    _record(
                        session_id=session_id,
                        query=query,
                        argv=_command_argv(command_argv),
                        started_at=started_at,
                        started_monotonic=started_monotonic,
                        operations=recorder.operations,
                        selection=selection,
                        hierarchy=hierarchy,
                        fallback=fallback,
                        status=trace_status,
                        matched_paths=matched_paths,
                        source_scopes=[str(source) for source in validate_sources(args.source)[0]],
                    )
                )
    except AuditTraceError as exc:
        fail(f"audit trace failed: {exc}")
    emit(result, pretty=args.pretty, exit_code=exit_code)


if __name__ == "__main__":
    main()

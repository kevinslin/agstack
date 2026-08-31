#!/usr/bin/env python3
"""Build the current mem workspace project index."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import secrets
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from base_index import BaseIndexError, read_index
from load_config import find_config_paths, load_config
from workspace_lookup import label_for_path
from workspace_llm import infer_projects as default_infer_projects
from workspace_rollouts import collect_work as default_collect_work


DEFAULT_WINDOW_DAYS = 7
MAX_ACTIVITY_TEXT = 1200
MAX_PACKET_TEXT_CHARS = 600_000
MAX_RELEVANT_CANDIDATES = 60
MAX_RELEVANT_PER_ROOT = 8
MAX_RELEVANT_BYTES = 2000
MAX_RELEVANT_WALK_DEPTH = 3
MAX_SCHEMA_NODES = 30

CollectWork = Callable[[Path, datetime, datetime], tuple[list[dict[str, Any]], list[str]]]


class WorkspaceBuildError(Exception):
    """A build failure tagged with the failed stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class BuildResult:
    status: str
    path: Path
    log_path: Path
    project_count: int
    partial: bool
    warnings: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": str(self.path),
            "log_path": str(self.log_path),
            "project_count": self.project_count,
            "partial": self.partial,
        }


def _timezone_name() -> str:
    configured = os.environ.get("TZ")
    if configured:
        candidate = configured.removeprefix(":")
        try:
            ZoneInfo(candidate)
            return candidate
        except ZoneInfoNotFoundError:
            pass

    localtime = Path("/etc/localtime").resolve(strict=False)
    parts = localtime.parts
    if "zoneinfo" in parts:
        name = "/".join(parts[parts.index("zoneinfo") + 1 :])
        if name:
            try:
                ZoneInfo(name)
                return name
            except ZoneInfoNotFoundError:
                pass
    return "UTC"


def _now() -> datetime:
    name = _timezone_name()
    try:
        return datetime.now(ZoneInfo(name)).replace(microsecond=0)
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).replace(microsecond=0)


def _default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser().resolve(strict=False)


def _default_output_path() -> Path:
    return Path.home() / ".mem" / "workspace" / "index.json"


def _workspace_log_relative_path(generated_at: datetime) -> Path:
    timestamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("logs") / f"workspace-{timestamp}-{secrets.token_hex(8)}.log"


def _hash_id(prefix: str, values: list[str]) -> str:
    digest = hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceBuildError("validation", f"{field} must be a non-empty string")
    return value.strip()


def _prepare_activity(activity: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(activity, list):
        raise WorkspaceBuildError("collection", "collector returned activity that is not a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(activity):
        if not isinstance(item, dict):
            raise WorkspaceBuildError("collection", f"activity[{index}] must be an object")
        task_id = _nonempty_string(item.get("task_id"), f"activity[{index}].task_id")
        path = _nonempty_string(item.get("path"), f"activity[{index}].path")
        line = item.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise WorkspaceBuildError("collection", f"activity[{index}].line must be a positive integer")
        occurred_at = _nonempty_string(item.get("occurred_at"), f"activity[{index}].occurred_at")
        cwd = _nonempty_string(item.get("cwd"), f"activity[{index}].cwd")
        text = _nonempty_string(item.get("text"), f"activity[{index}].text")
        if len(text) > MAX_ACTIVITY_TEXT:
            warnings.append(
                f"partial text: truncated collected activity at {path}:{line} to {MAX_ACTIVITY_TEXT} chars"
            )
            text = text[: MAX_ACTIVITY_TEXT - 3].rstrip() + "..."
        normalized.append(
            {
                "id": _hash_id("source", [task_id, path, str(line)]),
                "task_id": task_id,
                "path": path,
                "line": line,
                "occurred_at": occurred_at,
                "cwd": cwd,
                "text": text,
            }
        )
    return normalized


def _git_output(cwd: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _canonical_repo_path(cwd: Path) -> Path | None:
    top = _git_output(cwd, ["rev-parse", "--show-toplevel"])
    common = _git_output(cwd, ["rev-parse", "--git-common-dir"])
    if top is None or common is None:
        return None
    top_path = Path(top).resolve(strict=False)
    common_path = Path(common)
    if not common_path.is_absolute():
        common_path = (cwd / common_path).resolve(strict=False)
    else:
        common_path = common_path.resolve(strict=False)
    if common_path.name == ".git":
        primary = common_path.parent.resolve(strict=False)
        if primary.exists():
            return primary
    return top_path


def _strip_remote_credentials(remote: str | None) -> str | None:
    if remote is None:
        return None
    if "://" not in remote:
        return remote
    parsed = urlsplit(remote)
    if "@" not in parsed.netloc:
        return remote
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _repo_candidate(cwd: Path) -> dict[str, Any] | None:
    path = _canonical_repo_path(cwd)
    if path is None:
        return None
    remote = _strip_remote_credentials(_git_output(path, ["config", "--get", "remote.origin.url"]))
    name = path.name or "repository"
    return {"id": _hash_id("repo", [str(path)]), "name": name, "path": str(path), "remote": remote}


def _schema_descriptions(path: str | None) -> list[dict[str, str]]:
    if not path:
        return []
    schema_path = Path(path)
    if not schema_path.is_file():
        return []
    try:
        import yaml
    except ImportError:
        return []
    try:
        payload = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        return []
    root = payload.get("schema") if isinstance(payload, dict) else None
    if not isinstance(root, dict):
        return []
    descriptions: list[dict[str, str]] = []

    def visit(node: dict[str, Any], prefix: str) -> None:
        if len(descriptions) >= MAX_SCHEMA_NODES:
            return
        for name, value in node.items():
            if len(descriptions) >= MAX_SCHEMA_NODES:
                return
            if not isinstance(value, dict):
                continue
            logical_path = f"{prefix}/{name}" if prefix else str(name)
            description = value.get("description")
            if isinstance(description, str) and description.strip():
                descriptions.append({"path": logical_path, "description": description.strip()})
            children = value.get("children")
            if isinstance(children, dict):
                visit(children, logical_path)

    visit(root, "")
    return descriptions


def _read_base_index(base: dict[str, Any], warnings: list[str]) -> dict[str, Any] | None:
    try:
        index = read_index(base)
    except BaseIndexError as exc:
        warnings.append(f"base index unavailable for {base['name']} at {base['index_path']}: {exc}")
        return None
    except OSError as exc:
        warnings.append(f"base index unreadable for {base['name']} at {base['index_path']}: {exc}")
        return None
    return {
        "generated_at": index["generated_at"],
        "document_count": index["document_count"],
        "metadata": index["metadata"],
        "hierarchy": index["hierarchy"][:20],
    }


def _collect_bases(cwds: list[Path], home: Path, warnings: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for cwd in cwds:
        config_paths = find_config_paths(cwd, home)
        if not config_paths:
            continue
        error_stream = io.StringIO()
        try:
            with contextlib.redirect_stderr(error_stream):
                config = load_config(cwd=cwd, home=home, require_roots=False)
        except SystemExit:
            message = error_stream.getvalue().strip() or "unknown configuration error"
            warnings.append(f"mem config unavailable for cwd {cwd}: {message}")
            continue
        for base in config["bases"]:
            key = (base["config_path"], base["name"], base["root"])
            if key in seen:
                continue
            seen.add(key)
            schema_summaries = [
                {
                    "name": schema["name"],
                    "path": schema.get("path"),
                    "root": schema.get("root"),
                    "nodes": _schema_descriptions(schema.get("path")),
                }
                for schema in base["schemas"]
            ]
            candidate = {
                "id": _hash_id("base", list(key)),
                "config_path": base["config_path"],
                "name": base["name"],
                "root": base["root"],
                "managed_root": base["managed_root"],
                "description": base["description"],
                "schemas": schema_summaries,
                "index": _read_base_index(base, warnings),
            }
            candidates.append(candidate)
    candidates.sort(key=lambda item: (item["config_path"], item["name"], item["root"]))
    return candidates


PROJECT_RECORD_NAMES = {
    "README.md",
    "AGENTS.md",
    "design.md",
    "progress.md",
    "learnings.md",
    "steering.md",
    "spec.md",
    "handoff.md",
    "report.md",
}
SKIP_DOCUMENT_DIRS = {".git", ".hg", ".svn", ".venv", "__pycache__", "node_modules", "dist", "build"}


def _read_relevant_excerpt(path: Path, warnings: list[str]) -> str:
    if path.name == "AGENTS.md":
        return ""
    try:
        with path.open("rb") as handle:
            content = handle.read(MAX_RELEVANT_BYTES + 1)
    except OSError as exc:
        warnings.append(f"relevant document unreadable at {path}: {exc}")
        return ""
    truncated = len(content) > MAX_RELEVANT_BYTES
    if truncated:
        content = content[:MAX_RELEVANT_BYTES]
        warnings.append(f"partial relevant document: truncated {path} to {MAX_RELEVANT_BYTES} bytes")
    try:
        return content.decode("utf-8", errors="replace").strip()
    except UnicodeError:
        warnings.append(f"relevant document undecodable at {path}")
        return ""


def _direct_project_records(root: Path) -> list[Path]:
    paths = [root / name for name in sorted(PROJECT_RECORD_NAMES)]
    specs = root / "specs"
    if specs.is_dir():
        try:
            paths.extend(sorted(spec / "spec.md" for spec in specs.iterdir() if spec.is_dir()))
        except OSError:
            pass
    return paths


def _walk_project_records(root: Path) -> list[Path]:
    paths: list[Path] = []
    root_depth = len(root.parts)
    try:
        for directory, names, filenames in os.walk(root):
            current = Path(directory)
            depth = len(current.parts) - root_depth
            names[:] = [
                name
                for name in names
                if name not in SKIP_DOCUMENT_DIRS and not name.startswith(".") and depth < MAX_RELEVANT_WALK_DEPTH
            ]
            for filename in sorted(filenames):
                if filename in PROJECT_RECORD_NAMES:
                    paths.append(current / filename)
            if len(paths) >= MAX_RELEVANT_PER_ROOT:
                return paths
    except OSError:
        return paths
    return paths


def _candidate_documents_for_root(
    root: Path, warnings: list[str], *, allow_walk: bool
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()
    paths = _direct_project_records(root)
    if allow_walk:
        paths.extend(_walk_project_records(root))
    for path in paths:
        if len(candidates) >= MAX_RELEVANT_PER_ROOT:
            break
        if path in seen or not path.is_file():
            continue
        resolved = path.resolve(strict=False)
        seen.add(path)
        candidates.append(
            {
                "id": _hash_id("relevant", [str(resolved)]),
                "name": label_for_path(str(resolved), [str(root)]),
                "path": str(resolved),
                "hint": "Existing workspace document",
                "excerpt": _read_relevant_excerpt(resolved, warnings),
            }
        )
    return candidates


def _collect_relevant_documents(
    cwds: list[Path], bases: list[dict[str, Any]], warnings: list[str]
) -> list[dict[str, Any]]:
    roots: list[tuple[Path, bool]] = []
    for cwd in cwds:
        if cwd.exists():
            roots.append((cwd if cwd.is_dir() else cwd.parent, False))
    for base in bases:
        for field, allow_walk in (("managed_root", True), ("root", False)):
            root = Path(base[field])
            if root.exists() and root.is_dir():
                roots.append((root, allow_walk))
    seen_roots: set[tuple[Path, bool]] = set()
    documents: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for root, allow_walk in roots:
        resolved_root = root.resolve(strict=False)
        root_key = (resolved_root, allow_walk)
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        for document in _candidate_documents_for_root(resolved_root, warnings, allow_walk=allow_walk):
            path = Path(document["path"])
            if path in seen_paths:
                continue
            seen_paths.add(path)
            documents.append(document)
            if len(documents) >= MAX_RELEVANT_CANDIDATES:
                return documents
    return documents


def _collect_resources(
    activity: list[dict[str, Any]], home: Path, context_cwds: list[Path]
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    cwds = sorted(
        {
            Path(item["cwd"]).expanduser().resolve(strict=False)
            for item in activity
        }
        | {cwd.expanduser().resolve(strict=False) for cwd in context_cwds}
    )
    repos: dict[str, dict[str, Any]] = {}
    for cwd in cwds:
        repo = _repo_candidate(cwd)
        if repo is not None:
            repos[repo["id"]] = repo
    bases = _collect_bases(cwds, home, warnings)
    for base in bases:
        repo = _repo_candidate(Path(base["root"]))
        if repo is not None:
            repos[repo["id"]] = repo
    relevant = _collect_relevant_documents(cwds, bases, warnings)
    return {"repos": sorted(repos.values(), key=lambda item: item["path"]), "bases": bases, "relevant": relevant}, warnings


def _project_activity_for_packet(
    activity: list[dict[str, Any]], warnings: list[str]
) -> list[dict[str, Any]]:
    total_text = sum(len(item["text"]) for item in activity)
    per_item_limit = MAX_ACTIVITY_TEXT
    if total_text > MAX_PACKET_TEXT_CHARS and activity:
        per_item_limit = max(80, MAX_PACKET_TEXT_CHARS // len(activity))
        warnings.append(
            f"partial activity text: compressed {len(activity)} collected items to fit the inference packet"
        )

    projected: list[dict[str, Any]] = []
    for item in activity:
        text = item["text"]
        if len(text) > per_item_limit:
            text = text[: per_item_limit - 3].rstrip() + "..."
        projected.append(
            {
                "id": item["id"],
                "task_id": item["task_id"],
                "occurred_at": item["occurred_at"],
                "cwd": item["cwd"],
                "text": text,
            }
        )
    return projected


def model_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["projects"],
        "properties": {
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "description",
                        "aliases",
                        "priority",
                        "priority_reason",
                        "base_ids",
                        "repo_ids",
                        "relevant",
                        "source_ids",
                    ],
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "description": {"type": ["string", "null"]},
                        "aliases": {"type": "array", "items": {"type": "string", "minLength": 1}},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 3},
                        "priority_reason": {"type": "string", "minLength": 1},
                        "base_ids": {"type": "array", "items": {"type": "string"}},
                        "repo_ids": {"type": "array", "items": {"type": "string"}},
                        "relevant": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "reason"],
                                "properties": {
                                    "id": {"type": "string"},
                                    "reason": {"type": "string", "minLength": 1},
                                },
                            },
                        },
                        "source_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    }


def _packet(
    *,
    generated_at: datetime,
    start: datetime,
    end: datetime,
    timezone_name: str,
    activity: list[dict[str, Any]],
    resources: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "generated_at": generated_at.isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "timezone": timezone_name},
        "activity": _project_activity_for_packet(activity, warnings),
        "resources": resources,
        "warnings": warnings,
        "instructions": [
            "Return meaningful current projects only.",
            "Select resources and sources only by the candidate IDs present in this packet.",
            "Omit incidental work rather than forcing every activity into a project.",
            "Priority is 1 for primary focus, 2 for meaningful secondary work, and 3 for occasional or background work.",
        ],
    }


def _validate_model_output(output: Any) -> list[dict[str, Any]]:
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError as exc:
            raise WorkspaceBuildError("model", f"runner returned malformed JSON: {exc}") from exc
    if not isinstance(output, dict) or set(output) != {"projects"}:
        raise WorkspaceBuildError("validation", "model output must contain only projects")
    projects = output["projects"]
    if not isinstance(projects, list):
        raise WorkspaceBuildError("validation", "model output projects must be a list")
    validated: list[dict[str, Any]] = []
    for index, project in enumerate(projects):
        if not isinstance(project, dict):
            raise WorkspaceBuildError("validation", f"projects[{index}] must be an object")
        allowed = {
            "name",
            "description",
            "aliases",
            "priority",
            "priority_reason",
            "base_ids",
            "repo_ids",
            "relevant",
            "source_ids",
        }
        extra = set(project) - allowed
        required = allowed
        missing = required - set(project)
        if extra or missing:
            raise WorkspaceBuildError(
                "validation",
                f"projects[{index}] has invalid fields: missing={sorted(missing)} extra={sorted(extra)}",
            )
        priority = project["priority"]
        if not isinstance(priority, int) or isinstance(priority, bool) or priority not in {1, 2, 3}:
            raise WorkspaceBuildError("validation", f"projects[{index}].priority must be 1, 2, or 3")
        aliases = project["aliases"]
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
            raise WorkspaceBuildError("validation", f"projects[{index}].aliases must be non-empty strings")
        for field in ("base_ids", "repo_ids", "source_ids"):
            values = project[field]
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise WorkspaceBuildError("validation", f"projects[{index}].{field} must be string IDs")
        relevant = project["relevant"]
        if not isinstance(relevant, list):
            raise WorkspaceBuildError("validation", f"projects[{index}].relevant must be a list")
        for rel_index, item in enumerate(relevant):
            if not isinstance(item, dict) or set(item) != {"id", "reason"}:
                raise WorkspaceBuildError(
                    "validation", f"projects[{index}].relevant[{rel_index}] must contain id and reason"
                )
            _nonempty_string(item["id"], f"projects[{index}].relevant[{rel_index}].id")
            _nonempty_string(item["reason"], f"projects[{index}].relevant[{rel_index}].reason")
        _nonempty_string(project["name"], f"projects[{index}].name")
        _nonempty_string(project["priority_reason"], f"projects[{index}].priority_reason")
        if project["description"] is not None:
            _nonempty_string(project["description"], f"projects[{index}].description")
        if not project["source_ids"]:
            raise WorkspaceBuildError("validation", f"projects[{index}] must select at least one source")
        validated.append(project)
    return validated


def _hydrate_projects(
    model_projects: list[dict[str, Any]],
    *,
    activity: list[dict[str, Any]],
    resources: dict[str, Any],
) -> list[dict[str, Any]]:
    bases = {item["id"]: item for item in resources["bases"]}
    repos = {item["id"]: item for item in resources["repos"]}
    relevant = {item["id"]: item for item in resources["relevant"]}
    sources = {item["id"]: item for item in activity}
    projects: list[dict[str, Any]] = []
    for index, project in enumerate(model_projects):
        missing: list[str] = []
        base_ids = list(dict.fromkeys(project["base_ids"]))
        repo_ids = list(dict.fromkeys(project["repo_ids"]))
        source_ids = list(dict.fromkeys(project["source_ids"]))
        relevant_items = project["relevant"]
        for value in base_ids:
            if value not in bases:
                missing.append(value)
        for value in repo_ids:
            if value not in repos:
                missing.append(value)
        for value in source_ids:
            if value not in sources:
                missing.append(value)
        for item in relevant_items:
            if item["id"] not in relevant:
                missing.append(item["id"])
        if missing:
            raise WorkspaceBuildError(
                "validation", f"projects[{index}] selected unknown candidate id(s): {', '.join(sorted(set(missing)))}"
            )
        grouped_sources: list[dict[str, Any]] = []
        grouped_index: dict[tuple[str, str], dict[str, Any]] = {}
        for value in source_ids:
            source = sources[value]
            key = (source["task_id"], source["path"])
            group = grouped_index.get(key)
            if group is None:
                group = {"task_id": source["task_id"], "path": source["path"], "lines": []}
                grouped_index[key] = group
                grouped_sources.append(group)
            if source["line"] not in group["lines"]:
                group["lines"].append(source["line"])

        hydrated: dict[str, Any] = {
            "name": project["name"].strip(),
            "aliases": [alias.strip() for alias in project["aliases"]],
            "priority": project["priority"],
            "priority_reason": project["priority_reason"].strip(),
            "bases": [
                {"config_path": bases[value]["config_path"], "name": bases[value]["name"], "root": bases[value]["root"]}
                for value in base_ids
            ],
            "repos": [
                {"name": repos[value]["name"], "path": repos[value]["path"], "remote": repos[value]["remote"]}
                for value in repo_ids
            ],
            "relevant": [
                {
                    "name": relevant[item["id"]]["name"],
                    "path": relevant[item["id"]]["path"],
                    "reason": item["reason"].strip(),
                }
                for item in relevant_items
            ],
            "sources": grouped_sources,
        }
        if isinstance(project["description"], str) and project["description"].strip():
            hydrated["description"] = project["description"].strip()
        projects.append(hydrated)
    return projects


def build_workspace_index(
    *,
    codex_home: Path | None = None,
    output_path: Path | None = None,
    collect_work: CollectWork | None = None,
    infer_projects: Callable[..., dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> BuildResult:
    generated_at = (now or _now()).replace(microsecond=0)
    timezone_name = _timezone_name()
    end = generated_at
    start = end - timedelta(days=DEFAULT_WINDOW_DAYS)
    resolved_codex_home = (codex_home or _default_codex_home()).expanduser().resolve(strict=False)
    resolved_output_path = (output_path or _default_output_path()).expanduser()
    collector = collect_work or default_collect_work
    try:
        raw_activity, collection_warnings = collector(resolved_codex_home, start, end)
    except Exception as exc:
        raise WorkspaceBuildError("collection", str(exc)) from exc
    if not isinstance(collection_warnings, list) or any(
        not isinstance(value, str) or not value.strip() for value in collection_warnings
    ):
        raise WorkspaceBuildError("collection", "collector warnings must be non-empty strings")
    warnings = list(collection_warnings)
    activity = _prepare_activity(raw_activity, warnings)
    resources, resource_warnings = _collect_resources(activity, Path.home(), [Path.cwd()])
    warnings.extend(resource_warnings)

    if activity:
        runner = infer_projects or default_infer_projects
        packet = _packet(
            generated_at=generated_at,
            start=start,
            end=end,
            timezone_name=timezone_name,
            activity=activity,
            resources=resources,
            warnings=warnings,
        )
        try:
            model_output = runner(packet, model_schema(), codex_home=resolved_codex_home)
        except Exception as exc:
            raise WorkspaceBuildError("model", str(exc)) from exc
        projects = _hydrate_projects(_validate_model_output(model_output), activity=activity, resources=resources)
    else:
        projects = []

    window = {"start": start.isoformat(), "end": end.isoformat(), "timezone": timezone_name}
    log_path = _publish_workspace_snapshot(
        output_path=resolved_output_path,
        generated_at=generated_at,
        window=window,
        partial=bool(warnings),
        warnings=warnings,
        projects=projects,
    )
    return BuildResult(
        status="ok",
        path=resolved_output_path,
        log_path=log_path,
        project_count=len(projects),
        partial=bool(warnings),
        warnings=tuple(warnings),
    )


def _ensure_safe_output_parent(path: Path) -> None:
    parent = path.parent
    current = Path(path.anchor) if path.is_absolute() else Path(".")
    for part in parent.parts:
        if part in {"", path.anchor}:
            continue
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise WorkspaceBuildError("publish", f"unsafe output directory: {current}")
    metadata = None
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise WorkspaceBuildError("publish", f"unsafe output path: {path}")


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    parent = path.parent
    temporary = parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    try:
        _ensure_safe_output_parent(path)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        with contextlib.suppress(OSError):
            directory_descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    except OSError as exc:
        raise WorkspaceBuildError("publish", f"could not atomically publish {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _atomic_publish(path: Path, snapshot: dict[str, Any]) -> None:
    payload = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(path, payload)


def _warning_log_payload(
    *,
    generated_at: datetime,
    index_path: Path,
    warnings: list[str],
) -> bytes:
    lines = [
        "mem workspace build warning log",
        f"generated_at: {generated_at.isoformat()}",
        f"index_path: {index_path}",
        f"warning_count: {len(warnings)}",
        "",
    ]
    if warnings:
        lines.append("warnings:")
        lines.extend(f"{index}. {warning}" for index, warning in enumerate(warnings, start=1))
    else:
        lines.append("No warnings.")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def _publish_workspace_snapshot(
    *,
    output_path: Path,
    generated_at: datetime,
    window: dict[str, str],
    partial: bool,
    warnings: list[str],
    projects: list[dict[str, Any]],
) -> Path:
    log_relative_path = _workspace_log_relative_path(generated_at)
    log_path = output_path.parent / log_relative_path
    _atomic_write_bytes(
        log_path,
        _warning_log_payload(generated_at=generated_at, index_path=output_path, warnings=warnings),
    )
    snapshot = {
        "generated_at": generated_at.isoformat(),
        "window": window,
        "partial": partial,
        "log_path": log_relative_path.as_posix(),
        "projects": projects,
    }
    _atomic_publish(output_path, snapshot)
    return log_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mem workspace", description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("--pretty", action="store_true", help="Pretty-print the short success JSON.")
    lookup = subcommands.add_parser("lookup")
    lookup.add_argument("--query", help="Filter projects by exact name, alias, text, or resource path.")
    lookup.add_argument("--details", action="store_true", help="Include bases, repositories, relevant files, and priority reason.")
    lookup.add_argument(
        "--include-sources",
        action="store_true",
        help="Include grouped source locations; also includes detail fields.",
    )
    lookup.add_argument("--pretty", action="store_true", help="Pretty-print lookup JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "lookup":
        from workspace_lookup import lookup_workspace, WorkspaceLookupError

        try:
            result = lookup_workspace(
                query=args.query,
                details=args.details,
                include_sources=args.include_sources,
            )
        except WorkspaceLookupError as exc:
            print(f"error: lookup: {exc}", file=sys.stderr)
            return 1
        json.dump(result, sys.stdout, indent=2 if args.pretty else None)
        print()
        return 0
    if args.mode != "build":
        raise AssertionError(f"unhandled workspace mode: {args.mode}")
    try:
        result = build_workspace_index()
    except WorkspaceBuildError as exc:
        print(f"error: {exc.stage}: {exc}", file=sys.stderr)
        return 1
    if result.warnings:
        print(f"warning: {len(result.warnings)} warning(s); see {result.log_path}", file=sys.stderr)
    json.dump(result.summary(), sys.stdout, indent=2 if args.pretty else None)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

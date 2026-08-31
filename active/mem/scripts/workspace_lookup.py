"""Read the published mem workspace snapshot."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class WorkspaceLookupError(Exception):
    """The workspace index cannot be read as a valid lookup source."""


def default_index_path() -> Path:
    return Path.home() / ".mem" / "workspace" / "index.json"


def label_for_path(path: str, roots: list[str] | tuple[str, ...]) -> str:
    """Return a stable, scoped label for a document path."""
    target = Path(os.path.normpath(str(Path(path).expanduser())))
    best: tuple[int, str] | None = None
    for root_value in roots:
        if not isinstance(root_value, str) or not root_value.strip():
            continue
        root = Path(os.path.normpath(str(Path(root_value).expanduser())))
        try:
            relative = target.relative_to(root)
        except ValueError:
            continue
        label = relative.as_posix()
        if not label or label == ".":
            label = target.name
        score = len(root.parts)
        if best is None or score > best[0]:
            best = (score, label)
    if best is not None:
        return best[1]
    name = target.name
    if name:
        return name
    return path


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkspaceLookupError(f"{field} must be an object")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceLookupError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, field)


def _require_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise WorkspaceLookupError(f"{field} must be a list of non-empty strings")
    return value


def _require_record_list(
    value: Any,
    field: str,
    *,
    required: set[str],
    allowed: set[str],
    line_field: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WorkspaceLookupError(f"{field} must be a list")
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        current = _require_object(item, f"{field}[{index}]")
        extra = set(current) - allowed
        missing = required - set(current)
        if extra or missing:
            raise WorkspaceLookupError(
                f"{field}[{index}] has invalid fields: missing={sorted(missing)} extra={sorted(extra)}"
            )
        if line_field is None:
            if "path" in current:
                _require_string(current["path"], f"{field}[{index}].path")
            if "root" in current:
                _require_string(current["root"], f"{field}[{index}].root")
            if "config_path" in current:
                _require_string(current["config_path"], f"{field}[{index}].config_path")
            if "name" in current:
                _require_string(current["name"], f"{field}[{index}].name")
            if "reason" in current:
                _require_string(current["reason"], f"{field}[{index}].reason")
            if "remote" in current and current["remote"] is not None:
                _require_string(current["remote"], f"{field}[{index}].remote")
        else:
            _require_string(current.get("task_id"), f"{field}[{index}].task_id")
            _require_string(current.get("path"), f"{field}[{index}].path")
            lines = current.get(line_field)
            if not isinstance(lines, list) or any(
                not isinstance(line, int) or isinstance(line, bool) or line < 1 for line in lines
            ):
                raise WorkspaceLookupError(f"{field}[{index}].{line_field} must be a list of positive integers")
        validated.append(current)
    return validated


def _validate_project(project: Any, index: int) -> dict[str, Any]:
    current = _require_object(project, f"projects[{index}]")
    required = {"name", "aliases", "priority", "priority_reason", "bases", "repos", "relevant", "sources"}
    allowed = required | {"description"}
    extra = set(current) - allowed
    missing = required - set(current)
    if extra or missing:
        raise WorkspaceLookupError(
            f"projects[{index}] has invalid fields: missing={sorted(missing)} extra={sorted(extra)}"
        )
    priority = current["priority"]
    if not isinstance(priority, int) or isinstance(priority, bool) or priority not in {1, 2, 3}:
        raise WorkspaceLookupError(f"projects[{index}].priority must be 1, 2, or 3")
    _require_string(current["name"], f"projects[{index}].name")
    _optional_string(current.get("description"), f"projects[{index}].description")
    _require_string_list(current["aliases"], f"projects[{index}].aliases")
    _require_string(current["priority_reason"], f"projects[{index}].priority_reason")
    _require_record_list(
        current["bases"],
        f"projects[{index}].bases",
        required={"config_path", "name", "root"},
        allowed={"config_path", "name", "root"},
    )
    _require_record_list(
        current["repos"],
        f"projects[{index}].repos",
        required={"name", "path", "remote"},
        allowed={"name", "path", "remote"},
    )
    _require_record_list(
        current["relevant"],
        f"projects[{index}].relevant",
        required={"name", "path", "reason"},
        allowed={"name", "path", "reason"},
    )
    sources = _require_record_list(
        current["sources"],
        f"projects[{index}].sources",
        required={"task_id", "path", "lines"},
        allowed={"task_id", "path", "lines"},
        line_field="lines",
    )
    if not sources:
        raise WorkspaceLookupError(f"projects[{index}].sources must not be empty")
    return current


def load_workspace_index(index_path: Path | None = None) -> dict[str, Any]:
    path = (index_path or default_index_path()).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceLookupError(f"workspace index does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceLookupError(f"workspace index is malformed JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise WorkspaceLookupError(f"workspace index is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise WorkspaceLookupError(f"workspace index is unreadable: {exc}") from exc
    root = _require_object(payload, "workspace index")
    required = {"generated_at", "window", "partial", "log_path", "projects"}
    extra = set(root) - required
    missing = required - set(root)
    if extra or missing:
        raise WorkspaceLookupError(f"workspace index has invalid fields: missing={sorted(missing)} extra={sorted(extra)}")
    _require_string(root["generated_at"], "generated_at")
    window = _require_object(root["window"], "window")
    if set(window) != {"start", "end", "timezone"}:
        raise WorkspaceLookupError("window must contain only start, end, and timezone")
    _require_string(window["start"], "window.start")
    _require_string(window["end"], "window.end")
    _require_string(window["timezone"], "window.timezone")
    if not isinstance(root["partial"], bool):
        raise WorkspaceLookupError("partial must be a boolean")
    _require_string(root["log_path"], "log_path")
    projects = root["projects"]
    if not isinstance(projects, list):
        raise WorkspaceLookupError("projects must be a list")
    for index, project in enumerate(projects):
        _validate_project(project, index)
    return root


def _resource_roots(project: dict[str, Any]) -> list[str]:
    roots: list[str] = []
    for base in project["bases"]:
        roots.append(base["root"])
    for repo in project["repos"]:
        roots.append(repo["path"])
    return roots


def _project_paths(project: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for base in project["bases"]:
        paths.extend([base["root"], base["config_path"]])
    for repo in project["repos"]:
        paths.append(repo["path"])
    for item in project["relevant"]:
        paths.append(item["path"])
    return paths


def _is_path_query(query: str) -> bool:
    return "/" in query or "\\" in query or query.startswith(("~", "."))


def _path_relevance(query: str, paths: list[str]) -> int:
    raw = query.strip()
    if not raw:
        return 0
    query_path = Path(raw).expanduser()
    query_text = query_path.as_posix().rstrip("/").casefold()
    if not query_text:
        return 0
    best = 0
    for value in paths:
        path = Path(value).expanduser()
        path_text = path.as_posix().rstrip("/").casefold()
        if not path_text:
            continue
        if path_text == query_text:
            best = max(best, 100)
        if path_text.startswith(query_text + "/") or query_text.startswith(path_text + "/"):
            best = max(best, 80)
        if f"/{query_text}/" in f"/{path_text}/" or path_text.endswith(f"/{query_text}"):
            best = max(best, 60)
    return best


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text)
        if token.strip()
    ]


def _text_relevance(query: str, project: dict[str, Any]) -> int:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0
    strong = " ".join([project["name"], *project["aliases"]]).casefold()
    medium = " ".join(
        value
        for value in (project.get("description"), project["priority_reason"])
        if isinstance(value, str)
    ).casefold()
    weak = " ".join([item["reason"] for item in project["relevant"]] + _project_paths(project)).casefold()
    score = 0
    for token in query_tokens:
        if token in strong:
            score += 12
        if token in medium:
            score += 6
        if token in weak:
            score += 3
    return score


def _exact_rank(query: str, project: dict[str, Any]) -> int:
    folded = query.strip().casefold()
    if not folded:
        return 0
    names = [project["name"], *project["aliases"]]
    return 1 if any(value.casefold() == folded for value in names) else 0


def _rank_project(query: str, project: dict[str, Any]) -> tuple[int, int]:
    if _is_path_query(query):
        relevance = _path_relevance(query, _project_paths(project))
    else:
        relevance = _text_relevance(query, project)
    return (_exact_rank(query, project), relevance)


def _project_projection(project: dict[str, Any], *, details: bool, include_sources: bool) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "name": project["name"],
        "aliases": project["aliases"],
        "priority": project["priority"],
    }
    if project.get("description"):
        projected["description"] = project["description"]
    if details:
        roots = _resource_roots(project)
        projected["priority_reason"] = project["priority_reason"]
        projected["bases"] = project["bases"]
        projected["repos"] = project["repos"]
        projected["relevant"] = [
            {
                "name": label_for_path(item["path"], roots),
                "path": item["path"],
                "reason": item["reason"],
            }
            for item in project["relevant"]
        ]
    if include_sources:
        projected["sources"] = project["sources"]
    return projected


def lookup_workspace(
    *,
    query: str | None = None,
    details: bool = False,
    include_sources: bool = False,
    index_path: Path | None = None,
) -> dict[str, Any]:
    path = (index_path or default_index_path()).expanduser()
    snapshot = load_workspace_index(path)
    projects = list(snapshot["projects"])
    if query is None or not query.strip():
        ranked = sorted(
            [((1, 1), project) for project in projects],
            key=lambda item: (item[1]["priority"], item[1]["name"].casefold()),
        )
    else:
        scored = [(_rank_project(query, project), project) for project in projects]
        ranked = sorted(
            [(rank, project) for rank, project in scored if rank[0] or rank[1] > 0],
            key=lambda item: (-item[0][0], -item[0][1], item[1]["priority"], item[1]["name"].casefold()),
        )
    effective_details = details or include_sources
    matches = [
        _project_projection(project, details=effective_details, include_sources=include_sources)
        for _rank, project in ranked
    ]
    return {
        "status": "matched" if matches else "no_matches",
        "index_path": str(path),
        "snapshot": {
            "generated_at": snapshot["generated_at"],
            "window": snapshot["window"],
            "partial": snapshot["partial"],
            "log_path": snapshot["log_path"],
        },
        "projects": matches,
    }

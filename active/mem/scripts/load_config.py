#!/usr/bin/env python3
"""Load and validate a .mem.yaml configuration.

The script prints normalized JSON to stdout and validation errors to stderr.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - environment issue
    yaml = None


PATH_STYLES = {"directory", "dotted"}
DEFAULT_PATH_STYLE = "directory"
MATCH_FIELDS = {"source_globs", "cwd_globs"}
AUDIT_FIELDS = {"enabled", "trace_root"}
_LOAD_FROM_PATH = object()


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(f"{field} must be a non-empty string")
    return value.strip()


def normalize_path_style(value: Any, field: str) -> str:
    path_style = non_empty_string(value, field)
    if path_style not in PATH_STYLES:
        allowed = ", ".join(sorted(PATH_STYLES))
        fail(f"{field} must be one of: {allowed}")
    return path_style


def resolve_schema_path(raw_path: str, field: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw_path))
    path = Path(expanded)
    if not path.is_absolute():
        fail(f"{field} must be an absolute path")
    return path.resolve(strict=False)


def discover_schema_path(name: str, *, config_dir: Path, home: Path) -> Path | None:
    for directory in (config_dir, *config_dir.parents):
        candidate = directory / "schemas" / name / "schema.yaml"
        if candidate.is_file():
            return candidate.resolve(strict=False)

    candidate = home.expanduser().resolve(strict=False) / ".schemas" / name / "schema.yaml"
    return candidate.resolve(strict=False) if candidate.is_file() else None


def normalize_schema(
    value: Any, field: str, *, config_dir: Path, home: Path
) -> dict[str, str]:
    if not isinstance(value, dict):
        fail(f"{field} must be a mapping with name and optional path or root")

    name = non_empty_string(value.get("name"), f"{field}.name")
    normalized = {"name": name}

    extra_keys = set(value) - {"name", "path", "root"}
    if extra_keys:
        joined = ", ".join(sorted(extra_keys))
        fail(f"{field} has unsupported key(s): {joined}")

    if "root" in value:
        raw_root = non_empty_string(value["root"], f"{field}.root")
        if "\\" in raw_root:
            fail(f"{field}.root must not contain backslashes")
        schema_root = PurePosixPath(raw_root)
        if schema_root.is_absolute():
            fail(f"{field}.root must be a relative path")
        if ".." in schema_root.parts:
            fail(f"{field}.root must not contain '..' traversal")
        normalized["root"] = str(schema_root)

    if "path" in value:
        raw_path = non_empty_string(value.get("path"), f"{field}.path")
        path = resolve_schema_path(raw_path, f"{field}.path")
        if not path.is_file():
            fail(f"{field}.path does not exist or is not a file: {path}")
        normalized["path"] = str(path)
    else:
        discovered = discover_schema_path(name, config_dir=config_dir, home=home)
        if discovered is not None:
            normalized["path"] = str(discovered)

    return normalized


def normalize_string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        fail(f"{field} must be a list")
    normalized = [non_empty_string(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if len(normalized) != len(set(normalized)):
        fail(f"{field} must not contain duplicates")
    return normalized


def normalize_match(value: Any, field: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        fail(f"{field} must be a mapping")
    extra_keys = set(value) - MATCH_FIELDS
    if extra_keys:
        joined = ", ".join(sorted(extra_keys))
        fail(f"{field} has unsupported key(s): {joined}")
    normalized: dict[str, list[str]] = {}
    for key in MATCH_FIELDS:
        if key in value:
            normalized[key] = normalize_string_list(value[key], f"{field}.{key}")
    if not normalized:
        fail(f"{field} must contain at least one routing field")
    return normalized


def nearest_config(cwd: Path) -> Path | None:
    current = cwd.expanduser().resolve(strict=False)
    for directory in (current, *current.parents):
        candidate = directory / ".mem.yaml"
        if candidate.is_file():
            return candidate
    return None


def find_config_paths(cwd: Path, home: Path) -> list[Path]:
    candidates: list[Path] = []
    nearest = nearest_config(cwd)
    if nearest is not None:
        candidates.append(nearest)
    home_config = home.expanduser().resolve(strict=False) / ".mem.yaml"
    if home_config.is_file() and home_config not in candidates:
        candidates.append(home_config)
    return candidates


def find_configs(cwd: Path, home: Path) -> list[Path]:
    candidates = find_config_paths(cwd, home)
    if candidates:
        return candidates
    home_config = home.expanduser().resolve(strict=False) / ".mem.yaml"
    expected = f"nearest ancestor of {cwd} or {home_config}"
    fail(f"missing config: expected one of: {expected}")


def resolve_root(raw_root: str, config_dir: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(raw_root))
    path = Path(expanded)
    if not path.is_absolute():
        path = config_dir / path
    return path.resolve(strict=False)


def resolve_root_pattern(pattern: Any, *, cwd: Path, field: str) -> Path | None:
    value = non_empty_string(pattern, field)
    value = os.path.expandvars(os.path.expanduser(value))
    if "\\" in value or any(part in {".", ".."} for part in value.split("/")):
        fail(f"{field} must not contain backslashes or traversal")
    is_path_pattern = "/" in value
    if is_path_pattern and (not Path(value).is_absolute() or "**" in value.split("/")):
        fail(f"{field} must be a basename glob or absolute path glob without '**'")
    current = cwd.expanduser().resolve(strict=False)
    for directory in (current, *current.parents):
        matches = (
            directory.match(value)
            if is_path_pattern
            else fnmatch.fnmatchcase(directory.name, value)
        )
        if matches:
            return directory
    return None


def default_audit(home: Path) -> dict[str, Any]:
    trace_root = home.expanduser().resolve(strict=False) / ".config" / "mem" / "traces"
    return {"enabled": False, "trace_root": str(trace_root)}


def normalize_audit(value: Any, field: str, config_dir: Path, home: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{field} must be a mapping")
    extra_keys = set(value) - AUDIT_FIELDS
    if extra_keys:
        joined = ", ".join(sorted(extra_keys))
        fail(f"{field} has unsupported key(s): {joined}")

    normalized = default_audit(home)
    if "enabled" in value:
        enabled = value["enabled"]
        if not isinstance(enabled, bool):
            fail(f"{field}.enabled must be a boolean")
        normalized["enabled"] = enabled
    if "trace_root" in value:
        raw_trace_root = non_empty_string(value["trace_root"], f"{field}.trace_root")
        expanded = os.path.expandvars(os.path.expanduser(raw_trace_root))
        if "$" in expanded:
            fail(f"{field}.trace_root contains an unresolved environment variable")
        normalized["trace_root"] = str(resolve_root(raw_trace_root, config_dir))
    return normalized


def resolve_managed_root(
    raw_managed_root: Any,
    *,
    root: Path,
    field: str,
    require_roots: bool,
) -> Path:
    if raw_managed_root is None:
        return root
    value = non_empty_string(raw_managed_root, field)
    relative = Path(value)
    if relative.is_absolute():
        fail(f"{field} must be relative to root")
    if ".." in relative.parts:
        fail(f"{field} must not contain '..' traversal")
    managed_root = (root / relative).resolve(strict=False)
    if not managed_root.is_relative_to(root):
        fail(f"{field} resolves outside root: {managed_root}")
    if require_roots and not managed_root.is_dir():
        fail(f"{field} does not exist or is not a directory: {managed_root}")
    return managed_root


def infer_path_style(root: Path) -> str:
    if not root.is_dir():
        return DEFAULT_PATH_STYLE

    dotted_signals = 0
    directory_signals = 0
    scanned = 0
    for path in root.rglob("*.md"):
        if not path.is_file():
            continue
        scanned += 1
        if path.parent == root and "." in path.stem:
            dotted_signals += 1
        elif path.parent != root:
            directory_signals += 1
        if scanned >= 500:
            break

    if dotted_signals > directory_signals:
        return "dotted"
    if directory_signals > dotted_signals:
        return "directory"
    return DEFAULT_PATH_STYLE


def load_yaml(path: Path) -> Any:
    if yaml is None:
        fail("PyYAML is required to parse .mem.yaml")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        fail(f"invalid YAML in {path}: {exc}")
    except OSError as exc:
        fail(f"could not read {path}: {exc}")


def normalize_config(
    path: Path,
    require_roots: bool,
    *,
    home: Path,
    cwd: Path | None = None,
    raw_data: Any = _LOAD_FROM_PATH,
) -> tuple[dict[str, Any], bool]:
    data = load_yaml(path) if raw_data is _LOAD_FROM_PATH else raw_data
    if not isinstance(data, dict):
        fail("config must be a YAML mapping")
    version = data.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version == 1:
        fail("version 1 is no longer supported; run mem doctor --migrate")
    if not isinstance(version, int) or isinstance(version, bool) or version != 2:
        fail("version must be 2")

    bases = data.get("bases")
    if not isinstance(bases, list) or not bases:
        fail("bases must be a non-empty list")

    normalized_bases: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, base in enumerate(bases):
        label = f"bases[{index}]"
        if not isinstance(base, dict):
            fail(f"{label} must be a mapping")
        if "schema" in base:
            fail(f"{label}.schema is not supported; use {label}.schemas")

        name = non_empty_string(base.get("name"), f"{label}.name")
        if name in seen_names:
            fail(f"duplicate base name: {name}")
        seen_names.add(name)

        description = non_empty_string(base.get("description"), f"{label}.description")
        has_root = "root" in base
        has_root_pattern = "root_pattern" in base
        if has_root == has_root_pattern:
            fail(f"{label} must define exactly one of root or root_pattern")
        if has_root_pattern:
            root = resolve_root_pattern(
                base["root_pattern"], cwd=cwd or Path.cwd(), field=f"{label}.root_pattern"
            )
            if root is None:
                continue
        else:
            raw_root = non_empty_string(base["root"], f"{label}.root")
            root = resolve_root(raw_root, path.parent)
        if require_roots and not root.is_dir():
            fail(f"{label}.root does not exist or is not a directory: {root}")
        managed_root = resolve_managed_root(
            base.get("managed_root"),
            root=root,
            field=f"{label}.managed_root",
            require_roots=require_roots,
        )

        schemas = base.get("schemas")
        if not isinstance(schemas, list) or not schemas:
            fail(f"{label}.schemas must be a non-empty list")
        normalized_schemas = [
            normalize_schema(
                schema,
                f"{label}.schemas[{schema_index}]",
                config_dir=path.parent,
                home=home,
            )
            for schema_index, schema in enumerate(schemas)
        ]
        if "path_style" in base:
            path_style = normalize_path_style(base["path_style"], f"{label}.path_style")
        else:
            path_style = infer_path_style(managed_root)

        normalized: dict[str, Any] = {
            "name": name,
            "description": description,
            "root": str(root),
            "managed_root": str(managed_root),
            "index_path": str(managed_root / ".mem.index.json"),
            "path_style": path_style,
            "schemas": normalized_schemas,
            "config_path": str(path),
        }
        if has_root_pattern:
            normalized["root_pattern"] = base["root_pattern"].strip()
        if "skill" in base:
            normalized["skill"] = non_empty_string(base.get("skill"), f"{label}.skill")
        if "aliases" in base:
            normalized["aliases"] = normalize_string_list(base["aliases"], f"{label}.aliases")
        if "match" in base:
            normalized["match"] = normalize_match(base["match"], f"{label}.match")
        if "priority" in base:
            priority = base["priority"]
            if not isinstance(priority, int) or isinstance(priority, bool):
                fail(f"{label}.priority must be an integer")
            normalized["priority"] = priority
        normalized_bases.append(normalized)

    normalized_config = {
        "config_path": str(path),
        "version": 2,
        "bases": normalized_bases,
        "audit": default_audit(home),
    }
    audit_declared = "audit" in data
    if audit_declared:
        normalized_config["audit"] = normalize_audit(data["audit"], "audit", path.parent, home)
    return normalized_config, audit_declared


def merge_configs(
    paths: list[Path],
    require_roots: bool,
    *,
    home: Path,
    cwd: Path | None = None,
    raw_configs: dict[Path, Any] | None = None,
) -> dict[str, Any]:
    normalized_configs = [
        normalize_config(
            path,
            require_roots,
            home=home,
            cwd=cwd,
            raw_data=raw_configs[path] if raw_configs is not None else _LOAD_FROM_PATH,
        )
        for path in paths
    ]
    merged_bases: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for config, _ in normalized_configs:
        for base in config["bases"]:
            if base["name"] in seen_names:
                continue
            seen_names.add(base["name"])
            merged_bases.append(base)

    label_owners: dict[str, str] = {}
    for base in merged_bases:
        for label in (base["name"], *base.get("aliases", [])):
            owner = label_owners.get(label)
            if owner is not None:
                fail(f"base name/alias collision: {label} ({owner}, {base['name']})")
            label_owners[label] = base["name"]
    audit = default_audit(home)
    for config, audit_declared in normalized_configs:
        if audit_declared:
            audit = config["audit"]
            break
    return {
        "config_path": str(paths[0]),
        "config_paths": [str(path) for path in paths],
        "version": 2,
        "bases": merged_bases,
        "audit": audit,
    }


def load_config(
    *,
    cwd: Path,
    home: Path,
    config: Path | None = None,
    require_roots: bool = True,
) -> dict[str, Any]:
    paths = [config.expanduser().resolve(strict=False)] if config else find_configs(cwd, home)
    for path in paths:
        if not path.is_file():
            fail(f"config does not exist: {path}")
    return merge_configs(paths, require_roots, home=home, cwd=cwd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        help="Use only this .mem.yaml instead of merging nearest and home configs.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Current directory whose nearest ancestor config should be loaded.",
    )
    parser.add_argument("--home", type=Path, default=Path.home(), help="Home directory to search.")
    parser.add_argument(
        "--allow-missing-roots",
        action="store_true",
        help="Parse and normalize config without requiring base roots to exist.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized = load_config(
        cwd=args.cwd,
        home=args.home,
        config=args.config,
        require_roots=not args.allow_missing_roots,
    )
    json.dump(normalized, sys.stdout, indent=2 if args.pretty else None)
    print()


if __name__ == "__main__":
    main()

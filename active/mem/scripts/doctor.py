#!/usr/bin/env python3
"""Safely migrate discovered memory-base configurations to the current schema."""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
import stat
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any

import load_config


RETIRED_MATCH_FIELDS = ("topics", "artifact_kinds")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate",
        action="store_true",
        required=True,
        help="Migrate discovered version-1 configurations to version 2.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Use only this .mem.yaml instead of merging nearest and home configs.",
    )
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def discover_configs(args: argparse.Namespace) -> list[Path]:
    paths = (
        [args.config.expanduser().resolve(strict=False)]
        if args.config is not None
        else load_config.find_configs(args.cwd, args.home)
    )
    for path in paths:
        if not path.is_file():
            load_config.fail(f"config does not exist: {path}")
    return paths


def transform_config(path: Path, raw_data: Any) -> tuple[dict[str, Any], int, int]:
    if not isinstance(raw_data, dict):
        load_config.fail(f"config must be a YAML mapping: {path}")

    version = raw_data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version not in (1, 2):
        load_config.fail(f"config version must be integer 1 or 2: {path}")
    if version == 2:
        return raw_data, version, 0

    transformed = copy.deepcopy(raw_data)
    transformed["version"] = 2
    removed_fields = 0
    bases = transformed.get("bases")
    if isinstance(bases, list):
        for index, base in enumerate(bases):
            if not isinstance(base, dict) or "match" not in base:
                continue
            match = base["match"]
            if not isinstance(match, dict):
                load_config.fail(f"bases[{index}].match must be a mapping: {path}")
            for field in RETIRED_MATCH_FIELDS:
                if field in match:
                    del match[field]
                    removed_fields += 1
            if not any(field in match for field in load_config.MATCH_FIELDS):
                if match:
                    joined = ", ".join(sorted(str(field) for field in match))
                    load_config.fail(f"bases[{index}].match has unsupported key(s): {joined}")
                del base["match"]

    return transformed, version, removed_fields


def write_config_atomically(path: Path, data: dict[str, Any]) -> None:
    if load_config.yaml is None:
        raise RuntimeError("PyYAML is required to write .mem.yaml")

    original_mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.fchmod(handle.fileno(), original_mode)
            load_config.yaml.safe_dump(
                data,
                handle,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def migrate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = discover_configs(args)
    transformed_configs: dict[Path, dict[str, Any]] = {}
    plans: list[dict[str, Any]] = []

    for path in paths:
        raw_data = load_config.load_yaml(path)
        transformed, from_version, removed_fields = transform_config(path, raw_data)
        transformed_configs[path] = transformed
        plans.append(
            {
                "config_path": str(path),
                "from_version": from_version,
                "to_version": 2,
                "removed_fields": removed_fields,
            }
        )

    load_config.merge_configs(
        paths, True, home=args.home, cwd=args.cwd, raw_configs=transformed_configs
    )

    results: list[dict[str, Any]] = []
    failures = False
    for path, plan in zip(paths, plans):
        result = dict(plan)
        if plan["from_version"] == 2:
            result["status"] = "unchanged"
        else:
            try:
                write_config_atomically(path, transformed_configs[path])
            except (OSError, RuntimeError) as exc:
                result["status"] = "error"
                result["error"] = str(exc)
                failures = True
            else:
                result["status"] = "migrated"
        results.append(result)

    payload: dict[str, Any] = {
        "mode": "doctor_migrate",
        "status": "error" if failures else "ok",
        "config_paths": [str(path) for path in paths],
        "results": results,
    }

    if not failures:
        captured_errors = io.StringIO()
        try:
            with redirect_stderr(captured_errors):
                load_config.load_config(cwd=args.cwd, home=args.home, config=args.config)
        except SystemExit:
            payload["status"] = "error"
            payload["error"] = (
                captured_errors.getvalue().strip() or "final strict configuration reload failed"
            )
            failures = True

    return payload, 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        payload, exit_code = migrate(args)
    except SystemExit as exc:
        if exc.code == 0:
            return 0
        return 2

    json.dump(payload, sys.stdout, indent=2 if args.pretty else None)
    print()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

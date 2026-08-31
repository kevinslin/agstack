#!/usr/bin/env python3
"""Build, inspect, and verify structured indexes for configured memory bases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from base_index import BaseIndexError, build_index, check_index, read_index
from load_config import load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mem index", description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    for mode in ("build", "show", "check"):
        subcommand = subcommands.add_parser(mode)
        if mode == "show":
            subcommand.add_argument("--base", required=True)
        else:
            selection = subcommand.add_mutually_exclusive_group(required=True)
            selection.add_argument("--base")
            selection.add_argument("--all", action="store_true")
        subcommand.add_argument("--config", type=Path)
        subcommand.add_argument("--cwd", type=Path, default=Path.cwd())
        subcommand.add_argument("--home", type=Path, default=Path.home())
        subcommand.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def selected_bases(config: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "all", False):
        return list(config["bases"])
    for base in config["bases"]:
        if args.base == base["name"] or args.base in base.get("aliases", []):
            return [base]
    available = ", ".join(base["name"] for base in config["bases"])
    print(f"error: unknown base {args.base!r}; available bases: {available}", file=sys.stderr)
    raise SystemExit(2)


def validate_index_paths(bases: list[dict[str, Any]]) -> None:
    for base in bases:
        managed_root = Path(base["managed_root"]).resolve(strict=False)
        index_path = Path(base["index_path"])
        expected_path = managed_root / ".mem.index.json"
        if index_path != expected_path or index_path.is_symlink():
            print(
                f"error: unsafe index path for base {base['name']!r}: {index_path}",
                file=sys.stderr,
            )
            raise SystemExit(2)


def empty_result(base: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "base": base["name"],
        "index_path": base["index_path"],
        "status": status,
        "document_count": None,
        "source_fingerprint": None,
        "changed": False,
    }


def summarize_result(base: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "base": base["name"],
        "index_path": summary["index_path"],
        "status": summary["status"],
        "document_count": summary["document_count"],
        "source_fingerprint": summary["source_fingerprint"],
        "changed": summary["changed"],
    }


def process_base(mode: str, base: dict[str, Any]) -> dict[str, Any]:
    try:
        if mode == "build":
            return summarize_result(base, build_index(base))
        if mode == "check":
            return summarize_result(base, check_index(base))

        index = read_index(base)
        result = {
            "base": base["name"],
            "index_path": base["index_path"],
            "status": "loaded",
            "document_count": index["document_count"],
            "source_fingerprint": index["source_fingerprint"],
            "changed": False,
            "index": index,
        }
        return result
    except BaseIndexError as exc:
        status = "error"
        if mode in {"show", "check"} and exc.kind == "missing":
            status = "missing"
        elif mode in {"show", "check"} and exc.kind in {"invalid", "unsupported"}:
            status = "invalid"
        result = empty_result(base, status=status)
        result["error"] = str(exc)
        return result
    except OSError as exc:
        result = empty_result(base, status="error")
        result["error"] = str(exc)
        return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(cwd=args.cwd, home=args.home, config=args.config)
    except SystemExit:
        return 2

    bases = selected_bases(config, args)
    validate_index_paths(bases)
    results = [process_base(args.mode, base) for base in bases]
    healthy_statuses = {
        "build": {"created", "updated", "unchanged"},
        "show": {"loaded"},
        "check": {"current"},
    }
    successful = all(result["status"] in healthy_statuses[args.mode] for result in results)
    payload = {
        "mode": f"index_{args.mode}",
        "status": "ok" if successful else "error",
        "config_paths": config["config_paths"],
        "results": results,
    }
    json.dump(payload, sys.stdout, indent=2 if args.pretty else None)
    print()
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())

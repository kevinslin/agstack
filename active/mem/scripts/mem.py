#!/usr/bin/env python3
"""Unified entry point for memory routing and schema-backed materialization."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from load_config import load_config


SCRIPT_DIR = Path(__file__).resolve().parent


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def extract_option(args: list[str], name: str) -> str | None:
    value: str | None = None
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == name:
            if index + 1 >= len(args):
                fail(f"{name} requires a value")
            if value is not None:
                fail(f"{name} may be specified only once")
            value = args[index + 1]
            del args[index : index + 2]
            continue
        prefix = f"{name}="
        if argument.startswith(prefix):
            if value is not None:
                fail(f"{name} may be specified only once")
            value = argument[len(prefix) :]
            del args[index]
            continue
        index += 1
    return value


def extract_flag(args: list[str], name: str) -> bool:
    found = False
    while name in args:
        if found:
            fail(f"{name} may be specified only once")
        args.remove(name)
        found = True
    return found


def has_option(args: list[str], name: str) -> bool:
    prefix = f"{name}="
    return any(argument == name or argument.startswith(prefix) for argument in args)


def select_base(config: dict[str, object], target: str) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for candidate in config["bases"]:  # type: ignore[index]
        base = candidate  # type: ignore[assignment]
        aliases = base.get("aliases", [])
        if target == base["name"] or target in aliases:
            matches.append(base)
    if not matches:
        available = ", ".join(base["name"] for base in config["bases"])  # type: ignore[index]
        fail(f"unknown base {target!r}; available bases: {available}")
    return matches[0]


def managed_destination(managed_root: str, root_relative: str | None) -> Path:
    base_root = Path(managed_root).expanduser().resolve(strict=False)
    if root_relative is None:
        return base_root
    relative = Path(root_relative)
    if relative.is_absolute():
        fail("--root-relative must be relative to the selected managed root")
    destination = (base_root / relative).resolve(strict=False)
    if not destination.is_relative_to(base_root):
        fail("--root-relative resolves outside the selected managed root")
    return destination


def run_python(script_name: str, args: list[str]) -> None:
    script = SCRIPT_DIR / script_name
    os.execvp(sys.executable, [sys.executable, str(script), *args])


def run_schema(args: list[str]) -> None:
    script = SCRIPT_DIR / "schema.py"
    os.execvp("uv", ["uv", "run", "--script", str(script), *args])


def prepare_schema_args(args: list[str]) -> list[str]:
    if not args or args[0] != "materialize":
        return args

    prepared = list(args)
    base_name = extract_option(prepared, "--base")
    root_relative = extract_option(prepared, "--root-relative")
    config_path = extract_option(prepared, "--config")
    cwd_value = extract_option(prepared, "--cwd")
    home_value = extract_option(prepared, "--home")
    unmanaged = extract_flag(prepared, "--unmanaged")
    has_out = has_option(prepared, "--out")
    has_path_style = has_option(prepared, "--path-style")
    has_schema_path = has_option(prepared, "--schema-path")

    if base_name:
        if unmanaged:
            fail("--base and --unmanaged are mutually exclusive")
        if has_out:
            fail("managed materialization derives --out from --base; remove --out")
        if has_path_style:
            fail("managed materialization derives --path-style from --base")
        if has_schema_path:
            fail("managed materialization derives --schema-path from the base configuration")
        cwd = Path(cwd_value).expanduser() if cwd_value else Path.cwd()
        home = Path(home_value).expanduser() if home_value else Path.home()
        config = load_config(
            cwd=cwd,
            home=home,
            config=Path(config_path) if config_path else None,
        )
        base = select_base(config, base_name)
        schema_name = prepared[1] if len(prepared) > 1 else ""
        configured_schema = next(
            (
                schema
                for schema in base["schemas"]  # type: ignore[union-attr]
                if schema["name"] == schema_name
            ),
            None,
        )
        if configured_schema is None:
            configured_names = ", ".join(
                schema["name"] for schema in base["schemas"]  # type: ignore[union-attr]
            )
            fail(
                f"schema {schema_name!r} is not configured for base {base_name!r}; "
                f"configured schemas: {configured_names}"
            )
        destination = managed_destination(str(base["managed_root"]), root_relative)
        if "path" in configured_schema:
            prepared.extend(["--schema-path", str(configured_schema["path"])])
        prepared.extend(
            [
                "--out",
                str(destination),
                "--path-style",
                str(base["path_style"]),
            ]
        )
        return prepared

    if root_relative is not None:
        fail("--root-relative requires --base")
    if config_path or cwd_value or home_value:
        fail("--config, --cwd, and --home apply only to managed --base materialization")
    if has_out and not unmanaged:
        fail("explicit --out requires --unmanaged")
    if not has_out:
        fail("materialize requires --base or explicit --out with --unmanaged")
    return prepared


def usage() -> str:
    return """usage:
  mem.py config show [load_config options]
  mem.py context lookup --query <text> [context options]
  mem.py route [route options]
  mem.py context lookup [context options]
  mem.py schema <list|show|describe|validate|materialize> [schema options]

Managed schema materialization:
  mem.py schema materialize <schema> --base <base> [--root-relative <path>] ...

Explicit non-memory materialization:
  mem.py schema materialize <schema> --out <path> --unmanaged ...
"""


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print(usage())
        return

    command, command_args = args[0], args[1:]
    if command == "config":
        if not command_args or command_args[0] != "show":
            fail("config requires the 'show' subcommand")
        run_python("load_config.py", command_args[1:])
    if command == "context":
        if not command_args or command_args[0] != "lookup":
            fail("context requires the 'lookup' subcommand")
        from context import main as run_context

        context_args = command_args[1:]
        run_context(
            context_args,
            command_argv=[
                sys.executable,
                str(Path(__file__).resolve()),
                "context",
                "lookup",
                *context_args,
            ],
        )
        return
    if command == "route":
        run_python("route.py", command_args)
    if command == "schema":
        run_schema(prepare_schema_args(command_args))
    fail(f"unknown command: {command}")


if __name__ == "__main__":
    main()

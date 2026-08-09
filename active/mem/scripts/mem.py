#!/usr/bin/env python3
"""Unified entry point for memory routing and schema-backed materialization."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from load_config import load_config


SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class PreparedSchemaCommand:
    args: list[str]
    base: dict[str, Any] | None = None
    base_name: str | None = None
    config_controls: tuple[tuple[str, str], ...] = ()


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


def run_managed_schema(command: PreparedSchemaCommand) -> int:
    script = SCRIPT_DIR / "schema.py"
    child = subprocess.run(["uv", "run", "--script", str(script), *command.args], check=False)
    if child.returncode != 0:
        return child.returncode

    assert command.base is not None
    assert command.base_name is not None
    try:
        from base_index import build_index

        build_index(command.base)
    except Exception as exc:
        repair_argv = [sys.argv[0], "index", "build", "--base", command.base_name]
        for option, value in command.config_controls:
            repair_argv.extend([option, value])
        warning = {
            "level": "warning",
            "code": "index_refresh_failed",
            "base": command.base_name,
            "index_path": str(command.base["index_path"]),
            "error": str(exc),
            "repair_argv": repair_argv,
        }
        print(json.dumps(warning, separators=(",", ":")), file=sys.stderr)
    return 0


def prepare_schema_args(args: list[str]) -> PreparedSchemaCommand:
    if not args or args[0] != "materialize":
        return PreparedSchemaCommand(args=args)

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
        controls = tuple(
            (name, value)
            for name, value in (
                ("--config", config_path),
                ("--cwd", cwd_value),
                ("--home", home_value),
            )
            if value is not None
        )
        return PreparedSchemaCommand(
            args=prepared,
            base=base,
            base_name=base_name,
            config_controls=controls,
        )

    if root_relative is not None:
        fail("--root-relative requires --base")
    if config_path or cwd_value or home_value:
        fail("--config, --cwd, and --home apply only to managed --base materialization")
    if has_out and not unmanaged:
        fail("explicit --out requires --unmanaged")
    if not has_out:
        fail("materialize requires --base or explicit --out with --unmanaged")
    return PreparedSchemaCommand(args=prepared)


def usage() -> str:
    return """usage:
  mem.py config show [load_config options]
  mem.py context lookup --query <text> [context options]
  mem.py route [route options]
  mem.py context lookup [context options]
  mem.py doctor --migrate [--config <path>] [--cwd <path>] [--home <path>]
  mem.py index build (--base <base> | --all) [configuration options]
  mem.py index show --base <base> [configuration options]
  mem.py index check (--base <base> | --all) [configuration options]
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
    if command == "doctor":
        from doctor import main as run_doctor

        raise SystemExit(run_doctor(command_args))
    if command == "index":
        from index_cli import main as run_index

        raise SystemExit(run_index(command_args))
    if command == "schema":
        prepared = prepare_schema_args(command_args)
        if prepared.base is not None:
            raise SystemExit(run_managed_schema(prepared))
        run_schema(prepared.args)
    fail(f"unknown command: {command}")


if __name__ == "__main__":
    main()

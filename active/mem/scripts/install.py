#!/usr/bin/env python3
"""Install the mem command launcher into a local bin directory."""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import stat
import sys
import tempfile
from pathlib import Path
from shutil import which


MARKER = "# Installed by active/mem/scripts/install.py"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=DEFAULT_BIN_DIR,
        help="Directory where the mem launcher should be installed.",
    )
    return parser.parse_args(argv)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def launcher_source(*, interpreter: Path, mem_script: Path) -> str:
    return "\n".join(
        [
            "#!/bin/sh",
            MARKER,
            "",
            f"exec {shlex.quote(str(interpreter))} {shlex.quote(str(mem_script))} \"$@\"",
            "",
        ]
    )


def is_owned_launcher(path: Path) -> bool:
    try:
        if not path.is_file() or path.is_symlink():
            return False
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline()
            second = handle.readline()
    except (OSError, UnicodeDecodeError):
        return False
    return first.startswith("#!") and second.rstrip("\n") == MARKER


def ensure_safe_destination(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        fail(f"cannot inspect existing launcher {path}: {exc}")

    if is_owned_launcher(path):
        return
    fail(f"refusing to overwrite unrelated existing path: {path}")


def install_launcher(destination: Path, source: str) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(f"cannot create bin directory {destination.parent}: {exc}")
    if not destination.parent.is_dir():
        fail(f"bin directory is not a directory: {destination.parent}")
    ensure_safe_destination(destination)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(source)
        temp_path.chmod(
            stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IXOTH
        )
        temp_path.replace(destination)
    except Exception:
        with contextlib.suppress(OSError):
            temp_path.unlink()
        raise


def path_contains(directory: Path) -> bool:
    target = directory.resolve(strict=False)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        if Path(entry).expanduser().resolve(strict=False) == target:
            return True
    return False


def bound_interpreter() -> Path:
    if not sys.executable:
        fail("cannot determine the current Python interpreter")
    interpreter = Path(sys.executable).expanduser()
    if interpreter.is_absolute():
        return interpreter
    found = which(sys.executable)
    if found is None:
        fail(f"cannot locate Python interpreter: {sys.executable}")
    return Path(found)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bin_dir = args.bin_dir.expanduser().resolve(strict=False)
    destination = bin_dir / "mem"
    mem_script = (Path(__file__).resolve().parent / "mem.py").resolve(strict=False)
    interpreter = bound_interpreter()
    install_launcher(destination, launcher_source(interpreter=interpreter, mem_script=mem_script))

    print(f"installed: {destination}")
    if not path_contains(bin_dir):
        print(f"PATH does not include: {bin_dir}")
        print(f"Add it for this shell with: export PATH={shlex.quote(str(bin_dir))}:$PATH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

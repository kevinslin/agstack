#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parent.parent
    source_root = skill_root.parent.parent.parent
    proof_root = source_root / ".integ" / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    current_numbers = [
        int(path.name)
        for path in proof_root.iterdir()
        if path.is_dir() and path.name.isdigit()
    ]
    next_number = max(current_numbers, default=0) + 1
    target = proof_root / str(next_number)
    target.mkdir(parents=True, exist_ok=False)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

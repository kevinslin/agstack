#!/usr/bin/env python3
"""Validate a fresh, explicit simplification verdict for a feature specification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


VERDICTS = {
    "changes-proposed",
    "no-meaningful-simplification",
    "user-deferred",
}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_strings(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(
        _nonempty_string(item) for item in value
    )


def validate(
    spec_path: Path,
    review_path: Path,
    *,
    phase: str = "final",
    max_lines: int = 150,
) -> list[str]:
    errors: list[str] = []

    try:
        spec_bytes = spec_path.read_bytes()
    except OSError as error:
        return [f"Cannot read specification: {error}"]

    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"Cannot read simplification review JSON: {error}"]

    if not isinstance(review, dict):
        return ["Simplification review must be a JSON object"]

    if review.get("review_kind") != "simplify-spec":
        errors.append("Review must identify itself as an independent simplify-spec pass")

    if not _nonempty_string(review.get("reviewer")):
        errors.append("Review must identify its reviewer")

    reviewed_path = review.get("spec_path")
    if not _nonempty_string(reviewed_path):
        errors.append("Review must identify the exact specification path")
    elif Path(reviewed_path).resolve() != spec_path.resolve():
        errors.append("Review belongs to a different specification")

    current_digest = hashlib.sha256(spec_bytes).hexdigest()
    if review.get("spec_sha256") != current_digest:
        errors.append("Simplification review is stale; review the current specification again")

    if not _nonempty_string(review.get("smallest_viable_implementation")):
        errors.append("Review must describe the smallest viable implementation")

    if not _nonempty_strings(review.get("keep")):
        errors.append("Review must list the capabilities and invariants to preserve")

    if not _nonempty_strings(review.get("tradeoffs")):
        errors.append("Review must state concrete simplification tradeoffs")

    verdict = review.get("verdict")
    if verdict not in VERDICTS:
        errors.append("Review must provide an explicit supported simplification verdict")
    elif verdict == "changes-proposed":
        if not _nonempty_strings(review.get("remove_or_defer")):
            errors.append("Proposed simplifications must identify what to remove or defer")
        if phase == "final":
            errors.append("Unresolved simplification proposals block specification completion")
    elif verdict == "no-meaningful-simplification":
        if not _nonempty_string(review.get("no_changes_rationale")):
            errors.append("A no-change verdict requires an evidence-backed explanation")
    elif verdict == "user-deferred":
        if not _nonempty_strings(review.get("remove_or_defer")):
            errors.append("Deferred simplifications must identify what was deferred")
        if not _nonempty_string(review.get("user_decision")):
            errors.append("Deferred simplifications require an explicit user decision")

    line_count = len(spec_bytes.splitlines())
    if (
        line_count > max_lines
        and not _nonempty_string(review.get("line_limit_justification"))
        and (phase == "final" or verdict != "changes-proposed")
    ):
        errors.append(
            f"Specification has {line_count} lines; exceeding {max_lines} "
            "requires explicit justification"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--phase", choices=("review", "final"), default="final")
    parser.add_argument("--max-lines", type=int, default=150)
    arguments = parser.parse_args()

    if arguments.max_lines < 1:
        parser.error("--max-lines must be positive")

    errors = validate(
        arguments.spec,
        arguments.review,
        phase=arguments.phase,
        max_lines=arguments.max_lines,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"PASS: fresh {arguments.phase} simplification review for {arguments.spec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

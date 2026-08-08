#!/usr/bin/env python3
"""Select a configured memory base and explain the routing decision."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

from load_config import load_config


GENERIC_WORDS = {
    "and",
    "at",
    "base",
    "docs",
    "for",
    "knowledge",
    "notes",
    "openai",
    "project",
    "references",
    "related",
    "rooted",
    "specifications",
    "specs",
    "tasks",
    "workspace",
}
ARTIFACT_WORDS = {
    "cookbook",
    "decision",
    "finding",
    "findings",
    "guide",
    "lesson",
    "lessons",
    "reference",
    "report",
    "research",
    "runbook",
    "spec",
}


def normalized_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def compact(value: str) -> str:
    return "".join(normalized_words(value))


def phrase_matches(query: str, phrase: str) -> bool:
    query_lower = query.lower()
    phrase_lower = phrase.lower()
    if phrase_lower in query_lower:
        return True
    phrase_compact = compact(phrase)
    return len(phrase_compact) >= 5 and phrase_compact in compact(query)


def description_signals(description: str) -> list[str]:
    words = [word for word in normalized_words(description) if word not in GENERIC_WORDS]
    signals = list(dict.fromkeys(words))
    for size in (2, 3):
        signals.extend(" ".join(words[index : index + size]) for index in range(len(words) - size + 1))
    return signals


def score_query_signals(
    base: dict[str, Any],
    *,
    query: str,
    artifact_kind: str | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    aliases = base.get("aliases", [])

    for label in [base["name"], *aliases]:
        if phrase_matches(query, label):
            score += 120
            reasons.append(f"name-or-alias:{label}")

    match = base.get("match", {})
    for topic in match.get("topics", []):
        if phrase_matches(query, topic):
            score += 50
            reasons.append(f"topic:{topic}")

    requested_artifact = artifact_kind or next(
        (word for word in normalized_words(query) if word in ARTIFACT_WORDS),
        None,
    )
    if requested_artifact:
        for configured_kind in match.get("artifact_kinds", []):
            if phrase_matches(requested_artifact, configured_kind):
                score += 30
                reasons.append(f"artifact:{configured_kind}")

    if phrase_matches(query, base["description"]):
        score += 80
        reasons.append(f"description:{base['description'].lower()}")

    for signal in description_signals(base["description"]):
        if phrase_matches(query, signal):
            score += 80 if " " in signal else 3
            reasons.append(f"description:{signal}")

    return score, reasons


def path_matches(value: str, pattern: str) -> bool:
    resolved = str(Path(value).expanduser().resolve(strict=False))
    return fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(resolved, pattern)


def ownership_reasons(
    base: dict[str, Any], *, cwd: Path, source: str | list[str] | None
) -> list[str]:
    reasons: list[str] = []
    match = base.get("match", {})
    cwd_string = str(cwd.expanduser().resolve(strict=False))

    for pattern in match.get("cwd_globs", []):
        if path_matches(cwd_string, pattern):
            reasons.append(f"cwd:{pattern}")
    if cwd_string in {base["root"], base.get("managed_root", base["root"])}:
        reasons.append("cwd equals base root")

    sources = [source] if isinstance(source, str) else (source or [])
    for source_path in sources:
        for pattern in match.get("source_globs", []):
            if path_matches(source_path, pattern):
                reasons.append(f"source:{pattern}")

    return reasons


def ranked_candidate(
    base: dict[str, Any], *, score: int, reasons: list[str]
) -> dict[str, Any]:
    return {
        "name": base["name"],
        "root": base["root"],
        "managed_root": base.get("managed_root", base["root"]),
        "config_path": base["config_path"],
        "score": score,
        "priority": int(base.get("priority", 0)),
        "reasons": reasons,
    }


def sort_candidates(candidates: list[dict[str, Any]]) -> None:
    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            -candidate["priority"],
            candidate["name"],
        )
    )


def route(
    config: dict[str, Any],
    *,
    query: str,
    cwd: Path,
    source: str | list[str] | None = None,
    artifact_kind: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    if target:
        for base in config["bases"]:
            aliases = base.get("aliases", [])
            if target == base["name"]:
                candidate = ranked_candidate(base, score=10_000, reasons=["explicit base name"])
                return {
                    "status": "selected",
                    "tier": "explicit",
                    "selected": candidate,
                    "candidates": [candidate],
                    "config_paths": config["config_paths"],
                }
            if target in aliases:
                candidate = ranked_candidate(
                    base, score=9_000, reasons=[f"explicit alias:{target}"]
                )
                return {
                    "status": "selected",
                    "tier": "explicit",
                    "selected": candidate,
                    "candidates": [candidate],
                    "config_paths": config["config_paths"],
                }
        return {
            "status": "no_match",
            "tier": "explicit",
            "selected": None,
            "candidates": [],
            "config_paths": config["config_paths"],
        }

    owned: list[dict[str, Any]] = []
    for base in config["bases"]:
        reasons = ownership_reasons(base, cwd=cwd, source=source)
        if reasons:
            owned.append(ranked_candidate(base, score=len(reasons), reasons=reasons))
    if owned:
        sort_candidates(owned)
        return {
            "status": "selected" if len(owned) == 1 else "ambiguous",
            "tier": "ownership",
            "selected": owned[0] if len(owned) == 1 else None,
            "candidates": owned[:5],
            "config_paths": config["config_paths"],
        }

    ranked: list[dict[str, Any]] = []
    for base in config["bases"]:
        score, reasons = score_query_signals(
            base,
            query=query,
            artifact_kind=artifact_kind,
        )
        if score >= 0:
            ranked.append(ranked_candidate(base, score=score, reasons=reasons))
    sort_candidates(ranked)

    if not ranked:
        return {"status": "no_match", "tier": "query", "selected": None, "candidates": []}

    top = ranked[0]
    if len(ranked) == 1:
        decisive = True
        if not top["reasons"]:
            top["reasons"].append("only configured base")
    else:
        second = ranked[1]
        decisive = top["score"] > 0 and (
            top["score"] - second["score"] >= 15
            or (
                top["score"] == second["score"]
                and top["priority"] > second["priority"]
            )
        )
    return {
        "status": "selected" if decisive else "ambiguous",
        "tier": "query",
        "selected": top if decisive else None,
        "candidates": ranked[:5],
        "config_paths": config["config_paths"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="User intent or durable artifact request.")
    parser.add_argument("--target", help="Explicit base name or alias.")
    parser.add_argument(
        "--source",
        action="append",
        help="Relevant source path for source_globs matching; repeat for multiple scopes.",
    )
    parser.add_argument("--artifact-kind", help="Explicit artifact kind such as guide or runbook.")
    parser.add_argument("--config", type=Path, help="Use only this .mem.yaml.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--allow-missing-roots", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(
        cwd=args.cwd,
        home=args.home,
        config=args.config,
        require_roots=not args.allow_missing_roots,
    )
    result = route(
        config,
        query=args.query,
        cwd=args.cwd,
        source=args.source,
        artifact_kind=args.artifact_kind,
        target=args.target,
    )
    json.dump(result, sys.stdout, indent=2 if args.pretty else None)
    print()


if __name__ == "__main__":
    main()

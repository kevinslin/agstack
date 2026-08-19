#!/usr/bin/env python3
"""Select a configured memory base and explain the routing decision."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

from base_index import ensure_index
from load_config import load_config
from routing_signals import ARTIFACT_ALIASES, ARTIFACT_WORDS, GENERIC_WORDS, normalized_words


IndexState = tuple[str, dict[str, Any] | None, bool]


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
    index: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    aliases = base.get("aliases", [])

    for label in [base["name"], *aliases]:
        if phrase_matches(query, label):
            score += 120
            reasons.append(f"name-or-alias:{label}")

    metadata = index.get("metadata", {}) if index is not None else {}
    for topic in metadata.get("topics", []):
        if phrase_matches(query, topic):
            score += 50
            reasons.append(f"index-topic:{topic}")

    requested_artifact = artifact_kind or next(
        (word for word in normalized_words(query) if word in ARTIFACT_WORDS),
        None,
    )
    if requested_artifact:
        requested_kinds = ARTIFACT_ALIASES.get(requested_artifact.casefold(), (requested_artifact,))
        for configured_kind in metadata.get("artifact_kinds", []):
            if any(phrase_matches(requested_kind, configured_kind) for requested_kind in requested_kinds):
                score += 30
                reasons.append(f"index-artifact:{configured_kind}")

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
    resolved_cwd = cwd.expanduser().resolve(strict=False)
    cwd_string = str(resolved_cwd)

    for pattern in match.get("cwd_globs", []):
        if path_matches(cwd_string, pattern):
            reasons.append(f"cwd:{pattern}")
    if cwd_string in {base["root"], base.get("managed_root", base["root"])}:
        reasons.append("cwd equals base root")
    elif resolved_cwd.is_relative_to(Path(base["root"])):
        if "root_pattern" in base:
            reasons.append(f"root-pattern:{base['root_pattern']}")
        else:
            reasons.append("cwd within base root")

    sources = [source] if isinstance(source, str) else (source or [])
    for source_path in sources:
        for pattern in match.get("source_globs", []):
            if path_matches(source_path, pattern):
                reasons.append(f"source:{pattern}")

    return reasons


def ranked_candidate(
    base: dict[str, Any], *, score: int, reasons: list[str], index_status: str = "not_loaded"
) -> dict[str, Any]:
    return {
        "name": base["name"],
        "root": base["root"],
        "managed_root": base.get("managed_root", base["root"]),
        "config_path": base["config_path"],
        "score": score,
        "priority": int(base.get("priority", 0)),
        "reasons": reasons,
        "index": {"status": index_status},
    }


def ensure_base_index(
    base: dict[str, Any],
    *,
    cache: dict[str, IndexState],
    recorder: Any | None = None,
) -> IndexState:
    cached = cache.get(base["name"])
    if cached is not None:
        return cached

    span = recorder.start("load_index") if recorder is not None else None
    try:
        state = ensure_index(base)
    except Exception:
        state = ("build_failed", None, False)

    status, index, generated = state
    if span is not None and (generated or index is not None or status == "invalid"):
        if generated:
            span.name = "build_index"
        recorder.finish(span)
    cache[base["name"]] = state
    return state


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
    index_cache: dict[str, IndexState] | None = None,
    index_recorder: Any | None = None,
) -> dict[str, Any]:
    cache = index_cache if index_cache is not None else {}
    if target:
        for base in config["bases"]:
            aliases = base.get("aliases", [])
            if target == base["name"]:
                status, _, _ = ensure_base_index(base, cache=cache, recorder=index_recorder)
                candidate = ranked_candidate(
                    base, score=10_000, reasons=["explicit base name"], index_status=status
                )
                return {
                    "status": "selected",
                    "tier": "explicit",
                    "selected": candidate,
                    "candidates": [candidate],
                    "config_paths": config["config_paths"],
                }
            if target in aliases:
                status, _, _ = ensure_base_index(base, cache=cache, recorder=index_recorder)
                candidate = ranked_candidate(
                    base, score=9_000, reasons=[f"explicit alias:{target}"], index_status=status
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
        fixed_names = {
            base["name"] for base in config["bases"] if "root_pattern" not in base
        }
        fixed_owned = [candidate for candidate in owned if candidate["name"] in fixed_names]
        if fixed_owned:
            owned = fixed_owned
        sort_candidates(owned)
        if len(owned) == 1:
            selected_base = next(base for base in config["bases"] if base["name"] == owned[0]["name"])
            status, _, _ = ensure_base_index(selected_base, cache=cache, recorder=index_recorder)
            owned[0]["index"]["status"] = status
        return {
            "status": "selected" if len(owned) == 1 else "ambiguous",
            "tier": "ownership",
            "selected": owned[0] if len(owned) == 1 else None,
            "candidates": owned[:5],
            "config_paths": config["config_paths"],
        }

    ranked: list[dict[str, Any]] = []
    for base in config["bases"]:
        status, index, _ = ensure_base_index(base, cache=cache, recorder=index_recorder)
        score, reasons = score_query_signals(
            base,
            query=query,
            artifact_kind=artifact_kind,
            index=index,
        )
        if score >= 0:
            ranked.append(ranked_candidate(base, score=score, reasons=reasons, index_status=status))
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

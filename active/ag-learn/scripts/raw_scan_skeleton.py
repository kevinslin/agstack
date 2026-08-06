#!/usr/bin/env python3
"""Build a raw-scan skeleton for ag-learn from Codex rollout JSONL files."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TERMS = [
    "ag-learn",
    "trigger:",
    "$skill",
    "[$",
    "proof",
    "failed",
    "failure",
    "error",
    "review",
    "requested changes",
    "conflict",
    "rebase",
    "ci",
    "timeout",
    "blocked",
    "sandbox",
    "compacted",
]


@dataclass
class SessionMeta:
    line: int
    session_id: str | None = None
    forked_from_id: str | None = None
    parent_thread_id: str | None = None


@dataclass
class ScanResult:
    path: Path
    label: str
    total_lines: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    type_counts: dict[str, int] = field(default_factory=dict)
    compaction_lines: list[int] = field(default_factory=list)
    session_meta: list[SessionMeta] = field(default_factory=list)
    hits: list[tuple[int, str, str]] = field(default_factory=list)


def iter_rollouts(root: Path) -> Iterable[Path]:
    yield from root.glob("**/rollout-*.jsonl")


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def nested_get(data: Any, path: list[str]) -> Any:
    current = data
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def extract_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    if payload.get("arguments"):
        chunks.append(str(payload["arguments"]))
    if payload.get("output"):
        chunks.append(str(payload["output"]))
    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                chunks.append(str(item.get("text") or item.get("input_text") or item.get("output_text") or ""))
    if payload.get("message"):
        chunks.append(str(payload["message"]))
    return " ".join(chunks)


def scan_file(path: Path, label: str, pattern: re.Pattern[str], max_hits: int, snippet_chars: int) -> ScanResult:
    result = ScanResult(path=path, label=label)
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            result.total_lines = line_no
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = str(event.get("type") or "unknown")
            result.type_counts[event_type] = result.type_counts.get(event_type, 0) + 1
            timestamp = event.get("timestamp")
            if isinstance(timestamp, str):
                result.first_timestamp = result.first_timestamp or timestamp
                result.last_timestamp = timestamp

            payload = event.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            if event_type == "compacted":
                result.compaction_lines.append(line_no)

            if event_type == "session_meta":
                result.session_meta.append(
                    SessionMeta(
                        line=line_no,
                        session_id=nested_get(payload, ["payload", "id"]) or payload.get("id"),
                        forked_from_id=nested_get(payload, ["payload", "forked_from_id"])
                        or payload.get("forked_from_id"),
                        parent_thread_id=nested_get(payload, ["source", "subagent", "thread_spawn", "parent_thread_id"]),
                    )
                )

            if len(result.hits) < max_hits:
                text = extract_text(payload)
                if event_type != "response_item":
                    text = f"{text} {payload}"
                if pattern.search(text):
                    result.hits.append((line_no, event_type, truncate(text, snippet_chars)))
    return result


def path_session_ids(path: Path) -> set[str]:
    matches = re.findall(r"019[a-z0-9-]{32,}", path.name)
    return set(matches)


def resolve_rollouts(root: Path, session_id: str | None, explicit: list[str], include_related: bool) -> list[tuple[Path, str]]:
    candidates: dict[Path, str] = {}
    for raw in explicit:
        path = Path(raw).expanduser()
        candidates[path] = "explicit"

    if session_id:
        all_rollouts = list(iter_rollouts(root))
        for path in all_rollouts:
            if session_id in path.name:
                candidates[path] = "active"

        if include_related:
            parent_ids: set[str] = set()
            child_paths: set[Path] = set()
            for path in all_rollouts:
                try:
                    with path.open("r", encoding="utf-8") as handle:
                        for line in handle:
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            payload = event.get("payload")
                            payload = payload if isinstance(payload, dict) else {}
                            forked_from = nested_get(payload, ["payload", "forked_from_id"]) or payload.get("forked_from_id")
                            parent = nested_get(payload, ["source", "subagent", "thread_spawn", "parent_thread_id"])
                            sid = nested_get(payload, ["payload", "id"]) or payload.get("id")
                            if sid == session_id and isinstance(forked_from, str):
                                parent_ids.add(forked_from)
                            if forked_from == session_id or parent == session_id:
                                child_paths.add(path)
                            break
                except OSError:
                    continue
            for path in all_rollouts:
                if any(parent_id in path.name for parent_id in parent_ids):
                    candidates.setdefault(path, "parent")
            for path in child_paths:
                candidates.setdefault(path, "child")

    existing = [(path, label) for path, label in candidates.items() if path.exists()]
    return sorted(existing, key=lambda item: str(item[0]))


def format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def format_meta(items: list[SessionMeta]) -> str:
    if not items:
        return "none found"
    return "; ".join(
        f"line {item.line}: id={item.session_id or 'n/a'} forked_from={item.forked_from_id or 'n/a'} "
        f"parent_thread_id={item.parent_thread_id or 'n/a'}"
        for item in items
    )


def render(results: list[ScanResult], terms: list[str]) -> str:
    lines: list[str] = [
        "## Raw Scan Coverage",
    ]
    for result in results:
        compactions = ", ".join(str(line) for line in result.compaction_lines) or "none"
        lines.append(
            f"- {result.label}: `{result.path}` lines 1-{result.total_lines} scanned line by line; "
            f"timestamps {result.first_timestamp or 'unknown'}..{result.last_timestamp or 'unknown'}; "
            f"compaction lines {compactions}; session_meta {format_meta(result.session_meta)}; "
            f"type counts {format_counts(result.type_counts)}."
        )
    lines.extend(
        [
            f"- search terms: {', '.join(f'`{term}`' for term in terms)}",
            "- known gaps: fill in any skipped parent/forked sessions, blocked reads, or artifacts not inspected.",
            "",
            "## Source Of Truth Inventory",
            "- controlling user instructions: TODO",
            "- shortcuts/skills read: TODO",
            "- specs/docs/PR/review artifacts: TODO",
            "- canonical-vs-stale conflicts: TODO",
            "",
            "## Evidence Hits Sample",
        ]
    )
    for result in results:
        if not result.hits:
            lines.append(f"- `{result.path}`: no term hits captured.")
            continue
        lines.append(f"- `{result.path}`:")
        for line_no, event_type, snippet in result.hits:
            lines.append(f"  - line {line_no} `{event_type}`: {snippet}")
    lines.extend(
        [
            "",
            "## 1. TODO finding name",
            "- summary: TODO",
            "- citation: TODO",
            "- related: TODO",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit an ag-learn Pass 1 raw-scan skeleton.")
    parser.add_argument("--session-id", help="Codex session id to locate under --sessions-root")
    parser.add_argument("--rollout", action="append", default=[], help="Explicit rollout JSONL path; repeatable")
    parser.add_argument(
        "--sessions-root",
        default=os.path.expanduser("~/.codex/sessions"),
        help="Root containing Codex rollout JSONL files",
    )
    parser.add_argument("--term", action="append", help="Supplemental evidence search term; repeatable")
    parser.add_argument("--max-hits-per-file", type=int, default=40)
    parser.add_argument("--snippet-chars", type=int, default=260)
    parser.add_argument("--output", help="Write markdown to this path instead of stdout")
    parser.add_argument(
        "--no-related",
        action="store_true",
        help="Do not scan direct parent/child rollout relationships when --session-id is provided",
    )
    args = parser.parse_args()

    if not args.session_id and not args.rollout:
        print("provide --session-id or at least one --rollout", file=sys.stderr)
        return 2

    terms = args.term or DEFAULT_TERMS
    pattern = re.compile("|".join(re.escape(term) for term in terms), re.IGNORECASE)
    rollouts = resolve_rollouts(Path(args.sessions_root).expanduser(), args.session_id, args.rollout, not args.no_related)
    if not rollouts:
        print("no rollout files found", file=sys.stderr)
        return 1

    results = [
        scan_file(path, label, pattern, max(0, args.max_hits_per_file), max(40, args.snippet_chars))
        for path, label in rollouts
    ]
    output = render(results, terms)
    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect native user work from local Codex rollout stores."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROLLOUT_ROOTS = ("sessions", "archived_sessions")
MAX_ROLLOUT_FILES = 20_000
MAX_TEXT_CHARS = 8_000
NOISY_SUBSTRINGS = (
    "<codex_delegation>",
    "<recommended_plugins>",
    "<environment_context>",
    "AGENTS.md instructions for",
    "You are Codex, a coding agent",
    "You are an agent in a team of agents",
)
GENERATED_PROMPT_PATTERNS = (
    re.compile(r"\A\s*mem workspace build\s*:", re.IGNORECASE),
    re.compile(r"\A\s*build\b.*\bworkspace index\b.*\b(output[- ]schema|constrained json|synthesis)\b", re.IGNORECASE | re.DOTALL),
)
BRIEF_WORD_LIMIT = 24


@dataclass(frozen=True)
class _Candidate:
    task_id: str
    path: str
    line: int
    occurred_at: datetime
    cwd: str
    text: str
    message_id: str | None


@dataclass
class _TurnState:
    started_at: datetime | None = None
    cwd: str | None = None


def collect_work(codex_home: Path, start: datetime, end: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    """Return native user task-intent excerpts from Codex rollout JSONL files.

    The returned activity dictionaries contain only stable source coordinates and
    user text. Native message and turn identifiers are used only while scanning
    to deduplicate inherited fork history.
    """

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start and end must be timezone-aware datetimes")
    if start >= end:
        raise ValueError("start must be before end")

    home = codex_home.expanduser()
    if not home.is_dir():
        raise ValueError(f"codex_home is not a directory: {home}")

    warnings: list[str] = []
    candidates: list[_Candidate] = []
    roots_scanned = 0
    files_attempted = 0
    files_failed = 0
    for root_name in ROLLOUT_ROOTS:
        root = home / root_name
        if not root.exists():
            warnings.append(f"missing rollout root: {root}")
            continue
        if not root.is_dir():
            warnings.append(f"rollout root is not a directory: {root}")
            continue
        try:
            files, stat_failures = _rollout_files_newest_first(root, warnings)
        except OSError as exc:
            warnings.append(f"failed to scan rollout root {root}: {exc}")
            continue
        files_attempted += stat_failures
        files_failed += stat_failures
        roots_scanned += 1
        if len(files) > MAX_ROLLOUT_FILES:
            warnings.append(
                f"partial scan: {root} has {len(files)} rollout files; scanned newest {MAX_ROLLOUT_FILES}"
            )
            files = files[:MAX_ROLLOUT_FILES]
        for path in files:
            files_attempted += 1
            try:
                file_candidates, file_warnings = _collect_file(path, start, end)
            except OSError as exc:
                files_failed += 1
                warnings.append(f"failed to read rollout file {path}: {exc}")
                continue
            except json.JSONDecodeError as exc:
                files_failed += 1
                warnings.append(f"failed to parse rollout file {path}: line {exc.lineno}: {exc.msg}")
                continue
            candidates.extend(file_candidates)
            warnings.extend(file_warnings)

    if roots_scanned == 0:
        raise RuntimeError(f"no readable rollout roots under {home}")
    if files_attempted and files_failed == files_attempted:
        raise RuntimeError(f"all rollout files failed to read under {home}")

    activities = _deduplicate(candidates)
    return activities, warnings


def _iter_rollout_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("rollout-*.jsonl"):
        if path.is_file():
            yield path


def _rollout_files_newest_first(root: Path, warnings: list[str]) -> tuple[list[Path], int]:
    files: list[tuple[float, Path]] = []
    stat_failures = 0
    for path in _iter_rollout_files(root):
        try:
            modified_at = path.stat().st_mtime
        except OSError as exc:
            stat_failures += 1
            warnings.append(f"failed to stat rollout file {path}: {exc}")
            continue
        files.append((modified_at, path))
    return [path for _, path in sorted(files, key=lambda item: (-item[0], str(item[1])))], stat_failures


def _collect_file(path: Path, start: datetime, end: datetime) -> tuple[list[_Candidate], list[str]]:
    warnings: list[str] = []
    candidates: list[_Candidate] = []
    first_meta: dict[str, Any] | None = None
    default_cwd: str | None = None
    current_turn_id: str | None = None
    turns: dict[str, _TurnState] = {}
    previous_user_text: str | None = None

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            record = json.loads(raw_line)
            if not isinstance(record, dict):
                continue
            record_type = record.get("type")
            payload = record.get("payload")

            if record_type == "session_meta" and first_meta is None and isinstance(payload, dict):
                first_meta = payload
                default_cwd = _string(payload.get("cwd"))
                if _is_excluded_session(payload):
                    return [], []
                continue

            if record_type == "event_msg" and isinstance(payload, dict):
                event_type = _string(payload.get("type") or payload.get("event_type"))
                turn_id = _string(payload.get("turn_id"))
                if turn_id and event_type == "task_started":
                    current_turn_id = turn_id
                    state = turns.setdefault(turn_id, _TurnState())
                    state.started_at = _parse_time(payload.get("started_at"))
                continue

            if record_type == "turn_context" and isinstance(payload, dict):
                turn_id = _string(payload.get("turn_id")) or current_turn_id
                if turn_id:
                    state = turns.setdefault(turn_id, _TurnState())
                    state.cwd = _string(payload.get("cwd")) or state.cwd
                continue

            if record_type != "response_item" or not isinstance(payload, dict):
                continue
            if payload.get("role") != "user" or payload.get("type") != "message":
                continue

            metadata = payload.get("internal_chat_message_metadata_passthrough")
            metadata = metadata if isinstance(metadata, dict) else {}
            turn_id = _string(metadata.get("turn_id")) or current_turn_id
            turn_state = turns.get(turn_id or "", _TurnState())
            occurred_at = _parse_time(metadata.get("create_time")) or turn_state.started_at or _parse_time(record.get("timestamp"))
            if occurred_at is None:
                warnings.append(f"skipped user message without native time: {path}:{line_number}")
                continue
            occurred_at = occurred_at.astimezone(start.tzinfo)
            if occurred_at < start or occurred_at >= end:
                continue

            text = _extract_user_text(payload.get("content"))
            if not text:
                continue
            text, text_warnings = _clean_text(text, path, line_number)
            warnings.extend(text_warnings)
            if not text or _is_generated_prompt(text):
                continue

            task_id = _owning_task_id(first_meta) or _fallback_task_id(path)
            cwd = turn_state.cwd or default_cwd or ""
            contextual_text = _with_context(text, previous_user_text)
            previous_user_text = text
            candidates.append(
                _Candidate(
                    task_id=task_id,
                    path=str(path),
                    line=line_number,
                    occurred_at=occurred_at,
                    cwd=cwd,
                    text=contextual_text,
                    message_id=_string(payload.get("id")),
                )
            )

    return candidates, warnings


def _deduplicate(candidates: list[_Candidate]) -> list[dict[str, Any]]:
    seen_message_ids: set[str] = set()
    seen_fallback: set[tuple[str, str, str]] = set()
    activities: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item.occurred_at, item.path, item.line)):
        if candidate.message_id:
            if candidate.message_id in seen_message_ids:
                continue
            seen_message_ids.add(candidate.message_id)
        else:
            key = (candidate.occurred_at.isoformat(), candidate.cwd, candidate.text)
            if key in seen_fallback:
                continue
            seen_fallback.add(key)
        activities.append(
            {
                "task_id": candidate.task_id,
                "path": candidate.path,
                "line": candidate.line,
                "occurred_at": _rfc3339(candidate.occurred_at),
                "cwd": candidate.cwd,
                "text": candidate.text,
            }
        )
    return activities


def _is_excluded_session(meta: dict[str, Any]) -> bool:
    source = meta.get("source")
    if isinstance(source, dict) and "subagent" in source:
        return True
    if _contains_key_or_value(meta.get("source"), "automation"):
        return True
    if _contains_key_or_value(meta.get("thread_source"), "automation"):
        return True
    originator = _string(meta.get("originator")) or ""
    return "automation" in originator.lower()


def _contains_key_or_value(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return any(
            needle in str(key).lower() or _contains_key_or_value(nested, needle)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_key_or_value(item, needle) for item in value)
    if isinstance(value, str):
        return needle in value.lower()
    return False


def _owning_task_id(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    return _string(meta.get("id")) or _string(meta.get("session_id"))


def _fallback_task_id(path: Path) -> str:
    match = re.match(r"rollout-\d{4}-\d{2}-\d{2}T\d{2}[-:]\d{2}[-:]\d{2}-(.+)\.jsonl$", path.name)
    if match:
        return match.group(1)
    return path.stem


def _extract_user_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = _string(item.get("type"))
        if item_type in {"input_text", "text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n\n".join(part.strip() for part in parts if part.strip()).strip()


def _clean_text(text: str, path: Path, line: int) -> tuple[str, list[str]]:
    warnings: list[str] = []
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = _strip_injected_prefixes(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > MAX_TEXT_CHARS:
        cleaned = cleaned[:MAX_TEXT_CHARS].rstrip()
        warnings.append(f"partial text: truncated user message at {path}:{line} to {MAX_TEXT_CHARS} chars")
    return cleaned, warnings


def _strip_injected_prefixes(text: str) -> str:
    previous = None
    cleaned = text
    while previous != cleaned:
        previous = cleaned
        cleaned = _strip_wrapped_block(cleaned, "recommended_plugins").lstrip()
        cleaned = _strip_wrapped_block(cleaned, "environment_context").lstrip()
        cleaned = _strip_agents_prefix(cleaned).lstrip()
    return cleaned.strip()


def _strip_wrapped_block(text: str, tag: str) -> str:
    pattern = re.compile(rf"\A\s*<{tag}>.*?</{tag}>\s*", re.DOTALL)
    return pattern.sub("", text)


def _strip_agents_prefix(text: str) -> str:
    marker = "</INSTRUCTIONS>"
    if text.lstrip().startswith("# AGENTS.md instructions") and marker in text:
        return text.split(marker, 1)[1].strip()
    return text


def _is_generated_prompt(text: str) -> bool:
    if any(noisy in text for noisy in NOISY_SUBSTRINGS):
        return True
    return any(pattern.search(text) for pattern in GENERATED_PROMPT_PATTERNS)


def _with_context(text: str, previous_user_text: str | None) -> str:
    if previous_user_text is None or not _is_brief_followup(text):
        return text
    context = _compact_context(previous_user_text)
    return f"Task context: {context}\nFollow-up: {text}"


def _is_brief_followup(text: str) -> bool:
    words = re.findall(r"\S+", text)
    if len(words) > BRIEF_WORD_LIMIT:
        return False
    first = words[0].lower().strip(".,!?") if words else ""
    return first in {
        "also",
        "actually",
        "and",
        "yes",
        "yeah",
        "yep",
        "no",
        "ok",
        "okay",
        "wait",
        "plus",
        "continue",
        "same",
        "do",
        "please",
    }


def _compact_context(text: str) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) <= 240:
        return one_line
    return one_line[:237].rstrip() + "..."


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _rfc3339(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None

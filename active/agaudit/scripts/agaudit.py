#!/usr/bin/env python3
"""Audit local agent automation registrations and execution health."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import signal
import stat
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


EXIT_HEALTHY = 0
EXIT_ISSUES = 1
EXIT_INVALID = 2

TOP_LEVEL_KEYS = {"version", "notification", "crons"}
NOTIFICATION_KEYS = {"skill", "command", "timeout_seconds"}
CRON_KEYS = {"id", "scheduler", "command", "timeout_seconds", "expect_json"}
CODEX_SCHEDULER_KEYS = {"kind", "path", "id", "rrule", "prompt_contains"}
CRONTAB_SCHEDULER_KEYS = {"kind", "line"}
AUTOMATION_KINDS = {"cron", "heartbeat"}


@dataclass(frozen=True)
class ProcessResult:
    status: str
    stdout: str = ""


@dataclass(frozen=True)
class NotificationConfig:
    skill: str
    command: tuple[str, ...]
    timeout_seconds: float


@dataclass(frozen=True)
class SchedulerConfig:
    kind: str
    values: dict[str, str]


@dataclass(frozen=True)
class CronConfig:
    id: str
    scheduler: SchedulerConfig
    command: tuple[str, ...]
    timeout_seconds: float
    expect_json: dict[str, Any]


@dataclass(frozen=True)
class AuditConfig:
    notification: NotificationConfig
    crons: tuple[CronConfig, ...]


def utc_timestamp() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitized_error(location: str, reason: str, field: str | None = None) -> dict[str, str]:
    error = {"location": location, "reason": reason}
    if field is not None:
        error["field"] = field
    return error


def unknown_field_errors(
    value: dict[str, Any], allowed: set[str], location: str
) -> list[dict[str, str]]:
    return [
        sanitized_error(location, "unknown_field", field)
        for field in sorted(set(value) - allowed)
    ]


def missing_field_errors(
    value: dict[str, Any], required: set[str], location: str
) -> list[dict[str, str]]:
    return [
        sanitized_error(location, "missing_field", field)
        for field in sorted(required - set(value))
    ]


def expand_args(command: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(os.path.expanduser(arg) for arg in command)


def validate_command(value: Any, location: str) -> tuple[tuple[str, ...] | None, list[dict[str, str]]]:
    if not isinstance(value, list) or not value:
        return None, [sanitized_error(location, "invalid_command")]
    if not all(isinstance(arg, str) and arg for arg in value):
        return None, [sanitized_error(location, "invalid_command")]
    return tuple(value), []


def validate_timeout(value: Any, location: str) -> tuple[float | None, list[dict[str, str]]]:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        return None, [sanitized_error(location, "invalid_timeout")]
    return float(value), []


def read_frontmatter_name(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return None
        if stripped.startswith("name:"):
            value = stripped.removeprefix("name:").strip()
            return value.strip("\"'")
    return None


def validate_notification_binding(
    skill: str, command: tuple[str, ...], location: str
) -> list[dict[str, str]]:
    helper = Path(os.path.expanduser(command[0]))
    try:
        resolved = helper.resolve(strict=True)
    except OSError:
        return [sanitized_error(location, "invalid_notification_binding", "command")]
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return [sanitized_error(location, "invalid_notification_binding", "command")]
    if resolved.parent.name != "scripts":
        return [sanitized_error(location, "invalid_notification_binding", "command")]
    skill_root = resolved.parent.parent
    if skill_root.name != skill:
        return [sanitized_error(location, "invalid_notification_binding", "skill")]
    skill_file = skill_root / "SKILL.md"
    if not skill_file.is_file() or read_frontmatter_name(skill_file) != skill:
        return [sanitized_error(location, "invalid_notification_binding", "skill")]
    if skill == "slack-notify" and resolved.name != "slack-notify":
        return [sanitized_error(location, "invalid_notification_binding", "command")]
    return []


def validate_notification(value: Any) -> tuple[NotificationConfig | None, list[dict[str, str]]]:
    location = "notification"
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return None, [sanitized_error(location, "invalid_object")]
    errors.extend(unknown_field_errors(value, NOTIFICATION_KEYS, location))
    errors.extend(missing_field_errors(value, NOTIFICATION_KEYS, location))
    skill = value.get("skill")
    if not isinstance(skill, str) or not skill:
        errors.append(sanitized_error(location, "invalid_skill", "skill"))
    command, command_errors = validate_command(value.get("command"), f"{location}.command")
    errors.extend(command_errors)
    timeout, timeout_errors = validate_timeout(
        value.get("timeout_seconds"), f"{location}.timeout_seconds"
    )
    errors.extend(timeout_errors)
    if command is not None and isinstance(skill, str) and skill:
        errors.extend(validate_notification_binding(skill, command, location))
    if errors or command is None or timeout is None or not isinstance(skill, str):
        return None, errors
    return NotificationConfig(skill=skill, command=command, timeout_seconds=timeout), []


def validate_scheduler(value: Any, location: str) -> tuple[SchedulerConfig | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return None, [sanitized_error(location, "invalid_object")]
    kind = value.get("kind")
    if kind == "codex":
        required = CODEX_SCHEDULER_KEYS
    elif kind == "crontab":
        required = CRONTAB_SCHEDULER_KEYS
    else:
        return None, [sanitized_error(location, "unknown_scheduler_kind", "kind")]
    errors.extend(unknown_field_errors(value, required, location))
    errors.extend(missing_field_errors(value, required, location))
    values: dict[str, str] = {}
    for key in sorted(required - {"kind"}):
        current = value.get(key)
        if not isinstance(current, str) or not current:
            errors.append(sanitized_error(location, "invalid_field", key))
        else:
            values[key] = current
    if errors:
        return None, errors
    return SchedulerConfig(kind=kind, values=values), []


def validate_cron(value: Any, index: int) -> tuple[CronConfig | None, list[dict[str, str]]]:
    location = f"crons[{index}]"
    errors: list[dict[str, str]] = []
    if not isinstance(value, dict):
        return None, [sanitized_error(location, "invalid_object")]
    errors.extend(unknown_field_errors(value, CRON_KEYS, location))
    errors.extend(missing_field_errors(value, CRON_KEYS - {"expect_json"}, location))
    cron_id = value.get("id")
    if not isinstance(cron_id, str) or not cron_id:
        errors.append(sanitized_error(location, "invalid_id", "id"))
    scheduler, scheduler_errors = validate_scheduler(value.get("scheduler"), f"{location}.scheduler")
    errors.extend(scheduler_errors)
    command, command_errors = validate_command(value.get("command"), f"{location}.command")
    errors.extend(command_errors)
    timeout, timeout_errors = validate_timeout(value.get("timeout_seconds"), f"{location}.timeout_seconds")
    errors.extend(timeout_errors)
    expect_json = value.get("expect_json")
    if expect_json is None:
        expect_json = None
    elif not isinstance(expect_json, dict):
        errors.append(sanitized_error(location, "invalid_expect_json", "expect_json"))
    elif not all(isinstance(key, str) and key for key in expect_json):
        errors.append(sanitized_error(location, "invalid_expect_json", "expect_json"))
    if (
        errors
        or not isinstance(cron_id, str)
        or scheduler is None
        or command is None
        or timeout is None
        or not (expect_json is None or isinstance(expect_json, dict))
    ):
        return None, errors
    return CronConfig(
        id=cron_id,
        scheduler=scheduler,
        command=command,
        timeout_seconds=timeout,
        expect_json=expect_json or {},
    ), []


def validate_config(raw: Any) -> tuple[NotificationConfig | None, AuditConfig | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if not isinstance(raw, dict):
        return None, None, [sanitized_error("config", "invalid_object")]
    errors.extend(unknown_field_errors(raw, TOP_LEVEL_KEYS, "config"))
    errors.extend(missing_field_errors(raw, TOP_LEVEL_KEYS, "config"))
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        errors.append(sanitized_error("config", "invalid_version", "version"))
    elif version != 1:
        errors.append(sanitized_error("config", "unsupported_version", "version"))

    notification, notification_errors = validate_notification(raw.get("notification"))
    errors.extend(notification_errors)

    crons_raw = raw.get("crons")
    crons: list[CronConfig] = []
    if not isinstance(crons_raw, list):
        errors.append(sanitized_error("crons", "invalid_list"))
    elif not crons_raw:
        errors.append(sanitized_error("crons", "empty_crons"))
    else:
        seen: set[str] = set()
        for index, value in enumerate(crons_raw):
            duplicate = False
            if isinstance(value, dict) and isinstance(value.get("id"), str) and value["id"]:
                if value["id"] in seen:
                    errors.append(sanitized_error(f"crons[{index}]", "duplicate_id", "id"))
                    duplicate = True
                else:
                    seen.add(value["id"])
            cron, cron_errors = validate_cron(value, index)
            errors.extend(cron_errors)
            if cron is None:
                continue
            if duplicate:
                continue
            crons.append(cron)

    if errors:
        return notification, None, errors
    if notification is None:
        return None, None, [sanitized_error("notification", "invalid_object")]
    return notification, AuditConfig(notification=notification, crons=tuple(crons)), []


def read_private_config(path: Path) -> tuple[str | None, list[dict[str, str]]]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None, [sanitized_error("config", "missing_config")]
    except OSError:
        return None, [sanitized_error("config", "read_failed")]
    try:
        with os.fdopen(fd, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            mode = stat.S_IMODE(metadata.st_mode)
            if not stat.S_ISREG(metadata.st_mode):
                return None, [sanitized_error("config", "invalid_file_type")]
            if metadata.st_uid != os.getuid():
                return None, [sanitized_error("config", "invalid_file_owner")]
            if mode not in {0o400, 0o600}:
                return None, [sanitized_error("config", "invalid_file_permissions")]
            try:
                return handle.read().decode("utf-8"), []
            except UnicodeDecodeError:
                return None, [sanitized_error("config", "malformed_json")]
    except OSError:
        return None, [sanitized_error("config", "read_failed")]


def load_config(path: Path) -> tuple[NotificationConfig | None, AuditConfig | None, list[dict[str, str]]]:
    text, read_errors = read_private_config(path)
    if read_errors:
        return None, None, read_errors
    assert text is not None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None, None, [sanitized_error("config", "malformed_json")]
    return validate_config(raw)


def run_process(command: tuple[str, ...], timeout_seconds: float) -> ProcessResult:
    try:
        process = subprocess.Popen(
            list(expand_args(command)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except (OSError, ValueError, UnicodeError):
        return ProcessResult(status="spawn_failed")
    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            pass
        process.communicate()
        return ProcessResult(status="timeout")
    if process.returncode != 0:
        return ProcessResult(status="nonzero_exit")
    return ProcessResult(status="ok", stdout=stdout)


def verify_codex_scheduler(scheduler: SchedulerConfig) -> dict[str, str]:
    path = Path(os.path.expanduser(scheduler.values["path"]))
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {"status": "issue", "reason": "missing_registration"}
    except (tomllib.TOMLDecodeError, OSError):
        return {"status": "issue", "reason": "invalid_registration"}

    if data.get("id") != scheduler.values["id"]:
        return {"status": "issue", "reason": "registration_drift"}
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in AUTOMATION_KINDS:
        return {"status": "issue", "reason": "registration_drift"}
    if data.get("status") != "ACTIVE":
        return {"status": "issue", "reason": "registration_inactive"}
    if data.get("rrule") != scheduler.values["rrule"]:
        return {"status": "issue", "reason": "registration_drift"}
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or scheduler.values["prompt_contains"] not in prompt:
        return {"status": "issue", "reason": "registration_drift"}
    return {"status": "ok"}


def verify_crontab_scheduler(scheduler: SchedulerConfig) -> dict[str, str]:
    result = run_process(("crontab", "-l"), 15)
    if result.status != "ok":
        return {"status": "issue", "reason": "registration_unavailable"}
    active_lines = [
        line for line in result.stdout.splitlines() if not line.lstrip().startswith("#")
    ]
    if scheduler.values["line"] not in active_lines:
        return {"status": "issue", "reason": "missing_registration"}
    return {"status": "ok"}


def verify_scheduler(scheduler: SchedulerConfig) -> dict[str, str]:
    if scheduler.kind == "codex":
        return verify_codex_scheduler(scheduler)
    return verify_crontab_scheduler(scheduler)


def same_json_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual == expected
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and actual == expected
        )
    return type(actual) is type(expected) and actual == expected


def json_matches(actual: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual or not same_json_value(actual[key], value):
            return False
    return True


def run_cron(cron: CronConfig) -> dict[str, dict[str, str]]:
    installation = verify_scheduler(cron.scheduler)
    command: dict[str, str]
    if installation["status"] != "ok":
        command = {"status": "skipped", "reason": "registration_issue"}
        return {"installation": installation, "command": command}

    result = run_process(cron.command, cron.timeout_seconds)
    if result.status != "ok":
        command = {"status": "issue", "reason": result.status}
        return {"installation": installation, "command": command}
    if not cron.expect_json:
        return {"installation": installation, "command": {"status": "ok"}}
    try:
        actual = json.loads(result.stdout)
    except json.JSONDecodeError:
        command = {"status": "issue", "reason": "invalid_json"}
        return {"installation": installation, "command": command}
    if not json_matches(actual, cron.expect_json):
        command = {"status": "issue", "reason": "json_mismatch"}
        return {"installation": installation, "command": command}
    return {"installation": installation, "command": {"status": "ok"}}


def summary_from_report(report: dict[str, Any]) -> str:
    if report.get("status") == "invalid_config":
        reasons = sorted({error.get("reason", "invalid_config") for error in report.get("config_errors", [])})
        joined = ", ".join(reasons[:8]) or "invalid_config"
        return f"agaudit automations detected invalid config: {joined}"[:1000]

    issue_parts: list[str] = []
    for result in report.get("results", []):
        reasons: list[str] = []
        for section_name in ("installation", "command"):
            section = result.get(section_name, {})
            if isinstance(section, dict) and section.get("status") == "issue":
                reasons.append(str(section.get("reason", "issue")))
            if isinstance(section, dict) and section.get("status") == "skipped":
                reasons.append(str(section.get("reason", "skipped")))
        if reasons:
            issue_parts.append(f"{result.get('id', 'unknown')}: {','.join(reasons)}")
    joined = "; ".join(issue_parts[:10]) or "issue"
    return f"agaudit automations detected issues: {joined}"[:1000]


def maybe_notify(
    report: dict[str, Any],
    notification: NotificationConfig | None,
    *,
    no_notify: bool,
) -> tuple[str, str | None]:
    if report.get("status") == "healthy":
        return "not_needed", None
    if no_notify:
        return "suppressed", None
    if notification is None:
        return "unavailable", None
    message = summary_from_report(report)
    result = run_process((*notification.command, message), notification.timeout_seconds)
    if result.status != "ok":
        return "failed", result.status
    return "sent", None


def automation_report(
    config_path: Path,
    *,
    only: str | None = None,
    no_notify: bool = False,
) -> tuple[int, dict[str, Any]]:
    notification, config, config_errors = load_config(config_path)
    report: dict[str, Any] = {
        "timestamp_utc": utc_timestamp(),
        "subcommand": "automations",
    }
    if config_errors:
        report.update({"status": "invalid_config", "config_errors": config_errors})
        notification_status, notification_reason = maybe_notify(
            report, notification, no_notify=no_notify
        )
        report["notification"] = {"status": notification_status}
        if notification_reason is not None:
            report["notification"]["reason"] = notification_reason
        return EXIT_INVALID, report
    assert config is not None

    selected = [cron for cron in config.crons if only is None or cron.id == only]
    if only is not None and not selected:
        report.update(
            {
                "status": "invalid_config",
                "config_errors": [sanitized_error("selection", "unknown_id", "only")],
            }
        )
        notification_status, notification_reason = maybe_notify(
            report, config.notification, no_notify=no_notify
        )
        report["notification"] = {"status": notification_status}
        if notification_reason is not None:
            report["notification"]["reason"] = notification_reason
        return EXIT_INVALID, report

    results: list[dict[str, Any]] = []
    for cron in selected:
        result = {"id": cron.id}
        result.update(run_cron(cron))
        results.append(result)

    has_issues = any(
        result["installation"]["status"] != "ok" or result["command"]["status"] != "ok"
        for result in results
    )
    report.update({"status": "issues" if has_issues else "healthy", "results": results})
    notification_status, notification_reason = maybe_notify(
        report, config.notification, no_notify=no_notify
    )
    report["notification"] = {"status": notification_status}
    if notification_reason is not None:
        report["notification"]["reason"] = notification_reason
    if notification_status == "failed":
        return EXIT_INVALID, report
    return (EXIT_ISSUES if has_issues else EXIT_HEALTHY), report


def write_report(report: dict[str, Any], stream: TextIO) -> None:
    print(json.dumps(report, sort_keys=True), file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agaudit")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    automations = subcommands.add_parser("automations")
    automations.add_argument(
        "--config",
        default="~/.agaudit.json",
        help="Path to agaudit JSON config. Defaults to ~/.agaudit.json.",
    )
    automations.add_argument("--only", help="Run only one configured cron id.")
    automations.add_argument(
        "--no-notify",
        action="store_true",
        help="Suppress configured notification while still reporting issues.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "automations":
        exit_code, report = automation_report(
            Path(os.path.expanduser(args.config)),
            only=args.only,
            no_notify=args.no_notify,
        )
        write_report(report, sys.stdout)
        return exit_code
    parser.error("unknown subcommand")
    return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())

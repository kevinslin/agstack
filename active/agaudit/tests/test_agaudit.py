from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agaudit.py"
MODULE_SPEC = importlib.util.spec_from_file_location("agaudit_cli", SCRIPT_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
agaudit = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = agaudit
MODULE_SPEC.loader.exec_module(agaudit)


class AgauditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.config_path = self.root / "agaudit.json"
        self.automation_path = self.root / "automation.toml"
        self.notification_path = self.root / "notification.txt"
        self.notify_skill_root = self.root / "slack-notify"
        self.notify_script = self.notify_skill_root / "scripts" / "slack-notify"
        self.notify_skill_root.mkdir()
        (self.notify_skill_root / "scripts").mkdir()
        (self.notify_skill_root / "SKILL.md").write_text(
            "---\nname: slack-notify\ndescription: test fixture\n---\n"
        )
        self.write_notify_helper()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_automation(
        self,
        *,
        status: str = "ACTIVE",
        rrule: str = "FREQ=HOURLY;INTERVAL=24",
        prompt: str = "run example-check now",
        kind: str = "cron",
        automation_id: str = "scheduler-id",
    ) -> None:
        self.automation_path.write_text(
            "\n".join(
                [
                    f'id = "{automation_id}"',
                    f'kind = "{kind}"',
                    f'status = "{status}"',
                    f'rrule = "{rrule}"',
                    f'prompt = "{prompt}"',
                    "",
                ]
            )
        )

    def json_command(self, payload: dict[str, object]) -> list[str]:
        return [
            sys.executable,
            "-c",
            "import json; print(json.dumps(json.loads(__import__('sys').argv[1])))",
            json.dumps(payload, sort_keys=True),
        ]

    def notify_command(self, *, exits: int = 0) -> list[str]:
        self.write_notify_helper(exits=exits)
        return [str(self.notify_script), str(self.notification_path)]

    def write_notify_helper(self, *, exits: int = 0) -> None:
        code = (
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "Path(sys.argv[1]).write_text(sys.argv[2])\n"
            f"raise SystemExit({exits})"
        )
        self.notify_script.write_text(code)
        self.notify_script.chmod(0o700)

    def base_config(
        self,
        *,
        scheduler: dict[str, object] | None = None,
        command: list[str] | None = None,
        expect_json: dict[str, object] | None = None,
        notify_exits: int = 0,
    ) -> dict[str, object]:
        if scheduler is None:
            scheduler = {
                "kind": "codex",
                "path": str(self.automation_path),
                "id": "scheduler-id",
                "rrule": "FREQ=HOURLY;INTERVAL=24",
                "prompt_contains": "example-check",
            }
        return {
            "version": 1,
            "notification": {
                "skill": "slack-notify",
                "command": self.notify_command(exits=notify_exits),
                "timeout_seconds": 5,
            },
            "crons": [
                {
                    "id": "example",
                    "scheduler": scheduler,
                    "command": command
                    if command is not None
                    else self.json_command({"status": "recorded", "target": "ok"}),
                    "timeout_seconds": 5,
                    "expect_json": expect_json
                    if expect_json is not None
                    else {"status": "recorded", "target": "ok"},
                }
            ],
        }

    def write_config(self, config: dict[str, object]) -> None:
        self.config_path.write_text(json.dumps(config, sort_keys=True))
        self.config_path.chmod(0o600)

    def run_report(self, *, no_notify: bool = False, only: str | None = None) -> tuple[int, dict[str, object]]:
        return agaudit.automation_report(self.config_path, no_notify=no_notify, only=only)

    def test_active_codex_schedule_executes_successful_json_without_notification(self) -> None:
        self.write_automation()
        self.write_config(self.base_config())

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_HEALTHY)
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(report["notification"], {"status": "not_needed"})
        self.assertEqual(report["results"][0]["installation"], {"status": "ok"})
        self.assertEqual(report["results"][0]["command"], {"status": "ok"})
        self.assertFalse(self.notification_path.exists())

    def test_missing_paused_and_drifted_codex_registration_skip_command(self) -> None:
        cases = [
            ("missing", None, "missing_registration"),
            ("paused", {"status": "PAUSED"}, "registration_inactive"),
            ("rrule-drift", {"rrule": "FREQ=DAILY;INTERVAL=1"}, "registration_drift"),
            ("prompt-drift", {"prompt": "different task"}, "registration_drift"),
        ]
        for label, automation_kwargs, reason in cases:
            with self.subTest(label=label):
                self.notification_path.unlink(missing_ok=True)
                if automation_kwargs is None:
                    self.automation_path.unlink(missing_ok=True)
                else:
                    self.write_automation(**automation_kwargs)
                self.write_config(self.base_config())

                with mock.patch.object(agaudit, "run_process", wraps=agaudit.run_process) as run_process:
                    code, report = self.run_report(no_notify=True)

                self.assertEqual(code, agaudit.EXIT_ISSUES)
                self.assertEqual(report["results"][0]["installation"]["reason"], reason)
                self.assertEqual(
                    report["results"][0]["command"],
                    {"status": "skipped", "reason": "registration_issue"},
                )
                command_attempts = [
                    call.args[0]
                    for call in run_process.call_args_list
                    if call.args[0][0] == sys.executable
                ]
                self.assertEqual(command_attempts, [])

    def test_crontab_rejects_commented_exact_line(self) -> None:
        scheduler = {"kind": "crontab", "line": "0 7 * * * example-check"}
        self.write_config(self.base_config(scheduler=scheduler))

        def fake_run_process(command: tuple[str, ...], timeout: float) -> object:
            self.assertEqual(command, ("crontab", "-l"))
            self.assertEqual(timeout, 15)
            return agaudit.ProcessResult(
                status="ok",
                stdout="# 0 7 * * * example-check\n0 8 * * * other-check\n",
            )

        with mock.patch.object(agaudit, "run_process", side_effect=fake_run_process):
            code, report = self.run_report(no_notify=True)

        self.assertEqual(code, agaudit.EXIT_ISSUES)
        self.assertEqual(report["results"][0]["installation"]["reason"], "missing_registration")
        self.assertEqual(report["results"][0]["command"]["status"], "skipped")

    def test_crontab_active_line_runs_command(self) -> None:
        scheduler = {"kind": "crontab", "line": "0 7 * * * example-check"}
        self.write_config(self.base_config(scheduler=scheduler))
        calls: list[tuple[str, ...]] = []

        def fake_run_process(command: tuple[str, ...], timeout: float) -> object:
            calls.append(command)
            if command == ("crontab", "-l"):
                return agaudit.ProcessResult(status="ok", stdout="0 7 * * * example-check\n")
            return agaudit.ProcessResult(
                status="ok", stdout=json.dumps({"status": "recorded", "target": "ok"})
            )

        with mock.patch.object(agaudit, "run_process", side_effect=fake_run_process):
            code, report = self.run_report(no_notify=True)

        self.assertEqual(code, agaudit.EXIT_HEALTHY)
        self.assertEqual(calls[0], ("crontab", "-l"))
        self.assertEqual(report["results"][0]["command"], {"status": "ok"})

    def test_wrong_json_target_and_nonzero_command_are_issues(self) -> None:
        self.write_automation()
        self.write_config(
            self.base_config(
                command=self.json_command({"status": "recorded", "target": "wrong"})
            )
        )

        mismatch_code, mismatch_report = self.run_report(no_notify=True)

        self.assertEqual(mismatch_code, agaudit.EXIT_ISSUES)
        self.assertEqual(
            mismatch_report["results"][0]["command"],
            {"status": "issue", "reason": "json_mismatch"},
        )

        self.write_config(
            self.base_config(command=[sys.executable, "-c", "raise SystemExit(7)"])
        )
        nonzero_code, nonzero_report = self.run_report(no_notify=True)

        self.assertEqual(nonzero_code, agaudit.EXIT_ISSUES)
        self.assertEqual(
            nonzero_report["results"][0]["command"],
            {"status": "issue", "reason": "nonzero_exit"},
        )

    def test_expect_json_is_optional_for_exit_only_commands(self) -> None:
        self.write_automation()
        config = self.base_config(command=[sys.executable, "-c", "print('not-json')"])
        del config["crons"][0]["expect_json"]
        self.write_config(config)

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_HEALTHY)
        self.assertEqual(report["results"][0]["command"], {"status": "ok"})

    def test_json_matching_requires_present_keys_and_distinct_bool_numeric_types(self) -> None:
        self.write_automation()
        self.write_config(
            self.base_config(
                command=self.json_command({"count": True}),
                expect_json={"count": 1},
            )
        )

        bool_code, bool_report = self.run_report(no_notify=True)

        self.assertEqual(bool_code, agaudit.EXIT_ISSUES)
        self.assertEqual(bool_report["results"][0]["command"]["reason"], "json_mismatch")

        self.write_config(
            self.base_config(
                command=self.json_command({"other": None}),
                expect_json={"missing": None},
            )
        )
        missing_code, missing_report = self.run_report(no_notify=True)

        self.assertEqual(missing_code, agaudit.EXIT_ISSUES)
        self.assertEqual(missing_report["results"][0]["command"]["reason"], "json_mismatch")

    def test_timeout_kills_process_group_and_reports_issue(self) -> None:
        self.write_automation()
        self.write_config(
            self.base_config(
                command=[
                    sys.executable,
                    "-c",
                    "import time; time.sleep(5)",
                ]
            )
        )
        config = json.loads(self.config_path.read_text())
        config["crons"][0]["timeout_seconds"] = 0.1
        self.write_config(config)

        code, report = self.run_report(no_notify=True)

        self.assertEqual(code, agaudit.EXIT_ISSUES)
        self.assertEqual(
            report["results"][0]["command"], {"status": "issue", "reason": "timeout"}
        )

    def test_issue_notification_can_be_sent_failed_or_suppressed(self) -> None:
        self.write_automation()
        self.write_config(
            self.base_config(command=self.json_command({"status": "different"}))
        )

        sent_code, sent_report = self.run_report()

        self.assertEqual(sent_code, agaudit.EXIT_ISSUES)
        self.assertEqual(sent_report["notification"], {"status": "sent"})
        self.assertIn("example", self.notification_path.read_text())

        self.write_config(
            self.base_config(
                command=self.json_command({"status": "different"}), notify_exits=3
            )
        )
        failed_code, failed_report = self.run_report()

        self.assertEqual(failed_code, agaudit.EXIT_INVALID)
        self.assertEqual(failed_report["notification"]["status"], "failed")
        self.assertEqual(failed_report["notification"]["reason"], "nonzero_exit")

        self.notification_path.unlink(missing_ok=True)
        suppressed_code, suppressed_report = self.run_report(no_notify=True)

        self.assertEqual(suppressed_code, agaudit.EXIT_ISSUES)
        self.assertEqual(suppressed_report["notification"], {"status": "suppressed"})
        self.assertFalse(self.notification_path.exists())

    def test_unknown_only_uses_configured_notification(self) -> None:
        self.write_automation()
        self.write_config(self.base_config())

        code, report = self.run_report(only="missing-id")

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(report["status"], "invalid_config")
        self.assertEqual(report["config_errors"][0]["reason"], "unknown_id")
        self.assertEqual(report["notification"], {"status": "sent"})
        self.assertIn("invalid config", self.notification_path.read_text())

    def test_malformed_config_reports_invalid_and_does_not_execute_crons(self) -> None:
        self.config_path.write_text("{")
        self.config_path.chmod(0o600)

        with mock.patch.object(agaudit, "run_process") as run_process:
            code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(report["status"], "invalid_config")
        self.assertEqual(report["config_errors"][0]["reason"], "malformed_json")
        self.assertEqual(report["notification"], {"status": "unavailable"})
        run_process.assert_not_called()

    def test_invalid_config_rejects_empty_inventory_bool_version_and_nonfinite_timeout(self) -> None:
        config = self.base_config()
        config["version"] = True
        config["notification"]["timeout_seconds"] = float("nan")
        config["crons"] = []
        self.write_config(config)

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        reasons = {error["reason"] for error in report["config_errors"]}
        self.assertIn("empty_crons", reasons)
        self.assertIn("invalid_version", reasons)
        self.assertIn("invalid_timeout", reasons)
        self.assertEqual(report["notification"], {"status": "unavailable"})

    def test_private_config_file_permissions_are_required(self) -> None:
        self.write_config(self.base_config())
        self.config_path.chmod(0o644)

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(report["status"], "invalid_config")
        self.assertEqual(report["config_errors"][0]["reason"], "invalid_file_permissions")
        self.assertEqual(report["notification"], {"status": "unavailable"})

    def test_notification_command_must_match_skill_binding(self) -> None:
        config = self.base_config()
        config["notification"]["command"] = ["/bin/true"]
        self.write_config(config)

        with mock.patch.object(agaudit, "run_process") as run_process:
            code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(report["status"], "invalid_config")
        self.assertEqual(
            report["config_errors"][0]["reason"], "invalid_notification_binding"
        )
        self.assertEqual(report["notification"], {"status": "unavailable"})
        run_process.assert_not_called()

    def test_notification_skill_name_must_match_skill_frontmatter_and_directory(self) -> None:
        other_root = self.root / "other-skill"
        scripts = other_root / "scripts"
        scripts.mkdir(parents=True)
        helper = scripts / "helper"
        helper.write_text("#!/bin/sh\nexit 0\n")
        helper.chmod(0o700)
        (other_root / "SKILL.md").write_text(
            "---\nname: different-skill\ndescription: test fixture\n---\n"
        )
        config = self.base_config()
        config["notification"]["skill"] = "other-skill"
        config["notification"]["command"] = [str(helper)]
        self.write_config(config)

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(
            report["config_errors"][0]["reason"], "invalid_notification_binding"
        )

    def test_invalid_skill_frontmatter_text_is_sanitized(self) -> None:
        (self.notify_skill_root / "SKILL.md").write_bytes(b"\xff")
        self.write_config(self.base_config())

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        self.assertEqual(
            report["config_errors"][0]["reason"], "invalid_notification_binding"
        )

    def test_non_string_codex_kind_is_registration_drift(self) -> None:
        self.automation_path.write_text(
            "\n".join(
                [
                    'id = "scheduler-id"',
                    'kind = ["cron"]',
                    'status = "ACTIVE"',
                    'rrule = "FREQ=HOURLY;INTERVAL=24"',
                    'prompt = "run example-check now"',
                    "",
                ]
            )
        )
        self.write_config(self.base_config())

        code, report = self.run_report(no_notify=True)

        self.assertEqual(code, agaudit.EXIT_ISSUES)
        self.assertEqual(
            report["results"][0]["installation"]["reason"], "registration_drift"
        )

    def test_structural_config_errors_notify_when_notifier_is_usable(self) -> None:
        config = self.base_config()
        config["crons"][0]["extra"] = "ignored-value"
        config["crons"].append(config["crons"][0].copy())
        self.write_config(config)

        code, report = self.run_report()

        self.assertEqual(code, agaudit.EXIT_INVALID)
        reasons = {error["reason"] for error in report["config_errors"]}
        self.assertIn("unknown_field", reasons)
        self.assertIn("duplicate_id", reasons)
        self.assertEqual(report["notification"], {"status": "sent"})
        self.assertIn("invalid config", self.notification_path.read_text())

    def test_cli_outputs_json_report(self) -> None:
        self.write_automation()
        self.write_config(self.base_config())

        with mock.patch.object(sys, "stdout", new_callable=lambda: __import__("io").StringIO()) as stdout:
            code = agaudit.main(["automations", "--config", str(self.config_path)])

        self.assertEqual(code, agaudit.EXIT_HEALTHY)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["subcommand"], "automations")
        self.assertEqual(report["results"][0]["id"], "example")

    def test_spawn_failures_are_sanitized(self) -> None:
        result = agaudit.run_process(("bad\0arg",), 1)

        self.assertEqual(result, agaudit.ProcessResult(status="spawn_failed"))


if __name__ == "__main__":
    unittest.main()

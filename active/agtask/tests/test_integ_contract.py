from __future__ import annotations

import os
import re
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
INTEG_SKILL = ROOT / ".agents" / "skills" / "integ"


class IntegrationRunnerContractTest(unittest.TestCase):
    def run_with_fake_python(
        self, *, database: Path | None = None
    ) -> tuple[list[str], str, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        temp_root = Path(temporary.name)
        fake_bin = temp_root / "bin"
        fake_bin.mkdir()
        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$AGTASK_DB\" >> \"$INTEG_CAPTURE\"\n"
        )
        fake_python.chmod(0o755)

        proof_dir = temp_root / "proof"
        capture = temp_root / "capture.txt"
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment['PATH']}",
                "INTEG_CAPTURE": str(capture),
                "INTEG_PARENT_THREAD_ID": "contract-test-parent",
                "INTEG_PROOF_DIR": str(proof_dir),
            }
        )
        if database is None:
            environment.pop("AGTASK_DB", None)
        else:
            environment["AGTASK_DB"] = str(database)

        completed = subprocess.run(
            ["bash", str(INTEG_SKILL / "scripts" / "run_integration_tests.sh")],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return capture.read_text().splitlines(), completed.stdout, proof_dir

    def test_runner_defaults_to_proof_ledger(self) -> None:
        captured, output, proof_dir = self.run_with_fake_python()

        expected = str(proof_dir / "ledger.db")
        self.assertEqual(captured, [expected, expected])
        self.assertIn(f"Using ledger: {expected}", output)

    def test_runner_preserves_explicit_database_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "custom.db"
            captured, output, _ = self.run_with_fake_python(database=database)

        self.assertEqual(captured, [str(database), str(database)])
        self.assertIn(f"Using ledger: {database}", output)

    def test_direct_lifecycle_defaults_to_proof_ledger_and_canonicalizes_override(
        self,
    ) -> None:
        lifecycle_path = INTEG_SKILL / "scripts" / "test_lifecycle.py"
        configure_database = runpy.run_path(str(lifecycle_path))["configure_database"]

        with tempfile.TemporaryDirectory() as temporary:
            proof_dir = Path(temporary) / "proof"
            expected = (proof_dir / "ledger.db").resolve()
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AGTASK_DB", None)
                self.assertEqual(configure_database(proof_dir), expected)
                self.assertEqual(os.environ["AGTASK_DB"], str(expected))

            with mock.patch.dict(
                os.environ, {"AGTASK_DB": "relative-integration.db"}, clear=False
            ):
                expected_override = (Path.cwd() / "relative-integration.db").resolve()
                self.assertEqual(configure_database(proof_dir), expected_override)
                self.assertEqual(os.environ["AGTASK_DB"], str(expected_override))

    def test_runner_prevents_default_ledger_fallback(self) -> None:
        runner = (INTEG_SKILL / "scripts" / "run_integration_tests.sh").read_text()

        self.assertIn('PROOF_DIR="$(cd "$PROOF_DIR" && pwd)"', runner)
        self.assertIn('AGTASK_DB="${AGTASK_DB:-$PROOF_DIR/ledger.db}"', runner)
        self.assertIn("export AGTASK_DB", runner)
        self.assertNotIn(".llm/agtask/ledger.db", runner)

    def test_creation_identity_regression_rebinds_copied_session(self) -> None:
        lifecycle_path = INTEG_SKILL / "scripts" / "test_lifecycle.py"
        verify_creation = runpy.run_path(str(lifecycle_path))[
            "verify_creation_identity_regression"
        ]
        cli = ROOT / "skills" / "agtask" / "scripts" / "agtask"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            database = root / "ledger.db"
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment["AGTASK_DB"] = str(database)
            result = verify_creation(
                cli,
                database,
                ROOT,
                environment,
            )

        self.assertEqual(result["scenario_version"], 3)
        self.assertEqual(
            result["session_rebound_from"], result["copied_session_id"]
        )
        self.assertEqual(result["thread"]["session_id"], result["real_session_id"])
        self.assertEqual(
            [(row["role"], row["turn_id"]) for row in result["rollouts"]],
            [("meta", "thread.created"), ("user", "bootstrap")],
        )

    def test_archived_session_audit_scenario_runs_without_live_codex(self) -> None:
        lifecycle_path = INTEG_SKILL / "scripts" / "test_lifecycle.py"
        verify_audit = runpy.run_path(str(lifecycle_path))[
            "verify_archived_session_audit"
        ]
        cli = ROOT / "skills" / "agtask" / "scripts" / "agtask"
        audit_workflow_text = (
            ROOT / "skills" / "agtask" / "references" / "audit.md"
        ).read_text()

        with tempfile.TemporaryDirectory() as temporary:
            proof_dir = Path(temporary) / "proof"
            home = Path(temporary) / "home"
            proof_dir.mkdir()
            home.mkdir()
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            result = verify_audit(
                cli,
                proof_dir,
                ROOT,
                environment,
                audit_workflow_text,
            )

        self.assertEqual(result["scenario"], "archived-session-audit")
        self.assertEqual(result["scenario_version"], 2)
        self.assertTrue(result["applied"]["applied"])
        self.assertEqual(result["archived_thread"]["status"], "done")
        self.assertEqual(result["rerun"]["affected_tasks"], [])

    def test_current_task_add_scenario_runs_without_live_codex(self) -> None:
        lifecycle_path = INTEG_SKILL / "scripts" / "test_lifecycle.py"
        verify_add = runpy.run_path(str(lifecycle_path))[
            "verify_current_task_add"
        ]
        cli = ROOT / "skills" / "agtask" / "scripts" / "agtask"
        add_workflow_text = (
            ROOT / "skills" / "agtask" / "references" / "add.md"
        ).read_text()

        with tempfile.TemporaryDirectory() as temporary:
            proof_dir = Path(temporary) / "proof"
            home = Path(temporary) / "home"
            proof_dir.mkdir()
            home.mkdir()
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            result = verify_add(
                cli,
                proof_dir,
                ROOT,
                environment,
                add_workflow_text,
            )

        self.assertEqual(result["scenario"], "current-task-add")
        self.assertEqual(result["scenario_version"], 1)
        self.assertTrue(all(result["workflow_contract"].values()))
        self.assertEqual(result["created"]["id"], result["retried"]["id"])
        self.assertEqual(result["retried"]["hook_prompts"], [])
        self.assertEqual(len(result["final_rollouts"]), 1)

    def test_current_task_rename_scenario_runs_without_live_codex(self) -> None:
        lifecycle_path = INTEG_SKILL / "scripts" / "test_lifecycle.py"
        lifecycle = runpy.run_path(str(lifecycle_path))
        verify_rename = lifecycle["verify_current_task_rename"]
        cli = ROOT / "skills" / "agtask" / "scripts" / "agtask"
        rename_workflow_text = (
            ROOT / "skills" / "agtask" / "references" / "rename.md"
        ).read_text()

        with tempfile.TemporaryDirectory() as temporary:
            proof_dir = Path(temporary) / "proof"
            home = Path(temporary) / "home"
            proof_dir.mkdir()
            home.mkdir()
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            result = verify_rename(
                cli,
                proof_dir,
                ROOT,
                environment,
                rename_workflow_text,
            )

        self.assertEqual(result["scenario"], "current-task-rename")
        self.assertEqual(result["scenario_version"], 2)
        self.assertTrue(all(result["workflow_contract"].values()))
        self.assertIn(
            "current-task-rename",
            lifecycle["scenario_metadata"](ROOT)["scenarios"],
        )
        self.assertIn("surrounding whitespace", result["invalid_error"])
        self.assertIn("stale rename plan", result["stale_error"])
        self.assertEqual(
            result["after_app_failure"]["title"], "agtask/rename-old"
        )
        self.assertNotIn("apply:app-failure", result["operation_log"])
        self.assertLess(
            result["operation_log"].index("app:success:succeeded"),
            result["operation_log"].index("apply:success"),
        )
        self.assertEqual(
            result["compensation_target"], "agtask/rename-concurrent"
        )
        self.assertEqual(
            result["final_thread"]["title"], result["compensation_target"]
        )
        self.assertEqual(len(result["rename_events"]), 2)

    def test_suite_version_matches_shared_runner_contract(self) -> None:
        scenarios = (INTEG_SKILL / "references" / "scenarios.md").read_text()
        lifecycle = (INTEG_SKILL / "scripts" / "test_lifecycle.py").read_text()

        manifest_version = re.search(r"Suite version: (\d+)", scenarios)
        harness_version = re.search(r"SCENARIO_SUITE_VERSION = (\d+)", lifecycle)
        self.assertIsNotNone(manifest_version)
        self.assertIsNotNone(harness_version)
        self.assertEqual(manifest_version.group(1), "20")
        self.assertEqual(manifest_version.group(1), harness_version.group(1))
        self.assertIn("integration scenario may fall through", scenarios)
        self.assertIn("logical creation ID", scenarios)
        self.assertIn("register --authoritative-session", scenarios)
        self.assertIn("## current-task-rename", scenarios)
        self.assertIn("## current-task-add", scenarios)
        self.assertIn("## archived-session-audit", scenarios)
        self.assertIn("ADD_SCENARIO_VERSION = 1", lifecycle)
        self.assertIn("CREATION_BOOTSTRAP_SCENARIO_VERSION = 3", lifecycle)
        self.assertIn("DASHBOARD_SCENARIO_VERSION = 16", lifecycle)
        self.assertIn("RENAME_SCENARIO_VERSION = 2", lifecycle)
        self.assertIn("AUDIT_SCENARIO_VERSION = 2", lifecycle)


if __name__ == "__main__":
    unittest.main()

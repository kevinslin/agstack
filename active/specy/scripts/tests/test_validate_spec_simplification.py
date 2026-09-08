#!/usr/bin/env python3
"""Tests for the mandatory feature-spec simplification gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "validate_spec_simplification.py"
SPEC = importlib.util.spec_from_file_location("validate_spec_simplification", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)


class SpecSimplificationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.spec = Path(self.directory.name) / "feature.md"
        self.review = Path(self.directory.name) / "review.json"
        self.spec.write_text("# Feature\n\nOne necessary requirement.\n")
        self.verdict = {
            "review_kind": "simplify-spec",
            "reviewer": "independent-simplicity-reviewer",
            "spec_path": str(self.spec),
            "spec_sha256": hashlib.sha256(self.spec.read_bytes()).hexdigest(),
            "verdict": "no-meaningful-simplification",
            "smallest_viable_implementation": "Reuse the existing owner and lifecycle.",
            "keep": ["Agent isolation", "Persistent workspace"],
            "tradeoffs": ["Future storage backends remain unsupported."],
            "no_changes_rationale": "Every remaining requirement protects the requested outcome.",
        }

    def validate(self, *, phase: str = "final", max_lines: int = 150) -> list[str]:
        self.review.write_text(json.dumps(self.verdict))
        return validator.validate(self.spec, self.review, phase=phase, max_lines=max_lines)

    def test_evidence_backed_minimal_spec_passes(self) -> None:
        self.assertEqual(self.validate(), [])

    def test_proposed_changes_pass_review_but_block_completion(self) -> None:
        self.verdict["verdict"] = "changes-proposed"
        self.verdict["remove_or_defer"] = ["Remove speculative retry coordination."]

        self.assertEqual(self.validate(phase="review"), [])
        self.assertIn(
            "Unresolved simplification proposals block specification completion",
            self.validate(),
        )

    def test_proposed_changes_require_concrete_findings(self) -> None:
        self.verdict["verdict"] = "changes-proposed"

        self.assertIn(
            "Proposed simplifications must identify what to remove or defer",
            self.validate(phase="review"),
        )

    def test_no_change_verdict_requires_reason(self) -> None:
        del self.verdict["no_changes_rationale"]

        self.assertIn(
            "A no-change verdict requires an evidence-backed explanation",
            self.validate(),
        )

    def test_material_spec_change_invalidates_review(self) -> None:
        self.spec.write_text("# Feature\n\nA new lifecycle requirement.\n")

        self.assertIn(
            "Simplification review is stale; review the current specification again",
            self.validate(),
        )

    def test_review_for_different_spec_is_rejected(self) -> None:
        self.verdict["spec_path"] = str(Path(self.directory.name) / "other.md")

        self.assertIn("Review belongs to a different specification", self.validate())

    def test_correctness_review_cannot_satisfy_simplicity_gate(self) -> None:
        self.verdict["review_kind"] = "spec"

        self.assertIn(
            "Review must identify itself as an independent simplify-spec pass",
            self.validate(),
        )

    def test_oversized_spec_requires_explicit_justification(self) -> None:
        self.spec.write_text("line\n" * 151)
        self.verdict["spec_sha256"] = hashlib.sha256(self.spec.read_bytes()).hexdigest()

        self.assertIn(
            "Specification has 151 lines; exceeding 150 requires explicit justification",
            self.validate(),
        )

    def test_oversized_spec_passes_with_justified_required_detail(self) -> None:
        self.spec.write_text("line\n" * 151)
        self.verdict["spec_sha256"] = hashlib.sha256(self.spec.read_bytes()).hexdigest()
        self.verdict["line_limit_justification"] = (
            "The required security contract contains independent trust boundaries."
        )

        self.assertEqual(self.validate(), [])

    def test_oversized_draft_may_be_reviewed_when_shortening_is_proposed(self) -> None:
        self.spec.write_text("line\n" * 151)
        self.verdict["spec_sha256"] = hashlib.sha256(self.spec.read_bytes()).hexdigest()
        self.verdict["verdict"] = "changes-proposed"
        self.verdict["remove_or_defer"] = ["Remove the repeated lifecycle sections."]

        self.assertEqual(self.validate(phase="review"), [])

    def test_deferred_changes_require_user_decision(self) -> None:
        self.verdict["verdict"] = "user-deferred"
        self.verdict["remove_or_defer"] = ["Remove a compatibility path."]

        self.assertIn(
            "Deferred simplifications require an explicit user decision",
            self.validate(),
        )

    def test_user_approved_deferral_passes(self) -> None:
        self.verdict["verdict"] = "user-deferred"
        self.verdict["remove_or_defer"] = ["Remove a compatibility path."]
        self.verdict["user_decision"] = "User explicitly retained the compatibility path."

        self.assertEqual(self.validate(), [])

    def test_required_invariants_cannot_be_omitted(self) -> None:
        self.verdict["keep"] = []

        self.assertIn(
            "Review must list the capabilities and invariants to preserve",
            self.validate(),
        )

    def test_command_line_accepts_fresh_final_review(self) -> None:
        self.review.write_text(json.dumps(self.verdict))

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--spec",
                str(self.spec),
                "--review",
                str(self.review),
                "--phase",
                "final",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS: fresh final simplification review", result.stdout)

    def test_command_line_rejects_stale_review(self) -> None:
        self.review.write_text(json.dumps(self.verdict))
        self.spec.write_text("# Feature\n\nA newly introduced subsystem.\n")

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--spec",
                str(self.spec),
                "--review",
                str(self.review),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Simplification review is stale", result.stderr)


if __name__ == "__main__":
    unittest.main()

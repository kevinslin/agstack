#!/usr/bin/env python3
"""Tests for the specy flow-doc validator."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "validate_flow_doc.py"
SPEC = importlib.util.spec_from_file_location("validate_flow_doc", SCRIPT_PATH)
assert SPEC is not None
validate_flow_doc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_flow_doc
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_flow_doc)


def build_doc(
    *,
    title: str = "Example Flow",
    frontmatter_extra: str = "",
    legacy_headings: bool = False,
) -> str:
    flow_heading = "Sequence Diagram" if legacy_headings else "Flow"
    debugging_heading = "Observability" if legacy_headings else "Debugging and Verification"
    return f"""---
created: 2026-05-08
updated: 2026-05-08
last_updated_session: codex/session-id
{frontmatter_extra}---

# {title}

## Overview

This flow covers the example behavior.

## Entry Points

- Trigger: An example request arrives.
- Source: `src/example.ts:exampleEntry`

## {flow_heading}

```mermaid
graph TD
  A["Start"] --> B["Done"]
```

## Execution Trace

### 1. Start

`src/example.ts:exampleEntry` starts the flow and delegates to its owner.

## {debugging_heading}

None identified.

## Related docs

- docs/example.md

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog

- 2026-05-08 14:30: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905 - abc123def456)
"""


class FlowDocValidatorTests(unittest.TestCase):
    def validate(self, text: str):
        result = validate_flow_doc.ValidationResult()
        validate_flow_doc._validate_flow_doc(text, result)
        validate_flow_doc._validate_portable_repo_links(text, result)
        return result

    def test_concise_canonical_flow_passes_without_child_steps_or_pseudocode(self) -> None:
        result = self.validate(build_doc())

        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])

    def test_legacy_headings_remain_supported(self) -> None:
        result = self.validate(build_doc(legacy_headings=True))

        self.assertEqual(result.errors, [])

    def test_legacy_mermaid_sequence_diagram_is_preserved(self) -> None:
        result = self.validate(
            build_doc(legacy_headings=True).replace(
                'graph TD\n  A["Start"] --> B["Done"]',
                "sequenceDiagram\n  Alice->>Bob: Start the flow",
            )
        )

        self.assertEqual(result.errors, [])

    def test_canonical_mermaid_sequence_diagram_remains_invalid(self) -> None:
        result = self.validate(
            build_doc().replace(
                'graph TD\n  A["Start"] --> B["Done"]',
                "sequenceDiagram\n  Alice->>Bob: Start the flow",
            )
        )

        self.assertIn(
            "'## Flow' must include a fenced Mermaid 'graph TD' diagram", result.errors
        )

    def test_legacy_empty_mermaid_diagram_is_rejected(self) -> None:
        result = self.validate(
            build_doc(legacy_headings=True).replace(
                'graph TD\n  A["Start"] --> B["Done"]', "sequenceDiagram"
            )
        )

        self.assertIn(
            "'## Sequence Diagram' Mermaid diagram must include actual flow nodes", result.errors
        )

    def test_extensionless_executable_source_pointer_is_accepted(self) -> None:
        result = self.validate(
            build_doc().replace(
                "src/example.ts:exampleEntry",
                "skills/agtask/scripts/agtask:command_resolve_create",
            )
        )

        self.assertEqual(result.errors, [])

    def test_simple_filename_source_pointer_requires_an_extension(self) -> None:
        result = self.validate(
            build_doc().replace("src/example.ts:exampleEntry", "example.ts:exampleEntry")
        )

        self.assertEqual(result.errors, [])

    def test_missing_mermaid_diagram_is_rejected(self) -> None:
        result = self.validate(
            build_doc().replace(
                '```mermaid\ngraph TD\n  A["Start"] --> B["Done"]\n```',
                "Diagram not yet written.",
            )
        )

        self.assertIn(
            "'## Flow' must include a fenced Mermaid 'graph TD' diagram",
            result.errors,
        )

    def test_empty_mermaid_diagram_is_rejected(self) -> None:
        result = self.validate(
            build_doc().replace(
                'graph TD\n  A["Start"] --> B["Done"]',
                "graph TD",
            )
        )

        self.assertIn(
            "'## Flow' Mermaid 'graph TD' diagram must include actual flow nodes",
            result.errors,
        )

    def test_unresolved_braced_placeholders_are_rejected(self) -> None:
        result = self.validate(
            build_doc().replace("This flow covers the example behavior.", "{{behavior}}")
        )

        self.assertIn("Unresolved template placeholder: {{behavior}}", result.errors)

    def test_multiline_braced_placeholders_are_rejected(self) -> None:
        result = self.validate(
            build_doc().replace(
                "This flow covers the example behavior.", "{{Describe the flow\nand its terminal effect}}"
            )
        )

        self.assertIn(
            "Unresolved template placeholder: {{Describe the flow and its terminal effect}}",
            result.errors,
        )

    def test_known_bracket_placeholders_are_rejected(self) -> None:
        result = self.validate(build_doc(title="[Feature] Flow"))

        self.assertIn("Unresolved template placeholder: [Feature]", result.errors)

    def test_template_source_pointer_is_rejected(self) -> None:
        result = self.validate(build_doc().replace("src/example.ts:exampleEntry", "path/to/file.ts:functionName"))

        self.assertIn(
            "Unresolved template placeholder: path/to/file.ts:functionName", result.errors
        )

    def test_manual_notes_body_is_user_owned_and_not_scanned_for_placeholders(self) -> None:
        result = self.validate(
            build_doc().replace(
                "[keep this for the user to add notes. do not change between edits]",
                "[keep this for the user to add notes. do not change between edits]\n{{my private note}}",
            )
        )

        self.assertEqual(result.errors, [])

    def test_phase_without_source_pointer_is_rejected(self) -> None:
        result = self.validate(
            build_doc().replace(
                "`src/example.ts:exampleEntry` starts the flow and delegates to its owner.",
                "The handler starts the flow and delegates to its owner.",
            )
        )

        self.assertIn(
            "### 1. Start must include a real file/function pointer",
            result.errors,
        )

    def test_legacy_phase_without_source_pointer_produces_only_a_warning(self) -> None:
        result = self.validate(
            build_doc(legacy_headings=True).replace(
                "`src/example.ts:exampleEntry` starts the flow and delegates to its owner.",
                "The handler starts the flow and delegates to its owner.",
            )
        )

        self.assertEqual(result.errors, [])
        self.assertIn(
            "### 1. Start must include a real file/function pointer", result.warnings
        )

    def test_changelog_requires_time_session_and_commit_sha(self) -> None:
        for invalid_entry in (
            "- 2026-05-08: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905 - abc123def456)",
            "- 2026-05-08 14:30: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905)",
            "- 2026-05-08 14:30: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905 - nope)",
            "- 2026-05-08 14:30: Created doc. (codex/session-id - abc123def456)",
        ):
            with self.subTest(invalid_entry=invalid_entry):
                result = self.validate(
                    build_doc().replace(
                        "- 2026-05-08 14:30: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905 - abc123def456)",
                        invalid_entry,
                    )
                )

                self.assertTrue(
                    any("Changelog must start with an entry" in error for error in result.errors)
                )

    def test_legacy_changelog_accepts_older_complete_provenance(self) -> None:
        result = self.validate(
            build_doc(legacy_headings=True).replace(
                "## Changelog\n\n",
                "## Changelog\n\n- 2026-05-09: Updated the runtime path.\n",
            )
        )

        self.assertEqual(result.errors, [])

    def test_legacy_changelog_without_any_complete_provenance_is_rejected(self) -> None:
        result = self.validate(
            build_doc(legacy_headings=True).replace(
                "- 2026-05-08 14:30: Created doc. (codex/019f34a7-7791-7c12-8d01-d46a6f74e905 - abc123def456)",
                "- 2026-05-08: Created doc. (codex/session-id)",
            )
        )

        self.assertTrue(
            any("Changelog must contain an entry" in error for error in result.errors)
        )

    def test_canonical_changelog_still_requires_latest_complete_provenance(self) -> None:
        result = self.validate(
            build_doc().replace(
                "## Changelog\n\n",
                "## Changelog\n\n- 2026-05-09: Updated the runtime path.\n",
            )
        )

        self.assertTrue(
            any("Changelog must start with an entry" in error for error in result.errors)
        )

    def test_optional_typescript_pseudocode_is_accepted(self) -> None:
        result = self.validate(
            build_doc().replace(
                "`src/example.ts:exampleEntry` starts the flow and delegates to its owner.",
                "`src/example.ts:exampleEntry` starts the flow.\n\n```ts\nexampleEntry()\n```",
            )
        )

        self.assertEqual(result.errors, [])

    def test_sudocode_fence_is_rejected(self) -> None:
        result = self.validate(
            build_doc().replace(
                "`src/example.ts:exampleEntry` starts the flow and delegates to its owner.",
                "`src/example.ts:exampleEntry` starts the flow.\n\n```sudocode\nexampleEntry()\n```",
            )
        )

        self.assertIn(
            "### 1. Start must use a fenced 'ts' block for $sudocode, not 'sudocode'",
            result.errors,
        )

    def test_empty_debugging_scaffold_is_rejected(self) -> None:
        result = self.validate(build_doc().replace("None identified.", "Metrics:\nLogs:"))

        self.assertIn(
            "'## Debugging and Verification' must include concrete debugging signals or 'None identified'",
            result.errors,
        )

    def test_concrete_debugging_signal_is_accepted(self) -> None:
        result = self.validate(
            build_doc().replace("None identified.", "- Logs: gateway emits example.completed")
        )

        self.assertEqual(result.errors, [])

    def test_pr_flow_passes_with_title_prefix_and_frontmatter(self) -> None:
        result = self.validate(
            build_doc(
                title="PR 79160: Codex Plugin Migration Flow",
                frontmatter_extra="pr: 79160\n",
            )
        )

        self.assertEqual(result.errors, [])

    def test_pr_frontmatter_requires_pr_title_prefix(self) -> None:
        result = self.validate(build_doc(frontmatter_extra="pr: 79160\n"))

        self.assertIn(
            "PR-scoped flow docs must prefix the H1 with 'PR <number>:'",
            result.errors,
        )

    def test_pr_title_prefix_requires_pr_frontmatter(self) -> None:
        result = self.validate(build_doc(title="PR 79160: Codex Plugin Migration Flow"))

        self.assertIn(
            "PR-scoped flow docs must include non-empty frontmatter key: 'pr'",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()

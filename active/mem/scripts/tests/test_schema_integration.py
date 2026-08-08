#!/usr/bin/env python3
"""Integration tests for the schema engine embedded in mem."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TEST_DIR.parents[0] / "schema.py"
REAL_SKILL_DIR = SCRIPT_PATH.parents[1]


class SchemaScriptIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.skill_dir = self.root / "mem"
        self.references_dir = self.skill_dir / "references" / "schemas"
        self.script = self.skill_dir / "scripts" / "schema"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT_PATH, self.script)
        self.script.chmod(self.script.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_schema(self, name: str, schema_yaml: str, templates: dict[str, str]) -> None:
        schema_dir = self.references_dir / name
        schema_dir.mkdir(parents=True)
        (schema_dir / "schema.yaml").write_text(textwrap.dedent(schema_yaml).strip() + "\n", encoding="utf-8")
        for template_name, template in templates.items():
            (schema_dir / template_name).write_text(textwrap.dedent(template).strip() + "\n", encoding="utf-8")

    def install_prod_schema(self, name: str) -> None:
        shutil.copytree(REAL_SKILL_DIR / "references" / "schemas" / name, self.references_dir / name)

    def install_fixture_schema(self, name: str) -> None:
        shutil.copytree(TEST_DIR / "fixtures" / name, self.references_dir / name)

    def run_schema(
        self,
        *args: str,
        cwd: Path | None = None,
        home: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = None
        if home is not None:
            env = dict(os.environ)
            env["HOME"] = str(home)
            env.setdefault("UV_CACHE_DIR", str(Path.home() / ".cache" / "uv"))
        return subprocess.run(
            [str(self.script), *args],
            text=True,
            capture_output=True,
            check=False,
            cwd=cwd,
            env=env,
        )

    def test_schema_show_discovers_nearest_ancestor_schema(self) -> None:
        workspace = self.root / "workspace"
        nested = workspace / "tools" / "example"
        nested.mkdir(parents=True)
        schema = workspace / "schemas" / "workspace-layout" / "schema.yaml"
        schema.parent.mkdir(parents=True)
        schema.write_text(
            "version: 1.0\nschema:\n  tools:\n    description: Local tool projects.\n",
            encoding="utf-8",
        )

        result = self.run_schema("show", "workspace-layout", cwd=nested)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("workspace-layout", result.stdout)
        self.assertIn("tools", result.stdout)

    def test_schema_list_includes_project_local_schemas(self) -> None:
        workspace = self.root / "workspace"
        schema = workspace / "schemas" / "workspace-layout" / "schema.yaml"
        schema.parent.mkdir(parents=True)
        schema.write_text(
            "version: 1.0\nschema:\n  apps:\n    description: Local applications.\n",
            encoding="utf-8",
        )

        result = self.run_schema("list", cwd=workspace)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("workspace-layout\troot: apps", result.stdout)

    def test_schema_show_falls_back_to_global_schema_directory(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        home = self.root / "home"
        schema = home / ".schemas" / "shared-layout" / "schema.yaml"
        schema.parent.mkdir(parents=True)
        schema.write_text(
            "version: 1.0\nschema:\n  shared:\n    description: Global layout.\n",
            encoding="utf-8",
        )

        result = self.run_schema("show", "shared-layout", cwd=workspace, home=home)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("shared-layout", result.stdout)
        self.assertIn("shared", result.stdout)

    def test_unrestricted_path_placeholders_do_not_need_variable_definitions(self) -> None:
        self.write_schema(
            "unrestricted",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                children:
                  "{{slug}}":
                    template: page
            """,
            {"page.md.jinja": "slug={{ slug }}"},
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "unrestricted",
            "--out",
            str(out),
            "--var",
            "slug=custom-page",
            "--include",
            "root/custom-page",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "root" / "custom-page.md").read_text(encoding="utf-8").strip(), "slug=custom-page")

    def test_materialize_without_include_selects_no_files(self) -> None:
        self.write_schema(
            "explicit",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                template: page
            """,
            {"page.md.jinja": "root"},
        )

        result = self.run_schema("materialize", "explicit", "--out", str(self.root / "out"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema 'explicit' produced no files", result.stderr)

    def test_path_style_flag_controls_output_path(self) -> None:
        self.write_schema(
            "pages",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                children:
                  page:
                    template: page
            """,
            {"page.md.jinja": "page"},
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "pages",
            "--out",
            str(out),
            "--include",
            "root/page",
            "--path-style",
            "dotted",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "root.page.md").read_text(encoding="utf-8").strip(), "page")
        self.assertFalse((out / "root" / "page.md").exists())

    def test_schema_output_path_style_is_rejected(self) -> None:
        self.write_schema(
            "legacy",
            """
            version: 1.0
            output:
              path_style: dotted
              file_extension: md
            schema:
              root:
                template: page
            """,
            {"page.md.jinja": "root"},
        )

        result = self.run_schema("show", "legacy")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("path_style", result.stderr)

    def test_children_from_uses_explicit_vars_and_child_defaults_without_parent_inheritance(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            variables:
              name: ["*"]
              child_value: ["*"]
            schema:
              "{{name}}":
                template: parent
                children_from:
                  - schema: child
                    vars:
                      child_name: "{{ child_value }}"
            """,
            {"parent.md.jinja": "parent={{ name }}"},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            variables:
              name: ["*"]
              child_name: ["*"]
              child_default:
                values: ["*"]
                default: defaulted
            schema:
              child:
                template: child
            """,
            {
                "child.md.jinja": "\n".join(
                    [
                        "child_name={{ child_name }}",
                        "parent_name_defined={{ name is defined }}",
                        "child_default={{ child_default }}",
                    ]
                )
            },
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "parent",
            "--out",
            str(out),
            "--var",
            "name=parent-name",
            "--var",
            "child_value=mapped-child",
            "--include",
            "parent-name",
            "--include",
            "parent-name/child",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "parent-name.md").read_text(encoding="utf-8").strip(), "parent=parent-name")
        self.assertEqual(
            (out / "parent-name" / "child.md").read_text(encoding="utf-8").strip(),
            "\n".join(
                [
                    "child_name=mapped-child",
                    "parent_name_defined=False",
                    "child_default=defaulted",
                ]
            ),
        )

    def test_children_from_does_not_inherit_same_named_parent_vars_by_default(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            variables:
              name: ["*"]
            schema:
              "{{name}}":
                children_from:
                  - schema: child
            """,
            {},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            variables:
              name: ["*"]
            schema:
              "{{name}}":
                template: child
            """,
            {"child.md.jinja": "child={{ name }}"},
        )

        result = self.run_schema(
            "materialize",
            "parent",
            "--out",
            str(self.root / "out"),
            "--var",
            "name=parent-name",
            "--include",
            "parent-name/parent-name",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("schema 'parent' produced no files", result.stderr)

    def test_children_from_can_explicitly_plumb_same_named_vars(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            variables:
              name: ["*"]
            schema:
              "{{name}}":
                children_from:
                  - schema: child
                    vars:
                      name: "{{ name }}-child"
            """,
            {},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            variables:
              name: ["*"]
            schema:
              "{{name}}":
                template: child
            """,
            {"child.md.jinja": "child={{ name }}"},
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "parent",
            "--out",
            str(out),
            "--var",
            "name=parent-name",
            "--include",
            "parent-name/parent-name-child",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            (out / "parent-name" / "parent-name-child.md").read_text(encoding="utf-8").strip(),
            "child=parent-name-child",
        )

    def test_missing_child_var_mapping_values_are_omitted_until_needed(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                children_from:
                  - schema: child
                    vars:
                      optional_slug: "{{ optional_slug }}"
            """,
            {},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            schema:
              static:
                template: static
              optional:
                children:
                  "{{optional_slug}}":
                    template: optional
            """,
            {
                "static.md.jinja": "static child",
                "optional.md.jinja": "optional={{ optional_slug }}",
            },
        )

        out = self.root / "out"
        result = self.run_schema("materialize", "parent", "--out", str(out), "--include", "root/static")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "root" / "static.md").read_text(encoding="utf-8").strip(), "static child")
        self.assertFalse((out / "root" / "optional").exists())

        included_out = self.root / "included-out"
        included_result = self.run_schema(
            "materialize",
            "parent",
            "--out",
            str(included_out),
            "--var",
            "optional_slug=detail",
            "--include",
            "root/optional/detail",
        )

        self.assertEqual(included_result.returncode, 0, msg=included_result.stderr)
        self.assertEqual(
            (included_out / "root" / "optional" / "detail.md").read_text(encoding="utf-8").strip(),
            "optional=detail",
        )

    def test_parent_explicit_child_wins_over_mounted_child_conflict(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                children:
                  shared:
                    template: parent-shared
                children_from:
                  - schema: child
            """,
            {"parent-shared.md.jinja": "parent shared"},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            schema:
              shared:
                template: child-shared
              child-only:
                template: child-only
            """,
            {
                "child-shared.md.jinja": "child shared",
                "child-only.md.jinja": "child only",
            },
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "parent",
            "--out",
            str(out),
            "--include",
            "root/shared",
            "--include",
            "root/child-only",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "root" / "shared.md").read_text(encoding="utf-8").strip(), "parent shared")
        self.assertEqual((out / "root" / "child-only.md").read_text(encoding="utf-8").strip(), "child only")

    def test_children_from_path_resolves_relative_to_parent_schema_dir(self) -> None:
        self.write_schema(
            "parent",
            """
            version: 1.0
            output:
              file_extension: md
            schema:
              root:
                children_from:
                  - path: ../child/schema.yaml
            """,
            {},
        )
        self.write_schema(
            "child",
            """
            version: 1.0
            schema:
              child:
                template: child
            """,
            {"child.md.jinja": "child from path"},
        )

        out = self.root / "out"
        result = self.run_schema("materialize", "parent", "--out", str(out), "--include", "root/child")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual((out / "root" / "child.md").read_text(encoding="utf-8").strip(), "child from path")

    def test_show_fixture_schema_renders_path_tree_and_descriptions(self) -> None:
        self.install_prod_schema("code-core")
        self.install_fixture_schema("foo")

        result = self.run_schema("show", "foo")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("|-- tree", result.stdout)
        self.assertIn("    `-- pkg\n", result.stdout)
        self.assertIn("        `-- {{name}}\n", result.stdout)
        self.assertIn("            |-- dev\n", result.stdout)
        self.assertIn("            |   |-- qa\n", result.stdout)
        self.assertIn("            |   `-- obs\n", result.stdout)
        self.assertIn("            |-- api\n", result.stdout)
        self.assertNotIn("descriptions", result.stdout)
        self.assertNotIn("[template=", result.stdout)
        self.assertNotIn("[path-only", result.stdout)

        describe_result = self.run_schema("describe", "foo")

        self.assertEqual(describe_result.returncode, 0, msg=describe_result.stderr)
        self.assertIn("- pkg/{{name}}/dev: this is the foo test", describe_result.stdout)
        self.assertIn("- pkg/{{name}}/dev/qa: testing", describe_result.stdout)
        self.assertIn("- pkg/{{name}}/dev/obs: observability", describe_result.stdout)
        self.assertIn("- pkg/{{name}}/api: api reference", describe_result.stdout)
        self.assertIn("- pkg/{{name}}/api/{{api_name}}: api reference", describe_result.stdout)

    def test_fixture_schema_materializes_code_core_qa_template(self) -> None:
        self.install_prod_schema("code-core")
        self.install_fixture_schema("foo")

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "foo",
            "--out",
            str(out),
            "--var",
            "name=bar",
            "--include",
            "pkg/bar/dev/qa",
            "--skip-existing",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            (out / "pkg" / "bar" / "dev" / "qa.md").read_text(encoding="utf-8").strip(),
            "\n".join(["## Setup", "", "## Unit Tests", "", "## Integration Tests"]),
        )

    def test_tool_schema_expands_code_core_children(self) -> None:
        self.install_prod_schema("code-core")
        self.install_prod_schema("tool")

        result = self.run_schema("show", "tool")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("    `-- {{prefix}}\n", result.stdout)
        self.assertIn("        `-- {{name}}\n", result.stdout)
        self.assertIn("            |-- dev\n", result.stdout)
        self.assertIn("            |   |-- qa\n", result.stdout)
        self.assertIn("            |   `-- obs\n", result.stdout)
        self.assertIn("            |-- api\n", result.stdout)
        self.assertIn("            |   |-- {{api}}\n", result.stdout)
        self.assertIn("            |   `-- {{api_name}}\n", result.stdout)
        self.assertIn("            |-- flow\n", result.stdout)
        self.assertIn("            |   `-- {{flow}}\n", result.stdout)
        describe_result = self.run_schema("describe", "tool")

        self.assertEqual(describe_result.returncode, 0, msg=describe_result.stderr)
        self.assertIn("- {{prefix}}/{{name}}: general description", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/dev: development setup, tests, and debugging", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/dev/qa: how to test changes", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/dev/obs: observability", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/api: public module API namespace", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/api/{{api}}: public interfaces for a module", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/api/{{api_name}}: api reference", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/flow: execution-flow documentation", describe_result.stdout)
        self.assertIn("- {{prefix}}/{{name}}/flow/{{flow}}: flow doc for a specific execution path", describe_result.stdout)

    def test_tool_schema_materializes_mounted_unrestricted_api_name(self) -> None:
        self.install_prod_schema("code-core")
        self.install_prod_schema("tool")

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "tool",
            "--out",
            str(out),
            "--var",
            "prefix=pkg",
            "--var",
            "name=test",
            "--var",
            "api_name=custom-api",
            "--include",
            "pkg.test.api.custom-api",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(
            "# API Reference",
            (out / "pkg.test.api.custom-api.md").read_text(encoding="utf-8"),
        )

    def test_specs_schema_materializes_cook_and_artifact_docs(self) -> None:
        self.install_prod_schema("integ-proof")
        self.install_prod_schema("specs")

        show_result = self.run_schema("show", "specs")

        self.assertEqual(show_result.returncode, 0, msg=show_result.stderr)
        self.assertNotIn("            |-- spec\n", show_result.stdout)
        self.assertIn("        |-- .archive\n", show_result.stdout)
        self.assertIn("            |-- artifacts\n", show_result.stdout)
        self.assertIn("            |-- flows\n", show_result.stdout)
        self.assertIn("            |-- cook\n", show_result.stdout)

        describe_result = self.run_schema("describe", "specs")
        self.assertEqual(describe_result.returncode, 0, msg=describe_result.stderr)
        self.assertIn(
            "- specs/.archive: Completed or superseded spec units, including terminal milestone subspecs, moved here without renaming.",
            describe_result.stdout,
        )
        self.assertIn(
            "- specs/{{spec_number}}-{{spec_slug}}/artifacts: Durable supporting artifacts",
            describe_result.stdout,
        )

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "specs",
            "--out",
            str(out),
            "--path-style",
            "directory",
            "--var",
            "spec_number=1",
            "--var",
            "spec_slug=pilot",
            "--var",
            "artifact=run-release",
            "--var",
            "cook=release-loop",
            "--include",
            "specs/1-pilot/artifacts/run-release",
            "--include",
            "specs/1-pilot/cook/release-loop",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(
            "# Release Loop",
            (out / "specs" / "1-pilot" / "cook" / "release-loop.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "# Run Release",
            (out / "specs" / "1-pilot" / "artifacts" / "run-release.md").read_text(
                encoding="utf-8"
            ),
        )

    def test_project_schema_materializes_root_level_docs(self) -> None:
        self.install_prod_schema("project")

        show_result = self.run_schema("show", "project")

        self.assertEqual(show_result.returncode, 0, msg=show_result.stderr)
        self.assertIn("    |-- specs\n", show_result.stdout)
        self.assertIn("    |-- flows\n", show_result.stdout)
        self.assertIn("    |   `-- {{flow}}\n", show_result.stdout)
        self.assertIn("    |-- cook\n", show_result.stdout)
        self.assertIn("    |   `-- {{cook}}\n", show_result.stdout)
        self.assertIn("    `-- reports\n", show_result.stdout)

        describe_result = self.run_schema("describe", "project")

        self.assertEqual(describe_result.returncode, 0, msg=describe_result.stderr)
        self.assertIn("- specs: Project spec directory.", describe_result.stdout)
        self.assertIn("- flows/{{flow}}: Project-level flow doc", describe_result.stdout)
        self.assertIn("- cook/{{cook}}: Project-level cookbook", describe_result.stdout)
        self.assertIn("- reports/{{report}}: Project-level report.", describe_result.stdout)

        out = self.root / "out"
        materialize_result = self.run_schema(
            "materialize",
            "project",
            "--out",
            str(out),
            "--path-style",
            "directory",
            "--var",
            "flow=devbox-initialization",
            "--var",
            "cook=release-loop",
            "--var",
            "report=security-review",
            "--include",
            "flows/devbox-initialization",
            "--include",
            "cook/release-loop",
            "--include",
            "reports/security-review",
        )

        self.assertEqual(materialize_result.returncode, 0, msg=materialize_result.stderr)
        self.assertIn(
            "# Devbox Initialization Flow",
            (out / "flows" / "devbox-initialization.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "# Release Loop",
            (out / "cook" / "release-loop.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "# Security Review",
            (out / "reports" / "security-review.md").read_text(encoding="utf-8"),
        )

    def test_global_core_schema_shows_and_materializes_guide_reference_and_topic(self) -> None:
        self.install_prod_schema("global-core")

        show_result = self.run_schema("show", "global-core")

        self.assertEqual(show_result.returncode, 0, msg=show_result.stderr)
        self.assertIn("    |-- cook\n", show_result.stdout)
        self.assertIn("    |   `-- {{cook}}\n", show_result.stdout)
        self.assertIn("    |-- ref\n", show_result.stdout)
        self.assertIn("    |   `-- {{reference}}\n", show_result.stdout)
        self.assertIn("    `-- t\n", show_result.stdout)
        self.assertIn("        `-- {{topic}}\n", show_result.stdout)
        describe_result = self.run_schema("describe", "global-core")

        self.assertEqual(describe_result.returncode, 0, msg=describe_result.stderr)
        self.assertIn("- cook: Task-oriented guides", describe_result.stdout)
        self.assertIn("- cook/{{cook}}: Guide for completing", describe_result.stdout)
        self.assertIn("- ref: References for facts", describe_result.stdout)
        self.assertIn("- ref/{{reference}}: Reference for a fact", describe_result.stdout)
        self.assertIn("- t: Topics for domain entities", describe_result.stdout)

        validate_result = self.run_schema("validate", "global-core")

        self.assertEqual(validate_result.returncode, 0, msg=validate_result.stderr)
        self.assertIn("global-core\tvalid\t", validate_result.stdout)
        self.assertIn("- t/{{topic}}: Topic for a domain entity", describe_result.stdout)

        out = self.root / "out"
        materialize_result = self.run_schema(
            "materialize",
            "global-core",
            "--out",
            str(out),
            "--var",
            "cook=configure-slack",
            "--var",
            "reference=shared-fact",
            "--var",
            "topic=account",
            "--include",
            "cook/configure-slack",
            "--include",
            "ref/shared-fact",
            "--include",
            "t/account",
        )

        self.assertEqual(materialize_result.returncode, 0, msg=materialize_result.stderr)
        self.assertIn(
            "## Guide",
            (out / "cook" / "configure-slack.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Reference for a fact",
            (out / "ref" / "shared-fact.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Topic for a domain entity",
            (out / "t" / "account.md").read_text(encoding="utf-8"),
        )

    def test_pkg_schema_composes_code_specs_and_global_core(self) -> None:
        for schema_name in ("global-core", "code-core", "integ-proof", "specs", "pkg"):
            self.install_prod_schema(schema_name)

        show_result = self.run_schema("show", "pkg")
        self.assertEqual(show_result.returncode, 0, msg=show_result.stderr)
        self.assertIn("`-- {{package}}", show_result.stdout)
        self.assertIn("|-- readme", show_result.stdout)
        self.assertIn("`-- specs", show_result.stdout)
        self.assertIn("|-- cook", show_result.stdout)

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "pkg",
            "--out",
            str(out),
            "--path-style",
            "directory",
            "--var",
            "package=clawcmd",
            "--var",
            "cook=configure-service",
            "--var",
            "reference=shared-fact",
            "--var",
            "topic=account",
            "--var",
            "spec_number=1",
            "--var",
            "spec_slug=pilot",
            "--var",
            "artifact=run-release",
            "--include",
            "pkg/clawcmd/readme",
            "--include",
            "pkg/clawcmd/cook/configure-service",
            "--include",
            "pkg/clawcmd/ref/shared-fact",
            "--include",
            "pkg/clawcmd/t/account",
            "--include",
            "pkg/clawcmd/specs/1-pilot/artifacts/run-release",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((out / "pkg" / "clawcmd" / "readme.md").is_file())
        self.assertIn(
            "## Guide",
            (out / "pkg" / "clawcmd" / "cook" / "configure-service.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "Reference for a fact",
            (out / "pkg" / "clawcmd" / "ref" / "shared-fact.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            "Topic for a domain entity",
            (out / "pkg" / "clawcmd" / "t" / "account.md").read_text(encoding="utf-8"),
        )
        self.assertTrue(
            (out / "pkg" / "clawcmd" / "specs" / "1-pilot" / "artifacts" / "run-release.md").is_file()
        )

    def test_ag_dir_schema_materializes_project_and_run_notes(self) -> None:
        self.install_prod_schema("ag-dir")

        show_result = self.run_schema("show", "ag-dir")

        self.assertEqual(show_result.returncode, 0, msg=show_result.stderr)
        self.assertIn("    |-- design\n", show_result.stdout)
        self.assertIn("    `-- .agents\n", show_result.stdout)

        out = self.root / "out"
        result = self.run_schema(
            "materialize",
            "ag-dir",
            "--out",
            str(out),
            "--path-style",
            "directory",
            "--var",
            "project_title=Example Project",
            "--var",
            "spec_num=01",
            "--var",
            "spec_name=bootstrap",
            "--include",
            "design",
            "--include",
            "docs/spec-01-bootstrap",
            "--include",
            ".agents/runs/spec-01/handoff",
            "--include",
            ".agents/runs/spec-01/progress",
            "--include",
            ".agents/runs/spec-01/learnings",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Example Project Design", (out / "design.md").read_text(encoding="utf-8"))
        self.assertTrue((out / "docs" / "spec-01-bootstrap.md").is_file())
        self.assertTrue((out / ".agents" / "runs" / "spec-01" / "handoff.md").is_file())
        self.assertTrue((out / ".agents" / "runs" / "spec-01" / "progress.md").is_file())
        self.assertTrue((out / ".agents" / "runs" / "spec-01" / "learnings.md").is_file())


if __name__ == "__main__":
    unittest.main()

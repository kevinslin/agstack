from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SKILL = ROOT / "skills" / "agtask" / "scripts" / "install-skill"


class SkillzInstallerTest(unittest.TestCase):
    def test_config_only_adds_source_once_and_preserves_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = root / "skillz.json"
            source = root / "source-skills"
            (source / "agtask").mkdir(parents=True)
            (source / "agtask" / "SKILL.md").write_text(
                "---\nname: agtask\ndescription: test\ndependencies: []\n---\n"
            )
            original = {
                "version": "2.0",
                "targets": [{"destination": str(root / "runtime")}],
                "skillDirectories": [{"localPath": "/existing"}],
                "ignore": ["unchanged"],
            }
            config.write_text(json.dumps(original, indent=2) + "\n")

            command = [
                "python3",
                str(INSTALL_SKILL),
                "--config",
                str(config),
                "--source-dir",
                str(source),
                "--config-only",
            ]
            subprocess.run(command, check=True)
            subprocess.run(command, check=True)

            updated = json.loads(config.read_text())
            self.assertEqual(updated["ignore"], ["unchanged"])
            self.assertEqual(updated["skillDirectories"][0], {"localPath": "/existing"})
            self.assertEqual(
                [
                    entry
                    for entry in updated["skillDirectories"]
                    if entry["localPath"] == str(source.resolve())
                ],
                [{"localPath": str(source.resolve())}],
            )

    def test_config_only_relocates_one_missing_same_named_source(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = root / "skillz.json"
            source = root / "new-checkout" / "skills"
            previous = root / "retired-checkout" / "skills"
            (source / "agtask").mkdir(parents=True)
            (source / "agtask" / "SKILL.md").write_text(
                "---\nname: agtask\ndescription: test\ndependencies: []\n---\n"
            )
            config.write_text(
                json.dumps(
                    {
                        "version": "2.0",
                        "targets": [{"destination": str(root / "runtime")}],
                        "skillDirectories": [
                            {"localPath": str(previous), "include": ["agtask"]},
                            {"localPath": "/existing"},
                        ],
                    },
                    indent=2,
                )
                + "\n"
            )

            subprocess.run(
                [
                    "python3",
                    str(INSTALL_SKILL),
                    "--config",
                    str(config),
                    "--source-dir",
                    str(source),
                    "--config-only",
                ],
                check=True,
            )

            updated = json.loads(config.read_text())
            self.assertEqual(
                updated["skillDirectories"],
                [
                    {"localPath": str(source.resolve()), "include": ["agtask"]},
                    {"localPath": "/existing"},
                ],
            )

    def test_config_only_explicitly_replaces_dedicated_agtask_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = root / "skillz.json"
            old_source = root / "old" / "skills"
            new_source = root / "new" / "skills"
            for source in (old_source, new_source):
                (source / "agtask").mkdir(parents=True)
                (source / "agtask" / "SKILL.md").write_text("---\nname: agtask\n---\n")
            config.write_text(
                json.dumps(
                    {
                        "targets": [{"destination": str(root / "runtime")}],
                        "skillDirectories": [
                            {"localPath": str(old_source), "include": ["agtask"]},
                            {"localPath": "/unrelated"},
                            {"localPath": str(new_source)},
                        ],
                    }
                )
            )

            subprocess.run(
                [
                    "python3",
                    str(INSTALL_SKILL),
                    "--config",
                    str(config),
                    "--source-dir",
                    str(new_source),
                    "--config-only",
                    "--replace-existing-source",
                ],
                check=True,
            )

            self.assertEqual(
                json.loads(config.read_text())["skillDirectories"],
                [
                    {"localPath": str(new_source.resolve()), "include": ["agtask"]},
                    {"localPath": "/unrelated"},
                ],
            )

    def test_sync_fails_if_skillz_changes_an_unrelated_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            config = root / "skillz.json"
            source = root / "source-skills"
            runtime = root / "runtime"
            binary_dir = root / "bin"
            (source / "agtask" / "scripts").mkdir(parents=True)
            (source / "agtask" / "SKILL.md").write_text(
                "---\nname: agtask\ndescription: test\ndependencies: []\n---\n"
            )
            cli = source / "agtask" / "scripts" / "agtask"
            cli.write_text("#!/bin/sh\nexit 0\n")
            cli.chmod(0o755)
            (runtime / "other").mkdir(parents=True)
            (runtime / "other" / "SKILL.md").write_text("original\n")
            config.write_text(
                json.dumps(
                    {
                        "version": "2.0",
                        "targets": [{"destination": str(runtime)}],
                        "skillDirectories": [{"localPath": str(source)}],
                    },
                    indent=2,
                )
                + "\n"
            )

            binary_dir.mkdir()
            fake_skillz = binary_dir / "skillz"
            fake_skillz.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    case " $* " in
                      *" --dry-run "*) exit 0 ;;
                    esac
                    mkdir -p "{runtime}/agtask"
                    cp -R "{source}/agtask/." "{runtime}/agtask/"
                    printf 'changed\\n' > "{runtime}/other/SKILL.md"
                    """
                )
            )
            fake_skillz.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = str(binary_dir) + os.pathsep + environment["PATH"]
            result = subprocess.run(
                [
                    "python3",
                    str(INSTALL_SKILL),
                    "--config",
                    str(config),
                    "--source-dir",
                    str(source),
                ],
                text=True,
                capture_output=True,
                env=environment,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "scoped skillz sync changed unrelated installed skills: other",
                result.stderr,
            )


if __name__ == "__main__":
    unittest.main()

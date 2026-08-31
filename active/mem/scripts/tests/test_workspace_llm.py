"""Exercise Codex's subprocess boundary without calling a paid model in tests."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_llm import InferenceError, infer_projects


FAKE_CODEX = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
capture = pathlib.Path(os.environ["WORKSPACE_TEST_CAPTURE"])
capture.write_text(json.dumps({"args": args, "prompt": prompt, "cwd": os.getcwd(),
    "schema": json.loads(pathlib.Path(args[args.index("--output-schema")+1]).read_text()),
    "thread_id": os.environ.get("CODEX_THREAD_ID")}))
mode = os.environ.get("WORKSPACE_TEST_MODE", "success")
if mode == "fail":
    print("Error: configured test failure", file=sys.stderr)
    sys.exit(1)
if mode == "timeout":
    time.sleep(30)
output = pathlib.Path(args[args.index("--output-last-message")+1])
output.write_text("not json" if mode == "malformed" else '{"projects": []}')
print(json.dumps({"type": "turn.started" if mode == "unfinished" else "turn.completed"}))
'''


class WorkspaceInferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "codex-home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        codex = self.bin / "codex"
        codex.write_text(FAKE_CODEX)
        codex.chmod(0o755)
        self.capture = self.root / "capture.json"
        self.environment = mock.patch.dict(os.environ, {
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "WORKSPACE_TEST_CAPTURE": str(self.capture),
            "CODEX_THREAD_ID": "parent-task-should-not-be-inherited",
        })
        self.environment.start()
        self.schema = {"type": "object", "properties": {"projects": {"type": "array"}}}

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp.cleanup()

    def test_inference_is_scoped_and_only_model_and_login_settings_are_inherited(self) -> None:
        config = self.home / "config.toml"
        original = ('model = "configured-model"\nmodel_reasoning_effort = "high"\n'
                    'forced_chatgpt_workspace_id = "workspace-scope"\n'
                    'notify = ["unexpected-notifier"]\n'
                    '[mcp_servers.unrelated]\ncommand = "unexpected-mcp-server"\n')
        config.write_text(original)
        packet = {"work": [{"id": "w1", "text": "A quoted request with `$(text)` and unicode: café"}]}
        result = infer_projects(packet, self.schema, codex_home=self.home)
        self.assertEqual(result, {"projects": []})
        captured = json.loads(self.capture.read_text())
        args = captured["args"]
        self.assertIn('--ignore-user-config', args)
        self.assertIn('--ephemeral', args)
        self.assertIn('--strict-config', args)
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        for setting in ('approval_policy="never"', 'agents.enabled=false',
                        'model="configured-model"', 'forced_chatgpt_workspace_id="workspace-scope"'):
            self.assertIn(setting, args)
        for feature in ('apps', 'plugins', 'hooks', 'shell_tool', 'unified_exec'):
            self.assertTrue(any(args[i:i+2] == ['--disable', feature] for i in range(len(args)-1)))
        self.assertNotIn('unexpected-notifier', ' '.join(args))
        self.assertNotIn('unexpected-mcp-server', ' '.join(args))
        self.assertEqual(json.loads(captured['prompt'].split('Collected evidence:\n', 1)[1]), packet)
        self.assertEqual(captured['schema'], self.schema)
        self.assertIsNone(captured['thread_id'])
        self.assertFalse(Path(captured['cwd']).exists(), 'Inference scratch files must be cleaned up')
        self.assertEqual(config.read_text(), original)

    def test_failed_or_incomplete_inference_is_not_accepted(self) -> None:
        for mode in ('fail', 'malformed', 'unfinished'):
            with self.subTest(mode=mode), mock.patch.dict(os.environ, {'WORKSPACE_TEST_MODE': mode}):
                with self.assertRaises(InferenceError):
                    infer_projects({}, self.schema, codex_home=self.home)
                captured = json.loads(self.capture.read_text())
                self.assertFalse(Path(captured['cwd']).exists())

    def test_timeout_stops_inference_and_removes_its_scratch_files(self) -> None:
        with mock.patch.dict(os.environ, {'WORKSPACE_TEST_MODE': 'timeout'}), \
             mock.patch('workspace_llm.INFERENCE_TIMEOUT_SECONDS', 0.5):
            with self.assertRaisesRegex(InferenceError, 'timed out'):
                infer_projects({}, self.schema, codex_home=self.home)
        captured = json.loads(self.capture.read_text())
        self.assertFalse(Path(captured['cwd']).exists())


if __name__ == '__main__':
    unittest.main()

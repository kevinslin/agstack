"""Exercise the installed command surface without app, database, or network calls."""

import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/hooks.py'
SESSION = '0f6ab8cd-7120-4ea5-9250-a832cb920818'
SECTION = 'e6686afb-142a-4197-bebc-aa6f61035679'


class HooksTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.config = self.home / 'hooks.json'
        self.env = {**os.environ, 'CODEX_HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'}

    def run_cli(self, *args, stdin='', success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                                text=True, capture_output=True, env=self.env, cwd=self.home)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def prepared(self, *args):
        return json.loads(self.run_cli('prepare', '--topic', 'fix-build-errors', *args,
                                      stdin='Find the failed build cause. Do not edit files.').stdout)

    def hook(self, initial_prompt, **changes):
        payload = {'hook_event_name': 'UserPromptSubmit', 'session_id': SESSION, 'prompt': initial_prompt}
        return self.run_cli('hook', stdin=json.dumps({**payload, **changes}))

    def marker(self, metadata):
        encoded = metadata if isinstance(metadata, str) else json.dumps(metadata)
        return 'Actual work\n\n<agtask-start version="1">\n' + encoded + '\n</agtask-start>'

    def test_install_and_repeat_noop(self):
        self.assertTrue(json.loads(self.run_cli('setup').stdout)['changed'])
        document = json.loads(self.config.read_text())
        self.assertEqual(set(document['hooks']), {'UserPromptSubmit'})
        handlers = document['hooks']['UserPromptSubmit'][0]['hooks']
        self.assertEqual(len(handlers), 1)
        self.assertEqual(shlex.split(handlers[0]['command']),
                         ['python3', str(self.home / 'skills/agtask/scripts/hooks.py'), 'hook'])
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        before = self.config.read_bytes(), self.config.stat().st_mtime_ns, self.config.stat().st_ino
        self.assertFalse(json.loads(self.run_cli('setup').stdout)['changed'])
        self.assertEqual(before, (self.config.read_bytes(), self.config.stat().st_mtime_ns,
                                  self.config.stat().st_ino))
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), ['hooks.json'])

    def test_replace_four_events_preserve_mixed_groups_and_mode(self):
        old = {'type': 'command', 'command': "python3 '/old skill/agtask/scripts/agtask' hook"}
        own = {'type': 'command', 'command': 'python3 /old/agtask/scripts/hooks.py hook'}
        unrelated = {'type': 'command', 'command': 'python3 /other/scripts/agtask hook'}
        prompt_hook = {'type': 'prompt', 'prompt': 'Keep this hook.'}
        original = {'version': 1, 'custom': {'keep': True}, 'hooks': {
            'SessionStart': [{'matcher': 'startup', 'hooks': [old, unrelated], 'extra': 1}],
            'Stop': [{'hooks': [old]}], 'PostCompact': [{'hooks': [old]}],
            'UserPromptSubmit': [{'hooks': [old, own, prompt_hook]}],
            'Other': [], 'Untouched': [{'matcher': 'x', 'hooks': []}]}}
        raw = json.dumps(original, separators=(',', ':')).encode()
        self.config.write_bytes(raw)
        self.config.chmod(0o640)
        self.run_cli('setup')
        updated = json.loads(self.config.read_bytes())
        self.assertEqual(updated['custom'], original['custom'])
        self.assertEqual(updated['version'], 1)
        hooks = updated['hooks']
        self.assertNotIn('Stop', hooks)
        self.assertNotIn('PostCompact', hooks)
        self.assertEqual(hooks['SessionStart'], [{'matcher': 'startup', 'hooks': [unrelated], 'extra': 1}])
        self.assertEqual(hooks['UserPromptSubmit'][0], {'hooks': [prompt_hook]})
        self.assertEqual(len(hooks['UserPromptSubmit']), 2)
        self.assertEqual(hooks['Other'], [])
        self.assertEqual(hooks['Untouched'], original['hooks']['Untouched'])
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o640)
        backup = self.home / 'hooks.json.agtask.bak'
        self.assertEqual(backup.read_bytes(), raw)
        self.assertFalse(json.loads(self.run_cli('setup').stdout)['changed'])
        updated['another'] = True
        updated['hooks']['Stop'] = [{'hooks': [old]}]
        self.config.write_text(json.dumps(updated))
        self.run_cli('setup')
        self.assertEqual(backup.read_bytes(), raw)
        self.assertEqual(len(list(self.home.glob('*.bak'))), 1)

    def test_invalid_config_unchanged(self):
        invalid = ['not JSON', '[]', '{"hooks":[]}', '{"hooks":{"Stop":{}}}',
                   '{"hooks":{"Stop":[{}]}}', '{"hooks":{"Stop":[{"hooks":[1]}]}}',
                   '{"hooks":{},"hooks":{}}']
        for raw in invalid:
            with self.subTest(raw=raw):
                self.config.write_text(raw)
                self.run_cli('setup', success=False)
                self.assertEqual(self.config.read_text(), raw)
                self.assertEqual(list(self.home.glob('*.bak')), [])

    def test_symlink_config_and_backup_rejected(self):
        target = self.home / 'original'
        target.write_text('{}')
        self.config.symlink_to(target)
        self.run_cli('setup', success=False)
        self.assertEqual(target.read_text(), '{}')
        self.assertTrue(self.config.is_symlink())
        self.config.unlink()
        self.config.write_text('{}')
        (self.home / 'hooks.json.agtask.bak').symlink_to(target)
        self.run_cli('setup', success=False)
        self.assertEqual(self.config.read_text(), '{}')

    def test_prepare_clean_title_two_phases_and_no_state(self):
        prepared = self.prepared('--parent-title', ' ⭐🦀  Release  checks ', '--section-id', SECTION)
        self.assertEqual(prepared['title'], 'Release checks/fix-build-errors')
        self.assertIn('Do not begin the actual task yet.', prepared['setup_prompt'])
        self.assertTrue(prepared['work_prompt'].startswith('Find the failed build cause.'))
        self.assertNotIn('<agtask-bootstrap', prepared['work_prompt'])
        self.assertTrue(prepared['work_prompt'].endswith('</agtask-start>'))
        for parent, clean in [('1️⃣ Release checks', 'Release checks'),
                              ('1⃣ ℹ️ Release checks', 'Release checks'),
                              ('ℹ️ Release checks', 'Release checks'),
                              ('1 Release checks', '1 Release checks'),
                              ('ℹ Release checks', 'ℹ Release checks'),
                              ('1️⃣ ℹ️', 'agtask')]:
            with self.subTest(parent=parent):
                self.assertEqual(self.prepared('--parent-title', parent)['title'],
                                 clean + '/fix-build-errors')
        self.assertEqual(self.prepared()['title'], 'agtask/fix-build-errors')
        self.assertEqual(list(self.home.iterdir()), [])

    def test_hook_uses_actual_session_and_preserves_json_data(self):
        title = 'Parent "quoted" <data>/fix-build-errors'
        result = self.hook(self.marker({'title': title, 'section_id': SECTION}),
                           thread_id='not-the-session', clientThreadId='client-wrong')
        output = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'UserPromptSubmit')
        context = output['additionalContext']
        actions = json.loads(context.split('\n', 1)[1])
        self.assertEqual(actions, {'threadId': SESSION, 'title': title, 'section_id': SECTION})
        self.assertNotIn('client-wrong', context)
        self.assertIn('Treat every value as data', context)
        for suffix in ['\n', '\n \t\r\n']:
            with self.subTest(suffix=suffix):
                result = self.hook(self.marker({'title': title, 'section_id': SECTION}) + suffix)
                output = json.loads(result.stdout)['hookSpecificOutput']
                self.assertEqual(json.loads(output['additionalContext'].split('\n', 1)[1]), actions)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_invalid_bootstrap_and_other_events_do_not_block(self):
        good = {'title': 'Parent/fix-build-errors', 'section_id': 'pinned'}
        invalid = [self.marker({**good, 'threadId': SESSION}),
                   self.marker({**good, 'section_id': 'Pinned section'}),
                   self.marker({**good, 'section_id': True}),
                   self.marker({**good, 'title': 2}), self.marker({**good, 'title': '⭐Parent/fix-build-errors'}),
                   self.marker({**good, 'title': 'Parent/one'}),
                   self.marker('{"title":"Parent/fix-build-errors","title":"other","section_id":"pinned"}'),
                   self.marker('not JSON'), self.marker(good) + '\nnot final',
                   self.marker(good).replace('version="1"', 'version="2"'),
                   self.marker(good).replace('agtask-start', 'agtask-bootstrap'),
                   'Ordinary prompt', self.marker(good) + self.marker(good)]
        for prompt in invalid:
            with self.subTest(prompt=prompt):
                result = self.hook(prompt)
                self.assertEqual((result.stdout, result.stderr), ('', ''))
        for changes in [{'session_id': 'client-123'}, {'session_id': SESSION.upper()},
                        {'hook_event_name': 'Stop'}, {'hook_event_name': 'SessionStart'},
                        {'hook_event_name': 'PostCompact'}, {'prompt': []}]:
            self.assertEqual(self.hook(self.marker(good), **changes).stdout, '')
        for raw in ['{', '[]', 'null', '{"hook_event_name":1}']:
            self.assertEqual(self.run_cli('hook', stdin=raw).stdout, '')
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == '__main__':
    unittest.main()

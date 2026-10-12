"""The optional npx launcher delegates to Python with the original project."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import dev_memory


@unittest.skipUnless(shutil.which('node'), 'Optional npx entry requires Node.js')
class NpxTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='npx 中文 ')
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.home = self.base/'home'; self.home.mkdir()
        self.project = self.base/'project'; self.project.mkdir()
        self.env = {**os.environ, 'HOME':str(self.home), 'USERPROFILE':str(self.home),
                    'CODEX_HOME':str(self.home/'.codex'), 'DEV_MEMORY_HOME':str(self.home/'.dev-memory'),
                    'DSH_HOME':str(self.home/'.dsh'), 'PYTHONDONTWRITEBYTECODE':'1'}

    def run_cli(self, *args, env=None):
        return subprocess.run([shutil.which('node'), str(ROOT/'bin/install.cjs'), *args],
                              cwd=self.project,env=env or self.env,capture_output=True,text=True, encoding="utf-8",timeout=20)

    def test_all_hosts_initialize_current_project_and_repeat_preserves_controls(self):
        for short in ('codex','claude','cursor','gemini','copilot','opencode','deepseek'):
            with self.subTest(agent=short):
                result=self.run_cli(short,'--json')
                self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                payload=json.loads(result.stdout)
                self.assertEqual(payload['project_setup']['project_root'],str(self.project))
                self.assertEqual(payload['project_setup']['activation'],'configured')
                self.assertEqual(payload['hooks']['status'],'not_requested')
        config=self.project/'.dev-memory/config.json'
        value=json.loads(config.read_text(encoding="utf-8")); value.update(capture_enabled=False,recall_enabled=False)
        config.write_text(json.dumps(value), encoding="utf-8"); before=config.read_bytes()
        result=self.run_cli('codex','--json')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(config.read_bytes(),before)
        bindings=json.loads((self.project/'.dev-memory/activation.json').read_text(encoding="utf-8"))['bindings']
        self.assertEqual(set(bindings),set(dev_memory.AGENT_DIRS))
        self.assertNotIn('node_modules',json.dumps(bindings))

    def test_deepseek_aliases_custom_home_and_repeat_preserve_project_controls(self):
        custom = self.home/'DSH custom home'
        env = {**self.env, 'DSH_HOME':str(custom)}
        guide = self.project/'AGENTS.md'
        guide.write_text('Keep the team instructions.\n', encoding="utf-8")
        before = None
        for short in ('deepseek','dsh','deepseek-harness'):
            result = self.run_cli(short,'--json',env=env)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(Path(payload['path']),custom/'skills/dev-memory')
            self.assertEqual(payload['project_setup']['agent'],'deepseek-harness')
            self.assertIn('Keep the team instructions.',guide.read_text(encoding="utf-8"))
            binding = json.loads((self.project/'.dev-memory/activation.json').read_text(encoding="utf-8"))['bindings']['deepseek-harness']
            self.assertEqual(Path(binding['skill_file']),custom/'skills/dev-memory/SKILL.md')
            config = self.project/'.dev-memory/config.json'
            if before is None:
                value = json.loads(config.read_text(encoding="utf-8")); value['capture_enabled'] = False
                config.write_text(json.dumps(value), encoding="utf-8"); before = config.read_bytes()
            else:
                self.assertEqual(config.read_bytes(),before)
        self.assertFalse((self.home/'.dsh').exists())

    def test_deepseek_explicit_target_overrides_home(self):
        target = self.home/'explicit skill'
        result = self.run_cli('deepseek','--target',str(target),'--json')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(Path(json.loads(result.stdout)['path']),target)
        self.assertFalse((self.home/'.dsh').exists())

    def test_custom_target_and_explicit_project_take_precedence(self):
        other=self.base/'other'; other.mkdir()
        target=self.home/'custom'
        result=self.run_cli('--agent','claude',f'--project={other}','--target',str(target),'--json')
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        payload=json.loads(result.stdout)
        self.assertEqual(payload['project_setup']['project_root'],str(other))
        self.assertEqual(payload['path'],str(target))
        self.assertFalse((self.project/'.dev-memory').exists())

    def test_help_unknown_host_and_conflicting_arguments_do_not_initialize(self):
        for args,expected in ((['--help'],0),(['unknown','--json'],2),
                              (['codex','--agent','claude','--json'],2),(['--json'],2)):
            with self.subTest(args=args):
                result=self.run_cli(*args)
                self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
                self.assertFalse((self.project/'.dev-memory').exists())
                self.assertEqual(list(self.home.iterdir()),[])

    def test_source_failure_does_not_become_wrapper_success(self):
        (self.project/'AGENTS.md').write_text('<!-- dev-memory:managed:start -->', encoding="utf-8")
        result=self.run_cli('codex','--json')
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['status'],'failed')
        self.assertFalse((self.project/'.dev-memory').exists())

    def test_missing_python_returns_nonzero_receipt_without_writes(self):
        empty=self.base/'empty'; empty.mkdir()
        if os.name == 'nt':
            # Windows can find py.exe through system locations even with an empty PATH.
            shim = self.base/'no-python.cjs'
            shim.write_text("require('node:child_process').spawnSync = () => ({error: {code: 'ENOENT'}, status: null});", encoding='utf-8')
            result = subprocess.run([shutil.which('node'), '--require', str(shim), str(ROOT/'bin/install.cjs'), 'codex', '--json'],
                                    cwd=self.project, env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=20)
        else:
            result=self.run_cli('codex','--json',env={**self.env,'PATH':str(empty)})
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['error'],'python_unavailable')
        self.assertFalse((self.project/'.dev-memory').exists())
        self.assertEqual(list(self.home.iterdir()),[])

    def test_npm_manifest_has_no_dependencies_or_install_side_effects(self):
        package=json.loads((ROOT/'package.json').read_text(encoding="utf-8"))
        self.assertEqual(package['bin'],{'dev-memory':'bin/install.cjs'})
        self.assertFalse(package.get('dependencies'))
        self.assertFalse(package.get('devDependencies'))
        self.assertFalse(package.get('scripts'))
        self.assertEqual(set(package['files']),{'install.py','bin/install.cjs','LICENSE',
                            *('skills/dev-memory/'+name for name in dev_memory.SKILL_FILES)})

    @unittest.skipUnless(shutil.which('npm'), 'npm pack check requires npm')
    def test_npm_package_contains_only_public_whitelist(self):
        source=self.base/'source'; source.mkdir()
        package=json.loads((ROOT/'package.json').read_text(encoding="utf-8"))
        for name in [*package['files'],'package.json','README.md']:
            target=source/name; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)
        for name in ('skills/dev-memory/customer.sqlite3','skills/dev-memory/.dev-memory/memory.sqlite3',
                     '.dev-memory/memory.sqlite3','private-notes.md'):
            target=source/name; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text('synthetic data that must not be packaged', encoding="utf-8")
        result=subprocess.run([shutil.which('npm'),'pack','--dry-run','--json','--ignore-scripts',
                               '--cache',str(self.base/'cache')],cwd=source,env=self.env,
                              capture_output=True,text=True, encoding="utf-8",timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        paths={entry['path'] for entry in json.loads(result.stdout)[0]['files']}
        self.assertEqual(paths,set(package['files'])|{'package.json','README.md'})


if __name__=='__main__':
    unittest.main()

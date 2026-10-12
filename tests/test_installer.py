"""Installer UX regressions; all writes use synthetic temporary homes."""
from __future__ import annotations

import builtins
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import install as installer
import dev_memory
import dev_memory_store as store


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix='dev-memory installer 中文 ')
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
                    'CODEX_HOME': str(self.home / '.codex'), 'DEV_MEMORY_HOME': str(self.home / '.dev-memory'),
                    'DSH_HOME': str(self.home / '.dsh'), 'PYTHONDONTWRITEBYTECODE': '1'}

    def run_installer(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, '-B', str(ROOT / 'install.py'), *args],
                              cwd=self.home, env=self.env, text=True, encoding="utf-8", capture_output=True, timeout=15)

    def test_all_short_names_check_runtime_and_keep_empty_data(self) -> None:
        for agent, relative in dev_memory.AGENT_DIRS.items():
            short = next((key for key, value in installer.ALIASES.items() if value == agent), agent)
            with self.subTest(agent=agent):
                result = self.run_installer(short, '--json')
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload['status'], 'installed')
                self.assertEqual(payload['runtime_check']['status'], 'passed')
                self.assertEqual(Path(payload['path']), self.home / relative / 'dev-memory')
                self.assertEqual(payload['hooks']['status'], 'not_requested')
        self.assertFalse((self.home / '.dev-memory').exists())
        self.assertFalse((self.home / '.codex/hooks.json').exists())

    def test_no_agent_in_pipe_fails_without_installing_codex(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 2)
        self.assertIn('请指定 AI', result.stderr)
        self.assertFalse((self.home / '.agents').exists())

    def test_deepseek_home_cannot_point_into_memory_data(self) -> None:
        self.env['DSH_HOME'] = str(self.home / '.dev-memory')
        result = self.run_installer('deepseek', '--project', str(self.home / 'project'), '--json')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['error'], 'path_escape')
        self.assertFalse((self.home / '.dev-memory').exists())

    def test_public_program_directory_modes_do_not_change_memory_policy(self) -> None:
        original = Path.mkdir
        for platform, expected in (('win32', 0o755), ('linux', 0o700)):
            modes = []
            def mkdir(path, mode=0o777, parents=False, exist_ok=False):
                modes.append(mode)
                return original(path, mode=mode, parents=parents, exist_ok=exist_ok)
            target = self.home / platform
            with patch.object(dev_memory.sys, 'platform', platform), patch.object(Path, 'mkdir', mkdir):
                dev_memory._copy_release(target)
            self.assertTrue(modes)
            self.assertTrue(all(mode == expected for mode in modes), modes)
            self.assertEqual((target / 'SKILL.md').read_bytes(), (ROOT / 'skills/dev-memory/SKILL.md').read_bytes())

    def test_legacy_pipe_encoding_preserves_unicode_project_binding(self) -> None:
        self.env['PYTHONIOENCODING'] = 'cp1252'
        project = self.home / 'project'
        project.mkdir()
        result = self.run_installer('codex', '--project', str(project), '--json')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'installed')
        self.assertEqual(payload['project_setup']['project_root'], str(project))
        config = json.loads((project / '.dev-memory/config.json').read_text(encoding='utf-8'))
        self.assertEqual(config['project_root'], str(project))

    @unittest.skipUnless(sys.platform == 'win32', 'Actual Windows ACL regression')
    def test_windows_upgrade_inherits_public_acl_but_preserves_private_store_acl(self) -> None:
        parent = self.home / 'acl-parent'
        parent.mkdir()
        # A synthetic read principal on one temporary parent; no real-user ACLs.
        subprocess.run(['icacls', str(parent), '/grant', '*S-1-5-32-545:(OI)(CI)(RX)'],
                       check=True, capture_output=True, text=True, timeout=10)
        target = parent / 'dev-memory'
        with patch.object(dev_memory.sys, 'platform', 'old-policy'):
            dev_memory._copy_release(target)  # Reproduce the former Windows 0700 ACL.
        store.init_global(parent / 'private-memory')
        def read_acl(path):
            script = '''$a=Get-Acl -LiteralPath $env:DM_ACL_TEST_PATH;
$rules=@($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {[pscustomobject]@{sid=$_.IdentityReference.Value;inherited=$_.IsInherited;allow=$_.AccessControlType.ToString();rights=[int64]$_.FileSystemRights}});
[pscustomobject]@{protected=$a.AreAccessRulesProtected;rules=$rules} | ConvertTo-Json -Depth 5 -Compress'''
            result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                                    env={**os.environ, 'DM_ACL_TEST_PATH': str(path)},
                                    capture_output=True, text=True, check=True, timeout=15)
            return json.loads(result.stdout)
        def readable(acl):
            return any(r['sid'] == 'S-1-5-32-545' and r['allow'] == 'Allow' and r['rights'] & 131241 == 131241
                       for r in acl['rules'])
        self.assertTrue(readable(read_acl(parent)), read_acl(parent))
        self.assertFalse(readable(read_acl(target)), read_acl(target))
        result = dev_memory.install(target, with_hooks=False, upgrade=True)
        self.assertEqual(result['program_permissions'], 'inherited_windows_acl')
        self.assertFalse(result['sandbox_access_verified'])
        for path in (target, target / 'scripts', target / 'scripts/dev_memory.py', target / 'SKILL.md'):
            self.assertTrue(readable(read_acl(path)), read_acl(path))
        self.assertFalse(readable(read_acl(parent / 'private-memory/global')))

    def test_interactive_selection_installs_requested_host_and_prints_next_step(self) -> None:
        stdout = io.StringIO()
        with patch.dict(os.environ, self.env), patch.object(sys.stdin, 'isatty', return_value=True), \
                patch('builtins.input', return_value='2'), contextlib.redirect_stdout(stdout):
            status = installer.main([])
        self.assertEqual(status, 0)
        self.assertTrue((self.home / '.claude/skills/dev-memory/SKILL.md').is_file())
        self.assertFalse((self.home / '.agents').exists())
        self.assertIn('基础命令检查通过', stdout.getvalue())
        self.assertIn('--project', stdout.getvalue())
        self.assertNotIn('发送：', stdout.getvalue())
        self.assertFalse((self.home / '.dev-memory').exists())

    def test_cancel_and_invalid_selection_do_not_install(self) -> None:
        for response in (KeyboardInterrupt(), EOFError(), '0', '99', 'unknown'):
            with self.subTest(response=str(response)), patch.dict(os.environ, self.env), \
                    patch.object(sys.stdin, 'isatty', return_value=True), \
                    patch('builtins.input', side_effect=response if isinstance(response, BaseException) else None,
                          return_value=response), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                if isinstance(response, BaseException):
                    self.assertEqual(installer.main([]), 130)
                else:
                    with self.assertRaises(SystemExit) as exc:
                        installer.main([])
                    self.assertEqual(exc.exception.code, 2)
        self.assertFalse((self.home / '.agents').exists())
        self.assertFalse((self.home / '.claude').exists())

    def test_legacy_selector_and_explicit_target_work(self) -> None:
        target = self.home / '自定义 skill'
        result = self.run_installer('--agent', 'claude-code', '--target', str(target), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)['path']), target)

    def test_conflicting_selectors_fail_without_writes(self) -> None:
        result = self.run_installer('codex', '--agent', 'claude-code')
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.home / '.agents').exists())

    def test_existing_install_requires_upgrade_and_preserves_memory(self) -> None:
        self.assertEqual(self.run_installer('codex').returncode, 0)
        store.init_global(self.home / '.dev-memory')
        database = store.global_paths(self.home / '.dev-memory')[1]
        before = hashlib.sha256(database.read_bytes()).digest()
        config = store.global_paths(self.home / '.dev-memory')[0] / 'config.json'
        config_before = config.read_bytes()
        hooks = self.home / '.codex/hooks.json'
        hooks.parent.mkdir()
        hooks.write_text('{"hooks":{"UnrelatedEvent":[]},"custom":true}', encoding="utf-8")
        hooks_before = hooks.read_bytes()
        result = self.run_installer('codex')
        self.assertEqual(result.returncode, 1)
        self.assertIn('--upgrade', result.stderr)
        result = self.run_installer('codex', '--upgrade', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, hashlib.sha256(database.read_bytes()).digest())
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(hooks.read_bytes(), hooks_before)

    def test_unknown_extra_files_block_upgrade(self) -> None:
        self.assertEqual(self.run_installer('codex').returncode, 0)
        extra = self.home / '.agents/skills/dev-memory/user-notes.md'
        extra.write_text('synthetic user file', encoding="utf-8")
        result = self.run_installer('codex', '--upgrade', '--json')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['error'], 'unmanaged_files')
        self.assertEqual(extra.read_text(encoding="utf-8"), 'synthetic user file')

    def test_failed_runtime_check_does_not_claim_success(self) -> None:
        for index, value in enumerate(('{}', '[]', 'not-json', '{"status":"ok","base_mode":"available"}')):
            with self.subTest(diagnostic=value):
                stdout = io.StringIO()
                bad_result = subprocess.CompletedProcess([], 0, stdout=value, stderr='')
                with patch.dict(os.environ, self.env), patch.object(installer.subprocess, 'run', return_value=bad_result), \
                        contextlib.redirect_stdout(stdout):
                    status = installer.main(['codex', '--target', str(self.home / f'install-{index}'), '--json'])
                payload = json.loads(stdout.getvalue())
                self.assertEqual(status, 1)
                self.assertEqual(payload['status'], 'failed')
                self.assertIn('path', payload)
                self.assertNotIn('runtime_check', payload)

    def test_old_python_and_missing_sqlite_have_clear_errors(self) -> None:
        stderr = io.StringIO()
        with patch.object(sys, 'version_info', (3, 9, 0)), contextlib.redirect_stderr(stderr):
            self.assertEqual(installer.main(['codex']), 2)
        self.assertIn('Python 3.10+', stderr.getvalue())
        real_import = builtins.__import__
        def blocked_import(name, *args, **kwargs):
            if name == 'sqlite3':
                raise ImportError('synthetic missing sqlite')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=blocked_import), contextlib.redirect_stderr(stderr):
            self.assertEqual(installer.main(['codex']), 2)
        self.assertIn('sqlite3', stderr.getvalue())
        self.assertFalse((self.home / '.agents').exists())


if __name__ == '__main__':
    unittest.main()

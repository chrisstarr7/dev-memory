"""Project default activation regressions; no real homes or memories."""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import dev_memory
import dev_memory_setup as setup
import dev_memory_store as store


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix='dev-memory activation 中文 ')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name).resolve()
        self.project = self.home / 'project A'
        self.project.mkdir()
        self.global_root = self.home / 'private-global'
        self.skill = ROOT / 'skills/dev-memory'

    def activate(self, agent='codex'):
        return setup.setup(self.project, agent, self.skill, sys.executable, self.global_root)

    def test_one_command_installs_and_activates_empty_stores_idempotently(self):
        env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
               'CODEX_HOME': str(self.home / '.codex'), 'DEV_MEMORY_HOME': str(self.global_root)}
        cmd = [sys.executable, '-B', str(ROOT / 'install.py'), 'codex', '--project', str(self.project), '--json']
        for _ in range(2):
            run = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            result = json.loads(run.stdout)
            self.assertEqual(result['project_setup']['activation'], 'configured')
            self.assertEqual(result['runtime_check']['status'], 'passed')
        self.assertEqual((self.project / 'AGENTS.md').read_text(encoding="utf-8").count(setup.BEGIN), 1)
        for db in (store.project_paths(self.project)[1], store.global_paths(self.global_root)[1]):
            with contextlib.closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute('select count(*) from memories').fetchone()[0], 0)

    def test_existing_instructions_and_override_are_preserved(self):
        (self.project / 'AGENTS.md').write_text('Team instructions\n', encoding="utf-8")
        override = self.project / 'AGENTS.override.md'
        original = b'# Local requirements\nNo deployment.\n'
        override.write_bytes(original)
        self.activate()
        first = override.read_bytes()
        self.assertTrue(first.endswith(original))
        self.assertEqual((self.project / 'AGENTS.md').read_text(encoding="utf-8"), 'Team instructions\n')
        self.activate()
        self.assertEqual(override.read_bytes(), first)
        self.assertEqual(setup.status(self.project)['status'], 'configured')

    def test_all_host_guides_and_shared_binding_preserved(self):
        for agent in setup.GUIDES:
            with self.subTest(agent=agent):
                result = self.activate(agent)
                self.assertEqual(result['status'], 'initialized')
                guide = Path(result['guide']).read_text(encoding="utf-8")
                self.assertIn(setup.BEGIN, guide)
                if agent == 'cursor':
                    self.assertIn('alwaysApply: true', guide)
        activation = json.loads((self.project / '.dev-memory/activation.json').read_text(encoding="utf-8"))
        self.assertEqual(set(activation['bindings']), set(setup.GUIDES))
        self.assertEqual(activation['bindings']['codex']['global_root'], str(self.global_root))

    def test_empty_override_does_not_hide_existing_team_instructions(self):
        (self.project / 'AGENTS.md').write_text('Team instructions must remain visible.\n', encoding="utf-8")
        (self.project / 'AGENTS.override.md').write_text('  \n', encoding="utf-8")
        result = self.activate()
        self.assertEqual(Path(result['guide']).name, 'AGENTS.md')
        self.assertIn('Team instructions must remain visible.', Path(result['guide']).read_text(encoding="utf-8"))
        self.assertEqual((self.project / 'AGENTS.override.md').read_text(encoding="utf-8"), '  \n')

    def test_disabled_cursor_rule_is_not_claimed_automatic(self):
        result = self.activate('cursor')
        guide = Path(result['guide'])
        guide.write_text(guide.read_text(encoding="utf-8").replace('alwaysApply: true', 'alwaysApply: false'), encoding="utf-8")
        self.assertEqual(setup.status(self.project)['status'], 'not_configured')
        with self.assertRaises(store.MemoryError):
            self.activate('cursor')

    def test_unsafe_symlinks_and_malformed_markers_fail_before_init(self):
        target = self.home / 'untouched.txt'
        target.write_text('untouched', encoding="utf-8")
        guide = self.project / 'AGENTS.md'
        guide.symlink_to(target)
        with self.assertRaises(store.MemoryError):
            self.activate()
        guide.unlink()
        for content in (setup.BEGIN, setup.END + setup.BEGIN, setup.BEGIN + setup.BEGIN + setup.END):
            guide.write_text(content, encoding="utf-8")
            with self.assertRaises(store.MemoryError):
                self.activate()
            self.assertEqual(guide.read_text(encoding="utf-8"), content)
        self.assertEqual(target.read_text(encoding="utf-8"), 'untouched')
        self.assertFalse((self.project / '.dev-memory').exists())
        self.assertFalse(self.global_root.exists())

    def test_nested_symlink_and_unmanaged_cursor_rule_fail(self):
        outside = self.home / 'outside'
        outside.mkdir()
        (self.project / '.cursor').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(store.MemoryError):
            self.activate('cursor')
        (self.project / '.cursor').unlink()
        rule = self.project / '.cursor/rules/dev-memory.mdc'
        rule.parent.mkdir(parents=True)
        rule.write_text('User owned rule', encoding="utf-8")
        with self.assertRaises(store.MemoryError):
            self.activate('cursor')
        self.assertEqual(rule.read_text(encoding="utf-8"), 'User owned rule')
        self.assertFalse(self.global_root.exists())

    def test_repeat_setup_preserves_paused_or_disabled_capture(self):
        self.activate()
        for scope, config in [('project', self.project / '.dev-memory/config.json'),
                              ('global', self.global_root / 'global/config.json')]:
            value = json.loads(config.read_text(encoding="utf-8"))
            value.update(capture_enabled=False, recall_enabled=False)
            config.write_text(json.dumps(value), encoding="utf-8")
            before = config.read_bytes()
            self.activate()
            self.assertEqual(config.read_bytes(), before, scope)

    def test_project_failure_never_creates_global_or_guide(self):
        error = store.MemoryError('storage_unavailable', 'Synthetic permission failure')
        with patch.object(store, 'init_project', side_effect=error):
            result = self.activate()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['stores'][0]['scope'], 'project')
        self.assertFalse(self.global_root.exists())
        self.assertFalse((self.project / 'AGENTS.md').exists())

    def test_guide_write_failure_returns_partial_stores_and_releases_lock(self):
        original = store.write_bytes_atomic
        def fail_guide(path, *args, **kwargs):
            if Path(path).name == 'AGENTS.md':
                raise PermissionError('Synthetic guide write failure')
            return original(path, *args, **kwargs)
        with patch.object(store, 'write_bytes_atomic', side_effect=fail_guide):
            result = self.activate()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual([s['status'] for s in result['stores']], ['initialized', 'initialized'])
        self.assertEqual(result['activation'], 'failed')
        self.assertFalse((self.project / '.dev-memory/activation.lock').exists())
        self.assertEqual(setup.status(self.project)['status'], 'not_configured')
        self.assertEqual(self.activate()['status'], 'initialized')

    def test_global_failure_reports_partial_project_success(self):
        error = store.MemoryError('storage_unavailable', 'Synthetic permission failure')
        with patch.object(store, 'init_global', side_effect=error):
            result = self.activate()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual([s['status'] for s in result['stores']], ['initialized', 'failed'])
        self.assertFalse((self.project / 'AGENTS.md').exists())

    def test_tracked_memory_path_blocks_initialization(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        data = self.project / '.dev-memory'
        data.mkdir()
        (data / 'keep.txt').write_text('synthetic', encoding="utf-8")
        subprocess.run(['git', '-C', str(self.project), 'add', '-f', '.dev-memory/keep.txt'], check=True)
        result = self.activate()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(self.global_root.exists())

    def test_manifest_identity_budget_and_unavailable_runtime_are_honest(self):
        self.activate()
        manifest = self.project / '.dev-memory/activation.json'
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value['project_root'] = '/wrong/project'
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(store.MemoryError):
            self.activate()
        self.assertEqual(setup.status(self.project)['status'], 'failed')
        manifest.unlink()
        (self.project / 'AGENTS.md').write_text('x' * 25 * 1024, encoding="utf-8")
        with self.assertRaises(store.MemoryError):
            self.activate()
        (self.project / 'AGENTS.md').unlink()
        with self.assertRaises(store.MemoryError):
            setup.setup(self.project, 'codex', self.home / 'missing', sys.executable, self.global_root)

    def test_existing_setup_lock_is_bounded_and_preserved(self):
        self.activate()
        lock = self.project / '.dev-memory/activation.lock'
        lock.write_text('synthetic lock', encoding="utf-8")
        with self.assertRaises(store.MemoryError) as exc:
            self.activate()
        self.assertEqual(exc.exception.code, 'setup_busy')
        self.assertTrue(lock.exists())

    def test_doctor_checks_bootstrap_without_claiming_host_verification(self):
        self.activate()
        report = dev_memory.doctor(self.project, self.global_root)
        self.assertEqual(report['project_activation']['status'], 'configured')
        self.assertFalse(report['project_activation']['host_e2e_verified'])
        (self.project / 'AGENTS.md').unlink()
        self.assertEqual(setup.status(self.project)['status'], 'not_configured')

    def test_user_setup_updates_only_codex_managed_block_and_is_reversible(self):
        codex_home = self.home / '.codex'
        codex_home.mkdir()
        agents = codex_home / 'AGENTS.md'
        override = codex_home / 'AGENTS.override.md'
        agents.write_text('Base user instructions\n', encoding='utf-8')
        original_override = 'Temporary user override\n'
        override.write_text(original_override, encoding='utf-8')
        with patch.dict(os.environ, {'CODEX_HOME': str(codex_home)}):
            first = setup.setup_user('codex', self.skill, sys.executable, self.global_root)
            self.assertEqual(first['activation'], 'configured')
            self.assertEqual(first['guide'], str(override))
            managed = override.read_text(encoding='utf-8')
            self.assertIn('--global-only', managed)
            self.assertTrue(managed.endswith(original_override))
            self.assertEqual(agents.read_text(encoding='utf-8'), 'Base user instructions\n')
            setup.setup_user('codex', self.skill, sys.executable, self.global_root)
            self.assertEqual(override.read_text(encoding='utf-8').count(setup.USER_BEGIN), 1)
            other_a = store.recall('bug evidence', project_root=None, global_root=self.global_root)
            other_b = store.recall('feature reuse', project_root=None, global_root=self.global_root)
            self.assertEqual([item['scope'] for item in other_a['stores']], ['global'])
            self.assertEqual([item['scope'] for item in other_b['stores']], ['global'])
            removed = setup.remove_user('codex', self.skill)
            self.assertEqual(removed['status'], 'removed')
            self.assertEqual(override.read_text(encoding='utf-8'), original_override)
        self.assertTrue(store.global_paths(self.global_root)[1].is_file())
        self.assertFalse((self.project / '.dev-memory').exists())

    def test_user_setup_prefers_override_and_refuses_other_host(self):
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home / '.codex')}):
            with self.assertRaises(store.MemoryError) as exc:
                setup.setup_user('claude-code', self.skill, sys.executable, self.global_root)
            self.assertEqual(exc.exception.code, 'host_unsupported')

    def test_install_user_mode_does_not_initialize_working_project(self):
        env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
               'CODEX_HOME': str(self.home / '.codex'), 'DEV_MEMORY_HOME': str(self.global_root)}
        cmd = [sys.executable, '-B', str(ROOT / 'install.py'), 'codex', '--user', '--json']
        run = subprocess.run(cmd, env=env, cwd=self.project, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        result = json.loads(run.stdout)
        self.assertEqual(result['user_activation']['activation'], 'configured')
        self.assertFalse((self.project / '.dev-memory').exists())
        self.assertIn(setup.USER_BEGIN, (self.home / '.codex/AGENTS.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

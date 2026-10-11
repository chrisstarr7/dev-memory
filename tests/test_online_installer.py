"""Online bootstrap checks: synthetic snapshots, homes and projects only."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import stat
import warnings
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import install
import dev_memory
import dev_memory_store as store


def snapshot(changes=None, extra=None, manifest_change=None):
    contents = {name: (ROOT / name).read_bytes() for name in dev_memory.RELEASE_FILES}
    manifest = {'package': 'dev-memory', 'version': 'synthetic-test', 'files': [
        {'path': name, 'sha256': hashlib.sha256(content).hexdigest()}
        for name, content in contents.items()]}
    if manifest_change:
        manifest_change(manifest)
    contents.update(changes or {})
    contents['manifest.json'] = json.dumps(manifest).encode()
    out = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        warnings.filterwarnings('ignore', message='Duplicate name:', category=UserWarning)
        for name, content in contents.items():
            archive.writestr('dev-memory-main/' + name, content)
        for name, content in extra or []:
            archive.writestr(name, content)
    return out.getvalue()


class OnlineTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='online 中文 ')
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.home = self.base / 'home'
        self.project = self.base / 'project'
        self.home.mkdir()
        self.project.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
                    'CODEX_HOME': str(self.home / '.codex'),
                    'DEV_MEMORY_HOME': str(self.home / '.dev-memory'),
                    'PYTHONDONTWRITEBYTECODE': '1'}
        self.original = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, self.original)

    def run_online(self, *args, data=None, failure=None):
        stdout = io.StringIO()
        with patch.dict(os.environ, self.env), patch.object(
                install, 'download_snapshot', side_effect=failure,
                return_value=data if data is not None else snapshot()), \
                contextlib.redirect_stdout(stdout):
            code = install.online_main([*args, '--json'])
        return code, json.loads(stdout.getvalue())

    def test_all_hosts_initialize_original_project_not_staging(self):
        data = snapshot()
        for agent in ('codex', 'claude', 'cursor', 'gemini', 'copilot', 'opencode'):
            with self.subTest(agent=agent):
                code, result = self.run_online(agent, data=data)
                self.assertEqual(code, 0, result)
                self.assertEqual(result['project_setup']['project_root'], str(self.project))
                self.assertEqual(result['project_setup']['activation'], 'configured')
                self.assertEqual(result['runtime_check']['status'], 'passed')
                self.assertEqual(result['online']['verified_files'], len(dev_memory.RELEASE_FILES))
                self.assertEqual(result['hooks']['status'], 'not_requested')
                self.assertTrue(Path(result['path']).is_relative_to(self.home))
        binding = json.loads((self.project / '.dev-memory/activation.json').read_text())
        self.assertEqual(len(binding['bindings']), 6)
        self.assertNotIn('dev-memory-source-', json.dumps(binding))
        self.assertFalse((self.home / '.codex/hooks.json').exists())
        for database in (self.project / '.dev-memory/memory.sqlite3',
                         self.home / '.dev-memory/global/memory.sqlite3'):
            import sqlite3
            with contextlib.closing(sqlite3.connect(database)) as connection:
                self.assertEqual(connection.execute('select count(*) from memories').fetchone()[0], 0)

    def test_repeat_preserves_pause_memory_and_instructions(self):
        self.assertEqual(self.run_online('codex')[0], 0)
        record = {'kind': 'business_rule', 'claim_type': 'desired', 'strength': 'hard',
                  'title': 'Synthetic return policy', 'content': 'Allow returns within 14 days.',
                  'conditions': 'Delivered and unopened.', 'exceptions': 'No final-sale items.',
                  'do': 'Check all conditions.', 'dont': 'Do not omit exclusions.',
                  'verification_steps': 'Exercise the date boundary and exclusions.',
                  'tags': ['synthetic'],
                  'source': {'type': 'user_feedback', 'excerpt': 'Synthetic correction: 14 days.'}}
        saved = store.apply_payload({'schema_version': 1, 'scope': 'project',
                    'session_id': 'synthetic-session', 'turn_id': 'synthetic-turn',
                    'idempotency_key': 'synthetic-save',
                    'operations': [{'op': 'ADD', 'scope': 'project', 'record': record}]},
                    project_root=self.project, global_root=self.home / '.dev-memory')
        self.assertEqual(saved['status'], 'saved', saved)
        config = self.project / '.dev-memory/config.json' 
        state = json.loads(config.read_text())
        state.update(capture_enabled=False, recall_enabled=False)
        config.write_text(json.dumps(state))
        before = config.read_bytes()
        database = self.project / '.dev-memory/memory.sqlite3'
        import sqlite3
        def stored_rows():
            with contextlib.closing(sqlite3.connect(database)) as conn:
                return conn.execute('select * from memories').fetchall(), conn.execute(
                    "select value from meta where key='namespace_id'").fetchone()
        rows = stored_rows()
        self.assertEqual(len(rows[0]), 1)
        guide = self.project / 'AGENTS.md'
        guide.write_text('User instructions remain.\n' + guide.read_text())
        self.assertEqual(self.run_online('codex')[0], 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(stored_rows(), rows)
        self.assertTrue(guide.read_text().startswith('User instructions remain.\n'))
        self.assertEqual(guide.read_text().count('<!-- dev-memory:managed:start -->'), 1)

    def test_explicit_project_and_target_are_preserved(self):
        other = self.base / 'explicit project'
        other.mkdir()
        code, result = self.run_online('--agent', 'claude-code', '--project', str(other),
                                       '--target', str(self.home / 'custom skill'))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['project_setup']['project_root'], str(other))
        self.assertEqual(result['path'], str(self.home / 'custom skill'))
        self.assertFalse((self.project / '.dev-memory').exists())

    def test_help_invalid_and_conflicting_arguments_do_not_fetch(self):
        for args, expected in ((['--help'], 0), ([], 2), (['unknown'], 2),
                               (['codex', '--agent', 'claude'], 2), (['codex', '--bad'], 2)):
            with self.subTest(args=args), patch.object(install, 'download_snapshot') as fetch, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    install.online_main(args)
                self.assertEqual(exc.exception.code, expected)
                fetch.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_network_failure_and_timeout_have_one_attempt_no_writes(self):
        for failure in (urllib.error.URLError('offline'), TimeoutError('timed out')):
            with self.subTest(failure=failure):
                code, result = self.run_online('codex', failure=failure)
                self.assertEqual(code, 1)
                self.assertEqual(result['status'], 'failed')
                self.assertFalse((self.project / '.dev-memory').exists())
                self.assertEqual(list(self.home.iterdir()), [])

    def test_corrupt_manifest_and_hash_never_execute(self):
        cases = [
            snapshot(changes={'install.py': b'raise SystemExit(0)'}),
            snapshot(manifest_change=lambda m: m.update(package='other')),
            snapshot(manifest_change=lambda m: m['files'].append(m['files'][0])),
            snapshot(manifest_change=lambda m: m['files'].append({'path': '../escape', 'sha256': 'a'*64})),
            snapshot(manifest_change=lambda m: m['files'].append({'path': 'absent', 'sha256': 'a'*64})),
            snapshot(manifest_change=lambda m: m.update(files=[])),
            snapshot(manifest_change=lambda m: m.update(files=[x for x in m['files'] if x['path'] != 'install.py'])),
            b'not a ZIP',
        ]
        # Replace manifest bytes after fixture hashes are made.
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, 'w') as z:
            z.writestr('dev-memory-main/manifest.json', 'bad')
        cases.append(raw.getvalue())
        for data in cases:
            with self.subTest(size=len(data)), patch.object(install.subprocess, 'run') as child:
                code, result = self.run_online('codex', data=data)
                self.assertEqual(code, 1, result)
                child.assert_not_called()
                self.assertEqual(list(self.home.iterdir()), [])

    def test_unsafe_paths_links_duplicates_and_sizes_rejected(self):
        extras = [('../escape', b'x'), ('/absolute', b'x'),
                  ('dev-memory-main/../escape', b'x'), ('dev-memory-main/a\\b', b'x'),
                  ('dev-memory-main/C:/x', b'x'), ('other-root/file', b'x'),
                  ('dev-memory-main/install.py', b'x'),
                  ('dev-memory-main/huge', b'x' * (1024*1024+1))]
        link = zipfile.ZipInfo('dev-memory-main/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        extras.append((link, b'/tmp/target'))
        for extra in extras:
            with self.subTest(path=str(extra[0])), patch.object(install.subprocess, 'run') as child:
                code, result = self.run_online('codex', data=snapshot(extra=[extra]))
                self.assertEqual(code, 1, result)
                child.assert_not_called()
        with self.assertRaises(ValueError):
            install.unpack_snapshot(b'x' * (install.MAX_DOWNLOAD + 1), self.base / 'stage')
        data = snapshot(extra=[('dev-memory-main/extra'+str(i), b'') for i in range(1024)])
        self.assertEqual(self.run_online('codex', data=data)[0], 1)

    def test_child_bad_receipts_and_exit_codes_are_not_success(self):
        import subprocess
        for code, output in ((0, '{}'), (0, '[]'), (0, 'bad'),
                             (1, '{"status":"installed"}'),
                             (0, '{"status":"installed","runtime_check":[],"project_setup":{}}')):
            with self.subTest(output=output), patch.object(install.subprocess, 'run', return_value=
                    subprocess.CompletedProcess([], code, output, '')):
                status, result = self.run_online('codex')
                self.assertEqual(status, 1, result)
                self.assertEqual(result['status'], 'failed')
        with patch.object(install.subprocess, 'run', side_effect=subprocess.TimeoutExpired('install', 60)):
            code, result = self.run_online('codex')
            self.assertEqual(code, 1)
            self.assertEqual(result['error'], 'online_install_timeout')

    def test_partial_child_failure_is_returned_with_its_actual_stores(self):
        import subprocess
        payload = {'status': 'failed', 'message': 'project setup failed', 'path': 'synthetic',
                   'project_setup': {'stores': {'global': {'status': 'initialized'},
                                                 'project': {'status': 'failed'}}}}
        with patch.object(install.subprocess, 'run', return_value=
                subprocess.CompletedProcess([], 1, json.dumps(payload), '')):
            code, result = self.run_online('codex')
            self.assertEqual(code, 1)
            self.assertEqual(result['project_setup'], payload['project_setup'])

    def test_source_temp_is_removed_after_execution(self):
        import subprocess
        original_run = subprocess.run
        staged = []
        def run(command, **kwargs):
            staged.append(Path(command[2]).parent)
            return original_run(command, **kwargs)
        with patch.object(install.subprocess, 'run', side_effect=run):
            self.assertEqual(self.run_online('codex')[0], 0)
        self.assertTrue(staged)
        self.assertTrue(all(not path.exists() for path in staged))

    def test_download_stream_limits_and_deadline(self):
        response = io.BytesIO(b'x' * 1025)
        with patch('urllib.request.urlopen', return_value=response), patch.object(install, 'MAX_DOWNLOAD', 1024):
            with self.assertRaises(ValueError):
                install.download_snapshot()
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'x')), \
                patch('time.monotonic', side_effect=[0, 46]):
            with self.assertRaises(TimeoutError):
                install.download_snapshot()

    def test_unsupported_python_or_sqlite_does_not_fetch(self):
        for target, value in (('sys.version_info', (3, 9)),
                              ('sqlite3.connect', OSError('missing sqlite'))):
            with self.subTest(target=target), patch('install.download_snapshot') as fetch:
                replacement = patch(target, side_effect=value) if isinstance(value, Exception) else patch(target, value)
                with replacement, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(install.online_main(['codex', '--json']), 1)
                fetch.assert_not_called()

    def test_expanded_archive_limit(self):
        with patch.object(install, 'MAX_EXPANDED', 10), patch.object(install.subprocess, 'run') as child:
            self.assertEqual(self.run_online('codex')[0], 1)
            child.assert_not_called()

    def test_macos_system_cas_and_explicit_ca_settings(self):
        for custom in (False, True):
            with self.subTest(custom=custom), patch.dict(os.environ, {
                    'SSL_CERT_FILE': '/custom/ca' if custom else '', 'SSL_CERT_DIR': ''}), \
                    patch.object(sys, 'platform', 'darwin'), patch.object(Path, 'is_file', return_value=True), \
                    patch('ssl.create_default_context') as create, \
                    patch('urllib.request.urlopen', return_value=io.BytesIO(b'zip')) as request:
                self.assertEqual(install.download_snapshot(), b'zip')
                request.assert_called_once_with(install.ONLINE_URL, timeout=15, context=create.return_value)
                if custom:
                    create.return_value.load_verify_locations.assert_not_called()
                else:
                    create.return_value.load_verify_locations.assert_called_once_with(cafile='/etc/ssl/cert.pem')

    def test_recommended_shell_propagates_upstream_fetch_failure(self):
        import shlex
        import subprocess
        line = next(x for x in (ROOT/'README.md').read_text().splitlines() if x.startswith('bash -o pipefail '))
        command = shlex.split(line)
        fake = self.base / 'bin'
        fake.mkdir()
        curl = fake / 'curl'
        curl.write_text('#!/bin/sh\nexit 7\n')
        curl.chmod(0o700)
        result = subprocess.run(command, cwd=self.project, capture_output=True, text=True,
                                env={**self.env, 'PATH': str(fake)+os.pathsep+os.environ['PATH']}, timeout=10)
        self.assertEqual(result.returncode, 7)
        self.assertNotIn('安装成功', result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertFalse((self.project/'.dev-memory').exists())

    def test_exec_entry_without_file_routes_to_online(self):
        source = (ROOT / 'install.py').read_text()
        # Stop at the selected entry to avoid a real network call in this test.
        replacement = 'raise SystemExit("online" if globals().get("__file__", "<stdin>") == "<stdin>" else "local")'
        source = source[:source.rindex('    raise SystemExit(')] + '    ' + replacement
        for file, expected in ((None, 'online'), ('<stdin>', 'online'), (str(ROOT/'install.py'), 'local')):
            namespace = {'__name__': '__main__'}
            if file:
                namespace['__file__'] = file
            with self.assertRaises(SystemExit) as exc:
                exec(compile(source, '<online>', 'exec'), namespace)
            self.assertEqual(exc.exception.code, expected)


if __name__ == '__main__':
    unittest.main()

"""Single-store vector safety checks; no model download or network required."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from unittest.mock import patch

from test_dev_memory import MemoryTestCase
import dev_memory_store as store
import dev_memory_vectors as vectors


class VectorTests(MemoryTestCase):
    def test_inspect_returns_complete_vector_without_recall_or_model_work(self):
        mid = self.add_project_rule()
        config = self.runtime()
        self.seed_vector(mid, config)
        with self.connection() as conn:
            before = vectors.generation(conn)
        with patch.object(vectors, '_encode', side_effect=AssertionError('inspection cannot infer')), \
             patch.object(vectors, 'schedule', side_effect=AssertionError('inspection cannot index')), \
             patch.object(store, '_record_recall_counts', side_effect=AssertionError('inspection cannot count')):
            result = vectors.inspect_record('project', mid, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['embedding'], [1.] + [0.] * 383)
        self.assertEqual(result['dimensions'], 384)
        self.assertEqual(result['indexed_revision'], 1)
        self.assertTrue(result['is_current'])
        with self.connection() as conn:
            self.assertEqual(vectors.generation(conn), before)

    def test_inspect_marks_stale_vectors_and_respects_scope_and_disabled_store(self):
        mid = self.add_project_rule()
        config = self.runtime()
        self.seed_vector(mid, config)
        with self.connection() as conn:
            conn.execute('UPDATE memories SET revision=revision+1 WHERE id=?', (mid,))
        result = vectors.inspect_record('project', mid, project_root=self.project_a, global_root=self.global_root)
        self.assertFalse(result['is_current'])
        self.assertEqual(result['current_revision'], 2)
        self.assertEqual(result['indexed_revision'], 1)
        self.assertEqual(len(result['embedding']), 384)
        foreign = vectors.inspect_record('project', mid, project_root=self.project_b, global_root=self.global_root)
        self.assertEqual(foreign['status'], 'not_found')
        base, _, cfg = store._config_for('project', self.project_a, self.global_root)
        cfg['recall_enabled'] = False
        store.write_json_atomic(base / 'config.json', cfg)
        disabled = vectors.inspect_record('project', mid, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(disabled, {'status':'disabled'})

    def test_corrupt_optional_config_cannot_break_raw_capture(self):
        runtime = self.global_root / 'vector-runtime'
        runtime.mkdir()
        (runtime/'config.json').write_text('[]', encoding='utf-8')
        self.assertFalse(vectors.enabled(self.global_root))
        self.assertTrue(self.add_project_rule())

    def test_model_timeout_and_cancel_reap_actual_child(self):
        real_popen = subprocess.Popen
        for cancel in (False, True):
            children = []
            def sleeping_child(command, **kwargs):
                child = real_popen([sys.executable, '-c', 'import sys,time;sys.stdin.read();time.sleep(30)'], **kwargs)
                children.append(child)
                return child
            calls = []
            def cancelled():
                calls.append(1)
                return len(calls) > 1
            started = time.monotonic()
            with patch.object(vectors.subprocess, 'Popen', side_effect=sleeping_child):
                with self.assertRaises(ValueError if cancel else subprocess.TimeoutExpired):
                    vectors._encode(['fixture'], {'python':sys.executable},
                                    timeout=2 if cancel else .1, cancelled=cancelled if cancel else None)
            self.assertLess(time.monotonic()-started, 2)
            self.assertTrue(all(child.poll() is not None for child in children))

    def test_status_exposes_failed_batch_and_remaining_count(self):
        self.add_project_rule()
        config = {'model_fingerprint': 'fixture-1', 'model_name': 'fixture'}
        with self.connection() as conn:
            vectors._schema(conn)
            conn.execute("INSERT INTO vector_job VALUES(1,'token',?,'failed')", (time.time()+30,))
        with patch.object(vectors, '_settings', return_value=config):
            result = vectors.status('project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['eligible'], 1)
        self.assertEqual(result['pending'], 1)
        self.assertGreater(result['retry_after_seconds'], 0)

    def runtime(self):
        try:
            import sqlite_vec
        except ImportError:
            self.skipTest('sqlite-vec optional dependency not installed')
        runtime = self.global_root / 'vector-runtime'
        runtime.mkdir(exist_ok=True)
        source = Path(sqlite_vec.loadable_path())
        if not source.is_file():
            source = source.with_suffix('.dll' if sys.platform == 'win32' else '.dylib' if sys.platform == 'darwin' else '.so')
        extension = runtime / source.name
        shutil.copyfile(source, extension)
        python = runtime / 'python'
        python.write_text('test fixture, never executed', encoding='utf-8')
        config = {'enabled': True, 'python': str(python), 'extension_path': str(extension),
                  'model_cache': str(runtime/'models'), 'model_name': 'fixture', 'model_fingerprint': 'fixture-1'}
        (runtime/'config.json').write_text(json.dumps(config), encoding='utf-8')
        return config

    @contextmanager
    def connection(self):
        _, database, _ = store._config_for('project', self.project_a, self.global_root)
        conn = store._connect(database)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def seed_vector(self, memory_id, config, revision=1):
        with self.connection() as conn:
            vectors._schema(conn)
            vectors._load(conn, config)
            vectors._vector_schema(conn)
            conn.execute('INSERT INTO memory_vectors VALUES(?,?)', (memory_id, json.dumps([1.]+[0.]*383)))
            conn.execute("INSERT INTO vector_state VALUES(?,?,?,'ready',?,'')", (memory_id,revision,vectors._model_key(config),time.time()))

    def test_unconfigured_runtime_keeps_raw_save_and_does_not_create_tables(self):
        mid = self.add_project_rule()
        result = vectors.search('退款', 'project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['status'], 'unavailable')
        with self.connection() as conn:
            self.assertFalse(vectors._exists(conn, 'vector_state'))
            self.assertEqual(conn.execute('SELECT content FROM memories WHERE id=?', (mid,)).fetchone()[0], '仅已送达订单可退款')

    def test_search_skips_model_and_extension_when_index_is_empty(self):
        with self.connection() as conn:
            vectors._schema(conn)
            conn.execute('CREATE TABLE memory_vectors(memory_id TEXT, embedding BLOB)')
        with patch.object(vectors, '_settings', return_value={'model_fingerprint': 'fixture'}), \
             patch.object(vectors, '_encode', side_effect=AssertionError('empty index cannot infer')), \
             patch.object(vectors, '_load', side_effect=AssertionError('empty index needs no extension')):
            result = vectors.search('query', 'project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result, {'status': 'pending', 'records': []})

    def test_search_skips_model_and_extension_when_all_indexes_are_ineligible(self):
        mid = self.add_project_rule()
        config = {'model_fingerprint': 'fixture'}
        with self.connection() as conn:
            vectors._schema(conn)
            conn.execute('CREATE TABLE memory_vectors(memory_id TEXT, embedding BLOB)')
            conn.execute('INSERT INTO memory_vectors VALUES(?,?)', (mid, b'not loaded'))
        cases = [
            ('pending', 1, vectors._model_key(config), 'active', 'desired', 'project'),
            ('ready', 0, vectors._model_key(config), 'active', 'desired', 'project'),
            ('ready', 1, 'old-model', 'active', 'desired', 'project'),
            ('ready', 1, vectors._model_key(config), 'archived', 'desired', 'project'),
            ('ready', 1, vectors._model_key(config), 'candidate', 'desired', 'project'),
            ('ready', 1, vectors._model_key(config), 'active', 'hypothesis', 'project'),
            ('ready', 1, vectors._model_key(config), 'active', 'desired', 'global'),
        ]
        for state, revision, model, status, claim, scope in cases:
            with self.subTest(state=state, revision=revision, model=model, status=status, claim=claim, scope=scope):
                with self.connection() as conn:
                    conn.execute('UPDATE memories SET status=?,claim_type=?,scope=? WHERE id=?', (status, claim, scope, mid))
                    conn.execute("INSERT OR REPLACE INTO vector_state VALUES(?,?,?,?,0,'')", (mid, revision, model, state))
                with patch.object(vectors, '_settings', return_value=config), \
                     patch.object(vectors, '_encode', side_effect=AssertionError('ineligible index cannot infer')), \
                     patch.object(vectors, '_load', side_effect=AssertionError('ineligible index needs no extension')):
                    result = vectors.search('query', 'project', project_root=self.project_a, global_root=self.global_root)
                self.assertEqual(result, {'status': 'pending', 'records': []})

    def test_changed_raw_revision_invalidates_vector_without_loading_extension(self):
        mid = self.add_project_rule()
        with self.connection() as conn:
            vectors._schema(conn)
            conn.execute("INSERT INTO vector_state VALUES(?,1,'fixture','ready',0,'')", (mid,))
            with patch.object(vectors, '_load', side_effect=AssertionError('raw writes cannot require extension')):
                vectors.on_change(conn, [mid])
            self.assertEqual(conn.execute('SELECT state FROM vector_state').fetchone()[0], 'pending')
            self.assertNotEqual(vectors.generation(conn), '0')

    def test_real_knn_filters_revision_status_and_scope(self):
        mid = self.add_project_rule()
        config = self.runtime()
        self.seed_vector(mid, config)
        cache = {}
        with patch.object(vectors, '_encode', return_value=[[1.]+[0.]*383]) as encode:
            hit = vectors.search('不同表达', 'project', project_root=self.project_a, global_root=self.global_root, query_cache=cache)
            self.assertEqual([r['id'] for r in hit['records']], [mid])
            with self.connection() as conn:
                conn.execute('UPDATE memories SET revision=revision+1 WHERE id=?', (mid,))
            stale = vectors.search('不同表达', 'project', project_root=self.project_a, global_root=self.global_root, query_cache=cache)
            self.assertEqual(stale['records'], [])
            encode.assert_called_once()

    def test_forget_is_transactional_and_refuses_unavailable_extension(self):
        mid = self.add_project_rule()
        config = self.runtime()
        self.seed_vector(mid, config)
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            vectors.remove(conn, [mid], global_root=self.global_root)
            conn.rollback()
            vectors._load(conn, config)
            self.assertEqual(conn.execute('SELECT count(*) FROM memory_vectors').fetchone()[0], 1)
            with patch.object(vectors, '_settings', return_value=None):
                with self.assertRaises(sqlite3.Error):
                    vectors.remove(conn, [mid], global_root=self.global_root)
            self.assertEqual(conn.execute('SELECT count(*) FROM memories').fetchone()[0], 1)

    def test_disabled_vectors_can_still_be_permanently_deleted(self):
        mid = self.add_project_rule()
        config = self.runtime()
        self.seed_vector(mid, config)
        config['enabled'] = False
        path = self.global_root/'vector-runtime'/'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        self.assertFalse(vectors.enabled(self.global_root))
        with self.connection() as conn:
            vectors.remove(conn, [mid], global_root=self.global_root)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM memory_vectors').fetchone()[0], 0)

    def test_schedule_lease_prevents_duplicate_workers(self):
        self.add_project_rule()
        self.runtime()
        with patch.object(store, '_run_git', return_value=None), patch.object(vectors.subprocess, 'Popen') as process:
            first = vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
            second = vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(first['status'], 'running')
        self.assertEqual(second['status'], 'running')
        process.assert_called_once()
        result = vectors.finish('project', project_root=self.project_a, global_root=self.global_root, wait_seconds=.01)
        self.assertEqual(result['status'], 'deferred')
        with self.connection() as conn:
            self.assertEqual(conn.execute('SELECT deadline FROM vector_job').fetchone()[0], 0)

    def test_worker_rechecks_revision_after_computation(self):
        mid = self.add_project_rule()
        config = self.runtime()
        with patch.object(store, '_run_git', return_value=None), patch.object(vectors.subprocess, 'Popen'):
            vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
        with self.connection() as conn:
            token = conn.execute('SELECT token FROM vector_job').fetchone()[0]
        def changed_during_inference(*args, **kwargs):
            with self.connection() as conn:
                conn.execute('UPDATE memories SET revision=revision+1 WHERE id=?', (mid,))
            return [[1.]+[0.]*383]
        with patch.object(vectors, '_encode', side_effect=changed_during_inference):
            vectors._work('project', token, self.project_a, self.global_root)
        with self.connection() as conn:
            vectors._load(conn, config)
            self.assertEqual(conn.execute('SELECT count(*) FROM memory_vectors').fetchone()[0], 0)

    def test_worker_cannot_commit_after_deadline(self):
        self.add_project_rule()
        self.runtime()
        with patch.object(store, '_run_git', return_value=None), patch.object(vectors.subprocess, 'Popen'):
            vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
        with self.connection() as conn:
            token = conn.execute('SELECT token FROM vector_job').fetchone()[0]
        def late(*args, **kwargs):
            with self.connection() as conn:
                conn.execute('UPDATE vector_job SET deadline=0')
            return [[1.]+[0.]*383]
        with patch.object(vectors, '_encode', side_effect=late):
            vectors._work('project', token, self.project_a, self.global_root)
        with self.connection() as conn:
            self.assertFalse(vectors._exists(conn, 'memory_vectors'))
            self.assertEqual(conn.execute('SELECT state FROM vector_job').fetchone()[0], 'failed')
        with patch.object(store, '_run_git', return_value=None), patch.object(vectors.subprocess, 'Popen', side_effect=AssertionError('retry must back off')):
            result = vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['reason'], 'retry_backoff')

    def test_paused_capture_never_schedules_worker(self):
        self.runtime()
        store.set_capture('project', False, project_root=self.project_a)
        with patch.object(vectors.subprocess, 'Popen', side_effect=AssertionError('paused')):
            result = vectors.schedule('project', project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['status'], 'disabled')

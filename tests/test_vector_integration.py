"""Opt-in real CPU-model checks; synthetic project memory only."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from test_dev_memory import MemoryTestCase
import dev_memory_store as store
import dev_memory_vectors as vectors
import dev_memory_vector_setup as setup


class VectorRoutingTests(MemoryTestCase):
    def test_slow_optional_model_keeps_keyword_recall(self):
        memory_id = self.add_project_rule()
        def delayed(*args, **kwargs):
            time.sleep(.55)
            return {'status': 'deferred', 'reason': 'query_timeout', 'records': []}
        with patch.object(vectors, 'search', side_effect=delayed):
            result = store.recall('退款', project_root=self.project_a, global_root=self.global_root,
                                  readonly=True, max_details=10, max_chars=15000)
        project = result['stores'][1]
        self.assertEqual(project['status'], 'ok', project)
        self.assertIn(memory_id, [r['id'] for r in project['records']])

    def test_fused_semantic_hit_is_not_blocked_by_weak_keyword_match(self):
        weak = self.add_project_rule(turn='weak', title='响应日志', content='响应完成后输出日志。',
                                     strength='soft')
        strong = self.add_project_rule(turn='strong', title='接口契约',
                                       content='新增请求与返回字段要同步维护文档。', strength='soft')
        def semantic(query, kind, **kwargs):
            return {'status': 'ok', 'records': [{'id': strong, 'distance': .1}]} if kind == 'project' else {'status':'ok','records':[]}
        with patch.object(vectors, 'search', side_effect=semantic):
            result = store.recall('响应模型说明', project_root=self.project_a, global_root=self.global_root,
                                  readonly=True, max_details=1, max_chars=15000)
        returned = [r['id'] for r in result['stores'][1]['records']]
        self.assertEqual(returned, [strong])


@unittest.skipUnless(os.environ.get('DEV_MEMORY_VECTOR_INTEGRATION') == '1',
                     'Real model integration is opt-in; setup downloads dependencies and model')
class RealVectorIntegration(MemoryTestCase):
    def test_real_multilingual_offline_index_lifecycle(self):
        runtime_root = Path(os.environ.get('DEV_MEMORY_VECTOR_ROOT', str(self.global_root)))
        prepared = setup.setup(runtime_root, timeout_seconds=600)
        self.assertEqual(prepared['status'], 'ready', prepared)
        if not hasattr(sqlite3.Connection, 'enable_load_extension'):
            config = setup.read_config(runtime_root)
            self.assertNotEqual(Path(config['python']).resolve(), Path(sys.executable).resolve())
            child = subprocess.run([config['python'], '-m', 'unittest', 'discover', '-s', 'tests',
                                    '-p', 'test_vector_integration.py', '-v'],
                                   env={**os.environ,'DEV_MEMORY_VECTOR_ROOT':str(runtime_root)},
                                   capture_output=True, text=True, encoding='utf-8', timeout=180)
            self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
            return
        # A supplied runtime may be shared locally; all writes below target a synthetic project.
        self.global_root = runtime_root
        with patch.object(vectors, 'schedule', return_value={'status': 'deferred'}):
            memory_id = self.add_project_rule(
                title='接口模型注解', content='请求和响应模型必须补齐接口文档注解。',
                conditions='新增或修改 DTO 和 VO 时。', do='保持 Swagger 注解完整。',
                dont='不能遗漏新增字段。')
        started = vectors.schedule('project', project_root=self.project_a, global_root=runtime_root)
        self.assertIn(started['status'], ('running', 'scheduled', 'ready'), started)
        until = time.monotonic() + 13
        while time.monotonic() < until:
            indexed = vectors.status('project', project_root=self.project_a, global_root=runtime_root)
            if indexed.get('ready') == 1:
                break
            time.sleep(.1)
        self.assertEqual(indexed.get('ready'), 1, indexed)
        # Explicit long allowance here measures real inference, separate from the production 5s budget.
        settings = vectors._settings(runtime_root)
        real_query = vectors._encode(['request and response API documentation annotations'],
                                     settings, query=True, timeout=15)[0]
        with patch.object(vectors, '_encode', return_value=[real_query]):
            found = vectors.search('request and response API documentation annotations', 'project',
                                   project_root=self.project_a, global_root=runtime_root)
        self.assertEqual(found['status'], 'ok', found)
        self.assertIn(memory_id, [r['id'] for r in found['records']], found)
        prefix = '接口字段需要遵守业务规范。' * 40
        tails = vectors._encode([prefix + '禁止修改支付权限。', prefix + '允许修改支付权限。'],
                                settings, timeout=20)
        self.assertGreater(max(abs(a-b) for a, b in zip(*tails)), .00001,
                           'An important tail beyond 128 tokens must change the embedding')
        # Also exercise the actual uncached production query budget; fallback must stay bounded.
        before = time.monotonic()
        bounded = vectors.search('接口模型注解', 'project', project_root=self.project_a,
                                 global_root=runtime_root)
        self.assertLess(time.monotonic() - before, 8)
        self.assertIn(bounded['status'], ('ok', 'deferred', 'unavailable'), bounded)
        backup = store.backup_store('project', project_root=self.project_a, global_root=runtime_root)
        self.assertEqual(backup['status'], 'saved')
        current = store.show_record('project', memory_id, project_root=self.project_a,
                                    global_root=runtime_root)['record']
        revised = self.record(title='接口模型注解', content='接口模型使用项目统一的中文说明。')
        with patch.object(vectors, 'schedule', return_value={'status': 'deferred'}):
            result = self.apply(scope='project', turn='revise-vector', operations=[{
                'op': 'REVISE', 'scope': 'project', 'id': memory_id,
                'expected_revision': current['revision'], 'record': revised}])
        self.assertEqual(result['status'], 'saved', result)
        state = vectors.status('project', project_root=self.project_a, global_root=runtime_root)
        self.assertEqual(state['ready'], 0, state)
        restored = store.restore_store('project', Path(backup['backup']),
                                      project_root=self.project_a, global_root=runtime_root)
        self.assertEqual(restored['status'], 'restored', restored)
        preview = store.forget_preview('project', memory_id, project_root=self.project_a,
                                       global_root=runtime_root)
        token = preview.get('confirm_token') or preview.get('confirmation_token')
        self.assertIsNotNone(token, preview)
        forgotten = store.forget_apply('project', memory_id, token, project_root=self.project_a,
                                       global_root=runtime_root)
        self.assertEqual(forgotten['status'], 'forgotten', forgotten)
        self.assertNotIn('backup_cleanup_incomplete', forgotten, forgotten)


if __name__ == '__main__':
    unittest.main()

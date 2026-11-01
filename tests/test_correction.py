"""Find old memories for a natural-language correction without inventing a new record."""
import json
import os
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from test_dev_memory import MemoryTestCase, store, SCRIPTS


class CorrectionTests(MemoryTestCase):
    def lookup(self, query='表格导出', scope='both', project=None):
        return store.match_targets(query, scope, project_root=project or self.project_a,
                                   global_root=self.global_root)

    def test_search_includes_candidates_without_guessing_kind_or_claim(self):
        memory_id = self.add_project_rule(title='表格导出格式', content='导出为 CSV。', status='candidate')
        with patch.object(store, '_validate_record', side_effect=AssertionError('A lookup needs no proposed record')):
            result = self.lookup()
        self.assertEqual([r['id'] for b in result['stores'] for r in b['records']], [memory_id])
        row = result['stores'][1]['records'][0]
        self.assertEqual((row['revision'], row['status'], row['content']), (1,'candidate','导出为 CSV。'))

    def test_scope_identity_and_retired_records_are_not_silently_mixed(self):
        a = self.add_project_rule(title='导出格式', content='当前项目导出 XLSX。')
        self.add_project_rule(project=self.project_b, title='导出格式', content='另一项目导出 JSON。')
        for status in ('archived','superseded','stale'):
            self.add_project_rule(turn=status, title='导出格式', content='历史导出 '+status, status=status)
        habit = self.record(scope='global', kind='preference', claim_type='preference',
                            title='导出交付习惯', content='交付结果时说明导出文件位置。')
        g = self.apply(scope='global', turn='global', operations=[{'op':'ADD','record':habit}])['stores'][0]['operations'][0]['id']
        result = self.lookup('导出')
        self.assertEqual({(r['scope'],r['id']) for b in result['stores'] for r in b['records']}, {('global',g),('project',a)})
        self.assertNotIn(g, [r['id'] for b in self.lookup('导出','project')['stores'] for r in b['records']])
        with self.assertRaises(store.MemoryError):
            store.match_targets('导出','both',project_root=self.home/'missing',global_root=self.global_root)

    def test_lookup_does_not_write_or_invoke_vectors_and_honors_disable(self):
        self.add_project_rule(title='导出格式', content='导出 XLSX。')
        _, db = store.project_paths(self.project_a)
        def snapshot():
            with sqlite3.connect(db) as c:
                return {t:c.execute('SELECT * FROM '+t).fetchall() for t in
                        ('memories','evidence','revisions','recall_counts','receipts','session_context','meta')}
        before = snapshot()
        with patch('dev_memory_vectors.search',side_effect=AssertionError('No model for target lookup')):
            self.lookup('导出','project')
            self.assertEqual(snapshot(), before)
            store.set_capture('project',False,project_root=self.project_a)
            result = self.lookup('导出','project')
        self.assertTrue(result['stores'][0]['records'])
        self.assertFalse(result['stores'][0]['capture_enabled'])
        self.assertEqual(snapshot(), before)
        base,_,cfg = store._config_for('project',self.project_a,self.global_root)
        cfg['recall_enabled'] = False
        store.write_json_atomic(base/'config.json',cfg)
        self.assertEqual(self.lookup('导出','project')['stores'][0]['records'], [])

    def test_combined_output_is_bounded_and_exposes_omitted_matches(self):
        for i in range(12):
            self.add_project_rule(turn=str(i),title='导出规则 '+str(i),content='导出约束 '+str(i))
        result = self.lookup('导出')
        rows = [r for b in result['stores'] for r in b['records']]
        self.assertEqual(len(rows),8)
        self.assertLessEqual(sum(len(json.dumps(r,ensure_ascii=False)) for r in rows),12000)
        self.assertTrue(result['context_incomplete'])
        self.assertTrue(result['stores'][1]['remaining_ids'])
        self.assertEqual(self.lookup('不存在的搜索词')['stores'][1]['records'], [])

    def test_many_global_matches_cannot_hide_the_project_target(self):
        for i in range(8):
            habit = self.record(scope='global', kind='preference', claim_type='preference',
                                title='计划优先级 '+str(i), content='开发先列计划 '+str(i))
            saved = self.apply(scope='global', turn='habit-'+str(i), operations=[{'op':'ADD','record':habit}])
            self.assertEqual(saved['status'], 'saved', saved)
        memory_id = self.add_project_rule(title='计划规范', content='复杂改动先列计划。')
        result = self.lookup('计划')
        rows = [r for b in result['stores'] for r in b['records']]
        self.assertEqual(len(rows), 8)
        self.assertIn(memory_id, [r['id'] for r in rows])
        self.assertTrue(result['context_incomplete'])

    def test_large_bodies_and_deferred_search_do_not_look_like_complete_results(self):
        memory_id = self.add_project_rule(title='导出规则',content='导出约束。' * 4000)
        result = self.lookup('导出','project')
        self.assertEqual(result['stores'][0]['records'], [])
        self.assertEqual(result['stores'][0]['remaining_ids'], [memory_id])
        self.assertTrue(result['context_incomplete'])
        with patch.object(store,'_related_records',side_effect=sqlite3.OperationalError('interrupted')):
            result = self.lookup()
        self.assertTrue(result['context_incomplete'])
        self.assertTrue(all(b['status']=='deferred' for b in result['stores']))
        for query in ('', 'x'*10001):
            with self.assertRaises(store.MemoryError):
                self.lookup(query)

    def test_a_target_deleted_between_index_lookup_and_body_read_is_omitted(self):
        self.add_project_rule(title='导出格式', content='导出 XLSX。')
        with patch.object(store,'_select_record',return_value=None):
            result = self.lookup('导出','project')
        self.assertEqual(result['stores'][0]['records'], [])

    def test_cli_query_mode_is_read_only_and_keeps_legacy_input_mode(self):
        memory_id = self.add_project_rule(title='导出格式',content='导出 CSV。',status='candidate')
        env = {**os.environ,'DEV_MEMORY_HOME':str(self.global_root),'PYTHONDONTWRITEBYTECODE':'1'}
        args = [sys.executable,'-B',str(SCRIPTS/'dev_memory.py'),'match',
                '--project-root',str(self.project_a)]
        result = subprocess.run([*args,'--scope','both','--query','导出'],env=env,
                                capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertIn(memory_id,[r['id'] for b in json.loads(result.stdout)['stores'] for r in b['records']])
        legacy = subprocess.run(args,input=json.dumps({'scope':'project','record':self.record()}),env=env,
                                capture_output=True,text=True,encoding='utf-8',check=True)
        self.assertIn('exact_id',json.loads(legacy.stdout))
        invalid = subprocess.run([*args,'--scope','both'],input='{}',env=env,capture_output=True,text=True)
        self.assertNotEqual(invalid.returncode,0)

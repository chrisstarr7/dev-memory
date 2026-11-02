"""Optional disclosure preserves original constraints, budgets, counters and cache isolation."""
import json
from contextlib import closing
from test_dev_memory import MemoryTestCase, store, dev_memory

class ProgressiveTests(MemoryTestCase):
    def test_auto_is_lossless_for_short_body_and_preserves_constraints(self):
        mid=self.add_project_rule(title='receipt format',content='receipt format rule',conditions='复杂任务。',exceptions='紧急修复除外。',dont='不得改变编码。')
        full=store.recall('receipt',project_root=self.project_a,global_root=self.global_root,readonly=True)
        auto=store.recall('receipt',project_root=self.project_a,global_root=self.global_root,readonly=True,disclosure='auto')
        a=auto['stores'][1]['records'][0];f=full['stores'][1]['records'][0]
        self.assertEqual(a['id'],mid)
        for key,value in f.items():
            if value not in (None,'',[],{}):self.assertEqual(a[key],value)
        self.assertLess(len(json.dumps(a)),len(json.dumps(f)))
        self.assertNotIn('preview_instruction',auto['stores'][1])
        self.assertLess(len(json.dumps(auto)),len(json.dumps(full)))
    def test_long_preview_requires_read_and_never_counts_as_recalled_body(self):
        content='receipt invariant '+('x'*1400)
        mid=self.add_project_rule(title='receipt format',content=content,exceptions='仅复杂任务，简单任务例外。')
        result=dev_memory.context('receipt',project_root=self.project_a,global_root=self.global_root,disclosure='auto')
        bucket=result['stores'][1];self.assertEqual(bucket['records'],[])
        self.assertTrue(bucket['context_incomplete']);self.assertIn(mid,bucket['remaining_ids'])
        hint=bucket['unloaded_candidates'][0];self.assertTrue(hint['requires_full_read']);self.assertFalse(hint['content_loaded'])
        self.assertIsNone(bucket.get('recall_tracking'))
        _,db,_=store._config_for('project',self.project_a,self.global_root)
        with closing(store._connect(db,readonly=True)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM recall_counts WHERE memory_id=?',(mid,)).fetchone()[0],0)
        read=store.show_current('project',[mid],project_root=self.project_a,global_root=self.global_root)
        self.assertEqual(read['records'][0]['content'],content)
        self.assertIn('简单任务',read['records'][0]['exceptions'])
    def test_index_does_not_poison_full_cache_or_escape_disabled_store(self):
        mid=self.add_project_rule(title='receipt',content='receipt format')
        first=store.recall('receipt',global_root=self.global_root,project_root=self.project_a,session_id='m',disclosure='index')
        self.assertEqual(first['stores'][1]['records'],[])
        full=store.recall('receipt',global_root=self.global_root,project_root=self.project_a,session_id='m')
        self.assertEqual(full['stores'][1]['records'][0]['id'],mid)
        base,_,cfg=store._config_for('project',self.project_a,self.global_root);cfg['recall_enabled']=False;store.write_json_atomic(base/'config.json',cfg)
        blocked=store.recall('receipt',global_root=self.global_root,project_root=self.project_a,disclosure='auto')
        self.assertEqual(blocked['stores'][1]['status'],'disabled');self.assertNotIn('unloaded_candidates',blocked['stores'][1])
    def test_invalid_mode_is_not_silently_full(self):
        with self.assertRaises(store.MemoryError):store.recall('receipt',global_root=self.global_root,disclosure='bad')
    def test_body_lookup_after_preview_reads_latest_revision(self):
        mid=self.add_project_rule(title='receipt',content='receipt '+('x'*1400))
        preview=store.recall('receipt',project_root=self.project_a,global_root=self.global_root,readonly=True,disclosure='index')
        self.assertEqual(preview['stores'][1]['unloaded_candidates'][0]['revision'],1)
        result=self.apply(scope='project',turn='correct-after-preview',operations=[{'op':'REVISE','id':mid,'expected_revision':1,'record':{'content':'receipt new contract','exceptions':'只适用于复杂任务。','source':self.source('纠正为当前约定。')}}])
        self.assertEqual(result['status'],'saved')
        current=store.show_current('project',[mid],project_root=self.project_a,global_root=self.global_root)['records'][0]
        self.assertEqual(current['revision'],2);self.assertEqual(current['content'],'receipt new contract')
        self.assertEqual(current['exceptions'],'只适用于复杂任务。')

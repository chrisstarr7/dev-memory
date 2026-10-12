"""Synthetic development-cycle and recall regressions; no real private stores."""
from __future__ import annotations
import contextlib
import json
import sqlite3
import sys
import subprocess
from unittest.mock import patch
from test_dev_memory import MemoryTestCase, store, dev_memory


class LifecycleTests(MemoryTestCase):
    def config(self, kind='project', **updates):
        path=store.config_path_for(kind, root=self.project_a, global_root=self.global_root)
        value=json.loads(path.read_text(encoding="utf-8"));value.update(updates);path.write_text(json.dumps(value), encoding="utf-8")

    def test_global_preferences_cannot_starve_project_contract(self):
        for n in range(5):
            self.apply(scope='global',turn=f'global-{n}',operations=[{'op':'ADD','record':self.record(
                scope='global',kind='preference',title=f'Preference {n}',content=f'Confirmed global convention {n}.',
                conditions='All development projects',exceptions='',do='',dont='',verification_steps='')}])
        target=self.add_project_rule(content='Schema amounts must use integer cents.')
        recalled=store.recall('schema amounts cents',project_root=self.project_a,global_root=self.global_root,force=True)
        self.assertIn(target,[r['id'] for r in recalled['stores'][1]['records']])
        self.assertTrue(recalled['stores'][0]['context_incomplete'])

    def test_candidate_limit_is_incomplete_and_never_cached_as_full(self):
        self.config(limits={'max_candidates':100,'max_details':20,'max_context_chars':20000})
        for n in range(9):
            self.add_project_rule(turn=f'candidate-{n}',title=f'Schema {n}',content=f'Schema rule {n}',strength='soft')
        args=dict(project_root=self.project_a,global_root=self.global_root,max_candidates=6,max_details=20,
                  max_chars=20000,session_id='limited-candidates')
        first=store.recall('schema',**args)
        self.assertTrue(first['stores'][1]['context_incomplete'])
        self.assertTrue(first['stores'][1]['candidate_limit_reached'])
        self.assertNotEqual(store.recall('schema',**args)['stores'][1]['status'],'cached')

    def test_latest_checkpoint_wins_even_with_identical_timestamps(self):
        ids=[]
        with patch.object(store,'utc_now',return_value='2026-01-01T00:00:00+00:00'):
            for n in range(7):
                result=self.apply(scope='task',task='cycle',turn=f'stage-{n}',operations=[{'op':'CHECKPOINT',
                    'record':self.record(kind='checkpoint',title=f'Stage {n}',content=f'Completed stage {n}; next stage {n+1}.')}])
                ids.append(result['stores'][0]['operations'][0]['id'])
        records=store.list_records('project',project_root=self.project_a,status='all')['records']
        self.assertEqual([r['id'] for r in records if r['status']=='active'],[ids[-1]])
        result=store.recall('continue',project_root=self.project_a,global_root=self.global_root,resume=True,force=True)
        self.assertEqual([r['id'] for r in result['stores'][1]['records']],[ids[-1]])
        for old in ids[:-1]:
            detail=store.show_record('project',old,project_root=self.project_a)
            self.assertEqual(detail['record']['status'],'superseded')
            self.assertEqual(len(detail['evidence']),1)
            self.assertEqual(len(detail['revisions']),1)

    def test_new_checkpoint_retires_only_its_own_task_and_invalidates_summary(self):
        ids={}
        for task in ('cycle','other'):
            r=self.apply(scope='task',task=task,turn=task,operations=[{'op':'CHECKPOINT','record':self.record(kind='checkpoint',title=task)}])
            ids[task]=r['stores'][0]['operations'][0]['id']
        summary=self.record(kind='summary',title='Old progress summary',derived_from=[ids['cycle']],
                            expected_source_revisions={ids['cycle']:1})
        r=self.apply(scope='task',task='cycle',turn='summary',operations=[{'op':'ADD','record':summary}])
        sid=r['stores'][0]['operations'][0]['id']
        self.apply(scope='task',task='cycle',turn='next',operations=[{'op':'CHECKPOINT','record':self.record(kind='checkpoint',content='Tested; next fix boundary bug.')}])
        self.assertEqual(store.show_record('project',ids['other'],project_root=self.project_a)['record']['status'],'active')
        self.assertEqual(store.show_record('project',sid,project_root=self.project_a)['record']['status'],'stale')

    def test_combined_context_reuses_recall_and_checks_maintenance_without_doctor_probes(self):
        self.add_project_rule()
        kwargs=dict(project_root=self.project_a,global_root=self.global_root,session_id='context-session',query='refund')
        with patch.object(dev_memory,'_codex_version',side_effect=AssertionError('No host probe on normal context')):
            first=dev_memory.context(**kwargs)
            second=dev_memory.context(**kwargs)
        self.assertEqual(first['stores'][1]['status'],'ok')
        self.assertEqual(second['stores'][1]['status'],'cached')
        self.assertIn('maintenance',first['stores'][1])
        _,db=store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],1)

    def test_current_batch_show_is_bounded_and_omits_old_audit_bodies(self):
        ids=[self.add_project_rule(turn=str(n),content=f'Current rule {n}') for n in range(3)]
        result=store.show_current('project',ids,project_root=self.project_a)
        self.assertEqual({r['id'] for r in result['records']},set(ids))
        self.assertTrue(result['audit_not_loaded'])
        self.assertNotIn('revisions',result)
        with self.assertRaises(store.MemoryError):store.show_current('project',ids*3,project_root=self.project_a)

    def test_context_readonly_leaves_recall_cache_unchanged(self):
        self.add_project_rule()
        _,db=store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as c:
            before=c.execute('SELECT COUNT(*) FROM session_context').fetchone()[0]
        result=dev_memory.context(query='refund',project_root=self.project_a,global_root=self.global_root,
                                  session_id='read-only',readonly=True)
        self.assertEqual(result['stores'][1]['maintenance']['status'],'not_requested_readonly')
        with contextlib.closing(sqlite3.connect(db)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM session_context').fetchone()[0],before)

    def test_unknown_workspace_never_claims_cached_or_current_verification(self):
        self.add_project_rule()
        with patch.object(store,'_workspace_signature',return_value=None):
            for _ in range(2):
                result=store.recall('refund',project_root=self.project_a,global_root=self.global_root,session_id='unknown')
                self.assertNotEqual(result['stores'][1]['status'],'cached')
            self.assertEqual(store._verification_status({'verification':{'workspace_fingerprint':'old'}},self.project_a,'head',None),'workspace_unknown')

    def test_dirty_path_overflow_returns_unknown_fingerprint(self):
        result=subprocess.CompletedProcess(['git'],0,stdout=''.join(f' M f{n}\0' for n in range(1001)),stderr='')
        with patch.object(store,'_run_git',return_value=result):
            self.assertIsNone(store._workspace_signature(self.project_a))

    def test_recall_query_timeout_reports_deferred_and_incomplete(self):
        _,db,config=store._config_for('global',None,self.global_root)
        with contextlib.closing(store._connect(db)) as conn:
            for n in range(150):
                record=store._validate_record(self.record(scope='global',kind='preference',
                    title=f'Confirmed convention {n}',content=f'All projects use convention {n}.'),'global',None,config['namespace_id'])
                store._store_record(conn,record)
            conn.commit()
        with patch.object(store.time,'monotonic',side_effect=[0]+[2]*100):
            result=store._recall_store('global',None,self.global_root,'convention',task_id=None,session_id=None,
                module=None,max_candidates=20,max_details=5,max_chars=4000,force=True,readonly=True)
        self.assertEqual(result['status'],'deferred')
        self.assertTrue(result['context_incomplete'])

    def test_combined_context_and_batch_show_work_through_actual_cli(self):
        mid=self.add_project_rule()
        from pathlib import Path
        cli=Path(dev_memory.__file__)
        args=[sys.executable,str(cli),'--global-root',str(self.global_root)]
        context=subprocess.run([*args,'context','--project-root',str(self.project_a),'--query','refund','--readonly'],capture_output=True,text=True, encoding="utf-8")
        self.assertEqual(context.returncode,0,context.stdout+context.stderr)
        self.assertIn('maintenance',json.loads(context.stdout)['stores'][1])
        shown=subprocess.run([*args,'show','--scope','project','--project-root',str(self.project_a),'--ids',mid,'--current'],capture_output=True,text=True, encoding="utf-8")
        self.assertEqual(shown.returncode,0,shown.stdout+shown.stderr)
        self.assertEqual(json.loads(shown.stdout)['records'][0]['id'],mid)

    def test_seven_phase_memory_contract_and_project_switch(self):
        """Deterministic synthetic memory events; this is not an AI workflow timing test."""
        pref=self.apply(scope='global',turn='preference',operations=[{'op':'ADD','record':self.record(
            scope='global',kind='preference',claim_type='preference',tags=['reporting'],title='Reporting order',content='Report results before remaining work.',
            conditions='All development projects',exceptions='',do='',dont='',verification_steps='')}])
        pid=pref['stores'][0]['operations'][0]['id']
        mid=self.add_project_rule(turn='requirements',content='Synthetic refund policy: delivered/unopened within 30 days.',
            conditions='Delivered, unopened, delivery age <=30.',exceptions='Gift/final-sale excluded.',
            source={'type':'user_feedback','excerpt':'Synthetic requirement: delivered/unopened within 30 days; gift/final-sale excluded.'})
        stages=('requirements','schema','api','implementation','integration','testing','bugfix')
        for stage in stages:
            if stage=='implementation':
                corrected=self.record(content='Synthetic refund policy: delivered/unopened within 14 days.',
                    conditions='Delivered, unopened, delivery age <=14.',exceptions='Gift/final-sale excluded.')
                changed=self.apply(turn='correction',scope='project',operations=[{'op':'REVISE','id':mid,
                    'expected_revision':1,'record':corrected}])
                self.assertEqual(changed['stores'][0]['operations'][0]['id'],mid)
            self.apply(scope='task',task='cycle',turn=stage,operations=[{'op':'CHECKPOINT','record':self.record(
                kind='checkpoint',claim_type='observed',content=f'Synthetic fixture reached stage:{stage}; continue with the next stage.',
                source={'type':'code_observation','excerpt':f'Synthetic stage event: {stage}.'})}])
            context=dev_memory.context(query=f'refund stage:{stage}',project_root=self.project_a,
                global_root=self.global_root,task_id='cycle',force=True)
            bucket=context['stores'][1]
            relevant={r['id']:r for r in bucket['records']}
            if mid not in relevant:
                relevant.update({r['id']:r for r in store.show_current('project',[mid],project_root=self.project_a)['records']})
            self.assertIn(mid,relevant)
            expected='<=14' if stages.index(stage)>=3 else '<=30'
            self.assertIn(expected,relevant[mid]['conditions'])
            self.assertEqual(relevant[mid]['exceptions'],'Gift/final-sale excluded.')
        current=store.list_records('project',project_root=self.project_a)['records']
        self.assertEqual(sum(r['kind']=='checkpoint' for r in current),1)
        self.assertEqual(sum(r['kind']=='business_rule' for r in current),1)
        history=store.show_record('project',mid,project_root=self.project_a)
        self.assertTrue(history['revisions'])
        b=dev_memory.context(query='cancellation',project_root=self.project_b,global_root=self.global_root,force=True)
        self.assertIn(pid,[r['id'] for r in b['stores'][0]['records']])
        self.assertEqual(b['stores'][1]['records'],[])
        self.assertTrue(b['stores'][1]['empty_store'])
        self.assertNotIn('refund',json.dumps(b['stores'][0]['records']).lower())

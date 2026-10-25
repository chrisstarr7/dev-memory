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
    def test_focused_recall_prioritizes_relevant_rule_over_unrelated_hard_history(self):
        relevant = self.add_project_rule(turn='related', strength='informational', title='Refund eligibility',
                                        content='Refund eligibility uses the confirmed conditions.',
                                        source_refs=['contract:refund-v2'], code_refs=['refunds.py'])
        for n in range(12):
            self.add_project_rule(turn=f'noise-{n}', title=f'Inventory requirement {n}', content=f'Inventory count rule {n}.',
                                  conditions='', exceptions='', do='', dont='', verification_steps='', tags=['inventory'])
        response = store.recall('refund', project_root=self.project_a, global_root=self.global_root,
                                session_id='focused', max_details=3)
        project = response['stores'][1]
        self.assertEqual(project['records'][0]['id'], relevant)
        self.assertEqual(project['records'][0]['source_refs'], ['contract:refund-v2'])
        self.assertEqual(project['records'][0]['code_refs'], ['refunds.py'])
        self.assertTrue(project['context_incomplete'])
        self.assertTrue(project['unloaded_candidates'])
        self.assertTrue(all(c['content_loaded'] is False and 'content' not in c for c in project['unloaded_candidates']))
        self.assertLessEqual(len(project['unloaded_candidates']), 8)
        self.assertLessEqual(sum(len(json.dumps(c, ensure_ascii=False)) for c in project['unloaded_candidates']), 2000)

    def test_use_is_revision_guarded_receipt_without_new_memory_or_evidence(self):
        memory_id = self.add_project_rule()
        before = store.show_record('project', memory_id, project_root=self.project_a)
        result = self.apply(scope='project', turn='used', operations=[{
            'op':'USE', 'id':memory_id, 'expected_revision':1,
            'reason':'Implemented every applicable positive condition and exclusion.', 'action_ref':'refunds.py:eligible',
        }])
        self.assertEqual(result['status'], 'checked_noop', result)
        operation = result['stores'][0]['operations'][0]
        self.assertEqual(operation['usage'], 'ai_reported_not_behavior_verified')
        self.assertEqual(result['stores'][0]['data_revision'], 1)
        after = store.show_record('project', memory_id, project_root=self.project_a)
        self.assertEqual(before, after)
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            receipt = json.loads(conn.execute("SELECT result_json FROM receipts WHERE turn_id='used'").fetchone()[0])
        self.assertEqual(receipt[0]['used_id'], memory_id)
        self.assertNotIn('reason', receipt[0])
        self.assertNotIn('action_ref', receipt[0])
        self.assertEqual(operation['action_ref'], 'refunds.py:eligible')
        for label, fields, error in [('stale', {'expected_revision':99}, 'revision_conflict'),
                                      ('fake-source', {'source':{'type':'user_statement'}}, 'validation_error')]:
            failed = self.apply(scope='project', turn=label, operations=[{
                'op':'USE', 'id':memory_id, 'expected_revision':1, 'reason':'Used.', 'action_ref':'implementation', **fields,
            }])
            self.assertEqual(failed['stores'][0]['error'], error)

    def test_use_cannot_place_project_path_in_global_receipt(self):
        preference = self.apply(scope='global', turn='pref', operations=[{'op':'ADD','record':self.record(scope='global',kind='preference')}])
        pref_id = preference['stores'][0]['operations'][0]['id']
        failed = self.apply(scope='global', turn='global-path-use', operations=[{
            'op':'USE','id':pref_id,'expected_revision':1,'reason':'Applied preference.','action_ref':'/Users/example/private-project/api.py'}])
        self.assertEqual(failed['stores'][0]['error'], 'scope_error')

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

    def test_context_can_recall_and_maintain_only_global_and_project_memory(self):
        legacy_id = self.add_project_rule(turn='legacy-progress', title='Old task progress')
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE memories SET scope='task',kind='checkpoint' WHERE id=?", (legacy_id,))
            conn.commit()
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='session_bindings'").fetchone())
        project_id = self.add_project_rule(turn='durable-rule', title='Durable project rule')
        current = dev_memory.context('continue', project_root=self.project_a, global_root=self.global_root,
                                     session_id='session-test', force=True)
        self.assertNotIn(legacy_id, [r['id'] for r in current['stores'][1]['records']])
        self.assertIn(project_id, [r['id'] for r in current['stores'][1]['records']])
        self.assertEqual(current['stores'][1]['maintenance']['pending_up_to_threshold'], 1)
        cli = subprocess.run([sys.executable, str(dev_memory.__file__), '--global-root', str(self.global_root),
                              'context', '--project-root', str(self.project_a), '--query', 'continue',
                              '--session-id', 'session-test', '--force'],
                             cwd=self.project_a, capture_output=True, text=True, encoding='utf-8', check=True)
        response = json.loads(cli.stdout)
        self.assertNotIn(legacy_id, [r['id'] for r in response['stores'][1]['records']])

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
        with patch.object(store,'_workspace_signature',side_effect=AssertionError('Unverified reads need no workspace scan')):
            result=store.show_current('project',ids,project_root=self.project_a)
            self.assertIsNone(store.show_record('project',ids[0],project_root=self.project_a)['record']['verification_status'])
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
            result=store._recall_store('global',None,self.global_root,'convention',session_id=None,
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

    def test_project_borrows_unused_global_budget_without_cache_churn(self):
        self.apply(scope='global',task='one-task',turn='inactive-habit',operations=[{'op':'ADD','record':{
            'kind':'preference','claim_type':'preference','strength':'soft','status':'candidate',
            'cross_project_confirmed':False,'title':'Reuse','content':'Inspect suitable existing implementations.',
            'source':{'type':'user_feedback','excerpt':'The user chose checking existing implementations.'}}}])
        for n in range(3):
            self.add_project_rule(turn=f'rule-{n}',content=f'Project payment rule {n}.',
                conditions='',exceptions='',do='',dont='',verification_steps='')
        kwargs=dict(query='payment',project_root=self.project_a,global_root=self.global_root,session_id='borrow')
        first=dev_memory.context(**kwargs)
        self.assertEqual(len(first['stores'][1]['records']),3)
        self.assertFalse(first['stores'][1]['context_incomplete'])
        second=dev_memory.context(**kwargs)
        self.assertEqual([r['status'] for r in second['stores']],['cached','cached'])
        self.apply(scope='global',turn='confirmed-global',operations=[{'op':'ADD','record':self.record(
            scope='global',kind='preference',title='Reporting',content='Report outcomes before remaining gaps.')}])
        changed=dev_memory.context(**kwargs)
        self.assertEqual(len(changed['stores'][0]['records']),1)
        self.assertLessEqual(len(changed['stores'][1]['records']),2)
        self.assertTrue(changed['stores'][1]['context_incomplete'])

    def test_disabled_or_excluded_memory_cannot_be_read_through_inspection(self):
        ids={}
        ids['project']=self.add_project_rule(content='Synthetic private project constraint.')
        result=self.apply(scope='global',turn='global-rule',operations=[{'op':'ADD','record':self.record(
            scope='global',kind='preference',content='Use a consistent reporting order.')}])
        ids['global']=result['stores'][0]['operations'][0]['id']
        for kind in ('global','project'):
            path=store.config_path_for(kind,root=self.project_a,global_root=self.global_root)
            original=path.read_bytes()
            for control in ({'recall_enabled':False},{'excluded':True}):
                try:
                    config=json.loads(original);config.update(control);store.write_json_atomic(path,config)
                    shown=store.show_record(kind,ids[kind],project_root=self.project_a,global_root=self.global_root)
                    listed=store.list_records(kind,project_root=self.project_a,global_root=self.global_root)
                    self.assertEqual(shown.get('status'),'disabled')
                    self.assertNotIn('record',shown)
                    self.assertNotIn('evidence',shown)
                    self.assertEqual(listed.get('status'),'disabled')
                    self.assertEqual(listed['records'],[])
                finally:path.write_bytes(original)

    def test_current_lookup_labels_stale_verification_and_checks_workspace_once(self):
        (self.project_a/'app.py').write_text('PAYMENT_LIMIT = 30\n',encoding='utf-8')
        record=self.record(kind='lesson',claim_type='observed',content='The refund boundary regression passed on the checked source.',
            source={'type':'tool_result','excerpt':'The actual regression command completed with exit code zero.'},
            verification={'command':'python -m unittest','finished_at':'2026-10-22T00:00:00Z',
                          'code_version':'synthetic-v1','exit_code':0})
        memory_id=self.apply(scope='project',operations=[{'op':'ADD','record':record}])['stores'][0]['operations'][0]['id']
        other=self.apply(scope='project',turn='other-result',operations=[{'op':'ADD','record':{**record,'title':'Other check','content':'A separate durable regression check.'}}])['stores'][0]['operations'][0]['id']
        (self.project_a/'app.py').write_text('PAYMENT_LIMIT = 14\n',encoding='utf-8')
        with patch.object(store,'_workspace_signature',wraps=store._workspace_signature) as fingerprint:
            shown_records=store.show_current('project',[memory_id,other],project_root=self.project_a)['records']
            shown=shown_records[0]
            self.assertTrue(all(r['verification_status']=='stale_workspace_changed' for r in shown_records))
            self.assertEqual(fingerprint.call_count,1)
        self.assertEqual(shown['verification_status'],store.show_record('project',memory_id,project_root=self.project_a)['record']['verification_status'])
        summary=store.consolidate_sources('project',[memory_id],project_root=self.project_a)
        self.assertEqual(summary['sources'][0]['verification_status'],'stale_workspace_changed')

    def test_code_observation_cannot_become_a_desired_convention(self):
        for n,claim in enumerate(('desired','preference')):
            result=self.apply(scope='project',turn=f'legacy-code-{n}',operations=[{'op':'ADD',
                'record':self.record(kind='convention',claim_type=claim,
                    content='Always keep the observed permissive authorization behavior.',
                    code_refs=['auth.py#authorize'],
                    source={'type':'code_observation','excerpt':'Existing code returns true without checking permission.'})}])
            self.assertEqual(result['stores'][0]['error'],'provenance_error')
        observed=self.add_project_rule(turn='observed-only',kind='project_fact',claim_type='observed',
            content='The legacy authorization path currently returns true without checking permission.',
            code_refs=['auth.py#authorize'],
            source={'type':'code_observation','excerpt':'Observed the implementation; this is not a required behavior.'})
        self.assertEqual(store.show_record('project',observed,project_root=self.project_a)['record']['claim_type'],'observed')

    def test_project_code_observation_requires_a_source_reference(self):
        missing=self.apply(scope='project',turn='observed-no-ref',operations=[{'op':'ADD','scope':'project',
            'record':self.record(kind='project_fact',claim_type='observed',
                source={'type':'code_observation','excerpt':'Observed current behavior.'})}])
        self.assertEqual(missing['stores'][0]['error'],'provenance_error')
        saved=self.apply(scope='project',turn='observed-with-ref',operations=[{'op':'ADD','scope':'project',
            'record':self.record(kind='project_fact',claim_type='observed',code_refs=['auth.py#authorize'],
                source={'type':'code_observation','excerpt':'Observed current behavior.'})}])
        self.assertEqual(saved['status'],'saved',saved)

    def test_seven_phase_memory_contract_and_project_switch(self):
        """Deterministic synthetic memory events; this is not an AI workflow timing test."""
        pref=self.apply(scope='global',turn='preference',operations=[{'op':'ADD','record':self.record(
            scope='global',kind='preference',claim_type='preference',tags=['reporting'],title='Reporting order',content='Report results before remaining work.',
            conditions='All development projects',exceptions='',do='',dont='',verification_steps='')}])
        pid=pref['stores'][0]['operations'][0]['id']
        mid=self.add_project_rule(turn='requirements',content='Synthetic refund policy: delivered/unopened within 30 days.',
            conditions='Delivered, unopened, delivery age <=30.',exceptions='Gift/final-sale excluded.',
            source={'type':'user_feedback','excerpt':'Synthetic requirement: delivered/unopened within 30 days; gift/final-sale excluded.'})
        stages=('requirements','design','api','implementation','verification','bugfix','delivery')
        last_loaded=None
        for stage in stages:
            if stage=='implementation':
                corrected=self.record(content='Synthetic refund policy: delivered/unopened within 14 days.',
                    conditions='Delivered, unopened, delivery age <=14.',exceptions='Gift/final-sale excluded.')
                changed=self.apply(turn='correction',scope='project',operations=[{'op':'REVISE','id':mid,
                    'expected_revision':1,'record':corrected}])
                self.assertEqual(changed['stores'][0]['operations'][0]['id'],mid)
            context=dev_memory.context(query='refund eligibility',project_root=self.project_a,
                global_root=self.global_root,session_id='cycle')
            bucket=context['stores'][1]
            relevant={r['id']:r for r in bucket['records']}
            if mid not in relevant:
                self.assertEqual(bucket['status'],'cached')
                relevant[mid]=last_loaded
            else:
                self.assertEqual(bucket['status'],'ok')
                last_loaded=relevant[mid]
            self.assertIn(mid,relevant)
            expected='<=14' if stages.index(stage)>=3 else '<=30'
            self.assertIn(expected,relevant[mid]['conditions'])
            self.assertEqual(relevant[mid]['exceptions'],'Gift/final-sale excluded.')
        current=store.list_records('project',project_root=self.project_a)['records']
        self.assertFalse(any(r['scope']=='task' or r['kind']=='checkpoint' for r in current))
        self.assertEqual(sum(r['kind']=='business_rule' for r in current),1)
        history=store.show_record('project',mid,project_root=self.project_a)
        self.assertEqual(history['record']['revision'],2)
        self.assertEqual(len(history['revisions']),1)
        _,db=store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='session_bindings'").fetchone())
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],2)
        b=dev_memory.context(query='cancellation',project_root=self.project_b,global_root=self.global_root,force=True)
        self.assertIn(pid,[r['id'] for r in b['stores'][0]['records']])
        self.assertEqual(b['stores'][1]['records'],[])
        self.assertTrue(b['stores'][1]['empty_store'])
        self.assertNotIn('refund',json.dumps(b['stores'][0]['records']).lower())

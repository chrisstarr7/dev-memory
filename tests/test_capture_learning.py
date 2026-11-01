"""First-signal capture and activation diagnosis, using isolated user stores."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from test_dev_memory import MemoryTestCase, store, dev_memory, SCRIPTS
import dev_memory_setup as setup


class CaptureTests(MemoryTestCase):
    def test_partial_correction_preserves_unmentioned_constraints_and_history(self):
        memory_id = self.add_project_rule(source_refs=['policy.md#refunds'])
        before = store.show_record('project', memory_id, project_root=self.project_a)['record']
        result = self.apply(scope='project', turn='narrow-correction', operations=[{
            'op':'REVISE', 'id':memory_id, 'expected_revision':1,
            'record':{'kind':'business_rule', 'claim_type':'desired', 'title':'退款规则',
                      'content':'退款需由人工审核。',
                      'source':self.source('增加人工审核要求，其余退款条件保持不变。', 'user_feedback')}}])
        self.assertEqual(result['status'], 'saved', result)
        detail = store.show_record('project', memory_id, project_root=self.project_a)
        for field in ('kind','claim_type','status','strength','title','conditions','exceptions',
                      'do','dont','verification_steps','tags','source_refs'):
            self.assertEqual(detail['record'][field], before[field], field)
        self.assertEqual(detail['record']['content'], '退款需由人工审核。')
        self.assertEqual(json.loads(detail['revisions'][0]['snapshot'])['content'], before['content'])
        self.assertEqual(len(detail['evidence']), 2)
        recalled = store.recall('退款', project_root=self.project_a, global_root=self.global_root,
                                force=True, readonly=True)['stores'][1]['records'][0]
        self.assertEqual(recalled['exceptions'], before['exceptions'])
        self.assertEqual(recalled['content'], '退款需由人工审核。')

    def test_explicit_constraint_removal_is_distinct_from_omission_and_stale_save(self):
        memory_id = self.add_project_rule()
        operation = {'op':'REVISE', 'id':memory_id, 'expected_revision':1,
                     'record':{'exceptions':'', 'dont':'', 'source_refs':[],
                               'source':self.source('明确取消礼品和最终销售商品的排除项。', 'user_feedback')}}
        self.assertEqual(self.apply(scope='project', turn='remove-exclusions', operations=[operation])['status'], 'saved')
        current = store.show_record('project', memory_id, project_root=self.project_a)['record']
        self.assertEqual((current['exceptions'], current['dont'], current['source_refs']), ('','',[]))
        stale = self.apply(scope='project', turn='stale-correction', operations=[operation])
        self.assertEqual(stale['stores'][0]['error'], 'revision_conflict')
        self.assertEqual(store.show_record('project', memory_id, project_root=self.project_a)['record']['revision'], 2)

    def test_partial_revision_needs_fresh_source_and_does_not_inherit_verification(self):
        memory_id = self.add_project_rule(
            source=self.source('已执行合成检查。', 'tool_result'),
            verification={'command':'python check.py', 'finished_at':'2026-11-01T00:00:00Z',
                          'code_version':'fixture-v1', 'exit_code':0})
        operation = {'op':'REVISE', 'id':memory_id, 'expected_revision':1,
                     'record':{'content':'修正后的退款约束。'}}
        rejected = self.apply(scope='project', turn='missing-authority', operations=[operation])
        self.assertEqual(rejected['stores'][0]['error'], 'provenance_error')
        operation['record']['source'] = self.source('要求修正退款约束，尚未执行新检查。', 'user_feedback')
        result = self.apply(scope='project', turn='fresh-authority', operations=[operation])
        self.assertEqual(result['status'], 'saved', result)
        detail = store.show_record('project', memory_id, project_root=self.project_a)
        self.assertEqual(detail['record']['verification'], {})
        self.assertIsNone(detail['record']['last_verified_at'])
        self.assertTrue(json.loads(detail['revisions'][0]['snapshot'])['verification'])

    def test_editing_an_archived_rule_does_not_implicitly_reactivate_it(self):
        memory_id = self.add_project_rule(status='archived')
        result = self.apply(scope='project', turn='archived-edit', operations=[{
            'op':'REVISE', 'id':memory_id, 'expected_revision':1,
            'record':{'content':'修正历史记录的描述。', 'source':self.source('仅修正历史描述。')}}])
        self.assertEqual(result['status'], 'saved', result)
        self.assertEqual(store.show_record('project', memory_id, project_root=self.project_a)['record']['status'], 'archived')
        recalled = store.recall('退款', project_root=self.project_a, global_root=self.global_root, force=True)
        self.assertNotIn(memory_id, [r['id'] for r in recalled['stores'][1]['records']])

    def test_partial_global_revision_keeps_controlled_independent_task_evidence(self):
        first = self.signal('user_statement', 'task-one', 'first')['stores'][0]['operations'][0]
        for task, turn, expected_status, signals in (
                ('task-one','same-task','candidate',1), ('task-two','another-task','active',2)):
            current = store.show_record('global', first['id'], global_root=self.global_root)['record']
            result = self.apply(scope='global', task=task, turn=turn, operations=[{
                'op':'REVISE', 'id':first['id'], 'expected_revision':current['revision'],
                'record':{'title':'Reuse suitable code', 'scope':'project',
                          'source':{'type':'user_statement','message_id':'caller-controlled',
                                    'excerpt':'User chose the same reuse preference.'}}}])
            self.assertEqual(result['status'], 'saved', result)
            op = result['stores'][0]['operations'][0]
            self.assertEqual((op['memory_status'],op['independent_task_signals']), (expected_status,signals))
        evidence = store.show_record('global', first['id'], global_root=self.global_root)['evidence']
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(e['ingestion_id'].startswith('habit:') and e['message_id'] is None for e in evidence))

    def test_partial_global_revision_requires_task_and_pins_idempotency_to_it(self):
        first = self.signal('user_statement', 'task-one', 'first')['stores'][0]['operations'][0]
        operation = {'op':'REVISE','id':first['id'],'expected_revision':first['revision'],
                     'record':{'title':'Reuse suitable code', 'source':self.source('Same preference.')}}
        rejected = self.apply(scope='global', turn='missing-task', operations=[operation])
        self.assertEqual(rejected['stores'][0]['error'], 'provenance_error')
        saved = self.apply(scope='global', task='task-one', turn='same-turn', operations=[operation])
        self.assertEqual(saved['status'], 'saved', saved)
        replay = self.apply(scope='global', task='task-two', turn='same-turn', operations=[operation])
        self.assertEqual(replay['stores'][0]['error'], 'idempotency_conflict')

    def habit(self, source_type='user_statement'):
        return {'kind':'preference', 'claim_type':'preference', 'status':'candidate', 'strength':'soft',
                'cross_project_confirmed':False, 'title':'Reuse suitable existing code',
                'content':'Inspect suitable existing code before adding another implementation.',
                'conditions':'When existing code may satisfy the requirement.', 'tags':['implementation'],
                'source':{'type':source_type, 'excerpt':'User chose inspecting a suitable implementation before adding another.'}}

    def signal(self, source_type, task, turn):
        return self.apply(scope='global',task=task,turn=turn,
                          operations=[{'op':'ADD','scope':'global','record':self.habit(source_type)}])

    def test_first_user_requirement_is_saved_but_not_applied_as_a_rule(self):
        result = self.signal('user_statement','first-task','first-turn')
        op = result['stores'][0]['operations'][0]
        self.assertEqual((result['status'],op['memory_status'],op['independent_task_signals']),('saved','candidate',1))
        record = store.show_record('global',op['id'],global_root=self.global_root)
        self.assertEqual(record['evidence'][0]['source_type'],'user_statement')
        recall = store.recall('reuse code',global_root=self.global_root,force=True)
        self.assertEqual(recall['stores'][0]['records'],[])
        candidates = store.list_records('global',global_root=self.global_root,status='candidate')['records']
        self.assertEqual([r['id'] for r in candidates],[op['id']])

    def test_changing_user_source_type_in_one_task_does_not_create_independence(self):
        ids=[]
        for n,source in enumerate(store.USER_SOURCES):
            result=self.signal(source,'same-task',f'turn-{n}')
            op=result['stores'][0]['operations'][0];ids.append(op['id'])
            self.assertEqual((op['memory_status'],op['independent_task_signals']),('candidate',1))
        self.assertEqual(len(set(ids)),1)
        second=self.signal('user_confirmation','second-task','confirmed-choice')['stores'][0]['operations'][0]
        self.assertEqual((second['id'],second['memory_status'],second['habit_promoted']),(ids[0],'active',True))

    def test_all_direct_user_sources_can_start_a_candidate(self):
        for n,source in enumerate(store.USER_SOURCES):
            record=self.habit(source);record['content']+=f' Subject {n}.'
            result=self.apply(scope='global',task='one-task',turn=f'source-{n}',operations=[{'op':'ADD','record':record}])
            self.assertEqual(result['status'],'saved',result)

    def test_matching_a_candidate_is_read_only_then_new_evidence_reuses_its_body(self):
        first=self.signal('user_statement','task-one','first')['stores'][0]['operations'][0]
        proposal=self.habit('user_confirmation')
        proposal['content']='Check whether suitable existing code can be reused before adding another implementation.'
        match=store.match_payload({'scope':'global','record':proposal},global_root=self.global_root)
        self.assertIn(first['id'],[r['id'] for r in match['records']])
        self.assertIn('no evidence was saved',match['instruction'])
        self.assertEqual(len(store.show_record('global',first['id'],global_root=self.global_root)['evidence']),1)
        result=self.apply(scope='global',task='task-two',turn='second',operations=[{
            'op':'ADD','duplicate_of':first['id'],'expected_revision':1,'equivalent':True,'record':proposal}])
        op=result['stores'][0]['operations'][0]
        self.assertEqual((op['id'],op['memory_status'],op['body_written']),(first['id'],'active',False))
        self.assertEqual(len(store.list_records('global',global_root=self.global_root,status='all')['records']),1)

    def test_non_user_sources_and_project_markers_still_fail(self):
        for n,source in enumerate(['model_inference','tool_result','code_observation','external_reference']):
            result=self.signal(source,'task-one',f'non-user-{n}')
            self.assertEqual(result['stores'][0]['error'],'provenance_error')
        record=self.habit();record['source']['excerpt']='User choice for project_id:private-team.'
        result=self.apply(scope='global',task='task-one',turn='private-project',operations=[{'op':'ADD','record':record}])
        self.assertEqual(result['stores'][0]['error'],'scope_error')

    def test_other_global_kinds_cannot_bypass_candidate_provenance(self):
        record=self.habit();record['kind']='procedure';record['source']['message_id']='uncontrolled-project-reference'
        result=self.apply(scope='global',turn='wrong-kind',operations=[{'op':'ADD','record':record}])
        self.assertEqual(result['stores'][0]['error'],'scope_error')

    def test_user_statement_evidence_promotes_through_existing_revision_guard(self):
        first=self.signal('user_statement','task-one','first')['stores'][0]['operations'][0]
        result=self.apply(scope='global',task='task-two',turn='second',operations=[{
            'op':'ADD_EVIDENCE','id':first['id'],'expected_revision':1,
            'source':{'type':'user_confirmation','excerpt':'User selected the same reuse approach.'}}])
        op=result['stores'][0]['operations'][0]
        self.assertEqual((op['memory_status'],op['independent_task_signals']),('active',2))
        evidence=store.show_record('global',first['id'],global_root=self.global_root)['evidence']
        self.assertTrue(all(e['ingestion_id'].startswith('habit:') and e['message_id'] is None for e in evidence))

    def test_pause_and_opt_out_still_block_first_signal(self):
        store.set_capture('global',False,global_root=self.global_root)
        self.assertEqual(self.signal('user_statement','task-one','paused')['status'],'skipped_private')
        store.set_capture('global',True,global_root=self.global_root)
        store.record_private_skip('global',session_id='session-test',turn_id='private',global_root=self.global_root)
        self.assertEqual(self.signal('user_confirmation','task-two','private')['status'],'skipped_private')
        self.assertEqual(store.list_records('global',global_root=self.global_root,status='all')['records'],[])

    def test_status_counts_distinguish_persisted_candidates_from_active_rules(self):
        self.signal('user_statement','first-task','one')
        status=store.get_store_status('global',global_root=self.global_root)
        self.assertEqual((status['active_count'],status['candidate_count']),(0,1))
        self.signal('user_feedback','second-task','two')
        status=store.get_store_status('global',global_root=self.global_root)
        self.assertEqual((status['active_count'],status['candidate_count']),(1,0))

    def test_user_only_setup_cli_configures_no_project_and_preserves_pause(self):
        codex=self.home/'codex';codex.mkdir();guide=codex/'AGENTS.md';guide.write_bytes(b'Keep existing instructions.\r\n')
        store.set_capture('global',False,global_root=self.global_root)
        env={**os.environ,'HOME':str(self.home),'USERPROFILE':str(self.home),'CODEX_HOME':str(codex),
             'DEV_MEMORY_HOME':str(self.global_root),'PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-B',str(SCRIPTS/'dev_memory.py'),'setup','--user'],
                              cwd=self.home,env=env,text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout)['mode'],'user_global_habits')
        self.assertTrue(guide.read_bytes().endswith(b'Keep existing instructions.\r\n'))
        self.assertFalse((self.home/'.dev-memory').exists())
        with patch.dict(os.environ,{'CODEX_HOME':str(codex)}):
            self.assertEqual(setup.user_status(dev_memory.PACKAGE_ROOT)['status'],'configured')
        self.assertFalse(store.get_store_status('global',global_root=self.global_root)['capture_enabled'])

    def test_user_status_respects_override_and_different_runtime(self):
        codex=self.home/'codex';codex.mkdir()
        with patch.dict(os.environ,{'CODEX_HOME':str(codex)}):
            self.assertEqual(setup.user_status(dev_memory.PACKAGE_ROOT)['status'],'not_configured')
            setup.setup_user('codex',dev_memory.PACKAGE_ROOT,sys.executable,self.global_root)
            self.assertEqual(setup.user_status(dev_memory.PACKAGE_ROOT)['status'],'configured')
            self.assertEqual(setup.user_status(self.home/'other-runtime')['status'],'binding_mismatch')
            (codex/'AGENTS.override.md').write_text('An unrelated override shadows the base file.')
            self.assertEqual(setup.user_status(dev_memory.PACKAGE_ROOT)['status'],'not_configured')

    def test_doctor_reports_runtime_and_activation_without_initializing(self):
        codex=self.home/'codex'
        with patch.dict(os.environ,{'CODEX_HOME':str(codex)}):
            report=dev_memory.doctor(None,self.global_root)
            self.assertEqual(report['user_activation']['status'],'not_configured')
            self.assertEqual(report['skill_version'],'.'.join(map(str,dev_memory._release_version(dev_memory.PACKAGE_ROOT))))
            self.assertFalse(codex.exists())
            setup.setup_user('codex',dev_memory.PACKAGE_ROOT,sys.executable,self.global_root)
            report=dev_memory.doctor(None,self.global_root)
            self.assertEqual(report['mode'],'user_guided')
            self.assertFalse(report['user_activation']['host_e2e_verified'])

    def test_doctor_reports_a_different_global_root_instead_of_false_empty_binding(self):
        codex=self.home/'codex'
        other=self.home/'other-data';store.init_global(other)
        self.signal('user_statement','task-one','first')
        with patch.dict(os.environ,{'CODEX_HOME':str(codex)}):
            setup.setup_user('codex',dev_memory.PACKAGE_ROOT,sys.executable,self.global_root)
            report=dev_memory.doctor(None,other)
            self.assertEqual(report['user_activation']['status'],'binding_mismatch')
            self.assertEqual(report['user_activation']['reason'],'global_root_mismatch')
            self.assertEqual(report['user_activation']['global_root'],str(self.global_root.resolve()))
            self.assertNotEqual(report['mode'],'user_guided')
            self.assertEqual(store.get_store_status('global',global_root=self.global_root)['candidate_count'],1)

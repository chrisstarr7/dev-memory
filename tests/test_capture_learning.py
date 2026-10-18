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

"""Observable hot-path, habit evidence and cold storage contracts; synthetic stores only."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from test_dev_memory import MemoryTestCase, store, dev_memory, SCRIPTS
import codex_hook


class EfficiencyTests(MemoryTestCase):
    def test_runtime_check_never_probes_hosts_or_private_stores(self):
        output = io.StringIO()
        with patch.object(store, 'locate_project_root', side_effect=AssertionError('No project discovery')), \
             patch.object(dev_memory, 'doctor', side_effect=AssertionError('No full diagnostics')), \
             patch.object(dev_memory.subprocess, 'run', side_effect=AssertionError('No child processes')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(dev_memory.main(['runtime-check']), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['base_mode'], 'available')
        self.assertEqual(result['sqlite'], sqlite3.sqlite_version)

    def test_unverified_recall_without_cache_never_probes_git(self):
        memory_id = self.add_project_rule()
        for options in ({}, {'readonly': True, 'session_id': 'read-only'}, {'force': True}):
            with patch.object(store, '_run_git', side_effect=AssertionError('No Git needed without cache or verification')):
                result = store.recall('refund', project_root=self.project_a, global_root=self.global_root,
                                      **options)
            self.assertEqual([r['id'] for r in result['stores'][1]['records']], [memory_id])
            self.assertIsNone(result['stores'][1]['records'][0]['verification_status'])

    def test_uncached_verified_recall_checks_one_snapshot_and_preserves_staleness(self):
        path = self.project_a / 'refunds.py'
        path.write_text('limit = 14\n', encoding='utf-8')
        for n in range(2):
            self.add_project_rule(turn=f'verified-{n}', kind='lesson', claim_type='observed',
                title=f'Refund regression {n}', content=f'Refund boundary check {n} passed.',
                conditions='', exceptions='', do='', dont='', verification_steps='',
                source=self.source('The check exited successfully.', 'tool_result'),
                verification={'command':'python -m unittest', 'finished_at':'2026-10-22T00:00:00Z',
                              'code_version':'fixture-v1', 'exit_code':0})
        for expected in ('current_workspace', 'stale_workspace_changed', 'workspace_unknown'):
            if expected == 'stale_workspace_changed':
                path.write_text('limit = 300\n', encoding='utf-8')
            with patch.object(store, '_workspace_signature',
                              **({'return_value':None} if expected == 'workspace_unknown' else {'wraps':store._workspace_signature})) as fingerprint:
                result = store.recall('refund', project_root=self.project_a, global_root=self.global_root,
                                      readonly=True)
            records = result['stores'][1]['records']
            self.assertEqual(len(records), 2)
            self.assertEqual({r['verification_status'] for r in records}, {expected})
            self.assertEqual(fingerprint.call_count, 1)

    def habit(self, **updates):
        return dict(kind='preference', claim_type='preference', strength='soft', status='candidate',
                    cross_project_confirmed=False, title='Reuse suitable code', content='Reuse suitable existing code.',
                    conditions='When the implementation fits.', exceptions='', do='Inspect existing behavior.',
                    dont='Do not duplicate a suitable implementation.', tags=['implementation'],
                    source={'type':'user_feedback', 'excerpt':'User chose to reuse suitable existing code.'}, **updates)

    def test_stdin_file_inputs_share_validation_and_accept_dash(self):
        for path in (None, Path('-')):
            with patch.object(sys, 'stdin', io.StringIO('{"scope":"global"}')):
                self.assertEqual(dev_memory._read_payload(path), {'scope':'global'})
        source = self.home/'payload.json'
        source.write_text('[]')
        with self.assertRaises(store.MemoryError):
            dev_memory._read_payload(source)
        source.write_text(' ' * 1_000_001)
        with self.assertRaises(store.MemoryError):
            dev_memory._read_payload(source)

    def test_global_match_ignores_envelope_task_but_rejects_record_task(self):
        record = self.habit()
        matched = store.match_payload({'scope':'global','task_id':'opaque-task','record':record},global_root=self.global_root)
        self.assertEqual(matched['status'],'compare')
        record['task_id'] = 'must-not-enter-global'
        with self.assertRaises(store.MemoryError):
            store.match_payload({'scope':'global','record':record},global_root=self.global_root)

    def test_user_activation_separates_confirmed_instructions_from_candidates(self):
        import dev_memory_setup
        block = dev_memory_setup._user_block(Path('/synthetic/skill'), sys.executable, self.global_root)
        explicit, inferred = block.split('- At every development turn', 1)
        self.assertIn('status: active', explicit)
        self.assertIn('cross_project_confirmed: true', explicit)
        self.assertNotIn('status: candidate', explicit)
        self.assertIn('status: candidate', inferred)
        self.assertIn('cross_project_confirmed: false', inferred)

    def test_repeated_activation_preserves_crlf_bytes(self):
        import dev_memory_setup
        block = dev_memory_setup._user_block(Path('/synthetic/skill'), sys.executable, self.global_root)
        user = ('Keep my instructions.\r\n' + block.replace('\n','\r\n') + '\r\n').encode()
        self.assertEqual(dev_memory_setup._merge_user_guide(user,block),user)
        project = ('Keep team instructions.\r\n' + dev_memory_setup.BLOCK.replace('\n','\r\n')).encode()
        self.assertEqual(dev_memory_setup._merged(project,'codex'),project)
        cursor = b'---\r\nalwaysApply: true\r\n---\r\n' + project
        self.assertEqual(dev_memory_setup._merged(cursor,'cursor'),cursor)

    def test_paraphrase_and_evidence_only_paths_promote_without_duplicate_bodies(self):
        saved = self.apply(scope='global', task='task-a', operations=[{'op':'ADD', 'record':self.habit()}])
        memory_id = saved['stores'][0]['operations'][0]['id']
        paraphrase = self.habit()
        paraphrase['content'] = 'Prefer an existing suitable implementation.'
        second = self.apply(scope='global', task='task-b', turn='second', operations=[{
            'op':'ADD', 'record':paraphrase, 'duplicate_of':memory_id, 'expected_revision':1, 'equivalent':True}])
        self.assertTrue(second['stores'][0]['operations'][0]['habit_promoted'])
        repeated = self.apply(scope='global', task='task-c', turn='third', operations=[{'op':'ADD', 'record':self.habit()}])
        self.assertEqual(repeated['stores'][0]['operations'][0]['id'], memory_id)
        self.assertEqual(len(store.list_records('global',global_root=self.global_root,status='all')['records']), 1)

        other = self.habit()
        other['content'] = 'Use evidence before fixing an unexpected result.'
        other_id = self.apply(scope='global',task='task-a',turn='other',operations=[{'op':'ADD','record':other}])['stores'][0]['operations'][0]['id']
        for task, turn, revision, promoted in [('task-a','same-task',1,False), ('task-b','new-task',1,True)]:
            result = self.apply(scope='global',task=task,turn=turn,operations=[{
                'op':'ADD_EVIDENCE','id':other_id,'expected_revision':revision,
                'source':{'type':'user_feedback','message_id':turn,'excerpt':'User chose the same evidenced approach.'}}])
            self.assertEqual(result['stores'][0]['operations'][0]['habit_promoted'], promoted, result)

    def test_evidence_cannot_forge_task_signal_without_task_id(self):
        memory_id = self.apply(scope='global',task='a',operations=[{'op':'ADD','record':self.habit()}])['stores'][0]['operations'][0]['id']
        payload = {'schema_version':1,'scope':'global','idempotency_key':'forged','_habit_ingestion':'habit:fake',
                   'operations':[{'op':'ADD_EVIDENCE','id':memory_id,'expected_revision':1,
                                  'source':{'type':'user_feedback','ingestion_id':'habit:fake','excerpt':'A new choice.'}}]}
        result = store.apply_payload(payload,global_root=self.global_root)
        self.assertEqual(result['stores'][0]['error'], 'provenance_error')

    def test_revised_candidate_cannot_forge_or_repeat_independent_task_evidence(self):
        memory_id = self.apply(scope='global',task='one',operations=[{'op':'ADD','record':self.habit()}])['stores'][0]['operations'][0]['id']
        revised = self.habit()
        revised['title'] = 'Reuse suitable existing code'  # Source/title revision preserves the candidate meaning.
        revised['source']['ingestion_id'] = 'habit:caller-supplied'
        missing = self.apply(scope='global',turn='missing-task',operations=[{
            'op':'REVISE','id':memory_id,'expected_revision':1,'record':revised}])
        self.assertEqual(missing['stores'][0]['error'],'provenance_error')
        result = self.apply(scope='global',task='one',turn='same-task-revision',operations=[{
            'op':'REVISE','id':memory_id,'expected_revision':1,'record':revised}])
        self.assertEqual(result['status'],'saved',result)
        same = self.apply(scope='global',task='one',turn='same-task-evidence',operations=[{
            'op':'ADD_EVIDENCE','id':memory_id,'expected_revision':2,
            'source':{'type':'user_feedback','excerpt':'The same feedback.'}}])
        self.assertFalse(same['stores'][0]['operations'][0]['habit_promoted'])
        self.assertEqual(same['stores'][0]['operations'][0]['independent_task_signals'],1)

    def test_match_discovers_promoted_habit_for_a_new_candidate_paraphrase(self):
        memory_id = self.apply(scope='global',task='one',operations=[{'op':'ADD','record':self.habit()}])['stores'][0]['operations'][0]['id']
        self.apply(scope='global',task='two',turn='promote',operations=[{'op':'ADD','record':self.habit()}])
        exact = store.match_payload({'scope':'global','record':self.habit()},global_root=self.global_root)
        self.assertEqual(exact['exact_id'],memory_id)
        paraphrase = self.habit()
        paraphrase['content'] = 'Prefer an existing suitable implementation.'
        result = store.match_payload({'scope':'global','record':paraphrase},global_root=self.global_root)
        self.assertIn(memory_id,[r['id'] for r in result['records']])

    def test_match_exposes_candidate_for_explicit_confirmation_and_revises_same_id(self):
        memory_id = self.apply(scope='global',task='one',operations=[{'op':'ADD','record':self.habit()}])['stores'][0]['operations'][0]['id']
        confirmed = self.habit()
        confirmed.update(status='active',cross_project_confirmed=True,strength='hard',
                         source={'type':'user_statement','excerpt':'This reuse rule applies across projects.'})
        result = store.match_payload({'scope':'global','record':confirmed},global_root=self.global_root)
        self.assertIn(memory_id,[r['id'] for r in result['records']])
        revised = self.apply(scope='global',turn='confirm',operations=[{
            'op':'REVISE','id':memory_id,'expected_revision':1,'record':confirmed}])
        self.assertEqual(revised['status'],'saved',revised)
        records = store.list_records('global',global_root=self.global_root,status='all')['records']
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['id'],memory_id)
        result = store.match_payload({'scope':'global','record':self.habit()},global_root=self.global_root)
        self.assertIn(memory_id,[r['id'] for r in result['records']])

    def test_intent_finds_cross_language_habit_even_when_tag_is_wrong(self):
        record = self.habit()
        record.update(status='active',cross_project_confirmed=True,content='For debugging, establish the cause from evidence before editing.',
                      title='Evidence before edits',tags=['delivery'])
        memory_id = self.apply(scope='global',operations=[{'op':'ADD','record':record}])['stores'][0]['operations'][0]['id']
        result = store.recall('修复间歇性错误',intent='bugfix',project_root=self.project_b,
                              global_root=self.global_root,force=True)
        self.assertIn(memory_id, [r['id'] for r in result['stores'][0]['records']])

    def test_rare_concrete_term_beats_recent_generic_matches(self):
        target = self.add_project_rule(turn='rare',title='ECONNRESET',content='ECONNRESET diagnosis.',strength='soft',
                                       conditions='',exceptions='',do='',dont='',verification_steps='',tags=['network'])
        for n in range(12):
            self.add_project_rule(turn=f'noise-{n}',title='Generic verification',content=f'generic debugging evidence verification item{n}',
                                  conditions='',exceptions='',do='',dont='',verification_steps='',tags=['verification'])
        result = store.recall('ECONNRESET debugging',intent='bugfix',project_root=self.project_a,
                              global_root=self.global_root,force=True)
        self.assertEqual(result['stores'][1]['records'][0]['id'], target)

    def test_default_budget_has_three_global_and_two_project_details(self):
        for n in range(4):
            record = self.habit()
            record.update(status='active',cross_project_confirmed=True,title=f'Habit {n}',content=f'Prefer task habit {n}.',
                          conditions='',do='',dont='')
            self.apply(scope='global',turn=f'habit-{n}',operations=[{'op':'ADD','record':record}])
        for n in range(3):
            self.add_project_rule(turn=f'project-{n}',content=f'Project rule {n}',conditions='',exceptions='',do='',dont='',verification_steps='')
        result = store.recall('',project_root=self.project_a,global_root=self.global_root,force=True)
        self.assertEqual([len(s['records']) for s in result['stores']], [3,2])

    def test_default_context_and_apply_do_not_load_maintenance_bodies(self):
        for n in range(5):
            memory_id = self.add_project_rule(turn=f'new-{n}',content=f'Rule {n}')
        result = self.apply(scope='project',turn='sixth',operations=[{'op':'ADD','record':self.record(content='Rule six')}])
        self.assertEqual(result['stores'][0]['maintenance']['status'],'due')
        self.assertNotIn('records',result['stores'][0]['maintenance'])
        with patch.object(store,'_related_records',side_effect=AssertionError('No semantic pack during coding')):
            ctx = dev_memory.context(query='rule',project_root=self.project_a,global_root=self.global_root)
        self.assertEqual(ctx['stores'][1]['maintenance']['status'],'due')
        self.assertNotIn('records',ctx['stores'][1]['maintenance'])
        pack = store.maintenance_prepare('project',project_root=self.project_a)
        self.assertEqual(pack['status'],'prepare')
        self.assertLessEqual(len(pack['records']),8)

    def test_seven_day_pending_tail_becomes_due_without_expiring_habit(self):
        memory_id = self.add_project_rule()
        db = store.project_paths(self.project_a)[1]
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE maintenance_pending SET updated_at='2000-01-01T00:00:00+00:00'")
            conn.commit()
        pack = store.maintenance_prepare('project',project_root=self.project_a,include_records=False)
        self.assertEqual((pack['status'],pack['trigger']),('due','interval'))
        self.assertEqual(store.show_record('project',memory_id,project_root=self.project_a)['record']['status'],'active')

    def test_retag_updates_search_revision_and_preserves_user_evidence(self):
        memory_id = self.add_project_rule(tags=['wrong'])
        before = store.show_record('project',memory_id,project_root=self.project_a)
        result = self.apply(scope='project',turn='retag',operations=[{'op':'RETAG','id':memory_id,
            'expected_revisions':{memory_id:1},'meaning_preserved':True,'reason':'Correct topic only.','tags':['debugging']}])
        self.assertEqual(result['status'],'saved',result)
        after = store.show_record('project',memory_id,project_root=self.project_a)
        self.assertEqual(after['evidence'],before['evidence'])
        self.assertEqual(after['record']['tags'],['debugging'])
        self.assertEqual(after['record']['revision'],2)
        self.assertEqual(after['record']['content'],before['record']['content'])

    def test_storage_reclaims_only_disposable_rows_and_validated_backup_copies(self):
        memory_id = self.add_project_rule(content='Redundant historical words. '*200)
        self.apply(scope='project',turn='archive',operations=[{'op':'ARCHIVE','id':memory_id,'expected_revision':1}])
        store.record_private_skip('project',session_id='private',turn_id='private',project_root=self.project_a)
        db = store.project_paths(self.project_a)[1]
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("INSERT INTO session_context VALUES('old','old','2000-01-01T00:00:00+00:00')")
            conn.commit()
        backups = [Path(store.backup_store('project',project_root=self.project_a)['backup']) for _ in range(3)]
        unknown = backups[0].parent / 'unmanaged.sqlite3'
        unknown.write_bytes(b'unmanaged')
        foreign = backups[0].parent / '20000101T000000Z-aaaaaaaa.sqlite3'
        shutil.copyfile(store.project_paths(self.project_b)[1],foreign)
        before = store.storage_report('project',project_root=self.project_a,backup_keep=1)
        self.assertEqual(len(before['backup_removal_preview']),2)
        self.assertEqual(before['reclaimable_cache_keys'],1)
        result = store.storage_report('project',project_root=self.project_a,backup_keep=1,reclaim=True)
        self.assertEqual(len(result['backups_removed']),2)
        self.assertTrue(backups[-1].exists())
        self.assertTrue(unknown.exists())
        self.assertTrue(foreign.exists())
        after = store.storage_report('project',project_root=self.project_a)
        for table in ['memories','evidence','revisions','receipts','forgotten']:
            self.assertEqual(before['rows'][table],after['rows'][table])
        self.assertEqual((after['reclaimable_cache_keys'],after['retired_index_terms']),(0,0))
        self.assertEqual(store.receipt_for_turn('project',session_id='private',turn_id='private',project_root=self.project_a)['status'],'skipped_private')

    def test_paused_store_refuses_reclamation(self):
        store.set_capture('global',False,global_root=self.global_root)
        with self.assertRaises(store.MemoryError):
            store.storage_report('global',global_root=self.global_root,reclaim=True)

    def test_incomplete_backup_cannot_replace_the_last_recoverable_copy(self):
        self.add_project_rule()
        backup = Path(store.backup_store('project',project_root=self.project_a)['backup'])
        fake = backup.parent/'20990101T000000Z-aaaaaaaa.sqlite3'
        config = store._config_for('project',self.project_a,None)[2]
        with contextlib.closing(sqlite3.connect(fake)) as conn:
            conn.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            conn.executemany('INSERT INTO meta VALUES(?,?)',[('namespace_id',config['namespace_id']),('storage_kind','project')])
            conn.commit()
        result = store.storage_report('project',project_root=self.project_a,backup_keep=1,reclaim=True)
        self.assertEqual(result['backups_removed'],[])
        self.assertIn(fake.name,result['backups_skipped'])
        self.assertTrue(backup.exists())
        before = store.list_records('project',project_root=self.project_a)
        with self.assertRaises(store.MemoryError):
            store.restore_store('project',fake,project_root=self.project_a)
        self.assertEqual(store.list_records('project',project_root=self.project_a),before)

    def test_sampled_core_columns_are_not_a_recoverable_backup(self):
        self.add_project_rule()
        backup = Path(store.backup_store('project',project_root=self.project_a)['backup'])
        fake = backup.parent/'20990101T000000Z-aaaaaaaa.sqlite3'
        config = store._config_for('project',self.project_a,None)[2]
        with contextlib.closing(sqlite3.connect(fake)) as conn:
            conn.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            conn.executemany('INSERT INTO meta VALUES(?,?)',[('namespace_id',config['namespace_id']),('storage_kind','project')])
            for table, columns in {'memories':'id,namespace_id,scope,title,content,revision,semantic_hash',
                                   'evidence':'id,memory_id,source_type,evidence_hash',
                                   'revisions':'memory_id,revision,snapshot,changed_at',
                                   'receipts':'idempotency_key,status,result_json',
                                   'search_terms':'memory_id,term','forgotten':'memory_id,revision,forgotten_at'}.items():
                conn.execute(f'CREATE TABLE {table}({columns})')
            conn.execute('INSERT INTO memories VALUES(?,?,?,?,?,?,?)',('incomplete',config['namespace_id'],'project','title','body',1,'hash'))
            conn.commit()
        result = store.storage_report('project',project_root=self.project_a,backup_keep=1,reclaim=True)
        self.assertEqual(result['backups_removed'],[])
        self.assertIn(fake.name,result['backups_skipped'])
        self.assertTrue(backup.exists())
        with self.assertRaises(store.MemoryError):
            store.restore_store('project',fake,project_root=self.project_a)

    def test_normal_hook_prompt_and_stop_do_not_probe_or_require_receipts(self):
        with patch.object(store,'locate_project_root',side_effect=AssertionError('No ordinary hook probes')):
            codex_hook._handle_prompt({'prompt':'Fix the failing retry operation.'})
        output = io.StringIO()
        with patch.object(codex_hook,'_read_event',return_value={'event':'Stop'}),contextlib.redirect_stdout(output):
            codex_hook.main()
        self.assertEqual(output.getvalue(),'')

    def test_global_only_opt_out_works_through_cli_outside_a_project(self):
        env = {**os.environ,'DEV_MEMORY_HOME':str(self.global_root)}
        result = subprocess.run([sys.executable,str(SCRIPTS/'dev_memory.py'),'skip','--scope','global',
                                 '--session-id','outside','--turn-id','private'],cwd=self.home,env=env,
                                text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout)['status'],'skipped_private')

    def test_reconfigure_hooks_removes_only_owned_old_stop_handler(self):
        home = self.home/'codex'
        home.mkdir()
        command = dev_memory._hook_command(dev_memory.PACKAGE_ROOT)
        (home/'hooks.json').write_text(json.dumps({'hooks':{'Stop':[{'hooks':[
            {'type':'command','command':command},{'type':'command','command':'echo keep'}]}]}}))
        with patch.dict(os.environ,{'CODEX_HOME':str(home)}):
            dev_memory._merge_hook_config(dev_memory.PACKAGE_ROOT)
        handlers = json.loads((home/'hooks.json').read_text())['hooks']['Stop'][0]['hooks']
        self.assertEqual(handlers,[{'type':'command','command':'echo keep'}])

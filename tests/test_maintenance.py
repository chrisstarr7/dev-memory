"""Bounded automatic maintenance; all data are synthetic and project-local."""
from __future__ import annotations
import json
import contextlib
import sqlite3
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals'))
from check_maintenance import observed_maintenance, observed_usage
from bench_compare import _summary
from test_dev_memory import MemoryTestCase, store


class MaintenanceTests(MemoryTestCase):
    def test_batch_snapshot_revisions_and_single_compact_form_are_resolved_by_program(self):
        first = self.add_project_rule(content='Require all stated conditions.')
        duplicate = self.add_project_rule(turn='duplicate',content='Every stated condition must hold.')
        long_id = self.add_project_rule(turn='long-other',conditions='Separate condition.',content='Separate unchanged restriction. '*60)
        response = self.apply(scope='project', turn='ergonomic-batch', operations=[
            {'op':'MERGE_DUPLICATES','id':first,'expected_revisions':{first:1,duplicate:1},'meaning_preserved':True,'reason':'Same complete rule.'},
            {'op':'COMPACT','id':long_id,'expected_revision':1,'content':'Separate unchanged restriction.','meaning_preserved':True,'reason':'Repeated prose only.'},
            {'op':'MAINTENANCE_REVIEW','expected_revisions':{first:1,duplicate:1,long_id:1},'reason':'Inspected these original snapshots and proposed changes.'}])
        self.assertEqual(response['status'], 'saved', response)
        review = response['stores'][0]['operations'][-1]
        self.assertEqual(review['revision_resolution'], 'within_batch')
        self.assertEqual(review['reviewed_revisions'], {first:2,duplicate:2,long_id:2})
        self.assertEqual(self.detail(duplicate)['record']['status'], 'superseded')
        self.assertEqual(self.detail(long_id)['record']['content'], 'Separate unchanged restriction.')
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'], 'idle')

    def test_batch_resolution_does_not_accept_external_staleness_or_conflicting_compact_forms(self):
        first = self.add_project_rule()
        self.apply(scope='project',turn='external-update',operations=[{'op':'ADD_EVIDENCE','id':first,
            'expected_revision':1,'source':self.source('Independent current confirmation.')}])
        response = self.apply(scope='project',turn='stale-snapshot',operations=[{'op':'MAINTENANCE_REVIEW',
            'expected_revisions':{first:1},'reason':'Old snapshot.'}])
        self.assertEqual(response['stores'][0]['error'], 'revision_conflict')
        self.assertEqual(response['stores'][0]['transaction'], 'rolled_back')
        for n, fields in enumerate([{'expected_revision':True}, {'expected_revision':2,'expected_revisions':{first:1}}]):
            response = self.apply(scope='project',turn=f'invalid-compact-{n}',operations=[{
                'op':'COMPACT','id':first,'content':'Short.','meaning_preserved':True,'reason':'Reviewed.',**fields}])
            self.assertEqual(response['stores'][0]['error'], 'validation_error')
        self.assertEqual(self.detail(first)['record']['revision'], 2)

    def test_due_cycle_drains_small_tail_and_suppresses_second_pack_in_same_turn(self):
        ids = [self.add_project_rule(turn=f'queue-{n}', content=f'Synthetic rule {n}.') for n in range(5)]
        reviewed = self.apply(scope='project', turn='cleanup', operations=[{
            'op':'MAINTENANCE_REVIEW', 'expected_revisions':{i:1 for i in ids[:3]}, 'reason':'Read these three rules.'}])
        self.assertEqual(reviewed['stores'][0]['maintenance']['status'], 'pending_next_turn')
        same_turn = self.apply(scope='project', turn='cleanup', idem='later-write-in-same-turn', operations=[{
            'op':'NOOP', 'reason':'Checked remaining task; no increment.'}])
        self.assertEqual(same_turn['stores'][0]['maintenance']['status'], 'pending_next_turn')
        pack = store.maintenance_prepare('project', project_root=self.project_a, session_id='session-test', turn_id='cleanup')
        self.assertEqual(pack['status'], 'pending_next_turn')
        next_turn = self.apply(scope='project', turn='next-interaction', operations=[{'op':'NOOP','reason':'Checked.'}])
        pack = next_turn['stores'][0]['maintenance']
        self.assertEqual(pack['status'], 'prepare')
        self.assertEqual(pack['trigger'], 'drain')
        self.assertEqual(pack['pending_count'], 2)
        self.apply(scope='project', turn='next-interaction', idem='finish-tail', operations=[{
            'op':'MAINTENANCE_REVIEW','expected_revisions':{i:1 for i in ids[3:]},'reason':'Read the remaining two rules.'}])
        idle = self.apply(scope='project', turn='idle', operations=[{'op':'NOOP','reason':'Checked.'}])
        self.assertEqual(idle['stores'][0]['maintenance'], {'status':'not_due'})
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a)['status'], 'idle')

    def test_turn_opt_out_blocks_maintenance_prepare_without_consuming_queue(self):
        for n in range(5):
            self.add_project_rule(turn=f'pending-{n}', content=f'Rule {n}.')
        store.record_private_skip('project', session_id='private-session', turn_id='private-turn', project_root=self.project_a)
        skipped = store.maintenance_prepare('project', project_root=self.project_a, session_id='private-session', turn_id='private-turn')
        self.assertEqual(skipped['status'], 'skipped_private')
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a)['pending_count'], 5)

    def test_upgrade_restarts_review_for_an_existing_below_threshold_tail(self):
        memory_id = self.add_project_rule()
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("DELETE FROM maintenance_pending")
            conn.execute("UPDATE meta SET value='2' WHERE key='maintenance_review_version'")
            conn.commit()
        response = self.apply(scope='project', turn='upgraded-tail', operations=[{'op':'NOOP','reason':'Checked.'}])
        self.assertEqual(response['stores'][0]['maintenance']['trigger'], 'drain')
        self.assertEqual(response['stores'][0]['maintenance']['seed_ids'], [memory_id])

    def detail(self, memory_id):
        return store.show_record('project', memory_id, project_root=self.project_a)

    def maintain(self, action, ids, *, turn='maintain', **fields):
        revisions = {i: self.detail(i)['record']['revision'] for i in ids}
        return self.apply(scope='project', turn=turn, operations=[{
            'op': action, 'scope': 'project', 'id': ids[0], 'expected_revisions': revisions,
            'reason': 'Synthetic semantic review; preserve every eligibility condition.',
            'meaning_preserved': True, **fields}])

    def add_summary(self, source, turn='summary'):
        record = self.record(kind='summary', title='Derived checklist', content='Preserve all refund restrictions.',
                             derived_from=[source], expected_source_revisions={source: self.detail(source)['record']['revision']})
        result = self.apply(scope='project', turn=turn, operations=[{'op':'ADD','record':record}])
        self.assertEqual(result['status'], 'saved', result)
        return result['stores'][0]['operations'][0]['id']

    def test_changed_title_and_whitespace_do_not_create_new_body(self):
        first = self.add_project_rule(content='Delivered unopened order')
        second = self.add_project_rule(turn='same', title='A completely different heading', content='Delivered  unopened\norder')
        self.assertEqual(first, second)
        self.assertEqual(len(store.list_records('project', project_root=self.project_a)['records']), 1)
        self.assertEqual(self.detail(first)['record']['content'], 'Delivered unopened order')
        self.assertEqual(len(self.detail(first)['evidence']), 2)

    def test_case_sensitive_business_values_do_not_merge(self):
        first = self.add_project_rule(content='Require status Paid')
        second = self.add_project_rule(turn='different-case', content='Require status paid')
        self.assertNotEqual(first, second)

    def test_match_returns_related_records_without_writes_or_project_leak(self):
        first = self.add_project_rule()
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            before = conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        response = store.match_payload({'scope':'project','record':self.record(content='退款需要全部正向条件')}, project_root=self.project_a)
        self.assertIn(first, [r['id'] for r in response['records']])
        other = store.match_payload({'scope':'project','record':self.record()}, project_root=self.project_b)
        self.assertEqual(other['records'], [])
        with contextlib.closing(sqlite3.connect(db)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], before)

    def test_semantic_duplicate_reuses_body_and_only_independent_source(self):
        first = self.add_project_rule()
        record = self.record(title='换一个标题', content='退款需要满足所有已列出的条件')
        source = {'type':'user_feedback','message_id':'real-message-2','excerpt':'换句话说，同样的条件。'}
        record['source'] = source
        result = self.apply(scope='project', turn='paraphrase', operations=[{
            'op':'ADD','record':record,'duplicate_of':first,'expected_revision':1,'equivalent':True}])
        self.assertEqual(result['status'], 'saved', result)
        op = result['stores'][0]['operations'][0]
        self.assertFalse(op['body_written'])
        self.assertEqual(len(self.detail(first)['evidence']), 2)
        result = self.apply(scope='project', turn='replay-new-key', operations=[{
            'op':'ADD','record':record,'duplicate_of':first,'expected_revision':2,'equivalent':True}])
        self.assertEqual(result['stores'][0]['operations'][0]['status'], 'duplicate_evidence')
        self.assertEqual(len(self.detail(first)['evidence']), 2)
        self.assertEqual(len(store.list_records('project', project_root=self.project_a)['records']), 1)

    def test_semantic_reuse_rejects_changed_conditions_or_stale_revision(self):
        first = self.add_project_rule()
        for field, value in [('conditions','30 days'), ('exceptions','No exceptions'), ('dont','Allow gifts'), ('claim_type','observed')]:
            with self.subTest(field=field):
                result = self.apply(scope='project', turn=field, operations=[{'op':'ADD','record':self.record(**{field:value}),
                    'duplicate_of':first,'expected_revision':1,'equivalent':True}])
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['stores'][0]['error'], 'duplicate_conflict')
        result = self.apply(scope='project', turn='stale', operations=[{'op':'ADD','record':self.record(),
            'duplicate_of':first,'expected_revision':99,'equivalent':True}])
        self.assertEqual(result['stores'][0]['error'], 'revision_conflict')

    def test_observed_version_boundaries_do_not_auto_merge(self):
        first = self.add_project_rule(claim_type='observed', commit_id='aaa')
        other = self.add_project_rule(turn='v2', claim_type='observed', commit_id='bbb')
        self.assertNotEqual(first, other)

    def test_threshold_and_long_record_trigger_without_extra_prepare_call(self):
        for n in range(5):
            result = self.apply(scope='project', turn=f'new-{n}', operations=[{'op':'ADD','record':self.record(content=f'退款要求编号 {n}。')}])
            state = result['stores'][0]['maintenance']
            self.assertEqual(state['status'], 'prepare' if n == 4 else 'waiting')
        self.assertLessEqual(len(state['records']),8)
        self.assertLessEqual(sum(len(json.dumps(r,ensure_ascii=False)) for r in state['records']),12000)
        result = self.apply(scope='project', project=self.project_b, turn='long', operations=[{'op':'ADD','record':self.record(content='This is a long explanation. '*70)}])
        self.assertEqual(result['stores'][0]['maintenance']['status'],'prepare')

    def test_related_search_keeps_rare_topic_terms_from_long_records(self):
        rare_id = self.add_project_rule(turn='rare', content='zebra_topic_marker')
        common_terms = ' '.join(f'alpha{i:03d}' for i in range(100))
        for n in range(8):
            self.add_project_rule(turn=f'common-{n}', content=f'{common_terms} noise{n:03d}')
        query = {**self.record(content=f'{common_terms} zebra_topic_marker'),
                 'scope':'project', 'status':'active', 'task_id':None}
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(store._connect(db, readonly=True)) as conn:
            indexed = {row[0] for row in conn.execute('SELECT term FROM search_terms WHERE memory_id=?', (rare_id,))}
            query_terms = store._token_terms(store._record_search_text(query))
            self.assertIn('zebra', indexed)
            self.assertIn('zebra', query_terms)
            related = store._related_records(conn, query)
        self.assertIn(rare_id, [record['id'] for record in related],
                      [(record['id'], record['content']) for record in related])

    def test_confirmed_correction_replaces_active_body_and_archive_leaves_recall(self):
        memory_id = self.add_project_rule(content='Synthetic rule before correction.')
        revised = self.record(content='Synthetic corrected rule with the confirmed new condition.')
        revised['source'] = self.source('The prior condition was incorrect; use the new confirmed condition.', 'user_feedback')
        result = self.apply(scope='project', turn='confirmed-correction', operations=[{
            'op':'REVISE', 'id':memory_id, 'expected_revision':1, 'record':revised,
        }])
        self.assertEqual(result['status'], 'saved', result)
        current = self.detail(memory_id)
        self.assertEqual(current['record']['status'], 'active')
        self.assertEqual(current['record']['content'], revised['content'])
        self.assertEqual(json.loads(current['revisions'][0]['snapshot'])['content'], 'Synthetic rule before correction.')
        archived = self.apply(scope='project', turn='retire-obsolete', operations=[{
            'op':'ARCHIVE', 'id':memory_id, 'expected_revision':2, 'reason':'Explicitly expired in the synthetic test fixture.',
        }])
        self.assertEqual(archived['status'], 'saved', archived)
        self.assertEqual(self.detail(memory_id)['record']['status'], 'archived')
        self.assertEqual(store.list_records('project', project_root=self.project_a)['records'], [])

    def test_protocol_upgrade_requeues_existing_active_records_for_bounded_review(self):
        for n in range(5):
            self.add_project_rule(turn=f'pre-upgrade-{n}', content=f'Synthetic existing rule {n}.')
        _, db = store.project_paths(self.project_a)
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute("DELETE FROM maintenance_pending")
            conn.execute("UPDATE meta SET value='1' WHERE key='maintenance_review_version'")
            conn.commit()
        result = self.apply(scope='project', turn='first-post-upgrade-noop', operations=[{
            'op':'NOOP', 'reason':'Checked; no new information.'
        }])
        self.assertEqual(result['status'], 'checked_noop')
        pack = result['stores'][0]['maintenance']
        self.assertEqual(pack['status'], 'prepare')
        self.assertEqual(pack['pending_count'], 5)
        self.assertLessEqual(len(pack['records']), 8)

    def test_noop_never_returns_history_pack_or_rewrites_body(self):
        self.add_project_rule()
        result = self.apply(scope='project', turn='noop', operations=[{'op':'NOOP','reason':'Checked; no increment.'}])
        self.assertEqual(result['stores'][0]['maintenance'], {'status':'not_due'})
        self.assertEqual(result['stores'][0]['data_revision'],1)

    def test_maintenance_review_clears_only_expected_revisions(self):
        first = self.add_project_rule()
        result = self.maintain('MAINTENANCE_REVIEW',[first])
        self.assertEqual(result['status'],'checked_noop',result)
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'],'idle')
        self.apply(scope='project',turn='new-evidence',operations=[{'op':'ADD_EVIDENCE','id':first,'expected_revision':1,'source':self.source('An independent user confirmation.')}])
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'],'prepare')
        result = self.apply(scope='project',turn='stale-review',operations=[{'op':'MAINTENANCE_REVIEW','expected_revisions':{first:1},'reason':'old review'}])
        self.assertEqual(result['stores'][0]['error'],'revision_conflict')

    def test_compact_preserves_fields_evidence_and_invalidates_summary(self):
        first = self.add_project_rule(content='All refund conditions must hold. '*70)
        summary = self.add_summary(first)
        before = self.detail(first)
        result = self.maintain('COMPACT',[first],content='All refund conditions must hold.')
        self.assertEqual(result['status'],'saved',result)
        after = self.detail(first)
        for field in ('conditions','exceptions','dont','do','verification_steps','claim_type','strength','source_refs'):
            self.assertEqual(after['record'][field],before['record'][field])
        self.assertEqual(after['evidence'],before['evidence'])
        self.assertEqual(len(after['revisions']),1)
        self.assertEqual(self.detail(summary)['record']['status'],'stale')
        self.assertEqual(result['stores'][0]['maintenance'],{'status':'not_due'})
        self.assertNotIn(first,store.maintenance_prepare('project',project_root=self.project_a,force=True).get('seed_ids',[]))

    def test_compact_requires_review_and_rejects_credentials_or_larger_text(self):
        first = self.add_project_rule()
        for content,meaning in [('x',False),('x'*1000,True)]:
            with self.subTest(content=content):
                result = self.maintain('COMPACT',[first],content=content,meaning_preserved=meaning,turn=f'bad-{meaning}-{len(content)}')
                self.assertEqual(result['status'],'failed')
        with self.assertRaises(store.MemoryError) as error:
            self.maintain('COMPACT',[first],content='api_key=ABCDEFGHIJKLMNOPQRSTUV',turn='secret')
        self.assertEqual(error.exception.code,'sensitive_data_rejected')
        self.assertEqual(self.detail(first)['record']['revision'],1)

    def test_merge_keeps_one_active_rule_and_original_source_provenance(self):
        first = self.add_project_rule(content='All stated refund requirements are mandatory.')
        second = self.add_project_rule(turn='paraphrase',content='Every listed refund condition must hold.')
        summary = self.add_summary(second)
        before = [self.detail(i)['evidence'] for i in (first,second)]
        result = self.maintain('MERGE_DUPLICATES',[first,second])
        self.assertEqual(result['status'],'saved',result)
        self.assertEqual(self.detail(first)['record']['status'],'active')
        self.assertEqual(self.detail(second)['record']['status'],'superseded')
        self.assertEqual(self.detail(first)['merged_source_ids'],[second])
        self.assertEqual(self.detail(summary)['record']['status'],'stale')
        self.assertEqual([self.detail(i)['evidence'] for i in (first,second)],before)
        self.assertEqual(result['stores'][0]['maintenance'],{'status':'not_due'})

    def test_merge_cannot_weaken_conditions_or_cross_project_or_task(self):
        first = self.add_project_rule()
        second = self.add_project_rule(turn='other',conditions='30 days',content='Same headline but different boundary.')
        result = self.maintain('MERGE_DUPLICATES',[first,second])
        self.assertEqual(result['stores'][0]['error'],'duplicate_conflict')
        foreign = self.add_project_rule(project=self.project_b,turn='foreign')
        result = self.apply(scope='project',turn='cross-project',operations=[{'op':'MERGE_DUPLICATES','id':first,'expected_revisions':{first:1,foreign:1},'meaning_preserved':True,'reason':'same'}])
        self.assertEqual(result['stores'][0]['error'],'scope_error')

    def test_merge_forget_preview_includes_alias_sources_and_derived_history(self):
        first = self.add_project_rule(content='Require all conditions.')
        second = self.add_project_rule(turn='second',content='All conditions are required.')
        summary = self.add_summary(second)
        backup = store.backup_store('project',project_root=self.project_a)['backup']
        self.assertEqual(self.maintain('MERGE_DUPLICATES',[first,second])['status'],'saved')
        preview = store.forget_preview('project',second,project_root=self.project_a)
        self.assertEqual({r['id'] for r in preview['records']},{first,second,summary})
        store.forget_apply('project',second,preview['confirmation_token'],project_root=self.project_a)
        store.restore_store('project',Path(backup),project_root=self.project_a)
        self.assertEqual(store.list_records('project',project_root=self.project_a,status='all')['records'],[])

    def test_old_backup_without_maintenance_tables_restores_and_requeues(self):
        first = self.add_project_rule()
        backup = store.backup_store('project',project_root=self.project_a)['backup']
        with contextlib.closing(sqlite3.connect(backup)) as conn:
            conn.execute('DROP TABLE maintenance_pending'); conn.execute('DROP TABLE merged_aliases')
            conn.execute("DELETE FROM meta WHERE key='maintenance_seeded'")
            conn.commit()
        result = store.restore_store('project',Path(backup),project_root=self.project_a)
        self.assertEqual(result['status'],'restored')
        self.assertIn(first,store.maintenance_prepare('project',project_root=self.project_a,force=True)['seed_ids'])

    def test_late_source_revision_marks_merged_canonical_conflicted(self):
        first = self.add_project_rule(content='Require all conditions.')
        second = self.add_project_rule(turn='second',content='All conditions are required.')
        self.maintain('MERGE_DUPLICATES',[first,second])
        self.apply(scope='project',turn='revise-source',operations=[{'op':'REVISE','id':second,'expected_revision':2,'record':self.record(content='Different new rule.')}])
        self.assertEqual(self.detail(first)['record']['status'],'conflicted')

    def test_private_turn_cannot_run_maintenance(self):
        first = self.add_project_rule()
        store.record_private_skip('project',session_id='session-test',turn_id='private',project_root=self.project_a)
        result = self.maintain('COMPACT',[first],content='Short.',turn='private')
        self.assertEqual(result['status'],'skipped_private')
        self.assertEqual(self.detail(first)['record']['revision'],1)

    def test_pause_readonly_and_disable_maintenance_respected(self):
        first = self.add_project_rule()
        config_path = self.project_a/'.dev-memory/config.json'
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config['maintenance_enabled']=False; config_path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'],'disabled')
        self.assertEqual(self.maintain('COMPACT',[first],content='Short.')['status'],'failed')
        config.update(capture_enabled=False,maintenance_enabled=True);config_path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'],'skipped_private')
        self.assertEqual(self.maintain('COMPACT',[first],content='Short.',turn='paused')['status'],'skipped_private')

    def test_maintenance_failure_cannot_relabel_committed_write_failed(self):
        with patch.object(store,'maintenance_prepare',side_effect=store.MemoryError('storage_unavailable','synthetic')):
            result = self.apply(scope='project',operations=[{'op':'ADD','record':self.record()}])
        self.assertEqual(result['status'],'saved')
        self.assertEqual(result['stores'][0]['maintenance']['status'],'deferred')
        self.assertEqual(len(store.list_records('project',project_root=self.project_a)['records']),1)

    def test_oversized_context_never_silently_truncates_rules(self):
        first = self.add_project_rule(content='Long actual conditions. '*1000)
        plan = store.maintenance_prepare('project',project_root=self.project_a,force=True)
        self.assertTrue(plan['context_incomplete'])
        self.assertIn(first,plan['remaining_ids'])
        self.assertNotIn(first,[r['id'] for r in plan['records']])

    def test_one_batch_review_accepts_post_merge_superseded_revisions(self):
        first = self.add_project_rule(content='Require all conditions.')
        second = self.add_project_rule(turn='second',content='All conditions are required.')
        result = self.apply(scope='project',turn='combined',operations=[
            {'op':'MERGE_DUPLICATES','id':first,'expected_revisions':{first:1,second:1},'meaning_preserved':True,'reason':'Equivalent conditions.'},
            {'op':'MAINTENANCE_REVIEW','expected_revisions':{first:2,second:2},'reason':'Reviewed both sources.'}])
        self.assertEqual(result['status'],'saved',result)
        self.assertEqual(store.maintenance_prepare('project',project_root=self.project_a,force=True)['status'],'idle')

    def test_rephrased_excerpt_from_same_source_is_not_additional_evidence(self):
        record = self.record(source={'type':'user_feedback','message_id':'same-message','excerpt':'Original wording.'})
        first = self.add_project_rule(**record)
        self.apply(scope='project',turn='again',operations=[{'op':'ADD_EVIDENCE','id':first,'expected_revision':1,
            'source':{'type':'user_feedback','message_id':'same-message','excerpt':'Rephrased extract of that same message.'}}])
        self.assertEqual(len(self.detail(first)['evidence']),1)

    def test_merge_alias_chain_is_forgotten_as_a_connected_group(self):
        first = self.add_project_rule(content='Require all conditions.')
        second = self.add_project_rule(turn='second',content='All conditions are required.')
        third = self.add_project_rule(turn='third',content='Every stated condition is mandatory.')
        self.maintain('MERGE_DUPLICATES',[first,second])
        self.maintain('MERGE_DUPLICATES',[third,first],turn='merge-again')
        preview = store.forget_preview('project',second,project_root=self.project_a)
        self.assertEqual({r['id'] for r in preview['records']},{first,second,third})
        self.assertEqual(set(self.detail(third)['merged_source_ids']),{first,second})

    def test_global_maintenance_does_not_need_or_open_a_project(self):
        record = self.record(scope='global',kind='preference',title='Concise replies',content='Keep replies concise. '*100)
        result = self.apply(scope='global',turn='global-long',operations=[{'op':'ADD','scope':'global','record':record}])
        pack = result['stores'][0]['maintenance']
        self.assertEqual(pack['status'],'prepare')
        self.assertTrue(all(r['scope']=='global' and r['task_id'] is None for r in pack['records']))
        memory_id = pack['records'][0]['id']
        result = self.apply(scope='global',turn='global-compact',operations=[{'op':'COMPACT','scope':'global','id':memory_id,
            'expected_revisions':{memory_id:1},'content':'Keep replies concise.','meaning_preserved':True,'reason':'Repeated sentence only.'}])
        self.assertEqual(result['status'],'saved',result)
        self.assertEqual(store.list_records('project',project_root=self.project_a)['records'],[])

    def test_project_rule_is_deduplicated_across_tasks_but_task_constraints_are_separate(self):
        first=self.apply(scope='project',task='old-task',operations=[{'op':'ADD','record':self.record()}])['stores'][0]['operations'][0]['id']
        result=self.apply(scope='project',task='new-task',turn='new-task',operations=[{'op':'ADD','record':self.record(title='Different title')}])
        self.assertEqual(result['stores'][0]['operations'][0]['id'],first)
        match=store.match_payload({'scope':'project','task_id':'third-task','record':self.record()},project_root=self.project_a)
        self.assertIn(first,[r['id'] for r in match['records']])
        ids=[]
        for task in ('task-one','task-two'):
            result=self.apply(scope='task',task=task,turn=task,operations=[{'op':'ADD','record':self.record()}])
            ids.append(result['stores'][0]['operations'][0]['id'])
        self.assertNotEqual(*ids)

    def test_reactivated_alias_cannot_create_a_merge_cycle(self):
        first=self.add_project_rule(content='Require all conditions.')
        second=self.add_project_rule(turn='second',content='All conditions are required.')
        self.maintain('MERGE_DUPLICATES',[first,second])
        self.apply(scope='project',turn='revive-second',operations=[{'op':'REVISE','id':second,'expected_revision':2,'record':self.record(content='All conditions are required.')}])
        self.apply(scope='project',turn='resolve-first',operations=[{'op':'REVISE','id':first,'expected_revision':3,'record':self.record(content='Require all conditions.')}])
        result=self.maintain('MERGE_DUPLICATES',[second,first],turn='reverse-merge')
        self.assertEqual(result['stores'][0]['error'],'duplicate_conflict')
        self.assertEqual(self.detail(second)['merged_source_ids'],[])

    def test_global_compaction_cannot_introduce_project_paths(self):
        record=self.record(scope='global',kind='preference',content='Keep replies concise. '*100)
        result=self.apply(scope='global',turn='global-source',operations=[{'op':'ADD','scope':'global','record':record}])
        memory_id=result['stores'][0]['operations'][0]['id']
        result=self.apply(scope='global',turn='global-project-leak',operations=[{'op':'COMPACT','scope':'global','id':memory_id,
            'expected_revisions':{memory_id:1},'content':'Read /Users/example/customer-project/policy.py',
            'meaning_preserved':True,'reason':'Shorter summary.'}])
        self.assertEqual(result['stores'][0]['error'],'scope_error')
        self.assertEqual(store.show_record('global',memory_id,global_root=self.global_root)['record']['revision'],1)

    def test_task_pack_exposes_record_scope_for_a_valid_review(self):
        result=self.apply(scope='task',task='active-task',operations=[{'op':'CHECKPOINT','record':self.record(content='Actual progress. '*100)}])
        pack=result['stores'][0]['maintenance']
        self.assertEqual(pack['record_scope'],'task')
        self.assertEqual(pack['task_id'],'active-task')
        result=self.apply(scope='project',task=pack['task_id'],turn='review-task',operations=[{'op':'MAINTENANCE_REVIEW',
            'scope':pack['record_scope'],'expected_revisions':{r['id']:r['revision'] for r in pack['records']},'reason':'Read this task checkpoint.'}])
        self.assertEqual(result['status'],'checked_noop',result)


class MaintenanceObserverTests(unittest.TestCase):
    def test_usage_observation_requires_successful_structured_receipt(self):
        valid = {'used_id':'rule-one','usage':'ai_reported_not_behavior_verified'}
        self.assertEqual(observed_usage([self.event({'stores':[{'status':'checked_noop','operations':[valid]}]})]), ['rule-one'])
        self.assertEqual(observed_usage([self.event({'stores':[{'status':'failed','operations':[valid]}]}),
                                        self.event({'text':'USE rule-one'})]), [])

    def event(self, result, command='python apply'):
        return {'type':'item.completed','item':{'type':'command_execution','command':command,'aggregated_output':json.dumps(result)}}

    def test_keywords_and_doctor_status_are_not_operation_proof(self):
        events=[self.event({'stores':{'global':{'status':'available'}}}),
                self.event({'text':'COMPACT MERGE_DUPLICATES MAINTENANCE_REVIEW'}, 'rg COMPACT source.py'),
                self.event({'stores':[{'status':'failed','operations':[{'compacted':True}]}]})]
        self.assertFalse(any(observed_maintenance(events).values()))

    def test_successful_receipts_are_operation_proof(self):
        result=observed_maintenance([self.event({'stores':[{'status':'saved','operations':[
            {'compacted':True},{'merged_ids':['old-id']},{'reviewed_ids':['current-id']}]}]})])
        self.assertTrue(all(result.values()))

    def test_benchmark_keeps_host_failures_separate_from_completed_timing(self):
        rows=[{'exit_code':0,'duration_seconds':80,'first_effective_action_seconds':20,'tool_event_count':10,
               'token_usage':{'input_tokens':100,'output_tokens':10},'automated_criterion_match':True},
              {'exit_code':1,'duration_seconds':15,'first_effective_action_seconds':None,'tool_event_count':0,
               'token_usage':None,'automated_criterion_match':None}]
        result=_summary(rows)
        self.assertEqual(result['n'],2)
        self.assertEqual(result['host_failed_or_timed_out'],1)
        self.assertEqual(result['completed_metrics']['duration_seconds']['median'],80)
        self.assertEqual(result['criteria_unknown'],1)

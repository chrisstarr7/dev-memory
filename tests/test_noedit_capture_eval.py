"""Synthetic positive and negative controls; no model or private memory access."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evals'))
import check_noedit_capture as evaluation
import dev_memory_store as store


class NoEditCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='noedit-capture-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        baseline = evaluation.create_fixture(self.root, ROOT / 'skills/dev-memory')
        self.project = Path(baseline['project_root'])
        self.global_root = Path(baseline['global_root'])

    def apply(self, scope='project', turn='capture', **changes):
        record = {'kind': 'convention', 'claim_type': 'desired', 'status': 'active',
                  'strength': 'hard', 'title': 'DTO/VO Swagger annotations',
                  'content': 'DTO and VO classes and fields must use Swagger annotations in the existing style.',
                  'source': {'type': 'user_statement', 'excerpt': evaluation.PROMPT}}
        record.update(changes)
        return store.apply_payload(
            {'schema_version': 1, 'scope': scope, 'session_id': 'offline-test',
             'turn_id': turn, 'idempotency_key': turn, 'maintenance': 'defer',
             'operations': [{'op': 'ADD', 'scope': scope, 'record': record}]},
            project_root=self.project, global_root=self.global_root)

    def test_user_rule_with_unchanged_java_passes_and_inspection_is_readonly(self):
        self.assertFalse(evaluation.inspect_fixture(self.root)['passed'])
        result = self.apply()
        self.assertEqual(result['status'], 'saved', result)
        db = self.project / '.dev-memory/memory.sqlite3'
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        checked = evaluation.snapshot(self.root, output=self.root / 'outcome.json')
        self.assertTrue(checked['passed'], checked)
        self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
        self.assertEqual(json.loads((self.root / 'outcome.json').read_text(encoding='utf-8')), checked)

    def test_observed_code_fact_cannot_satisfy_user_convention(self):
        result = self.apply(claim_type='observed', source={
            'type': 'code_observation', 'excerpt': 'Both existing classes use Swagger annotations.'})
        self.assertEqual(result['status'], 'saved', result)
        self.assertFalse(evaluation.inspect_fixture(self.root)['checks']['user_sourced_active_project_convention'])

    def test_cli_failure_is_not_reported_as_a_successful_exit(self):
        with patch.object(sys, 'argv', ['check_noedit_capture', str(self.root)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(evaluation.main(), 1)
            self.apply()
            self.assertEqual(evaluation.main(), 0)

    def test_candidate_and_global_only_are_not_project_success(self):
        self.assertEqual(self.apply(status='candidate')['status'], 'saved')
        self.assertFalse(evaluation.inspect_fixture(self.root)['passed'])
        result = self.apply(scope='global', turn='global', cross_project_confirmed=True,
                            source={'type': 'user_statement', 'excerpt': 'Apply this convention to all projects.'})
        self.assertEqual(result['status'], 'saved', result)
        checked = evaluation.inspect_fixture(self.root)
        self.assertFalse(checked['checks']['user_sourced_active_project_convention'])
        self.assertFalse(checked['checks']['no_global_records'])

    def test_java_changes_and_task_checkpoints_fail_separately(self):
        self.apply()
        java = self.project / 'AssetItemVO.java'
        java.write_text(java.read_text(encoding='utf-8') + '// unnecessary edit\n', encoding='utf-8')
        self.assertFalse(evaluation.inspect_fixture(self.root)['checks']['java_unchanged'])
        # Seed a prohibited row directly: normal capture correctly rejects task checkpoints.
        db = self.project / '.dev-memory/memory.sqlite3'
        with contextlib.closing(store._connect(db)) as conn:
            conn.execute("UPDATE memories SET kind='checkpoint', scope='task'")
            conn.commit()
        self.assertFalse(evaluation.inspect_fixture(self.root)['checks']['no_checkpoints'])

    def test_pause_and_turn_optout_block_capture(self):
        store.set_capture('project', False, project_root=self.project)
        self.assertEqual(self.apply(turn='paused')['status'], 'skipped_private')
        store.set_capture('project', True, project_root=self.project)
        store.record_private_skip('project', session_id='offline-test', turn_id='private',
                                  project_root=self.project, global_root=self.global_root)
        self.assertEqual(self.apply(turn='private')['status'], 'skipped_private')
        checked = evaluation.inspect_fixture(self.root)
        self.assertEqual(checked['project_records'], [])
        self.assertFalse(checked['passed'])

    def test_later_recall_must_include_persisted_rule_id(self):
        self.apply()
        recalled = store.recall('DTO VO Swagger annotations existing style',
                               project_root=self.project, global_root=self.global_root, force=True)
        ids = [record['id'] for block in recalled['stores'] for record in block['records']]
        self.assertTrue(evaluation.snapshot(self.root, recalled_ids=ids)['passed'])
        self.assertFalse(evaluation.snapshot(self.root, recalled_ids=['unrelated'])['passed'])
        self.assertFalse(evaluation.snapshot(self.root, recalled_ids=[])['passed'])


if __name__ == '__main__':
    unittest.main()

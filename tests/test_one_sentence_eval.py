"""The real-host evaluator must reject false correction receipts and lost boundaries."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'evals'))
from check_one_sentence import correction_checks


class OneSentenceEvaluationTests(unittest.TestCase):
    def snapshots(self):
        record = dict(id='target', kind='convention', claim_type='desired', status='candidate', strength='soft',
                      revision=1, conditions='All tasks', exceptions='May add when reuse cannot meet the need.',
                      dont='Never sacrifice correctness.', verification_steps='Check correctness.',
                      code_refs=[], source_refs=[])
        before = {'global':[], 'project':[{'record':record,
                  'evidence':[{'excerpt':'Original requirement','source_type':'user_statement'}], 'revisions':[]}]}
        after = copy.deepcopy(before)
        current = after['project'][0]
        current['record'].update(revision=2, conditions='Complex tasks')
        current['evidence'].append({'excerpt':'Only complex tasks','source_type':'user_feedback'})
        current['revisions'].append({'revision':1})
        return before, after

    def test_receipt_cannot_hide_lost_exceptions_activation_or_duplicate(self):
        before, after = self.snapshots()
        self.assertTrue(all(correction_checks(before, after, 'synonym').values()))
        for field, value in (('exceptions',''), ('status','active'), ('revision',1)):
            bad = copy.deepcopy(after)
            bad['project'][0]['record'][field] = value
            self.assertFalse(all(correction_checks(before, bad, 'synonym').values()), field)
        duplicate = copy.deepcopy(after)
        duplicate['project'].append(copy.deepcopy(duplicate['project'][0]))
        self.assertFalse(correction_checks(before, duplicate, 'synonym')['no_duplicate_records'])

    def test_ai_restatement_is_not_new_user_evidence(self):
        before, after = self.snapshots()
        after['project'][0]['evidence'][-1]['source_type'] = 'model_inference'
        self.assertFalse(correction_checks(before, after, 'synonym')['new_user_evidence'])

    def test_ambiguous_and_temporary_cases_reject_any_semantic_write(self):
        before, after = self.snapshots()
        for label in ('ambiguous','temporary'):
            self.assertTrue(all(correction_checks(before, before, label).values()))
            self.assertFalse(all(correction_checks(before, after, label).values()))

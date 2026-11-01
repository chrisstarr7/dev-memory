"""Independent artifact and delivery checks; no credentials or model calls."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'evals'))
import check_cross_session as evaluation


class CrossSessionEvaluationTests(unittest.TestCase):
    def test_saved_rule_must_change_the_actual_workbook(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            self.assertFalse(evaluation.workbook_matches(project))
            (project/'artifacts').mkdir()
            target = project/'artifacts/intake-template.xlsx'
            def write(sheet='交付登记', cells=''):
                with zipfile.ZipFile(target, 'w') as archive:
                    for name in ('[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels'):
                        archive.writestr(name, '<fixture/>')
                    archive.writestr('xl/workbook.xml', f'<workbook><sheets><sheet name="{sheet}"/></sheets></workbook>')
                    archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet><sheetData>{cells}</sheetData></worksheet>')
            write()
            self.assertTrue(evaluation.workbook_matches(project))
            write(sheet='Sheet1')
            self.assertFalse(evaluation.workbook_matches(project))
            write(cells='<row><c><v>1</v></c></row>')
            self.assertFalse(evaluation.workbook_matches(project))
            target.write_bytes(b'not an xlsx')
            self.assertFalse(evaluation.workbook_matches(project))

    def test_cache_or_success_claim_without_body_is_not_delivery(self):
        cached = {'stores':[{'status':'cached', 'records':[]}]}
        actual = {'stores':[{'status':'ok', 'records':[{'id':'saved-rule'}]}]}
        def command(result):
            return {'command':'python dev_memory.py context --query template', 'exit_code':0,
                    'aggregated_output':json.dumps(result)}
        self.assertEqual(evaluation.delivered_ids([command(cached)]), set())
        self.assertEqual(evaluation.delivered_ids([command(actual)]), {'saved-rule'})
        self.assertEqual(evaluation.delivered_ids([{**command(actual), 'exit_code':2}]), set())
        self.assertEqual(evaluation.delivered_ids([{'command':'echo saved-rule', 'aggregated_output':'saved-rule'}]), set())

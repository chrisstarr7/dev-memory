"""The fidelity evaluator must reject lost exceptions and obsolete defaults."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'evals'))
import check_memory_fidelity as evaluation


class FidelityEvaluationTests(unittest.TestCase):
    def test_default_success_cannot_hide_lost_override_or_wrong_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            code = '''from pathlib import Path
import zipfile
def export_template(sheet_name=None):
    name = NAME_EXPRESSION
    target = Path('artifacts/export.xlsx')
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, 'w') as z:
        for p in ('[Content_Types].xml','_rels/.rels','xl/_rels/workbook.xml.rels'):
            z.writestr(p, '<fixture/>')
        z.writestr('xl/workbook.xml', f'<workbook><sheets><sheet name="{name}"/></sheets></workbook>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet><sheetData/></worksheet>')
    return target
'''
            def exporter(expression):
                (project/'exporter.py').write_text(code.replace('NAME_EXPRESSION', expression), encoding='utf-8')
            exporter("sheet_name or '核验登记'")
            self.assertTrue(evaluation.export_matches(project, '核验登记'))
            self.assertTrue(evaluation.export_matches(project, '显式名称', '显式名称'))
            exporter("'核验登记'")
            self.assertTrue(evaluation.export_matches(project, '核验登记'))
            self.assertFalse(evaluation.export_matches(project, '显式名称', '显式名称'))
            exporter("sheet_name or '交付登记'")
            self.assertFalse(evaluation.export_matches(project, '核验登记'))
            (project/'exporter.py').write_text('def export_template(sheet_name=None): return "success"\n', encoding='utf-8')
            self.assertFalse(evaluation.export_matches(project, '核验登记'))

"""Opt-in real-host meaning preservation and correction check with synthetic data."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from check_cross_session import ROOT, delivered_ids
from check_lifecycle import run_model, source_hashes
import dev_memory_setup as setup
import dev_memory_store as store

CAPTURE = ('本项目的表格导出模块长期要求：只导出一张空白的 .xlsx 工作表，不提供导入；'
           '默认表名“交付登记”，但调用者显式指定合法表名时采用指定名称。输出路径固定 artifacts/export.xlsx。'
           '“改用 CSV、允许两张表”是此前被否决的方案，不是当前要求。'
           '另一个习惯明确适用于以后所有项目：尽量复用合适的现有实现；不能满足需求时允许新增。'
           '这只是软偏好，不是禁止新写代码。本轮只确认需求，不改业务文件、AGENTS.md 或创建需求文档。')
CORRECT = '把项目记忆里的默认工作表名改成“核验登记”，其他要求不变。'
IMPLEMENT = ('实现 exporter.py 的 export_template(sheet_name=None)：生成本项目的表格模板，'
             '返回相对于项目根目录的输出路径。None 表示采用项目默认；其他参数是合法的非空表名，'
             '无需新增表名校验。只用 Python 标准库，实际运行验证，不改 AGENTS.md 或创建需求文档。')


def export_matches(project, expected_sheet, sheet_name=None, *, env=None):
    """Execute generated code and inspect the artifact, ignoring its success claims."""
    try:
        child = subprocess.run([sys.executable, '-B', '-c',
            'import json,sys; from exporter import export_template; '
            'print(json.dumps(str(export_template(json.loads(sys.argv[1])))))', json.dumps(sheet_name)],
            cwd=project, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
        if child.returncode:
            return False
        result = json.loads(child.stdout)
        if Path(result).as_posix() != 'artifacts/export.xlsx':
            return False
        with zipfile.ZipFile(project/result) as archive:
            for part in ('[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels'):
                ET.fromstring(archive.read(part))
            sheets = ET.fromstring(archive.read('xl/workbook.xml')).findall('{*}sheets/{*}sheet')
            parts = [p for p in archive.namelist() if p.startswith('xl/worksheets/') and p.endswith('.xml')]
            return (len(sheets) == len(parts) == 1 and sheets[0].get('name') == expected_sheet
                    and not ET.fromstring(archive.read(parts[0])).findall('.//{*}c'))
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired, zipfile.BadZipFile, ET.ParseError):
        return False


def snapshot(project, global_root):
    return {kind:[store.show_record(kind, r['id'], project_root=project, global_root=global_root)
                  for r in store.list_records(kind, project_root=project, global_root=global_root,
                                              status='all')['records']]
            for kind in ('global', 'project')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--reasoning', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT):
        parser.error('Keep synthetic reports and transcripts outside the repository.')
    output.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which('codex')
    if not codex:
        parser.error('Codex CLI required; this evaluation makes real model calls.')
    auth = Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'auth.json'
    report = {'status':'running', 'semantic_review':'required', 'synthetic_only':True, 'model':args.model, 'reasoning':args.reasoning,
              'runtime_source_sha256':source_hashes(), 'runs':[], 'checks':{},
              'limitations':['One host/model sample, not a semantic accuracy rate.',
                             'Stored bodies and evidence require source-by-source semantic review.']}
    try:
        with tempfile.TemporaryDirectory(prefix='dev-memory fidelity ') as td:
            root = Path(td).resolve()
            home, project = root/'home', root/'project'
            ch = home/'.codex'
            ch.mkdir(parents=True, mode=0o700)
            if auth.is_file():
                shutil.copyfile(auth, ch/'auth.json')
                (ch/'auth.json').chmod(0o600)
            skill = home/'.agents/skills/dev-memory'
            shutil.copytree(ROOT/'skills/dev-memory', skill, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            project.mkdir()
            starter = b'"""Synthetic blank template exporter."""\n'
            (project/'exporter.py').write_bytes(starter)
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            global_root = home/'.dev-memory'
            setup.setup(project, 'codex', skill, sys.executable, global_root)
            guide = (project/'AGENTS.md').read_bytes()
            env = {**os.environ, 'HOME':str(home), 'USERPROFILE':str(home), 'CODEX_HOME':str(ch),
                   'DEV_MEMORY_HOME':str(global_root), 'PYTHONDONTWRITEBYTECODE':'1', 'DEV_MEMORY_VECTOR_SETUP':'0'}
            for key in ('CODEX_DISABLE_PROJECT_DOCS', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID'):
                env.pop(key, None)
            for label, prompt in (('capture', CAPTURE), ('correct', CORRECT), ('implement', IMPLEMENT)):
                row, commands = run_model(codex, args.model, args.reasoning, project, home, env,
                                          'fidelity-'+label, prompt, output, 240, network_access=False)
                row['memories'] = snapshot(project, global_root)
                report['runs'].append(row)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                assert row['exit_code'] == 0 and not row['timed_out'] and not row['host_errors'], row
                assert (project/'AGENTS.md').read_bytes() == guide, 'Managed guide changed.'
                if label != 'implement':
                    assert (project/'exporter.py').read_bytes() == starter
                    assert {p.name for p in project.iterdir()} == {'.git','.dev-memory','AGENTS.md','exporter.py'}
            first, corrected, implemented = report['runs']
            prior = {d['record']['id']:d['record']['revision'] for d in first['memories']['project']}
            current = [d['record'] for d in corrected['memories']['project'] if d['record']['status'] == 'active']
            global_rules = [d['record'] for d in corrected['memories']['global']]
            report['checks'] = {
                'three_distinct_conversations':len({t for r in report['runs'] for t in r['thread_ids']}) == 3,
                'correction_revised_existing_rule':any(r['id'] in prior and r['revision'] > prior[r['id']] for r in current),
                'explicit_global_preference_stays_soft':len(global_rules) == 1 and global_rules[0]['strength'] == 'soft'
                    and global_rules[0]['status'] == 'active' and global_rules[0]['cross_project_confirmed'],
                'implementation_received_corrected_body':bool({r['id'] for r in current} & delivered_ids(commands)),
                'corrected_default_in_real_artifact':export_matches(project, '核验登记', env=env),
                'caller_override_exception_preserved':export_matches(project, '显式名称', '显式名称', env=env),
                'source_unchanged_during_evaluation':source_hashes() == report['runtime_source_sha256'],
            }
            assert all(report['checks'].values()), report['checks']
            report['status'] = 'behavior_checks_passed'
    except (AssertionError, OSError, ValueError) as exc:
        report.update(status='failed', error=str(exc))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0 if report['status'] == 'behavior_checks_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Explicit real-host capture, fresh-session recall and observable behavior check."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import dev_memory_setup as setup
import dev_memory_store as store
from check_lifecycle import run_model, source_hashes

REQUIREMENT = ('本项目以后的表格模板导出必须遵守：只生成一张空白工作表，'
               '工作表名称固定为“交付登记”，文件固定输出到 artifacts/intake-template.xlsx；不提供导入。'
               '此要求长期适用于本项目。本轮只确认需求，不修改 AGENTS.md、exporter.py，'
               '也不要创建需求文档或其他业务文件。')
IMPLEMENT = '实现 exporter.py：直接执行时生成一个空白的 .xlsx 表格模板，使用 Python 标准库，并实际运行验证。'


def workbook_matches(project: Path) -> bool:
    """Check the produced artifact, independently of the assistant's success claim."""
    path = project / 'artifacts/intake-template.xlsx'
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            for name in ('[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels'):
                ET.fromstring(archive.read(name))
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            sheets = workbook.findall('{*}sheets/{*}sheet')
            worksheets = [name for name in archive.namelist()
                          if name.startswith('xl/worksheets/') and name.endswith('.xml')]
            return (len(sheets) == len(worksheets) == 1 and sheets[0].get('name') == '交付登记'
                    and not ET.fromstring(archive.read(worksheets[0])).findall('.//{*}c'))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return False


def delivered_ids(commands: list[dict]) -> set[str]:
    ids = set()
    for command in commands:
        text = command.get('command', '')
        if command.get('exit_code') != 0 or 'dev_memory.py' not in text or ' context ' not in text:
            continue
        for line in command.get('aggregated_output', '').splitlines():
            try:
                result = json.loads(line)
            except ValueError:
                continue
            if isinstance(result, dict):
                ids.update(record['id'] for bucket in result.get('stores', [])
                           for record in bucket.get('records', []))
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, help='Exact model to use for both independent conversations')
    parser.add_argument('--reasoning', required=True)
    parser.add_argument('--output', type=Path, required=True, help='Synthetic report/transcripts outside the source repository')
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT) or args.timeout_seconds < 1:
        parser.error('Use an output outside the source repository and a positive timeout.')
    output.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which('codex')
    if not codex:
        parser.error('Codex CLI is required; this check makes real model calls.')
    auth = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'auth.json'
    frozen = source_hashes()
    report = {'status':'running', 'synthetic_only':True, 'host':subprocess.check_output([codex, '--version'], text=True).strip(),
              'model':args.model, 'reasoning':args.reasoning, 'runtime_source_sha256':frozen,
              'prompts_mention_memory':False, 'hooks_configured':False, 'runs':[], 'checks':{},
              'limitations':['One named host/model sample; not enforcement on every future task or other hosts.',
                             'Tests source-only memory with vectors unconfigured; vector integration is separate.']}
    try:
        with tempfile.TemporaryDirectory(prefix='dev-memory fresh conversations ') as td:
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
            starter = b'"""Empty spreadsheet template exporter."""\n'
            (project/'exporter.py').write_bytes(starter)
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            global_root = home/'.dev-memory'
            setup.setup(project, 'codex', skill, sys.executable, global_root)
            guide = (project/'AGENTS.md').read_bytes()
            subprocess.run(['git', '-C', str(project), 'add', 'AGENTS.md', 'exporter.py'], check=True)
            subprocess.run(['git', '-C', str(project), '-c', 'user.name=Synthetic Check',
                            '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'fixture'], check=True)
            env = {**os.environ, 'HOME':str(home), 'USERPROFILE':str(home), 'CODEX_HOME':str(ch),
                   'DEV_MEMORY_HOME':str(global_root), 'PYTHONDONTWRITEBYTECODE':'1', 'DEV_MEMORY_VECTOR_SETUP':'0'}
            for key in ('CODEX_DISABLE_PROJECT_DOCS', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID'):
                env.pop(key, None)
            def run(label, prompt):
                row, commands = run_model(codex, args.model, args.reasoning, project, home, env,
                                          label, prompt, output, args.timeout_seconds, network_access=False)
                report['runs'].append(row)
                assert row['exit_code'] == 0 and not row['timed_out'] and not row['host_errors'], row
                calls = [c for c in commands if c.get('exit_code') == 0
                         and 'dev_memory.py' in c.get('command', '') and ' context ' in c.get('command', '')]
                assert calls and '--force' in calls[0]['command'], 'First successful context must reload current bodies.'
                return commands
            run('capture', REQUIREMENT)
            records = store.list_records('project', project_root=project)['records']
            assert records, 'No active project memory was saved by conversation A.'
            ids = {record['id'] for record in records}
            assert (project/'exporter.py').read_bytes() == starter and (project/'AGENTS.md').read_bytes() == guide
            assert set(p.name for p in project.iterdir()) == {'.git', '.dev-memory', 'AGENTS.md', 'exporter.py'}
            report['checks']['capture_without_business_file_changes'] = True
            commands = run('fresh-implementation', IMPLEMENT)
            assert (len(report['runs'][0]['thread_ids']) == len(report['runs'][1]['thread_ids']) == 1
                    and report['runs'][0]['thread_ids'] != report['runs'][1]['thread_ids']), 'Distinct host conversations not observed.'
            assert ids & delivered_ids(commands), 'Conversation B did not receive saved memory bodies.'
            assert workbook_matches(project), 'Generated workbook did not follow the saved sheet/path/blankness rule.'
            assert (project/'AGENTS.md').read_bytes() == guide
            report['checks'].update(distinct_host_conversations=True, fresh_session_received_saved_body=True, artifact_follows_rule=True,
                                    managed_guide_unchanged=True)
            assert source_hashes() == frozen, 'Source changed during evaluation.'
            report['status'] = 'passed'
    except Exception as exc:
        report.update(status='failed', failure=f'{type(exc).__name__}: {exc}')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status':report['status'], 'checks':report['checks']}, ensure_ascii=False), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

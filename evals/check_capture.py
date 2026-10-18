"""Explicit isolated Codex probe for ordinary first-signal habit capture."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from check_lifecycle import run_model
from dev_memory import SKILL_FILES
import dev_memory_store as store

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    ('first', 'describe_name', 'normalize_text',
     "修复 helper.py 的 describe_name(value)：字符串应去首尾空白，空白字符串返回 '(empty)'。这里先查已有实现复用，别又写一套。保留公开函数。完成后简短说明结果。"),
    ('independent', 'label_text', 'canonical_text',
     "修复 helper.py 的 label_text(value)：字符串应去首尾空白，空白字符串返回 '(empty)'。还是先看看现有逻辑是否合适，别重复造一份。保留公开函数。完成后简短说明结果。"),
    ('temporary', None, None,
     '更新 STATUS.md：这个项目只允许 pending 和 approved 两种业务状态，不允许新增其他状态。这次不要运行测试，只修改这个说明文件。简短说明完成情况。'),
]


def snapshots(global_root: Path) -> list[dict]:
    records = store.list_records('global', global_root=global_root, status='all')['records']
    result=[]
    for item in records:
        shown=store.show_record('global',item['id'],global_root=global_root)
        record=shown['record']
        result.append({k:record[k] for k in ('title','content','conditions','do','dont','exceptions','status','strength','cross_project_confirmed')}
                      | {'evidence_count':len(shown['evidence']),
                         'source_types':sorted({e['source_type'] for e in shown['evidence']}),
                         'independent_signals':len({e['ingestion_id'] for e in shown['evidence']
                                                   if e['ingestion_id'].startswith('habit:')})})
    return result


def implementation(project: Path, function: str | None, helper: str | None) -> dict:
    if function is None:
        text=(project/'STATUS.md').read_text()
        return {'passed':'pending' in text and 'approved' in text}
    try:
        spec=importlib.util.spec_from_file_location('capture_fixture',project/'helper.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        target=getattr(module,function)
        assert target('  hello  ')=='hello' and target('   ')=='(empty)'
        calls=[]
        def observed(value):
            calls.append(value)
            return 'delegated'
        setattr(module,helper,observed)
        reused=target('test')=='delegated' and calls==['test']
        return {'passed':True,'existing_helper_reused':reused}
    except Exception as exc:
        return {'passed':False,'reason':type(exc).__name__}


def acceptance(cells: list[dict]) -> dict[str, bool]:
    """Check synthetic outcomes separately from successful host commands."""
    current={row['stage']:row for row in cells if row['version']=='current'}
    if set(current)!={'first','independent','temporary'}:
        return {'all_stages_present':False}
    first=current['first']['memories'];second=current['independent']['memories']
    return {
        'business_tasks_passed':all(row['implementation'].get('passed') for row in current.values()),
        'existing_helpers_reused':all(current[s]['implementation'].get('existing_helper_reused') for s in ('first','independent')),
        'first_signal_saved_inactive':len(first)==1 and first[0]['status']=='candidate' and first[0]['independent_signals']==1,
        'independent_evidence_promoted_same_body':bool(first) and len(second)==1 and second[0]['status']=='active'
            and second[0]['strength']=='soft' and not second[0]['cross_project_confirmed']
            and second[0]['independent_signals']==2 and second[0]['content']==first[0]['content'],
        'temporary_and_business_request_added_no_memory':current['temporary']['memories']==second,
    }


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--reasoning',default='high')
    parser.add_argument('--baseline-ref',default='ecc9744')
    parser.add_argument('--versions',nargs='+',choices=('baseline','current'),default=['baseline','current'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT):parser.error('Raw host logs must stay outside the repository.')
    output.parent.mkdir(parents=True,exist_ok=True)
    codex=shutil.which('codex')
    if not codex:parser.error('Codex CLI required.')
    auth=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    report={'status':'running','synthetic_only':True,'model':args.model,'reasoning':args.reasoning,
            'host':subprocess.check_output([codex,'--version'],text=True).strip(),'baseline_ref':args.baseline_ref,
            'cells':[],'limitations':['Exploratory sequential semantic probe, not a repeated latency benchmark.',
                                      'A typed user source or receipt alone does not prove correct semantic capture.']}
    with tempfile.TemporaryDirectory(prefix='dev-memory-capture-') as temp:
        scratch=Path(temp);current=scratch/'current';current.mkdir()
        shutil.copytree(ROOT/'skills',current/'skills',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(ROOT/'install.py',current/'install.py')
        report['runtime_source_sha256']={n:hashlib.sha256((current/'skills/dev-memory'/n).read_bytes()).hexdigest() for n in SKILL_FILES}
        baseline=scratch/'baseline';baseline.mkdir();archive=scratch/'baseline.zip'
        subprocess.run(['git','archive','--format=zip',f'--output={archive}',args.baseline_ref],cwd=ROOT,check=True)
        with zipfile.ZipFile(archive) as package:package.extractall(baseline)
        for version,source in [('baseline',baseline),('current',current)]:
            if version not in args.versions:continue
            home=scratch/('home-'+version);home.mkdir();codex_home=home/'codex';codex_home.mkdir()
            if auth.is_file():shutil.copyfile(auth,codex_home/'auth.json');os.chmod(codex_home/'auth.json',0o600)
            env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(codex_home),
                 'DEV_MEMORY_HOME':str(home/'data'),'PYTHONDONTWRITEBYTECODE':'1'}
            env.pop('CODEX_DISABLE_PROJECT_DOCS',None)
            for stage,function,helper,prompt in STAGES[:1] if version=='baseline' else STAGES:
                project=home/stage;project.mkdir()
                if function:
                    (project/'helper.py').write_text(f"def {helper}(value):\n    return value.strip() or '(empty)'\n\ndef {function}(value):\n    return value\n")
                else:(project/'STATUS.md').write_text('Allowed states: draft, pending, approved.\n')
                installed=subprocess.run([sys.executable,'-B',str(source/'install.py'),'codex','--target',str(home/'runtime'),
                                          '--project',str(project),'--json'],cwd=home,env=env,text=True,capture_output=True,check=True)
                assert json.loads(installed.stdout)['user_activation']['activation']=='configured'
                before=snapshots(home/'data')
                row,commands=run_model(codex,args.model,args.reasoning,project,home,env,f'{version}-{stage}',prompt,output,240)
                row.update(version=version,stage=stage,implementation=implementation(project,function,helper),
                           records_before=len(before),memories=snapshots(home/'data'),
                           memory_commands=sum('dev_memory.py' in c.get('command','') for c in commands))
                report['cells'].append(row);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                if row['exit_code'] or row['timed_out']:
                    report['status']='host_incomplete';output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');return 1
    report['acceptance']=acceptance(report['cells']) if 'current' in args.versions else {}
    passed=all(report['acceptance'].values())
    report['status']='completed' if passed else 'semantic_failure'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())

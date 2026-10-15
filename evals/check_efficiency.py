"""Compare a Git baseline/current runtime with synthetic scale or explicit Codex tasks."""
from __future__ import annotations

import argparse
import contextlib
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

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r'''
import contextlib, json, statistics, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(sys.argv[1])/'skills/dev-memory/scripts'))
import dev_memory as cli
import dev_memory_store as store
with tempfile.TemporaryDirectory() as td:
    root=Path(td);project=root/'project';project.mkdir();glob=root/'data'
    store.init_project(project);store.init_global(glob)
    _,db,cfg=store._config_for('global',None,glob)
    rows=[];count=0
    for size in (1000,10000):
        with contextlib.closing(store._connect(db)) as conn:
            for n in range(count,size):
                record=store._validate_record({'kind':'preference','claim_type':'preference','status':'active','strength':'soft',
                    'cross_project_confirmed':True,'title':f'Habit shard{n}',
                    'content':f'For shard{n} prefer evidence before a narrow debugging change.', 'tags':['debugging'],
                    'source':{'type':'user_confirmation','excerpt':'Synthetic cross-project habit.'}},'global',None,cfg['namespace_id'])
                mid,_=store._store_record(conn,record,evidence=False);store._queue_maintenance(conn,mid)
            conn.commit()
        count=size;times=[];queries=[];connect=store._connect
        def traced(*a,**kw):
            conn=connect(*a,**kw)
            conn.set_trace_callback(lambda sql:queries.append(sql) if 'INDEXED BY search_term_term' in sql and 'JOIN memories' in sql else None)
            return conn
        for _ in range(10):
            start=time.perf_counter()
            with patch.object(store,'_connect',traced):
                result=cli.context(f'shard{size-1}',project_root=project,global_root=glob,force=True,include_task=False)
            times.append((time.perf_counter()-start)*1000)
        with contextlib.closing(connect(db,readonly=True)) as conn:
            plan=[r[3] for r in conn.execute('EXPLAIN QUERY PLAN '+queries[-1])]
        assert any('search_term_term' in p for p in plan)
        assert any(r['title']==f'Habit shard{size-1}' for r in result['stores'][0]['records'])
        maintenance=result['stores'][0]['maintenance']
        rows.append({'records':size,'median_ms':round(statistics.median(times),3),'max_ms':round(max(times),3),
            'response_characters':len(json.dumps(result,ensure_ascii=False)),
            'body_records':sum(len(b['records']) for b in result['stores']),
            'maintenance_bodies':len(maintenance.get('records',[])), 'query_plan':plan})
    print(json.dumps(rows))
'''

SEED = r'''
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'skills/dev-memory/scripts'))
import dev_memory_store as store
root=Path(sys.argv[2]);store.init_global(root)
records=[
('Evidence for fixes','For bug fixes, inspect the existing implementation and establish the cause before editing.','debugging'),
('Boundary regressions','For bug fixes, add and run standard-library unit tests for success, exhausted attempts and nonretryable errors.','verification'),
('Delivery order','For development tasks, report in three headings: 结果, 验证, 遗留.','communication')]
for n,(title,content,topic) in enumerate(records):
 result=store.apply_payload({'schema_version':1,'scope':'global','session_id':'seed','turn_id':str(n),'idempotency_key':f'seed-{n}',
  'operations':[{'op':'ADD','scope':'global','record':{'kind':'preference','claim_type':'preference','strength':'hard','status':'active',
   'cross_project_confirmed':True,'title':title,'content':content,'tags':[topic],
   'source':{'type':'user_confirmation','excerpt':'Synthetic preference explicitly applies across projects.'}}}]},global_root=root)
 assert result['status']=='saved',result
'''

STARTER = 'def retry(operation, attempts=3):\n    return operation()\n'
PROMPT = '''修复 retry.py 中的 retry：遇到 OSError 时最多尝试 attempts 次，成功则返回结果；次数耗尽时抛出最后一次原始异常；其他异常立即抛出；attempts 必须是正整数，否则 ValueError。保留现有公开函数。完成后说明结果和验证情况。
补充一个以后所有项目都适用的习惯：涉及重试时，要明确区分“尝试总次数”和“额外重试次数”，避免次数歧义。'''


def correctness(project: Path) -> dict:
    path = project/'retry.py'
    if not path.exists():
        return {'passed':False,'reason':'missing implementation'}
    try:
        spec=importlib.util.spec_from_file_location('synthetic_retry',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calls=[]
        def transient():
            calls.append(1)
            if len(calls)<3:raise OSError('temporary')
            return 7
        assert module.retry(transient,3)==7 and len(calls)==3
        for value in [0,-1,True,1.5]:
            try:module.retry(lambda:1,value)
            except ValueError:pass
            else:raise AssertionError('invalid attempts accepted')
        error=OSError('last');calls=[]
        def fail():calls.append(1);raise error
        try:module.retry(fail,2)
        except OSError as exc:assert exc is error and len(calls)==2
        else:raise AssertionError('expected exhaustion')
        calls=[]
        def fatal():calls.append(1);raise TypeError('fatal')
        try:module.retry(fatal,3)
        except TypeError:assert len(calls)==1
        else:raise AssertionError('nonretryable error swallowed')
        return {'passed':True}
    except Exception as exc:
        return {'passed':False,'reason':type(exc).__name__+': '+str(exc)}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-ref',default='9ecc959')
    p.add_argument('--host',action='store_true');p.add_argument('--model');p.add_argument('--reasoning',default='high')
    p.add_argument('--user-level-second-project',action='store_true',help='In current project B, rely only on the existing user-level binding.')
    p.add_argument('--versions',nargs='+',choices=('off','baseline','current'),default=['off','baseline','current'])
    args=p.parse_args();output=args.output.resolve()
    if output.is_relative_to(ROOT):p.error('Keep raw synthetic host logs outside the repository.')
    if args.host and not args.model:p.error('Explicit host evaluation requires --model for a matched comparison.')
    output.parent.mkdir(parents=True,exist_ok=True)
    report={'status':'running','baseline_ref':args.baseline_ref,'synthetic_only':True,'repetitions':1 if args.host else 10,
            'kind':'real_codex_tasks' if args.host else 'local_program_operations','cells':[],
            'limitations':['One host trial per cell is exploratory, not a latency/accuracy guarantee.'] if args.host else
                          ['Bulk synthetic index seeding omits evidence; local program timing is not AI task latency.']}
    with tempfile.TemporaryDirectory(prefix='dev-memory-efficiency-') as td:
        scratch=Path(td);archive=scratch/'baseline.zip';baseline=scratch/'baseline';baseline.mkdir()
        current=scratch/'current';current.mkdir()
        shutil.copytree(ROOT/'skills',current/'skills',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(ROOT/'install.py',current/'install.py')
        report['runtime_source_sha256']={str(path.relative_to(current)):hashlib.sha256(path.read_bytes()).hexdigest()
                                        for path in sorted(current.rglob('*')) if path.is_file()}
        subprocess.run(['git','archive','--format=zip',f'--output={archive}',args.baseline_ref],cwd=ROOT,check=True)
        with zipfile.ZipFile(archive) as z:z.extractall(baseline)
        if not args.host:
            for label,source in [('baseline',baseline),('current',current)]:
                reply=subprocess.run([sys.executable,'-c',PROGRAM,str(source)],text=True,capture_output=True,check=True)
                report['cells'].append({'version':label,'measurements':json.loads(reply.stdout)})
        else:
            from check_lifecycle import run_model
            codex=shutil.which('codex')
            if not codex:p.error('Codex CLI required.')
            auth=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
            report.update(model=args.model,reasoning=args.reasoning,host=subprocess.check_output([codex,'--version'],text=True).strip())
            for label,source in [('off',current),('baseline',baseline),('current',current)]:
                if label not in args.versions:continue
                home=scratch/('case-'+label);home.mkdir();ch=home/'.codex';ch.mkdir();project=home/'project-a';project.mkdir()
                if auth.is_file():shutil.copyfile(auth,ch/'auth.json');os.chmod(ch/'auth.json',0o600)
                env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(ch),
                     'DEV_MEMORY_HOME':str(home/'data'),'PYTHONDONTWRITEBYTECODE':'1'}
                env.pop('CODEX_DISABLE_PROJECT_DOCS',None)
                subprocess.run([sys.executable,'-c',SEED,str(source),str(home/'data')],env=env,check=True)
                for project_label in (['a'] if label=='off' else ['a','b']):
                    project=home/f'project-{project_label}';project.mkdir(exist_ok=True)
                    (project/'retry.py').write_text(STARTER)
                    unbound = args.user_level_second_project and label=='current' and project_label=='b'
                    if label!='off' and not unbound:
                        setup=subprocess.run([sys.executable,str(source/'install.py'),'codex','--target',str(home/'runtime'),
                                              '--project',str(project),'--json'],env=env,cwd=home,text=True,capture_output=True,check=True)
                        assert json.loads(setup.stdout)['user_activation']['activation']=='configured'
                    run_label=f'{label}-{project_label}'
                    row,commands=run_model(codex,args.model,args.reasoning,project,home,env,run_label,PROMPT,output,240)
                    row['version']=label;row['project']=project_label;row['activation']='user_level_only' if unbound else ('off' if label=='off' else 'project_and_user_level');row['correctness']=correctness(project)
                    row['memory_calls']=sum('dev_memory.py' in c.get('command','') or 'dev-memory/scripts/' in c.get('command','') for c in commands)
                    row['test_command_observed']=any('unittest' in c.get('command','') for c in commands)
                    from dev_memory_store import list_records, show_record
                    memories=list_records('global',global_root=home/'data')['records']
                    row['active_habits']=[{'title':r['title'],'content':r['content']} for item in memories
                                          for r in [show_record('global',item['id'],global_root=home/'data')['record']]]
                    report['cells'].append(row);output.write_text(json.dumps(report,indent=2)+'\n')
                    if row['exit_code'] or row['timed_out']:
                        report['status']='host_incomplete';output.write_text(json.dumps(report,indent=2)+'\n');return 1
        report['status']='completed'
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0


if __name__=='__main__':raise SystemExit(main())

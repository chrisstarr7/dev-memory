"""Opt-in paired real-task memory baseline; synthetic stores, independent artifacts, no new runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile

from check_lifecycle import ROOT, run_model, store
import dev_memory_setup as setup

CASES = ('durable', 'override', 'conditional', 'long')


def usage_total(usage):
    if not isinstance(usage, dict):
        return None
    values = [usage.get(k) for k in ('input_tokens', 'output_tokens')]
    return sum(values) if all(type(v) is int and v >= 0 for v in values) else None


def delivered(commands):
    """Successful context/show bodies only, never claims, indexes or cached metadata."""
    ids = set()
    for command in commands:
        text = command.get('command', '')
        if command.get('exit_code') != 0 or not cli_read(text):
            continue
        for line in command.get('aggregated_output', '').splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            for bucket in data.get('stores', [data]):
                ids.update(r['id'] for r in bucket.get('records', [])
                           if isinstance(r, dict) and r.get('id') and 'content' in r)
    return ids


def cli_read(command):
    """Recognize an actual Python CLI invocation, not echo/agent claims containing its name."""
    try:
        tokens=shlex.split(command)
        for _ in range(3):
            if len(tokens)==3 and Path(tokens[0]).name in {'sh','bash','zsh'} and tokens[1] in {'-c','-lc'}:
                tokens=shlex.split(tokens[2])
            else:break
        if not tokens or not re.fullmatch(r'python(?:\d+(?:\.\d+)?)?(?:\.exe)?',Path(tokens[0]).name) or '-c' in tokens[:3]:
            return False
        index=next((n for n,t in enumerate(tokens[1:5],1) if Path(t).name=='dev_memory.py'),None)
        return index is not None and any(t in {'context','recall','show'} for t in tokens[index+1:])
    except ValueError:
        return False


def artifact(project, env, expected, bad_prefix):
    """Run generated function independently; absence/failure cannot pass as non-adoption."""
    cmd = 'import json;from formatter import format_label;print(json.dumps([format_label("中文",False),format_label("中文",True)],ensure_ascii=False))'
    try:
        result = subprocess.run([sys.executable, '-B', '-c', cmd], cwd=project, env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=10)
        values = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        values = None
    valid = isinstance(values, list) and len(values) == 2 and all(isinstance(v, str) for v in values)
    return {'passed': valid and values == expected, 'readable_artifact': valid,
            'wrong_memory_behavior': any(bad_prefix in v for v in values) if valid else None}


def summarize(rows):
    on = [r for r in rows if r['mode'] == 'on']
    expected = sum(r['expected_count'] for r in on)
    readable = [r for r in on if r['artifact']['readable_artifact']]
    pairs = []
    for row in on:
        other = next((r for r in rows if r['case'] == row['case'] and r['repeat'] == row['repeat'] and r['mode'] == 'off'), None)
        if other:
            a, b = usage_total(row.get('usage')), usage_total(other.get('usage'))
            pairs.append({'case': row['case'], 'repeat': row['repeat'],
                          'token_delta': a-b if a is not None and b is not None else None,
                          'seconds_delta': row['seconds']-other['seconds']})
    times = sorted(r['seconds'] for r in rows)
    return {'recall': {'hits':sum(r['correct_delivered'] for r in on), 'expected':expected,
                       'rate':sum(r['correct_delivered'] for r in on)/expected if expected else None},
            'rule_execution': {'passed':sum(r['artifact']['passed'] for r in on), 'tasks':len(on)},
            'off_execution': {'passed':sum(r['artifact']['passed'] for r in rows if r['mode']=='off'),
                              'tasks':sum(r['mode']=='off' for r in rows)},
            'wrong_adoption': {'tasks':sum(r['artifact']['wrong_memory_behavior'] is True for r in readable),
                               'readable_tasks':len(readable), 'missing_artifacts':len(on)-len(readable),
                               'rate':sum(r['artifact']['wrong_memory_behavior'] is True for r in readable)/len(readable) if readable else None},
            'host_failures':sum(bool(r.get('exit_code')) or r.get('timed_out',False) for r in rows),
            'missing_usage':sum(usage_total(r.get('usage')) is None for r in rows),
            'task_seconds': {'median':statistics.median(times) if times else None,
                             'p95':times[max(0,math.ceil(.95*len(times))-1)] if times else None},
            'paired_deltas':pairs}


def finish_status(rows):
    on=[r for r in rows if r['mode']=='on']
    successful=[r for r in on if not r['exit_code'] and not r['timed_out']]
    if not on or not all(r.get('off_runtime_absent') for r in rows):
        return 'failed'
    if not all(r['artifact']['passed'] and r['correct_delivered']==r['expected_count'] for r in successful):
        return 'failed'
    if any(r['exit_code'] or r['timed_out'] for r in rows):
        return 'host_incomplete'
    return 'metrics_incomplete' if any(usage_total(r.get('usage')) is None for r in rows) else 'passed'


def seed(project, other, global_root, case, good, bad):
    expected = [good+'中文', good+'中文']
    text = f'formatter.py 的 format_label(text, complex_task=False) 返回 {good} 加原始 text。'
    if case in {'conditional', 'long'}:
        text = f'formatter.py 的 format_label 仅在 complex_task=True 时返回 {good} 加 text；False 时原样返回 text，禁止前缀。'
        expected = ['中文', good+'中文']
        if case == 'long':
            text = f'formatter.py 的 format_label 在 complex_task=True 时返回 {good} 加 text。'+('说明：仅定义文本标签约定，不改变其他接口。'*35)+'重要例外：complex_task=False 时原样返回 text，禁止添加前缀。'
    def add(scope, root, title, content, status='active'):
        record = {'kind':'preference' if scope=='global' else 'convention',
                  'claim_type':'preference' if scope=='global' else 'desired','status':status,
                  'strength':'hard','title':title,'content':content,
                  'conditions':'实现 formatter.py 的 format_label 时。',
                  'source':{'type':'user_statement','excerpt':'仅用于隔离评测的长期格式约定。'}}
        if scope == 'global': record['cross_project_confirmed']=True
        result = store.apply_payload({'schema_version':1,'scope':scope,'session_id':'seed','turn_id':title,
            'idempotency_key':title,'operations':[{'op':'ADD','scope':scope,'record':record}]},
            project_root=root, global_root=global_root, schedule_vectors=False)
        assert result['status']=='saved', result
        return result['stores'][0]['operations'][0]['id']
    gold = add('project',project,'format_label current receipt',text)
    add('project',project,'format_label retired receipt',f'历史格式返回 {bad} 加 text。','archived')
    add('project',other,'format_label other project',f'返回 {bad} 加 text。')
    if case == 'override':
        add('global',None,'format_label historical global preference',f'默认 format_label 返回 {bad} 加 text，当前用户要求优先。')
    return {gold}, expected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True);p.add_argument('--reasoning',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repetitions',type=int,default=2)
    p.add_argument('--seed',type=int,default=1702);p.add_argument('--timeout-seconds',type=int,default=180)
    p.add_argument('--runtime-ref',help='Replay the same scenarios with an exact Git runtime commit')
    p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES[:3]))
    p.add_argument('--disclosure',choices=('full','auto','index'),default='full')
    args = p.parse_args();output=args.output.expanduser().resolve()
    if output.is_relative_to(ROOT) or not 1 <= args.repetitions <= 10 or args.timeout_seconds < 1:
        p.error('Use an output outside the repo, 1..10 repetitions and a positive timeout.')
    codex=shutil.which('codex')
    if not codex:p.error('Real Codex CLI required; this command spends model quota.')
    output.parent.mkdir(parents=True,exist_ok=True)
    auth=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    report={'schema_version':1,'status':'running','synthetic_only':True,'model':args.model,'reasoning':args.reasoning,
            'seed':args.seed,'repetitions':args.repetitions,'cases':args.cases,'disclosure':args.disclosure,
            'evaluator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'runtime_source_sha256':{},
            'host':subprocess.check_output([codex,'--version'],text=True).strip(),'rows':[],
            'limits':['Small synthetic paired sample, not a population accuracy or speedup guarantee.',
                      'Off mode lacks stored project knowledge by design; report failures, do not hide them.',
                      'Wrong adoption is observable forbidden output, not a claim about model internal reasoning.',
                      'Cached input is reported separately, never added twice to total input tokens.',
                      'Token/time deltas do not by themselves establish a correctness improvement.']}
    try:
        with tempfile.TemporaryDirectory(prefix='memory-quality ') as td:
            scratch=Path(td).resolve();frozen=scratch/'source'
            if args.runtime_ref:
                commit=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',args.runtime_ref+'^{commit}'],cwd=ROOT,text=True).strip()
                from dev_memory import SKILL_FILES
                for name in SKILL_FILES:
                    target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(subprocess.check_output(['git','show',commit+':skills/dev-memory/'+name],cwd=ROOT))
                report['runtime_commit']=commit
            else:
                shutil.copytree(ROOT/'skills/dev-memory',frozen,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            report['runtime_source_sha256']={str(f.relative_to(frozen)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(frozen.rglob('*')) if f.is_file()}
            for repeat in range(args.repetitions):
                for case in args.cases:
                    rng=random.Random(f'{args.seed}:{case}:{repeat}')
                    good=f'R{rng.getrandbits(40):x}|';bad=f'OLD{rng.getrandbits(40):x}|'
                    for mode in (('off','on') if repeat%2==0 else ('on','off')):
                        label=f'{case}-{repeat}-{mode}';home=scratch/label;ch=home/'.codex';ch.mkdir(parents=True,mode=0o700)
                        if auth.is_file():shutil.copyfile(auth,ch/'auth.json');(ch/'auth.json').chmod(0o600)
                        project=home/'project';other=home/'other-project';project.mkdir();other.mkdir()
                        glob=home/'.dev-memory'
                        if mode=='on':
                            skill=home/'.agents/skills/dev-memory';shutil.copytree(frozen,skill)
                            setup.setup(project,'codex',skill,sys.executable,glob);store.init_project(other)
                            gold,expected=seed(project,other,glob,case,good,bad)
                            if args.disclosure!='full':
                                with (project/'AGENTS.md').open('a',encoding='utf-8') as guide:
                                    guide.write('\nFor context/recall in this evaluation, use --disclosure '+args.disclosure+'.\n')
                        else:
                            # Removing AGENTS alone is insufficient: hosts auto-discover user Skills.
                            gold=set();expected=['中文' if case in {'conditional','long'} else good+'中文',good+'中文']
                        (project/'formatter.py').write_text('"""Implement format_label here."""\n',encoding='utf-8')
                        env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(ch),
                             'DEV_MEMORY_HOME':str(glob),'DEV_MEMORY_VECTOR_SETUP':'0','PYTHONDONTWRITEBYTECODE':'1'}
                        for k in ('CODEX_DISABLE_PROJECT_DOCS','PYTHONPATH','PYTHONHOME'):env.pop(k,None)
                        prompt='实现 formatter.py 的 format_label(text, complex_task=False)，遵守当前项目的文本标签约定。仅使用标准库，实际运行验证，不修改 AGENTS.md；不要读取其他项目。'
                        if case=='override':prompt+=f' 本轮明确要求始终返回 {good} 加原始 text，覆盖历史默认前缀。'
                        row,commands=run_model(codex,args.model,args.reasoning,project,home,env,label,prompt,output,args.timeout_seconds,network_access=False)
                        row.update(case=case,mode=mode,repeat=repeat,expected_count=len(gold),
                                   expected_ids=sorted(gold),delivered_ids=sorted(delivered(commands)),
                                   correct_delivered=len(gold & delivered(commands)),artifact=artifact(project,env,expected,bad))
                        row['off_runtime_absent'] = mode!='off' or (not (home/'.agents').exists() and not glob.exists() and not (project/'.dev-memory').exists())
                        report['rows'].append(row);report['metrics']=summarize(report['rows'])
                        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        report['status']=finish_status(report['rows'])
        report['temporary_data_removed']=not scratch.exists()
    except BaseException as exc:
        report['status']='failed';report['error']=type(exc).__name__+': '+str(exc);raise
    finally:
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'status':report['status'],'metrics':report['metrics']},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())

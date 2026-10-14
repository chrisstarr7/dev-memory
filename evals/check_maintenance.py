"""Real-host semantic maintenance check using only isolated synthetic memory."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'skills/dev-memory/scripts'))
import dev_memory_store as store
from dev_memory import SKILL_FILES


def source_hashes():
    return {name:hashlib.sha256((ROOT/'skills/dev-memory'/name).read_bytes()).hexdigest() for name in SKILL_FILES}


def observed_maintenance(events):
    observed = {'COMPACT':False, 'MERGE_DUPLICATES':False, 'MAINTENANCE_REVIEW':False}
    for event in events:
        if event.get('type') != 'item.completed':
            continue
        item = event.get('item',{})
        if item.get('type') != 'command_execution':
            continue
        try:
            result = json.loads(item.get('aggregated_output',''))
        except ValueError:
            continue
        if not isinstance(result,dict):
            continue
        stores=result.get('stores',[])
        if not isinstance(stores,list):
            continue
        for bucket in stores:
            if not isinstance(bucket,dict) or bucket.get('status') not in {'saved','checked_noop'}:
                continue
            for operation in bucket.get('operations',[]):
                if not isinstance(operation,dict):
                    continue
                observed['COMPACT'] |= operation.get('compacted') is True
                observed['MERGE_DUPLICATES'] |= bool(operation.get('merged_ids'))
                observed['MAINTENANCE_REVIEW'] |= bool(operation.get('reviewed_ids'))
    return observed


def observed_usage(events):
    """AI-reported concrete use, separate from independent behavioral checks."""
    ids = set()
    for event in events:
        item = event.get('item', {})
        if event.get('type') != 'item.completed' or item.get('type') != 'command_execution':
            continue
        try:
            result = json.loads(item.get('aggregated_output', ''))
        except ValueError:
            continue
        if not isinstance(result, dict) or not isinstance(result.get('stores'), list):
            continue
        for bucket in result['stores']:
            if not isinstance(bucket, dict) or bucket.get('status') not in {'saved','checked_noop'}:
                continue
            for operation in bucket.get('operations', []):
                if isinstance(operation, dict) and operation.get('usage') == 'ai_reported_not_behavior_verified' and isinstance(operation.get('used_id'), str):
                    ids.add(operation['used_id'])
    return sorted(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--reasoning', choices=('low','medium','high','xhigh'),required=True)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT):
        parser.error('Keep synthetic model transcripts outside the public repository.')
    output.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which('codex')
    if not codex:
        parser.error('Codex CLI is required for this optional real model check.')
    auth = Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    frozen = source_hashes()
    report = {'runtime_source_sha256':frozen,'status':'running','runtime_version':'0.6.0','host':subprocess.check_output([codex,'--version'],text=True).strip(),
              'model':args.model,'reasoning_effort':args.reasoning,'synthetic_only':True,
              'user_prompts_mention_skill_or_maintenance':False,'hooks_configured':False,'runs':[]}
    try:
        with tempfile.TemporaryDirectory(prefix='dev-memory maintenance model ') as temporary:
            home = Path(temporary).resolve(); project = home/'project-a'; project.mkdir()
            other = home/'project-b'; other.mkdir()
            codex_home=home/'.codex'; codex_home.mkdir()
            if auth.is_file():
                shutil.copyfile(auth,codex_home/'auth.json');os.chmod(codex_home/'auth.json',0o600)
            env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(codex_home),
                 'DEV_MEMORY_HOME':str(home/'.dev-memory'),'PYTHONDONTWRITEBYTECODE':'1'}
            env.pop('CODEX_DISABLE_PROJECT_DOCS',None)
            global_root=home/'.dev-memory'
            for directory in (project,other):
                subprocess.run(['git','init','-q',str(directory)],check=True)
                (directory/'policy.py').write_text('def eligible(delivered, unopened, days, gift, final_sale):\n    return days <= 30\n')
                setup=subprocess.run([sys.executable,'-B',str(ROOT/'install.py'),'codex','--project',str(directory),'--json'],
                                     cwd=home,env=env,capture_output=True,text=True,timeout=20)
                assert setup.returncode==0,setup.stdout+setup.stderr
            policy={
                'kind':'business_rule','claim_type':'desired','strength':'hard','title':'Return policy',
                'conditions':'Signed for, unopened, at most 14 days after delivery.',
                'exceptions':'Gift orders and final-sale items are excluded.',
                'do':'Require every condition.','dont':'Never permit excluded orders.',
                'verification_steps':'Check each positive condition, day 14/15, and both exclusions.',
                'tags':['refund'], 'source':{'type':'user_confirmation','excerpt':'Synthetic: delivered, unopened, 14 days; exclude gifts and final sale.'}}
            contents=['All specified return eligibility conditions and exclusions must hold.',
                      'Refund eligibility requires every listed condition; the exclusions always apply.',
                      'All specified return eligibility conditions and exclusions must hold. '*30]
            seed_ids=[]
            for n,content in enumerate(contents):
                result=store.apply_payload({'schema_version':1,'scope':'project','session_id':'synthetic-seed','turn_id':f'seed-{n}',
                    'idempotency_key':f'seed-{n}','operations':[{'op':'ADD','record':{**policy,'content':content}}]},project_root=project)
                assert result['status']=='saved',result
                seed_ids.append(result['stores'][0]['operations'][0]['id'])
            # A similar title must not erase an incompatible condition or a version-specific fact.
            distinct={**policy,'conditions':'Damaged-on-arrival items only, at most 7 days.',
                      'exceptions':'No refund after day 7.','content':('Separate damaged-item policy: only damaged arrivals within 7 days. ReturnPolicyV2 only. manual_review blocks automatic approval unless supervisor_override=true. '*20),
                      'source':{'type':'user_confirmation','excerpt':'Synthetic: damaged arrivals within 7 days, ReturnPolicyV2 only; manual_review blocks automatic approval unless supervisor_override=true.'}}
            result=store.apply_payload({'schema_version':1,'scope':'project','session_id':'synthetic-seed','turn_id':'distinct',
                'idempotency_key':'distinct','operations':[{'op':'ADD','record':distinct}]},project_root=project)
            distinct_id=result['stores'][0]['operations'][0]['id']
            source_count_before=sum(len(store.show_record('project',i,project_root=project)['evidence']) for i in [*seed_ids,distinct_id])
            def run(label,prompt):
                assert source_hashes()==frozen, 'Runtime changed during evaluation.'
                print('Starting '+label,flush=True)
                cmd=[codex,'exec','--json','--ephemeral','--ignore-user-config','--ignore-rules','--skip-git-repo-check',
                     '--sandbox','workspace-write','--model',args.model,'--config',f'model_reasoning_effort="{args.reasoning}"',
                     '--add-dir',str(home),prompt]
                started=time.monotonic(); first=None; events=[]
                with subprocess.Popen(cmd,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as process:
                    # Whole-run timeout is external and bounded. No hidden model retries.
                    try:
                        stdout,stderr=process.communicate(timeout=240)
                    except subprocess.TimeoutExpired:
                        process.kill();stdout,stderr=process.communicate();raise RuntimeError('Model timeout: '+label)
                for line in stdout.splitlines():
                    try: events.append(json.loads(line))
                    except ValueError: pass
                commands=[e['item'].get('command','') for e in events if e.get('type')=='item.completed'
                          and isinstance(e.get('item'),dict) and e['item'].get('type')=='command_execution']
                (output.parent/f'maintenance-{label}.jsonl').write_text(stdout)
                (output.parent/f'maintenance-{label}.stderr').write_text(stderr)
                result={'label':label,'exit_code':process.returncode,'seconds':round(time.monotonic()-started,3),
                        'tool_calls':len(commands),'usage':next((e.get('usage') for e in reversed(events) if e.get('usage')),None),
                        'first_effective_action_seconds':None,'first_action_note':'Not sampled by this E2E runner; use matched A/B benchmark for timing.',
                        'maintenance_operations_observed':observed_maintenance(events),
                        'final':next((e['item'].get('text') for e in reversed(events) if e.get('item',{}).get('type')=='agent_message'),None)}
                report['runs'].append(result);print(json.dumps({k:v for k,v in result.items() if k!='final'}),flush=True)
                assert process.returncode==0,'Host failed: '+label
                return result
            initial=run('ordinary-task','检查 policy.py 的退货判断，结合现有项目规则说明缺什么条件。今天停在准备阶段，不修改业务代码。')
            active=store.list_records('project',project_root=project)['records']
            policy_active=[r for r in active if r['kind']=='business_rule' and store.show_record('project',r['id'],project_root=project)['record']['conditions']==policy['conditions']]
            assert len(policy_active)==1,'Historical duplicate rules were not merged automatically.'
            canonical=store.show_record('project',policy_active[0]['id'],project_root=project)
            assert len(canonical['record']['content'])<500,'Long canonical body was not shortened.'
            assert initial['maintenance_operations_observed']['COMPACT'],'No successful COMPACT receipt observed.'
            assert initial['maintenance_operations_observed']['MERGE_DUPLICATES'],'No successful merge receipt observed.'
            distinct_after=store.show_record('project',distinct_id,project_root=project)['record']
            assert distinct_after['status']=='active','Incompatible rule was retired.'
            assert len(distinct_after['content'])<500,'Independent long body was not compacted.'
            assert all(term in distinct_after['content'] for term in ('ReturnPolicyV2','manual_review','supervisor_override')), 'Lost a prose-only version or condition.'
            assert 'unless' in distinct_after['content'].casefold() or '除非' in distinct_after['content'], 'Lost the prose-only exception.'
            for field in ('conditions','exceptions','dont','do','verification_steps'):
                assert distinct_after[field]==distinct[field],'Compaction lost a restriction: '+field
            for field in ('conditions','exceptions','do','dont','verification_steps','claim_type','strength'):
                assert canonical['record'][field]==policy[field], 'Lost protected field: '+field
            source_count_after=sum(len(store.show_record('project',i,project_root=project)['evidence']) for i in [*seed_ids,distinct_id])
            assert source_count_after==source_count_before,'Maintenance invented evidence.'
            assert (project/'policy.py').read_text().endswith('    return days <= 30\n'),'Preparation changed code.'
            repeat=run('paraphrase','本项目正常退货仍要求已签收、未拆封、签收后不超过14天，礼品单与最终销售商品都不允许退。只确认现有 policy.py 需要修改的地方，暂不改业务代码。')
            active=store.list_records('project',project_root=project)['records']
            rules=[r for r in active if r['kind']=='business_rule']
            assert len(rules)==2,'Paraphrase added a duplicate business rule.'
            assert store.list_records('project',project_root=other)['records']==[],'A leaked into B.'
            assert store.list_records('global',global_root=global_root)['records']==[],'Project rules leaked into global.'
            report['reviewed_compacted_bodies']={'normal_policy':canonical['record']['content'],'damaged_policy':distinct_after['content']}
            report.update(status='passed',checks={'automatic_historical_duplicate_merge':True,'long_body_compaction':True,
                 'incompatible_condition_preserved':True,'all_protected_fields_preserved':True,'no_maintenance_evidence_inflation':True,'prose_only_version_condition_exception_preserved':True,
                 'fresh_session_paraphrase_no_new_rule':True,'no_business_code_edits':True,'scope_isolation':True},
                 limitations=['Two ordinary-prompt Codex CLI sessions; not proof of every-turn enforcement or all-host reliability.',
                              'Model semantic judgment is sampled, not exhaustive; no new matched on/off latency comparison.',
                              'Audit history remains stored; no automatic disk-size cap.'])
    except Exception as exc:
        report.update(status='failed',failure=f'{type(exc).__name__}: {exc}')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':report.get('checks',{}),'failure':report.get('failure')}),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())

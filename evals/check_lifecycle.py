"""Explicit real Codex development-cycle evaluation with isolated synthetic projects."""
from __future__ import annotations
import argparse
import ast
import contextlib
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/dev-memory/scripts'))
from dev_memory import SKILL_FILES, PACKAGE_ROOT, _release_version
import dev_memory_store as store
from check_maintenance import observed_usage

DESIGN='''Create a synthetic refund approval project. This turn finish requirements, SQLite schema and an API draft only; do not implement the application yet.
Confirmed policy: delivered and unopened orders within 30 days after delivery, excluding gift and final-sale orders. Refund the full paid amount only; no partial refunds. Amounts are integer cents, never floats/dollars. Enforce integer/nonnegative amounts in SQLite.
Tenant identity is represented by X-Tenant in this local test fixture, not production authentication. Orders are identified within their tenant. One approved refund per tenant/order. Idempotency is tenant plus key: same key/order returns the original result, same key with another order gives 409; a new key for an already refunded order gives 409. Never disclose another tenant's order. Use uppercase APPROVED.
Create SPEC.md, schema.sql and api.md. Tables: orders(tenant_id,id,paid_cents,delivered,unopened,days_since_delivery,gift,final_sale), refunds(tenant_id,id,order_id,idempotency_key,amount_cents,status); order primary key is (tenant_id,id), both refund key and order are unique within tenant. Boolean fixture fields are 0/1; delivery-age fixture is a nonnegative integer. POST /api/v1/refunds takes order_id and idempotency_key. Return JSON including refund_id, order_id, amount_cents, status: 201 new, 200 replay, 409 conflict, 422 ineligible, 404 absent/other-tenant order. No real customer data or production security claims. State what is designed and still unfinished.
One development communication preference explicitly applies to all my projects: report the result first, then remaining work.'''
IMPLEMENT='''Continue this project. Correction: refund eligibility is now at most 14 days after delivery, inclusive; replace the previous 30-day requirement. All other exclusions, tenant boundaries, cents, uppercase status and idempotency semantics remain unchanged.
Finalize the API contract and implement backend.py plus frontend.mjs. Backend starts with python3 backend.py --db PATH --port PORT and binds 127.0.0.1. Apply schema.sql to an empty database on startup if necessary. Frontend exports async requestRefund(baseUrl,tenantId,orderId,key), calls the endpoint with X-Tenant and returns the JSON object on success; fail clearly on non-2xx. This is a local HTTP fixture, not a production app. Add Python and Node built-in tests and actually run backend/frontend integration. Update SPEC.md/api.md and report verified versus untested behavior. Do not add dependencies.'''
FIX='''Continue testing and fixing this project. An independent integration check found that a normal delivered, unopened order at delivery age 15 was approved. The required boundary remains 14 inclusive; gifts/final-sale stay excluded. Inspect the current code, fix the cause and add regression coverage. Re-run Python and frontend/HTTP tests, including 14/15 boundary, every exclusion, tenant-isolated replay, key conflict and integer cents. Preserve the other API semantics. Report actual results and any remaining gaps.'''
SWITCH='''Implement cancel_allowed(age_hours) in cancel.py for this project's separate cancellation policy: cancellation is allowed from 0 through 2 hours inclusive, and prohibited afterward. Add and run unit tests. This task has no refund policy. Do not inspect another project.'''


def source_hashes():
    return {n:hashlib.sha256((ROOT/'skills/dev-memory'/n).read_bytes()).hexdigest() for n in SKILL_FILES}


def run_model(codex, model, reasoning, project, home, env, label, prompt, output, timeout):
    argv=[codex,'exec','--json','--ephemeral','--ignore-user-config','--ignore-rules','--skip-git-repo-check',
          '--sandbox','workspace-write','--config','sandbox_workspace_write.network_access=true',
          '--model',model,'--config',f'model_reasoning_effort="{reasoning}"','--add-dir',str(home),prompt]
    print('Starting '+label,flush=True)
    started=time.monotonic();events=[];timed_out=False
    log=output.parent/f'lifecycle-{label}.jsonl'
    # File-backed output avoids pipe deadlocks when a tool inherits the host's handles.
    with log.open('w',encoding='utf-8') as stdout, (output.parent/f'lifecycle-{label}.stderr').open('w',encoding='utf-8') as stderr:
        with subprocess.Popen(argv,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr) as process:
            try:process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True;process.kill();process.communicate()
    elapsed=round(time.monotonic()-started,3)
    for line in log.read_text(encoding='utf-8').splitlines():
        try:event=json.loads(line)
        except ValueError:continue
        if isinstance(event,dict):events.append(event)
    commands=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='command_execution']
    result={'label':label,'exit_code':process.returncode,'timed_out':timed_out,'seconds':elapsed,
            'first_tool_action_seconds':None,'timing_note':'Buffered logs do not measure first tool receipt time','command_calls':len(commands),
            'tool_calls':sum(e.get('type')=='item.started' and e.get('item',{}).get('type') in {'command_execution','mcp_tool_call','file_change'} for e in events),
            'usage':next((e['usage'] for e in reversed(events) if e.get('usage')),None),
            'memory_use_reported_ids':observed_usage(events),
            'host_errors':[e for e in events if e.get('type') in {'error','turn.failed'}]}
    print(json.dumps(result),flush=True)
    return result,commands


def project_capture_checks(project, days=None):
    """Check durable sourced policy; ordinary work must not produce task memories."""
    records=store.list_records('project',project_root=project,status='all',limit=200)['records']
    assert len(records)<200,'Synthetic capture inspection reached its record limit.'
    assert not any(r['scope']=='task' or r['kind']=='checkpoint' for r in records),'Ordinary workflow captured task memory/checkpoints.'
    history=[store.show_record('project',r['id'],project_root=project) for r in records if r['status']=='active']
    details=[d['record'] for d in history]
    rules=[r for r in details if r['kind'] in {'business_rule','decision'} and r['claim_type']=='desired']
    sourced_rules=[d['record'] for d in history if d['record'] in rules
                   and any(e['source_type'] in store.USER_SOURCES for e in d['evidence'])]
    if days is not None:
        assert any(re.search(r'(?<!\d)'+str(days)+r'(?!\d)', ' '.join(r.get(k,'') for k in ('title','content','conditions','exceptions','do','dont')))
                   for r in sourced_rules),f'{days}-day business requirement was not captured as a sourced desired rule.'
    if days==14:
        assert not any('30 days' in r['conditions'] or '30-day' in r['conditions'] for r in rules),'Old operative condition remained active.'
    observations=0;verified=0
    for detail in history:
        record=detail['record'];verification=record.get('verification')
        has_tool_source=any(e['source_type']=='tool_result' for e in detail['evidence'])
        observations+=record['claim_type']=='observed' and has_tool_source
        if verification:
            assert has_tool_source,'Verification lacks tool-result evidence.'
            assert all(isinstance(verification.get(k),str) and verification[k].strip() for k in ('command','finished_at','code_version')), 'Verification lacks command/time/code version.'
            assert type(verification.get('exit_code')) is int and verification['exit_code']==0,'Verification lacks successful exit code.'
            verified+=1
    return {'project_global_only_capture':True,'structured_verification_records':verified,
            'actual_tool_result_observations':observations,
            'record_kinds':{k:sum(r['kind']==k for r in details) for k in {r['kind'] for r in details}}}


def independent_integration(project, home):
    """Actual SQLite + loopback HTTP + Node client checks, independent of generated tests."""
    db=home/'probe.sqlite3';db.unlink(missing_ok=True)
    with contextlib.closing(sqlite3.connect(db)) as c:
        c.executescript((project/'schema.sql').read_text())
        values=[('eligible',14,1,1,0,0),('late',15,1,1,0,0),('gift',14,1,1,1,0),
                ('final',14,1,1,0,1),('undelivered',14,0,1,0,0),('opened',14,1,0,0,0)]
        for tenant in ['blue','green']:
            for oid,days,delivered,unopened,gift,final in values:
                c.execute('INSERT INTO orders(tenant_id,id,paid_cents,delivered,unopened,days_since_delivery,gift,final_sale) VALUES(?,?,?,?,?,?,?,?)',
                          (tenant,oid,1499,delivered,unopened,days,gift,final))
        for bad in [-1,1.25]:
            try:c.execute('INSERT INTO orders(tenant_id,id,paid_cents,delivered,unopened,days_since_delivery,gift,final_sale) VALUES(?,?,?,?,?,?,?,?)',('bad',str(bad),bad,1,1,0,0,0))
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('SQLite accepted noninteger/negative cents.')
        c.commit()
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    server=subprocess.Popen([sys.executable,'backend.py','--db',str(db),'--port',str(port)],cwd=project,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+8
        while True:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if server.poll() is not None or time.monotonic()>deadline:raise AssertionError('Backend did not start.')
                time.sleep(.05)
        def post(tenant,oid,key):
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
            conn.request('POST','/api/v1/refunds',json.dumps({'order_id':oid,'idempotency_key':key}),{'Content-Type':'application/json','X-Tenant':tenant})
            response=conn.getresponse();value=json.loads(response.read());status=response.status;conn.close();return status,value
        checks={}
        status,original=post('blue','eligible','same');assert status==201,(status,original)
        assert original['amount_cents']==1499 and type(original['amount_cents']) is int and original['status']=='APPROVED',original
        checks['integer_cents_uppercase_status']=True
        status,replay=post('blue','eligible','same');assert status==200 and replay==original,(status,replay)
        checks['idempotent_replay']=True
        assert post('blue','eligible','new-key')[0]==409;checks['already_refunded_order_conflict']=True
        status,other=post('green','eligible','same');assert status==201,(status,other)
        checks['tenant_isolated_keys']=True
        assert post('blue','late','same')[0]==409;checks['key_conflict']=True
        for oid in ['late','gift','final','undelivered','opened']:
            status,body=post('blue',oid,'key-'+oid);assert status==422,(oid,status,body)
        checks['boundary_and_all_exclusions']=True
        assert post('unknown','eligible','missing')[0]==404;checks['no_cross_tenant_order_leak']=True
        client=f"import {{requestRefund}} from './frontend.mjs';const x=await requestRefund('http://127.0.0.1:{port}','blue','eligible','same');if(x.status!=='APPROVED'||x.amount_cents!==1499)throw Error('Client contract mismatch');"
        client+=f"let rejected=false;try{{await requestRefund('http://127.0.0.1:{port}','blue','late','client-late')}}catch(e){{rejected=true}}if(!rejected)throw Error('Client accepted non-2xx');"
        node=subprocess.run(['node','--input-type=module','-e',client],cwd=project,capture_output=True,text=True,timeout=15)
        assert node.returncode==0,'Frontend request failed: '+node.stderr[-1000:]
        checks['actual_frontend_backend_http']=True
        checks['frontend_rejects_non_2xx']=True
        return checks
    finally:
        server.terminate()
        try:server.wait(timeout=3)
        except subprocess.TimeoutExpired:server.kill();server.wait()


def program_scale_probe():
    """Bulk synthetic fixture seeding, then bounded program operations; no model claims."""
    result={'synthetic_only':True,'model_invoked':False,'repetitions':10,'cells':[]}
    with tempfile.TemporaryDirectory(prefix='dev-memory-scale-') as td:
        home=Path(td);project=home/'project';project.mkdir();global_root=home/'global-root'
        store.init_global(global_root);store.init_project(project)
        _,db,config=store._config_for('project',project,global_root)
        count=0
        for target in (1000,10000):
            with contextlib.closing(store._connect(db)) as conn:
                for n in range(count,target):
                    record=store._validate_record({'kind':'business_rule','claim_type':'desired','strength':'soft',
                        'title':f'Synthetic shard{n} contract','content':f'Synthetic topic shard{n} requires integer cents; forbidden negative values.',
                        'tags':['synthetic-topic',f'shard{n}'],'source':{'type':'user_confirmation','excerpt':'Synthetic fixture, not a real user memory.'}},'project',None,config['namespace_id'])
                    mid,_=store._store_record(conn,record);store._queue_maintenance(conn,mid)
                conn.commit()
            count=target
            cell={'active_records':count,'operations':{}}
            for label, operation in [('narrow_recall',lambda:store.recall(f'shard{target-1}',project_root=project,global_root=global_root,force=True,readonly=True)),
                                     ('saturated_recall',lambda:store.recall('synthetic topic',project_root=project,global_root=global_root,force=True,readonly=True)),
                                     ('pending_maintenance',lambda:store.maintenance_prepare('project',project_root=project,global_root=global_root))]:
                times=[]
                for _ in range(10):
                    start=time.perf_counter();reply=operation();times.append((time.perf_counter()-start)*1000)
                bucket=reply['stores'][1] if 'stores' in reply else reply
                cell['operations'][label]={'median_ms':round(statistics.median(times),3),'max_ms':round(max(times),3),
                    'status':bucket['status'],'records_returned':len(bucket.get('records',[])),
                    'context_incomplete':bucket.get('context_incomplete',False),'candidate_limit_reached':bucket.get('candidate_limit_reached',False)}
                if label=='narrow_recall':assert len(bucket.get('records',[]))==1,'Narrow topic was not retrieved.'
                if label=='saturated_recall':assert bucket.get('context_incomplete'),'Saturated query falsely complete.'
                if label=='pending_maintenance':assert len(bucket.get('records',[]))<=8,'Unbounded maintenance.'
            result['cells'].append(cell)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model');p.add_argument('--reasoning');p.add_argument('--program-only',action='store_true');p.add_argument('--timeout-seconds',type=int,default=360)
    p.add_argument('--design-only',action='store_true',help='Fail fast on first-turn sourced requirement/global preference capture without task memories')
    a=p.parse_args();output=a.output.expanduser().resolve()
    if output.is_relative_to(ROOT):p.error('Keep synthetic transcripts outside the repository.')
    output.parent.mkdir(parents=True,exist_ok=True)
    version=_release_version(PACKAGE_ROOT)
    assert version is not None,'Runtime release version unavailable.'
    runtime_version='.'.join(map(str,version))
    if a.program_only:
        report={'status':'passed','runtime_version':runtime_version,'runtime_source_sha256':source_hashes(),'program_scale':program_scale_probe()}
        output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0
    if not a.model or not a.reasoning:p.error('--model and --reasoning are required for real-host evaluation.')
    codex=shutil.which('codex');assert codex and shutil.which('node'),'Codex and Node required for explicit evaluation.'
    frozen=source_hashes()
    report={'status':'running','runtime_version':runtime_version,'host':subprocess.check_output([codex,'--version'],text=True).strip(),
            'model':a.model,'reasoning':a.reasoning,'runtime_source_sha256':frozen,'synthetic_only':True,'hooks_configured':False,
            'ordinary_prompts_without_skill_invocation':True,'runs':[],'checks':{},'limitations':[
            'One synthetic project cycle over fresh Codex CLI sessions; not exhaustive semantic validation or other-host enforcement.',
            'Timeout kills and reaps the host process; independently spawned descendants are not recursively terminated.',
            'Loopback networking is explicitly allowed for the local fixture; not proof of production authentication/security.',
            'Independent behavior checks do not prove negligible whole-workflow overhead; matched benchmark is separate.']}
    try:
        with tempfile.TemporaryDirectory(prefix='dev-memory-cycle-') as td:
            home=Path(td).resolve();project=home/'project-a';other=home/'project-b';project.mkdir();other.mkdir();ch=home/'.codex';ch.mkdir()
            auth=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
            if auth.is_file():shutil.copyfile(auth,ch/'auth.json');os.chmod(ch/'auth.json',0o600)
            env={**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(ch),'DEV_MEMORY_HOME':str(home/'.dev-memory'),'PYTHONDONTWRITEBYTECODE':'1'}
            env.pop('CODEX_DISABLE_PROJECT_DOCS',None)
            for directory in [project,other]:
                subprocess.run(['git','init','-q',str(directory)],check=True,env=env)
                r=subprocess.run([sys.executable,str(ROOT/'install.py'),'codex','--project',str(directory),'--json'],cwd=home,env=env,capture_output=True,text=True,timeout=30)
                assert r.returncode==0,r.stdout+r.stderr
            def run(label,directory,prompt):
                assert source_hashes()==frozen,'Runtime changed during the evaluation.'
                result,commands=run_model(codex,a.model,a.reasoning,directory,home,env,label,prompt,output,a.timeout_seconds)
                report['runs'].append(result);output.write_text(json.dumps(report,indent=2)+'\n')
                assert result['exit_code']==0 and not result['timed_out'],'Host did not complete '+label
                return commands
            run('requirements-schema-api-draft',project,DESIGN)
            for name in ['SPEC.md','schema.sql','api.md']:assert (project/name).is_file(),name
            assert not (project/'backend.py').exists(),'Implemented before authorization.'
            report['checks']['requirements_schema_api_artifacts']=True
            report['checks']['first_turn_capture']=project_capture_checks(project,30)
            assert store.list_records('global',global_root=home/'.dev-memory')['records'], 'Explicit cross-project preference missing.'
            report['checks']['first_turn_requirement_preference_captured']=True
            if a.design_only:
                report['status']='passed'
                output.write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps({'status':report['status'],'checks':report['checks']}),flush=True)
                return 0
            run('correction-code-frontend-integration',project,IMPLEMENT)
            report['checks']['implementation_capture']=project_capture_checks(project,14)
            report['checks']['independent_before_bug']=independent_integration(project,home)
            backend=project/'backend.py';tree=ast.parse(backend.read_text());changed=0
            class BoundaryBug(ast.NodeTransformer):
                def visit_Constant(self,node):
                    nonlocal changed
                    if type(node.value) is int and node.value==14:changed+=1;return ast.copy_location(ast.Constant(15),node)
                    return node
            tree=BoundaryBug().visit(tree);assert changed,'No 14 boundary found for explicit fault injection.'
            backend.write_text(ast.unparse(tree)+'\n')
            try:independent_integration(project,home)
            except AssertionError as exc:
                report['checks']['injected_bug_detected']=str(exc)
            else:raise AssertionError('The injected boundary defect was not detected.')
            run('testing-regression-bugfix',project,FIX)
            report['checks']['independent_after_fix']=independent_integration(project,home)
            report['checks']['corrected_policy_capture']=project_capture_checks(project,14)
            report['checks']['semantic_review_note']='Historical superseded-rule annotations may remain in current prose; manually distinguish them from operative conditions.'
            commands=run('project-switch',other,SWITCH)
            subprocess.run([sys.executable,'-c',"from cancel import cancel_allowed;assert cancel_allowed(0);assert cancel_allowed(2);assert not cancel_allowed(3)"],cwd=other,check=True,env=env)
            report['checks']['project_switch_capture']=project_capture_checks(other)
            b=store.list_records('project',project_root=other)['records']
            assert not any('final_sale' in store.show_record('project',r['id'],project_root=other)['record']['content'] for r in b),'Project A leaked into B.'
            global_records=store.list_records('global',global_root=home/'.dev-memory')['records']
            assert global_records and all(r['kind'] in {'preference','convention'} for r in global_records),'Global scope incorrect.'
            report['checks']['project_switch_and_global_scope']=True
            assert source_hashes()==frozen,'Source changed during evaluation.'
            report['status']='passed'
    except Exception as exc:
        report['status']='failed';report['failure']=f'{type(exc).__name__}: {exc}'
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'checks':report['checks']}),flush=True)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())

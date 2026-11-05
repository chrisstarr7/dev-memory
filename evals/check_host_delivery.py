"""Real Codex startup/resume/compaction acceptance; opt-in, isolated and stdlib-only."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

from check_lifecycle import ROOT, source_hashes, store
import dev_memory_setup as setup


class CodexServer:
    """Small test-only stdio client for the installed app-server protocol."""
    def __init__(self, codex, project, env, output, label, timeout):
        self.argv = [codex, 'app-server', '--stdio']
        self.project, self.env, self.timeout = project, env, timeout
        self.log = (output.parent/(label+'.jsonl')).open('w', encoding='utf-8')
        self.stderr = (output.parent/(label+'.stderr')).open('w', encoding='utf-8')
        self.events, self.serial = [], 0
        self.process = None

    async def __aenter__(self):
        try:
            self.process = await asyncio.create_subprocess_exec(*self.argv, cwd=self.project, env=self.env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self.stderr, limit=4_000_000)
            await self.request('initialize', {'clientInfo':{'name':'dev_memory_acceptance','version':'1.0'}})
            await self.send({'method':'initialized'})
        except BaseException:
            await self.__aexit__()
            raise
        return self

    async def __aexit__(self, *_):
        if self.process is not None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                if self.process.returncode is None:
                    self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except asyncio.TimeoutError:
                    if self.process.returncode is None:
                        self.process.kill()
                    await self.process.wait()
        self.log.close()
        self.stderr.close()

    async def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False)+'\n').encode())
        await self.process.stdin.drain()

    async def receive(self, deadline):
        raw = await asyncio.wait_for(self.process.stdout.readline(), max(.001, deadline-time.monotonic()))
        if not raw:
            raise RuntimeError('App-server ended before the requested lifecycle completed.')
        event = json.loads(raw)
        self.log.write(json.dumps(event, ensure_ascii=False)+'\n')
        self.log.flush()
        self.events.append(event)
        if 'method' in event and 'id' in event:
            # No implicit approval of unexpected tool/auth requests in the test harness.
            await self.send({'id':event['id'], 'error':{'code':-32601,'message':'Unsupported acceptance request'}})
            raise RuntimeError('Unexpected server request: '+event['method'])
        return event

    async def request(self, method, params):
        self.serial += 1
        serial = self.serial
        await self.send({'id':serial, 'method':method, 'params':params})
        deadline = time.monotonic()+self.timeout
        while True:
            event = await self.receive(deadline)
            if event.get('id') == serial and 'method' not in event:
                if 'error' in event:
                    raise RuntimeError(method+': '+str(event['error']))
                return event['result']

    async def completed(self, thread_id, offset):
        deadline = time.monotonic()+self.timeout
        while True:
            for event in self.events[offset:]:
                params = event.get('params', {})
                if event.get('method') == 'turn/completed' and params.get('threadId') == thread_id:
                    if params['turn']['status'] != 'completed':
                        raise RuntimeError('Host turn failed: '+str(params['turn'].get('error')))
                    return self.events[offset:]
            offset = len(self.events)
            await self.receive(deadline)

    async def turn(self, thread_id, prompt, model, reasoning, home):
        offset = len(self.events)
        started = time.monotonic()
        await self.request('turn/start', {'threadId':thread_id, 'input':[{'type':'text','text':prompt}],
            'model':model, 'effort':reasoning, 'approvalPolicy':'never',
            'sandboxPolicy':{'type':'workspaceWrite', 'writableRoots':[str(home)], 'networkAccess':False}})
        await self.completed(thread_id, offset)
        return self.events[offset:], round(time.monotonic()-started, 3)


def context_bodies(events):
    """Count actual successful CLI outputs, never assistant claims or a cached empty result."""
    bodies, forced = {}, set()
    for event in events:
        if event.get('method') != 'item/completed':
            continue
        item = event.get('params', {}).get('item', {})
        command = item.get('command', '')
        if item.get('type') != 'commandExecution' or item.get('exitCode') != 0:
            continue
        normalized = command.lower().replace('\\', '/')
        resolved_cli = '.dev-memory/activation.json' in normalized and 'bindings.codex.cli' in normalized
        if ('dev_memory.py' not in normalized and not resolved_cli) or ' context ' not in ' '+normalized+' ':
            continue
        for line in (item.get('aggregatedOutput') or '').splitlines():
            try:
                result = json.loads(line)
            except ValueError:
                continue
            if not isinstance(result, dict):
                continue
            for bucket in result.get('stores', []):
                for record in bucket.get('records', []):
                    bodies[record['id']] = record
                    if '--force' in command:
                        forced.add(record['id'])
    return bodies, forced


def seed_or_revise(project, global_root, marker, memory_id=None):
    rule = {'kind':'convention','claim_type':'desired','status':'active','strength':'hard',
            'title':'文本回执格式','content':f'write_receipt(text) 在 artifacts/receipt.txt 输出 UTF-8 文本，精确格式为 {marker}|文本内容，然后一个换行。',
            'conditions':'实现或修改 receipt.py 的文本回执功能时。', 'do':'保持固定格式，使用 Python 标准库。',
            'dont':'不得增加导入功能或第三方依赖。', 'tags':['implementation','receipt'],
            'source':{'type':'user_statement','excerpt':'本项目文本回执使用已确认的固定标记、分隔符和单个末尾换行。'}}
    op = {'op':'REVISE','id':memory_id,'expected_revision':store.show_record('project',memory_id,
          project_root=project,global_root=global_root)['record']['revision'],'record':rule} if memory_id else {'op':'ADD','record':rule}
    result = store.apply_payload({'schema_version':1,'scope':'project','session_id':'synthetic-seed',
        'turn_id':marker,'idempotency_key':marker,'operations':[op]}, project_root=project,
        global_root=global_root, schedule_vectors=False)
    assert result['status'] == 'saved', result
    return result['stores'][0]['operations'][0]['id']


def artifact_matches(project, marker, text, env):
    """Execute the implementation ourselves, independently of model-generated tests."""
    target = project/'artifacts/receipt.txt'
    target.unlink(missing_ok=True)
    checked = subprocess.run([sys.executable,'-B','-c','import receipt; receipt.write_receipt('+repr(text)+')'],
        cwd=project, env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    return checked.returncode == 0 and target.is_file() and target.read_bytes() == (marker+'|'+text+'\n').encode('utf-8')


async def evaluate(args, report):
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI with app-server is required.')
    auth = Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    report.update(host=subprocess.check_output([codex,'--version'],text=True).strip(),
                  runtime_source_sha256=source_hashes())
    with tempfile.TemporaryDirectory(prefix='dev-memory host acceptance ') as td:
        root = Path(td).resolve()
        home, project = root/'home', root/'project'
        ch = home/'.codex'
        ch.mkdir(parents=True, mode=0o700)
        if auth.is_file():
            shutil.copyfile(auth,ch/'auth.json')
            (ch/'auth.json').chmod(0o600)
        skill = home/'.agents/skills/dev-memory'
        shutil.copytree(ROOT/'skills/dev-memory',skill,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        project.mkdir()
        subprocess.run(['git','init','-q',str(project)],check=True)
        global_root = home/'.dev-memory'
        setup.setup(project,'codex',skill,sys.executable,global_root)
        guide = (project/'AGENTS.md').read_bytes()
        env = {**os.environ,'HOME':str(home),'USERPROFILE':str(home),'CODEX_HOME':str(ch),
               'DEV_MEMORY_HOME':str(global_root),'PYTHONDONTWRITEBYTECODE':'1','DEV_MEMORY_VECTOR_SETUP':'0'}
        for key in ('CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_DISABLE_PROJECT_DOCS'):
            env.pop(key,None)
        (ch/'config.toml').write_text('model = '+json.dumps(args.model)+'\n[analytics]\nenabled = false\n',encoding='utf-8')
        global_rule = {'kind':'preference','claim_type':'preference','status':'active','strength':'soft',
            'cross_project_confirmed':True,'title':'文本输出习惯','content':'本地文本输出使用 UTF-8，优先 Python 标准库。',
            'source':{'type':'user_confirmation','excerpt':'这个文本输出习惯长期适用于所有项目。'}}
        saved = store.apply_payload({'schema_version':1,'scope':'global','session_id':'synthetic-seed',
            'turn_id':'global','idempotency_key':'global','operations':[{'op':'ADD','record':global_rule}]},
            global_root=global_root,schedule_vectors=False)
        global_id = saved['stores'][0]['operations'][0]['id']
        marker = secrets.token_hex(8)
        memory_id = seed_or_revise(project,global_root,marker)
        (project/'receipt.py').write_text('"""Synthetic receipt utility."""\n',encoding='utf-8')

        async def run_phase(server, thread_id, label, marker, revision):
            prompt = '实现 receipt.py 的 write_receipt(text)，用 Python 标准库写入文本回执，输出内容为“'+label+'检查”，并实际运行验证。'
            print('Starting host '+label,flush=True)
            events, seconds = await server.turn(thread_id,prompt,args.model,args.reasoning,home)
            bodies, forced = context_bodies(events)
            checks = {'global_body_received':global_id in bodies,
                      'current_project_revision_received':bodies.get(memory_id,{}).get('revision') == revision,
                      'force_recall_received_body':memory_id in forced,
                      'artifact_follows_unseen_marker':artifact_matches(project,marker,label+'检查',env),
                      'guide_unchanged':(project/'AGENTS.md').read_bytes() == guide}
            row = {'phase':label,'seconds':seconds,'thread_id':thread_id,'checks':checks,
                   'delivered_ids':list(bodies),'expected_revision':revision,'expected_marker':marker}
            report['runs'].append(row)
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            assert all(checks.values()), row
            print(json.dumps(row,ensure_ascii=False),flush=True)

        options = {'model':args.model,'cwd':str(project),'approvalPolicy':'never','sandbox':'workspace-write'}
        async with CodexServer(codex,project,env,args.output,'startup',args.timeout_seconds) as server:
            started = await server.request('thread/start',options)
            thread_id = started['thread']['id']
            report['instruction_sources'] = started.get('instructionSources',[])
            await run_phase(server,thread_id,'startup',marker,1)
        marker = secrets.token_hex(8)
        seed_or_revise(project,global_root,marker,memory_id)
        (project/'receipt.py').write_text('"""Synthetic receipt utility."""\n',encoding='utf-8')
        async with CodexServer(codex,project,env,args.output,'resumed',args.timeout_seconds) as server:
            await server.request('thread/resume',{'threadId':thread_id,'excludeTurns':True,**options})
            await run_phase(server,thread_id,'resume',marker,2)
            marker = secrets.token_hex(8)
            seed_or_revise(project,global_root,marker,memory_id)
            (project/'receipt.py').write_text('"""Synthetic receipt utility."""\n',encoding='utf-8')
            offset = len(server.events)
            await server.request('thread/compact/start',{'threadId':thread_id})
            await server.completed(thread_id,offset)
            report['real_compaction_observed'] = any(e.get('method') == 'item/completed' and
                e.get('params',{}).get('item',{}).get('type') == 'contextCompaction' for e in server.events[offset:])
            assert report['real_compaction_observed'], 'No real contextCompaction completion was observed.'
            await run_phase(server,thread_id,'compact',marker,3)
    assert source_hashes() == report['runtime_source_sha256'], 'Runtime source changed during the evaluation.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--reasoning',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=240)
    args = parser.parse_args()
    args.output = args.output.expanduser().resolve()
    if args.output.is_relative_to(ROOT) or args.timeout_seconds < 1:
        parser.error('Keep reports outside the repository and use a positive timeout.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report = {'status':'running','synthetic_only':True,'model':args.model,'reasoning':args.reasoning,
              'hooks_configured':False,'prompts_mention_memory':False,'runs':[],
              'limitations':['Named Codex app-server/model sample, not all hosts or future tasks.',
                             'No hook trust bypass or automatic model/vector setup.',
                             'Scope controls and vector integration are checked separately.']}
    try:
        asyncio.run(evaluate(args,report))
        report['status'] = 'passed'
    except (AssertionError,OSError,RuntimeError,ValueError,KeyError,asyncio.TimeoutError) as exc:
        report.update(status='failed',error=str(exc))
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())

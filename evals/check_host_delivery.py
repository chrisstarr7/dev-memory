"""Real Codex lifecycle or capture collaboration acceptance in synthetic projects."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
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
    def __init__(self, codex, project, env, output, label, timeout, *, windows_sandbox=None):
        self.argv = [codex, 'app-server', '--stdio', '-c', 'sandbox_mode="workspace-write"']
        if windows_sandbox:
            self.argv += ['-c', 'windows.sandbox='+json.dumps(windows_sandbox)]
        self.project, self.env, self.timeout = project, env, timeout
        self.log = (output.parent/(label+'.jsonl')).open('w', encoding='utf-8')
        self.stderr = (output.parent/(label+'.stderr')).open('w', encoding='utf-8')
        self.events, self.serial = [], 0
        self.event_times = []
        self.on_event = None
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
        try:
            raw = await asyncio.wait_for(self.process.stdout.readline(), max(.001, deadline-time.monotonic()))
        except asyncio.TimeoutError as exc:
            last_error = next((event.get('params', {}).get('error', {}).get('message')
                               for event in reversed(self.events) if event.get('method') == 'error'), None)
            detail = f' Last host error: {last_error}.' if last_error else ''
            raise RuntimeError('Timed out waiting for Codex app-server events.'+detail) from exc
        if not raw:
            raise RuntimeError('App-server ended before the requested lifecycle completed.')
        event = json.loads(raw)
        self.log.write(json.dumps(event, ensure_ascii=False)+'\n')
        self.log.flush()
        self.events.append(event)
        self.event_times.append(time.monotonic())
        if 'method' in event and 'id' in event:
            # No implicit approval of unexpected tool/auth requests in the test harness.
            await self.send({'id':event['id'], 'error':{'code':-32601,'message':'Unsupported acceptance request'}})
            raise RuntimeError('Unexpected server request: '+event['method'])
        if self.on_event is not None:
            self.on_event(event)
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
            'cwd':str(self.project), 'sandboxPolicy':fixture_policy(self.project, home)})
        await self.completed(thread_id, offset)
        return self.events[offset:], round(time.monotonic()-started, 3)


def require_workspace(started):
    policy = started.get('sandbox', {})
    if policy.get('type') != 'workspaceWrite':
        raise RuntimeError(f'Host did not grant the isolated workspace-write sandbox: {policy!r}')


def fixture_policy(project, home):
    return {'type':'workspaceWrite', 'writableRoots':[str(project), str(home)], 'networkAccess':False,
            'excludeTmpdirEnvVar':True, 'excludeSlashTmp':True}


async def probe_fixture_access(server, project, home):
    marker = '.host-acceptance-write-probe'
    probe = await server.request('command/exec', {
        'command':[sys.executable, '-B', '-c',
                   'from pathlib import Path; assert Path("AGENTS.md").is_file(); '
                   'assert Path(".dev-memory/activation.json").is_file(); '
                   f'Path({marker!r}).write_text("ok", encoding="utf-8")'],
        'cwd':str(project), 'sandboxPolicy':fixture_policy(project, home), 'timeoutMs':10000})
    target = project/marker
    if probe.get('exitCode') != 0 or not target.is_file() or target.read_bytes() != b'ok':
        error = probe.get('stderr', '').strip().splitlines()
        raise RuntimeError('Host shell could not read and write the test project: '+
                           (error[-1][:300] if error else 'fixture write not observed'))
    target.unlink()


def completed_items(events, thread_id):
    return [(i, event['params']['item']) for i, event in enumerate(events)
            if event.get('method') == 'item/completed' and event['params'].get('threadId') == thread_id]


def capture_trace(events, thread_id, record_id):
    """Use parent tool receipts and real collaboration events, not agent messages."""
    spawn, joined, stopped, revoked, receipt, attempts = [], [], [], {}, [], 0
    proposals, late = {}, []
    starts = {event['params']['item']['id']:i for i, event in enumerate(events)
              if event.get('method') == 'item/started' and event['params'].get('threadId') == thread_id
              and event['params']['item'].get('id')}
    apply_starts = []
    items = completed_items(events, thread_id)
    for i, item in items:
        if item['type'] == 'collabAgentToolCall' and item.get('senderThreadId') == thread_id:
            if item.get('tool') == 'spawnAgent':
                spawn.append((i, item))
            if item.get('tool') == 'wait' and item.get('status') == 'completed':
                joined.extend((i, child) for child, state in item.get('agentsStates', {}).items()
                              if state.get('status') == 'completed' and isinstance(state.get('message'), str)
                              and state['message'].strip())
                for child, state in item.get('agentsStates', {}).items():
                    if state.get('status') == 'completed' and state.get('message'):
                        proposals.setdefault(child, []).append((i, state['message']))
            if item.get('tool') == 'closeAgent':
                for child in item.get('receiverThreadIds', []):
                    revoked.setdefault(child, starts.get(item.get('id'), i))
                if item.get('status') == 'completed':
                    stopped.extend((i, child) for child, state in item.get('agentsStates', {}).items()
                                   if state.get('status') == 'shutdown')
        command = item.get('command', '').lower()
        if (item['type'] != 'commandExecution' or not ('dev_memory.py' in command or 'bindings.codex.cli' in command)
                or ' apply ' not in ' '+command+' '):
            continue
        attempts += 1
        # 回执可能晚于评审返回；必须核对写入启动顺序，缺少启动事件不能证明通过。
        apply_starts.append(starts.get(item.get('id')))
        if record_id is None or item.get('exitCode') != 0:
            continue
        for line in (item.get('aggregatedOutput') or '').splitlines():
            try:
                result = json.loads(line)
            except ValueError:
                continue
            if not isinstance(result, dict):
                continue
            for scope in result.get('stores', []):
                if scope.get('scope') == 'project' and scope.get('status') == 'saved' and any(
                        op.get('id') == record_id and op.get('status') == 'saved'
                        for op in scope.get('operations', [])):
                    receipt.append(i)
    children = {child:i for i, item in spawn if item.get('status') == 'completed'
                for child in item.get('receiverThreadIds', [])}
    closures = {child:at for at, child in reversed(stopped) if child in children and children[child] < at}
    joins = [(at, children[child]) for at, child in joined if child in children and children[child] < at
             and (child not in revoked or at < revoked[child])]
    first_apply = min(apply_starts) if apply_starts and all(at is not None for at in apply_starts) else None
    joined_children = {child for at, child in joined if child in children and children[child] < at
                       and (child not in revoked or at < revoked[child])
                       and first_apply is not None and at < first_apply}
    late = [{'child':child, 'event':at} for child, messages in proposals.items()
            for at, _ in messages if child in revoked and at >= revoked[child]]
    stopped_children = {child for child, at in closures.items() if first_apply is not None and at < first_apply}
    settlements = joins + [(at, children[child]) for child, at in closures.items()]
    work = [i for i, item in items if
            (item['type'] == 'fileChange' and item.get('status') == 'completed'
             and any(Path(change['path']).name == 'math_fixture.py' for change in item.get('changes', [])))
            or (item['type'] == 'commandExecution' and item.get('exitCode') == 0
                and 'math_fixture.py' in item.get('command', ''))]
    return {'spawn_attempts':len(spawn), 'children':sorted(children), 'parent_apply_attempts':attempts,
            'parent_save_receipts':len(receipt),
            'joined_before_save':bool(receipt and children and set(children) == joined_children),
            'stopped_before_save':bool(receipt and children and set(children) == stopped_children),
            'settled_before_write':bool(receipt and children and set(children) <= joined_children | stopped_children),
            'first_apply_event':first_apply,
            'received_proposals':{child:[{'event':at,'message':message} for at,message in messages]
                                  for child,messages in proposals.items()},
            'late_proposals':late,
            'work_after_spawn':any(started < i < at for at, started in settlements for i in work)}


async def assessment_case(codex, project, home, env, global_root, args, report, case, label):
    # Only synthetic inputs. This fixture does not attest isolation of a user's real host.
    ch = home/'.codex'
    enabled = case in {'simple', 'delegated', 'paused'}
    config = ch/'config.toml'
    config.write_text(config.read_text(encoding='utf-8')+
        '\n[features]\napps = false\nplugins = false\n'+
        f'\n[agents]\nenabled = {str(enabled).lower()}\n', encoding='utf-8')
    roles = ch/'agents'
    roles.mkdir()
    (roles/'memory_reviewer.toml').write_text(
        'name = "memory_reviewer"\ndescription = "Synthetic proposal-only memory reviewer"\n'
        'developer_instructions = "Analyze only the supplied excerpts. No tools or further delegation."\n'
        '[features]\nshell_tool = false\napps = false\nplugins = false\nmemories = false\n'
        'request_permissions_tool = false\n'
        '[skills]\ninclude_instructions = false\n', encoding='utf-8')
    # Keep this opt-in test configuration outside the installed/generated guide.
    if args.behavior_probe:
        with (project/'AGENTS.md').open('a', encoding='utf-8') as guide:
            guide.write('\nFor this synthetic fixture only, the memory_reviewer role is available when agents '
                    'are enabled. This is a behavior probe with disposable stores: use the role to exercise '
                    'eligible complex proposals even if the host cannot attest full tool isolation. '
                    'Launch it with fresh context, pass only the allowed excerpts, and identify the role '
                    'explicitly. Complete the independent file task while it runs.\n')
    marker, override, private = (secrets.token_hex(6) for _ in range(3))
    rule = (f'For future work in this project, format_stamp() returns "{marker}" by default. '
            if case == 'simple' else
            f'Confirmed permanent rule for this project: format_stamp(mode, legacy=False) returns "{marker}" '
            f'by default and "{override}" only when mode is "audit" and legacy is false. '
            f'Legacy always uses the default, even for audit. Never put "{private}" in a durable record or '
            'share it with other agents; it is a temporary example value.')
    prompt = rule+' For the unrelated current task, create math_fixture.py with double(n) returning n*2. Do not implement format_stamp yet.'
    options = {'model':args.model,'cwd':str(project),'approvalPolicy':'never','sandbox':'workspace-write'}
    row = {'phase':label, 'case':case, 'checks':{}, 'semantic_review':'required',
           'routing':'explicit_behavior_probe' if args.behavior_probe else 'ordinary',
           'prompt':prompt}
    report['runs'].append(row)
    print('Starting assessment '+label,flush=True)
    async with CodexServer(codex,project,env,args.output,label,args.timeout_seconds,
                           windows_sandbox=args.windows_sandbox) as server:
        started = await server.request('thread/start',options)
        row['sandbox'] = started.get('sandbox')
        row['instruction_sources'] = started.get('instructionSources', [])
        require_workspace(started)
        await probe_fixture_access(server,project,home)
        row['fixture_shell_probe'] = 'passed'
        thread_id = started['thread']['id']
        if args.preflight_only:
            return
        paused = False
        if case == 'paused':
            def pause_on_spawn(event):
                nonlocal paused
                params = event.get('params', {})
                item = params.get('item', {})
                if (not paused and params.get('threadId') == thread_id and item.get('tool') == 'spawnAgent'
                        and event.get('method') == 'item/completed' and item.get('status') == 'completed'):
                    store.set_capture('project', False, project_root=project, global_root=global_root)
                    paused = True
            server.on_event = pause_on_spawn
        offset = len(server.events)
        events, row['seconds'] = await server.turn(thread_id,prompt,args.model,args.reasoning,home)
        server.on_event = None
        records = [store.show_record('project', r['id'], project_root=project,global_root=global_root)
                   for r in store.list_records('project',project_root=project,global_root=global_root,
                                               status='all',limit=20)['records']]
        row['records'] = records
        record_id = records[0]['record']['id'] if len(records) == 1 else None
        trace = row['trace'] = capture_trace(events,thread_id,record_id)
        row['token_usage_by_thread'] = {e['params']['threadId']:e['params']['tokenUsage']['total']
                                       for e in events if e.get('method') == 'thread/tokenUsage/updated'}
        wait_starts, wait_times, wait_completions = {}, [], 0
        for event, received in zip(events, server.event_times[offset:]):
            params = event.get('params', {})
            item = params.get('item', {})
            if params.get('threadId') != thread_id or item.get('type') != 'collabAgentToolCall' or item.get('tool') != 'wait':
                continue
            if event.get('method') == 'item/started':
                wait_starts[item['id']] = received
            if event.get('method') == 'item/completed':
                wait_completions += 1
                if item['id'] in wait_starts:
                    wait_times.append(round(received-wait_starts.pop(item['id']),3))
        row['observed_wait_seconds'] = wait_times or None
        row['wait_measurement_complete'] = not wait_starts and wait_completions == len(wait_times)
        checked = subprocess.run([sys.executable, '-B', '-c',
            'from math_fixture import double; assert double(-3) == -6 and double(5) == 10'],
            cwd=project,env=env,capture_output=True,timeout=10)
        bodies = ' '.join(str(r['record'].get(field, '')) for r in records
                          for field in ('title','content','conditions','exceptions','do','dont'))
        checks = row['checks']
        prompts = [item.get('prompt') for _, item in completed_items(events,thread_id)
                   if item['type'] == 'collabAgentToolCall' and item.get('tool') in
                   {'spawnAgent','sendInput','sendMessage','followupTask'}]
        checks.update(main_task_correct=checked.returncode == 0,
                      project_guide_loaded=any(Path(source).resolve() == project/'AGENTS.md'
                                               for source in row['instruction_sources']),
                      no_global_leak=not store.list_records('global',global_root=global_root,status='all')['records'],
                      private_value_not_forwarded=all(isinstance(sent,str) and private not in sent for sent in prompts),
                      private_value_not_stored=private not in json.dumps(records,ensure_ascii=False))
        if case == 'paused':
            checks.update(paused_after_spawn=paused, no_capture_after_pause=not records,
                          no_apply_after_pause=trace['parent_apply_attempts'] == 0)
        else:
            checks.update(one_sourced_active_record=len(records) == 1 and records[0]['record']['status'] == 'active'
                          and any(e['source_type'] in store.USER_SOURCES for e in records[0]['evidence']),
                          values_saved=marker in bodies and (case == 'simple' or override in bodies),
                          parent_committed_once=trace['parent_save_receipts'] == 1)
        if case in {'delegated', 'paused'} and args.behavior_probe:
            checks['one_child'] = trace['spawn_attempts'] == len(trace['children']) == 1
        elif case in {'simple','baseline'}:
            checks['no_spawn'] = trace['spawn_attempts'] == 0
        if case == 'delegated' and trace['children']:
            checks['assessment_settled_before_write'] = trace['settled_before_write']
            checks['bounded_assessment_wait'] = (row['wait_measurement_complete'] and
                                                  len(wait_times) <= 1 and sum(wait_times) <= 5)
            row['assessment_resolution'] = ('reviewed' if trace['joined_before_save'] else
                                            'primary_takeover_after_stop' if trace['stopped_before_save'] else
                                            'unverified')
            checks['independent_work_while_assessment_pending'] = trace['work_after_spawn']
        elif case == 'delegated':
            row['assessment_resolution'] = 'primary_only_fallback'
            row['delegation_acceptance'] = 'not_exercised'
        if case == 'delegated' and trace['joined_before_save']:
            row['proposal_use_review'] = 'required: compare received_proposals with stored fields and user evidence'
        if case == 'delegated' and all(checks.values()):
            fresh = await server.request('thread/start',options)
            require_workspace(fresh)
            followup, row['fresh_seconds'] = await server.turn(fresh['thread']['id'],
                'Implement format_stamp(mode, legacy=False) in stamp.py using the project rules. '
                'Do not change existing behavior outside this new function.',args.model,args.reasoning,home)
            recalled, _ = context_bodies(followup)
            checks['fresh_recall_contains_saved_rule'] = record_id in recalled
            result = subprocess.run([sys.executable, '-B', '-c',
                f'from stamp import format_stamp as f; assert (f("normal"), f("audit"), f("audit", True)) '
                f'== ({marker!r}, {override!r}, {marker!r})'],
                cwd=project,env=env,capture_output=True,timeout=10)
            checks['fresh_behavior_matches_rule_and_exception'] = result.returncode == 0


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


async def evaluate(args, report, case=None, label=None):
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI with app-server is required.')
    auth = Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'auth.json'
    report.setdefault('host', subprocess.check_output([codex,'--version'],text=True).strip())
    with tempfile.TemporaryDirectory(prefix='dev-memory host acceptance ', dir=args.output.parent) as td, ExitStack() as credentials:
        root = Path(td).resolve()
        home, project = root/'home', root/'project'
        ch = home/'.codex'
        ch.mkdir(parents=True, mode=0o700)
        if not args.preflight_only and auth.is_file():
            copy = ch/'auth.json'
            # Remove the test-owned login copy before Windows sandbox ACLs can interrupt tree cleanup.
            credentials.callback(copy.unlink, missing_ok=True)
            shutil.copyfile(auth,copy)
            copy.chmod(0o600)
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
        if case:
            await assessment_case(codex,project,home,env,global_root,args,report,case,label)
            return
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
        async with CodexServer(codex,project,env,args.output,'startup',args.timeout_seconds,
                               windows_sandbox=args.windows_sandbox) as server:
            started = await server.request('thread/start',options)
            report['instruction_sources'] = started.get('instructionSources',[])
            report['sandbox'] = started.get('sandbox')
            require_workspace(started)
            await probe_fixture_access(server,project,home)
            report['fixture_shell_probe'] = 'passed'
            if args.preflight_only:
                return
            thread_id = started['thread']['id']
            await run_phase(server,thread_id,'startup',marker,1)
        marker = secrets.token_hex(8)
        seed_or_revise(project,global_root,marker,memory_id)
        (project/'receipt.py').write_text('"""Synthetic receipt utility."""\n',encoding='utf-8')
        async with CodexServer(codex,project,env,args.output,'resumed',args.timeout_seconds,
                               windows_sandbox=args.windows_sandbox) as server:
            resumed = await server.request('thread/resume',{'threadId':thread_id,'excludeTurns':True,**options})
            require_workspace(resumed)
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


async def assess_collaboration(args, report):
    cases = [('simple','simple')]
    if not args.preflight_only and not args.behavior_probe:
        cases = [('simple','ordinary-simple'), ('delegated','ordinary-complex')]
    elif not args.preflight_only:
        cases = [('simple','simple'), ('paused','paused')]
        for i in range(args.repetitions):
            pair = ('baseline','delegated') if i % 2 == 0 else ('delegated','baseline')
            cases.extend((case,f'{case}-{i+1}') for case in pair)
    for case,label in cases:
        await evaluate(args,report,case,label)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not args.preflight_only:
        assert all(row['checks'] and all(row['checks'].values()) for row in report['runs']), (
            'At least one collaboration behavior check failed; see runs.')


def opencode_results(events):
    """仅接受宿主返回的已完成工具输出，不读取模型对成功的自述。"""
    results, children = [], []
    for event in events:
        part = event.get('part', {})
        state = part.get('state', {})
        if event.get('type') != 'tool_use' or state.get('status') != 'completed':
            continue
        if part.get('tool') == 'subagent':
            children.append(part)
        if part.get('tool') != 'shell':
            continue
        command = state.get('input',{}).get('command','').lower().replace('\\','/')
        resolved_cli = '.dev-memory/activation.json' in command and 'bindings.opencode.cli' in command
        if (not ('dev_memory.py' in command or resolved_cli) or
                not any(' '+operation+' ' in ' '+command+' ' for operation in ('context','apply')) or
                command.lstrip().startswith(('echo ', 'write-output ', 'printf '))):
            continue
        metadata = state.get('metadata',{})
        exit_statuses = [source[key] for source in (state,metadata,metadata.get('metadata',{}))
                         for key in ('exit','exitCode','exit_code') if key in source]
        if any(code not in (0,'0') for code in exit_statuses):
            continue
        try:
            result = json.loads(state.get('output', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(result, dict):
            results.append(result)
    return results, children


def opencode_completed(events, exit_code):
    """结束事件格式会变化；进程成功且确有正文，并且没有宿主错误才算完成。"""
    return exit_code == 0 and any(event.get('type') == 'text' and
        event.get('part',{}).get('text','').strip() for event in events) and not any(
        event.get('type') == 'error' for event in events)


def evaluate_opencode(args, report):
    """普通提示验收；未证实停止能力的宿主必须从主智能体直接评估。"""
    host = shutil.which('opencode.exe') or shutil.which('opencode')
    if host and Path(host).suffix.lower() in {'.cmd','.ps1'}:
        bundled = Path(host).parent/'node_modules/@opencode/cli/bin/opencode.exe'
        if bundled.is_file():
            host = str(bundled)
    if not host or not args.provider_config:
        raise RuntimeError('OpenCode acceptance requires its executable and --provider-config (providers only).')
    config = json.loads(args.provider_config.read_text(encoding='utf-8'))
    if set(config) != {'providers'}:
        raise ValueError('--provider-config must contain only providers; no agents, instructions or credentials.')
    # 配置只允许通过进程环境取得凭据，临时项目不得落地凭据副本。
    for provider in config['providers'].values():
        settings = provider.get('settings',{})
        endpoint = settings.get('baseURL','')
        if (set(provider) - {'models','settings','package','env'} or
                set(settings) - {'baseURL','headerTimeout','timeout','chunkTimeout','encoding'} or
                not endpoint.startswith('{env:') or not endpoint.endswith('}') or
                not endpoint[5:-1].isidentifier() or
                not isinstance(provider.get('env'),list) or
                not all(isinstance(name,str) and name.isidentifier() for name in provider['env']) or
                any(set(model) - {'limit','name','capabilities'} for model in provider.get('models',{}).values())):
            raise ValueError('Use provider env names, an {env:VARIABLE} baseURL and model metadata only.')
    report.update(host=subprocess.check_output([host,'--version'],text=True).strip(),
                  mode='ordinary_routing', reasoning='host_default_unavailable',
                  capability_evidence={'native_result_delivery':'not_attested', 'native_stop':'not_attested'},
                  delegation_acceptance='not_exercised', semantic_review='required')
    with tempfile.TemporaryDirectory(prefix='dev-memory-opencode-',dir=args.output.parent) as td:
        root = Path(td)
        project, global_root = root/'project', root/'global'
        project.mkdir()
        skill = project/'.opencode/skills/dev-memory'
        shutil.copytree(ROOT/'skills/dev-memory',skill,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        setup.setup(project,'opencode',skill,sys.executable,global_root)
        config['mcp'] = {'servers':{'enabled':False}}
        (project/'opencode.json').write_text(json.dumps(config),encoding='utf-8')
        guide = (project/'AGENTS.md').read_bytes()
        env = {**os.environ,**{'XDG_'+name+'_HOME':str(root/name.lower())
                             for name in ('DATA','CONFIG','STATE','CACHE')},'DEV_MEMORY_HOME':str(global_root),
               'OPENCODE_CONFIG':str(project/'opencode.json'),'OPENCODE_CONFIG_DIR':str(root/'config'),
               'PYTHONDONTWRITEBYTECODE':'1','DEV_MEMORY_VECTOR_SETUP':'0'}
        marker, override = secrets.token_hex(6), secrets.token_hex(6)
        prompts = [
            f'Confirmed permanent rule for this project: format_stamp(mode, legacy=False) returns "{marker}" '
            f'by default and "{override}" only when mode is "audit" and legacy is false. '
            'Legacy always uses the default, even for audit. For the current unrelated task, '
            'create math_fixture.py with double(n) returning n*2. Do not implement format_stamp yet.',
            'Implement format_stamp(mode, legacy=False) in stamp.py using the project rules. '
            'Do not change existing behavior outside this new function.']
        record_id = None
        for phase,prompt in zip(('capture','fresh_recall'),prompts):
            print('Starting OpenCode ordinary '+phase,flush=True)
            started = time.monotonic()
            log = args.output.parent/(phase+'.jsonl')
            with log.open('w',encoding='utf-8') as output, \
                    (args.output.parent/(phase+'.stderr')).open('w',encoding='utf-8') as error:
                proc = subprocess.run([host,'--standalone','run','--auto','--format','json',
                    '--model',args.model,prompt],cwd=project,env=env,stdout=output,stderr=error,
                    timeout=args.timeout_seconds)
            events = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines() if line.strip()]
            results,children = opencode_results(events)
            records = [store.show_record('project', r['id'], project_root=project,global_root=global_root)
                       for r in store.list_records('project',project_root=project,global_root=global_root,
                                                   status='all',limit=20)['records']]
            checks = {'host_completed':opencode_completed(events,proc.returncode),
                      'guide_unchanged':(project/'AGENTS.md').read_bytes() == guide,
                      'primary_only_without_attested_stop':not children,
                      'no_global_leak':not store.list_records('global',global_root=global_root,status='all')['records']}
            if phase == 'capture':
                record_id = records[0]['record']['id'] if len(records) == 1 else None
                checks['one_sourced_active_record'] = bool(record_id and records[0]['record']['status'] == 'active'
                    and any(e['source_type'] in store.USER_SOURCES for e in records[0]['evidence']))
                checks['parent_save_receipt'] = sum(1 for result in results for scope in result.get('stores',[])
                    for op in scope.get('operations',[]) if scope.get('scope') == 'project'
                    and op.get('status') == 'saved' and op.get('id') == record_id) == 1
                checks['values_saved'] = all(value in json.dumps(records,ensure_ascii=False)
                                             for value in (marker,override))
                code = 'from math_fixture import double; assert double(-3) == -6 and double(5) == 10'
            else:
                checks['saved_body_received'] = any(r.get('id') == record_id for result in results
                    for scope in result.get('stores',[]) for r in scope.get('records',[]))
                code = ('from stamp import format_stamp as f; assert '
                        f'(f("normal"),f("audit"),f("audit",True)) == ({marker!r},{override!r},{marker!r})')
            checks['independent_behavior_check'] = subprocess.run([sys.executable,'-B','-c',code],
                cwd=project,env=env,capture_output=True,timeout=10).returncode == 0
            report['runs'].append({'phase':phase,'routing':'ordinary','prompt':prompt,'checks':checks,
                'seconds':round(time.monotonic()-started,3),'records':records,'tool_receipts':results,
                'native_children':len(children),'assessment_resolution':'primary_only_fallback'})
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            assert all(checks.values()), 'OpenCode '+phase+' checks failed; see report.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',required=True)
    parser.add_argument('--host',choices=('codex','opencode'),default='codex')
    parser.add_argument('--provider-config',type=Path,help='OpenCode providers-only JSON; credentials must remain in inherited env.')
    parser.add_argument('--reasoning',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=240)
    parser.add_argument('--assessment',action='store_true',help='Check capture collaboration separately from lifecycle recall.')
    parser.add_argument('--behavior-probe',action='store_true',
                        help='Explicitly inject fixture delegation instructions; never ordinary-routing acceptance. Requires --assessment.')
    parser.add_argument('--repetitions',type=int,default=1,help='Number of baseline/delegated pairs.')
    parser.add_argument('--preflight-only',action='store_true',help='Inspect the isolated sandbox without a model turn.')
    parser.add_argument('--windows-sandbox',choices=('elevated','unelevated'),
                        help='Use the named Windows backend for this isolated process.')
    args = parser.parse_args()
    if args.behavior_probe and not args.assessment:
        parser.error('--behavior-probe requires --assessment.')
    if args.host == 'opencode' and (not args.assessment or args.behavior_probe or args.preflight_only):
        parser.error('OpenCode supports ordinary --assessment real-model checks only.')
    args.output = args.output.expanduser().resolve()
    if args.output.is_relative_to(ROOT) or args.timeout_seconds < 1 or args.repetitions < 1:
        parser.error('Keep reports outside the repository; timeout and repetitions must be positive.')
    if args.windows_sandbox and os.name != 'nt':
        parser.error('--windows-sandbox only applies on Windows.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report = {'status':'running','synthetic_only':True,'model':args.model,'reasoning':args.reasoning,
              'hooks_configured':False,'prompts_mention_memory':False,'runs':[],
              'mode':('explicit_behavior_probe' if args.behavior_probe else 'ordinary_routing') if args.assessment else 'lifecycle',
              'runtime_source_sha256':source_hashes(),
              'limitations':['Named Codex app-server/model sample, not all hosts or future tasks.',
                             'No hook trust bypass or automatic model/vector setup.',
                             'Scope controls and vector integration are checked separately.']}
    try:
        if args.host == 'opencode':
            evaluate_opencode(args,report)
        else:
            asyncio.run(assess_collaboration(args,report) if args.assessment else evaluate(args,report))
        assert source_hashes() == report['runtime_source_sha256'], 'Runtime source changed during the evaluation.'
        report['status'] = ('preflight_passed' if args.preflight_only else
                            'behavior_checks_passed' if args.assessment else 'passed')
    except (AssertionError,OSError,RuntimeError,ValueError,KeyError,asyncio.TimeoutError,subprocess.TimeoutExpired) as exc:
        report.update(status='failed',error=str(exc))
        if isinstance(exc, OSError) and exc.__context__ is not None:
            report['underlying_error'] = str(exc.__context__)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())

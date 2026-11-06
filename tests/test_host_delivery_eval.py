"""Independent acceptance guards; no credentials, host startup or model calls."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'evals'))
import check_host_delivery as evaluation


class HostDeliveryEvaluationTests(unittest.TestCase):
    def event(self, result, command='python dev_memory.py context --force', exit_code=0):
        return {'method':'item/completed','params':{'item':{'type':'commandExecution','command':command,
            'exitCode':exit_code,'aggregatedOutput':json.dumps(result)}}}

    def test_assessment_defaults_to_ordinary_routing_and_probe_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as td:
            for extra,expected in (([],False),(['--behavior-probe'],True)):
                output = Path(td)/'result.json'
                argv = ['acceptance','--model','synthetic-model','--reasoning','high','--assessment',
                        '--output',str(output),*extra]
                run = AsyncMock()
                with patch.object(sys,'argv',argv), patch.object(evaluation,'assess_collaboration',run), \
                     patch.object(evaluation,'source_hashes',return_value={}):
                    self.assertEqual(evaluation.main(),0)
                self.assertEqual(run.call_args.args[0].behavior_probe,expected)
                self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['mode'],
                                 'explicit_behavior_probe' if expected else 'ordinary_routing')

    def test_cached_failed_or_claimed_delivery_is_not_a_body_receipt(self):
        body = {'stores':[{'scope':'project','records':[{'id':'rule','revision':3}]}]}
        cached = {'stores':[{'status':'cached','records':[]}]}
        self.assertEqual(evaluation.context_bodies([self.event(cached)]), ({},set()))
        self.assertEqual(evaluation.context_bodies([self.event(body,exit_code=1)]), ({},set()))
        self.assertEqual(evaluation.context_bodies([{'method':'item/completed','params':{
            'item':{'type':'agentMessage','text':json.dumps(body)}}}]), ({},set()))
        records, forced = evaluation.context_bodies([self.event(body)])
        self.assertEqual(records['rule']['revision'],3)
        self.assertEqual(forced,{'rule'})

    def test_opencode_receipts_reject_claims_failed_tools_and_unparsed_output(self):
        def tool(name, output, status='completed', command='python dev_memory.py apply', metadata=None):
            return {'type':'tool_use','part':{'tool':name,'state':{'status':status,'output':output,
                'input':{'command':command},'metadata':metadata or {}}}}
        receipt = {'status':'saved','stores':[{'scope':'project'}]}
        events = [tool('shell',json.dumps(receipt)),tool('shell',json.dumps(receipt),'error'),
                  tool('shell','saved'),tool('subagent','{"title":"proposal"}'),
                  tool('shell',json.dumps(receipt),command='echo '+json.dumps(receipt)),
                  tool('shell',json.dumps(receipt),command='echo "python dev_memory.py apply"'),
                  tool('shell',json.dumps(receipt),command='python unrelated.py apply'),
                  tool('shell',json.dumps(receipt),metadata={'metadata':{'exit':1}}),
                  tool('shell',json.dumps(receipt),metadata={'exitCode':2}),
                  {'type':'text','part':{'text':json.dumps(receipt)}}]
        results,children = evaluation.opencode_results(events)
        self.assertEqual(results,[receipt])
        self.assertEqual(len(children),1)
        binding = ('$a = Get-Content .dev-memory/activation.json | ConvertFrom-Json; '
                   '& $a.bindings.opencode.python $a.bindings.opencode.cli context --force')
        results,_ = evaluation.opencode_results([tool('shell',json.dumps(receipt),command=binding,
                                                    metadata={'metadata':{'exit':0}})])
        self.assertEqual(results,[receipt])

    def test_opencode_completion_accepts_trailing_stop_but_rejects_errors_and_empty_text(self):
        text = {'type':'text','part':{'text':'Completed task.'}}
        stop = {'type':'step_finish','part':{'reason':'stop'}}
        for events in ([text],[text,stop]):
            self.assertTrue(evaluation.opencode_completed(events,0))
        for events,code in (([text,stop],1),([text,{'type':'error'}],0),([stop],0),
                            ([{'type':'text','part':{'text':'  '}}],0)):
            self.assertFalse(evaluation.opencode_completed(events,code))

    def test_opencode_rejects_fixture_routing_and_embedded_credentials_before_host_start(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as td:
            config = Path(td)/'providers.json'
            args = Namespace(provider_config=config)
            for body in ({'providers':{},'agents':{}}, {'providers':{'fixture':{'settings':{'apiKey':'synthetic'}}}}):
                config.write_text(json.dumps(body),encoding='utf-8')
                with patch.object(evaluation.shutil,'which',return_value='opencode.exe'), \
                     patch.object(evaluation.subprocess,'check_output') as started:
                    with self.assertRaises(ValueError):
                        evaluation.evaluate_opencode(args,{})
                    started.assert_not_called()

    def test_readonly_host_fails_before_model_work(self):
        with self.assertRaisesRegex(RuntimeError, 'readOnly'):
            evaluation.require_workspace({'sandbox':{'type':'readOnly'}})
        evaluation.require_workspace({'sandbox':{'type':'workspaceWrite'}})

    def test_shell_probe_requires_a_real_fixture_write(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            server = Mock(request=AsyncMock(return_value={'exitCode':0,'stderr':''}))
            with self.assertRaisesRegex(RuntimeError, 'could not read and write'):
                asyncio.run(evaluation.probe_fixture_access(server,project,project))

    def test_collaboration_requires_real_parent_receipt_after_joining_its_child(self):
        def completed(item, thread='parent'):
            return {'method':'item/completed','params':{'threadId':thread,'item':item}}

        def collab(tool, child='child', state='completed', status='completed'):
            return completed({'type':'collabAgentToolCall','tool':tool,'status':status,
                              'senderThreadId':'parent','receiverThreadIds':[child],
                              'agentsStates':{child:{'status':state,'message':'{"title":"Scoped rule"}'}}})

        receipt = {'stores':[{'scope':'project','status':'saved','operations':[{'id':'rule','status':'saved'}]}]}
        command = self.event(receipt,command='python dev_memory.py apply')
        command['params']['threadId'] = 'parent'
        command['params']['item']['id'] = 'write-1'
        write_start = {'method':'item/started','params':command['params']}
        work = completed({'type':'fileChange','status':'completed','changes':[{'path':'math_fixture.py'}]})
        spawn, join = collab('spawnAgent'), collab('wait')
        good = evaluation.capture_trace([spawn,work,join,write_start,command],'parent','rule')
        self.assertEqual(good['children'],['child'])
        self.assertEqual(good['parent_save_receipts'],1)
        self.assertTrue(good['joined_before_save'])
        self.assertTrue(good['work_after_spawn'])
        self.assertTrue(good['settled_before_write'])
        cases = {
            'save before join':[spawn,work,write_start,command,join],
            'receipt after join but write started earlier':[spawn,work,write_start,join,command],
            'wrong reviewer':[spawn,work,collab('wait','other'),write_start,command],
            'missing write start':[spawn,work,join,command],
            'wait timed out':[spawn,work,collab('wait',state='running'),write_start,command],
            'failed wait':[spawn,work,collab('wait',status='errored'),write_start,command],
            'another reviewer still running':[spawn,collab('spawnAgent','other'),work,join,write_start,command],
            'first write before review then second write after':[
                spawn,write_start,command,work,join,
                {'method':'item/started','params':{'threadId':'parent','item':{
                    **command['params']['item'],'id':'write-2'}}},
                completed({**command['params']['item'],'id':'write-2'})],
        }
        for name, events in cases.items():
            with self.subTest(name=name):
                trace = evaluation.capture_trace(events,'parent','rule')
                self.assertFalse(trace['joined_before_save'])
                self.assertFalse(trace['settled_before_write'])
        empty_delivery = collab('wait')
        empty_delivery['params']['item']['agentsStates']['child'].pop('message')
        trace = evaluation.capture_trace([spawn,work,empty_delivery,write_start,command],'parent','rule')
        self.assertFalse(trace['joined_before_save'])
        self.assertFalse(trace['settled_before_write'])
        stopped = collab('closeAgent',state='shutdown')
        for tail in ([], [join]):
            trace = evaluation.capture_trace([spawn,work,stopped,*tail,write_start,command],'parent','rule')
            self.assertTrue(trace['stopped_before_save'])
            self.assertTrue(trace['settled_before_write'])
            self.assertFalse(trace['joined_before_save'])  # 迟到结果不能把接管路径伪装成评审通过。
            self.assertEqual(len(trace['late_proposals']),len(tail))
        trace = evaluation.capture_trace([spawn,work,join,stopped,write_start,command],'parent','rule')
        self.assertTrue(trace['joined_before_save'])  # 已收到结果后的正常关闭不撤销评审。
        stopping = collab('closeAgent',state='shutdown')
        stopping['params']['item']['id'] = 'stop-1'
        stop_start = {'method':'item/started','params':stopping['params']}
        trace = evaluation.capture_trace([spawn,work,stop_start,join,stopping,write_start,command],'parent','rule')
        self.assertTrue(trace['stopped_before_save'])
        self.assertFalse(trace['joined_before_save'])
        failed_stop = collab('closeAgent',state='running',status='errored')
        trace = evaluation.capture_trace([spawn,work,failed_stop,join,write_start,command],'parent','rule')
        self.assertFalse(trace['joined_before_save'])
        self.assertFalse(trace['stopped_before_save'])
        self.assertFalse(trace['settled_before_write'])
        command['params']['threadId'] = 'child'
        child_write = evaluation.capture_trace([spawn,work,join,write_start,command],'parent','rule')
        self.assertEqual(child_write['parent_save_receipts'],0)
        self.assertFalse(child_write['joined_before_save'])

    def test_body_without_force_is_not_evidence_of_forced_recall(self):
        body = {'stores':[{'records':[{'id':'rule','revision':1}]}]}
        records, forced = evaluation.context_bodies([self.event(body,command='python dev_memory.py context')])
        self.assertIn('rule',records)
        self.assertFalse(forced)

    def test_activation_resolved_cli_path_counts_as_context_delivery(self):
        body = {'stores':[{'records':[{'id':'rule','revision':3}]}]}
        command = ('$a = Get-Content .dev-memory/activation.json | ConvertFrom-Json; '
                   '& $a.bindings.codex.cli --global-root $a.bindings.codex.global_root '
                   'context --project-root $a.project_root --force')
        records, forced = evaluation.context_bodies([self.event(body,command=command)])
        self.assertEqual(records['rule']['revision'],3)
        self.assertEqual(forced,{'rule'})

    def test_real_artifact_must_have_current_marker_utf8_and_exact_newline(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            module = project/'receipt.py'
            env = {**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            for marker, suffix, expected in [('new','\n',True),('old','\n',False),('new','',False),('new','\r\n',False)]:
                module.write_text('from pathlib import Path\ndef write_receipt(text):\n'
                    '    Path("artifacts").mkdir(exist_ok=True)\n'
                    f'    Path("artifacts/receipt.txt").write_bytes(({marker!r}+"|"+text+{suffix!r}).encode("utf-8"))\n',encoding='utf-8')
                self.assertEqual(evaluation.artifact_matches(project,'new','中文',env),expected)

    def test_failed_host_turn_cannot_pass_acceptance(self):
        async def check(output):
            server = evaluation.CodexServer('unused',output.parent,{},output,'failed',1)
            server.events = [{'method':'turn/completed','params':{'threadId':'t',
                'turn':{'status':'failed','error':{'message':'quota'}}}}]
            try:
                with self.assertRaises(RuntimeError):
                    await server.completed('t',0)
            finally:
                await server.__aexit__()
        with tempfile.TemporaryDirectory() as td:
            asyncio.run(check(Path(td)/'result.json'))

    def test_initialization_failure_still_closes_own_process_and_logs(self):
        async def check(output):
            process = Mock(returncode=0)
            process.wait = AsyncMock(return_value=0)
            server = evaluation.CodexServer('unused',output.parent,{},output,'initialization',1)
            with patch.object(evaluation.asyncio,'create_subprocess_exec',AsyncMock(return_value=process)), \
                 patch.object(server,'request',AsyncMock(side_effect=RuntimeError('unsupported protocol'))):
                with self.assertRaises(RuntimeError):
                    await server.__aenter__()
            process.stdin.close.assert_called_once()
            process.wait.assert_awaited()
            self.assertTrue(server.log.closed)
            self.assertTrue(server.stderr.closed)
        with tempfile.TemporaryDirectory() as td:
            asyncio.run(check(Path(td)/'result.json'))

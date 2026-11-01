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

    def test_body_without_force_is_not_evidence_of_forced_recall(self):
        body = {'stores':[{'records':[{'id':'rule','revision':1}]}]}
        records, forced = evaluation.context_bodies([self.event(body,command='python dev_memory.py context')])
        self.assertIn('rule',records)
        self.assertFalse(forced)

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

"""Offline checks for the lifecycle evaluator, without model or private host access."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_dev_memory import MemoryTestCase, dev_memory, store
import check_lifecycle as lifecycle


class ModelRunnerTests(unittest.TestCase):
    def run_emitter(self, body, timeout=5):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home=Path(temp.name)
        script=home/'emitter.py';script.write_text(body,encoding='utf-8')
        popen=subprocess.Popen
        processes=[]
        def spawn(argv, **kwargs):
            process=popen([sys.executable,'-u',str(script)],**kwargs)
            processes.append(process)
            return process
        with patch.object(lifecycle.subprocess,'Popen',side_effect=spawn), contextlib.redirect_stdout(io.StringIO()):
            result,commands=lifecycle.run_model('unused','fake','low',home,home,os.environ.copy(),
                                                 'fake','unused',home/'report.json',timeout)
        self.assertIsNotNone(processes[0].poll())
        return result,commands,home

    def test_json_events_metrics_and_complete_logs(self):
        events=[{'type':'item.started','item':{'type':'command_execution'}},
                {'type':'item.completed','item':{'type':'command_execution','command':'fixture',
                  'aggregated_output':json.dumps({'stores':[{'status':'saved','operations':[
                    {'usage':'ai_reported_not_behavior_verified','used_id':'rule-one'}]}]})}},
                {'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':3}}]
        payload='noise\n[]\n'+''.join(json.dumps(e)+'\n' for e in events)
        result,commands,home=self.run_emitter(f'import sys\nsys.stdout.write({payload!r})\nsys.stderr.write("fixture stderr")\n')
        self.assertEqual(result['exit_code'],0)
        self.assertFalse(result['timed_out'])
        self.assertEqual((result['command_calls'],result['tool_calls']),(1,1))
        self.assertEqual(result['usage'],events[-1]['usage'])
        self.assertEqual(result['memory_use_reported_ids'],['rule-one'])
        self.assertEqual(commands,[events[1]['item']])
        self.assertIsNone(result['first_tool_action_seconds'])
        self.assertEqual((home/'lifecycle-fake.jsonl').read_text(encoding='utf-8'),payload)
        self.assertEqual((home/'lifecycle-fake.stderr').read_text(encoding='utf-8'),'fixture stderr')

    def test_timeout_preserves_partial_events_and_cleans_up(self):
        event={'type':'item.started','item':{'type':'mcp_tool_call'}}
        result,commands,home=self.run_emitter(
            f'import time,sys\nprint({json.dumps(event)!r},flush=True)\nprint("before timeout",file=sys.stderr,flush=True)\ntime.sleep(30)\n',timeout=1)
        self.assertTrue(result['timed_out'])
        self.assertNotEqual(result['exit_code'],0)
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(commands,[])
        self.assertLess(result['seconds'],5)
        self.assertIn('before timeout',(home/'lifecycle-fake.stderr').read_text(encoding='utf-8'))

    def test_host_failure_is_reported(self):
        event={'type':'turn.failed','error':{'message':'synthetic failure'}}
        result,_,_=self.run_emitter(f'import sys\nprint({json.dumps(event)!r})\nsys.exit(3)\n')
        self.assertEqual(result['exit_code'],3)
        self.assertEqual(result['host_errors'],[event])

    def test_program_report_reads_runtime_version(self):
        with tempfile.TemporaryDirectory() as td, patch.object(sys,'argv',['check_lifecycle','--program-only','--output',str(Path(td)/'report.json')]), \
                patch.object(lifecycle,'program_scale_probe',return_value={}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lifecycle.main(),0)
            report=json.loads((Path(td)/'report.json').read_text())
        self.assertEqual(report['runtime_version'],'.'.join(map(str,dev_memory._release_version(dev_memory.PACKAGE_ROOT))))


class CaptureCheckTests(MemoryTestCase):
    def test_sourced_requirement_and_correction_need_no_checkpoint_or_test_progress(self):
        memory_id=self.add_project_rule(content='Eligible within 30 days.',conditions='Within 30 days.')
        first=lifecycle.project_capture_checks(self.project_a,30)
        self.assertEqual(first['structured_verification_records'],0)
        self.assertEqual(first['actual_tool_result_observations'],0)
        revised=self.record(content='Eligible within 14 days.',conditions='Within 14 days.')
        receipt=self.apply(scope='project',turn='correction',operations=[
            {'op':'REVISE','id':memory_id,'expected_revision':1,'record':revised}])
        self.assertEqual(receipt['status'],'saved')
        self.assertTrue(lifecycle.project_capture_checks(self.project_a,14)['project_global_only_capture'])
        with self.assertRaisesRegex(AssertionError,'sourced desired rule'):
            lifecycle.project_capture_checks(self.project_a,30)

    def test_task_or_checkpoint_is_rejected_even_when_archived(self):
        for scope,kind in [('task','lesson'),('project','checkpoint')]:
            with self.subTest(scope=scope,kind=kind), patch.object(store,'list_records',return_value={
                    'records':[{'scope':scope,'kind':kind,'status':'archived'}]}):
                with self.assertRaisesRegex(AssertionError,'task memory/checkpoints'):
                    lifecycle.project_capture_checks(self.project_a)

    def test_verification_is_optional_but_must_be_sourced_and_structured(self):
        verification={'command':'fixture test','finished_at':'2026-10-22T00:00:00Z','code_version':'fixture','exit_code':0}
        self.add_project_rule(kind='lesson',claim_type='observed',verification=verification,
                              source={'type':'tool_result','excerpt':'Synthetic regression verified.'})
        checks=lifecycle.project_capture_checks(self.project_a)
        self.assertEqual((checks['structured_verification_records'],checks['actual_tool_result_observations']),(1,1))
        show=store.show_record
        for invalid in ['source','command','exit_code']:
            def altered(*args, **kwargs):
                detail=show(*args,**kwargs)
                if invalid=='source':detail['evidence']=[]
                elif invalid=='command':detail['record']['verification'].pop('command')
                else:detail['record']['verification']['exit_code']=True
                return detail
            with self.subTest(invalid=invalid), patch.object(store,'show_record',side_effect=altered):
                with self.assertRaises(AssertionError):lifecycle.project_capture_checks(self.project_a)

    def test_non_user_policy_source_does_not_satisfy_requirement_capture(self):
        self.add_project_rule(claim_type='observed',source={'type':'code_observation','excerpt':'Synthetic code observation.'})
        with self.assertRaisesRegex(AssertionError,'sourced desired rule'):
            lifecycle.project_capture_checks(self.project_a,14)


if __name__=='__main__':unittest.main()

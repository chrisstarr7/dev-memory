"""High-value event hints remain content-free and never bypass ordinary capture controls."""
import contextlib
import io
import json
from unittest.mock import patch
from test_dev_memory import MemoryTestCase, store
import codex_hook

class SignalTests(MemoryTestCase):
    def test_direct_signals_and_adversarial_non_signals(self):
        for text,want in [('纠正：那条规则只适用于复杂任务。','correction'),('以后所有项目都要先核验已有实现。','durable_requirement'),('已验证：故障根因是错误配置。','verified_claim'),('From now on use existing code first.','durable_requirement'),('本轮不记，以后都用它。',None),('例如：以后所有项目都用它。',None),('这次先临时修改那条规则。',None),('解释为什么“以后”不等于这次。',None),('运行测试。',None)]:
            with self.subTest(text=text):self.assertEqual(codex_hook.capture_signal(text),want)
    def test_signal_requires_host_ids_and_never_probes_or_writes(self):
        event={'prompt':'纠正：那条长期规则适用于复杂任务。','session_id':'s','turn_id':'t'}
        for value,want in [(event,True),({**event,'turn_id':None},False),({**event,'session_id':''},False)]:
            output=io.StringIO()
            with patch.object(store,'locate_project_root',side_effect=AssertionError('No scan')),patch.object(store,'apply_payload',side_effect=AssertionError('No capture write')),contextlib.redirect_stdout(output):
                codex_hook._handle_prompt(value)
            self.assertEqual(bool(output.getvalue()),want)
            if want:
                result=json.loads(output.getvalue());body=result['hookSpecificOutput']['additionalContext']
                self.assertIn('not a save receipt',body);self.assertNotIn(event['prompt'],body)
                self.assertIn('read-only',body)
    def test_user_verified_claim_is_not_tool_proof(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):codex_hook._handle_prompt({'prompt':'已验证：测试成功。','session_id':'s','turn_id':'t'})
        self.assertIn('only a user claim',output.getvalue())

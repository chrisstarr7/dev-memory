"""Baseline scoring cannot turn missing evidence or failures into successful memory use."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evals'))
import check_memory_quality as quality

class QualityTests(unittest.TestCase):
    def test_usage_missing_is_unknown_and_cache_not_double_counted(self):
        self.assertIsNone(quality.usage_total(None))
        self.assertIsNone(quality.usage_total({'input_tokens':1}))
        self.assertEqual(quality.usage_total({'input_tokens':10,'output_tokens':2,'cached_input_tokens':8}),12)
    def test_index_claim_and_failed_command_do_not_count_as_body(self):
        result={'stores':[{'records':[{'id':'a','content':'rule'}],'unloaded_candidates':[{'id':'b'}]}]}
        cmd={'command':'python dev_memory.py context --force','exit_code':0,'aggregated_output':json.dumps(result)}
        self.assertEqual(quality.delivered([cmd]),{'a'})
        self.assertEqual(quality.delivered([{**cmd,'exit_code':1}]),set())
        self.assertEqual(quality.delivered([{**cmd,'command':'echo claimed memory'}]),set())
        self.assertEqual(quality.delivered([{**cmd,'command':"echo 'dev_memory.py context --force'"}]),set())
        self.assertEqual(quality.delivered([{**cmd,'command':'python -c "print(\'dev_memory.py context\')"'}]),set())
    def test_missing_artifact_and_timeout_remain_in_denominators(self):
        row={'case':'x','repeat':0,'mode':'on','expected_count':1,'correct_delivered':0,
             'seconds':10,'exit_code':1,'timed_out':True,'usage':None,
             'artifact':{'passed':False,'readable_artifact':False,'wrong_memory_behavior':None}}
        r=quality.summarize([row]);self.assertEqual(r['rule_execution'],{'passed':0,'tasks':1})
        self.assertEqual(r['wrong_adoption']['missing_artifacts'],1)
        self.assertEqual(r['wrong_adoption']['readable_tasks'],0)
        self.assertEqual(r['recall']['rate'],0);self.assertEqual(r['host_failures'],1)
        self.assertEqual(r['missing_usage'],1)
    def test_paired_delta_requires_both_usage_receipts(self):
        row={'case':'x','repeat':0,'mode':'on','expected_count':1,'correct_delivered':1,'seconds':10,
             'exit_code':0,'usage':{'input_tokens':10,'output_tokens':2},
             'artifact':{'passed':True,'readable_artifact':True,'wrong_memory_behavior':False}}
        off={**row,'mode':'off','seconds':8,'usage':None}
        r=quality.summarize([row,off]);self.assertIsNone(r['paired_deltas'][0]['token_delta'])
        self.assertEqual(r['paired_deltas'][0]['seconds_delta'],2)
    def test_capacity_missing_usage_and_wrong_artifact_cannot_report_passed(self):
        row={'mode':'on','expected_count':1,'correct_delivered':1,'exit_code':0,'timed_out':False,
             'off_runtime_absent':True,'usage':{'input_tokens':10,'output_tokens':2},'artifact':{'passed':True}}
        self.assertEqual(quality.finish_status([row]),'passed')
        self.assertEqual(quality.finish_status([row,{**row,'mode':'off','exit_code':1}]),'host_incomplete')
        self.assertEqual(quality.finish_status([{**row,'usage':None}]),'metrics_incomplete')
        self.assertEqual(quality.finish_status([{**row,'artifact':{'passed':False}}]),'failed')
        self.assertEqual(quality.finish_status([{**row,'off_runtime_absent':False}]),'failed')

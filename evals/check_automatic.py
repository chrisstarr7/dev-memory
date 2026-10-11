"""Isolated real-host check; prompts contain no memory/Skill invocation."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='Report path outside the source repository')
args = parser.parse_args()
REPO = Path(__file__).resolve().parents[1]
output = args.output.expanduser().resolve()
if output.is_relative_to(REPO):
    parser.error('Use an output outside the source repository for synthetic transcripts and reports.')
output.parent.mkdir(parents=True, exist_ok=True)
WORK = output.parent
sys.path.insert(0, str(REPO / 'skills/dev-memory/scripts'))
import dev_memory_store as store

AUTH = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'auth.json'
CODEX = shutil.which('codex')
report = {'status': 'running', 'host': subprocess.check_output([CODEX, '--version'], text=True).strip(),
          'model': 'gpt-6-astra', 'reasoning_effort': 'medium',
          'user_prompts_mention_skill': False, 'hooks_configured': False, 'runtime_version': '0.3.0', 'runs': []}
with tempfile.TemporaryDirectory(prefix='dev-memory automatic onboarding ') as tmp:
    home = Path(tmp).resolve()
    codex_home = home / '.codex'
    codex_home.mkdir()
    if AUTH.is_file():
        shutil.copyfile(AUTH, codex_home / 'auth.json')
        os.chmod(codex_home / 'auth.json', 0o600)
    env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home), 'CODEX_HOME': str(codex_home),
           'DEV_MEMORY_HOME': str(home / '.dev-memory'), 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('CODEX_DISABLE_PROJECT_DOCS', None)
    a, b = home / 'project-a', home / 'project-b'
    for project in (a, b):
        project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        (project / 'policy.py').write_text('def eligible(delivered, unopened, days, gift, final_sale):\n    return days <= 30\n')
        result = subprocess.run([sys.executable, '-B', str(REPO / 'install.py'), 'codex', '--project', str(project), '--json'],
                                env=env, cwd=home, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        setup = json.loads(result.stdout)
        assert setup['project_setup']['activation'] == 'configured'
    def run(label, project, prompt):
        print('Starting ' + label, flush=True)
        started = time.monotonic()
        cmd = [CODEX, 'exec', '--json', '--ephemeral', '--ignore-user-config', '--ignore-rules',
               '--skip-git-repo-check', '--sandbox', 'workspace-write', '--model', 'gpt-6-astra',
               '--config', 'model_reasoning_effort="medium"', '--add-dir', str(home),
               '--output-last-message', str(home / f'{label}-final.txt'), prompt]
        process = subprocess.Popen(cmd, cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = process.communicate(timeout=240)
        except subprocess.TimeoutExpired:
            process.kill(); stdout, stderr = process.communicate()
            raise RuntimeError('Host run timed out: ' + label)
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        commands = [e['item'].get('command', '') for e in events
                    if isinstance(e.get('item'), dict) and e['item'].get('type') == 'command_execution'
                    and e.get('type') == 'item.completed']
        # Retain only scoped synthetic transcripts outside the public release.
        (WORK / f'automatic-{label}.jsonl').write_text(stdout)
        (WORK / f'automatic-{label}.stderr').write_text(stderr)
        final = (home / f'{label}-final.txt').read_text() if (home / f'{label}-final.txt').exists() else ''
        recalled_kinds = {}
        for event in events:
            item = event.get('item', {})
            if event.get('type') != 'item.completed' or 'recall' not in item.get('command', ''):
                continue
            try:
                value = json.loads(item.get('aggregated_output', ''))
            except ValueError:
                continue
            if isinstance(value, dict):
                for block in value.get('stores', []):
                    recalled_kinds.setdefault(block['scope'], []).extend(r['kind'] for r in block.get('records', []))
        metrics = {'label': label, 'exit_code': process.returncode, 'seconds': round(time.monotonic()-started, 3),
                   'recalled_record_kinds': recalled_kinds, 'tool_calls': len(commands), 'usage': next((e.get('usage') for e in reversed(events) if e.get('usage')), None),
                   'skill_read': any('SKILL.md' in command for command in commands),
                   'recall_called': any('dev_memory.py' in c and 'recall' in c for c in commands),
                   'apply_called': any(('dev_memory.py' in c or "b['cli']" in c or 'b["cli"]' in c) and 'apply' in c for c in commands), 'final': final}
        report['runs'].append(metrics)
        print(json.dumps({k: v for k,v in metrics.items() if k != 'final'}), flush=True)
        assert process.returncode == 0, label + ' failed'
        return metrics
    initial = run('a-correction', a,
        '纠正本项目退货规则：必须已签收、未拆封、签收后不超过14天；礼品订单和最终销售商品不能退。'
        '这条只适用本项目。另一个明确跨项目适用的研发偏好：回复先给结论，再给必要依据。'
        '先检查现有 policy.py，今天停在准备阶段，不修改业务代码。')
    assert initial['skill_read'] and initial['recall_called'] and initial['apply_called'], 'Missing automatic workflow'
    a_records = store.list_records('project', project_root=a, limit=100)['records']
    global_records = store.list_records('global', global_root=home / '.dev-memory', limit=100)['records']
    assert any(r['kind'] == 'business_rule' for r in a_records), 'A rule was not saved'
    assert any(r['kind'] == 'checkpoint' for r in a_records), 'A checkpoint was not saved'
    assert any(r['kind'] == 'preference' for r in global_records), 'Global confirmation was not saved'
    for record in global_records:
        detail = store.show_record('global', record['id'], global_root=home / '.dev-memory')['record']
        assert detail.get('cross_project_confirmed') is True
    assert not any(r['kind'] == 'business_rule' for r in global_records), 'Business leaked globally'
    resumed = run('a-new-session', a, '继续上次的任务，实现 policy.py 中的 eligible 函数，只修改这个文件。')
    namespace = {}; exec((a / 'policy.py').read_text(), namespace)
    eligible = namespace['eligible']
    cases = [(True,True,14,False,False,True), (True,True,15,False,False,False),
             (False,True,3,False,False,False), (True,False,3,False,False,False),
             (True,True,3,True,False,False), (True,True,3,False,True,False)]
    assert all(eligible(*case[:-1]) == case[-1] for case in cases), 'A recovery lost a key condition'
    assert resumed['recall_called'] and resumed['apply_called'], 'Resume memory workflow missing'
    assert 'checkpoint' in resumed['recalled_record_kinds'].get('project', []), 'Checkpoint was not recalled by the host'
    switched = run('b-new-session', b,
        '实现订单取消判断，在 policy.py 新增 can_cancel(shipped)，只允许尚未发货的订单取消。仅修改这个文件。')
    namespace = {}; exec((b / 'policy.py').read_text(), namespace)
    assert namespace['can_cancel'](False) is True and namespace['can_cancel'](True) is False
    assert 'return days <= 30' in (b / 'policy.py').read_text(), 'A business affected B code'
    recalled = store.recall('订单取消', project_root=b, global_root=home / '.dev-memory', readonly=True, force=True)
    raw = json.dumps(recalled, ensure_ascii=False)
    assert '14天' not in raw and '14 天' not in raw and '最终销售' not in raw, 'A business in B recall'
    assert '结论' in raw, 'B did not receive confirmed global preference'
    assert switched['recall_called'] and switched['apply_called']
    assert 'preference' in switched['recalled_record_kinds'].get('global', []), 'Global preference was not recalled by B host'
    report.update(status='passed', checks={'automatic_skill_load': True, 'automatic_correction_save': True,
        'automatic_checkpoint_save': True, 'new_session_recovery_six_conditions': True,
        'project_b_isolation': True, 'confirmed_global_preference_in_b': True},
        per_turn_event_enforcement=False, limitations=['Observed three ordinary-prompt Codex CLI sessions; not proof of every-turn enforcement.',
            'Desktop app and other hosts were not run.', 'Existing performance A/B evidence remains separate; these runs are not a controlled latency comparison.'])
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('Automatic onboarding check passed.', flush=True)

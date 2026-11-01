"""Explicit real-host synonym correction checks; synthetic stores and separate conversations only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from check_lifecycle import ROOT, run_model, source_hashes, store
from check_memory_fidelity import snapshot
import dev_memory_setup as setup

PROMPTS = {
    'synonym': '把“别再造轮子”那条约定改为仅复杂开发任务需要遵守，其他条件不变。',
    'ambiguous': '把“别再造轮子”那条约定改成仅复杂开发任务适用。',
    'temporary': '这次临时直接重新写，不用遵守那条避免重复实现的约定。',
}


def correction_checks(before: dict, after: dict, label: str) -> dict[str, bool]:
    """Check identity/history/protected fields independently of the AI's success claim."""
    unchanged_global = before['global'] == after['global']
    if label != 'synonym':
        return {'global_unchanged': unchanged_global,
                'memory_evidence_and_history_unchanged': before['project'] == after['project']}
    prior, current = before['project'][0], after['project'][0]
    a, b = prior['record'], current['record']
    preserved = ('id', 'kind', 'claim_type', 'status', 'strength', 'exceptions', 'dont',
                 'verification_steps', 'code_refs', 'source_refs')
    old_evidence = prior['evidence']
    return {'global_unchanged': unchanged_global,
            'no_duplicate_records': len(after['project']) == len(before['project']) == 1,
            'same_target_revised_once': a['id'] == b['id'] and b['revision'] == a['revision'] + 1,
            'protected_fields_preserved': all(a[k] == b[k] for k in preserved),
            'candidate_remains_inactive': b['status'] == 'candidate',
            'old_evidence_preserved': all(e in current['evidence'] for e in old_evidence),
            'new_user_evidence': any(e not in old_evidence and e['source_type'] in store.USER_SOURCES
                                     for e in current['evidence']),
            'revision_history_retained': len(current['revisions']) > len(prior['revisions'])}


def seed(project: Path, global_root: Path, label: str) -> None:
    titles = ['服务模块复用', '界面组件复用'] if label == 'ambiguous' else ['实现复用']
    for n, title in enumerate(titles):
        record = {'kind':'convention', 'claim_type':'desired', 'status':'candidate', 'strength':'soft',
                  'title':title, 'content':title + '：开发前优先检查现成实现，合适时复用。',
                  'conditions':'开发任务开始时。', 'do':'检查现成实现，合适时复用。',
                  'exceptions':'已有实现无法满足需求时允许新增。', 'dont':'不得为复用而牺牲正确性。',
                  'verification_steps':'核对正确性及现有实现能否满足需求。', 'tags':['implementation'],
                  'source':{'type':'user_statement', 'excerpt':'开发前检查现成实现；不满足需求时可新增，正确性优先。'}}
        result = store.apply_payload({'schema_version':1, 'scope':'project', 'session_id':'synthetic-seed',
            'turn_id':str(n), 'idempotency_key':f'seed-{n}',
            'operations':[{'op':'ADD', 'scope':'project', 'record':record}]},
            project_root=project, global_root=global_root, schedule_vectors=False)
        assert result['status'] == 'saved', result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--reasoning', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-seconds', type=int, default=180)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.is_relative_to(ROOT) or args.timeout_seconds < 1:
        parser.error('Use an output outside the repository and a positive timeout.')
    output.parent.mkdir(parents=True, exist_ok=True)
    codex = shutil.which('codex')
    if not codex:
        parser.error('Codex CLI required; this evaluation makes real model calls.')
    auth = Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'auth.json'
    report = {'status':'running', 'synthetic_only':True, 'semantic_review':'required',
              'model':args.model, 'reasoning':args.reasoning,
              'host':subprocess.check_output([codex, '--version'], text=True).strip(),
              'runtime_source_sha256':source_hashes(), 'runs':[],
              'limitations':['One named host/model sample, not a semantic accuracy rate.',
                             'Primary AI must review prompts, final replies and every changed field.',
                             'These inactive candidates have no vector index; query reformulation is exercised.']}
    try:
        for label, prompt in PROMPTS.items():
            with tempfile.TemporaryDirectory(prefix='dev-memory sentence ') as td:
                root = Path(td).resolve()
                home, project = root/'home', root/'project'
                ch = home/'.codex'
                ch.mkdir(parents=True, mode=0o700)
                if auth.is_file():
                    shutil.copyfile(auth, ch/'auth.json')
                    (ch/'auth.json').chmod(0o600)
                skill = home/'.agents/skills/dev-memory'
                shutil.copytree(ROOT/'skills/dev-memory', skill, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                project.mkdir()
                subprocess.run(['git','init','-q',str(project)], check=True)
                global_root = home/'.dev-memory'
                setup.setup(project, 'codex', skill, sys.executable, global_root)
                seed(project, global_root, label)
                guide = (project/'AGENTS.md').read_bytes()
                before = snapshot(project, global_root)
                assert len(before['project']) == (2 if label == 'ambiguous' else 1), 'Fixture targets were merged.'
                miss = store.match_targets('别再造轮子', 'project', project_root=project, global_root=global_root)
                assert not miss['stores'][0]['records'], 'The synonym fixture must not be an exact keyword hit.'
                env = {**os.environ, 'HOME':str(home), 'USERPROFILE':str(home), 'CODEX_HOME':str(ch),
                       'DEV_MEMORY_HOME':str(global_root), 'PYTHONDONTWRITEBYTECODE':'1','DEV_MEMORY_VECTOR_SETUP':'0'}
                for key in ('CODEX_DISABLE_PROJECT_DOCS','CODEX_THREAD_ID','CODEX_SESSION_ID'):
                    env.pop(key, None)
                row, commands = run_model(codex, args.model, args.reasoning, project, home, env,
                    'sentence-'+label, prompt, output, args.timeout_seconds, network_access=False)
                row.update(prompt=prompt, before=before, after=snapshot(project, global_root))
                report['runs'].append(row)
                row['checks'] = correction_checks(before, row['after'], label)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                assert row['exit_code'] == 0 and not row['timed_out'] and not row['host_errors'], row
                assert (project/'AGENTS.md').read_bytes() == guide, 'Managed guide changed.'
                assert all(row['checks'].values()), row['checks']
        assert len({t for r in report['runs'] for t in r['thread_ids']}) == len(PROMPTS)
        assert source_hashes() == report['runtime_source_sha256'], 'Runtime changed during evaluation.'
        report['status'] = 'program_checks_passed_semantic_review_required'
    except (AssertionError, OSError, ValueError, IndexError, KeyError) as exc:
        report.update(status='failed', error=str(exc))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return 0 if report['status'] == 'program_checks_passed_semantic_review_required' else 1


if __name__ == '__main__':
    raise SystemExit(main())

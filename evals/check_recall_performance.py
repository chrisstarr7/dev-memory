#!/usr/bin/env python3
"""Matched synthetic recall timings; no model calls or real user stores.

Freeze the old scripts first (for example with git archive), then pass their
directory as --baseline-scripts. Results are measurements, not timing gates.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/dev-memory/scripts'


def summary(value):
    """Compare retrieved evidence and completeness, excluding cache bookkeeping."""
    if 'stores' in value:
        return [summary(bucket) for bucket in value['stores']]
    records = value.get('records', value.get('matches', []))
    return {'status': value.get('status'), 'records': records,
            'signature': value.get('signature'),
            'remaining_ids': value.get('remaining_ids', []),
            'unloaded_candidates': value.get('unloaded_candidates', []),
            'maintenance': {key: value.get('maintenance', {}).get(key)
                            for key in ('status', 'threshold', 'pending_up_to_threshold',
                                        'trigger', 'records_loaded')},
            'context_incomplete': value.get('context_incomplete', False),
            'candidate_limit_reached': value.get('candidate_limit_reached', False)}


def measure(operation, repetitions, store):
    elapsed, counts, signatures = [], [], []
    for index in range(repetitions):
        with patch.object(store, '_run_git', wraps=store._run_git) as git:
            start = time.perf_counter()
            result = operation(index)
            elapsed.append((time.perf_counter() - start) * 1000)
            counts.append(git.call_count)
        signatures.append(summary(result))
    return {'median_ms': round(statistics.median(elapsed), 3),
            'max_ms': round(max(elapsed), 3), 'samples_ms': elapsed,
            'git_calls': counts, 'results': signatures}


def worker(args):
    sys.path.insert(0, str(args.scripts))
    import dev_memory
    import dev_memory_store as store
    home = args.fixture
    project, global_root = home / 'project', home / 'global-root'
    record = {'kind': 'business_rule', 'claim_type': 'desired', 'strength': 'soft',
              'title': 'Synthetic shard0 contract',
              'content': 'Synthetic topic shard0 requires integer cents; forbidden negative values.',
              'tags': ['synthetic-topic', 'shard0'],
              'source': {'type': 'user_confirmation', 'excerpt': 'Synthetic fixture only.'}}
    if args.seed:
        project.mkdir(parents=True)
        if args.git:
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            (project / 'fixture.txt').write_text('Synthetic fixture\n', encoding='utf-8')
            subprocess.run(['git', '-C', str(project), 'add', 'fixture.txt'], check=True)
            subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture',
                            '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Fixture'], check=True)
        store.init_global(global_root)
        store.init_project(project)
        _, db, config = store._config_for('project', project, global_root)
        with contextlib.closing(store._connect(db)) as conn:
            for n in range(args.size):
                item = {**record, 'title': f'Synthetic shard{n} contract',
                        'content': f'Synthetic topic shard{n} requires integer cents; forbidden negative values.',
                        'tags': ['synthetic-topic', f'shard{n}']}
                normalized = store._validate_record(item, 'project', None, config['namespace_id'])
                mid, _ = store._store_record(conn, normalized)
                store._queue_maintenance(conn, mid)
            conn.commit()
        return {'seeded': args.size}
    common = dict(project_root=project, global_root=global_root, include_task=False)
    query = f'shard{args.size - 1}'
    operations = {
        'readonly_narrow': lambda _: store.recall(query, readonly=True, force=True, **common),
        'readonly_saturated': lambda _: store.recall('synthetic topic', readonly=True, force=True, **common),
        'context_no_session': lambda _: dev_memory.context(query, **common),
        'context_first_session': lambda n: dev_memory.context(query, session_id=f'{args.label}-first-{n}', **common),
        'context_cached': lambda _: dev_memory.context(query, session_id=f'{args.label}-cached', **common),
        'match': lambda _: store.match_payload({'scope': 'project', 'record': record},
                                             project_root=project, global_root=global_root),
    }
    report = {}
    for name, operation in operations.items():
        if name == 'context_cached':
            operation(0)
        report[name] = measure(operation, args.repetitions, store)
        if name in {'readonly_narrow', 'context_no_session', 'context_first_session'}:
            assert all(len(result[1]['records']) == 1
                       and result[1]['records'][0]['title'] == f'Synthetic shard{args.size - 1} contract'
                       for result in report[name]['results']), f'{name} failed narrow retrieval'
        if name == 'context_cached':
            assert all(result[1]['status'] == 'cached' for result in report[name]['results']), 'Cache miss'
    def cli(_):
        result = subprocess.run([sys.executable, '-B', str(args.scripts / 'dev_memory.py'),
                                 '--global-root', str(global_root), 'context', '--project-root', str(project),
                                 '--exclude-task', '--query', query], capture_output=True, text=True,
                                encoding='utf-8', timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    report['cli_context_no_session'] = measure(cli, args.repetitions, store)
    report['cli_context_no_session']['git_calls'] = None  # Separate process is not instrumented.
    if args.git:
        dirty = project / 'dirty-fixture'
        dirty.mkdir()
        try:
            for n in range(500):
                path = dirty / f'{n}.txt'
                path.write_text('synthetic\n', encoding='utf-8')
                os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
            report['dirty_500_signature'] = measure(
                lambda _: {'status': 'ok', 'signature': store._workspace_signature(project)},
                args.repetitions, store)
            assert all(item['signature'] for item in report['dirty_500_signature']['results'])
        finally:
            for path in dirty.iterdir():
                path.unlink()
            dirty.rmdir()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-scripts', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--sizes', type=int, nargs='+', default=[1000, 10000])
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--scripts', type=Path, default=SCRIPTS, help=argparse.SUPPRESS)
    parser.add_argument('--fixture', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--size', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--git', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--seed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--label', default='baseline', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args)))
        return 0
    if not args.baseline_scripts or not args.output:
        parser.error('--baseline-scripts and --output are required')
    if args.repetitions < 5 or any(size < 1 for size in args.sizes):
        parser.error('Use at least five repetitions and positive fixture sizes.')
    args.output = args.output.resolve()
    if args.output.is_relative_to(ROOT):
        parser.error('Keep synthetic reports outside the repository.')
    report = {'status': 'running', 'synthetic_only': True, 'model_invoked': False, 'repetitions': args.repetitions,
              'limitations': ['Local wall-clock timings; not whole AI conversation latency.',
                              'Sequential versions under possible concurrent test load; not interleaved timings.',
                              'Git counts exclude subprocess CLI instrumentation.',
                              'Large common-term queries may hit the existing SQLite deadline.'],
              'source_hashes': {}, 'cells': []}
    versions = [('baseline', args.baseline_scripts.resolve())]
    if not args.baseline_only:
        versions.append(('working', SCRIPTS))
    for label, scripts in versions:
        report['source_hashes'][label] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(scripts.glob('*.py'))}
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    def run(scripts, fixture, size, git, label, seed=False):
        cmd = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', '--scripts', str(scripts),
               '--fixture', str(fixture), '--size', str(size), '--repetitions', str(args.repetitions), '--label', label]
        if git:
            cmd.append('--git')
        if seed:
            cmd.append('--seed')
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env, timeout=300)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    with tempfile.TemporaryDirectory(prefix='dev-memory-perf-') as td:
        for git in (False, True):
            for size in args.sizes:
                fixture = Path(td) / f'{git}-{size}'
                run(versions[0][1], fixture, size, git, 'seed', seed=True)
                cell = {'git_project': git, 'active_records': size, 'versions': {}}
                for label, scripts in versions:
                    cell['versions'][label] = run(scripts, fixture, size, git, label)
                if len(versions) == 2:
                    cell['semantic_equivalence'] = {}
                    cell['comparison'] = {}
                    for name, before in cell['versions']['baseline'].items():
                        after = cell['versions']['working'][name]
                        # Timed-out matches are explicitly deferred, not complete evidence.
                        equal = before['results'] == after['results']
                        statuses = {bucket['status'] for result in before['results'] + after['results']
                                    for bucket in (result if isinstance(result, list) else [result])}
                        cell['semantic_equivalence'][name] = equal
                        cell['comparison'][name] = ('different' if not equal else
                            'inconclusive_query_deadline' if 'deferred' in statuses else
                            'inconclusive_unavailable' if statuses - {'ok', 'cached', 'matched', 'compare'} else 'equivalent')
                report['cells'].append(cell)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                print(json.dumps({'git': git, 'size': size,
                                 'median_ms': {label: {name: op['median_ms'] for name, op in ops.items()}
                                               for label, ops in cell['versions'].items()},
                                 'semantic_equivalence': cell.get('semantic_equivalence')}), flush=True)
    for label, scripts in versions:
        assert report['source_hashes'][label] == {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(scripts.glob('*.py'))
        }, f'{label} runtime changed during measurement'
    report['status'] = 'passed' if all(all(value == 'equivalent' for value in cell.get('comparison', {}).values())
                                     for cell in report['cells']) else 'needs_review'
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

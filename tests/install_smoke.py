#!/usr/bin/env python3
"""Opt-in network test of the actual skills CLI, with an isolated HOME/cache."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import dev_memory
import dev_memory_store as store


def run(output: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix='dev-memory-installer-smoke-') as scratch:
        base = Path(scratch).resolve()
        home, project = base / 'home', base / 'project'
        home.mkdir()
        project.mkdir()
        env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home), 'CODEX_HOME': str(home / '.codex'),
               'XDG_CONFIG_HOME': str(home / '.config'), 'NPM_CONFIG_CACHE': str(base / 'npm-cache'),
               'NPM_CONFIG_USERCONFIG': str(base / 'npmrc'), 'DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1'}
        (base / 'npmrc').write_text('')
        commands = []
        def command(args, action):
            started = time.monotonic()
            result = subprocess.run(args, env=env, cwd=base, text=True, capture_output=True, timeout=90)
            commands.append({'action': action, 'exit_code': result.returncode,
                             'elapsed_seconds': round(time.monotonic() - started, 3)})
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:] + result.stdout[-2000:])
            return result
        # This pinned external manager predates DSH; use our native installer for DSH.
        agents = [agent for agent in dev_memory.AGENT_DIRS if agent != 'deepseek-harness']
        prefix = ['npx', '--yes', 'skills@1.7.2']
        add = [*prefix, 'add', str(ROOT), '--skill', 'dev-memory', '-g', '-a', *agents, '--copy', '-y']
        command(add, 'install')
        assert not (home / '.dev-memory').exists(), 'Unexpected initialization'
        files_checked = 0
        destinations = {}
        for agent, relative in dev_memory.AGENT_DIRS.items():
            if agent not in agents:
                continue
            target = home / relative / 'dev-memory'
            if not target.is_dir() and agent in {'cursor', 'gemini-cli', 'github-copilot', 'opencode'}:
                target = home / '.agents/skills/dev-memory'
            destinations[agent] = target.relative_to(home).as_posix()
            for name in dev_memory.SKILL_FILES:
                source = ROOT / 'skills/dev-memory' / name
                assert (target / name).is_file(), (agent, name)
                assert hashlib.sha256((target / name).read_bytes()).digest() == hashlib.sha256(source.read_bytes()).digest()
                files_checked += 1
            assert not (target / 'tests').exists()
            assert not (target / 'reports').exists()
            result = command([sys.executable, str(target / 'scripts/dev_memory.py'), 'doctor'], 'doctor:' + agent)
            assert json.loads(result.stdout)['read_only'] is True
        store.init_global(home / '.dev-memory')
        store.init_project(project)
        databases = [store.global_paths(home / '.dev-memory')[1], store.project_paths(project)[1]]
        before = [hashlib.sha256(path.read_bytes()).digest() for path in databases]
        command(add, 'reinstall')
        assert before == [hashlib.sha256(path.read_bytes()).digest() for path in databases]
        command([*prefix, 'remove', 'dev-memory', '-g', '-a', *agents, '-y'], 'remove')
        assert before == [hashlib.sha256(path.read_bytes()).digest() for path in databases]
        assert not (home / '.codex/hooks.json').exists()
        for relative in dev_memory.AGENT_DIRS.values():
            assert not (home / relative / 'dev-memory').exists(), relative
        report = {'status': 'passed', 'source': 'local repository with public-compatible layout',
                  'installer': 'skills@1.7.2', 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                  'agents': agents, 'destinations': destinations, 'files_hash_checked': files_checked,
                  'install_reinstall_remove': True, 'memory_preserved': True, 'hooks_unchanged': True,
                  'remote_github_install': 'not run: repository not yet published',
                  'host_invocation': 'not established by copying files or doctor', 'commands': commands}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))

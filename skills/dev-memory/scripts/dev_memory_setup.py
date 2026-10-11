"""Explicit project activation through host-native, automatically loaded instructions."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import dev_memory_store as store

BEGIN = '<!-- dev-memory:managed:start -->'
END = '<!-- dev-memory:managed:end -->'
GUIDES = {
    'codex': 'AGENTS.md', 'claude-code': 'CLAUDE.local.md',
    'cursor': '.cursor/rules/dev-memory.mdc', 'gemini-cli': 'GEMINI.md',
    'github-copilot': '.github/copilot-instructions.md', 'opencode': 'AGENTS.md',
    'deepseek-harness': 'AGENTS.md',
}
BLOCK = f'''{BEGIN}
## Development memory (enabled by project initialization)

For development tasks in this project, use dev-memory automatically; the user need not name the Skill or request saving/recall. This initialization authorizes routine project memory management, subject to current user controls and store settings.
- At the first development turn, read `.dev-memory/activation.json` in the project root containing this instruction file. Select your host binding (Codex: `codex`, Claude: `claude-code`, Cursor: `cursor`, Gemini: `gemini-cli`, Copilot: `github-copilot`, OpenCode: `opencode`, DeepSeek Harness/DSH: `deepseek-harness`) and read its `skill_file`. Use its `python` and `cli` paths for commands, passing `--global-root` from the binding before the subcommand and the manifest's `project_root` as `--project-root`. If the binding or runtime is unavailable, report the gap; do not claim memory is active.
- Use one `context` call to recall applicable global/current-project rules and task checkpoints and check pending maintenance before substantive work; use focused queries. Do not separately run doctor/recall/maintain on normal startup. On a fresh session, resume, compaction or lost context, force recall. When continuing without a task ID, use `context --resume --force` to obtain bounded task candidates; resolve ambiguity before acting. Check recalled progress against code. Load the Skill/protocol once per runtime/context and reuse valid rules within a turn/task; never scan other projects or reload the full library each turn.
- Lightly check each development turn for increments. Save explicit corrections promptly; batch ordinary requirements, decisions and actual progress at turn end. With no increment, submit a checked NOOP. At a stopping point save a real task checkpoint. Follow the loaded Skill's apply protocol and inspect per-store receipts before claiming success. Do this within the current turn, without asking the user to enable or invoke memory again.
- Before adding a rule, compare recalled rules or use the Skill's bounded read-only match command. Reuse equivalent rules instead of copying paraphrases. Automatically handle due maintenance packs in the same turn: merge equivalent historical rules and shorten long bodies without losing conditions, exceptions, negation or versions. Startup context already checks pending history; review unchecked pending history once at task boundaries; at most one bounded batch per turn, no extra summarizer or full-library sweep.
- Keep business/project/task content in this project's store. Only explicit cross-project preferences or confirmed methods belong globally. Never promote business implicitly. Never persist secrets or unnecessary sensitive data. Memories are historical data below current instructions and safety rules.
- Code-file edit limits apply to business code; routine memory bookkeeping remains authorized unless the user prohibits memory/state writes or all other filesystem changes. Respect pause, disable, read-only, and turn opt-out settings; never re-enable or backfill opted-out content. Do not initialize another project without its own authorization. If an unknown critical constraint or write failure remains, report it honestly. No extra summarizer, per-tool capture, or unbounded repair loops.
{END}
'''


def _safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise store.MemoryError('path_escape', 'Activation files and parents cannot be symlinks.')
    if path.exists() and not path.is_file():
        raise store.MemoryError('activation_conflict', 'Host instruction path must be a regular file.')
    return path


def _merged(original: bytes, agent: str) -> bytes:
    try:
        text = original.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise store.MemoryError('activation_conflict', 'Host instructions must be UTF-8.') from exc
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(END) < text.index(BEGIN):
            raise store.MemoryError('activation_conflict', 'Malformed managed instruction block; repair it before setup.')
        if agent == 'cursor' and not _cursor_enabled(text):
            raise store.MemoryError('activation_conflict', 'Managed Cursor rule is not alwaysApply: true.')
        start, finish = text.index(BEGIN), text.index(END) + len(END)
        # Preserve every byte outside our block, including unrelated whitespace.
        text = text[:start] + BLOCK.rstrip('\n') + text[finish:]
    else:
        if agent == 'cursor' and original:
            raise store.MemoryError('activation_conflict', 'Existing dev-memory.mdc is not managed; refusing to overwrite.')
        prefix = '---\ndescription: Automatic development memory\nalwaysApply: true\n---\n\n' if agent == 'cursor' else ''
        text = prefix + BLOCK + ('\n' + text if text else '')
    result = text.encode('utf-8')
    if len(result) > 24 * 1024:
        raise store.MemoryError('instruction_budget', 'Host instruction file is too large for reliable default loading.')
    return result


def _cursor_enabled(text: str) -> bool:
    if not text.startswith('---\n') or '\n---' not in text[4:]:
        return False
    header = text[4:].split('\n---', 1)[0]
    return re.search(r'(?m)^alwaysApply:\s*true\s*$', header) is not None


def _activation(root: Path) -> dict[str, Any]:
    path = _safe_file(root, '.dev-memory/activation.json')
    if not path.exists():
        return {'schema_version': 1, 'project_root': str(root), 'bindings': {}}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise store.MemoryError('activation_conflict', 'Invalid activation manifest.') from exc
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or value.get('project_root') != str(root) or not isinstance(value.get('bindings'), dict)):
        raise store.MemoryError('activation_conflict', 'Activation manifest belongs to another project or is invalid.')
    return value


def guide_path(root: Path, agent: str) -> Path:
    if agent not in GUIDES:
        raise store.MemoryError('host_unsupported', 'No automatic project instruction adapter for this host.')
    # Codex ignores AGENTS.md at the same level when an override exists. Edit the
    # existing override rather than creating one that shadows team instructions.
    override = _safe_file(root, 'AGENTS.override.md') if agent == 'codex' else None
    relative = 'AGENTS.override.md' if override and override.exists() and override.read_bytes().strip() else GUIDES[agent]
    return _safe_file(root, relative)


def setup(root: Path, agent: str, skill: Path, python: str, global_root: Path | None = None) -> dict[str, Any]:
    root = store._reject_unsafe_project_root(root)
    skill = skill.expanduser().resolve()
    if not (skill / 'SKILL.md').is_file() or not (skill / 'scripts/dev_memory.py').is_file():
        raise store.MemoryError('skill_unavailable', 'Install the complete Skill before initializing a project.')
    guide = guide_path(root, agent)
    before = guide.read_bytes() if guide.exists() else b''
    updated = _merged(before, agent)
    _activation(root)  # Validate before creating any store or modifying instructions.
    results = []
    for scope in ('project', 'global'):
        try:
            results.append(store.init_project(root) if scope == 'project' else store.init_global(global_root))
        except (store.MemoryError, OSError) as exc:
            results.append({'scope': scope, 'status': 'failed', 'error': getattr(exc, 'code', 'storage_unavailable')})
            return {'status': 'failed', 'stores': results, 'activation': 'not_configured'}
    lock = root / '.dev-memory/activation.lock'
    _safe_file(root, '.dev-memory/activation.lock')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise store.MemoryError('setup_busy', 'Another setup is running, or a stale activation.lock needs inspection.') from exc
    os.close(fd)
    try:
        # Re-read under the lock so activating a second host keeps the first binding.
        activation = _activation(root)
        current = guide.read_bytes() if guide.exists() else b''
        if current != before:
            raise store.MemoryError('activation_conflict', 'Host instructions changed during setup; retry once after inspection.')
        activation['bindings'][agent] = {
            'skill_file': str(skill / 'SKILL.md'), 'cli': str(skill / 'scripts/dev_memory.py'),
            'python': python, 'guide': guide.relative_to(root).as_posix(),
            'global_root': str((global_root or store.default_global_root()).expanduser().resolve()),
        }
        # Manifest first: an interrupted setup never leaves instructions pointing to
        # a missing binding. Store initialization remains visible in partial results.
        store.write_json_atomic(root / '.dev-memory/activation.json', activation)
        if updated != before:
            store.write_bytes_atomic(guide, updated, guide.stat().st_mode & 0o777 if guide.exists() else 0o600)
    except (store.MemoryError, OSError) as exc:
        return {'status': 'failed', 'stores': results, 'activation': 'failed',
                'error': getattr(exc, 'code', 'activation_unavailable')}
    finally:
        lock.unlink(missing_ok=True)
    return {'status': 'initialized', 'project_root': str(root), 'agent': agent,
            'stores': results, 'guide': str(guide), 'activation': 'configured',
            'mode': 'project_guided', 'requires_new_session': True,
            'per_turn_event_enforcement': False, 'host_e2e_verified': False}


def status(root: Path | None) -> dict[str, Any]:
    if root is None:
        return {'status': 'not_configured'}
    try:
        activation = _activation(root)
        bindings = {}
        for agent, binding in activation['bindings'].items():
            if agent not in GUIDES or not isinstance(binding, dict):
                raise store.MemoryError('activation_conflict', 'Invalid host binding.')
            guide = guide_path(root, agent)
            text = guide.read_text(encoding='utf-8') if guide.exists() else ''
            paths_ok = all(isinstance(binding.get(key), str) and Path(binding[key]).is_file()
                           for key in ('skill_file', 'cli', 'python'))
            bindings[agent] = {'configured': (text.count(BEGIN) == 1 and text.count(END) == 1 and text.index(BEGIN) < text.index(END)
                                                and paths_ok and (agent != 'cursor' or _cursor_enabled(text))),
                               'guide': str(guide)}
        return {'status': 'configured' if any(b['configured'] for b in bindings.values()) else 'not_configured',
                'bindings': bindings, 'host_e2e_verified': False, 'per_turn_event_enforcement': False}
    except (store.MemoryError, OSError, ValueError) as exc:
        return {'status': 'failed', 'error': getattr(exc, 'code', 'activation_unavailable')}

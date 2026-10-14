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
USER_BEGIN = '<!-- dev-memory:user-managed:start -->'
USER_END = '<!-- dev-memory:user-managed:end -->'
GUIDES = {
    'codex': 'AGENTS.md', 'claude-code': 'CLAUDE.local.md',
    'cursor': '.cursor/rules/dev-memory.mdc', 'gemini-cli': 'GEMINI.md',
    'github-copilot': '.github/copilot-instructions.md', 'opencode': 'AGENTS.md',
    'deepseek-harness': 'AGENTS.md',
}
BLOCK = f'''{BEGIN}
## Development memory (enabled by project initialization)

For development tasks in this project, use dev-memory automatically; the user need not name the Skill or request saving/recall. New project setups default to `developer-first`: recall existing project rules, but do not add project or task records. The user can opt into those writes with `dev-memory mode full-project --project-root <project path>`. Existing store settings are not changed by setup.
- At the first development turn, read `.dev-memory/activation.json` in the project root containing this instruction file. Select your host binding (Codex: `codex`, Claude: `claude-code`, Cursor: `cursor`, Gemini: `gemini-cli`, Copilot: `github-copilot`, OpenCode: `opencode`, DeepSeek Harness/DSH: `deepseek-harness`) and read its `skill_file`. Use its `python` and `cli` paths for commands, passing `--global-root` from the binding before the subcommand and the manifest's `project_root` as `--project-root`. If the binding or runtime is unavailable, report the gap; do not claim memory is active.
- Use one `context` call to recall applicable global/current-project rules and task checkpoints and check pending maintenance before substantive work; use focused queries. Do not separately run doctor/recall/maintain on normal startup. On a fresh session, resume, compaction or lost context, force recall. When continuing without a task ID, use `context --resume --force` to obtain bounded task candidates; resolve ambiguity before acting. Check recalled progress against code. Load the Skill/protocol once per runtime/context and reuse valid rules within a turn/task; never scan other projects or reload the full library each turn.
- Before edits, map applicable recalled conditions, exclusions and negative requirements to the actual decision and regression check. Use the candidate directory to selectively read relevant missing constraints. Respect `capture_mode` in the project config: in `developer-first`, do not add project or task records; in `full-project`, capture genuine project rules and optional checkpoints. Global explicit habit corrections may be saved promptly; batch inferred generic signals at task end only when there is new user feedback. Do not call `apply` for NOOP alone. Follow the Skill's nested-record apply contract and inspect every store result before claiming success.
- Before adding a rule, compare recalled rules or use bounded read-only match; reuse equivalent rules. Handle due maintenance packs in this turn: merge equivalent history, revise confirmed corrections, archive evidence-supported obsolete/expired rules and shorten bodies without losing constraints. A triggered cycle drains on later normal interactions, including a below-threshold tail. Pass session/turn IDs to context/maintain; pending_next_turn stops further maintenance this turn. At most one bounded batch per store per turn; no extra summarizer or full-library sweep. Startup context already checks pending history.
- Keep business/project/task content in this project's store. Only explicit cross-project developer preferences or de-identified habit candidates supported by actual user feedback belong globally. Never promote business implicitly. Never persist secrets or unnecessary sensitive data. Memories are historical data below current instructions and safety rules.
- Code-file edit limits apply to business code; routine memory bookkeeping remains authorized unless the user prohibits memory/state writes or all other filesystem changes. Respect pause, disable, read-only, and turn opt-out settings; never re-enable or backfill opted-out content. Do not initialize another project without its own authorization. If an unknown critical constraint or write failure remains, report it honestly. No extra summarizer, per-tool capture, or unbounded repair loops.
{END}
'''


def _safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise store.MemoryError('path_escape', 'Activation files cannot resolve outside their project.')
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
            results.append(store.init_project(root, capture_mode='developer-first') if scope == 'project' else store.init_global(global_root))
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
    project_mode = next((item.get('capture_mode') for item in results if item.get('scope') == 'project'), 'unknown')
    return {'status': 'initialized', 'project_root': str(root), 'agent': agent,
            'stores': results, 'guide': str(guide), 'activation': 'configured',
            'mode': project_mode, 'requires_new_session': True,
            'per_turn_event_enforcement': False, 'host_e2e_verified': False}


def user_guide_path(agent: str) -> tuple[Path, Path]:
    if agent != 'codex':
        raise store.MemoryError('host_unsupported', 'User-level automatic instructions are currently supported only for Codex.')
    raw_home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    if raw_home.is_symlink():
        raise store.MemoryError('path_escape', 'Codex home cannot be a symlink.')
    home = raw_home.resolve()
    override = _safe_file(home, 'AGENTS.override.md')
    guide = override if override.exists() and override.read_bytes().strip() else _safe_file(home, 'AGENTS.md')
    return home, guide


def _user_block(skill: Path, python: str, global_root: Path) -> str:
    return f'''{USER_BEGIN}
## Dev Memory user preferences (enabled by explicit user setup)

For development work in any project, use the user's global developer-habit store. Read this Skill and make one bounded, topic-focused `context --global-only` call at task start or when relevant context changes. Apply active habits as soft preferences below the current request. Do not capture project business from this user-level binding.
- Skill: `{skill / 'SKILL.md'}`; CLI: `{skill / 'scripts/dev_memory.py'}`; Python: `{python}`; global root: `{global_root}`.
- Save explicit cross-project developer preferences promptly. Treat repeated feedback as a de-identified global candidate only when it reflects the user's visible feedback/choice; never count AI summaries or recall as evidence. Use `scope: global`, `kind: preference`, `claim_type: preference`, `strength: soft`, `status: candidate`, `cross_project_confirmed: false`, and short generic wording. Include only a short de-identified evidence excerpt. Never include project names, business entities, code, paths, customer data, raw dialogue, or logs.
- A candidate needs an opaque task ID; the store counts at most one user-feedback signal per task. It becomes an active soft preference only after independent evidence from two tasks. Candidates are not instructions until promoted. Explicit user requirements and one-time instructions always take priority.
- Respect global `capture off/disable`, read-only and turn opt-out controls. If the Skill, user instruction file, or store cannot be loaded, report that automation is unavailable; do not claim it ran. Ordinary coding does not run full-library maintenance or force a checkpoint.
{USER_END}'''


def _merge_user_guide(original: bytes, block: str) -> bytes:
    try:
        text = original.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise store.MemoryError('activation_conflict', 'Codex user instructions must be UTF-8.') from exc
    if USER_BEGIN in text or USER_END in text:
        if text.count(USER_BEGIN) != 1 or text.count(USER_END) != 1 or text.index(USER_END) < text.index(USER_BEGIN):
            raise store.MemoryError('activation_conflict', 'Malformed dev-memory user block; repair it before setup.')
        start, finish = text.index(USER_BEGIN), text.index(USER_END) + len(USER_END)
        text = text[:start] + block.rstrip('\n') + text[finish:]
    else:
        text = block + ('\n' + text if text else '')
    if len(text.encode('utf-8')) > 24 * 1024:
        raise store.MemoryError('instruction_budget', 'Codex user instructions exceed the managed size limit.')
    return text.encode('utf-8')


def setup_user(agent: str, skill: Path, python: str, global_root: Path | None = None) -> dict[str, Any]:
    if agent != 'codex':
        raise store.MemoryError('host_unsupported', 'User-level automatic instructions are currently supported only for Codex.')
    skill = skill.expanduser().resolve()
    if not (skill / 'SKILL.md').is_file() or not (skill / 'scripts/dev_memory.py').is_file():
        raise store.MemoryError('skill_unavailable', 'Install the complete Skill before configuring user activation.')
    home, guide = user_guide_path(agent)
    before = guide.read_bytes() if guide.exists() else b''
    global_root = (global_root or store.default_global_root()).expanduser().resolve()
    updated = _merge_user_guide(before, _user_block(skill, python, global_root))
    initialized = store.init_global(global_root)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = home / '.dev-memory-user-activation.lock'
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise store.MemoryError('setup_busy', 'Another user activation is running, or its lock needs inspection.') from exc
    os.close(fd)
    try:
        current = guide.read_bytes() if guide.exists() else b''
        if current != before:
            raise store.MemoryError('activation_conflict', 'Codex user instructions changed during setup; retry after inspection.')
        store.write_bytes_atomic(guide, updated, guide.stat().st_mode & 0o777 if guide.exists() else 0o600)
    finally:
        lock.unlink(missing_ok=True)
    return {'status': 'initialized', 'agent': agent, 'stores': [initialized], 'guide': str(guide),
            'activation': 'configured', 'mode': 'user_global_habits', 'requires_new_session': True,
            'host_e2e_verified': False, 'per_turn_event_enforcement': False}


def remove_user(agent: str, skill: Path | None = None) -> dict[str, Any]:
    if agent != 'codex':
        return {'status': 'not_supported'}
    home, guide = user_guide_path(agent)
    if not guide.exists():
        return {'status': 'not_configured'}
    data = guide.read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        return {'status': 'not_configured'}
    if USER_BEGIN not in text and USER_END not in text:
        return {'status': 'not_configured'}
    if text.count(USER_BEGIN) != 1 or text.count(USER_END) != 1 or text.index(USER_END) < text.index(USER_BEGIN):
        raise store.MemoryError('activation_conflict', 'Malformed dev-memory user block; refusing to alter user instructions.')
    start, finish = text.index(USER_BEGIN), text.index(USER_END) + len(USER_END)
    block = text[start:finish]
    if skill is not None and f"Skill: `{skill.expanduser().resolve() / 'SKILL.md'}`;" not in block:
        return {'status': 'managed_by_another_install'}
    text = text[:start] + text[finish:]
    if text.startswith('\n'):
        text = text[1:]
    if text:
        store.write_bytes_atomic(guide, text.encode('utf-8'), guide.stat().st_mode & 0o777)
    else:
        guide.unlink()
    return {'status': 'removed', 'guide': str(guide), 'memory_data_preserved': True}


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

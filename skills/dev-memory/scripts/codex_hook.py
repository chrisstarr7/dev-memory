#!/usr/bin/env python3
"""Optional Codex guidance and private-turn suppression. Never log transcripts."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import dev_memory_store as store

PROTOCOL = (
    'dev-memory: Follow the loaded Skill and user controls. On a new development task or changed topic, '
    'make one focused context call with task terms and optional --intent. Reuse valid context. '
    'Current instructions win. Assess user requirements and supported project knowledge in the primary assistant, '
    'including inspection/review turns needing no code edits; respect memory/all-write bans. Save important corrections '
    'before affected work and batch ordinary increments before final delivery. No increment needs no write '
    'or checked NOOP. Do not create task checkpoints or claim a save without a successful store receipt.'
)

PRIVATE_PHRASES = (
    '本轮不记', '这轮不记', '本次不记', '不要记住这次', '不要保存这轮', '不要保存本轮', '不要记忆本轮',
    '这一轮不要保存记忆', '这一轮不保存记忆',
    'do not remember this turn', "don't remember this turn", 'do not store this turn', "don't store this turn",
    'do not save this turn', "don't save this turn", 'do not save memory from this turn',
    'do not remember this', "don't remember this",
)


def _emit(event: str, context: str) -> None:
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}, ensure_ascii=False))


def _read_event() -> dict[str, Any]:
    raw = sys.stdin.read(2_000_001)
    if len(raw) > 2_000_000:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _is_private_skip(prompt: str) -> bool:
    return any(phrase in prompt.casefold() for phrase in PRIVATE_PHRASES)


def _handle_prompt(event: dict[str, Any]) -> None:
    prompt = event.get('prompt')
    if not isinstance(prompt, str) or not _is_private_skip(prompt):
        return  # No Git/database probes, baseline recall or receipt for ordinary prompts.
    session_id, turn_id = event.get('session_id'), event.get('turn_id')
    if not isinstance(session_id, str) or not session_id or not isinstance(turn_id, str) or not turn_id:
        _emit('UserPromptSubmit', 'Do not save this turn. Stable IDs are unavailable; persistent suppression was not recorded.')
        return
    cwd = event.get('cwd')
    root = store.locate_project_root(Path(cwd) if isinstance(cwd, str) else Path.cwd())
    scope = 'global'
    if root is not None:
        try:
            store._config_for('project', root, None)
            scope = 'both'
        except store.MemoryError:
            pass
    result = store.record_private_skip(scope, session_id=session_id, turn_id=turn_id, project_root=root)
    _emit('UserPromptSubmit', f"This turn was marked private; no content was saved. Receipt status: {result['status']}. Do not later ingest its content.")


def main() -> int:
    event = _read_event()
    name = str(event.get('hook_event_name') or event.get('event') or '')
    try:
        if name == 'SessionStart':
            suffix = ' Context was resumed/compacted: force one fresh focused recall before affected work.' if event.get('source') in {'resume', 'compact'} else ''
            _emit(name, PROTOCOL + suffix)
        elif name == 'UserPromptSubmit':
            _handle_prompt(event)
        # Older installed Stop handlers are harmless; there is no receipt gate or recovery turn.
    except (OSError, store.MemoryError, ValueError, sqlite3.Error):
        if name in {'SessionStart', 'UserPromptSubmit'}:
            _emit(name, 'Memory processing was unavailable; no operation is confirmed. Respect any private-turn request.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Optional Codex guidance and private-turn suppression. Never log transcripts."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import dev_memory_store as store

PROTOCOL = (
    'dev-memory: Follow the loaded Skill and user controls. On a new development task or changed topic, '
    'make one focused context call with task terms and optional --intent. Use --force for the first recall '
    'of a new conversation or after resume/compaction; reuse only bodies still visible here, not cached metadata. '
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


def capture_signal(prompt: str) -> str | None:
    """Conservative routing hint, never a semantic decision or evidence of verification."""
    if len(prompt) > 10000 or _is_private_skip(prompt):
        return None
    # Quotes/code/examples and temporary exceptions are deliberately left to the Skill.
    if any(word in prompt.casefold() for word in ('```', '举例', '例如', '示例', '引用', 'quote', 'example', '临时', '这次先', 'for this turn', 'temporarily')):
        return None
    text = re.sub(r'\s+', ' ', prompt).strip()
    patterns = (
        ('correction', r'^(?:纠正|更正|修正)(?:一下)?[：:，, ]|^把.{1,80}(?:记忆|约定|规则).{0,40}改(?:成|为)|^(?:correction:|correct the (?:memory|rule))'),
        ('durable_requirement', r'^(?:以后|今后|长期要求|长期约定)|(?:本项目|所有项目).{0,15}(?:长期|必须始终)|^(?:from now on|always for this project|for all future projects)'),
        ('verified_claim', r'^(?:已验证|验证确认|已经核实|已确认根因)[：:，, ]|^(?:verified:|confirmed root cause:)'),
    )
    return next((name for name, pattern in patterns if re.search(pattern, text, re.I)), None)


def _handle_prompt(event: dict[str, Any]) -> None:
    prompt = event.get('prompt')
    if not isinstance(prompt, str):
        return
    if not _is_private_skip(prompt):
        signal = capture_signal(prompt)
        # An actually delivered host event with stable IDs can trigger review. No store probe/write.
        if signal and all(isinstance(event.get(k), str) and 0 < len(event[k]) <= 200 for k in ('session_id', 'turn_id')):
            _emit('UserPromptSubmit', 'dev-memory capture review: '+signal+'. Review the current user message '
                  'under the loaded Skill before final delivery; save eligible durable increments with actual scope/source '
                  'and revision/duplicate checks. Important corrections precede affected edits. A verified_claim is only '
                  'a user claim until supported by actual tool evidence. Private/pause/disable/read-only controls win. '
                  'Use the host session/turn IDs for idempotency; do not retain the prompt or create task checkpoints. '
                  'This hint is not a save receipt and does not authorize a write.')
        return
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

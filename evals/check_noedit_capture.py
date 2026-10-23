"""Offline fixture and read-only outcome checks; a real host performs capture/recall."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/dev-memory/scripts'))
import dev_memory_setup as setup

PROMPT = ('本项目的 DTO/VO 类和字段需要 Swagger 注解，并沿用现有样式。'
          '请检查现有 AssetQueryDTO 和 AssetItemVO；如果已经符合就无需修改代码。')


def java_hashes(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(project.rglob('*.java'))}


def create_fixture(root, skill_path):
    root = Path(root).resolve()
    if root.is_relative_to(ROOT):
        raise ValueError('Place evaluation fixtures outside the source repository.')
    project, global_root = root / 'project', root / 'global-data'
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('Fixture directory must be empty; refusing to overwrite evidence.')
    project.mkdir()
    for name, description, field in [('AssetQueryDTO', 'Asset query', 'keyword'),
                                      ('AssetItemVO', 'Asset item', 'name')]:
        (project / (name + '.java')).write_text(
            'import io.swagger.annotations.ApiModel;\n'
            'import io.swagger.annotations.ApiModelProperty;\n\n'
            f'@ApiModel(value = "{name}", description = "{description}")\n'
            f'public class {name} {{\n'
            f'    @ApiModelProperty(value = "{field}")\n'
            f'    private String {field};\n}}\n', encoding='utf-8')
    initialized = setup.setup(project, 'codex', Path(skill_path), sys.executable, global_root)
    if initialized['status'] != 'initialized':
        raise RuntimeError(initialized)
    baseline = {'project_root': str(project), 'global_root': str(global_root),
                'java_hashes': java_hashes(project), 'prompt': PROMPT}
    (root / 'baseline.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding='utf-8')
    return baseline


def read_records(database):
    # mode=ro prevents inspection from initializing, migrating, or repairing a store.
    with contextlib.closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        records = [dict(row) for row in conn.execute('SELECT * FROM memories ORDER BY id')]
        for record in records:
            record['evidence'] = [dict(row) for row in conn.execute(
                'SELECT source_type, excerpt FROM evidence WHERE memory_id=?', (record['id'],))]
    return records


def desired_convention(record):
    # Topic/provenance screening only; a host result still needs semantic review.
    text = ' '.join(record.get(k, '') for k in ('title', 'content', 'conditions', 'do_text')).lower()
    return (record['scope'] == 'project' and record['kind'] == 'convention'
            and record['claim_type'] == 'desired' and record['status'] == 'active'
            and any(e['source_type'] in {'user_statement', 'user_confirmation', 'user_feedback'}
                    for e in record['evidence'])
            and 'dto' in text and 'vo' in text
            and bool(re.search(r'swagger|apimodel', text))
            and bool(re.search(r'注解|annotation', text))
            and bool(re.search(r'现有|沿用|保持.*样式|existing|same style|consistent', text)))


def inspect_fixture(root, recalled_ids=None):
    baseline = json.loads((Path(root) / 'baseline.json').read_text(encoding='utf-8'))
    project, global_root = Path(baseline['project_root']), Path(baseline['global_root'])
    records = read_records(project / '.dev-memory/memory.sqlite3')
    global_records = read_records(global_root / 'global/memory.sqlite3')
    matching = [r['id'] for r in records if desired_convention(r)]
    checks = {'java_unchanged': java_hashes(project) == baseline['java_hashes'],
              'user_sourced_active_project_convention': bool(matching),
              'no_global_records': not global_records,
              'no_checkpoints': not any(r['scope'] == 'task' or r['kind'] == 'checkpoint'
                                        for r in records + global_records)}
    if recalled_ids is not None:
        checks['later_recall_verified'] = bool(set(matching) & set(recalled_ids))
    return {'passed': all(checks.values()), 'checks': checks, 'matching_rule_ids': matching,
            'project_records': records, 'global_records': global_records}


def snapshot(root, recalled_ids=None, output=None):
    if output is not None and Path(output).resolve().is_relative_to(ROOT):
        raise ValueError('Write evaluation output outside the source repository.')
    result = inspect_fixture(root, recalled_ids)
    if output is not None:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--skill', type=Path, default=ROOT / 'skills/dev-memory')
    parser.add_argument('--recalled-ids', nargs='*', default=None)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = (create_fixture(args.root, args.skill) if args.create else
              snapshot(args.root, args.recalled_ids, args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.create or result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

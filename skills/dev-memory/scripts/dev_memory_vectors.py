"""Optional, bounded local vector indexing in the authoritative memory database."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import closing

DIMENSIONS = 384
BATCH_SIZE = 4
WORK_SECONDS = 10
QUERY_SECONDS = 5
EMBEDDING_FORMAT = "minilm-onnx-chunks96-v1"
MAX_DISTANCE = .60  # Calibrated on initial bilingual fixtures; retrieval never establishes rule applicability.


def _settings(global_root=None, *, cleanup=False):
    import dev_memory_store as store
    root = (global_root or store.default_global_root()).expanduser().resolve()
    runtime = root / 'vector-runtime'
    path = runtime / 'config.json'
    if runtime.is_symlink() or path.is_symlink() or not path.is_file():
        return None
    try:
        config = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            return None
        if config.get('enabled') is not True and not cleanup:
            return None
        for name in ('python', 'extension_path', 'model_cache'):
            target = Path(config[name])
            if target.is_symlink() or not target.resolve().is_relative_to(runtime.resolve()):
                return None
            if name != 'model_cache' and not target.is_file():
                return None
        if config.get('model_dir') and not Path(config['model_dir']).resolve().is_relative_to(runtime.resolve()):
            return None
        if not all(isinstance(config.get(key), str) and config[key] for key in ('model_name', 'model_fingerprint')):
            return None
        return config
    except (OSError, ValueError, KeyError, TypeError):
        return None


def enabled(global_root=None):
    return _settings(global_root) is not None


def _model_key(config):
    return config['model_fingerprint'] + ':' + EMBEDDING_FORMAT


def _exists(conn, table):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() is not None


def _schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS vector_state(
        memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL, model_key TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL, updated_at REAL NOT NULL, error TEXT NOT NULL DEFAULT '')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS vector_job(
        id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL,
        deadline REAL NOT NULL, state TEXT NOT NULL)''')


def _bump(conn):
    conn.execute("INSERT INTO meta(key,value) VALUES('vector_generation','1') ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")


def generation(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='vector_generation'").fetchone()
    return EMBEDDING_FORMAT + ':' + (row[0] if row else '0')


def on_change(conn, ids):
    """Invalidate before the source transaction commits; never require the extension."""
    if not _exists(conn, 'vector_state'):
        return
    for memory_id in ids:
        row = conn.execute('SELECT revision,status,claim_type FROM memories WHERE id=?', (memory_id,)).fetchone()
        if row:
            state = 'pending' if row[1] in ('active', 'conflicted') and row[2] != 'hypothesis' else 'inactive'
            conn.execute('''INSERT INTO vector_state(memory_id,revision,state,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(memory_id) DO UPDATE SET revision=excluded.revision,state=excluded.state,
                updated_at=excluded.updated_at,error='' ''', (memory_id, row[0], state, time.time()))
    _bump(conn)


def _load(conn, config):
    if config is None:
        raise sqlite3.OperationalError('vector_runtime_unavailable')
    expected = config.get('extension_sha256')
    if expected and hashlib.sha256(Path(config['extension_path']).read_bytes()).hexdigest() != expected:
        raise sqlite3.OperationalError('vector_extension_checksum_mismatch')
    try:
        conn.enable_load_extension(True)
        conn.load_extension(config['extension_path'])
    finally:
        if hasattr(conn, 'enable_load_extension'):
            conn.enable_load_extension(False)


def _vector_schema(conn):
    conn.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors USING vec0(
        memory_id TEXT PRIMARY KEY, embedding float[384] distance_metric=cosine)''')


def remove(conn, ids, global_root=None):
    ids = list(ids)
    if _exists(conn, 'memory_vectors'):
        _load(conn, _settings(global_root, cleanup=True))
        for memory_id in ids:
            conn.execute('DELETE FROM memory_vectors WHERE memory_id=?', (memory_id,))
    if _exists(conn, 'vector_state'):
        conn.executemany('DELETE FROM vector_state WHERE memory_id=?', ((i,) for i in ids))
        _bump(conn)


def reset(conn, global_root=None):
    if _exists(conn, 'memory_vectors'):
        _load(conn, _settings(global_root, cleanup=True))
        conn.execute('DELETE FROM memory_vectors')
    if _exists(conn, 'vector_state'):
        conn.execute('DELETE FROM vector_state')
    if _exists(conn, 'vector_job'):
        conn.execute('DELETE FROM vector_job')
    _bump(conn)


def _target(kind, project_root, global_root, write=False):
    import dev_memory_store as store
    _, database, config = store._config_for(kind, project_root, global_root)
    if config.get('excluded') or not config.get('recall_enabled', True):
        return database, config, False
    return database, config, not write or config.get('capture_enabled', True)


def status(kind, *, project_root=None, global_root=None, memory_id=None):
    import dev_memory_store as store
    settings = _settings(global_root)
    try:
        database, config, allowed = _target(kind, project_root, global_root)
        if not allowed:
            return {'status': 'disabled'}
        conn = store._connect(database, readonly=True)
        try:
            eligible = conn.execute("SELECT COUNT(*) FROM memories WHERE scope=? AND status IN ('active','conflicted') AND claim_type!='hypothesis'", (kind,)).fetchone()[0]
            ready = 0
            if settings and _exists(conn, 'vector_state'):
                ready = conn.execute("""SELECT COUNT(*) FROM vector_state v JOIN memories m ON m.id=v.memory_id
                    WHERE v.state='ready' AND v.revision=m.revision AND v.model_key=? AND m.scope=?
                    AND m.status IN ('active','conflicted') AND m.claim_type!='hypothesis'""",
                    (_model_key(settings), kind)).fetchone()[0]
            running = _exists(conn, 'vector_job') and conn.execute("SELECT 1 FROM vector_job WHERE state='running' AND deadline>?", (time.time(),)).fetchone() is not None
            result = {'status': 'running' if running else ('pending' if settings and eligible > ready else 'ready') if settings else 'unavailable',
                    'ready': ready, 'pending': eligible-ready, 'model': settings['model_name'] if settings else None,
                    'generation': generation(conn)}
            if _exists(conn, 'vector_job'):
                job = conn.execute('SELECT state,deadline FROM vector_job WHERE id=1').fetchone()
                if job and job[0] == 'failed' and job[1] > time.time():
                    result.update(reason='model_unavailable_or_timeout', retry_after_seconds=math.ceil(job[1]-time.time()))
            if memory_id and _exists(conn, 'vector_state'):
                row = conn.execute('''SELECT v.state,v.revision,v.error,v.model_key,m.revision
                    FROM vector_state v JOIN memories m ON m.id=v.memory_id WHERE v.memory_id=?''', (memory_id,)).fetchone()
                state = row[0] if row else 'pending'
                if not settings:
                    state = 'unavailable'
                elif row and (row[1] != row[4] or row[3] != _model_key(settings)):
                    state = 'pending'
                result['record'] = {'state': state, 'revision': row[1], 'error': row[2]} if row else {'state': state}
            return result
        finally:
            conn.close()
    except (store.MemoryError, sqlite3.Error, OSError, ValueError):
        return {'status': 'unavailable', 'reason': 'store_unavailable'}


def _flags():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}


def schedule(kind, *, project_root=None, global_root=None):
    import dev_memory_store as store
    settings = _settings(global_root)
    if not settings:
        return {'status': 'unavailable', 'reason': 'runtime_not_configured', 'raw_saved': True}
    database, config, allowed = _target(kind, project_root, global_root, write=True)
    if not allowed:
        return {'status': 'disabled'}
    conn = store._connect(database)
    token = secrets.token_hex(16)
    try:
        conn.execute('BEGIN IMMEDIATE')
        _schema(conn)
        previous = conn.execute('SELECT deadline,state FROM vector_job WHERE id=1').fetchone()
        if previous and previous[1] == 'failed' and previous[0] > time.time():
            conn.rollback()
            return {'status': 'deferred', 'reason': 'retry_backoff', 'raw_saved': True}
        if previous and previous[1] == 'running' and previous[0] > time.time():
            conn.rollback()
            return {'status': 'running'}
        conn.execute("""INSERT INTO vector_state(memory_id,revision,state,updated_at)
            SELECT id,revision,'pending',? FROM memories WHERE scope=? AND status IN ('active','conflicted')
            AND claim_type!='hypothesis' AND 1 ON CONFLICT(memory_id) DO NOTHING""", (time.time(), kind))
        pending = conn.execute("""SELECT 1 FROM vector_state v JOIN memories m ON m.id=v.memory_id
            WHERE m.scope=? AND m.status IN ('active','conflicted') AND m.claim_type!='hypothesis'
            AND (v.state!='ready' OR v.revision!=m.revision OR v.model_key!=?) LIMIT 1""",
            (kind, _model_key(settings))).fetchone()
        if not pending:
            conn.rollback()
            return {'status': 'ready'}
        conn.execute("INSERT OR REPLACE INTO vector_job VALUES(1,?,?,'running')", (token, time.time()+WORK_SECONDS))
        conn.commit()
    finally:
        conn.close()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--work', kind, '--token', token,
               '--global-root', str(global_root or store.default_global_root())]
    if project_root:
        command += ['--project-root', str(project_root)]
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, **_flags())
        # Reap a finished worker without making the saving CLI wait for inference.
        threading.Thread(target=process.wait, daemon=True).start()
    except OSError:
        with closing(store._connect(database)) as failed:
            with failed:
                failed.execute("UPDATE vector_job SET state='failed' WHERE token=?", (token,))
        return {'status': 'deferred', 'reason': 'worker_start_failed', 'raw_saved': True}
    return {'status': 'running', 'budget_seconds': WORK_SECONDS, 'raw_saved': True}


def finish(kind, *, project_root=None, global_root=None, wait_seconds=3):
    import dev_memory_store as store
    deadline = time.monotonic()+max(0, min(float(wait_seconds), 3))
    while True:
        result = status(kind, project_root=project_root, global_root=global_root)
        if result['status'] != 'running':
            return result
        if time.monotonic() >= deadline:
            database, _, allowed = _target(kind, project_root, global_root, write=True)
            if allowed:
                with closing(store._connect(database)) as conn:
                    with conn:
                        conn.execute("UPDATE vector_job SET deadline=0 WHERE state='running'")
            result.update(status='deferred', reason='finish_timeout', raw_saved=True)
            return result
        time.sleep(min(.05, max(0, deadline-time.monotonic())))


def _encode(texts, settings, *, query=False, timeout=2, cancelled=None):
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'TOKENIZERS_PARALLELISM': 'false', 'OMP_NUM_THREADS': '1'}
    command = [settings['python'], '-B', str(Path(__file__).resolve()), '--encode']
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env, **_flags())
    deadline = time.monotonic()+timeout
    message = json.dumps({'texts': texts, 'settings': settings, 'query': query})
    try:
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            if cancelled and cancelled():
                raise ValueError('index_cancelled')
            try:
                output, _ = process.communicate(input=message, timeout=min(.1, remaining) if cancelled else remaining)
                break
            except subprocess.TimeoutExpired:
                message = None
        if process.returncode:
            raise ValueError('model_unavailable')
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
    values = json.loads(output)
    if len(values) != len(texts) or any(len(v) != DIMENSIONS or any(not math.isfinite(x) for x in v) for v in values):
        raise ValueError('invalid_embedding')
    return values


def search(query, kind, *, project_root=None, global_root=None, query_cache=None, timeout=QUERY_SECONDS):
    import dev_memory_store as store
    settings = _settings(global_root)
    unavailable = {'status': 'unavailable', 'reason': 'runtime_not_configured', 'records': []}
    if not settings or not query.strip():
        return unavailable
    cache = query_cache if query_cache is not None else {}
    cache.setdefault('deadline', time.monotonic()+max(0, min(timeout, QUERY_SECONDS)))
    conn = None
    try:
        database, config, allowed = _target(kind, project_root, global_root)
        if not allowed:
            return {'status': 'disabled', 'records': []}
        conn = store._connect(database, readonly=True)
        if not _exists(conn, 'memory_vectors') or not _exists(conn, 'vector_state'):
            return {'status': 'pending', 'records': []}
        key = (_model_key(settings), query)
        if key not in cache:
            if cache.get('failed') or time.monotonic() >= cache['deadline']:
                return {'status': 'deferred', 'reason': 'query_timeout', 'records': []}
            cache[key] = _encode([query], settings, query=True, timeout=max(.001, cache['deadline']-time.monotonic()))[0]
        _load(conn, settings)
        conn.set_progress_handler(lambda: int(time.monotonic()>cache['deadline']), 1000)
        # Filter authoritative eligibility before ranking, so stale vectors cannot occupy all K slots.
        rows = conn.execute("""SELECT e.memory_id,vec_distance_cosine(e.embedding,?) AS distance
            FROM memory_vectors e JOIN vector_state v ON e.memory_id=v.memory_id
            JOIN memories m ON m.id=v.memory_id
            WHERE v.state='ready' AND v.revision=m.revision AND v.model_key=? AND m.scope=?
            AND m.status IN ('active','conflicted') AND m.claim_type!='hypothesis'
            ORDER BY distance LIMIT 20""", (json.dumps(cache[key]), _model_key(settings), kind)).fetchall()
        records = []
        for memory_id, distance in rows:
            valid = conn.execute("""SELECT 1 FROM vector_state v JOIN memories m ON m.id=v.memory_id
                WHERE m.id=? AND m.scope=? AND v.state='ready' AND v.revision=m.revision AND v.model_key=?
                AND m.status IN ('active','conflicted') AND m.claim_type!='hypothesis'""",
                (memory_id, kind, _model_key(settings))).fetchone()
            if valid and distance <= MAX_DISTANCE:
                records.append({'id': memory_id, 'distance': distance})
        return {'status': 'ok', 'records': records, 'model': settings['model_name']}
    except subprocess.TimeoutExpired:
        cache['failed'] = True
        return {'status': 'deferred', 'reason': 'query_timeout', 'records': []}
    except (OSError, ValueError, sqlite3.Error, store.MemoryError, AttributeError):
        cache['failed'] = True
        return {'status': 'unavailable', 'reason': 'query_unavailable', 'records': []}
    finally:
        if conn:
            conn.close()


def _work(kind, token, project_root, global_root):
    import dev_memory_store as store
    settings = _settings(global_root)
    database, config, allowed = _target(kind, project_root, global_root, write=True)
    if not settings or not allowed:
        return
    conn = store._connect(database, readonly=True)
    try:
        job = conn.execute("SELECT deadline FROM vector_job WHERE token=? AND state='running'", (token,)).fetchone()
        if not job or job[0] <= time.time():
            return
        rows = conn.execute("""SELECT m.id,m.revision FROM memories m LEFT JOIN vector_state v ON m.id=v.memory_id
            WHERE m.scope=? AND m.status IN ('active','conflicted') AND m.claim_type!='hypothesis'
            AND (v.state IS NULL OR v.state!='ready' OR v.revision!=m.revision OR v.model_key!=?)
            ORDER BY m.updated_at DESC,m.id LIMIT ?""", (kind, _model_key(settings), BATCH_SIZE)).fetchall()
        texts = []
        for memory_id, revision in rows:
            record = store._select_record(conn, memory_id)
            texts.append('\n'.join(store._field_text(record, k) for k in ('title','content','conditions','do','dont','exceptions')))
    finally:
        conn.close()
    failure = ''
    def cancelled():
        _, live_config, live_allowed = _target(kind, project_root, global_root, write=True)
        if not live_allowed or live_config['namespace_id'] != config['namespace_id']:
            return True
        with closing(store._connect(database, readonly=True)) as check:
            return check.execute("SELECT 1 FROM vector_job WHERE token=? AND state='running' AND deadline>?",
                                 (token, time.time())).fetchone() is None
    try:
        values = _encode(texts, settings, timeout=max(.001, job[0]-time.time()), cancelled=cancelled)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        values = []
        failure = 'model_unavailable_or_timeout'
    # No database write lock is held during model loading or inference.
    _, fresh, allowed = _target(kind, project_root, global_root, write=True)
    current_settings = _settings(global_root)
    conn = store._connect(database)
    try:
        conn.execute('BEGIN IMMEDIATE')
        # Recheck after lock acquisition: controls can change while the writer waits.
        _, fresh, allowed = _target(kind, project_root, global_root, write=True)
        current_settings = _settings(global_root)
        valid_job = conn.execute("SELECT deadline FROM vector_job WHERE token=? AND state='running'", (token,)).fetchone()
        if not valid_job or not allowed or fresh['namespace_id'] != config['namespace_id'] or not current_settings or _model_key(current_settings) != _model_key(settings):
            conn.rollback()
            return
        if valid_job[0] <= time.time():
            values = []
            failure = 'model_unavailable_or_timeout'
        if values:
            _load(conn, settings)
            _vector_schema(conn)
            for (memory_id, revision), vector in zip(rows, values):
                row = conn.execute("SELECT revision,status,claim_type FROM memories WHERE id=?", (memory_id,)).fetchone()
                if not row or row[0] != revision or row[1] not in ('active','conflicted') or row[2] == 'hypothesis':
                    continue
                conn.execute('DELETE FROM memory_vectors WHERE memory_id=?', (memory_id,))
                conn.execute('INSERT INTO memory_vectors(memory_id,embedding) VALUES(?,?)', (memory_id, json.dumps(vector)))
                conn.execute("""INSERT OR REPLACE INTO vector_state VALUES(?,?,?,'ready',?,'')""",
                             (memory_id, revision, _model_key(settings), time.time()))
            _bump(conn)
        conn.execute('UPDATE vector_job SET state=?,deadline=? WHERE token=?',
                     ('failed' if failure else 'done', time.time()+60 if failure else time.time(), token))
        if failure:
            conn.execute("UPDATE vector_state SET error=? WHERE state='pending'", (failure,))
        conn.commit()
    finally:
        conn.close()


def _infer(payload):
    """Run the pinned MiniLM ONNX graph without importing the download framework."""
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    config = payload['settings']
    model_dir = Path(config['model_dir'])
    tokenizer = Tokenizer.from_file(str(model_dir / 'tokenizer.json'))
    # The shipped tokenizer enables 128-token truncation; turn it off before splitting.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    boundaries = tokenizer.encode('').ids
    if len(boundaries) != 2:
        raise ValueError('unsupported_tokenizer_template')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    model = ort.InferenceSession(str(model_dir / 'model_optimized.onnx'), sess_options=options,
                                 providers=['CPUExecutionProvider'])
    input_names = {item.name for item in model.get_inputs()}
    values = []
    for text in payload['texts']:
        ids = tokenizer.encode(text, add_special_tokens=False).ids
        chunks = [ids[i:i+96] for i in range(0, len(ids), 80)] or [[]]
        pooled = []
        for chunk in chunks:
            tokens = np.asarray([[boundaries[0], *chunk, boundaries[1]]], dtype=np.int64)
            attention = np.ones_like(tokens)
            inputs = {'input_ids': tokens, 'attention_mask': attention,
                      'token_type_ids': np.zeros_like(tokens)}
            hidden = model.run(None, {key: value for key, value in inputs.items() if key in input_names})[0]
            vector = hidden.mean(axis=1)[0]
            length = np.linalg.norm(vector)
            if not length:
                raise ValueError('empty_embedding')
            pooled.append(vector/length)
        vector = np.mean(pooled, axis=0)
        length = np.linalg.norm(vector)
        if not length:
            raise ValueError('empty_embedding')
        values.append((vector/length).tolist())
    return values


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--encode', action='store_true')
    parser.add_argument('--work')
    parser.add_argument('--token')
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--global-root', type=Path)
    args = parser.parse_args()
    if args.encode:
        payload = json.load(sys.stdin)
        print(json.dumps(_infer(payload)))
    elif args.work:
        _work(args.work, args.token, args.project_root, args.global_root)


if __name__ == '__main__':
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    _main()

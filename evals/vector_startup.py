"""Opt-in cold-process timings; reads an installed runtime and uses synthetic text only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'dev-memory' / 'scripts'))
import dev_memory_vectors as vectors

TEXTS = ['request and response API documentation annotations', '接口模型注解']


def _profile(settings):
    """测量真实编码路径；包装仅计时，不替换模型、分词或池化逻辑。"""
    started = time.monotonic()
    timings = {}
    before = time.monotonic()
    import numpy
    timings['numpy_import'] = time.monotonic() - before
    before = time.monotonic()
    import onnxruntime as ort
    timings['onnxruntime_import'] = time.monotonic() - before
    before = time.monotonic()
    import tokenizers
    timings['tokenizers_import'] = time.monotonic() - before
    original_tokenizer, original_model = tokenizers.Tokenizer, ort.InferenceSession

    def load_tokenizer(*args, **kwargs):
        before = time.monotonic()
        result = original_tokenizer.from_file(*args, **kwargs)
        timings['tokenizer_load'] = time.monotonic() - before
        return result

    def load_model(*args, **kwargs):
        before = time.monotonic()
        model = original_model(*args, **kwargs)
        timings['model_load'] = time.monotonic() - before

        def run(*args, **kwargs):
            before = time.monotonic()
            result = model.run(*args, **kwargs)
            timings['inference'] = timings.get('inference', 0) + time.monotonic() - before
            return result

        return SimpleNamespace(get_inputs=model.get_inputs, run=run)

    tokenizers.Tokenizer = SimpleNamespace(from_file=load_tokenizer)
    ort.InferenceSession = load_model
    try:
        values = vectors._infer({'settings': settings, 'texts': TEXTS, 'query': True})
    finally:
        tokenizers.Tokenizer, ort.InferenceSession = original_tokenizer, original_model
    timings['worker_total'] = time.monotonic() - started
    return {'timings': timings, 'values': values}


def measure(runtime_root):
    """只读取现有运行配置，比较计时包装与正常子进程的完整向量。"""
    settings = vectors._settings(runtime_root)
    if not settings:
        raise ValueError('configured_vector_runtime_required')
    before = time.monotonic()
    child = subprocess.run([settings['python'], '-B', str(Path(__file__).resolve()), '--worker'],
                           input=json.dumps(settings), text=True, encoding='utf-8', capture_output=True,
                           timeout=30, env={**os.environ, 'HF_HUB_OFFLINE': '1',
                               'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
                               'OMP_NUM_THREADS': '1'}, **vectors._flags())
    elapsed = time.monotonic() - before
    if child.returncode:
        raise ValueError('profile_worker_failed')
    profiled = json.loads(child.stdout)
    before = time.monotonic()
    reference = vectors._encode(TEXTS, settings, query=True, timeout=30)
    reference_elapsed = time.monotonic() - before
    assert len(reference) == len(profiled['values']) == len(TEXTS)
    assert all(len(vector) == vectors.DIMENSIONS for vector in reference + profiled['values'])
    delta = max(abs(a - b) for left, right in zip(reference, profiled['values'])
                for a, b in zip(left, right))
    assert delta == 0, 'Timing instrumentation must preserve every embedding value'
    timings = profiled['timings']
    timings['process_imports_io_and_shutdown'] = elapsed - timings['worker_total']
    return {'platform': sys.platform, 'profile_seconds': round(elapsed, 4),
            'reference_seconds': round(reference_elapsed, 4), 'max_embedding_delta': delta,
            'stage_seconds': {key: round(value, 4) for key, value in timings.items()},
            'query_budget_seconds': vectors.QUERY_SECONDS}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(_profile(json.load(sys.stdin))))
    elif args.runtime_root:
        print(json.dumps(measure(args.runtime_root), ensure_ascii=False))
    else:
        parser.error('--runtime-root is required; this diagnostic never installs a runtime')

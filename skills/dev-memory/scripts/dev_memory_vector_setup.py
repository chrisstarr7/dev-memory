"""Install and verify optional local vector dependencies without changing memory stores."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PACKAGES = ("sqlite-vec==0.1.9", "fastembed==0.9.1")
UV_PACKAGE = "uv==0.13.6"

# This subprocess is also the offline health check; success requires real model inference.
PROBE = r'''
import hashlib,json,math,sqlite3,struct,sys
from pathlib import Path
import sqlite_vec
from fastembed import TextEmbedding
root=Path(sys.argv[1]).resolve()
download=sys.argv[2]=='download'
cache=root/'models'
name=sys.argv[3]
options=dict(model_name=name,cache_dir=str(cache),threads=1,providers=['CPUExecutionProvider'],local_files_only=not download)
if not download:
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    options['specific_model_path']=config['model_dir']
model=TextEmbedding(**options)
embedding=next(iter(model.embed(['接口字段变化时更新接口文档。'])))
assert len(embedding)==384 and all(math.isfinite(float(x)) for x in embedding)
db=sqlite3.connect(':memory:')
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)
db.execute('CREATE VIRTUAL TABLE vectors USING vec0(id integer primary key, embedding float[384])')
blob=struct.pack('<384f',*embedding)
db.execute('INSERT INTO vectors VALUES(1,?)',(blob,))
db.commit()
assert db.execute('SELECT id FROM vectors WHERE embedding MATCH ? AND k=1',(blob,)).fetchone()[0]==1
db.execute('BEGIN')
db.execute('DELETE FROM vectors WHERE id=1')
db.rollback()
assert db.execute('SELECT count(*) FROM vectors').fetchone()[0]==1
db.close()
directory=Path(model.model._model_dir).resolve()
assert directory.is_relative_to(cache.resolve())
artifacts={}
for item in sorted(directory.rglob('*')):
    if item.is_file():
        actual=item.resolve()
        assert actual.is_relative_to(cache.resolve())
        artifacts[str(actual.relative_to(root))]=hashlib.sha256(actual.read_bytes()).hexdigest()
extension=Path(sqlite_vec.loadable_path())
if not extension.is_file():
    extension=next((Path(str(extension)+suffix) for suffix in ('.dll','.dylib','.so') if Path(str(extension)+suffix).is_file()))
extension=extension.resolve()
assert extension.is_relative_to(root)
fingerprint=hashlib.sha256(json.dumps({'name':name,'artifacts':artifacts},sort_keys=True).encode()).hexdigest()
print(json.dumps(dict(model_name=name,model_cache=str(cache),model_dir=str(directory),model_fingerprint=fingerprint,
                     artifact_hashes=artifacts,extension_path=str(extension),extension_sha256=hashlib.sha256(extension.read_bytes()).hexdigest(),
                     runtime_python=sys.version.split()[0],runtime_sqlite=sqlite3.sqlite_version)))
'''


def _safe_root(global_root: Path) -> Path:
    """拒绝运行目录重定向，避免将可执行依赖写入陌生位置。"""
    base = global_root.expanduser().absolute()
    for path in (base, base / "vector-runtime"):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("unsafe_runtime_path")
    return base.resolve() / "vector-runtime"


def read_config(global_root: Path) -> dict:
    """只读获取运行配置，不触发安装或模型下载。"""
    root = _safe_root(global_root)
    path = root / "config.json"
    if path.is_symlink():
        raise ValueError("unsafe_config_path")
    if not path.exists():
        return {}
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("invalid_runtime_config")
    return result


def _run(command: list[str], deadline: float, *, offline: bool = False) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(command[0], 0)
    env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
           "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "1"}
    if offline:
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=remaining, env=env,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if result.returncode:
        # Dependencies can emit URLs and system details; do not copy their logs into memory or receipts.
        raise RuntimeError("dependency_or_probe_failed")
    return json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip().startswith("{") else {}


def _verify_artifacts(config: dict, root: Path) -> bool:
    directory = Path(config.get("model_dir", "")).resolve()
    if not directory.is_relative_to(root / "models") or config.get("model_name") != MODEL:
        return False
    artifacts = config.get("artifact_hashes")
    if not isinstance(artifacts, dict) or not artifacts:
        return False
    for relative, digest in artifacts.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    extension = Path(config.get("extension_path", "")).resolve()
    return (extension.is_relative_to(root) and extension.is_file()
            and hashlib.sha256(extension.read_bytes()).hexdigest() == config.get("extension_sha256"))


def _mac_intel() -> bool:
    return platform.system() == "Darwin" and platform.machine().lower() in {"x86_64", "amd64"}


def _mac() -> bool:
    return platform.system() == "Darwin"


def _packages() -> tuple[str, ...]:
    # FastEmbed requires ORT >=1.24.2 on CPython 3.14, which has no Intel macOS wheel.
    ort = "1.23.2" if _mac() or sys.version_info < (3, 14) else "1.31.1"
    return (*PACKAGES, "onnxruntime==" + ort)


def _compatible_python(root: Path, deadline: float) -> str:
    """Mac 使用支持 SQLite 扩展的独立 Python 3.12，保留宿主环境。"""
    if not _mac():
        return sys.executable
    if tuple(int(part) for part in platform.mac_ver()[0].split(".")[:1] if part) < (13,):
        raise RuntimeError("macos_13_required")
    directory = root / "python"
    bootstrap = root / "bootstrap"
    if directory.is_symlink() or bootstrap.is_symlink():
        raise ValueError("unsafe_runtime_path")
    architecture = "x86_64" if _mac_intel() else "aarch64"
    def existing() -> Path | None:
        for path in sorted(directory.glob(f"cpython-3.12.*-macos-{architecture}-*/bin/python3.12"), reverse=True):
            if path.is_file() and path.resolve().is_relative_to(root):
                return path
        return None
    if python := existing():
        return str(python)
    uv = bootstrap / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    if uv.is_symlink():
        raise ValueError("unsafe_runtime_path")
    if not uv.is_file():
        _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--only-binary=:all:",
              "--target", str(bootstrap), UV_PACKAGE], deadline)
    _run([str(uv), "python", "install", "--install-dir", str(directory),
          f"cpython-3.12-macos-{architecture}-none"], deadline)
    python = existing()
    if python is None:
        raise RuntimeError("managed_python_unavailable")
    return str(python)


def _setup(global_root: Path, *, timeout_seconds: float = 180) -> dict:
    """安装独立依赖并验证离线向量化；失败时保留普通记忆功能。"""
    deadline = time.monotonic() + max(1, min(float(timeout_seconds), 1800))
    phase = "preflight"
    try:
        root = _safe_root(global_root)
        config = read_config(global_root)
        if config.get("enabled") is False:
            return {"status": "disabled", "reason": "explicitly_disabled"}
        if not _mac():
            with closing(sqlite3.connect(":memory:")) as conn:
                if not hasattr(conn, "enable_load_extension"):
                    return {"status": "degraded", "reason": "sqlite_extensions_unsupported",
                            "message": "Use a Python build with SQLite extension support."}
                conn.enable_load_extension(True)
                conn.enable_load_extension(False)
        if root.exists() and any(path.is_symlink() for path in (root / "venv", root / "models")):
            raise ValueError("unsafe_runtime_path")
        packages = _packages()
        venv = root / ("venv-py312" if _mac() else "venv")
        if venv.is_symlink():
            raise ValueError("unsafe_runtime_path")
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if config.get("enabled") and config.get("packages") == list(packages) and _verify_artifacts(config, root):
            phase = "offline_probe"
            probe = _run([str(python), "-c", PROBE, str(root), "offline", MODEL], deadline, offline=True)
            if probe.get("model_fingerprint") == config.get("model_fingerprint"):
                return {"status": "ready", "reused": True, "model": MODEL,
                        "model_fingerprint": config["model_fingerprint"], "architecture": platform.machine()}
        root.mkdir(parents=True, exist_ok=True)
        phase = "environment"
        if not python.is_file():
            interpreter = _compatible_python(root, deadline)
            _run([interpreter, "-m", "venv", "--copies", str(venv)], deadline)
        phase = "dependencies"
        _run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--only-binary=:all:", *packages], deadline)
        phase = "model_and_probe"
        probe = _run([str(python), "-c", PROBE, str(root), "download", MODEL], deadline)
        if not probe.get("model_fingerprint"):
            raise RuntimeError("invalid_probe_result")
        config = {**probe, "enabled": True, "python": str(python), "packages": list(packages),
                  "architecture": platform.machine(), "dimension": 384}
        path = root / "config.json"
        if path.is_symlink():
            raise ValueError("unsafe_config_path")
        temporary = root / "config.json.tmp"
        if temporary.is_symlink():
            raise ValueError("unsafe_config_path")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return {"status": "ready", "reused": False, "model": MODEL,
                "model_fingerprint": config["model_fingerprint"], "architecture": platform.machine()}
    except subprocess.TimeoutExpired:
        return {"status": "degraded", "reason": "setup_timeout", "phase": phase}
    except RuntimeError as exc:
        reason = str(exc) if str(exc) in {"macos_13_required", "managed_python_unavailable"} else "setup_failed"
        return {"status": "degraded", "reason": reason, "phase": phase}
    except (OSError, ValueError, sqlite3.Error, KeyError):
        return {"status": "degraded", "reason": "setup_failed", "phase": phase}


def setup(global_root: Path, *, timeout_seconds: float = 180) -> dict:
    """串行化共享运行环境升级，防止不同项目同时安装同一个虚拟环境。"""
    lock = None
    try:
        root = _safe_root(global_root)
        if read_config(global_root).get("enabled") is False:
            return {"status": "disabled", "reason": "explicitly_disabled"}
        root.mkdir(parents=True, exist_ok=True)
        path = root / "setup.lock"
        # A crashed installer cannot retain the lock beyond the maximum allowed setup duration.
        if path.exists() and not path.is_symlink() and time.time() - path.stat().st_mtime > 1800:
            path.unlink()
        lock = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        return _setup(global_root, timeout_seconds=timeout_seconds)
    except FileExistsError:
        return {"status": "degraded", "reason": "setup_busy", "phase": "preflight"}
    except (OSError, ValueError):
        return {"status": "degraded", "reason": "setup_failed", "phase": "preflight"}
    finally:
        if lock is not None:
            os.close(lock)
            try:
                path.unlink()
            except OSError:
                pass

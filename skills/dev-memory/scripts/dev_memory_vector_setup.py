"""Install and verify optional local vector dependencies without changing memory stores."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import sqlite3
import subprocess
import struct
import sys
import sysconfig
import time
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PACKAGES = ("sqlite-vec==0.1.9", "fastembed==0.9.1")
UV_PACKAGE = "uv==0.13.6"


class SetupFailure(RuntimeError):
    def __init__(self, reason, message, remediation, exit_code=None):
        super().__init__(reason)
        self.details = dict(reason=reason, message=message, remediation=remediation)
        if exit_code is not None:
            self.details['exit_code'] = exit_code


def _command_failure(output: str, exit_code: int, pip: bool) -> SetupFailure:
    # Match categories locally; never return dependency logs, URLs or credentials.
    text = output.lower()
    categories = (
        (('certificate_verify_failed', 'certificate verify failed', 'sslcertverificationerror'),
         'certificate_error', '下载连接的 TLS 证书校验失败。', '配置可信的系统或企业 CA 证书；不要关闭证书校验。'),
        (('proxyerror', 'cannot connect to proxy', 'could not connect to proxy'),
         'proxy_error', '依赖下载代理连接失败。', '检查终端的代理配置与代理访问权限。'),
        (('401 error', '403 error', '401 client error', '403 client error', 'http error 401', 'http error 403'),
         'download_access_denied', '依赖或模型下载源拒绝访问。', '检查软件源认证和组织网络访问策略。'),
        (('connectionerror', 'connection refused', 'network is unreachable', 'temporary failure in name resolution',
          'getaddrinfo failed', 'nameresolutionerror', 'read timed out', 'the read operation timed out', 'connecttimeout', 'readtimeout', 'could not fetch url', 'failed to establish a new connection'),
         'download_network_error', '无法连接依赖或模型下载源。', '检查网络、DNS、代理及软件源访问权限后重新运行安装。'),
        (('no module named pip', "no module named 'pip'", 'no module named ensurepip', 'ensurepip is not available', 'no module named venv'),
         'python_environment_incomplete', 'Python 环境缺少 pip、venv 或 ensurepip。', '安装包含 pip 和虚拟环境组件的标准 CPython，再重新运行安装。'),
        (('permission denied', 'access is denied', 'winerror 5', 'errno 13'),
         'runtime_permission_denied', '向量运行目录或依赖文件没有写入权限。', '使用当前用户可写的运行目录，并检查文件占用或安全软件限制。'),
        (('resolutionimpossible', 'conflicting dependencies'),
         'dependency_conflict', '固定依赖版本无法共同解析。', '核对 Python 版本和软件源；若均符合要求，请提交此错误代码供维护者检查固定版本。'),
        (('no matching distribution found', 'could not find a version that satisfies the requirement'),
         'dependency_wheel_unavailable', '当前 Python、架构或软件源没有所需的二进制依赖包。', 'Windows 使用标准 64 位 CPython 3.14，并确认软件源提供所需版本；不要改为源码编译。'),
        (('dll load failed', 'winerror 126', 'library not loaded', 'wrong architecture', 'incompatible architecture'),
         'native_dependency_load_failed', '原生向量依赖加载失败。', '检查 Python 与依赖架构一致；Windows 还需核对 Visual C++ 运行库，macOS 核对系统版本。'),
    )
    for patterns, reason, message, remediation in categories:
        if any(pattern in text for pattern in patterns):
            return SetupFailure(reason, message, remediation, exit_code)
    return SetupFailure('dependency_install_failed' if pip else 'vector_probe_failed',
                        '依赖安装进程失败。' if pip else '向量环境验证进程失败。',
                        '检查安装前置条件；此结果尚不能判定具体环境原因。', exit_code)

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
        raise _command_failure(result.stderr + '\n' + result.stdout, result.returncode, 'pip' in command)
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


def _packages(version=None) -> tuple[str, ...]:
    # FastEmbed requires ORT >=1.24.2 on CPython 3.14, which has no Intel macOS wheel.
    version = tuple(version) if version is not None else sys.version_info
    ort = "1.23.2" if _mac() or version < (3, 14) else "1.31.1"
    return (*PACKAGES, "onnxruntime==" + ort)


def _windows_preflight(info: dict) -> None:
    if info['implementation'] != 'CPython' or not (3, 10) <= tuple(info['version']) <= (3, 14) or info['free_threaded']:
        raise SetupFailure('windows_python_unsupported', '向量功能需要标准 CPython 3.10–3.14，不支持自由线程版本。',
                           '安装标准 64 位 CPython 3.14，并用该解释器重新运行安装。')
    if info['bits'] != 64 or info['architecture'].lower() not in {'amd64', 'x86_64'}:
        raise SetupFailure('windows_architecture_unsupported', '当前固定向量依赖需要 Windows x64 Python。',
                           '安装标准 x64 CPython 3.14；32 位或原生 ARM64 Python 无对应 sqlite-vec 包。')


def _interpreter_info(python: Path, deadline: float) -> dict:
    code = "import importlib.util,json,platform,sqlite3,struct,sys,sysconfig; print(json.dumps(dict(version=list(sys.version_info[:2]),implementation=platform.python_implementation(),architecture=platform.machine(),bits=struct.calcsize('P')*8,free_threaded=bool(sysconfig.get_config_var('Py_GIL_DISABLED')),sqlite_extensions=hasattr(sqlite3.Connection,'enable_load_extension'),pip_available=importlib.util.find_spec('pip') is not None,prefix=sys.prefix)))"
    info = _run([str(python), '-c', code], deadline)
    if (not isinstance(info, dict) or not isinstance(info.get('version'), list) or len(info['version']) != 2
            or any(type(v) is not int for v in info['version']) or not isinstance(info.get('architecture'), str)
            or not isinstance(info.get('implementation'), str) or type(info.get('bits')) is not int
            or type(info.get('free_threaded')) is not bool or type(info.get('sqlite_extensions')) is not bool
            or type(info.get('pip_available')) is not bool or not isinstance(info.get('prefix'), str)):
        raise SetupFailure('runtime_info_invalid', '无法验证向量虚拟环境的解释器信息。', '检查虚拟环境完整性后重新运行安装。')
    return info


def _compatible_python(root: Path, deadline: float) -> str:
    """优先复用 npx 的专用 Python；直接 Python 安装仍保留 Mac 引导。"""
    if not _mac():
        return sys.executable
    if tuple(int(part) for part in platform.mac_ver()[0].split(".")[:1] if part) < (13,):
        raise RuntimeError("macos_13_required")
    shared = Path(os.environ.get("DEV_MEMORY_HOME") or Path.home() / ".dev-memory").expanduser().resolve()
    if (sys.version_info[:2] == (3, 12)
            and Path(sys.executable).resolve().is_relative_to(shared / "python-runtime" / "python")):
        return sys.executable
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
        if root.exists() and any(path.is_symlink() for path in (root / "venv", root / "models")):
            raise ValueError("unsafe_runtime_path")
        venv = root / ("venv-py312" if _mac() else "venv")
        if venv.is_symlink():
            raise ValueError("unsafe_runtime_path")
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        phase = "environment"
        if not python.is_file():
            if not _mac():
                if platform.system() == 'Windows':
                    _windows_preflight(dict(version=list(sys.version_info[:2]), implementation=platform.python_implementation(),
                                            architecture=platform.machine(), bits=struct.calcsize('P')*8,
                                            free_threaded=bool(sysconfig.get_config_var('Py_GIL_DISABLED'))))
                if any(importlib.util.find_spec(name) is None for name in ('venv', 'ensurepip')):
                    raise SetupFailure('python_environment_incomplete', 'Python 缺少虚拟环境或 ensurepip 组件。',
                                       '安装包含 pip 和虚拟环境组件的标准 CPython，再重新运行安装。')
            root.mkdir(parents=True, exist_ok=True)
            interpreter = _compatible_python(root, deadline)
            _run([interpreter, "-m", "venv", "--copies", str(venv)], deadline)
        info = _interpreter_info(python, deadline)
        if not _mac() and platform.system() == 'Windows':
            _windows_preflight(info)
        if not info['sqlite_extensions']:
            raise SetupFailure('sqlite_extensions_unsupported', '向量解释器不支持 SQLite 扩展加载。',
                               '使用支持 SQLite 扩展的标准 CPython；macOS 使用 Skill 管理的 Python 3.12。')
        if not info['pip_available']:
            if Path(info['prefix']).resolve() != venv.resolve():
                raise SetupFailure('runtime_environment_mismatch', '向量解释器没有绑定到预期虚拟环境，未修复 pip。',
                                   '检查 vector-runtime 中的虚拟环境配置；不要用系统 Python 替换其解释器。')
            # An interrupted venv can contain its interpreter before ensurepip completes.
            _run([str(python), '-m', 'ensurepip', '--upgrade'], deadline)
        packages = _packages(info['version'])
        if config.get("enabled") and config.get("packages") == list(packages) and _verify_artifacts(config, root):
            phase = "offline_probe"
            probe = _run([str(python), "-c", PROBE, str(root), "offline", MODEL], deadline, offline=True)
            if probe.get("model_fingerprint") == config.get("model_fingerprint"):
                return {"status": "ready", "reused": True, "model": MODEL,
                        "model_fingerprint": config["model_fingerprint"], "architecture": info['architecture']}
        phase = "dependencies"
        _run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--only-binary=:all:", *packages], deadline)
        phase = "model_and_probe"
        probe = _run([str(python), "-c", PROBE, str(root), "download", MODEL], deadline)
        if not probe.get("model_fingerprint"):
            raise RuntimeError("invalid_probe_result")
        config = {**probe, "enabled": True, "python": str(python), "packages": list(packages),
                  "architecture": info['architecture'], "dimension": 384}
        path = root / "config.json"
        if path.is_symlink():
            raise ValueError("unsafe_config_path")
        temporary = root / "config.json.tmp"
        if temporary.is_symlink():
            raise ValueError("unsafe_config_path")
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        return {"status": "ready", "reused": False, "model": MODEL,
                "model_fingerprint": config["model_fingerprint"], "architecture": info['architecture']}
    except subprocess.TimeoutExpired:
        return {"status": "degraded", "reason": "setup_timeout", "phase": phase}
    except SetupFailure as exc:
        return {"status": "degraded", "phase": phase, **exc.details}
    except PermissionError:
        return {"status": "degraded", "phase": phase, **_command_failure('permission denied', 1, False).details}
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
    except PermissionError:
        return {"status": "degraded", "phase": "preflight", **_command_failure('permission denied', 1, False).details}
    except (OSError, ValueError):
        return {"status": "degraded", "reason": "setup_failed", "phase": "preflight"}
    finally:
        if lock is not None:
            os.close(lock)
            try:
                path.unlink()
            except OSError:
                pass

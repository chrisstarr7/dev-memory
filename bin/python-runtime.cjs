'use strict';

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

const UV_VERSION = '0.13.6';
const TARGETS = {
  'win32-x64': ['x86_64-pc-windows-msvc.zip', 'a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f', 'cpython-3.12-windows-x86_64-none'],
  'darwin-x64': ['x86_64-apple-darwin.tar.gz', '63ba17fdda55ad1a230d4b37fc6017ffa10c23688c83818bd3bfdf914c652a02', 'cpython-3.12-macos-x86_64-none'],
  'darwin-arm64': ['aarch64-apple-darwin.tar.gz', '60fbd5c8a1ed681845eea28d9d622fcde03c51e91a43465b64a1e17db1ed3472', 'cpython-3.12-macos-aarch64-none'],
};
const PROBE = "import json,platform,sqlite3,struct,sys,venv,ensurepip; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); c.enable_load_extension(False); c.close(); print(json.dumps(dict(version=list(sys.version_info[:2]),implementation=platform.python_implementation(),architecture=platform.machine().lower(),bits=struct.calcsize('P')*8,executable=sys.executable)))";

function failure(code, message) {
  return Object.assign(new Error(message), { code });
}

function inside(base, target) {
  const relative = path.relative(base, target);
  return relative !== '' && !relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative);
}

// Reject links before any write or execution, including existing parent junctions.
function safePath(target) {
  const absolute = path.resolve(target);
  let current = absolute;
  while (true) {
    try {
      if (fs.lstatSync(current).isSymbolicLink()) throw failure('python_runtime_unsafe_path', '专用 Python 路径包含符号链接或目录联接；请检查运行目录。');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return absolute;
}

function childEnv(root) {
  const env = { ...process.env, PYTHONUTF8: '1', UV_PYTHON_INSTALL_DIR: path.join(root, 'python'),
    UV_PYTHON_BIN_DIR: path.join(root, 'bin'), UV_CACHE_DIR: path.join(root, 'cache'),
    UV_PYTHON_INSTALL_BIN: '0', UV_PYTHON_INSTALL_REGISTRY: '0', UV_NO_CONFIG: '1' };
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  return env;
}

function run(command, args, root, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) throw failure('python_runtime_timeout', '专用 Python 准备超时；可重新执行安装命令。');
  const result = spawnSync(command, args, { encoding: 'utf8', windowsHide: true,
    timeout: remaining, maxBuffer: 1024 * 1024, env: childEnv(root), cwd: root });
  if (result.error || result.status !== 0) throw failure(
    result.error?.code === 'ETIMEDOUT' ? 'python_runtime_timeout' : 'python_runtime_command_failed',
    '专用 Python 准备进程失败；请检查网络、证书及目录权限后重试。');
  return result.stdout.trim();
}

function validatePython(python, root, deadline) {
  if (typeof python !== 'string' || !path.isAbsolute(python) || !inside(path.join(root, 'python'), python)) {
    throw failure('python_runtime_unsafe_path', '专用 Python 记录指向运行目录之外；未执行该程序。');
  }
  const directory = safePath(path.join(root, 'python'));
  const resolved = fs.realpathSync(python);
  if (!inside(directory, resolved) || !fs.statSync(resolved).isFile()) {
    throw failure('python_runtime_unsafe_path', '专用 Python 解释器路径不安全。');
  }
  // uv maintains minor-version aliases; execute and persist only their in-directory real target.
  safePath(resolved);
  const info = JSON.parse(run(resolved, ['-I', '-c', PROBE], root, Math.min(deadline, Date.now() + 10000)));
  if (info.implementation !== 'CPython' || JSON.stringify(info.version) !== '[3,12]' || info.bits !== 64
      || !(process.arch === 'arm64' ? ['arm64','aarch64'] : ['x86_64','amd64']).includes(info.architecture)
      || path.resolve(info.executable) !== resolved) {
    throw failure('python_runtime_invalid', '专用 Python 校验失败；需要完整的 64 位 CPython 3.12。');
  }
  return resolved;
}

function existing(root, deadline) {
  const manifest = safePath(path.join(root, 'runtime.json'));
  if (!fs.existsSync(manifest)) return null;
  try {
    if (fs.statSync(manifest).size > 8192) return null;
    const info = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    if (!info || typeof info.python !== 'string') return null;
    return validatePython(info.python, root, deadline);
  } catch (error) {
    if (error.code === 'python_runtime_unsafe_path') throw error;
    return null;
  }
}

function download(url, expectedHash, root, deadline) {
  const timeout = Math.min(60000, deadline - Date.now());
  if (timeout <= 0) throw failure('python_runtime_timeout', '专用 Python 准备超时；可重新执行安装命令。');
  const curl = process.platform === 'win32'
    ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'curl.exe') : '/usr/bin/curl';
  const result = spawnSync(curl, ['--proto', '=https', '--proto-redir', '=https', '--location', '--fail',
    '--silent', '--show-error', '--max-time', String(timeout / 1000), '--max-filesize', String(80 * 1024 * 1024), url],
    { timeout, maxBuffer: 80 * 1024 * 1024, windowsHide: true, cwd: root, env: childEnv(root) });
  if (result.error) {
    if (result.error.code === 'ENOBUFS') throw failure('python_runtime_download_limit', '专用 Python 引导下载超出大小限制。');
    throw result.error;
  }
  if (result.status === 28) throw failure('python_runtime_timeout', '专用 Python 下载超时；请检查网络和代理后重试。');
  if (result.status === 60) throw failure('python_runtime_certificate_error', '专用 Python 下载证书校验失败；请配置可信 CA 证书，不要关闭 TLS 校验。');
  if ([5, 6, 7].includes(result.status)) throw failure('python_runtime_network_error', '无法连接专用 Python 下载源；请检查网络、DNS 和代理设置。');
  if (result.status === 22) throw failure('python_runtime_download_access_denied', '专用 Python 下载源返回 HTTP 错误；请检查访问权限或稍后重试。');
  if (result.status === 63) throw failure('python_runtime_download_limit', '专用 Python 引导下载超出大小限制。');
  const data = result.stdout;
  if (result.status !== 0 || !Buffer.isBuffer(data) || data.length === 0) throw failure('python_runtime_download_failed', '专用 Python 引导下载失败；请检查下载源访问权限。');
  if (crypto.createHash('sha256').update(data).digest('hex') !== expectedHash) {
    throw failure('python_runtime_hash_mismatch', '专用 Python 引导完整性校验失败；未执行下载文件。');
  }
  return data;
}

async function ensurePython({ allowDownload = true, onProgress = () => {} } = {}) {
  const target = TARGETS[`${process.platform}-${process.arch}`];
  if (!target) throw failure('python_runtime_platform_unsupported', '自动 Python 环境支持 Windows x64 及 macOS Intel/Apple Silicon。');
  const root = safePath(path.resolve(process.env.DEV_MEMORY_HOME || path.join(os.homedir(), '.dev-memory'), 'python-runtime'));
  const deadline = Date.now() + 180000;
  try {
    const python = existing(root, deadline);
    if (python) return python;
    if (!allowDownload) throw failure('python_runtime_missing', '尚未准备专用 Python；请执行安装命令。');
    if (process.env.UV_PYTHON_DOWNLOADS === 'never' || process.env.UV_OFFLINE === '1') {
      throw failure('python_runtime_download_disabled', '当前环境禁止下载 Python；已有有效专用解释器可离线复用，否则需先允许下载。');
    }
    fs.mkdirSync(root, { recursive: true, mode: 0o700 });
    const lockPath = safePath(path.join(root, 'setup.lock'));
    const waitUntil = Date.now() + 30000;
    let lock;
    while (lock === undefined) {
      try { lock = fs.openSync(lockPath, 'wx', 0o600); }
      catch (error) {
        if (error.code !== 'EEXIST') throw error;
        const python = existing(root, deadline);
        if (python) return python;
        // shortcut: a crashed installer leaves its lock; review/remove it only after confirming its owner exited.
        if (Date.now() >= waitUntil) throw failure('python_runtime_busy', '另一个安装进程正在准备 Python；请稍后重试。若进程已异常退出，请检查 python-runtime/setup.lock。');
        await delay(250);
      }
    }
    const token = crypto.randomUUID();
    fs.writeFileSync(lock, JSON.stringify({ pid: process.pid, token }));
    let staging, archivePath, uv;
    try {
      const cached = existing(root, deadline);
      if (cached) return cached;
      onProgress('正在准备 dev-memory 专用 Python；不会修改系统 Python 或 PATH。');
      const [asset, digest, request] = target;
      const archive = download(`https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${asset}`, digest, root, deadline);
      staging = safePath(path.join(root, `bootstrap-${crypto.randomUUID()}`));
      fs.mkdirSync(staging, { mode: 0o700 });
      archivePath = path.join(staging, `uv-${asset}`);
      fs.writeFileSync(archivePath, archive, { mode: 0o600, flag: 'wx' });
      const windows = process.platform === 'win32';
      const member = windows ? 'uv.exe' : `uv-${asset.replace('.tar.gz', '')}/uv`;
      const tar = windows ? path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe') : '/usr/bin/tar';
      run(tar, ['-xf', archivePath, '-C', staging, member], root, deadline);
      uv = safePath(path.join(staging, member));
      if (!fs.statSync(uv).isFile()) throw failure('python_runtime_extract_failed', '未能解压 Python 引导程序。');
      safePath(path.join(root, 'python'));
      safePath(path.join(root, 'cache'));
      const install = ['python', 'install', '--install-dir', path.join(root, 'python'), '--no-bin', '--no-registry', '--no-config', request];
      // uv checks its own installation cache first; reinstall only after the cached probe failed.
      if (fs.existsSync(path.join(root, 'runtime.json'))) install.push('--reinstall');
      run(uv, install, root, deadline);
      const found = run(uv, ['python', 'find', '--managed-python', '--no-python-downloads', '--no-project', '--no-config', request], root, deadline);
      const python = validatePython(found, root, deadline);
      const temporary = safePath(path.join(root, `runtime-${token}.json`));
      fs.writeFileSync(temporary, JSON.stringify({ python, version: '3.12' }) + '\n', { mode: 0o600, flag: 'wx' });
      fs.renameSync(temporary, path.join(root, 'runtime.json'));
      return python;
    } finally {
      // Only these known temporary files are disposable; downloaded Python remains shared.
      try {
        if (archivePath && fs.existsSync(archivePath)) fs.unlinkSync(safePath(archivePath));
        if (uv && fs.existsSync(uv)) fs.unlinkSync(safePath(uv));
        if (uv && path.dirname(uv) !== staging) fs.rmdirSync(safePath(path.dirname(uv)));
        if (staging) fs.rmdirSync(safePath(staging));
      } catch { /* Cleanup failure must not invalidate a verified interpreter. */ }
      fs.closeSync(lock);
      if (JSON.parse(fs.readFileSync(safePath(lockPath), 'utf8')).token === token) fs.unlinkSync(lockPath);
    }
  } catch (error) {
    if (typeof error.code === 'string' && error.code.startsWith('python_runtime_')) throw error;
    const cause = typeof error.cause?.code === 'string' ? error.cause.code : error.code;
    if (['TimeoutError','AbortError'].includes(error.name) || ['ETIMEDOUT','UND_ERR_CONNECT_TIMEOUT','UND_ERR_HEADERS_TIMEOUT'].includes(cause)) {
      throw failure('python_runtime_timeout', '专用 Python 下载或准备超时；请检查网络和代理后重试。');
    }
    if (typeof cause === 'string' && /CERT|SELF_SIGNED|UNABLE_TO_VERIFY/.test(cause)) {
      throw failure('python_runtime_certificate_error', '专用 Python 下载证书校验失败；请配置可信 CA 证书，不要关闭 TLS 校验。');
    }
    if (['ENOTFOUND','EAI_AGAIN','ECONNREFUSED','ECONNRESET','UND_ERR_SOCKET'].includes(cause)) {
      throw failure('python_runtime_network_error', '无法连接专用 Python 下载源；请检查网络、DNS 和代理设置。');
    }
    throw failure('python_runtime_failed', '专用 Python 环境准备失败；请检查网络、证书和运行目录权限。系统 Python 未修改。');
  }
}

module.exports = { ensurePython };

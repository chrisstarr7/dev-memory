#!/usr/bin/env node
'use strict';

// npx handles transport; Python provides installation and dashboard commands.
const { spawn, spawnSync } = require('node:child_process');
const path = require('node:path');
const args = process.argv.slice(2);
const project = process.cwd();
const json = args.includes('--json');

function fail(error, message) {
  if (json) console.log(JSON.stringify({ status: 'failed', error, message }));
  else console.error(message);
  process.exit(1);
}

// Reject malformed lifecycle requests before preparing a runtime; Python owns full CLI validation.
function installationRequested() {
  const aliases = {claude: 'claude-code', gemini: 'gemini-cli', copilot: 'github-copilot',
    deepseek: 'deepseek-harness', dsh: 'deepseek-harness'};
  const hosts = new Set(['codex', 'claude-code', 'cursor', 'gemini-cli', 'github-copilot', 'opencode', 'deepseek-harness']);
  const values = new Set(['--agent', '--project', '--target']);
  const switches = new Set(['--upgrade', '--with-codex-hooks', '--json', '--without-vectors']);
  const positional = [];
  let option;
  for (let i = 0; i < args.length; i++) {
    const [flag, ...value] = args[i].split('=');
    if (!flag.startsWith('-')) positional.push(args[i]);
    else if (values.has(flag)) {
      const argument = value.length ? value.join('=') : args[++i];
      if (!argument || argument.startsWith('--')) return false;
      if (flag === '--agent') option = aliases[argument] || argument;
    } else if (!switches.has(args[i])) return false;
  }
  if (['update', 'uninstall'].includes(positional[0])) positional.shift();
  if (positional.length > 1) return false;
  const host = aliases[positional[0]] || positional[0];
  return hosts.has(host || option) && (!host || !option || host === option);
}

async function main() {
  const { ensurePython } = require('./python-runtime.cjs');
  const actionable = installationRequested() || (args[0] === 'dashboard' && !args.includes('--help') && !args.includes('-h'));
  let python;
  if (process.platform === 'win32' || process.platform === 'darwin') {
    try {
      python = [await ensurePython({ allowDownload: actionable,
        onProgress: message => { if (!json) console.error(message); } })];
    } catch (error) {
      if (actionable) fail(error.code || 'python_runtime_failed', error.message);
    }
  }
  if (!python) {
    const candidates = process.platform === 'win32'
      ? [['py', '-3.14'], ['py', '-3'], ['python3'], ['python']]
      : [['python3'], ['python']];
    const check = 'import sys, sqlite3; sqlite3.connect(":memory:").close(); sys.exit(0 if sys.version_info >= (3, 10) else 1)';
    python = candidates.find(([command, ...prefix]) => {
      const result = spawnSync(command, [...prefix, '-c', check], { encoding: 'utf8', timeout: 5000 });
      return !result.error && result.status === 0;
    });
  }
  if (!python) fail('python_unavailable', '未找到可用 Python。Windows/macOS 请指定宿主执行安装命令以自动准备专用环境；其他入口需要 Python 3.10+。');
  const env = { ...process.env };
  delete env.PYTHONHOME;
  delete env.PYTHONPATH;
  if (args[0] === 'dashboard') {
    const [command, ...prefix] = python;
    const child = spawn(command, [...prefix, '-B', path.join(__dirname, '..', 'skills', 'dev-memory', 'scripts', 'dev_memory.py'), ...args], {
      cwd: project, stdio: 'inherit', env,
    });
    child.on('error', error => fail('dashboard_start_failed', '无法启动本地看板：' + error.message));
    child.on('exit', (code, signal) => process.exit(signal ? 1 : (code ?? 1)));
  } else {
    if (!['update', 'uninstall'].includes(args[0]) && !args.some(arg => arg === '--project' || arg.startsWith('--project='))) {
      args.push('--project', project);
    }
    const [command, ...prefix] = python;
    const result = spawnSync(command, [...prefix, '-B', path.join(__dirname, '..', 'install.py'), ...args], {
      cwd: project, stdio: 'inherit', env, timeout: 240000,
    });
    if (result.error) {
      fail('installation_process_failed', result.error.code === 'ETIMEDOUT'
        ? '安装超时；部分程序或空库可能已创建，请检查后重试同一命令。'
        : '无法运行安装程序：' + result.error.message);
    }
    process.exit(result.status === null ? 1 : result.status);
  }
}

main().catch(() => fail('python_runtime_failed', '专用 Python 环境准备失败；未修改系统 Python，请检查网络和运行目录权限。'));

#!/usr/bin/env node
'use strict';

// npx handles transport; install.py handles both codex and update codex.
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const args = process.argv.slice(2);
const project = process.cwd();
const json = args.includes('--json');

function fail(error, message) {
  if (json) console.log(JSON.stringify({ status: 'failed', error, message }));
  else console.error(message);
  process.exit(1);
}

const candidates = process.platform === 'win32'
  ? [['py', '-3'], ['python3'], ['python']]
  : [['python3'], ['python']];
const check = 'import sys, sqlite3; sqlite3.connect(":memory:").close(); sys.exit(0 if sys.version_info >= (3, 10) else 1)';
const python = candidates.find(([command, ...prefix]) => {
  const result = spawnSync(command, [...prefix, '-c', check], { encoding: 'utf8', timeout: 5000 });
  return !result.error && result.status === 0;
});
if (!python) fail('python_unavailable', '需要 Python 3.10+（含 sqlite3）。请安装后重试同一命令。');
if (!args.some(arg => arg === '--project' || arg.startsWith('--project='))) {
  args.push('--project', project);
}
const [command, ...prefix] = python;
const result = spawnSync(command, [...prefix, '-B', path.join(__dirname, '..', 'install.py'), ...args], {
  cwd: project, stdio: 'inherit', timeout: 240000,
});
if (result.error) {
  fail('installation_process_failed', result.error.code === 'ETIMEDOUT'
    ? '安装超时；部分程序或空库可能已创建，请检查后重试同一命令。'
    : '无法运行安装程序：' + result.error.message);
}
process.exit(result.status === null ? 1 : result.status);

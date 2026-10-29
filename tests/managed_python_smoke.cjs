'use strict';

// Opt-in native CI: only synthetic stores under the explicitly supplied runtime root.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { ensurePython } = require('../bin/python-runtime.cjs');

async function main() {
  assert(process.env.DEV_MEMORY_HOME && path.isAbsolute(process.env.DEV_MEMORY_HOME));
  const root = path.resolve(process.env.DEV_MEMORY_HOME);
  const source = path.resolve(__dirname, '..');
  const originalPath = process.env.PATH;
  // A missing or obsolete system Python cannot participate in this installation.
  process.env.PATH = '';
  const python = await ensurePython({ onProgress: console.error });
  const offlineEnv = { ...process.env, UV_OFFLINE: '1', UV_PYTHON_DOWNLOADS: 'never' };
  process.env.UV_OFFLINE = '1';
  assert.equal(await ensurePython(), python);
  delete process.env.UV_OFFLINE;
  const env = { ...process.env, DEV_MEMORY_VECTOR_SETUP: '0' };
  const run = (command, args, options = {}) => {
    const result = spawnSync(command, args, { cwd: source, env, encoding: 'utf8',
      windowsHide: true, timeout: 240000, ...options });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    return result.stdout;
  };
  const target = path.join(root, 'smoke-skill');
  const cli = path.join(target, 'scripts', 'dev_memory.py');
  for (const name of ['smoke-project-a', 'smoke-project-b']) {
    const project = path.join(root, name);
    fs.mkdirSync(project, { recursive: true });
    const receipt = JSON.parse(run(process.execPath, [path.join(source, 'bin/install.cjs'),
      'opencode', '--without-vectors', '--project', project, '--target', target, '--json']));
    assert.equal(receipt.status, 'installed');
    const binding = JSON.parse(fs.readFileSync(path.join(project, '.dev-memory', 'activation.json'))).bindings.opencode;
    assert.equal(path.resolve(binding.python), path.resolve(python));
    // Daily memory is called directly; Node and uv are absent from PATH and downloads are disabled.
    const context = JSON.parse(run(python, ['-B', cli, '--global-root', root, 'context',
      '--project-root', project, '--query', 'isolated runtime', '--readonly'], { env: offlineEnv }));
    assert.equal(context.status, 'ok');
  }
  assert.equal(process.env.PATH, '');
  process.env.PATH = originalPath;
  if (process.env.DEV_MEMORY_VECTOR_INTEGRATION === '1') {
    // Real model checks run in the same managed base used by npx, on all native CI architectures.
    run(python, ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_vector_integration.py', '-v'],
      { env: { ...process.env, DEV_MEMORY_VECTOR_ROOT: root }, timeout: 480000 });
    const vector = JSON.parse(fs.readFileSync(path.join(root, 'vector-runtime', 'config.json')));
    if (process.platform === 'darwin') {
      assert(!fs.existsSync(path.join(root, 'vector-runtime', 'python')), 'Mac downloaded another base Python');
    }
    assert(path.resolve(vector.python).startsWith(path.join(root, 'vector-runtime') + path.sep));
  }
  console.log(JSON.stringify({ status: 'ok', system_python_required: false,
    shared_interpreter: python, projects: 2, daily_memory_without_node: true,
    vectors_checked: process.env.DEV_MEMORY_VECTOR_INTEGRATION === '1' }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });

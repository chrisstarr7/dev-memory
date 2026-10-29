"""Managed interpreter bootstrap uses only built-in Node APIs; fixtures never download."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'bin/python-runtime.cjs'

HARNESS = r'''
const fs = require('node:fs'), path = require('node:path');
const root = path.join(process.env.DEV_MEMORY_HOME, 'python-runtime');
Object.defineProperty(process, 'platform', {value: process.env.FIXTURE_PLATFORM || 'darwin'});
Object.defineProperty(process, 'arch', {value: process.env.FIXTURE_ARCH || 'arm64'});
const python = path.join(root, 'python', 'cpython-3.12-fixture', 'bin', 'python3.12');
const calls = [];
let downloads=0;
require('node:child_process').spawnSync = (command, args, options) => {
  calls.push({command,args,env: options.env});
  if (args.includes('--proto')) {
    downloads++;
    if (process.env.FIXTURE_NUMERIC_ERROR) return {error:Object.assign(new Error('private URL'),{code:23,name:'TimeoutError'})};
    if (process.env.FIXTURE_CERT_ERROR) return {status:60,stderr:Buffer.from('private URL')};
    if (process.env.FIXTURE_OFFLINE) return {status:7,stderr:Buffer.from('private URL and token')};
    if (process.env.FIXTURE_TOO_LARGE) return {status:63};
    if (process.env.FIXTURE_HTTP_ERROR) return {status:22};
    if (process.env.FIXTURE_EMPTY) return {status:0,stdout:Buffer.alloc(0)};
    return {status:0,stdout:Buffer.from('uv fixture')};
  }
  if (args.includes('-I')) return {status: 0, stdout: JSON.stringify({version: process.env.FIXTURE_INVALID ? [3,9] : [3,12], implementation:'CPython',architecture:process.env.FIXTURE_WRONG_ARCH?'other':process.arch==='arm64'?'aarch64':'amd64',bits:64,executable:command})};
  if (args.includes('-xf')) {
    const dest=args[args.indexOf('-C')+1], member=args[args.length-1];
    fs.mkdirSync(path.dirname(path.join(dest,member)),{recursive:true});
    fs.writeFileSync(path.join(dest,member),'uv fixture');
  }
  if (args[0]==='python' && args[1]==='install') {
    if (process.env.FIXTURE_INSTALL_FAIL) return {status:1,stdout:'private download URL and secret'};
    fs.mkdirSync(path.dirname(python),{recursive:true}); fs.writeFileSync(python,'python fixture');
  }
  return {status:0,stdout:args[1]==='find'?python:''};
};
if (!process.env.FIXTURE_BAD_HASH) {
  require('node:crypto').createHash = () => ({update(){return this},digest(){
    return process.platform==='win32'?'a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f':
      process.arch==='arm64'?'60fbd5c8a1ed681845eea28d9d622fcde03c51e91a43465b64a1e17db1ed3472':
      '63ba17fdda55ad1a230d4b37fc6017ffa10c23688c83818bd3bfdf914c652a02';
  }});
}
const fixture = process.env.FIXTURE_ACTION;
if (fixture === 'existing') {
  fs.mkdirSync(path.dirname(python),{recursive:true});fs.writeFileSync(python,'python fixture');
  fs.writeFileSync(path.join(root,'runtime.json'),JSON.stringify({python}));
}
if (fixture === 'escape') {
  fs.mkdirSync(root,{recursive:true});
  fs.writeFileSync(path.join(root,'runtime.json'),JSON.stringify({python:path.join(process.env.DEV_MEMORY_HOME,'outside.exe')}));
}
if (fixture === 'corrupt' || fixture === 'missing') {
  fs.mkdirSync(root,{recursive:true});
  fs.writeFileSync(path.join(root,'runtime.json'),fixture==='corrupt'?'broken JSON':JSON.stringify({python}));
}
if (fixture === 'locked') {
  fs.mkdirSync(root,{recursive:true}); fs.writeFileSync(path.join(root,'setup.lock'),'other owner');
  const realNow=Date.now; let n=0; Date.now=()=>realNow()+(n++>3?31000:0);
}
require(process.env.FIXTURE_MODULE).ensurePython({allowDownload:!process.env.FIXTURE_NO_DOWNLOAD})
  .then(result=>console.log(JSON.stringify({result,downloads,calls})))
  .catch(error=>console.log(JSON.stringify({code:error.code,message:error.message,downloads,calls})));
'''


@unittest.skipUnless(shutil.which('node'), 'Managed bootstrap requires Node')
class PythonRuntimeTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='managed Python 中文 ')
        self.addCleanup(scratch.cleanup)
        self.base = Path(scratch.name).resolve()
        self.env = {**os.environ, 'DEV_MEMORY_HOME':str(self.base), 'FIXTURE_MODULE':str(MODULE)}

    def run_fixture(self, **flags):
        result = subprocess.run([shutil.which('node'), '-e', HARNESS], env={**self.env, **flags},
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        return json.loads(result.stdout)

    def test_bootstrap_without_host_python_is_isolated_on_all_targets(self):
        for platform, arch in [('win32','x64'),('darwin','x64'),('darwin','arm64')]:
            with self.subTest(platform=platform,arch=arch):
                sub=self.base/(platform+arch);sub.mkdir()
                old=dict(os.environ)
                result=self.run_fixture(DEV_MEMORY_HOME=str(sub),FIXTURE_PLATFORM=platform,FIXTURE_ARCH=arch,
                                        PYTHONHOME='old-python',PYTHONPATH='old-packages')
                self.assertEqual(result['downloads'],1,result)
                self.assertTrue(Path(result['result']).is_file())
                self.assertTrue((sub/'python-runtime/runtime.json').is_file())
                commands=result['calls']
                self.assertEqual(len(commands),5)
                install=commands[2]
                self.assertIn('--no-bin',install['args'])
                self.assertIn('--no-registry',install['args'])
                self.assertIn('--no-config',install['args'])
                self.assertEqual(install['env']['PATH'],self.env['PATH'])
                self.assertNotIn('PYTHONHOME',install['env'])
                self.assertNotIn('PYTHONPATH',install['env'])
                self.assertEqual(os.environ,old)
                self.assertFalse((sub/'python-runtime/setup.lock').exists())

    def test_existing_interpreter_is_reused_without_uv_or_network(self):
        result=self.run_fixture(FIXTURE_ACTION='existing',FIXTURE_OFFLINE='1')
        self.assertIn('result',result)
        self.assertEqual(result['downloads'],0)
        self.assertEqual(len(result['calls']),1)
        self.assertIn('-I',result['calls'][0]['args'])

    def test_missing_interpreter_does_not_download_for_help(self):
        result=self.run_fixture(FIXTURE_NO_DOWNLOAD='1')
        self.assertEqual(result['code'],'python_runtime_missing')
        self.assertEqual(result['downloads'],0)
        self.assertFalse((self.base/'python-runtime').exists())

    def test_hash_failure_never_extracts_or_publishes(self):
        result=self.run_fixture(FIXTURE_BAD_HASH='1')
        self.assertEqual(result['code'],'python_runtime_hash_mismatch')
        self.assertEqual(len(result['calls']),1)
        self.assertFalse((self.base/'python-runtime/runtime.json').exists())
        self.assertFalse((self.base/'python-runtime/setup.lock').exists())

    def test_failure_does_not_expose_private_download_logs(self):
        result=self.run_fixture(FIXTURE_OFFLINE='1')
        self.assertEqual(result['code'],'python_runtime_network_error')
        self.assertNotIn('private',result['message'])
        self.assertFalse((self.base/'python-runtime/runtime.json').exists())

    def test_numeric_dom_exception_is_reported_as_timeout(self):
        result=self.run_fixture(FIXTURE_NUMERIC_ERROR='1')
        self.assertEqual(result['code'],'python_runtime_timeout')
        self.assertNotIn('private',result['message'])

    def test_certificate_error_has_static_safe_remediation(self):
        result=self.run_fixture(FIXTURE_CERT_ERROR='1')
        self.assertEqual(result['code'],'python_runtime_certificate_error')
        self.assertNotIn('private',result['message'])

    def test_escape_in_manifest_is_rejected_without_execution(self):
        result=self.run_fixture(FIXTURE_ACTION='escape')
        self.assertEqual(result['code'],'python_runtime_unsafe_path')
        self.assertEqual(result['calls'],[])
        self.assertEqual(result['downloads'],0)

    def test_invalid_interpreter_is_not_published(self):
        result=self.run_fixture(FIXTURE_INVALID='1')
        self.assertEqual(result['code'],'python_runtime_invalid')
        self.assertFalse((self.base/'python-runtime/runtime.json').exists())
        self.assertFalse((self.base/'python-runtime/setup.lock').exists())

    def test_python_install_failure_releases_own_lock_without_manifest(self):
        result=self.run_fixture(FIXTURE_INSTALL_FAIL='1')
        self.assertEqual(result['code'],'python_runtime_command_failed')
        self.assertNotIn('private',result['message'])
        self.assertFalse((self.base/'python-runtime/runtime.json').exists())
        self.assertFalse((self.base/'python-runtime/setup.lock').exists())

    def test_corrupt_manifest_and_missing_interpreter_are_repairable(self):
        for action in ('corrupt','missing'):
            with self.subTest(action=action):
                sub=self.base/action;sub.mkdir()
                result=self.run_fixture(DEV_MEMORY_HOME=str(sub),FIXTURE_ACTION=action)
                self.assertIn('result',result)
                self.assertIn('--reinstall',result['calls'][2]['args'])
                self.assertEqual(json.loads((sub/'python-runtime/runtime.json').read_text())['python'],result['result'])

    def test_wrong_architecture_is_not_published(self):
        result=self.run_fixture(FIXTURE_WRONG_ARCH='1')
        self.assertEqual(result['code'],'python_runtime_invalid')
        self.assertFalse((self.base/'python-runtime/runtime.json').exists())

    def test_explicit_download_disable_keeps_offline_reuse(self):
        result=self.run_fixture(UV_PYTHON_DOWNLOADS='never')
        self.assertEqual(result['code'],'python_runtime_download_disabled')
        self.assertEqual(result['downloads'],0)
        reused=self.run_fixture(FIXTURE_ACTION='existing',UV_PYTHON_DOWNLOADS='never')
        self.assertIn('result',reused)
        self.assertEqual(reused['downloads'],0)

    def test_download_limit_stops_without_extracting(self):
        result=self.run_fixture(FIXTURE_TOO_LARGE='1')
        self.assertEqual(result['code'],'python_runtime_download_limit')
        self.assertEqual(len(result['calls']),1)

    def test_curl_preserves_proxy_and_enforces_https_redirects(self):
        result=self.run_fixture(HTTPS_PROXY='http://example.invalid:7890')
        curl=result['calls'][0]
        self.assertEqual(curl['env']['HTTPS_PROXY'],'http://example.invalid:7890')
        self.assertEqual(curl['args'][:4],['--proto','=https','--proto-redir','=https'])
        self.assertIn('--max-filesize',curl['args'])
        self.assertIn('--max-time',curl['args'])

    def test_http_failure_and_empty_download_do_not_publish(self):
        for flag,code in [('FIXTURE_HTTP_ERROR','python_runtime_download_access_denied'),('FIXTURE_EMPTY','python_runtime_download_failed')]:
            with self.subTest(flag=flag):
                result=self.run_fixture(**{flag:'1'})
                self.assertEqual(result['code'],code)
                self.assertEqual(len(result['calls']),1)
                self.assertFalse((self.base/'python-runtime/runtime.json').exists())

    def test_unsupported_platform_does_not_write(self):
        result=self.run_fixture(FIXTURE_PLATFORM='win32',FIXTURE_ARCH='arm64')
        self.assertEqual(result['code'],'python_runtime_platform_unsupported')
        self.assertEqual(list(self.base.iterdir()),[])

    def test_other_install_lock_is_not_removed(self):
        result=self.run_fixture(FIXTURE_ACTION='locked')
        self.assertEqual(result['code'],'python_runtime_busy',result)
        self.assertEqual((self.base/'python-runtime/setup.lock').read_text(),'other owner')
        self.assertEqual(result['downloads'],0)

    def test_runtime_symlink_is_rejected(self):
        outside=self.base/'outside';outside.mkdir()
        try:
            (self.base/'python-runtime').symlink_to(outside,target_is_directory=True)
        except OSError:
            self.skipTest('Directory symlink privilege unavailable')
        result=self.run_fixture()
        self.assertEqual(result['code'],'python_runtime_unsafe_path')
        self.assertEqual(result['calls'],[])
        self.assertEqual(list(outside.iterdir()),[])


if __name__ == '__main__':
    unittest.main()

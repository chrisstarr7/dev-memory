"""Vector setup tests do not install packages or download model weights."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/dev-memory/scripts"))
import dev_memory_vector_setup as setup


class VectorSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vector setup 中文 ")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.compatible_python = setup._compatible_python
        self.real_compatible_python = setup._compatible_python
        runtime = patch.object(setup, "_compatible_python", return_value=sys.executable)
        runtime.start()
        self.addCleanup(runtime.stop)
        self.real_info = setup._interpreter_info
        self.info = dict(version=list(sys.version_info[:2]), implementation='CPython', architecture='AMD64',
                         bits=64, free_threaded=False, sqlite_extensions=True, pip_available=True,
                         prefix=str(self.base/'vector-runtime/venv'))
        info = patch.object(setup, '_interpreter_info', return_value=self.info)
        info.start()
        self.addCleanup(info.stop)

    def fake_probe(self):
        root = self.base / "vector-runtime"
        models = root / "models" / "model"
        models.mkdir(parents=True, exist_ok=True)
        model = models / "model.onnx"
        model.write_bytes(b"test-weight")
        ext = root / "vec0.dll"
        ext.write_bytes(b"test-extension")
        return {"model_name": setup.MODEL, "model_dir": str(models), "model_cache": str(root / "models"),
                "model_fingerprint": "fixture-model", "extension_path": str(ext),
                "extension_sha256": hashlib.sha256(ext.read_bytes()).hexdigest(),
                "artifact_hashes": {str(model.relative_to(root)): hashlib.sha256(model.read_bytes()).hexdigest()}}

    def test_setup_writes_config_only_after_successful_probe(self):
        probe = self.fake_probe()
        with patch.object(setup, "_run", side_effect=[{}, {}, probe]) as run:
            result = setup.setup(self.base)
        self.assertEqual(result["status"], "ready")
        config = setup.read_config(self.base)
        self.assertTrue(config["enabled"])
        self.assertEqual(config["model_name"], setup.MODEL)
        self.assertEqual(config["packages"], list(setup._packages()))
        self.assertIn("--copies", run.call_args_list[0].args[0])
        self.assertEqual(run.call_args_list[1].args[0][6:8],
                         ["--cache-dir", str(self.base/"vector-runtime"/"pip-cache")])
        self.assertEqual(run.call_args_list[1].args[0][-3:], list(setup._packages()))
        self.assertFalse((self.base / "global" / "memory.sqlite3").exists())

    def test_explicit_disabled_runtime_is_not_reenabled(self):
        root = self.base / "vector-runtime"
        root.mkdir()
        (root / "config.json").write_text('{"enabled": false}', encoding="utf-8")
        with patch.object(setup, "_run", side_effect=AssertionError("must not install")):
            self.assertEqual(setup.setup(self.base)["status"], "disabled")

    def test_failed_download_never_reports_ready(self):
        with patch.object(setup, "_run", side_effect=[{}, {}, subprocess.TimeoutExpired("probe", 1)]):
            result = setup.setup(self.base, timeout_seconds=1)
        self.assertEqual(result, {"status": "degraded", "reason": "setup_timeout", "phase": "model_and_probe"})
        self.assertFalse((self.base / "vector-runtime" / "config.json").exists())

    def test_reuses_only_verified_artifacts_and_offline_probe(self):
        probe = self.fake_probe()
        with patch.object(setup, "_run", side_effect=[{}, {}, probe]):
            self.assertEqual(setup.setup(self.base)["status"], "ready")
        python = Path(setup.read_config(self.base)['python'])
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_text('fixture', encoding='utf-8')
        with patch.object(setup, "_run", return_value=probe) as run:
            result = setup.setup(self.base)
        self.assertTrue(result["reused"])
        self.assertEqual(run.call_count, 1)
        self.assertTrue(run.call_args.kwargs["offline"])

    def test_changed_artifact_is_not_silently_reused(self):
        probe = self.fake_probe()
        config = {**probe, "enabled": True, "packages": list(setup._packages())}
        root = self.base / "vector-runtime"
        (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (Path(probe["model_dir"]) / "model.onnx").write_bytes(b"tampered")
        self.assertFalse(setup._verify_artifacts(config, root))

    def test_incomplete_venv_repairs_pip_before_installing_dependencies(self):
        probe = self.fake_probe()
        python = self.base/'vector-runtime/venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        python.parent.mkdir(parents=True)
        python.write_text('fixture', encoding='utf-8')
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup, '_interpreter_info', return_value={**self.info, 'pip_available':False}), \
             patch.object(setup, '_run', side_effect=[{}, {}, probe]) as run:
            result = setup.setup(self.base)
        self.assertEqual(result['status'], 'ready', result)
        self.assertEqual(run.call_args_list[0].args[0], [str(python), '-m', 'ensurepip', '--upgrade'])
        self.assertEqual(run.call_args_list[1].args[0][:4], [str(python), '-m', 'pip', 'install'])
        self.assertFalse((self.base/'global').exists())

    def test_pip_repair_failure_never_installs_dependencies_or_publishes_config(self):
        failure = setup._command_failure('No module named ensurepip', 1, False)
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup, '_interpreter_info', return_value={**self.info, 'pip_available':False}), \
             patch.object(setup, '_run', side_effect=[{}, failure]) as run:
            result = setup.setup(self.base)
        self.assertEqual(result['reason'], 'python_environment_incomplete', result)
        self.assertEqual(result['phase'], 'environment')
        self.assertEqual(run.call_count, 2)
        self.assertIn('ensurepip', run.call_args.args[0])
        self.assertFalse((self.base/'vector-runtime/config.json').exists())

    def test_pip_repair_refuses_an_interpreter_using_the_system_prefix(self):
        python = self.base/'vector-runtime/venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        python.parent.mkdir(parents=True)
        python.write_text('fixture', encoding='utf-8')
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup, '_interpreter_info', return_value={**self.info, 'pip_available':False, 'prefix':sys.base_prefix}), \
             patch.object(setup, '_run', side_effect=AssertionError('must not repair outside the venv')):
            result = setup.setup(self.base)
        self.assertEqual(result['reason'], 'runtime_environment_mismatch', result)
        self.assertFalse((self.base/'vector-runtime/config.json').exists())

    def test_interrupted_venv_recovers_using_only_its_bundled_pip(self):
        venv = self.base/'vector-runtime/venv'
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', '--copies', str(venv)],
                       check=True, capture_output=True, timeout=30)
        python = venv/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.assertFalse(self.real_info(python, time.monotonic()+10)['pip_available'])
        probe = self.fake_probe()
        real_run = setup._run
        def offline_run(command, deadline, **kwargs):
            if command[1:4] == ['-m', 'pip', 'install']:
                return {}
            if command[1:3] == ['-c', setup.PROBE]:
                return probe
            return real_run(command, deadline, **kwargs)
        def pip_info(interpreter, deadline):
            # Host macOS Python may omit SQLite extensions; this test exercises only pip recovery.
            return {**self.real_info(interpreter, deadline), 'sqlite_extensions':True}
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup, '_interpreter_info', side_effect=pip_info), \
             patch.object(setup, '_run', side_effect=offline_run) as run:
            first = setup.setup(self.base, timeout_seconds=30)
            self.assertEqual(first['status'], 'ready', first)
            self.assertTrue(self.real_info(python, time.monotonic()+10)['pip_available'])
            self.assertTrue(setup.setup(self.base, timeout_seconds=30)['reused'])
        repairs = [call.args[0] for call in run.call_args_list if 'ensurepip' in call.args[0]]
        self.assertEqual(repairs, [[str(python), '-m', 'ensurepip', '--upgrade']])
        self.assertFalse((self.base/'global').exists())

    def test_setup_does_not_publish_config_on_dependency_failure(self):
        with patch.object(setup, "_run", side_effect=RuntimeError("failed")):
            self.assertEqual(setup.setup(self.base)["status"], "degraded")
        self.assertFalse((self.base / "vector-runtime" / "config.json").exists())

    def test_concurrent_installer_is_rejected_without_touching_runtime(self):
        root = self.base / "vector-runtime"
        root.mkdir()
        (root / "setup.lock").write_text("", encoding="utf-8")
        with patch.object(setup, "_run", side_effect=AssertionError("must not install")):
            self.assertEqual(setup.setup(self.base)["reason"], "setup_busy")
        self.assertTrue((root / "setup.lock").exists())

    def test_artifact_path_cannot_escape_runtime(self):
        probe = self.fake_probe()
        outside = self.base / "outside.onnx"
        outside.write_bytes(b"outside")
        probe["artifact_hashes"] = {"../outside.onnx": hashlib.sha256(outside.read_bytes()).hexdigest()}
        self.assertFalse(setup._verify_artifacts(probe, self.base / "vector-runtime"))

    def test_macos_intel_reuses_managed_python_without_download(self):
        root = self.base / "vector-runtime"
        python = root / "python/cpython-3.12.13-macos-x86_64-none/bin/python3.12"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"managed-python")
        with patch.object(setup, "_mac", return_value=True), patch.object(setup, "_mac_intel", return_value=True), \
             patch.object(setup.platform, "mac_ver", return_value=("13.0", (), "")), \
             patch.object(setup, "_run", side_effect=AssertionError("must reuse")):
            self.assertEqual(self.compatible_python(root, time.monotonic()+10), str(python))

    def test_macos_intel_bootstraps_compatible_python_in_runtime(self):
        root = self.base / "vector-runtime"
        root.mkdir()
        python = root / "python/cpython-3.12.13-macos-x86_64-none/bin/python3.12"
        def run(command, deadline):
            if "--install-dir" in command:
                python.parent.mkdir(parents=True)
                python.write_bytes(b"managed-python")
            return {}
        with patch.object(setup, "_mac", return_value=True), patch.object(setup, "_mac_intel", return_value=True), \
             patch.object(setup.platform, "mac_ver", return_value=("13.0", (), "")), \
             patch.object(setup, "_run", side_effect=run) as calls:
            self.assertEqual(self.compatible_python(root, time.monotonic()+10), str(python))
        self.assertIn(setup.UV_PACKAGE, calls.call_args_list[0].args[0])
        self.assertEqual(calls.call_args_list[1].args[0][-1], "cpython-3.12-macos-x86_64-none")
        self.assertIn(str(root / "python"), calls.call_args_list[1].args[0])

    def test_macos_intel_rejects_unsupported_os_before_download(self):
        with patch.object(setup, "_mac", return_value=True), patch.object(setup, "_mac_intel", return_value=True), \
             patch.object(setup.platform, "mac_ver", return_value=("12.7", (), "")), \
             patch.object(setup, "_run", side_effect=AssertionError("must not download")):
            with self.assertRaisesRegex(RuntimeError, "macos_13_required"):
                self.compatible_python(self.base, time.monotonic()+10)

    def test_macos_arm_bootstraps_native_managed_python(self):
        root = self.base / "vector-runtime"
        root.mkdir()
        python = root / "python/cpython-3.12.13-macos-aarch64-none/bin/python3.12"
        def run(command, deadline):
            if "--install-dir" in command:
                python.parent.mkdir(parents=True)
                python.write_bytes(b"managed-python")
            return {}
        with patch.object(setup, "_mac", return_value=True), patch.object(setup, "_mac_intel", return_value=False), \
             patch.object(setup.platform, "mac_ver", return_value=("14.0", (), "")), \
             patch.object(setup, "_run", side_effect=run) as calls:
            self.assertEqual(self.compatible_python(root, time.monotonic()+10), str(python))
        self.assertEqual(calls.call_args_list[1].args[0][-1], "cpython-3.12-macos-aarch64-none")
        self.assertEqual(Path(calls.call_args_list[1].args[0][0]).parent, root / 'bootstrap' / 'bin')

    def test_macos_without_host_sqlite_extensions_uses_managed_probe(self):
        probe = self.fake_probe()
        with patch.object(setup, "_mac", return_value=True), \
             patch.object(setup.sqlite3, "connect", side_effect=AssertionError("host SQLite must not block setup")), \
             patch.object(setup, "_run", side_effect=[{}, {}, probe]):
            result = setup.setup(self.base)
        self.assertEqual(result["status"], "ready")
        self.assertIn("venv-py312", setup.read_config(self.base)["python"])

    def test_effective_onnxruntime_pin_matches_interpreter_constraints(self):
        with patch.object(setup, "_mac", return_value=True), patch.object(setup.sys, "version_info", (3, 14)):
            self.assertIn("onnxruntime==1.23.2", setup._packages())
        with patch.object(setup, "_mac", return_value=False), patch.object(setup.sys, "version_info", (3, 14)):
            self.assertIn("onnxruntime==1.31.1", setup._packages())
        with patch.object(setup, "_mac", return_value=False), patch.object(setup.sys, "version_info", (3, 10)):
            self.assertIn("onnxruntime==1.23.2", setup._packages())

    def test_sanitized_command_failures_and_network_precedence(self):
        cases = [
            ('CERTIFICATE_VERIFY_FAILED\nNo matching distribution found', 'certificate_error'),
            ('ProxyError: failed\nNo matching distribution found', 'proxy_error'),
            ('403 Client Error\nNo matching distribution found', 'download_access_denied'),
            ('Could not fetch URL\nNo matching distribution found', 'download_network_error'),
            ('No module named pip', 'python_environment_incomplete'),
            ('Permission denied', 'runtime_permission_denied'),
            ('ResolutionImpossible', 'dependency_conflict'),
            ('No matching distribution found for onnxruntime', 'dependency_wheel_unavailable'),
            ('DLL load failed', 'native_dependency_load_failed'),
            ('unrecognized failure', 'dependency_install_failed'),
        ]
        for stderr, reason in cases:
            with self.subTest(reason=reason), patch.object(setup.subprocess, 'run', return_value=
                    subprocess.CompletedProcess(['python'], 1, 'https://user:secret@private.example/path', stderr)):
                with self.assertRaises(setup.SetupFailure) as raised:
                    setup._run(['python', '-m', 'pip', 'install'], time.monotonic()+10)
                details = raised.exception.details
                self.assertEqual(details['reason'], reason)
                self.assertEqual(details['exit_code'], 1)
                self.assertNotIn('secret', json.dumps(details))
                self.assertNotIn('private.example', json.dumps(details))

    def test_pip_install_uses_skill_source_without_changing_parent_environment(self):
        parent = {'PIP_INDEX_URL': 'https://stale.example/simple',
                  'PIP_EXTRA_INDEX_URL': 'https://other.example/simple', 'PIP_NO_INDEX': '1',
                  'PIP_FIND_LINKS': 'C:/wheelhouse', 'PIP_TRUSTED_HOST': 'stale.example',
                  'PIP_CONSTRAINT': 'C:/other-project/constraints.txt', 'PIP_REQUIRE_HASHES': '1',
                  'PIP_CACHE_DIR': 'C:/shared/pip-cache', 'PIP_PROXY': 'http://proxy.example',
                  'HTTPS_PROXY': 'http://proxy.example', 'SSL_CERT_FILE': 'C:/certs/company.pem'}
        with patch.dict(os.environ, parent, clear=True), \
             patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess(
                 ['python', '-m', 'pip', 'install'], 0, '{}\n', '')) as run:
            setup._run(['python', '-m', 'pip', 'install'], time.monotonic()+10)
            env = run.call_args.kwargs['env']
            self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
            self.assertEqual(env['PIP_INDEX_URL'], 'https://pypi.org/simple')
            self.assertTrue(all(key not in env for key in ('PIP_EXTRA_INDEX_URL', 'PIP_FIND_LINKS',
                                                           'PIP_NO_INDEX', 'PIP_TRUSTED_HOST', 'PIP_CONSTRAINT',
                                                           'PIP_REQUIRE_HASHES', 'PIP_CACHE_DIR')))
            self.assertEqual(env['HTTPS_PROXY'], parent['HTTPS_PROXY'])
            self.assertEqual(env['SSL_CERT_FILE'], parent['SSL_CERT_FILE'])
            self.assertEqual(env['PIP_PROXY'], parent['PIP_PROXY'])
            self.assertEqual(os.environ['PIP_INDEX_URL'], parent['PIP_INDEX_URL'])

    def test_pip_install_accepts_skill_scoped_mirror_override(self):
        with patch.dict(os.environ, {'DEV_MEMORY_PIP_INDEX_URL': 'https://mirror.example/simple'}, clear=True), \
             patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess(
                 ['python', '-m', 'pip', 'install'], 0, '{}\n', '')) as run:
            setup._run(['python', '-m', 'pip', 'install'], time.monotonic()+10)
            self.assertEqual(run.call_args.kwargs['env']['PIP_INDEX_URL'], 'https://mirror.example/simple')

    def test_setup_keeps_diagnostic_and_never_publishes_failed_config(self):
        command = ['python', '-m', 'pip', 'install', '--only-binary=:all:', 'onnxruntime==1.31.1']
        failure = setup._command_failure('No matching distribution found for onnxruntime', 1, True, command)
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup, '_run', side_effect=[{}, failure]):
            result = setup.setup(self.base)
        self.assertEqual(result['reason'], 'dependency_wheel_unavailable')
        self.assertEqual(result['phase'], 'dependencies')
        self.assertEqual(result['package_requirement'], 'onnxruntime==1.31.1')
        self.assertIn('CPython', result['message'])
        self.assertIn('3.13', result['message'])
        self.assertIn('AMD64', result['message'])
        self.assertIn('DEV_MEMORY_PIP_INDEX_URL', result['remediation'])
        self.assertNotIn('改 Python 版本', result['remediation'])
        self.assertFalse((self.base/'vector-runtime/config.json').exists())

    def test_missing_wheel_diagnostic_uses_only_the_requested_package_pin(self):
        command = ['python', '-m', 'pip', 'install', 'onnxruntime==1.31.1', 'https://private.example/token']
        failure = setup._command_failure(
            'No matching distribution found for onnxruntime; index https://user:secret@private.example/simple',
            1, True, command)
        self.assertEqual(failure.details['package_requirement'], 'onnxruntime==1.31.1')
        self.assertNotIn('secret', json.dumps(failure.details))
        self.assertNotIn('private.example', json.dumps(failure.details))

    def test_windows_rejects_incompatible_host_before_creating_environment(self):
        with patch.object(setup, '_mac', return_value=False), patch.object(setup.platform, 'system', return_value='Windows'), \
             patch.object(setup.struct, 'calcsize', return_value=4), \
             patch.object(setup, '_run', side_effect=AssertionError('must fail before subprocess')):
            result = setup.setup(self.base)
        self.assertEqual(result['reason'], 'windows_architecture_unsupported')

    def test_windows_prerequisite_matrix(self):
        for changes, reason in [({'version':[3,15]}, 'windows_python_unsupported'),
                                ({'free_threaded':True}, 'windows_python_unsupported'),
                                ({'implementation':'PyPy'}, 'windows_python_unsupported'),
                                ({'architecture':'ARM64'}, 'windows_architecture_unsupported')]:
            with self.subTest(changes=changes), self.assertRaises(setup.SetupFailure) as raised:
                setup._windows_preflight({**self.info, **changes})
            self.assertEqual(raised.exception.details['reason'], reason)

    def test_missing_venv_components_fail_before_installation(self):
        with patch.object(setup, '_mac', return_value=False), \
             patch.object(setup.importlib.util, 'find_spec', return_value=None), \
             patch.object(setup, '_run', side_effect=AssertionError('must not install')):
            result = setup.setup(self.base)
        self.assertEqual(result['reason'], 'python_environment_incomplete')

    def test_existing_interpreter_controls_pin_even_when_host_version_differs(self):
        root=self.base/'vector-runtime'
        python=root/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        python.parent.mkdir(parents=True); python.write_text('fixture', encoding='utf-8')
        probe=self.fake_probe()
        for effective, host, expected in [([3,10],(3,14),'onnxruntime==1.23.2'),([3,14],(3,15),'onnxruntime==1.31.1')]:
            with self.subTest(effective=effective), patch.object(setup, '_mac', return_value=False), \
                 patch.object(setup.platform, 'system', return_value='Windows'), \
                 patch.object(setup.sys,'version_info',host), \
                 patch.object(setup, '_interpreter_info', return_value={**self.info,'version':effective}), \
                 patch.object(setup, '_run', side_effect=[{},probe]) as run:
                result=setup.setup(self.base)
                self.assertEqual(result['status'],'ready',result)
                self.assertIn(expected,run.call_args_list[0].args[0])

    def test_interpreter_info_uses_bounded_stdlib_probe(self):
        with patch.object(setup, '_run', return_value=self.info) as run:
            self.assertEqual(self.real_info(Path(sys.executable),time.monotonic()+1),self.info)
        self.assertNotIn('pip',run.call_args.args[0])

    def test_mac_reuses_npx_python_without_downloading_another_interpreter(self):
        python = self.base/'python-runtime/python/cpython-3.12.12-macos-aarch64-none/bin/python3.12'
        with patch.object(setup, '_mac', return_value=True), \
             patch.dict(os.environ, {'DEV_MEMORY_HOME':str(self.base)}), \
             patch.object(setup.platform, 'mac_ver', return_value=('13.0', (), '')), \
             patch.object(setup.sys, 'version_info', (3,12)), \
             patch.object(setup.sys, 'executable', str(python)), \
             patch.object(setup, '_run', side_effect=AssertionError('must reuse without downloads')):
            self.assertEqual(self.real_compatible_python(self.base/'vector-runtime', time.monotonic()+10), str(python))
            self.assertEqual(self.real_compatible_python(self.base/'historical-root/vector-runtime', time.monotonic()+10), str(python))


if __name__ == "__main__":
    unittest.main()

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
        runtime = patch.object(setup, "_compatible_python", return_value=sys.executable)
        runtime.start()
        self.addCleanup(runtime.stop)

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


if __name__ == "__main__":
    unittest.main()

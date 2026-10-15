"""Adversarial regression checks. All stores and installs are synthetic."""
import json
import os
import shutil
import sys
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from test_dev_memory import MemoryTestCase, ROOT, store, dev_memory


class AdversarialTests(MemoryTestCase):
    def test_late_git_tracking_blocks_private_writes_views_and_backups_but_keeps_global_independent(self):
        subprocess.run(['git', 'init', '-q', str(self.project_a)], check=True)
        store.init_project(self.project_a)
        self.add_project_rule()
        subprocess.run(['git', '-C', str(self.project_a), 'add', '-f', '.dev-memory/memory.sqlite3'], check=True)
        db = store.project_paths(self.project_a)[1]; before = db.read_bytes()
        result = self.apply(scope='both', turn='late-tracked', operations=[
            {'op':'NOOP', 'scope':'global', 'reason':'checked'},
            {'op':'ADD', 'scope':'project', 'record':self.record(content='Do not store this addition')}])
        self.assertEqual(result['status'], 'partial_success')
        self.assertEqual(result['stores'][1]['error'], 'tracked_memory_path')
        self.assertEqual(db.read_bytes(), before)
        for action in (lambda: store.export_views('project', project_root=self.project_a),
                       lambda: store.backup_store('project', project_root=self.project_a)):
            with self.assertRaises(store.MemoryError) as exc:
                action()
            self.assertEqual(exc.exception.code, 'tracked_memory_path')

    def test_removed_git_exclusion_and_unknown_git_state_fail_closed_before_write(self):
        subprocess.run(['git', 'init', '-q', str(self.project_a)], check=True)
        store.init_project(self.project_a)
        exclude = store._git_info(self.project_a)[1]
        exclude.write_text('', encoding='utf-8')
        op = {'op':'ADD', 'scope':'project', 'record':self.record()}
        result = self.apply(scope='project', operations=[op])
        self.assertEqual(result['stores'][0]['error'], 'git_exclude_failed')
        store.init_project(self.project_a)
        with patch.object(store, '_run_git', return_value=None):
            result = self.apply(scope='project', turn='git-unknown', operations=[op])
        self.assertEqual(result['stores'][0]['error'], 'git_protection_unavailable')
        self.assertEqual(store.list_records('project', project_root=self.project_a)['records'], [])

    def test_global_guard_rejects_windows_drive_paths_with_either_separator(self):
        for index, path in enumerate(('C:/Projects/asset-library/spec.md', r'C:\Projects\asset-library\spec.md', r'\\server\share\business\spec.md')):
            record = self.record(scope='global', kind='preference', content='Generic preference', source_refs=[path])
            result = self.apply(scope='global', turn=f'windows-global-{index}', operations=[{'op':'ADD', 'scope':'global', 'record':record}])
            self.assertEqual(result['stores'][0]['error'], 'scope_error', result)
        self.assertEqual(store.list_records('global', global_root=self.global_root)['records'], [])

    def test_windows_path_guard_does_not_mistake_code_escape_for_unc_share(self):
        record = self.record(scope='global', kind='preference', title='JSON line breaks',
            content=r'Use \n escapes in JSON strings.', conditions='Across development projects.',
            exceptions='', do='Use valid JSON.', dont='Never insert unescaped control characters.',
            verification_steps='Parse JSON.')
        result = self.apply(scope='global', operations=[{'op':'ADD', 'scope':'global', 'record':record}])
        self.assertEqual(result['status'], 'saved', result)

    def test_apply_returns_committed_revision_without_a_postcommit_database_reopen(self):
        with patch.object(store, 'data_revision', side_effect=store.MemoryError('storage_unavailable', 'synthetic postcommit read failure')):
            result = self.apply(scope='project', operations=[{'op':'ADD', 'scope':'project', 'record':self.record()}])
        self.assertEqual(result['status'], 'saved', result)
        self.assertEqual(result['stores'][0]['data_revision'], store.data_revision(store.project_paths(self.project_a)[1]))
        self.assertEqual(store.receipt_for_turn('project', session_id='session-test', turn_id='turn-1', project_root=self.project_a)['status'], 'saved')

    def test_global_revision_read_failure_does_not_block_independent_project_recall(self):
        memory_id = self.add_project_rule()
        original = store.data_revision
        def fail_global(db):
            if db == store.global_paths(self.global_root)[1]:
                raise store.MemoryError('storage_unavailable', 'synthetic failed global revision read')
            return original(db)
        with patch.object(store, 'data_revision', side_effect=fail_global):
            result = store.recall('退款', project_root=self.project_a, global_root=self.global_root, force=True)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['stores'][0]['status'], 'unavailable')
        self.assertTrue(any(record['id'] == memory_id for record in result['stores'][1]['records']))
    def test_first_config_creation_cannot_replace_winning_namespace(self):
        path = self.home / "first-create/config.json"
        first = {"schema_version": 1, "namespace_id": "winner"}
        second = {"schema_version": 1, "namespace_id": "loser"}
        self.assertEqual(store._create_config_once(path, first), first)
        self.assertEqual(store._create_config_once(path, second), first)

    def test_init_cannot_relabel_an_existing_database_scope(self):
        _, db = store.project_paths(self.project_a)
        config = store.read_json(store.config_path_for("project", self.project_a))
        with self.assertRaises(store.MemoryError) as caught:
            store._init_database(db, config["namespace_id"], "global")
        self.assertEqual(caught.exception.code, "scope_error")

    def test_noop_does_not_scan_worktree_and_benchmark_copies_complete_runtime(self):
        with patch.object(store, "_workspace_signature", side_effect=AssertionError("NOOP must be light")):
            result = self.apply(scope="project", operations=[{"op": "NOOP", "scope": "project", "reason": "checked"}])
        self.assertEqual(result["status"], "checked_noop")
        import bench_compare
        project = self.home / "benchmark"
        copied = bench_compare._copy_support(project)
        self.assertTrue((copied / "references/protocol.md").is_file())
        self.assertEqual(set(bench_compare.SOURCES), set(dev_memory.SKILL_FILES))

    def test_foreign_backup_is_not_mutated_during_forget(self):
        memory_id = self.add_project_rule(id="same-id")
        self.add_project_rule(project=self.project_b, turn="b", id="same-id", content="B business")
        source = store.backup_store("project", project_root=self.project_b)["backup"]
        directory = self.project_a / ".dev-memory/backups"
        directory.mkdir()
        foreign = directory / "foreign.sqlite3"
        shutil.copyfile(source, foreign)
        preview = store.forget_preview("project", memory_id, project_root=self.project_a)
        result = store.forget_apply("project", memory_id, preview["confirmation_token"], project_root=self.project_a)
        self.assertIn("foreign.sqlite3", result["backup_cleanup_incomplete"])
        conn = store._connect(foreign, readonly=True)
        self.assertEqual(conn.execute("SELECT content FROM memories WHERE id='same-id'").fetchone()[0], "B business")
        conn.close()

    def test_benchmark_inspects_full_records_instead_of_summary_fields(self):
        import bench_compare
        self.add_project_rule(title='Confirmed refund eligibility',tags=['refund'])
        self.assertNotIn('claim_type',store.list_records('project',project_root=self.project_a)['records'][0])
        for mode in ('on','off'):
            result=bench_compare._memory_state(self.project_a,history=True,mode=mode)
            self.assertEqual(result['active_refund_rules'],1)
            self.assertEqual(result['historical_duplicates_retired'],True if mode=='on' else None)

    def test_global_init_refuses_orphaned_private_data(self):
        base = self.home / "orphan/global"
        base.mkdir(parents=True)
        (base / "memory.sqlite3").write_bytes(b"synthetic orphan")
        with self.assertRaises(store.MemoryError) as caught:
            store.init_global(base.parent)
        self.assertEqual(caught.exception.code, "unmanaged_existing_data")
        self.assertFalse((base / "config.json").exists())

    def test_evidence_requires_type_and_generated_id_is_labelled(self):
        memory_id = self.add_project_rule()
        evidence = store.show_record("project", memory_id, project_root=self.project_a)["evidence"]
        self.assertEqual(evidence[0]["ingestion_origin"], "generated_by_dev_memory")
        result = self.apply(scope="project", turn="no-source-type", operations=[{"op": "ADD_EVIDENCE", "scope": "project",
            "id": memory_id, "expected_revision": 1, "source": {"excerpt": "AI text"}}])
        self.assertEqual(result["stores"][0]["error"], "provenance_error")

    def test_project_exclusion_and_configured_query_limits(self):
        self.add_project_rule()
        path = store.config_path_for("project", self.project_a)
        config = store.read_json(path)
        config["limits"]["max_context_chars"] = 10
        store.write_json_atomic(path, config)
        result = store.recall("refund", project_root=self.project_a, global_root=self.global_root)
        self.assertTrue(result["context_incomplete"])
        config["excluded"] = True
        store.write_json_atomic(path, config)
        result = store.recall("refund", project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result["stores"][1]["status"], "disabled")
        result = self.apply(scope="project", turn="excluded", operations=[{"op": "ADD", "scope": "project", "record": self.record(content="not stored")}])
        self.assertEqual(result["status"], "skipped_private")

    def test_corrupt_project_does_not_prevent_independent_global_commit(self):
        store.project_paths(self.project_a)[1].write_bytes(b"not a SQLite database")
        result = self.apply(scope="both", operations=[
            {"op": "NOOP", "scope": "global", "reason": "checked"},
            {"op": "NOOP", "scope": "project", "reason": "checked"}])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["stores"][0]["status"], "checked_noop")
        self.assertEqual(result["stores"][1]["status"], "failed")

    def test_skip_blocks_late_apply_and_survives_restore(self):
        backup = store.backup_store("project", project_root=self.project_a)["backup"]
        store.record_private_skip("project", session_id="session-test", turn_id="private",
                                  project_root=self.project_a)
        operation = {"op": "ADD", "scope": "project", "record": self.record()}
        result = self.apply(scope="project", turn="private", operations=[operation])
        self.assertEqual(result["status"], "skipped_private")
        store.restore_store("project", Path(backup), project_root=self.project_a)
        retry = self.apply(scope="project", turn="private", idem="new-key", operations=[operation])
        self.assertEqual(retry["status"], "skipped_private")
        self.assertEqual(store.list_records("project", project_root=self.project_a)["records"], [])

    def test_add_cannot_overwrite_or_recreate_forgotten_id(self):
        memory_id = self.add_project_rule(id="protected")
        bad = self.apply(scope="project", turn="overwrite", operations=[
            {"op": "ADD", "scope": "project", "record": self.record(id=memory_id, content="overwrite") }])
        self.assertEqual(bad["stores"][0]["error"], "revision_conflict")
        preview = store.forget_preview("project", memory_id, project_root=self.project_a)
        store.forget_apply("project", memory_id, preview["confirmation_token"], project_root=self.project_a)
        bad = self.apply(scope="project", turn="resurrect", operations=[
            {"op": "ADD", "scope": "project", "record": self.record(id=memory_id)}])
        self.assertEqual(bad["stores"][0]["error"], "forgotten_record")

    def test_idempotency_key_cannot_claim_different_payload_saved(self):
        self.add_project_rule()
        result = self.apply(scope="project", operations=[
            {"op": "ADD", "scope": "project", "record": self.record(content="different") }])
        self.assertEqual(result["stores"][0]["error"], "idempotency_conflict")

    def test_task_and_claim_type_are_dedup_boundaries(self):
        ids = []
        for i, task in enumerate(("task-a", "task-b")):
            result = self.apply(scope="task", task=task, turn=f"task-{i}", operations=[
                {"op": "CHECKPOINT", "scope": "task", "record": self.record(kind="checkpoint") }])
            ids.append(result["stores"][0]["operations"][0]["id"])
        self.assertNotEqual(*ids)
        desired = self.add_project_rule(turn="desired", claim_type="desired")
        observed = self.add_project_rule(turn="observed", claim_type="observed", source=self.source("observed", "code_observation"))
        self.assertNotEqual(desired, observed)

    def test_same_turn_id_in_separate_sessions_is_independent_evidence(self):
        operation = {"op": "ADD", "scope": "project", "record": self.record()}
        for session in ("s-a", "s-b"):
            result = store.apply_payload({"schema_version": 1, "scope": "project", "session_id": session,
                "turn_id": "t1", "idempotency_key": session, "operations": [operation]}, project_root=self.project_a)
        memory_id = result["stores"][0]["operations"][0]["id"]
        self.assertEqual(len(store.show_record("project", memory_id, project_root=self.project_a)["evidence"]), 2)

    def test_global_evidence_and_metadata_cannot_bypass_scope_guard(self):
        record = self.record(scope="global", kind="preference", title="Concise", content="Be concise")
        added = self.apply(scope="global", operations=[{"op": "ADD", "scope": "global", "record": record}])
        memory_id = added["stores"][0]["operations"][0]["id"]
        bad = self.apply(scope="global", turn="bad-evidence", operations=[{"op": "ADD_EVIDENCE", "scope": "global",
            "id": memory_id, "expected_revision": 1, "source": self.source("/Users/example/private-project/secret", "user_feedback")}])
        self.assertEqual(bad["stores"][0]["error"], "scope_error")
        record["source_refs"] = ["/home/example/private-project/spec.md"]
        bad = self.apply(scope="global", turn="bad-meta", operations=[{"op": "ADD", "scope": "global", "record": record}])
        self.assertEqual(bad["stores"][0]["error"], "scope_error")
        record.pop("source_refs")
        record["cross_project_confirmed"] = "false"
        bad = self.apply(scope="global", turn="truthy", operations=[{"op": "ADD", "scope": "global", "record": record}])
        self.assertEqual(bad["stores"][0]["error"], "scope_error")

    def test_nested_git_project_refuses_tracked_memory_and_escapes_patterns(self):
        repo = self.home / "nested-repo"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        sub = repo / "tracked"
        (sub / ".dev-memory").mkdir(parents=True)
        (sub / ".dev-memory/leak.txt").write_text("synthetic", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "tracked/.dev-memory/leak.txt"], check=True)
        with self.assertRaises(store.MemoryError) as caught:
            store.init_project(sub)
        self.assertIn(caught.exception.code, {"tracked_memory_path", "unmanaged_existing_data"})
        with self.assertRaises(store.MemoryError) as caught:
            store._ensure_local_git_exclude(sub)
        self.assertEqual(caught.exception.code, "tracked_memory_path")
        for name in ("module [one]", "module two"):
            project = repo / name
            project.mkdir()
            store.init_project(project)
            ignored = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--", name + "/.dev-memory/"], check=False)
            self.assertEqual(ignored.returncode, 0)

    def test_forget_removes_existing_views_and_export_clears_archived_bucket(self):
        memory_id = self.add_project_rule()
        store.export_views("project", project_root=self.project_a)
        view = self.project_a / ".dev-memory/views/business.md"
        self.assertTrue(view.exists())
        preview = store.forget_preview("project", memory_id, project_root=self.project_a)
        deleted = store.forget_apply("project", memory_id, preview["confirmation_token"], project_root=self.project_a)
        self.assertNotIn("view_cleanup_incomplete", deleted)
        self.assertFalse(view.exists())
        memory_id = self.add_project_rule(turn="new")
        store.export_views("project", project_root=self.project_a)
        self.apply(scope="project", turn="archive", operations=[{"op": "ARCHIVE", "scope": "project", "id": memory_id, "expected_revision": 1}])
        store.export_views("project", project_root=self.project_a)
        self.assertFalse(view.exists())

    def test_swapped_database_fails_identity_check(self):
        shutil.copyfile(store.project_paths(self.project_a)[1], store.global_paths(self.global_root)[1])
        with self.assertRaises(store.MemoryError) as caught:
            store.show_record("global", "absent", global_root=self.global_root)
        self.assertEqual(caught.exception.code, "namespace_mismatch")

    def test_topic_change_and_incomplete_recall_cannot_use_wrong_cache(self):
        self.add_project_rule(title="topic-one", content="alpha only", strength="informational")
        self.add_project_rule(turn="second", title="topic-two", content="beta only", strength="informational")
        first = store.recall("alpha", project_root=self.project_a, session_id="cache", global_root=self.global_root)
        second = store.recall("beta", project_root=self.project_a, session_id="cache", global_root=self.global_root)
        self.assertEqual(second["stores"][1]["status"], "ok")
        self.assertIn("beta only", json.dumps(second))
        for _ in range(2):
            incomplete = store.recall("alpha", project_root=self.project_a, session_id="incomplete", max_chars=10, global_root=self.global_root)
            self.assertTrue(incomplete["context_incomplete"])
            self.assertNotEqual(incomplete["stores"][1]["status"], "cached")

    def test_global_preference_is_loaded_for_unrelated_business_query(self):
        record = self.record(scope="global", kind="preference", title="Output", content="Concise output")
        self.apply(scope="global", operations=[{"op": "ADD", "scope": "global", "record": record}])
        result = store.recall("entirely_unrelated_business", project_root=self.project_b, global_root=self.global_root)
        self.assertIn("Concise output", json.dumps(result))

    def test_paused_recall_does_not_write_session_cache(self):
        self.add_project_rule()
        store.set_capture("project", False, project_root=self.project_a)
        store.recall("refund", project_root=self.project_a, session_id="no-write", global_root=self.global_root)
        conn = store._connect(store.project_paths(self.project_a)[1], readonly=True)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM session_context").fetchone()[0], 0)
        conn.close()

    def test_stale_summary_sources_and_self_supersede_are_rejected(self):
        memory_id = self.add_project_rule()
        summary = {"kind": "summary", "title": "summary", "content": "only from sources", "status": "candidate",
            "source": {"type": "model_inference"}, "derived_from": [memory_id], "expected_source_revisions": {memory_id: 0}}
        bad = self.apply(scope="project", turn="summary", operations=[{"op": "ADD", "scope": "project", "record": summary}])
        self.assertEqual(bad["stores"][0]["error"], "revision_conflict")
        bad = self.apply(scope="project", turn="self", operations=[{"op": "SUPERSEDE", "scope": "project", "id": memory_id,
            "expected_revision": 1, "record": self.record(id=memory_id, content="replacement")}])
        self.assertEqual(bad["stores"][0]["error"], "revision_conflict")
        self.assertEqual(store.show_record("project", memory_id, project_root=self.project_a)["record"]["status"], "active")

    def test_malformed_json_shapes_fail_cleanly(self):
        for record in ([], "text", {**self.record(), "claim_type": []}, {**self.record(), "source": {"type": []}}):
            result = self.apply(scope="project", operations=[{"op": "ADD", "scope": "project", "record": record}])
            self.assertEqual(result["status"], "failed")
        with self.assertRaises(store.MemoryError):
            store.apply_payload({"schema_version": 1, "scope": [], "operations": []})

    def test_python_installer_runtime_whitelist_and_host_destinations(self):
        for agent, relative in dev_memory.AGENT_DIRS.items():
            with patch.object(Path, "home", return_value=self.home):
                result = dev_memory.install(None, False, False, agent)
            target = self.home / relative / "dev-memory"
            self.assertEqual(result["path"], str(target.resolve()))
            self.assertTrue((target / "LICENSE").is_file())
            self.assertFalse((target / "tests").exists())
            self.assertFalse((target / "evals").exists())

    def test_extra_files_marker_symlinks_and_data_paths_block_removal(self):
        target = self.home / "installed"
        dev_memory.install(target, False, False)
        extra = target / "private.sqlite3"
        extra.write_text("synthetic private data", encoding="utf-8")
        with self.assertRaises(store.MemoryError):
            dev_memory.install(target, False, True)
        with self.assertRaises(store.MemoryError):
            dev_memory.uninstall(target)
        self.assertTrue(extra.exists())
        extra.unlink()
        marker = target / dev_memory.MARKER
        marker.unlink()
        marker.symlink_to(ROOT / "skills/dev-memory" / dev_memory.MARKER)
        with self.assertRaises(store.MemoryError):
            dev_memory.uninstall(target)
        with self.assertRaises(store.MemoryError):
            dev_memory.install(self.global_root / ".dev-memory/skill", False, False)

    def test_hook_removal_preserves_unknown_shapes_and_echo_of_adapter_path(self):
        codex_home = self.home / "codex"
        codex_home.mkdir()
        target = self.home / "installed"
        script = str((target / "scripts/codex_hook.py").resolve())
        data = {"hooks": {"Future": {"schema": "unknown"}, "Stop": [{"hooks": [
            {"type": "command", "command": "echo " + script},
            {"type": "command", "command": dev_memory._hook_command(target)}]}]}}
        hooks = codex_home / "hooks.json"
        hooks.write_text(json.dumps(data), encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}):
            result = dev_memory._remove_hook_config(target)
        after = json.loads(hooks.read_text(encoding="utf-8"))
        self.assertEqual(result["handlers_removed"], 1)
        self.assertEqual(after["hooks"]["Future"], data["hooks"]["Future"])
        self.assertIn("echo ", json.dumps(after))

    def test_published_apply_example_actually_executes(self):
        protocol = (ROOT / "skills/dev-memory/references/protocol.md").read_text(encoding="utf-8")
        payload = json.loads(protocol.split("```json\n", 1)[1].split("```", 1)[0])
        result = store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result["status"], "saved", result)

    def test_skill_ordinary_apply_contract_is_a_valid_nested_record(self):
        skill = (ROOT / 'skills/dev-memory/SKILL.md').read_text(encoding='utf-8')
        payload = json.loads(skill.split('```json\n', 1)[1].split('```', 1)[0])
        result = store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result['status'], 'saved', result)
        active = store.list_records('global', global_root=self.global_root)['records']
        self.assertEqual({r['kind'] for r in active}, {'preference'})

    def test_empty_apply_input_explains_input_contract_and_writes_nothing(self):
        result = subprocess.run([sys.executable, str(ROOT/'skills/dev-memory/scripts/dev_memory.py'),
                                 'apply', '--project-root', str(self.project_a)], input='', capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--input', json.loads(result.stdout)['message'])
        self.assertEqual(store.list_records('project',project_root=self.project_a)['records'], [])


if __name__ == "__main__":
    unittest.main()

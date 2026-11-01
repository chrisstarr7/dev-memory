from __future__ import annotations

import http.cookiejar
import http.client
import queue
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit
from datetime import datetime, timezone
from pathlib import Path

from test_dev_memory import MemoryTestCase
import dev_memory_dashboard as dashboard
import dev_memory
import dev_memory_store as store
import dev_memory_setup as setup


class DashboardTests(MemoryTestCase):
    def test_catalog_lock_releases_after_process_exit_and_write_error(self):
        dashboard.register_project(self.project_a, self.global_root)
        lock = dashboard._catalog_path(self.global_root).with_suffix('.lock')
        code = (f"import sys,time; from pathlib import Path; sys.path.insert(0,{str(Path(dashboard.__file__).parent)!r}); "
                "import dev_memory_dashboard as d; "
                f"lock=d._catalog_write_lock(Path({str(self.global_root)!r})); lock.__enter__(); "
                "print('locked',flush=True); time.sleep(30)")
        process = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready = queue.Queue()
            threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
            self.assertEqual(ready.get(timeout=10).strip(), 'locked')
            with self.assertRaises(store.MemoryError) as busy:
                dashboard.register_project(self.project_b, self.global_root)
            self.assertEqual(busy.exception.code, 'catalog_busy')
        finally:
            process.kill()
            process.communicate(timeout=5)
        dashboard.register_project(self.project_b, self.global_root)
        self.assertTrue(lock.exists())
        with patch.object(store, 'write_json_atomic', side_effect=OSError('simulated write failure')):
            with self.assertRaises(OSError):
                dashboard.remove_project(dashboard.projects(self.global_root)[0]['namespace_id'], self.global_root)
        dashboard.register_project(self.project_b, self.global_root)
        self.assertEqual(len(dashboard.projects(self.global_root)), 2)

    def test_concurrent_catalog_writes_report_busy_instead_of_losing_projects(self):
        entered = threading.Event()
        release = threading.Event()
        errors = []
        original = store.write_json_atomic
        def slow_first(path, value):
            if path == dashboard._catalog_path(self.global_root) and value['projects'][0]['path'] == str(self.project_a.resolve()):
                entered.set()
                if not release.wait(timeout=5):
                    raise AssertionError('catalog writer was not released')
            return original(path, value)
        def first():
            try:
                dashboard.register_project(self.project_a, self.global_root)
            except Exception as exc:
                errors.append(exc)
        with patch.object(store, 'write_json_atomic', side_effect=slow_first):
            thread = threading.Thread(target=first)
            thread.start()
            try:
                self.assertTrue(entered.wait(timeout=5))
                with self.assertRaises(store.MemoryError) as busy:
                    dashboard.register_project(self.project_b, self.global_root)
                self.assertEqual(busy.exception.code, 'catalog_busy')
            finally:
                release.set()
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        dashboard.register_project(self.project_b, self.global_root)
        self.assertEqual(len(dashboard.projects(self.global_root)), 2)

    def test_runtime_fallback_interrupt_returns_cancel_without_traceback(self):
        with patch.object(dev_memory.sqlite3, 'Connection', object), \
             patch.dict(dev_memory.os.environ, {'DEV_MEMORY_VECTOR_REEXEC':''}), \
             patch('dev_memory_vectors._settings', return_value={'python':str(self.home/'runtime-python')}), \
             patch.object(dev_memory.subprocess, 'call', side_effect=KeyboardInterrupt):
            self.assertEqual(dev_memory.main(['--global-root',str(self.global_root),
                                             'dashboard','serve','--no-open']), 130)

    def test_bad_optional_vector_metadata_keeps_raw_memory_readable(self):
        import dev_memory_vectors as vectors
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        _, db, _ = store._config_for('project', self.project_a, self.global_root)
        conn = store._connect(db)
        with conn:
            vectors._schema(conn)
            conn.execute("INSERT INTO vector_state VALUES(?,1,'fixture','ready',?,'')", (mid, 1e100))
        app = dashboard.Dashboard(self.global_root)
        with self.subTest(metadata='invalid_timestamp'):
            page = app.index({'scope':key})
            self.assertIn('仅已送达订单可退款', page)
            self.assertIn('未知', page)
        with conn:
            conn.execute('DROP TABLE vector_state')
            conn.execute('CREATE TABLE vector_state(memory_id TEXT PRIMARY KEY)')
        conn.close()
        with self.subTest(metadata='unreadable_optional_schema'):
            page = app.index({'scope':key})
            self.assertIn('仅已送达订单可退款', page)
            self.assertIn('不可用', page)

    def test_detail_shows_full_vector_and_escapes_stored_metadata(self):
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        app = dashboard.Dashboard(self.global_root)
        with patch('dev_memory_vectors.inspect_record', return_value={
            'status':'ok', 'dimensions':384, 'embedding':[.25]*384,
            'is_current':True, 'indexed_revision':1, 'model_key':'<script>bad</script>',
            'model_name':'本地模型', 'updated_at':1}):
            page = app.detail(key, mid, include_vector=True)
        self.assertIn('查看实际存储的向量数据', page)
        self.assertIn('维度：384', page)
        self.assertEqual(page.count('0.25'), 384)
        self.assertIn('&lt;script&gt;bad&lt;/script&gt;', page)
        self.assertNotIn('<script>bad</script>', page)

    def test_vector_panel_is_readonly_and_retry_uses_selected_scope(self):
        self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        app = dashboard.Dashboard(self.global_root)
        with patch('dev_memory_vectors.schedule', side_effect=AssertionError('GET must not index')), \
             patch('dev_memory_vectors._load', side_effect=AssertionError('listing must not load sqlite-vec')), \
             patch('dev_memory_vectors._encode', side_effect=AssertionError('listing must not embed')), \
             patch('dev_memory_vectors.inspect_record', side_effect=AssertionError('listing must not load full vectors')):
            page = app.index({'scope': key})
        self.assertIn('向量索引', page)
        self.assertIn('记忆列表', page)
        self.assertIn('来源记忆', page)
        with patch('dev_memory_vectors.schedule', return_value={'status':'running'}) as schedule:
            target = app.action({'action':'vectors_sync', 'scope':key})
        self.assertEqual(target, '/?scope=' + key)
        schedule.assert_called_once_with('project', project_root=self.project_a.resolve(), global_root=self.global_root)

    def test_compact_dashboard_scope_links_memory_and_vector_tables(self):
        project_id, _ = self._seed()
        row = dashboard.register_project(self.project_a, self.global_root)
        app = dashboard.Dashboard(self.global_root)
        page = app.index({"scope": row["namespace_id"], "q": "退款", "status": "active"})
        self.assertIn('name="scope"', page)
        self.assertIn(str(self.project_a.resolve()), page)
        self.assertIn('class="filters"', page)
        self.assertIn('class="stats"', page)
        self.assertIn('/record?', page)
        self.assertIn('value="backup"', page)
        self.assertIn('<dialog id="edit-', page)
        self.assertIn('name="revision"', page)
        self.assertIn(project_id, page)
        self.assertNotIn('Reuse implementations', page)
        self.assertNotIn('<nav>', page)

    def test_record_detail_does_not_read_full_vector_without_explicit_request(self):
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        app = dashboard.Dashboard(self.global_root)
        with patch('dev_memory_vectors.inspect_record', side_effect=AssertionError('full vector requires explicit request')):
            page = app.detail(key, mid)
        self.assertIn('完整向量只在你主动选择查看时读取', page)
        self.assertIn('vector=1', page)

    def _seed(self) -> tuple[str, str]:
        project_id = self.add_project_rule(turn="dashboard-project", title="<script>alert(1)</script>")
        global_record = self.record(scope="global", kind="preference", title="Reuse implementations",
                                    content="Review existing implementations before writing new code.")
        global_record.update(claim_type="preference", strength="soft", tags=["implementation"])
        result = self.apply(scope="global", turn="dashboard-global", operations=[
            {"op": "ADD", "scope": "global", "record": global_record}])
        global_id = result["stores"][0]["operations"][0]["id"]
        return project_id, global_id

    def test_index_reuses_status_and_limits_statistics_to_page(self):
        self._seed()
        app = dashboard.Dashboard(self.global_root)
        with patch.object(store, 'get_store_status', wraps=store.get_store_status) as status, \
             patch.object(store, 'recall_stats', wraps=store.recall_stats) as stats:
            app.index({})
        self.assertEqual(status.call_count, 1)
        self.assertFalse(status.call_args.kwargs['check_integrity'])
        self.assertLessEqual(len(stats.call_args.kwargs['memory_ids']), dashboard.PAGE_SIZE)

    def test_filtered_statistics_keep_total_without_loading_other_records(self):
        first, _ = self._seed()
        second = self.add_project_rule(turn='second-rule', title='Other rule')
        _, db, _ = store._config_for('project', self.project_a, self.global_root)
        store._record_recall_counts(db, [first, second])
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        stats = store.recall_stats('project', month, project_root=self.project_a,
                                   memory_ids=[first])
        self.assertEqual(stats['total_recalls'], 2)
        self.assertEqual([row['id'] for row in stats['memories']], [first])
        empty = store.recall_stats('project', month, project_root=self.project_a, memory_ids=[])
        self.assertEqual(empty['memories'], [])
        self.assertEqual(empty['total_recalls'], 2)

    def test_stored_vector_distinguishes_eligibility_and_source_version(self):
        import dev_memory_vectors as vectors
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        _, db, _ = store._config_for('project', self.project_a, self.global_root)
        conn = store._connect(db)
        with conn:
            vectors._schema(conn)
            conn.execute("INSERT INTO vector_state VALUES(?,?,?,'ready',1,'')", (mid, 0, 'old-model'))
        app = dashboard.Dashboard(self.global_root)
        page = app.index({'scope': key})
        self.assertIn('v0 / 当前 v1', page)
        self.assertIn('vector=1', page)
        with conn:
            conn.execute("UPDATE memories SET status='archived' WHERE id=?", (mid,))
        conn.close()
        rows, _, _ = app._list(key, '', 'all', 1)
        meta = app._vector_metadata(key, rows)[mid]
        self.assertFalse(meta['current'])
        self.assertEqual(meta['state'], 'not_eligible')

    def test_compact_edit_preserves_fields_and_invalidates_old_vector(self):
        import dev_memory_vectors as vectors
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        current = store.show_record('project', mid, project_root=self.project_a)['record']
        _, db, _ = store._config_for('project', self.project_a, self.global_root)
        conn = store._connect(db)
        with conn:
            vectors._schema(conn)
            conn.execute("INSERT INTO vector_state VALUES(?,?,?,'ready',1,'')", (mid, 1, 'old-model'))
        conn.close()
        app = dashboard.Dashboard(self.global_root)
        with patch.object(vectors, 'schedule') as schedule:
            app.action({'action': 'revise', 'scope': key, 'id': mid, 'revision': '1',
                        'title': '中文标题', 'content': '仅已签收订单可退款', 'reason': '用户确认修订'})
        schedule.assert_not_called()
        updated = store.show_record('project', mid, project_root=self.project_a)['record']
        self.assertEqual(updated['title'], '中文标题')
        for field in ('conditions', 'exceptions', 'do', 'dont'):
            self.assertEqual(updated[field], current[field])
        rows, _, _ = app._list(key, '', 'all', 1)
        self.assertFalse(app._vector_metadata(key, rows)[mid]['current'])

    def test_paused_scope_hides_edit_and_unknown_scope_never_falls_back_to_global(self):
        self._seed()
        base, _, config = store._config_for('global', None, self.global_root)
        config['capture_enabled'] = False
        store.write_json_atomic(base / 'config.json', config)
        app = dashboard.Dashboard(self.global_root)
        self.assertNotIn('<dialog id="edit-', app.index({}))
        with self.assertRaises(store.MemoryError) as missing:
            app.index({'scope': 'unregistered'})
        self.assertEqual(missing.exception.code, 'project_not_registered')

    def test_detail_hides_changes_when_paused_or_readonly_and_rejects_paused_post(self):
        mid, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        app = dashboard.Dashboard(self.global_root)
        store.set_capture('project', False, project_root=self.project_a)
        page = app.detail(key, mid)
        self.assertIn('仅已送达订单可退款', page)
        self.assertNotIn('value=revise', page)
        self.assertNotIn('value=archive', page)
        with self.assertRaises(store.MemoryError):
            app.action({'action':'revise', 'scope':key, 'id':mid, 'revision':'1',
                        'title':'被暂停的修改', 'content':'不应保存', 'reason':'隔离测试'})
        self.assertEqual(store.show_record('project', mid, project_root=self.project_a)['record']['revision'], 1)
        store.set_capture('project', True, project_root=self.project_a)
        _, database, _ = store._config_for('project', self.project_a, self.global_root)
        with patch.object(store.os, 'access', side_effect=lambda path, _mode: Path(path) != database):
            self.assertFalse(app._status(key)['writable'])
            self.assertNotIn('<dialog id="edit-', app.index({'scope':key}))
            page = app.detail(key, mid)
        self.assertNotIn('value=revise', page)
        self.assertNotIn('value=archive', page)

    def test_catalog_is_metadata_only_and_project_reads_keep_scope(self) -> None:
        project_id, global_id = self._seed()
        first = dashboard.register_project(self.project_a, self.global_root)
        dashboard.register_project(self.project_a, self.global_root)
        second = dashboard.register_project(self.project_b, self.global_root)
        self.assertEqual(len(dashboard.projects(self.global_root)), 2)
        catalog_text = dashboard._catalog_path(self.global_root).read_text(encoding="utf-8")
        self.assertNotIn("退款", catalog_text)
        app = dashboard.Dashboard(self.global_root)
        listing = app.index({"scope": first["namespace_id"], "status": "all"})
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", listing)
        self.assertNotIn("<script>alert(1)</script>", listing)
        self.assertNotIn("Reuse implementations", listing)
        detail = app.detail(first["namespace_id"], project_id)
        self.assertIn("仅已送达订单可退款", detail)
        self.assertIn("适用条件", detail)
        self.assertNotIn("Review existing implementations", detail)
        self.assertEqual(app._list(second["namespace_id"], "", "all", 1)[2], 0)
        self.assertTrue(dashboard.remove_project(first["namespace_id"], self.global_root))
        self.assertTrue((self.project_a / ".dev-memory" / "memory.sqlite3").exists())
        self.assertEqual(app._list("global", "", "all", 1)[2], 1)
        self.assertEqual(global_id, app._list("global", "", "all", 1)[0][0]["id"])

    def test_project_setup_registers_new_project(self) -> None:
        skill = Path(dashboard.__file__).parents[1]
        result = setup.setup(self.project_a, "codex", skill, sys.executable, self.global_root)
        self.assertEqual(result["status"], "initialized")
        self.assertEqual(result["dashboard_registration"], "registered")
        self.assertEqual(len(dashboard.projects(self.global_root)), 1)

    def test_preview_and_browsing_do_not_increment_recall_counts(self) -> None:
        project_id, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)["namespace_id"]
        app = dashboard.Dashboard(self.global_root)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        before = store.recall_stats("project", month, project_root=self.project_a)
        self.assertEqual(before["total_recalls"], 0)
        app.index({"scope": key, "status": "all", "month": month})
        app.detail(key, project_id)
        preview = app.preview(key, "退款 已送达", "planning")
        self.assertIn("只读预览", preview)
        after = store.recall_stats("project", month, project_root=self.project_a)
        self.assertEqual(after["total_recalls"], 0)
        store.recall("退款 已送达", project_root=self.project_a, global_root=self.global_root, force=True)
        self.assertEqual(store.recall_stats("project", month, project_root=self.project_a)["total_recalls"], 1)

    def test_default_preview_matches_daily_recall_and_expansion_is_explicit(self):
        for n in range(6):
            self.add_project_rule(turn=f'preview-{n}', title=f'Export {n}', content=f'Export requirement {n}',
                                  conditions='', exceptions='', do='', dont='', verification_steps='', tags=[])
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        app = dashboard.Dashboard(self.global_root)
        normal = store.recall('Export', project_root=self.project_a, global_root=self.global_root, readonly=True)
        page = app.preview(key, 'Export', None)
        self.assertEqual(page.count('正文已返回'), len(normal['stores'][1]['records']))
        self.assertIn('日常默认：5 条／4000 字符', page)
        self.assertIn('关键词匹配', page)
        self.assertIn('条数额度不足', page)
        self.assertIn('runtime_not_configured', page)
        self.assertIn('v1', page)
        expanded = app.preview(key, 'Export', None, 'expanded')
        self.assertIn('结果不代表日常默认调用', expanded)
        self.assertIn('name="mode"', app.index({'scope':key}))
        with self.assertRaises(store.MemoryError):
            app.preview(key, 'Export', None, 'anything')

    def test_preview_escapes_diagnostics_and_exposes_degraded_vector_recall(self):
        mid = self.add_project_rule(title='<script>Export</script>', content='Export requirement.')
        key = dashboard.register_project(self.project_a, self.global_root)['namespace_id']
        with patch('dev_memory_vectors.search', return_value={'status':'deferred','reason':'query_timeout','records':[]}):
            page = dashboard.Dashboard(self.global_root).preview(key, 'Export', None)
        self.assertNotIn('<script>Export</script>', page)
        self.assertIn('&lt;script&gt;Export&lt;/script&gt;', page)
        self.assertIn('query_timeout', page)
        self.assertIn('语义检索未参与', page)
        self.assertIn(mid, page)

    def test_page_through_more_than_existing_list_limit(self) -> None:
        self._seed()
        _, db, config = store._config_for("project", self.project_a, self.global_root)
        conn = store._connect(db)
        source = conn.execute("SELECT * FROM memories WHERE scope='project' LIMIT 1").fetchone()
        columns = [row[1] for row in conn.execute("PRAGMA table_info(memories)")]
        template = dict(zip(columns, source))
        for n in range(205):
            template["id"] = f"dashboard-{n:03}"
            template["title"] = f"Generated {n:03}"
            template["semantic_hash"] = f"dashboard-hash-{n:03}"
            conn.execute(f"INSERT INTO memories({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                         tuple(template[column] for column in columns))
        conn.commit(); conn.close()
        key = dashboard.register_project(self.project_a, self.global_root)["namespace_id"]
        app = dashboard.Dashboard(self.global_root)
        rows, more, total = app._list(key, "", "all", 35)
        self.assertEqual(total, 206)
        self.assertEqual(len(rows), 2)
        self.assertFalse(more)

    def test_management_checks_revision_and_forget_preview(self) -> None:
        project_id, _ = self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)["namespace_id"]
        app = dashboard.Dashboard(self.global_root)
        current = store.show_record("project", project_id, project_root=self.project_a)["record"]
        form = {field: str(current.get(field, "")) for field in
                ("title", "content", "conditions", "exceptions", "do", "dont", "rationale", "verification_steps")}
        form.update(action="revise", scope=key, id=project_id, revision=str(current["revision"]),
                    reason="用户在看板中确认新规则", content="仅已签收订单可退款")
        app.action(form)
        self.assertEqual(store.show_record("project", project_id, project_root=self.project_a)["record"]["content"],
                         "仅已签收订单可退款")
        with self.assertRaises(store.MemoryError) as stale:
            app.action(form)
        self.assertEqual(stale.exception.code, "revision_conflict")
        revision = store.show_record("project", project_id, project_root=self.project_a)["record"]["revision"]
        app.action({"action": "archive", "scope": key, "id": project_id,
                    "revision": str(revision), "confirm": "yes"})
        self.assertEqual(store.show_record("project", project_id, project_root=self.project_a)["record"]["status"], "archived")
        preview = app.forget_preview(key, project_id)
        self.assertIn("永久遗忘", preview)
        token = store.forget_preview("project", project_id, project_root=self.project_a)["confirmation_token"]
        app.action({"action": "forget", "scope": key, "id": project_id,
                    "token": token, "confirm": "yes"})
        with self.assertRaises(store.MemoryError):
            store.show_record("project", project_id, project_root=self.project_a)

    def test_disabled_statistics_do_not_expose_titles(self) -> None:
        self._seed()
        base, _, config = store._config_for("project", self.project_a, self.global_root)
        config["recall_enabled"] = False
        store.write_json_atomic(base / "config.json", config)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        result = store.recall_stats("project", month, project_root=self.project_a)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["memories"], [])
        key = dashboard.register_project(self.project_a, self.global_root)["namespace_id"]
        page = dashboard.Dashboard(self.global_root).index({"scope": key, "status": "all"})
        self.assertNotIn("alert(1)", page)

    def test_global_candidate_requires_explicit_confirmation(self) -> None:
        candidate = {"kind": "preference", "claim_type": "preference", "status": "candidate",
                     "strength": "soft", "title": "Read existing implementation",
                     "content": "Read the current implementation before changing behavior.",
                     "cross_project_confirmed": False, "tags": ["analysis"],
                     "source": {"type": "user_statement", "excerpt": "先检查已有实现。"}}
        saved = self.apply(scope="global", turn="dashboard-candidate", task="candidate-task",
                           operations=[{"op": "ADD", "scope": "global", "record": candidate}])
        memory_id = saved["stores"][0]["operations"][0]["id"]
        app = dashboard.Dashboard(self.global_root)
        with self.assertRaises(store.MemoryError) as missing_confirmation:
            app.action({"action": "confirm", "scope": "global", "id": memory_id, "revision": "1"})
        self.assertEqual(missing_confirmation.exception.code, "confirmation_required")
        app.action({"action": "confirm", "scope": "global", "id": memory_id,
                    "revision": "1", "confirm": "yes"})
        current = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        self.assertEqual(current["status"], "active")
        self.assertTrue(current["cross_project_confirmed"])

    def test_controls_and_backup_do_not_mix_stores(self) -> None:
        self._seed()
        key = dashboard.register_project(self.project_a, self.global_root)["namespace_id"]
        app = dashboard.Dashboard(self.global_root)
        app.action({"action": "control", "scope": key, "mode": "disable"})
        self.assertFalse(store.get_store_status("project", project_root=self.project_a)["recall_enabled"])
        self.assertTrue(store.get_store_status("global", global_root=self.global_root)["recall_enabled"])
        app.action({"action": "control", "scope": key, "mode": "on"})
        app.action({"action": "mode", "scope": key, "mode": "developer-first"})
        self.assertEqual(store.get_store_status("project", project_root=self.project_a)["capture_mode"], "developer-first")
        app.action({"action": "backup", "scope": key})
        self.assertTrue(list((self.project_a / ".dev-memory" / "backups").glob("*.sqlite3")))
        self.assertFalse(list((self.global_root / "global" / "backups").glob("*.sqlite3")))

    def test_browser_launcher_cannot_block_or_abort_server(self) -> None:
        self._seed()
        scripts = str(Path(dashboard.__file__).parent)
        for launch in ("import time; time.sleep(60)",
                       "raise dashboard.webbrowser.Error('no browser')",
                       "raise OSError('no desktop')", "return False"):
            with self.subTest(launch=launch):
                code = ("import sys\nfrom pathlib import Path\n"
                        f"sys.path.insert(0, {scripts!r})\n"
                        "import dev_memory_dashboard as dashboard\n"
                        f"def launch(url):\n    {launch}\n"
                        "dashboard.webbrowser.open = launch\n"
                        f"dashboard.serve(Path({str(self.global_root)!r}))\n")
                process = subprocess.Popen([sys.executable, "-u", "-c", code],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                lines: queue.Queue[str] = queue.Queue()
                reader = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
                reader.start()
                try:
                    url = lines.get(timeout=15).strip()
                    self.assertTrue(url.startswith("http://127.0.0.1:"), url)
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                    with opener.open(url, timeout=5) as response:
                        self.assertIn("记忆总览", response.read().decode())
                finally:
                    process.kill()
                    _, errors = process.communicate(timeout=5)
                    reader.join(timeout=5)
                self.assertIn("Ctrl+C", errors)
                self.assertNotIn("Traceback", errors)

    def test_unreadable_project_catalog_keeps_global_view_and_does_not_raise_server_error(self) -> None:
        self._seed()
        scripts = str(Path(dashboard.__file__).parent)
        code = ("import sys\nfrom pathlib import Path\n"
                f"sys.path.insert(0, {scripts!r})\n"
                "import dev_memory_dashboard as dashboard\n"
                "dashboard.projects = lambda _root=None: (_ for _ in ()).throw(PermissionError('access denied'))\n"
                f"dashboard.serve(Path({str(self.global_root)!r}), open_browser=False)\n")
        process = subprocess.Popen([sys.executable, "-u", "-c", code], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                             urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            url = lines.get(timeout=15).strip()
            with opener.open(url, timeout=5) as response:
                body = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertIn("项目列表暂不可用", body)
                self.assertIn("记忆总览", body)
                self.assertIn("Reuse implementations", body)
        finally:
            process.kill()
            _, errors = process.communicate(timeout=5)
        self.assertNotIn("Traceback", errors)

    def test_live_loopback_page_rejects_foreign_host_and_missing_csrf(self) -> None:
        project_id, _ = self._seed()
        script = Path(dashboard.__file__).with_name("dev_memory.py")
        process = subprocess.Popen([sys.executable, "-u", str(script), "--global-root", str(self.global_root),
                                    "dashboard", "serve", "--project-root", str(self.project_a), "--no-open"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        lines: queue.Queue[str] = queue.Queue()
        thread = threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            url = lines.get(timeout=30).strip()
            self.assertTrue(url.startswith("http://127.0.0.1:"), url)
            with opener.open(url, timeout=5) as response:
                body = response.read().decode()
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertEqual(response.headers['Referrer-Policy'], 'same-origin')
                self.assertIn("记忆总览", body)
                csp = response.headers["Content-Security-Policy"]
                nonce = re.search(r"script-src 'nonce-([^']+)'", csp)
                self.assertIsNotNone(nonce)
                self.assertIn(f'<script nonce="{nonce.group(1)}">', body)
            csrf = re.search(r'name=csrf value="([^"]+)"', body)
            self.assertIsNotNone(csrf)
            clean_url = urlsplit(url)._replace(query="").geturl()
            outsider = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with self.assertRaises(urllib.error.HTTPError) as unauthenticated:
                outsider.open(clean_url, timeout=5)
            self.assertEqual(unauthenticated.exception.code, 403)
            unauthenticated.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as foreign:
                opener.open(urllib.request.Request(url, headers={"Host": "example.com"}), timeout=5)
            self.assertEqual(foreign.exception.code, 403)
            foreign.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as forgery:
                opener.open(urllib.request.Request(clean_url + "action", data=b"action=backup&scope=global"), timeout=5)
            self.assertEqual(forgery.exception.code, 403)
            forgery.exception.close()
            key = dashboard.projects(self.global_root)[0]["namespace_id"]
            preview = urllib.request.Request(clean_url + "preview",
                                             data=urlencode({"csrf": csrf.group(1), "scope": key,
                                                             "q": "退款 已送达"}).encode(),
                                             headers={"Origin": urlsplit(clean_url).scheme + "://" +
                                                      urlsplit(clean_url).netloc + "/"})
            with opener.open(preview, timeout=5) as response:
                self.assertIn("只读预览", response.read().decode())
            bad_origin = urllib.request.Request(clean_url + "preview",
                                                data=urlencode({"csrf": csrf.group(1), "scope": key,
                                                                "q": "退款"}).encode(),
                                                headers={"Origin": "https://example.com"})
            with self.assertRaises(urllib.error.HTTPError) as origin_rejected:
                opener.open(bad_origin, timeout=5)
            self.assertEqual(origin_rejected.exception.code, 403)
            self.assertIn("来源与本机看板不一致", origin_rejected.exception.read().decode())
            origin_rejected.exception.close()
            for origin in ('null', 'http://127.0.0.1:notaport', 'http://[broken', clean_url + '?query', clean_url + '#fragment'):
                with self.subTest(origin=origin):
                    request = urllib.request.Request(clean_url + 'preview',
                        data=urlencode({'csrf':csrf.group(1), 'scope':key, 'q':'退款'}).encode(),
                        headers={'Origin':origin})
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        opener.open(request, timeout=5)
                    self.assertEqual(rejected.exception.code, 403)
                    rejected.exception.close()
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            self.assertEqual(store.recall_stats("project", month, project_root=self.project_a)["total_recalls"], 0)
            backup = urllib.request.Request(clean_url + "action",
                                            data=urlencode({"csrf": csrf.group(1), "scope": key,
                                                            "action": "backup"}).encode())
            with opener.open(backup, timeout=5) as response:
                self.assertIn("备份已创建", response.read().decode())
            self.assertTrue(list((self.project_a / ".dev-memory" / "backups").glob("*.sqlite3")))
            edit = {"csrf": csrf.group(1), "scope": key, "id": project_id, "revision": "1",
                    "action": "revise", "content": "Updated refund rule", "conditions": "", "exceptions": "",
                    "reason": "The old conditions and exceptions no longer apply."}
            with opener.open(urllib.request.Request(clean_url + "action", data=urlencode(edit).encode()), timeout=5) as response:
                self.assertIn("Updated refund rule", response.read().decode())
            record = store.show_record("project", project_id, project_root=self.project_a)["record"]
            self.assertEqual(record["conditions"], "")
            self.assertEqual(record["exceptions"], "")
            for field in ("title", "content"):
                with self.subTest(empty_required_field=field):
                    invalid = {**edit, "revision": str(record["revision"]), field: ""}
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        opener.open(urllib.request.Request(clean_url + "action", data=urlencode(invalid).encode()), timeout=5)
                    self.assertEqual(rejected.exception.code, 400)
                    rejected.exception.close()
                    unchanged = store.show_record("project", project_id, project_root=self.project_a)["record"]
                    self.assertEqual(unchanged, record)
            with self.subTest(request='empty_scope'):
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    with opener.open(clean_url + '?scope=', timeout=5):
                        pass
                self.assertEqual(rejected.exception.code, 400)
                rejected.exception.close()
            with self.subTest(request='non_ascii_access_token'):
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    outsider.open(clean_url + '?' + urlencode({'access':'无效令牌'}), timeout=5)
                self.assertEqual(rejected.exception.code, 403)
                rejected.exception.close()
            with self.subTest(request='non_ascii_csrf_token'):
                request = urllib.request.Request(clean_url + 'action', data=urlencode({
                    'csrf':'无效令牌', 'action':'backup', 'scope':key}).encode())
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    opener.open(request, timeout=5)
                self.assertEqual(rejected.exception.code, 403)
                rejected.exception.close()
            with self.subTest(request='malformed_url'):
                parsed = urlsplit(clean_url)
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
                try:
                    connection.request('GET', 'http://[broken', headers={'Host':parsed.netloc})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    connection.close()
        except Exception as exc:
            process.terminate()
            _, errors = process.communicate(timeout=5)
            self.fail(f"Live dashboard failed: {exc}; server stderr: {errors}")
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)

    def test_two_dashboard_ports_keep_independent_browser_sessions(self) -> None:
        self._seed()
        script = Path(dashboard.__file__).with_name("dev_memory.py")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                            urllib.request.HTTPCookieProcessor(jar))
        processes, sessions = [], []
        try:
            for _ in range(2):
                process = subprocess.Popen([sys.executable, "-u", str(script), "--global-root", str(self.global_root),
                                            "dashboard", "serve", "--no-open"],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(process)
                lines: queue.Queue[str] = queue.Queue()
                threading.Thread(target=lambda p=process, q=lines: q.put(p.stdout.readline()), daemon=True).start()
                url = lines.get(timeout=30).strip()
                self.assertTrue(url.startswith("http://127.0.0.1:"), url)
                with opener.open(url, timeout=5) as response:
                    body = response.read().decode()
                csrf = re.search(r'name=csrf value="([^"]+)"', body).group(1)
                sessions.append((urlsplit(url)._replace(query="").geturl(), csrf))
            for url, csrf in sessions:
                with opener.open(url, timeout=5) as response:
                    self.assertIn("记忆总览", response.read().decode())
                preview = {"csrf": csrf, "scope": "global", "q": "Reuse implementations"}
                with opener.open(urllib.request.Request(url + "preview", data=urlencode(preview).encode()), timeout=5) as response:
                    self.assertIn("只读预览", response.read().decode())
            self.assertEqual(len(list(jar)), 2)
            for cookie in jar:
                self.assertTrue(cookie.has_nonstandard_attr("HttpOnly"))
                self.assertEqual(cookie.get_nonstandard_attr("SameSite"), "Strict")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=5)

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "dev-memory" / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "evals"))

import dev_memory_store as store
import dev_memory
import bench_compare


class MemoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dev memory 中文 ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.global_root = self.home / "global data"
        self.project_a = self.home / "项目 A"
        self.project_b = self.home / "project B"
        self.project_a.mkdir()
        self.project_b.mkdir()
        store.init_global(self.global_root)
        store.init_project(self.project_a)
        store.init_project(self.project_b)

    def source(self, excerpt: str, source_type: str = "user_statement") -> dict:
        return {"type": source_type, "excerpt": excerpt}

    def record(self, *, kind: str = "business_rule", title: str = "退款规则", content: str = "仅已送达订单可退款",
               scope: str = "project", **fields) -> dict:
        value = {
            "kind": kind, "claim_type": "desired", "strength": "hard", "title": title, "content": content,
            "conditions": "订单已送达，商品未拆封，购买后 14 天内。", "exceptions": "礼品订单和最终销售商品除外。",
            "do": "实施时要求全部条件成立。", "dont": "不得为礼品单或最终销售商品退款。",
            "verification_steps": "测试每一正向条件以及两类排除项。", "tags": ["refund"],
            "source": self.source("退款只限已送达、未拆封且 14 天内。", "user_feedback"),
        }
        value.update(fields)
        if scope == "global":
            value["cross_project_confirmed"] = True
            value["source"] = self.source("这项研发规范明确适用于我之后的所有项目。", "user_confirmation")
        return value

    def apply(self, *, scope: str, operations: list[dict], project: Path | None = None,
              turn: str = "turn-1", idem: str | None = None, task: str | None = None,
              global_root: Path | None = None, maintenance: str = 'defer', include_task: bool = False) -> dict:
        payload = {"schema_version": 1, "scope": scope, "session_id": "session-test", "turn_id": turn,
                   "idempotency_key": idem or f"idem-{turn}", "task_id": task, "operations": operations,
                   'maintenance': maintenance, 'include_task': include_task}
        return store.apply_payload(payload, project_root=project or self.project_a,
                                   global_root=global_root or self.global_root)

    def add_project_rule(self, *, project: Path | None = None, turn: str = "turn-1", **kwargs) -> str:
        result = self.apply(scope="project", project=project, turn=turn,
                            operations=[{"op": "ADD", "scope": "project", "record": self.record(**kwargs)}])
        self.assertEqual(result["status"], "saved", result)
        return result["stores"][0]["operations"][0]["id"]


class StoreTests(MemoryTestCase):
    def test_explicit_global_developer_habit_is_recalled_in_two_projects(self) -> None:
        habit = self.record(scope="global", kind="preference", title="Reuse existing code",
                            content="Before adding an implementation, inspect and reuse a suitable existing path.")
        habit.update(claim_type="preference", strength="soft", conditions="When an existing implementation may fit.",
                     exceptions="Add a new path when existing code cannot meet the requirement.",
                     do="Inspect current code and reuse a suitable implementation.",
                     dont="Do not add parallel code before checking existing behavior.", tags=["implementation"])
        saved = self.apply(scope="global", turn="explicit-global-habit", operations=[
            {"op": "ADD", "scope": "global", "record": habit}])
        self.assertEqual(saved["status"], "saved", saved)
        habit_id = saved["stores"][0]["operations"][0]["id"]
        for project in (self.project_a, self.project_b):
            recalled = store.recall("reuse existing implementation", project_root=project,
                                    global_root=self.global_root, force=True)
            self.assertTrue(any(item["id"] == habit_id for item in recalled["stores"][0]["records"]))

    def test_global_capture_off_blocks_habit_learning(self) -> None:
        base, _, config = store._config_for("global", None, self.global_root)
        config["capture_enabled"] = False
        store.write_json_atomic(base / "config.json", config)
        habit = {"kind": "preference", "claim_type": "preference", "status": "candidate",
                 "strength": "soft", "title": "Prefer narrow changes",
                 "content": "Use the smallest change that fully addresses the observed issue.",
                 "cross_project_confirmed": False,
                 "source": {"type": "user_feedback", "excerpt": "The user preferred a narrower implementation."}}
        result = self.apply(scope="global", task="task-one", turn="capture-disabled", operations=[
            {"op": "ADD", "scope": "global", "record": habit}])
        self.assertEqual(result["status"], "skipped_private")
        self.assertEqual(store.list_records("global", global_root=self.global_root)["records"], [])

    def test_inferred_global_habit_needs_two_independent_user_tasks_and_is_shared(self) -> None:
        habit = {"kind": "preference", "claim_type": "preference", "status": "candidate", "strength": "soft",
                 "title": "Reuse existing code", "content": "Prefer reusing a suitable existing implementation before adding another one.",
                 "conditions": "When an existing implementation fits the requested behavior.",
                 "exceptions": "Add a new implementation when the existing one does not fit.",
                 "do": "Inspect existing code and reuse a suitable path.", "dont": "Do not add parallel code without checking for an existing implementation.",
                 "cross_project_confirmed": False,
                 "source": {"type": "user_feedback", "excerpt": "User corrected the approach to reuse an existing implementation."}}
        def signal(task: str, turn: str):
            return self.apply(scope="global", task=task, turn=turn,
                              operations=[{"op": "ADD", "scope": "global", "record": dict(habit)}])

        first = signal("task-alpha", "habit-one")
        self.assertEqual(first["stores"][0]["operations"][0]["habit_promoted"], False)
        memory_id = first["stores"][0]["operations"][0]["id"]
        record = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        self.assertEqual(record["status"], "candidate")
        signal("task-alpha", "habit-repeat")  # Same task, different turn: still one signal.
        record = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        self.assertEqual(record["status"], "candidate")
        third = signal("task-beta", "habit-two")
        self.assertTrue(third["stores"][0]["operations"][0]["habit_promoted"])
        record = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        self.assertEqual((record["status"], record["strength"], record["cross_project_confirmed"]), ("active", "soft", False))
        self.assertFalse(record["source_refs"])
        conn = store._connect(store.global_paths(self.global_root)[1], readonly=True)
        ids = [row[0] for row in conn.execute("SELECT ingestion_id FROM evidence WHERE memory_id=?", (memory_id,))]
        conn.close()
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(item.startswith("habit:") for item in ids))
        self.assertNotIn("task-alpha", " ".join(ids))
        other_project = store.recall("reuse existing code", project_root=self.project_b, global_root=self.global_root)
        self.assertTrue(any(row["id"] == memory_id for row in other_project["stores"][0]["records"]))
        current = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        revised = dict(habit, status="active", content="Prefer extending a suitable existing implementation before adding a parallel one.",
                       source={"type": "user_feedback", "excerpt": "User corrected this reusable preference."})
        changed = self.apply(scope="global", task="task-gamma", turn="habit-correction", operations=[
            {"op": "REVISE", "scope": "global", "id": memory_id, "expected_revision": current["revision"], "record": revised}])
        self.assertEqual(changed["status"], "saved", changed)
        corrected = store.show_record("global", memory_id, global_root=self.global_root)["record"]
        self.assertEqual(corrected["content"], revised["content"])
        self.assertEqual(corrected["status"], "active")

    def test_global_habit_candidates_reject_model_summaries_and_project_content(self) -> None:
        candidate = {"kind": "preference", "claim_type": "preference", "status": "candidate", "strength": "soft",
                     "title": "Prefer narrow fixes", "content": "Prefer narrow fixes that address the evidenced cause.",
                     "cross_project_confirmed": False,
                     "source": {"type": "model_inference", "excerpt": "The assistant inferred this preference."}}
        rejected = self.apply(scope="global", task="task-one", turn="model-only",
                             operations=[{"op": "ADD", "scope": "global", "record": candidate}])
        self.assertEqual(rejected["stores"][0]["error"], "provenance_error")
        candidate["source"] = {"type": "user_feedback", "excerpt": "User preferred this change for project_id:team-a."}
        rejected = self.apply(scope="global", task="task-one", turn="project-text",
                             operations=[{"op": "ADD", "scope": "global", "record": candidate}])
        self.assertEqual(rejected["stores"][0]["error"], "scope_error")

    def test_developer_first_project_capture_skips_records_until_mode_enabled(self) -> None:
        project = self.home / "developer-first"
        project.mkdir()
        store.init_project(project, capture_mode="developer-first")
        payload = {"schema_version": 1, "scope": "task", "session_id": "s", "turn_id": "t",
                   "task_id": "task-1", "idempotency_key": "developer-first-add",
                   "operations": [{"op": "CHECKPOINT", "scope": "task", "record": self.record(kind="checkpoint")}]}
        result = store.apply_payload(payload, project_root=project, global_root=self.global_root)
        self.assertEqual(result["status"], "skipped_developer_first")
        base, _, config = store._config_for("project", project, self.global_root)
        config["capture_mode"] = "full-project"
        store.write_json_atomic(base / "config.json", config)
        payload["idempotency_key"] = "full-project-add"
        self.assertEqual(store.apply_payload(payload, project_root=project, global_root=self.global_root)["status"], "saved")

    def test_growth_recall_uses_sqlite_index_and_returns_bounded_records(self) -> None:
        operations = []
        for number in range(300):
            operations.append({"op": "ADD", "scope": "global", "record": {
                "kind": "preference", "claim_type": "preference", "strength": "soft", "status": "active",
                "title": f"Synthetic habit {number:03d}", "content": f"For synthetic topic-{number:03d}, prefer evidence-based narrow changes.",
                "cross_project_confirmed": True,
                "source": {"type": "user_confirmation", "excerpt": "This synthetic habit is a test fixture."}}})
        result = self.apply(scope="global", turn="growth-seed", operations=operations)
        self.assertEqual(result["status"], "saved", result)
        _, db = store.global_paths(self.global_root)
        conn = store._connect(db, readonly=True)
        plan = [row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT m.id FROM search_terms st INDEXED BY search_term_term "
            "CROSS JOIN memories m ON m.id=st.memory_id "
            "WHERE st.term=? AND m.scope='global' AND m.status IN ('active','conflicted')", ("topic-299",))]
        conn.close()
        self.assertTrue(any("search_term_term" in row for row in plan), plan)
        started = time.perf_counter()
        for index in range(10):
            recalled = store.recall("topic-299", project_root=None, global_root=self.global_root,
                                   max_candidates=10, max_details=2, max_chars=1500,
                                   session_id=f"growth-{index}", force=True)
            self.assertLessEqual(len(recalled["stores"][0]["records"]), 2)
            self.assertLessEqual(recalled["stores"][0]["matched_count"], 2 * 10 + 2)
            self.assertTrue(recalled["stores"][0]["candidate_limit_reached"])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 3.0, f"bounded recall took {elapsed:.3f}s for 300 records x10")

    def test_resume_recovers_checkpoint_candidates_without_binding_a_task(self) -> None:
        for task in ("task-a", "task-b"):
            self.apply(scope="task", task=task, turn=task, operations=[
                {"op": "CHECKPOINT", "scope": "task", "record": self.record(kind="checkpoint", title=task)}])
        ordinary = store.recall("continue", project_root=self.project_a, global_root=self.global_root)
        self.assertFalse(any(r["kind"] == "checkpoint" for block in ordinary["stores"] for r in block["records"]))
        resumed = store.recall("continue", project_root=self.project_a, global_root=self.global_root, resume=True, force=True)
        block = resumed["stores"][1]
        self.assertEqual({r["task_id"] for r in block["records"]}, {"task-a", "task-b"})
        self.assertIsNone(block["task_id"])
        b = store.recall("continue", project_root=self.project_b, global_root=self.global_root, resume=True, force=True)
        self.assertFalse(b["stores"][1]["records"])
        limited = store.recall("continue", project_root=self.project_a, global_root=self.global_root, resume=True,
                               max_details=1, force=True)
        self.assertTrue(limited["stores"][1]["context_incomplete"])

    def test_mixed_batch_project_context_does_not_stamp_global_records(self) -> None:
        global_rule = self.record(scope="global", kind="preference", title="Reply order", content="Conclusion first.",
                                  conditions="All development projects", exceptions="", dont="")
        payload = {"schema_version": 1, "scope": "both", "session_id": "mixed-session", "turn_id": "mixed-turn",
                   "task_id": "task-a", "branch": "project-A-private-branch", "commit_id": "abc123",
                   "idempotency_key": "mixed-context", "operations": [
                       {"op": "ADD", "scope": "global", "record": global_rule},
                       {"op": "CHECKPOINT", "scope": "task", "record": self.record(kind="checkpoint")}]}
        result = store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result["status"], "saved", result)
        global_id = result["stores"][0]["operations"][0]["id"]
        record = store.show_record("global", global_id, global_root=self.global_root)["record"]
        for key in ("task_id", "branch", "commit_id", "workspace_id"):
            self.assertFalse(record.get(key), key)
        project_id = result["stores"][1]["operations"][0]["id"]
        self.assertEqual(store.show_record("project", project_id, project_root=self.project_a)["record"]["task_id"], "task-a")
        payload["idempotency_key"] = "explicit-global-task"
        payload["operations"][0]["record"]["task_id"] = "task-a"
        self.assertEqual(store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)["stores"][0]["status"], "failed")

    def test_independent_paths_and_empty_namespaces(self) -> None:
        gbase, gdb = store.global_paths(self.global_root)
        self.assertEqual(gbase, (self.global_root / "global").resolve())
        self.assertEqual(gdb, (self.global_root / "global" / "memory.sqlite3").resolve())
        self.assertEqual(store.project_paths(self.project_a)[0], (self.project_a / ".dev-memory").resolve())
        self.assertNotEqual(store._config_for("project", self.project_a, self.global_root)[2]["namespace_id"],
                            store._config_for("project", self.project_b, self.global_root)[2]["namespace_id"])

    def test_legacy_session_cache_schema_migrates_without_losing_binding(self) -> None:
        _, db = store.global_paths(self.global_root)
        config = store.read_json(store.config_path_for("global", global_root=self.global_root))
        conn = store._connect(db)
        conn.execute("DROP TABLE session_context")
        conn.execute("CREATE TABLE session_context(session_id TEXT PRIMARY KEY,context_key TEXT NOT NULL,updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO session_context VALUES('legacy-session','legacy-key','2026-01-01T00:00:00+00:00')")
        conn.commit()
        conn.close()
        store._init_database(db, config["namespace_id"], "global")
        conn = store._connect(db, readonly=True)
        info = conn.execute("PRAGMA table_info(session_context)").fetchall()
        saved = conn.execute("SELECT context_key FROM session_context WHERE session_id=?", ("legacy-session",)).fetchone()
        conn.close()
        self.assertEqual([row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])],
                         ["session_id", "context_key"])
        self.assertEqual(saved[0], "legacy-key")

    def test_project_recall_never_reads_other_project(self) -> None:
        self.add_project_rule(content="项目 A 的退款规则是已送达、未拆封、14 天内。")
        self.apply(scope="project", project=self.project_b, turn="turn-b", operations=[
            {"op": "ADD", "scope": "project", "record": self.record(content="项目 B 只允许 7 天内退款。", conditions="7 天内。")}
        ])
        a = store.recall("退款规则", project_root=self.project_a, global_root=self.global_root)
        b = store.recall("退款规则", project_root=self.project_b, global_root=self.global_root)
        a_ids = {r["id"] for block in a["stores"] for r in block["records"]}
        b_ids = {r["id"] for block in b["stores"] for r in block["records"]}
        self.assertTrue(a_ids)
        self.assertTrue(b_ids)
        self.assertFalse(a_ids & b_ids)

    def test_project_a_correction_resumes_and_only_global_preference_crosses_to_project_b(self) -> None:
        original = self.record(title="Refund eligibility", content="Delivered, unopened orders within 30 days; gifts and final-sale items excluded.",
                               conditions="Delivered, unopened, no more than 30 days.")
        added = self.apply(scope="project", turn="refund-original", task="refund-task", operations=[
            {"op": "ADD", "scope": "project", "record": original}
        ])
        rule_id = added["stores"][0]["operations"][0]["id"]
        prior = store.show_record("project", rule_id, project_root=self.project_a)["record"]
        corrected = self.record(title="Refund eligibility", content="Delivered, unopened orders within 14 days; gifts and final-sale items excluded.",
                                conditions="Delivered, unopened, no more than 14 days.", exceptions="Gift and final-sale items are excluded.")
        correction = self.apply(scope="project", turn="refund-correction", task="refund-task", operations=[
            {"op": "REVISE", "scope": "project", "id": rule_id,
             "expected_revision": prior["revision"], "record": corrected}
        ])
        self.assertEqual(correction["status"], "saved")
        checkpoint = {"kind": "checkpoint", "claim_type": "observed", "title": "Refund eligibility task",
                      "content": "Corrected the project rule to 14 days. Implementation remains; next implement and run tests.",
                      "source": self.source("The correction was saved; implementation remains.", "user_feedback")}
        saved_checkpoint = self.apply(scope="task", turn="refund-checkpoint", task="refund-task", operations=[
            {"op": "CHECKPOINT", "scope": "task", "record": checkpoint}
        ])
        self.assertEqual(saved_checkpoint["status"], "saved")
        global_preference = self.record(scope="global", kind="preference", title="Progress reporting",
                                        content="Keep progress reports concise and state tests only when actually run.",
                                        conditions="", exceptions="", do="", dont="", verification_steps="")
        global_saved = self.apply(scope="global", turn="confirmed-preference", operations=[
            {"op": "ADD", "scope": "global", "record": global_preference}
        ])
        self.assertEqual(global_saved["status"], "saved")

        resumed = store.recall("refund eligibility", project_root=self.project_a, global_root=self.global_root,
                               session_id="new-a-session", task_id="refund-task", force=True)
        resumed_records = [row for block in resumed["stores"] for row in block["records"]]
        corrected_rule = next(row for row in resumed_records if row["id"] == rule_id)
        self.assertIn("14 days", corrected_rule["content"])
        self.assertNotIn("30 days", corrected_rule["content"])
        self.assertTrue(any(row["kind"] == "checkpoint" and "next implement" in row["content"]
                            for row in resumed_records))

        project_b = store.recall("refund eligibility", project_root=self.project_b, global_root=self.global_root,
                                 session_id="b-session", force=True)
        project_b_records = [row for block in project_b["stores"] for row in block["records"]]
        self.assertTrue(any(row["scope"] == "global" and row["kind"] == "preference" for row in project_b_records))
        self.assertFalse(any(row["id"] == rule_id or "14 days" in row["content"] for row in project_b_records))

    def test_project_config_cannot_redirect_project_content_to_global(self) -> None:
        config_path = self.project_a / ".dev-memory" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config.update({"global_root": str(self.global_root), "scope": "global", "telemetry": True})
        config_path.write_text(json.dumps(config), encoding="utf-8")
        result = self.apply(scope="project", turn="untrusted-config", operations=[
            {"op": "ADD", "scope": "project", "record": self.record(content="This business rule remains project-local.")}
        ])
        self.assertEqual(result["status"], "saved")
        self.assertEqual(len(store.list_records("project", project_root=self.project_a)["records"]), 1)
        self.assertEqual(store.list_records("global", global_root=self.global_root)["records"], [])

    def test_global_requires_explicit_confirmation_and_global_kind(self) -> None:
        rule = self.record(scope="global", kind="business_rule")
        result = self.apply(scope="global", operations=[{"op": "ADD", "scope": "global", "record": rule}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stores"][0]["error"], "scope_error")
        preference = self.record(scope="global", kind="preference", title="简洁的修复说明", content="解释优先说明变更和验证。")
        saved = self.apply(scope="global", turn="global-pref", operations=[{"op": "ADD", "scope": "global", "record": preference}])
        self.assertEqual(saved["status"], "saved")
        recalled = store.recall("", global_root=self.global_root)
        self.assertEqual(recalled["stores"][0]["records"][0]["kind"], "preference")

    def test_global_project_markers_rejected(self) -> None:
        preference = self.record(scope="global", kind="preference", content="在 /Users/example/customer-project 中运行脚本。")
        result = self.apply(scope="global", operations=[{"op": "ADD", "scope": "global", "record": preference}])
        self.assertEqual(result["stores"][0]["error"], "scope_error")

    def test_partial_success_keeps_stores_independent(self) -> None:
        bad_parent = self.home / "bad-global"
        bad_parent.mkdir()
        external = self.home / "outside"
        external.mkdir()
        (bad_parent / "global").symlink_to(external, target_is_directory=True)
        project_record = self.record(content="项目库应该保存此项目规则。")
        result = self.apply(scope="both", turn="partial", global_root=bad_parent, operations=[
            {"op": "NOOP", "scope": "global", "reason": "本轮没有新的跨项目要求"},
            {"op": "ADD", "scope": "project", "record": project_record},
        ])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual([item["status"] for item in result["stores"]], ["failed", "saved"])
        self.assertEqual(store.get_store_status("global", global_root=bad_parent)["status"], "unavailable")

    def test_unavailable_project_content_is_not_promoted_to_global(self) -> None:
        uninitialized = self.home / "uninitialized project"
        uninitialized.mkdir()
        preference = self.record(scope="global", kind="preference", title="Explicit general preference",
                                 content="Use consistent formatting across all future projects.")
        business = self.record(content="This project's return window is 9 days.", conditions="9 days in this project.")
        result = store.apply_payload({"schema_version": 1, "scope": "both", "session_id": "s", "turn_id": "t",
                                      "idempotency_key": "isolated-failure", "operations": [
            {"op": "ADD", "scope": "global", "record": preference},
            {"op": "ADD", "scope": "project", "record": business},
        ]}, project_root=uninitialized, global_root=self.global_root)
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["stores"][0]["status"], "saved")
        self.assertEqual(result["stores"][1]["status"], "failed")
        global_records = store.list_records("global", global_root=self.global_root)["records"]
        self.assertEqual([row["title"] for row in global_records], ["Explicit general preference"])

    def test_model_inference_cannot_be_active_and_verification_requires_actual_result_fields(self) -> None:
        inferred = self.record(source={"type": "model_inference"})
        result = self.apply(scope="project", turn="inference", operations=[{"op": "ADD", "scope": "project", "record": inferred}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stores"][0]["error"], "provenance_error")

    def test_hypotheses_cannot_be_active_or_recalled_from_legacy_rows(self):
        rejected = self.apply(scope='project', turn='hypothesis', operations=[{
            'op':'ADD', 'record':self.record(claim_type='hypothesis')}])
        self.assertEqual(rejected['stores'][0]['error'], 'provenance_error')
        legacy_id = self.add_project_rule(turn='legacy-rule', title='Unconfirmed naming')
        _, db = store.project_paths(self.project_a)
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE memories SET claim_type='hypothesis' WHERE id=?", (legacy_id,))
            conn.commit()
        recalled = store.recall('Unconfirmed naming', project_root=self.project_a,
            global_root=self.global_root, include_task=False, force=True)
        self.assertNotIn(legacy_id, [r['id'] for r in recalled['stores'][1]['records']])
        self.assertTrue(store.show_record('project', legacy_id, project_root=self.project_a)['record'])
        checkpoints = []
        for turn in ('older', 'newer'):
            result = self.apply(scope='task', task='legacy-resume', turn=turn,
                operations=[{'op':'CHECKPOINT', 'record':self.record(kind='checkpoint', claim_type='observed',
                    title=turn, content='Synthetic checkpoint ' + turn)}])
            checkpoints.append(result['stores'][0]['operations'][0]['id'])
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE memories SET status='active' WHERE id=?", (checkpoints[0],))
            conn.execute("UPDATE memories SET claim_type='hypothesis' WHERE id=?", (checkpoints[1],))
            conn.commit()
        resumed = store.recall('continue', project_root=self.project_a, global_root=self.global_root,
                               resume=True, force=True)
        resumed_ids = [r['id'] for r in resumed['stores'][1]['records']]
        self.assertIn(checkpoints[0], resumed_ids)
        self.assertNotIn(checkpoints[1], resumed_ids)

    def test_desired_policy_and_observed_implementation_remain_distinct(self) -> None:
        desired = self.record(title="Desired policy", content="Must reject final-sale items.")
        observed = self.record(kind="project_fact", title="Observed implementation", content="Current code permits final-sale items.",
                               claim_type="observed", code_refs=["refunds.py#refund_eligible"],
                               source=self.source("Observed in source inspection.", "code_observation"))
        result = self.apply(scope="project", turn="desired-observed", operations=[
            {"op": "ADD", "scope": "project", "record": desired},
            {"op": "ADD", "scope": "project", "record": observed},
        ])
        self.assertEqual(result["status"], "saved")
        rows = store.list_records("project", project_root=self.project_a)["records"]
        self.assertEqual({row["title"]: row["kind"] for row in rows},
                         {"Desired policy": "business_rule", "Observed implementation": "project_fact"})

    def test_verified_result_is_version_pinned_and_goes_stale_after_workspace_change(self) -> None:
        (self.project_a / "refunds.py").write_text("def refund_eligible(order): return True\n", encoding="utf-8")
        verified = self.record(kind="lesson", title="Refund regression result", content="The test passed on this code.",
                               source=self.source("Unit test completed with exit code zero.", "tool_result"),
                               verification={"command": "python3 -m unittest", "finished_at": "2026-10-10T00:00:00Z",
                                             "code_version": "abc123", "exit_code": 0})
        payload = {"schema_version": 1, "scope": "project", "session_id": "verify-session", "turn_id": "verify-turn",
                   "idempotency_key": "verify-idem", "task_id": "refund-task", "commit_id": "abc123",
                   "operations": [{"op": "ADD", "scope": "project", "record": verified}]}
        result = store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result["status"], "saved")
        memory_id = result["stores"][0]["operations"][0]["id"]
        saved = store.show_record("project", memory_id, project_root=self.project_a)["record"]
        self.assertEqual(saved["verification"]["code_version"], "abc123")
        self.assertEqual(saved["verification"]["commit_id"], "abc123")
        self.assertEqual(saved["verification_status"], "current_workspace")
        (self.project_a / "refunds.py").write_text("def refund_eligible(order): return False\n", encoding="utf-8")
        stale = store.show_record("project", memory_id, project_root=self.project_a)["record"]
        self.assertEqual(stale["verification_status"], "stale_workspace_changed")
        fabricated = self.record(source={"type": "tool_result"}, verification={"command": "pytest", "finished_at": "today"})
        result = self.apply(scope="project", turn="fabricated", operations=[{"op": "ADD", "scope": "project", "record": fabricated}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["stores"][0]["error"], "provenance_error")

    def test_same_turn_source_retried_three_times_has_one_evidence(self) -> None:
        rule = self.record()
        for i in range(3):
            result = self.apply(scope="project", turn="same-source-turn", idem=f"trigger-{i}",
                                operations=[{"op": "ADD", "scope": "project", "record": rule}])
            self.assertIn(result["status"], {"saved", "duplicate_evidence"})
        record_id = store.list_records("project", project_root=self.project_a)["records"][0]["id"]
        details = store.show_record("project", record_id, project_root=self.project_a)
        self.assertEqual(len(details["evidence"]), 1)

    def test_independent_user_evidence_merges_without_fake_revisions(self) -> None:
        rule = self.record()
        for turn in ("user-1", "user-2", "user-3"):
            self.apply(scope="project", turn=turn, operations=[{"op": "ADD", "scope": "project", "record": rule}])
        record_id = store.list_records("project", project_root=self.project_a)["records"][0]["id"]
        details = store.show_record("project", record_id, project_root=self.project_a)
        self.assertEqual(len(details["evidence"]), 3)

    def test_both_scope_noop_has_separate_checked_receipts(self) -> None:
        result = self.apply(scope="both", turn="noop-turn", operations=[
            {"op": "NOOP", "scope": "both", "reason": "检查了相关要求，本轮没有增量。"}
        ])
        self.assertEqual(result["status"], "checked_noop")
        for scope, project in (("global", None), ("project", self.project_a)):
            receipt = store.receipt_for_turn(scope, session_id="session-test", turn_id="noop-turn",
                                             project_root=project, global_root=self.global_root)
            self.assertEqual(receipt["status"], "checked_noop")

    def test_unchecked_turn_has_missing_receipt(self) -> None:
        receipt = store.receipt_for_turn("project", session_id="session-test", turn_id="never-checked",
                                         project_root=self.project_a)
        self.assertEqual(receipt["status"], "missing")

    def test_store_transaction_rolls_back_all_operations_on_failure(self) -> None:
        result = self.apply(scope="project", turn="atomic-failure", operations=[
            {"op": "ADD", "scope": "project", "record": self.record()},
            {"op": "UNSUPPORTED", "scope": "project"},
        ])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(store.list_records("project", project_root=self.project_a)["records"], [])
        self.assertEqual(store.receipt_for_turn("project", session_id="session-test", turn_id="atomic-failure",
                                                project_root=self.project_a)["status"], "missing")

    def test_paused_capture_does_not_write_and_readonly_recall_remains_available(self) -> None:
        self.add_project_rule()
        store.set_capture("project", False, project_root=self.project_a)
        result = self.apply(scope="project", turn="paused", operations=[{"op": "ADD", "scope": "project", "record": self.record(title="Second") }])
        self.assertEqual(result["status"], "skipped_private")
        self.assertEqual(store.get_store_status("project", project_root=self.project_a)["capture_enabled"], False)
        recalled = store.recall("退款", project_root=self.project_a, force=True)
        self.assertTrue(any(block["records"] for block in recalled["stores"]))
        self.assertEqual(store.receipt_for_turn("project", session_id="session-test", turn_id="paused",
                                                project_root=self.project_a)["status"], "missing")

    def test_private_skip_persists_only_opaque_ids(self) -> None:
        result = store.record_private_skip("both", session_id="private-session", turn_id="private-turn",
                                           project_root=self.project_a, global_root=self.global_root)
        self.assertEqual(result["status"], "skipped_private")
        receipt = store.receipt_for_turn("project", session_id="private-session", turn_id="private-turn",
                                         project_root=self.project_a)
        self.assertEqual(receipt["status"], "skipped_private")
        conn = store._connect(store.project_paths(self.project_a)[1], readonly=True)
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        raw = conn.execute("SELECT result_json FROM receipts WHERE session_id=?", ("private-session",)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)
        self.assertEqual(raw, "[]")

    def test_secret_patterns_are_rejected_before_write(self) -> None:
        record = self.record(content="token = ghp_" + "A" * 40)
        with self.assertRaises(store.MemoryError) as caught:
            self.apply(scope="project", operations=[{"op": "ADD", "scope": "project", "record": record}])
        self.assertEqual(caught.exception.code, "sensitive_data_rejected")
        self.assertNotIn("ghp_", caught.exception.message)

    def test_revision_replaces_rule_and_invalidates_derived_summary(self) -> None:
        record_id = self.add_project_rule()
        summary = {"kind": "summary", "claim_type": "hypothesis", "status": "candidate", "title": "归纳候选",
                   "content": "来源规则的摘要。", "derived_from": [record_id], "expected_source_revisions": {record_id: 1},
                   "source": {"type": "model_inference"}}
        added = self.apply(scope="project", turn="summary", operations=[{"op": "ADD", "scope": "project", "record": summary}])
        summary_id = added["stores"][0]["operations"][0]["id"]
        summary_two = {"kind": "summary", "claim_type": "hypothesis", "status": "candidate", "title": "二级归纳候选",
                       "content": "归纳候选的二级摘要。", "derived_from": [summary_id], "expected_source_revisions": {summary_id: 1},
                       "source": {"type": "model_inference"}}
        added_two = self.apply(scope="project", turn="summary-two", operations=[{"op": "ADD", "scope": "project", "record": summary_two}])
        summary_two_id = added_two["stores"][0]["operations"][0]["id"]
        old = store.show_record("project", record_id, project_root=self.project_a)["record"]
        revised = self.record(content="修订后仅已送达且未拆封订单可退款。", conditions="已送达且未拆封。",
                              exceptions="礼品订单和最终销售商品除外。", id=record_id, revision=old["revision"] + 1)
        result = self.apply(scope="project", turn="revise", operations=[
            {"op": "REVISE", "scope": "project", "id": record_id, "expected_revision": old["revision"], "record": revised}
        ])
        self.assertEqual(result["status"], "saved")
        self.assertEqual(store.show_record("project", summary_id, project_root=self.project_a)["record"]["status"], "stale")
        self.assertEqual(store.show_record("project", summary_two_id, project_root=self.project_a)["record"]["status"], "stale")
        recalled = store.recall("退款", project_root=self.project_a, force=True)
        self.assertNotIn("仅已送达订单可退款", json.dumps(recalled, ensure_ascii=False))

    def test_consolidation_is_a_same_store_proposal_with_revisioned_sources(self) -> None:
        first = self.add_project_rule(turn="consolidate-one", title="退款条件 A")
        second = self.add_project_rule(turn="consolidate-two", title="退款条件 B", content="另一条业务条件。")
        proposal = store.consolidate_sources("project", [first, second], project_root=self.project_a)
        self.assertEqual(proposal["status"], "prepare")
        self.assertEqual({row["id"] for row in proposal["sources"]}, {first, second})
        self.assertTrue(all(isinstance(row["revision"], int) for row in proposal["sources"]))
        with self.assertRaises(store.MemoryError) as caught:
            store.consolidate_sources("project", [first], project_root=self.project_b)
        self.assertEqual(caught.exception.code, "scope_error")

    def test_task_checkpoint_is_project_local_and_recallable(self) -> None:
        checkpoint = {"kind": "checkpoint", "claim_type": "observed", "title": "当前断点",
                      "content": "已修好解析；还未运行回归。", "source": {"type": "tool_result"}}
        result = self.apply(scope="task", task="task-42", turn="checkpoint", operations=[
            {"op": "CHECKPOINT", "scope": "task", "record": checkpoint}
        ])
        self.assertEqual(result["status"], "saved")
        recalled = store.recall("", project_root=self.project_a, task_id="task-42", force=True)
        self.assertTrue(any(r["kind"] == "checkpoint" for s in recalled["stores"] for r in s["records"]))

    def test_two_sessions_keep_separate_task_bindings(self) -> None:
        for session, task in (("session-one", "task-one"), ("session-two", "task-two")):
            payload = {"schema_version": 1, "scope": "task", "session_id": session, "turn_id": f"turn-{task}",
                       "idempotency_key": f"idem-{task}", "task_id": task, "operations": [
                {"op": "CHECKPOINT", "scope": "task", "record": {"kind": "checkpoint", "claim_type": "observed",
                    "title": task, "content": f"progress {task}", "source": {"type": "tool_result"}}}
            ]}
            self.assertEqual(store.apply_payload(payload, project_root=self.project_a, global_root=self.global_root)["status"], "saved")
        one = store.recall("", project_root=self.project_a, session_id="session-one", force=True)
        two = store.recall("", project_root=self.project_a, session_id="session-two", force=True)
        one_records = [r for block in one["stores"] for r in block["records"]]
        two_records = [r for block in two["stores"] for r in block["records"]]
        self.assertTrue(any(r["task_id"] == "task-one" for r in one_records))
        self.assertFalse(any(r["task_id"] == "task-two" for r in one_records))
        self.assertTrue(any(r["task_id"] == "task-two" for r in two_records))
        self.assertFalse(any(r["task_id"] == "task-one" for r in two_records))

    def test_chinese_and_code_terms_recall_with_bounds(self) -> None:
        self.add_project_rule(title="退款服务 RefundPolicy ECONNRESET", content="退款条件含 ECONNRESET 排查。")
        recalled = store.recall("退款 RefundPolicy ECONNRESET", project_root=self.project_a, max_details=1, force=True)
        self.assertTrue(any(r["title"].find("RefundPolicy") >= 0 for s in recalled["stores"] for r in s["records"]))
        for n in range(3):
            item = self.record(title=f"额外约束 {n}", content=f"规则说明第 {n} 项。")
            self.apply(scope="project", turn=f"extra-{n}", operations=[{"op": "ADD", "scope": "project", "record": item}])
        bounded = store.recall("规则", project_root=self.project_a, max_details=1, max_chars=100, force=True)
        self.assertTrue(bounded["context_incomplete"])

    def test_session_cache_invalidates_on_memory_revision_and_module_change(self) -> None:
        first = store.recall("退款", project_root=self.project_a, session_id="cache-session", module="src/pay", force=True)
        second = store.recall("退款", project_root=self.project_a, session_id="cache-session", module="src/pay")
        self.assertEqual(first["stores"][1]["status"], "ok")
        self.assertEqual(second["stores"][1]["status"], "cached")
        self.add_project_rule(turn="cache-revision")
        third = store.recall("退款", project_root=self.project_a, session_id="cache-session", module="src/pay")
        self.assertEqual(third["stores"][1]["status"], "ok")
        fourth = store.recall("退款", project_root=self.project_a, session_id="cache-session", module="src/auth")
        self.assertEqual(fourth["stores"][1]["status"], "ok")
        returned = store.recall("退款", project_root=self.project_a, session_id="cache-session", module="src/pay")
        self.assertEqual(returned["stores"][1]["status"], "cached")

    def test_project_paths_and_symlink_escapes(self) -> None:
        with self.assertRaises(store.MemoryError):
            store.project_paths(Path.home())
        outside = self.home / "outside-store"
        outside.mkdir()
        project = self.home / "symlink-project"
        project.mkdir()
        (project / ".dev-memory").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(store.MemoryError):
            store.project_paths(project)

    def test_project_git_exclusion_and_tracked_path_refusal(self) -> None:
        project = self.home / "git project"
        project.mkdir()
        subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
        store.init_project(project)
        ignored = subprocess.run(["git", "-C", str(project), "check-ignore", "-q", "--", ".dev-memory/"], check=False)
        self.assertEqual(ignored.returncode, 0)
        (project / ".dev-memory" / "tracked.txt").write_text("data", encoding="utf-8")
        subprocess.run(["git", "-C", str(project), "add", "-f", ".dev-memory/tracked.txt"], check=True)
        with self.assertRaises(store.MemoryError):
            store.init_project(project)

    def test_backup_restore_does_not_resurrect_forgotten_memory(self) -> None:
        memory_id = self.add_project_rule()
        backup = store.backup_store("project", project_root=self.project_a)["backup"]
        preview = store.forget_preview("project", memory_id, project_root=self.project_a)
        store.forget_apply("project", memory_id, preview["confirmation_token"], project_root=self.project_a)
        restored = store.restore_store("project", Path(backup), project_root=self.project_a)
        self.assertEqual(restored["status"], "restored")
        with self.assertRaises(store.MemoryError):
            store.show_record("project", memory_id, project_root=self.project_a)

    def test_forget_preview_lists_same_store_derivatives_and_promoted_global_links(self) -> None:
        global_record = self.record(scope="global", kind="preference", title="Reusable preference",
                                    content="Use concise progress notes.", id="global-preference")
        self.apply(scope="global", turn="global-link", operations=[
            {"op": "ADD", "scope": "global", "record": global_record}
        ])
        project_record = self.record(title="Promoted candidate", promoted_global_ids=["global-preference"])
        added = self.apply(scope="project", turn="project-link", operations=[
            {"op": "ADD", "scope": "project", "record": project_record}
        ])
        source_id = added["stores"][0]["operations"][0]["id"]
        summary = {"kind": "summary", "claim_type": "hypothesis", "status": "candidate",
                   "title": "Derived summary", "content": "Project-derived summary.",
                   "derived_from": [source_id], "expected_source_revisions": {source_id: 1}, "source": {"type": "model_inference"}}
        summary_result = self.apply(scope="project", turn="project-summary", operations=[
            {"op": "ADD", "scope": "project", "record": summary}
        ])
        summary_id = summary_result["stores"][0]["operations"][0]["id"]
        preview = store.forget_preview("project", source_id, project_root=self.project_a)
        self.assertEqual({row["id"] for row in preview["records"]}, {source_id, summary_id})
        self.assertEqual(preview["promoted_global_ids"], ["global-preference"])
        store.forget_apply("project", source_id, preview["confirmation_token"], project_root=self.project_a)
        self.assertEqual(store.show_record("global", "global-preference", global_root=self.global_root)["record"]["id"],
                         "global-preference")

    def test_abrupt_process_exit_rolls_back_uncommitted_sqlite_transaction(self) -> None:
        _, db_path = store.project_paths(self.project_a)
        script = (
            "import os,sqlite3,sys; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE meta SET value='999' WHERE key='data_revision'\"); "
            "os._exit(17)"
        )
        crashed = subprocess.run([sys.executable, "-c", script, str(db_path)], check=False)
        self.assertEqual(crashed.returncode, 17)
        self.assertEqual(store.data_revision(db_path), 0)

    def test_markdown_export_is_on_demand_and_not_authoritative(self) -> None:
        memory_id = self.add_project_rule()
        status = store.get_store_status("project", project_root=self.project_a)
        self.assertEqual(status["view_status"], "not_exported")
        exported = store.export_views("project", project_root=self.project_a)
        view = Path(exported["views"]) / "business.md"
        self.assertTrue(view.exists())
        view.write_text("manual edit\n", encoding="utf-8")
        self.assertEqual(store.show_record("project", memory_id, project_root=self.project_a)["record"]["id"], memory_id)
        self.assertEqual(store.get_store_status("project", project_root=self.project_a)["view_status"], "current")

    def test_both_context_query_and_workspace_change_cache(self) -> None:
        project = self.home / "git-workspace"
        project.mkdir()
        subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
        store.init_project(project)
        store.recall("", project_root=project, session_id="workspace-session", module="src", force=True)
        unchanged = store.recall("", project_root=project, session_id="workspace-session", module="src")
        self.assertEqual(unchanged["stores"][1]["status"], "cached")
        (project / "new-file.txt").write_text("new workspace file", encoding="utf-8")
        changed = store.recall("", project_root=project, session_id="workspace-session", module="src")
        self.assertEqual(changed["stores"][1]["status"], "ok")


class IntegrationTests(MemoryTestCase):
    def test_hook_stop_does_not_require_noop_and_private_skip_is_preserved(self) -> None:
        script = SCRIPTS / "codex_hook.py"
        env = {**os.environ, "DEV_MEMORY_HOME": str(self.global_root)}
        event = {"hook_event_name": "Stop", "cwd": str(self.project_a), "session_id": "s1", "turn_id": "t1",
                 "stop_hook_active": False}
        missing = subprocess.run([sys.executable, str(script)], input=json.dumps(event), text=True, encoding="utf-8",
                                 capture_output=True, env=env, cwd=self.project_a, check=True)
        self.assertEqual(missing.stdout, '')
        event["stop_hook_active"] = True
        limited = subprocess.run([sys.executable, str(script)], input=json.dumps(event), text=True, encoding="utf-8",
                                 capture_output=True, env=env, cwd=self.project_a, check=True)
        self.assertEqual(limited.stdout, "")
        prompt = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.project_a), "session_id": "s1",
                  "turn_id": "t-private", "prompt": "本轮不记任何内容"}
        skipped = subprocess.run([sys.executable, str(script)], input=json.dumps(prompt), text=True, encoding="utf-8",
                                 capture_output=True, env=env, cwd=self.project_a, check=True)
        self.assertIn("marked private", json.loads(skipped.stdout)["hookSpecificOutput"]["additionalContext"])
        event.update({"turn_id": "t-private", "stop_hook_active": False})
        no_recovery = subprocess.run([sys.executable, str(script)], input=json.dumps(event), text=True, encoding="utf-8",
                                     capture_output=True, env=env, cwd=self.project_a, check=True)
        self.assertEqual(no_recovery.stdout, "")

    def test_release_installer_preserves_other_hooks_and_memory(self) -> None:
        target = self.home / "installed skill"
        codex_home = self.home / "codex"
        codex_home.mkdir()
        hooks = {"keep": "untouched", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo other"}]}]}}
        (codex_home / "hooks.json").write_text(json.dumps(hooks), encoding="utf-8")
        before = os.environ.copy()
        try:
            os.environ["CODEX_HOME"] = str(codex_home)
            result = dev_memory.install(target, with_hooks=True, upgrade=False)
            self.assertEqual(result["status"], "installed")
            self.assertEqual(result["hooks"]["status"], "configured_requires_review")
            upgraded = dev_memory.install(target, with_hooks=False, upgrade=True)
            self.assertEqual(upgraded["status"], "installed")
            data = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(data["keep"], "untouched")
            uninstalled = dev_memory.uninstall(target)
            self.assertTrue(uninstalled["memory_data_preserved"])
            after = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
            self.assertEqual(after["keep"], "untouched")
            self.assertIn("echo other", json.dumps(after))
            self.assertNotIn("dev_memory.py", json.dumps(after))
            self.assertFalse(target.exists())
        finally:
            os.environ.clear()
            os.environ.update(before)

    def test_benchmark_fixture_is_identical_and_synthetic(self) -> None:
        self.assertIn("prior confirmed refund policy", bench_compare.TASK)
        self.assertIn("14", json.dumps(bench_compare.CRITERIA))
        self.assertTrue(bench_compare.STARTER.startswith("def refund_eligible"))

    def test_cli_runs_without_third_party_dependencies(self) -> None:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(self.home), "PYTHONNOUSERSITE": "1"}
        if os.name == 'nt':
            env['SYSTEMROOT'] = os.environ['SYSTEMROOT']
            env['USERPROFILE'] = str(self.home)
        result = subprocess.run([sys.executable, str(SCRIPTS / "dev_memory.py"), "--help"], cwd=self.home,
                                env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dev-memory", result.stdout)

    def test_release_build_whitelist_excludes_runtime_data(self) -> None:
        import build_release
        target = self.home / "release.zip"
        result = build_release.build(target)
        self.assertEqual(result["status"], "built")
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            self.assertIn("dev-memory/skills/dev-memory/SKILL.md", names)
            self.assertNotIn("dev-memory/.dev-memory/", "\n".join(names))
            self.assertFalse(any(name.endswith((".sqlite", ".sqlite3", ".log")) for name in names))
        with self.assertRaises(ValueError):
            build_release.build(ROOT / "nested" / ".." / "must-not-build-inside.zip")


if __name__ == "__main__":
    unittest.main()

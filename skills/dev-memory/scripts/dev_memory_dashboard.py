"""Local, on-demand dashboard. SQLite remains the only source of memory truth."""
from __future__ import annotations

import html
import json
import re
import secrets
import sqlite3
import sys
import threading
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import dev_memory_store as store

STATUS_LABELS = {"active": "生效", "candidate": "候选（未生效）", "conflicted": "冲突待核对",
                 "stale": "待复核", "archived": "已归档", "superseded": "已替代", "all": "全部状态"}
PAGE_SIZE = 6
KIND_LABELS = {"preference": "开发偏好", "convention": "开发规范", "project_fact": "项目事实",
               "business_rule": "业务规则", "decision": "决策", "lesson": "经验教训",
               "procedure": "操作流程", "summary": "摘要"}
CLAIM_LABELS = {"desired": "期望行为", "observed": "观察事实", "preference": "偏好", "hypothesis": "待验证假设"}
STRENGTH_LABELS = {"hard": "必须遵守", "soft": "偏好", "informational": "参考"}
SOURCE_LABELS = {"user_statement": "用户要求", "user_confirmation": "用户确认",
                 "user_feedback": "用户反馈", "code_observation": "代码观察",
                 "tool_result": "工具结果", "external_reference": "外部资料", "model_inference": "模型推断"}


def _h(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _local_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _catalog_path(global_root: Path | None) -> Path:
    root = (global_root or store.default_global_root()).expanduser().resolve()
    directory = root / "dashboard"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise store.MemoryError("path_escape", "Dashboard directory is not a regular directory.")
    return directory / "projects.json"


def projects(global_root: Path | None = None) -> list[dict[str, str]]:
    path = _catalog_path(global_root)
    if not path.exists():
        return []
    value = store.read_json(path)
    rows = value.get("projects")
    if not isinstance(rows, list) or any(not isinstance(row, dict) or
        not isinstance(row.get("path"), str) or not isinstance(row.get("namespace_id"), str)
        for row in rows):
        raise store.MemoryError("catalog_invalid", "Dashboard project catalog is invalid.")
    return rows


def register_project(project_root: Path, global_root: Path | None = None) -> dict[str, str]:
    root = store._reject_unsafe_project_root(project_root)
    _, _, config = store._config_for("project", root, global_root)
    row = {"path": str(root), "namespace_id": config["namespace_id"]}
    path = _catalog_path(global_root)
    rows = [item for item in projects(global_root) if item["path"] != row["path"] and
            item["namespace_id"] != row["namespace_id"]]
    rows.append(row)
    store.write_json_atomic(path, {"schema_version": store.SCHEMA_VERSION,
                                   "projects": sorted(rows, key=lambda item: item["path"].casefold())})
    return row


def remove_project(namespace_id: str, global_root: Path | None = None) -> bool:
    path = _catalog_path(global_root)
    rows = projects(global_root)
    remaining = [row for row in rows if row["namespace_id"] != namespace_id]
    if len(remaining) == len(rows):
        return False
    store.write_json_atomic(path, {"schema_version": store.SCHEMA_VERSION, "projects": remaining})
    return True


class Dashboard:
    def __init__(self, global_root: Path | None = None):
        self.global_root = global_root
        self.csrf = secrets.token_urlsafe(32)
        self.script_nonce = secrets.token_urlsafe(18)

    def _registered_projects(self) -> tuple[list[dict[str, str]], Exception | None]:
        try:
            return projects(self.global_root), None
        except (store.MemoryError, OSError, sqlite3.Error) as exc:
            return [], exc

    def _target(self, key: str) -> tuple[str, Path | None]:
        if key == "global":
            return "global", None
        row = next((item for item in projects(self.global_root) if item["namespace_id"] == key), None)
        if row is None:
            raise store.MemoryError("project_not_registered", "Project is not in the dashboard catalog.")
        root = Path(row["path"])
        _, _, config = store._config_for("project", root, self.global_root)
        if config["namespace_id"] != key:
            raise store.MemoryError("namespace_mismatch", "Registered project identity has changed.")
        return "project", root

    def _status(self, key: str) -> dict:
        try:
            kind, root = self._target(key)
            return store.get_store_status(kind, project_root=root, global_root=self.global_root, check_integrity=False)
        except (store.MemoryError, OSError, sqlite3.Error) as exc:
            return {"status": "unavailable", "reason": getattr(exc, "code", "storage_unavailable")}

    def _scope_name(self, key: str) -> str:
        if key == "global":
            return "全局记忆"
        row = next((item for item in projects(self.global_root) if item["namespace_id"] == key), None)
        if row:
            project = Path(row["path"])
            return f"{project.name} · {project.parent}"
        return "未知项目"

    def _shell(self, title: str, body: str) -> str:
        _, catalog_error = self._registered_projects()
        if catalog_error:
            body = ('<section class=panel><h2>项目列表暂不可用</h2>'
                    '<p>仍可查看全局记忆。请检查本机看板目录的读取权限，修复后重启看板。</p></section>' + body)
        return ("<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>{_h(title)} · Dev Memory</title><style>"
                "*{box-sizing:border-box}body{font:14px/1.5 'Microsoft YaHei','PingFang SC',system-ui,sans-serif;color:#16233f;background:#f5f7fb;margin:0;-webkit-font-smoothing:antialiased}button,input,select{font:inherit}"
                "header{height:60px;background:#fff;color:#253650;padding:0 max(calc((100vw - 1548px)/2),24px);border-bottom:1px solid #e8edf5;display:flex;align-items:center;justify-content:space-between}header b{color:#2563eb}.brand{display:flex;align-items:center;gap:8px;font-size:16px}.brand-mark{display:inline-grid;place-items:center;width:34px;height:34px;margin-right:4px;border-radius:10px;background:linear-gradient(135deg,#1558e8,#5787f4);color:white;box-shadow:0 6px 13px #336be934}.top-status{font-size:12px;color:#64718a}.top-status span{background:#eff8f3;color:#12845a;padding:6px 11px;border-radius:99px;border:1px solid #d8eee4;font-weight:650;margin-left:12px}"
                "main{max-width:1548px;margin:26px auto 35px;padding:0 24px;display:block}.pagehead{display:flex;align-items:center;justify-content:space-between;margin:0 2px 17px}.pagehead p{margin:0;color:#718097;font-size:13px}"
                ".panel{background:white;border:1px solid #e5eaf3;border-radius:14px;padding:19px 22px 17px;margin-bottom:17px;box-shadow:0 4px 19px #233c6708}"
                "a{color:#2355a5;text-decoration:none}a:hover{text-decoration:underline}"
                "h1{font-size:26px;letter-spacing:-.5px;margin:0 0 3px}h2{font-size:17px;letter-spacing:-.3px;margin:0 0 1px}h3{margin-bottom:6px}"
                ".muted{color:#5c6878}.warn{color:#a14c00}.bad{color:#a52222}.pill{background:#eaf0fb;padding:2px 8px;border-radius:12px}"
                ".scope-row{display:flex;justify-content:space-between;gap:16px;border-top:1px solid #e9edf2;padding:10px 0}"
                "table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e6e9ee;padding:8px}"
                "input,select,textarea,button{font:inherit;padding:9px 11px;margin:4px 5px 4px 0;max-width:100%;box-sizing:border-box;border:1px solid #cbd3df;border-radius:7px}"
                "form.filters{display:flex;flex-wrap:wrap;align-items:center;gap:10px}form.filters>*{margin:0}"
                "form.filters input[name=q]{flex:1;min-width:220px}"
                "textarea{width:100%;min-height:90px}button{background:#2456a6;color:white;border:0;border-radius:7px;cursor:pointer}"
                "button.danger{background:#ad2d2d}form.inline{display:inline}.record{white-space:pre-wrap;overflow-wrap:anywhere}"
                ".link-button{background:transparent;color:#2563eb;padding:0;height:auto;border:0}details{margin:8px 0}code{overflow-wrap:anywhere}table{display:table}dialog{width:min(680px,calc(100% - 28px));max-height:85vh;border:1px solid #dce1e8;border-radius:12px;padding:22px;box-shadow:0 20px 60px #14223b33}dialog::backdrop{background:#14223b66}dialog label{display:block;margin:8px 0;color:#56657a}dialog textarea{min-height:70px}"
                ".panel-head{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:13px}.panel-title{display:flex;align-items:center;gap:11px}.panel-title p{margin:0;color:#8a95a8;font-size:12px}.sectionicon{height:36px;width:36px;display:grid;place-items:center;border-radius:10px;background:#eff5ff;color:#2465ea;font-size:17px;font-weight:800}.sectionicon.v{color:#6b4ed5;background:#f3efff}.panel-meta{color:#687891;background:#f6f8fc;padding:6px 9px;border-radius:6px;font-size:12px}"
                ".stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin:12px 0 13px}.stats>div{min-height:68px;border:1px solid #e8edf5;border-radius:10px;background:linear-gradient(180deg,#fff,#fafcff);padding:10px 15px;display:flex;align-items:center;justify-content:space-between}.stats small{display:block;color:#74829a;font-size:12px;font-weight:600}.stats b{font-size:24px;letter-spacing:-.7px}.glyph{width:34px;height:34px;display:grid;place-items:center;background:#ebf3ff;border-radius:10px;color:#2570f6;font-size:17px;font-weight:750}.stats>div:nth-child(2) .glyph{color:#0fa477;background:#e5f8f1}.stats>div:nth-child(3) .glyph{color:#dd8b1a;background:#fff4e2}.stats>div:nth-child(4) .glyph{color:#704ed1;background:#f2ecff}"
                ".track{height:8px;background:#eaf0fa;border-radius:99px;overflow:hidden;margin:8px 0}.track span{display:block;height:100%;background:linear-gradient(90deg,#2f7bf3,#66a4fa)}"
                ".filters{display:flex;align-items:end;gap:10px;padding:11px 12px;background:#f8faff;border:1px solid #e8edf6;border-radius:10px;margin:12px 0}.filters label{display:flex;flex-direction:column;gap:5px;min-width:150px;color:#718097;font-size:12px}.filters label:first-child{width:22%}.filters .query{flex:1;min-width:0}.filters input,.filters select{width:100%}input,select{height:35px;border:1px solid #dbe3ef;border-radius:7px;padding:0 11px;background:#fff;color:#384762;font-size:12px}"
                ".tabletop,.tablefoot{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:10px 0;color:#738097}.tablewrap{border:1px solid #e8edf5;border-radius:9px;overflow:auto}table{width:100%;min-width:850px;border-collapse:collapse;table-layout:fixed}th{background:#f8fafd;color:#697991;font-size:12px;text-align:left;height:36px}td{font-size:12px;padding:9px 10px;border-bottom:1px solid #eef2f6;height:39px}.memory-table td,.vector-detail td{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.subject{font-weight:650;color:#223b68}.button{display:inline-block;padding:8px 12px;border:1px solid #dbe4ef;border-radius:7px;background:white}.tablefoot{font-size:12px}.vector-layout{display:grid;grid-template-columns:minmax(280px, .85fr) minmax(0,2.15fr);gap:16px}.vector-progress,.vector-detail{border:1px solid #e8edf5;border-radius:10px;padding:15px}.vector-progress h3,.vector-detail h3{font-size:14px;margin:0 0 10px}.progress-number{font-size:28px;font-weight:800;color:#2563eb}.progress-meta{display:flex;justify-content:space-between;gap:10px;color:#8090a8;font-size:12px;margin:8px 0}.vscope{display:inline-block;margin-right:10px;padding:7px 11px;border:1px solid #dce8fb;border-radius:99px;background:#f5f9ff;color:#6480a9;font-size:12px}.panel-head>div:last-child{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap}.inline .primary,.filters button{height:35px;padding:0 15px}dialog label{font-size:13px}dialog input,dialog textarea{width:100%;padding:9px;border:1px solid #dbe3ef;border-radius:7px}dialog input{height:36px}dialog button{height:36px;padding:0 14px;margin-top:8px}"
                "@media(max-width:750px){main{display:block;padding:0 14px;margin:16px auto}.panel{padding:16px}.filters{display:grid}.filters label,.filters label:first-child,.filters .query{width:100%}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.panel-head{align-items:flex-start;flex-direction:column}.vector-layout{grid-template-columns:1fr}.top-status{display:none}.tabletop{align-items:flex-start;flex-wrap:wrap}}"
                "</style><header><div class=brand><span class=brand-mark>M</span><strong><b>Dev</b> Memory</strong><span class=muted>本地记忆看板</span></div><div class=top-status>● 仅本机访问 · 按需启动 <span>127.0.0.1</span></div></header><main>"
                f'<div class=pagehead><div><h1>{_h(title)}</h1><p>同一页面管理全局与项目记忆，手动编辑后按需同步本地向量索引。</p></div><span class=panel-meta>仅本机数据</span></div>{body}</main><script nonce="{_h(self.script_nonce)}">document.addEventListener("click",e=>{{const b=e.target.closest("[data-dialog]");if(b)document.getElementById(b.dataset.dialog).showModal();const c=e.target.closest("[data-close]");if(c)c.closest("dialog").close()}})</script></html>')

    def _form_token(self) -> str:
        return f'<input type=hidden name=csrf value="{_h(self.csrf)}">'

    def _stats(self, key: str, month: str, *, state: dict | None = None,
               memory_ids: list[str] | None = None) -> tuple[str, dict]:
        status = state if state is not None else self._status(key)
        if status.get("status") != "available" or not status.get("recall_enabled"):
            return "不可读取", {}
        kind, root = self._target(key)
        _, db, _ = store._config_for(kind, root, self.global_root)
        conn = store._connect(db, readonly=True)
        try:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recall_counts'").fetchone()
        finally:
            conn.close()
        if not exists:
            return "尚无可用统计；历史未知", {}
        result = store.recall_stats(kind, month, project_root=root, global_root=self.global_root, memory_ids=memory_ids)
        return str(result["total_recalls"]), {
            item["id"]: item["recall_count"] for item in result["memories"]}

    def _list(self, key: str, query: str, status_filter: str, page: int, *,
              state: dict | None = None) -> tuple[list[dict], bool, int]:
        kind, root = self._target(key)
        state = state if state is not None else self._status(key)
        if state.get("status") != "available" or not state.get("recall_enabled"):
            return [], False, 0
        _, db, _ = store._config_for(kind, root, self.global_root)
        where = ["scope=?"]
        params: list[object] = [kind]
        if status_filter in store.STATUSES:
            where.append("status=?"); params.append(status_filter)
        if query:
            where.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params.extend((pattern, pattern))
        conn = store._connect(db, readonly=True)
        conn.row_factory = sqlite3.Row
        try:
            predicate = " AND ".join(where)
            count = conn.execute(f"SELECT COUNT(*) FROM memories WHERE {predicate}", params).fetchone()[0]
            rows = conn.execute(f"SELECT id,title,content,kind,claim_type,status,strength,updated_at,revision "
                                f"FROM memories WHERE {predicate} ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?",
                                (*params, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()
            return [dict(row) for row in rows], count > page * PAGE_SIZE, count
        finally:
            conn.close()

    def _vector_metadata(self, key: str, rows: list[dict]) -> dict[str, dict]:
        if not rows:
            return {}
        kind, root = self._target(key)
        _, db, _ = store._config_for(kind, root, self.global_root)
        conn = store._connect(db, readonly=True)
        conn.row_factory = sqlite3.Row
        try:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='vector_state'").fetchone()
            if not exists:
                return {}
            ids = [row['id'] for row in rows]
            placeholders = ','.join('?' for _ in ids)
            states = {row['memory_id']: dict(row) for row in conn.execute(
                f"SELECT v.memory_id,v.revision AS indexed_revision,v.state,v.updated_at,v.error,v.model_key,m.revision,m.title,m.status,m.claim_type "
                f"FROM vector_state v JOIN memories m ON m.id=v.memory_id WHERE m.scope=? AND v.memory_id IN ({placeholders})",
                [kind, *ids])}
            import dev_memory_vectors as vectors
            settings = vectors._settings(self.global_root)
            expected = vectors._model_key(settings) if settings else None
            for item in states.values():
                eligible = item['status'] in {'active', 'conflicted'} and item['claim_type'] != 'hypothesis'
                item['current'] = bool(eligible and expected and item['state'] == 'ready' and
                                       item['indexed_revision'] == item['revision'] and item['model_key'] == expected)
                if item['state'] == 'ready' and not item['current']:
                    item['state'] = 'pending'
                if not eligible:
                    item['state'] = 'not_eligible'
            return states
        finally:
            conn.close()

    def index(self, params: dict[str, str]) -> str:
        key = params.get("scope", "global")
        query = params.get("q", "")[:120].strip()
        status_filter = params.get("status", "all")
        if status_filter != "all" and status_filter not in store.STATUSES:
            status_filter = "all"
        page_text = params.get("page", "1")
        page = int(page_text) if re.fullmatch(r'[1-9][0-9]{0,8}', page_text) else 1
        month = params.get("month", datetime.now(timezone.utc).strftime("%Y-%m"))
        if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", month):
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        projects, catalog_error = self._registered_projects()
        choices = [("global", "全局记忆（默认）", "")]
        choices.extend((item["namespace_id"], Path(item["path"]).name, item["path"]) for item in projects)
        if key not in {item[0] for item in choices}:
            raise store.MemoryError('project_not_registered', 'The selected memory scope is not registered.')
        state = self._status(key)
        rows, has_more, total = self._list(key, query, status_filter, page, state=state)
        counts = {"all": 0, "active": 0, "candidate": 0}
        recall_label = "不可读取"
        recall_counts = {}
        vector_state = {"status": "unavailable", "ready": 0, "pending": 0}
        vector_reason = ""
        vector_meta = {}
        if state.get("status") == "available" and state.get("recall_enabled"):
            kind, root = self._target(key)
            counts.update(state.get('record_counts', {}))
            counts['all'] = sum(state.get('record_counts', {}).values())
            recall_label, recall_counts = self._stats(key, month, state=state, memory_ids=[row['id'] for row in rows])
            import dev_memory_vectors as vectors
            vector_state = vectors.status(kind, project_root=root, global_root=self.global_root)
            vector_reason = vector_state.get("reason", "")
            vector_meta = self._vector_metadata(key, rows)
        labels = {"ready": "已完成", "pending": "待补齐", "running": "运行中", "failed": "失败", "unavailable": "不可用", "disabled": "已禁用"}
        scope_options = "".join(
            f'<option value="{_h(sid)}" {"selected" if sid == key else ""}>{_h(name + (" · " + path if path else ""))}</option>'
            for sid, name, path in choices)
        body = f'''<section class="panel"><div class="panel-head"><div class="panel-title"><span class="sectionicon">M</span><div><h2>记忆数据</h2><p>默认查看全局记忆；切换项目后，下方记忆和向量数据同步切换。</p></div></div><span class="panel-meta">SQLite · 本地</span></div>
        <div class="stats"><div><div><small>记忆总数</small><b>{counts['all']}</b></div><span class="glyph">☷</span></div><div><div><small>生效记忆</small><b>{counts['active']}</b></div><span class="glyph">✓</span></div><div><div><small>候选记忆</small><b>{counts['candidate']}</b></div><span class="glyph">↻</span></div><div><div><small>{_h(month)} 详情返回</small><b>{_h(recall_label)}</b></div><span class="glyph">△</span></div></div>
        <form class="filters" method="get"><label>记忆范围<select name="scope">{scope_options}</select></label><label class="query">关键词搜索<input name="q" value="{_h(query)}" placeholder="搜索标题或正文"></label><label>状态<select name="status">'''
        body += ''.join(f'<option value="{_h(value)}" {"selected" if value == status_filter else ""}>{_h(STATUS_LABELS[value])}</option>'
                        for value in ("all", "active", "candidate", "conflicted", "stale", "archived", "superseded"))
        body += f'''</select></label><input type="hidden" name="month" value="{_h(month)}"><button class="primary">查询</button><a class="button" href="/?scope={_h(key)}">重置</a></form>'''
        if params.get("notice") == "backup_created":
            body += '<p class="pill">当前记忆库备份已创建。</p>'
        if catalog_error:
            body += '<p class="warn">项目列表暂不可用；仍可查看全局记忆，请检查项目目录权限。</p>'
        body += f'<div class="tabletop"><b>记忆列表</b><span>共 {total} 条 · 当前显示 {len(rows)} 条</span><form method="post" action="/action">{self._form_token()}<input type="hidden" name="action" value="backup"><input type="hidden" name="scope" value="{_h(key)}"><button class="outline">备份当前库</button></form></div>'
        body += '<div class="tablewrap"><table class="memory-table"><colgroup><col style="width:20%"><col style="width:10%"><col style="width:10%"><col style="width:32%"><col style="width:13%"><col style="width:8%"><col style="width:7%"></colgroup><thead><tr><th>记忆标题</th><th>类型</th><th>状态</th><th>内容摘要</th><th>更新时间</th><th>本月返回</th><th>操作</th></tr></thead><tbody>'
        dialogs = []
        for row in rows:
            link = '/record?' + urlencode({"scope": key, "id": row["id"]})
            summary = re.sub(r"\s+", " ", row.get("content", ""))[:110]
            editable = (state.get('capture_enabled') and state.get('writable') and row["status"] == "active"
                        and row["claim_type"] in {"desired", "preference"} and row["kind"] != "summary")
            actions = f'<button type="button" class="link-button" data-dialog="edit-{_h(row["id"])}">编辑</button> ' if editable else ""
            actions += f'<a href="{_h(link)}">查看</a>'
            if editable:
                dialogs.append(f'<dialog id="edit-{_h(row["id"])}"><h2>编辑记忆</h2><form method="post" action="/action">{self._form_token()}<input type="hidden" name="action" value="revise"><input type="hidden" name="scope" value="{_h(key)}"><input type="hidden" name="id" value="{_h(row["id"])}"><input type="hidden" name="revision" value="{_h(row["revision"])}"><label>标题<input name="title" value="{_h(row["title"])}" required></label><label>正文<textarea name="content" required>{_h(row["content"])}</textarea></label><label>修订依据<input name="reason" required maxlength="500"></label><button class="primary">保存修改</button><button type="button" class="outline" data-close>取消</button></form></dialog>')
            body += (f'<tr><td class="subject"><a href="{_h(link)}">{_h(row["title"])}</a></td>'
                     f'<td>{_h(KIND_LABELS.get(row["kind"], row["kind"]))}</td>'
                     f'<td>{_h(STATUS_LABELS.get(row["status"], row["status"]))}</td><td title="{_h(summary)}">{_h(summary)}</td>'
                     f'<td>{_h(_local_time(row["updated_at"]))}</td><td>{_h(recall_counts.get(row["id"], 0))}</td><td>{actions}</td></tr>')
        if not rows:
            body += '<tr><td colspan="7">没有符合条件的记忆。</td></tr>'
        body += '</tbody></table></div><div class="tablefoot">'
        body += ''.join(dialogs)
        body += f'<span>当前库：{_h(self._scope_name(key))}</span><span>'
        if page > 1:
            body += f'<a href="/?{urlencode({"scope":key,"q":query,"status":status_filter,"month":month,"page":page-1})}">上一页</a>　'
        body += f'第 {page} 页'
        if has_more:
            body += f'　<a href="/?{urlencode({"scope":key,"q":query,"status":status_filter,"month":month,"page":page+1})}">下一页</a>'
        body += '</span></div></section>'
        ready = vector_state.get("ready", 0)
        pending = vector_state.get("pending", 0)
        eligible = ready + pending
        progress = round(ready * 100 / eligible) if eligible else 0
        vector_status = labels.get(vector_state.get("status"), vector_state.get("status", "未知"))
        can_sync = state.get("capture_enabled") and state.get('writable') and vector_state.get("status") == "pending"
        body += f'''<section class="panel"><div class="panel-head"><div class="panel-title"><span class="sectionicon v">V</span><div><h2>向量索引</h2><p>与上方记忆范围、关键词和状态筛选联动；只读取当前库，不会自动启动模型。</p></div></div><div><span class="vscope">当前范围：{_h(self._scope_name(key))}</span>'''
        if can_sync:
            body += f'<form method="post" action="/action" class="inline">{self._form_token()}<input type="hidden" name="action" value="vectors_sync"><input type="hidden" name="scope" value="{_h(key)}"><button class="primary">同步当前范围</button></form>'
        body += '</div></div>'
        dimensions = vector_state.get("dimensions", 384)
        body += f'<div class="stats"><div><div><small>可索引记忆</small><b>{eligible}</b></div><span class="glyph">⌁</span></div><div><div><small>已就绪</small><b>{ready}</b></div><span class="glyph">✓</span></div><div><div><small>待同步</small><b>{pending}</b></div><span class="glyph">↻</span></div><div><div><small>向量维度</small><b>{dimensions}</b></div><span class="glyph">∴</span></div></div>'
        body += f'<p class="muted">同步状态：{_h(vector_status)}；统计覆盖当前记忆库，明细跟随上方筛选与分页。</p>'
        body += f'<div class="vector-layout"><div class="vector-progress"><h3>索引进度 <span class="muted" style="float:right">SQLite / sqlite-vec</span></h3><div class="progress-number">{progress}%</div><div class="progress-meta"><span>同步进度</span><span>已同步 {ready} / {eligible} 条可索引记忆</span></div><div class="track" aria-label="向量同步完成 {progress}%"><span style="width:{progress}%"></span></div><hr><div class="progress-meta"><span>本地索引</span><b>SQLite + sqlite-vec</b></div><div class="progress-meta"><span>Embedding</span><b>{_h(vector_state.get("model") or "未配置")} · {dimensions} 维</b></div><p class="muted">候选和失效记忆不参与普通向量召回。</p>'
        if vector_state.get("status") == "running":
            body += '任务运行中；刷新页面查看状态。'
        elif vector_state.get("status") == "pending" and pending > 0:
            body += f'剩余 {pending} 条，可再次点击“同步当前范围”继续。'
        elif vector_state.get("status") == "failed":
            body += f'<p class="warn">同步失败；{vector_state.get("retry_after_seconds", 0)} 秒后可重试。</p>'
        elif vector_state.get("status") == "unavailable":
            body += '<p class="muted">向量模型不可用；SQLite 中的原始记忆不受影响。</p>'
        if vector_reason:
            body += f'<p class="muted">原因：{_h(vector_reason)}</p>'
        body += '</div><div class="vector-detail"><h3>向量明细 <span class="muted" style="float:right">按当前记忆列表筛选</span></h3><div class="tablewrap"><table><thead><tr><th>来源记忆</th><th>原文版本</th><th>索引状态</th><th>更新时间</th><th>操作</th></tr></thead><tbody>'
        for row in rows:
            meta = vector_meta.get(row["id"], {})
            indexable = row['status'] in {'active', 'conflicted'} and row['claim_type'] != 'hypothesis'
            state_label = ("不参与索引" if not indexable else "已就绪" if meta.get("current")
                           else labels.get(meta.get("state"), "待生成" if not meta else "待补齐"))
            updated = datetime.fromtimestamp(meta["updated_at"], timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M") if meta.get("updated_at") else "—"
            vector_link = '/record?' + urlencode({"scope": key, "id": row["id"], "vector": "1"}) + '#vector'
            vector_action = f'<a href="{_h(vector_link)}">查看向量</a>' if meta.get("model_key") else ("待生成" if indexable else "—")
            version = f'v{meta["indexed_revision"]} / 当前 v{row["revision"]}' if meta else f'当前 v{row["revision"]}'
            body += f'<tr><td>{_h(row["title"])}</td><td>{_h(version)}</td><td>{_h(state_label)}</td><td>{_h(updated)}</td><td>{vector_action}</td></tr>'
        if not rows:
            body += '<tr><td colspan="5">当前查询没有对应记忆。</td></tr>'
        body += '</tbody></table></div></div></div><p class="pill">切换上方范围，下方状态与列表联动；编辑保存后旧索引失效，再按需同步新版本。</p></section>'
        return self._shell("记忆总览", body)

    def detail(self, key: str, memory_id: str, *, include_vector: bool = False) -> str:
        kind, root = self._target(key)
        data = store.show_record(kind, memory_id, project_root=root, global_root=self.global_root)
        if data.get("status") == "disabled":
            return self._shell("已禁用", '<section class=panel>该范围的记忆读取已禁用。</section>')
        record = data["record"]
        import dev_memory_vectors as vectors
        vector_state = vectors.status(kind, project_root=root, global_root=self.global_root, memory_id=memory_id)
        body = f'<section class=panel><p><a href="/?scope={_h(key)}">← {_h(self._scope_name(key))}</a></p>'
        body += f'<p class=muted>向量：{_h(vector_state.get("record", {}).get("state", vector_state["status"]))}</p>'
        stored_vector = (vectors.inspect_record(kind, memory_id, project_root=root, global_root=self.global_root)
                         if include_vector else {})
        body += '<details id=vector open><summary>查看实际存储的向量数据</summary>' if include_vector else '<details id=vector><summary>查看实际存储的向量数据</summary><p>完整向量只在你主动选择查看时读取。</p><a href="' + _h('/record?' + urlencode({"scope": key, "id": memory_id, "vector": "1"}) + '#vector') + '">加载实际向量</a>'
        if not include_vector:
            body += '</details>'
        else:
            body += (f'<p>当前原文版本：{_h(record["revision"])}；索引原文版本：{_h(stored_vector.get("indexed_revision", "尚未建立"))}；'
                     f'维度：{_h(stored_vector.get("dimensions", 0))}；'
                     f'索引与当前生效规则一致：{"是" if stored_vector.get("is_current") else "否"}。</p>')
            if stored_vector.get('model_key'):
                body += f'<p>模型：{_h(stored_vector.get("model_name") or "历史模型，以存储指纹为准")}</p>'
                body += f'<p class=record>存储模型指纹：{_h(stored_vector["model_key"])}</p>'
            if stored_vector.get('updated_at'):
                try:
                    updated = datetime.fromtimestamp(stored_vector['updated_at'], timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, OverflowError, OSError, TypeError):
                    updated = '未知'
                body += f'<p>索引更新时间（本机）：{_h(updated)}</p>'
            if stored_vector.get('embedding') is not None:
                if not stored_vector.get('is_current'):
                    body += '<p class=warn>下面是旧版本或非生效记录的存储向量，不代表当前可召回内容。</p>'
                body += f'<pre class=record style="max-height:24rem;overflow:auto">{_h(json.dumps(stored_vector["embedding"]))}</pre>'
            else:
                body += '<p>当前没有可读取的向量数值；中文原文仍可查看。</p>'
            if stored_vector.get('error') or stored_vector.get('reason'):
                body += f'<p class=muted>原因：{_h(stored_vector.get("error") or stored_vector.get("reason"))}</p>'
            body += '</details>'
        body += (f'<p><span class=pill>{_h(STATUS_LABELS.get(record["status"], record["status"]))}</span>　'
                 f'{_h(KIND_LABELS.get(record["kind"], record["kind"]))} / {_h(CLAIM_LABELS.get(record["claim_type"], record["claim_type"]))}'
                 f'　{_h(STRENGTH_LABELS.get(record["strength"], record["strength"]))}　修订 {_h(record["revision"])}</p>')
        for field, label in (("content", "正文"), ("conditions", "适用条件"), ("exceptions", "例外"),
                             ("do", "应做"), ("dont", "禁止"), ("rationale", "理由"),
                             ("verification_steps", "验证方式")):
            if record.get(field):
                body += f'<h3>{label}</h3><div class=record>{_h(record[field])}</div>'
        body += f'<p class=muted>ID: {_h(memory_id)} · 本机时间：{_h(_local_time(record["updated_at"]))} · 验证状态：{_h(record.get("verification_status") or "未提供")}</p>'
        for field, label in (("tags", "标签"), ("source_refs", "来源引用"), ("code_refs", "代码引用")):
            if record.get(field):
                body += f'<details><summary>{label}</summary><pre class=record>{_h(json.dumps(record[field], ensure_ascii=False, indent=2))}</pre></details>'
        body += '</section><section class=panel><h2>依据与修订</h2>'
        for evidence in data["evidence"]:
            body += (f'<p><strong>{_h(SOURCE_LABELS.get(evidence["source_type"], evidence["source_type"]))}</strong>'
                     f' · {_h(_local_time(evidence["created_at"]))}<br>{_h(evidence["excerpt"])}</p>')
        body += f'<details><summary>历史版本（{len(data["revisions"])}）</summary>'
        for rev in data["revisions"]:
            body += f'<h3>修订 {_h(rev["revision"])} · {_h(rev["changed_at"])}</h3><pre class=record>{_h(rev["snapshot"])}</pre>'
        body += '</details></section>'
        if record["status"] in {"active", "candidate", "conflicted", "stale"}:
            body += f'<section class=panel id=edit><h2>管理这条记忆</h2><p class=muted>操作使用当前修订号；归档保留审计历史，遗忘将删除受影响记录。</p>'
            if (record["status"] == "active" and record["claim_type"] in {"desired", "preference"}
                    and record["kind"] != "summary"):
                body += (f'<details><summary>修订内容</summary><form method=post action=/action>{self._form_token()}'
                         f'<input type=hidden name=action value=revise><input type=hidden name=scope value="{_h(key)}">'
                         f'<input type=hidden name=id value="{_h(memory_id)}"><input type=hidden name=revision value="{_h(record["revision"])}">')
                for field, label in (("title", "标题"), ("content", "正文"), ("conditions", "适用条件"),
                                     ("exceptions", "例外"), ("do", "应做"), ("dont", "禁止"),
                                     ("rationale", "理由"), ("verification_steps", "验证方式")):
                    body += f'<label>{label}<textarea name={field}>{_h(record.get(field, ""))}</textarea></label>'
                body += '<label>本次修订的用户依据<input name=reason required maxlength=500></label><button>检查修订号并保存</button></form></details>'
            if key == "global" and record["status"] == "candidate" and record["kind"] == "preference":
                body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=confirm>'
                         f'<input type=hidden name=scope value=global><input type=hidden name=id value="{_h(memory_id)}">'
                         f'<input type=hidden name=revision value="{_h(record["revision"])}">'
                         '<label><input type=checkbox name=confirm value=yes required>我确认这条规则适用于以后所有项目</label>'
                         '<button>确认全局适用</button></form>')
            body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=archive>'
                     f'<input type=hidden name=scope value="{_h(key)}"><input type=hidden name=id value="{_h(memory_id)}">'
                     f'<input type=hidden name=revision value="{_h(record["revision"])}">'
                     '<label><input type=checkbox name=confirm value=yes required>归档后不再参与普通召回</label>'
                     '<button>归档</button></form>')
            body += '</section>'
        body += (f'<section class=panel><a class=bad href="{_h("/forget?" + urlencode({"scope":key,"id":memory_id}))}">预览永久遗忘的影响</a></section>')
        return self._shell(record["title"], body)

    def preview(self, key: str, query: str, intent: str | None) -> str:
        if not query.strip():
            raise store.MemoryError("validation_error", "Supply task terms for recall preview.")
        kind, root = self._target(key)
        result = store.recall(query[:500], project_root=root if kind == "project" else None,
                              global_root=self.global_root, readonly=True, force=True,
                              intent=intent if intent in store.INTENTS else None,
                              max_candidates=50, max_details=20, max_chars=20000)
        body = '<section class=panel><p>只读预览：不会记录召回次数，也不证明 AI 将执行这些规则。</p>'
        for bucket in result.get("stores", []):
            body += f'<h2>{_h(bucket["scope"])} · {_h(bucket["status"])}</h2>'
            for record in bucket.get("records", []):
                target = "global" if bucket["scope"] == "global" else key
                body += f'<p><a href="{_h("/record?" + urlencode({"scope":target,"id":record["id"]}))}">{_h(record["title"])}</a></p>'
            if bucket.get("context_incomplete"):
                body += '<p class=warn>召回结果超出预算；未加载的记录不能视为已检查。</p>'
        body += '</section>'
        return self._shell("召回预览", body)

    def forget_preview(self, key: str, memory_id: str) -> str:
        kind, root = self._target(key)
        state = self._status(key)
        if state.get("status") != "available" or not state.get("recall_enabled"):
            raise store.MemoryError("disabled", "This store is not readable.")
        result = store.forget_preview(kind, memory_id, project_root=root, global_root=self.global_root)
        body = '<section class=panel><p class=bad>永久遗忘会删除以下记录及其受影响的派生记录；此操作没有普通撤销。</p><ul>'
        body += ''.join(f'<li>{_h(row["title"])} · 修订 {_h(row["revision"])}</li>' for row in result["records"])
        body += '</ul>'
        if result["promoted_global_ids"]:
            body += '<p class=warn>关联的全局记录不会自动删除：' + ', '.join(map(_h, result["promoted_global_ids"])) + '</p>'
        body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=forget>'
                 f'<input type=hidden name=scope value="{_h(key)}"><input type=hidden name=id value="{_h(memory_id)}">'
                 f'<input type=hidden name=token value="{_h(result["confirmation_token"])}">'
                 '<label><input type=checkbox name=confirm value=yes required>我已阅读影响范围并确认永久遗忘</label>'
                 '<button class=danger>永久遗忘</button></form><p class=muted>宿主对话和用户自行复制的文件不在此工具的删除范围内。</p></section>')
        return self._shell("遗忘影响预览", body)

    def projects_page(self, notice: str = "") -> str:
        body = ('<section class=panel>备份已创建，文件保存在该库的 backups 目录。</section>'
                if notice == "backup_created" else "")
        body += '<section class=panel><h2>添加已有项目</h2><p>只登记已初始化的项目路径，不扫描整个磁盘，也不复制记忆正文。</p>'
        body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=add_project>'
                 '<input name=path placeholder="项目根目录的绝对路径" size=55 required><button>登记项目</button></form></section>')
        for row in projects(self.global_root):
            key = row["namespace_id"]
            state = self._status(key)
            body += (f'<section class=panel><h2>{_h(Path(row["path"]).name)}</h2><p class=record>{_h(row["path"])}</p>'
                     f'<p>状态：{_h(state.get("status"))}　捕获：{_h(state.get("capture_enabled", "?"))}'
                     f'　召回：{_h(state.get("recall_enabled", "?"))}　捕获模式：{_h(state.get("capture_mode", "?"))}</p>')
            if state.get("status") == "available":
                body += f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=backup><input type=hidden name=scope value="{_h(key)}"><button>备份此库</button></form>'
                body += self._control_form(key)
                body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=mode>'
                         f'<input type=hidden name=scope value="{_h(key)}"><select name=mode>'
                         f'<option value=full-project {"selected" if state.get("capture_mode") == "full-project" else ""}>保存符合条件的项目记忆</option>'
                         f'<option value=developer-first {"selected" if state.get("capture_mode") == "developer-first" else ""}>仅开发者习惯模式，不新增项目记忆</option>'
                         '</select><button>更新项目捕获模式</button></form>')
            body += (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=remove_project>'
                     f'<input type=hidden name=scope value="{_h(key)}"><button class=danger>仅从看板移除</button></form></section>')
        body += (f'<section class=panel><h2>全局库</h2><form method=post action=/action>{self._form_token()}'
                 '<input type=hidden name=action value=backup><input type=hidden name=scope value=global><button>备份全局库</button></form>'
                 + self._control_form("global") + '</section>')
        return self._shell("项目管理", body)

    def _control_form(self, key: str) -> str:
        state = self._status(key)
        current = ("disable" if not state.get("recall_enabled") else
                   "on" if state.get("capture_enabled") else "pause")
        return (f'<form method=post action=/action>{self._form_token()}<input type=hidden name=action value=control>'
                f'<input type=hidden name=scope value="{_h(key)}"><select name=mode>'
                f'<option value=pause {"selected" if current == "pause" else ""}>暂停捕获，保留召回</option>'
                f'<option value=disable {"selected" if current == "disable" else ""}>禁用捕获和召回</option>'
                f'<option value=on {"selected" if current == "on" else ""}>开启捕获和召回</option>'
                '</select><button>更新控制</button></form>')

    def action(self, form: dict[str, str]) -> str:
        action = form.get("action", "")
        if action == "add_project":
            path = Path(form.get("path", ""))
            if not path.is_absolute():
                raise store.MemoryError("project_root_invalid", "Use an absolute project path.")
            register_project(path, self.global_root)
            return "/projects"
        key = form.get("scope", "")
        if action == "remove_project":
            if key == "global" or not remove_project(key, self.global_root):
                raise store.MemoryError("project_not_registered", "Project is not registered.")
            return "/projects"
        kind, root = self._target(key)
        if action == "mode":
            mode = form.get("mode")
            if kind != "project" or mode not in {"full-project", "developer-first"}:
                raise store.MemoryError("validation_error", "Unsupported project capture mode.")
            base, _, config = store._config_for(kind, root, self.global_root)
            config.update(capture_mode=mode, updated_at=store.utc_now())
            store.write_json_atomic(base / "config.json", config)
            return "/projects"
        if action == "control":
            mode = form.get("mode")
            if mode not in {"pause", "disable", "on"}:
                raise store.MemoryError("validation_error", "Unsupported control mode.")
            base, _, config = store._config_for(kind, root, self.global_root)
            config.update(capture_enabled=mode == "on", recall_enabled=mode != "disable",
                          updated_at=store.utc_now())
            store.write_json_atomic(base / "config.json", config)
            return "/projects"
        if action == "backup":
            store.backup_store(kind, project_root=root, global_root=self.global_root)
            return "/?" + urlencode({"scope": key, "notice": "backup_created"})
        if action == 'vectors_sync':
            import dev_memory_vectors as vectors
            vectors.schedule(kind, project_root=root, global_root=self.global_root)
            return '/?scope=' + key
        memory_id = form.get("id", "")
        if action == "forget":
            if form.get("confirm") != "yes":
                raise store.MemoryError("confirmation_required", "Confirm permanent forgetting.")
            store.forget_apply(kind, memory_id, form.get("token", ""), project_root=root, global_root=self.global_root)
            return "/?scope=" + key
        if action not in {"archive", "revise", "confirm"}:
            raise store.MemoryError("validation_error", "Unsupported dashboard action.")
        if action in {"archive", "confirm"} and form.get("confirm") != "yes":
            raise store.MemoryError("confirmation_required", "Confirm this action.")
        current = store.show_record(kind, memory_id, project_root=root, global_root=self.global_root)
        if "record" not in current:
            raise store.MemoryError("disabled", "This store is not readable.")
        record = current["record"]
        try:
            expected = int(form.get("revision", ""))
        except ValueError as exc:
            raise store.MemoryError("validation_error", "Revision is required.") from exc
        if expected != record["revision"]:
            raise store.MemoryError("revision_conflict", "Record changed; reload it before editing.")
        if action == "archive":
            if record["status"] not in {"active", "candidate", "conflicted", "stale"}:
                raise store.MemoryError("scope_error", "This record cannot be archived from the dashboard.")
            operation = {"op": "ARCHIVE", "scope": kind, "id": memory_id, "expected_revision": expected}
        else:
            updated = dict(record)
            # A browser edit or confirmation is user evidence, never a fresh tool verification.
            updated["verification"] = {}
            updated["last_verified_at"] = None
            if action == "confirm":
                if kind != "global" or record["status"] != "candidate" or record["kind"] != "preference":
                    raise store.MemoryError("scope_error", "Only a global preference candidate can be confirmed.")
                updated.update(status="active", cross_project_confirmed=True)
                updated["source"] = {"type": "user_confirmation", "excerpt": "我确认这条规则适用于以后所有项目。"}
            else:
                if (record["status"] != "active" or record["claim_type"] not in {"desired", "preference"}
                        or record["kind"] == "summary"):
                    raise store.MemoryError("scope_error", "This record needs a source review before a semantic revision.")
                reason = form.get("reason", "").strip()
                if not reason or len(reason) > 500:
                    raise store.MemoryError("validation_error", "A short user basis is required.")
                for field in ("title", "content", "conditions", "exceptions", "do", "dont", "rationale", "verification_steps"):
                    if field in form:
                        updated[field] = form[field]
                updated["source"] = {"type": "user_statement", "excerpt": reason}
            operation = {"op": "REVISE", "scope": kind, "id": memory_id,
                         "expected_revision": expected, "record": updated}
        turn = uuid.uuid4().hex
        payload = {"schema_version": 1, "scope": kind, "session_id": "local-dashboard",
                   "turn_id": turn, "idempotency_key": "dashboard:" + turn, "operations": [operation]}
        result = store.apply_payload(payload, project_root=root, global_root=self.global_root, schedule_vectors=False)
        if result.get("status") not in {"saved", "checked_noop"}:
            first = result.get("stores", [{}])[0]
            raise store.MemoryError(first.get("error", "apply_failed"), "Memory change was not committed.")
        return "/record?" + urlencode({"scope": key, "id": memory_id})


def serve(global_root: Path | None = None, *, project_root: Path | None = None,
          open_browser: bool = True) -> None:
    if project_root is not None:
        register_project(project_root, global_root)
    app = Dashboard(global_root)
    access = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass  # Paths and query terms can contain private memory text.

        def _respond(self, body: str, status: int = 200, location: str | None = None,
                     set_cookie: bool = False) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            # Chromium sends Origin:null on navigation POSTs under no-referrer.
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", f"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-{app.script_nonce}'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            if location:
                self.send_header("Location", location)
            if set_cookie:
                self.send_header("Set-Cookie", f"dev_memory_session={access}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(encoded)

        def _host_ok(self) -> bool:
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def _authorized(self) -> bool:
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                item = cookie.get("dev_memory_session")
                return bool(item and secrets.compare_digest(item.value, access))
            except (CookieError, ValueError):
                return False

        def do_GET(self) -> None:
            if not self._host_ok():
                self._respond("Invalid host", 403); return
            parsed = urlsplit(self.path)
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            if parsed.path == "/" and params.get("access") and secrets.compare_digest(params["access"], access):
                self._respond("", 303, "/", set_cookie=True); return
            if not self._authorized():
                self._respond("Forbidden", 403); return
            try:
                if parsed.path == "/":
                    body = app.index(params)
                elif parsed.path == "/record":
                    body = app.detail(params.get("scope", ""), params.get("id", ""),
                                      include_vector=params.get("vector") == "1")
                elif parsed.path == "/forget":
                    body = app.forget_preview(params.get("scope", ""), params.get("id", ""))
                elif parsed.path == "/projects":
                    body = app.projects_page(params.get("notice", ""))
                else:
                    self._respond("Not found", 404); return
                self._respond(body)
            except (store.MemoryError, OSError, sqlite3.Error, ValueError) as exc:
                self._respond(app._shell("无法读取", f'<section class=panel>{_h(exc)}</section>'), 400)

        def do_POST(self) -> None:
            if not self._host_ok() or not self._authorized():
                self._respond("本机看板会话无效，请从看板启动链接重新打开页面。", 403); return
            origin = self.headers.get("Origin")
            if origin is not None:
                parsed_origin = urlsplit(origin)
                if (parsed_origin.scheme != "http" or parsed_origin.hostname != "127.0.0.1" or
                        parsed_origin.port != self.server.server_port or parsed_origin.path not in ("", "/") or
                        parsed_origin.username is not None or parsed_origin.password is not None):
                    self._respond("请求来源与本机看板不一致，请从看板页面重新操作。", 403); return
            route = urlsplit(self.path).path
            if route not in {"/action", "/preview"}:
                self._respond("Not found", 404); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    self._respond("Invalid request size", 413); return
                raw = self.rfile.read(length).decode("utf-8")
                form = {key: values[0] for key, values in parse_qs(raw).items()}
                if not secrets.compare_digest(form.get("csrf", ""), app.csrf):
                    self._respond("页面安全令牌已失效，请刷新看板后重试。", 403); return
                if route == "/preview":
                    self._respond(app.preview(form.get("scope", ""), form.get("q", ""), form.get("intent")))
                    return
                location = app.action(form)
                self._respond("", 303, location)
            except (store.MemoryError, OSError, sqlite3.Error, UnicodeError, ValueError) as exc:
                self._respond(app._shell("操作未完成", f'<section class=panel>{_h(exc)}<p><a href="/">返回看板</a></p></section>'), 400)

    class LocalServer(ThreadingHTTPServer):
        def server_bind(self) -> None:
            # HTTPServer's default calls getfqdn() on startup; loopback DNS can stall CI hosts.
            TCPServer.server_bind(self)
            self.server_name = "127.0.0.1"
            self.server_port = self.server_address[1]

    server = LocalServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/?{urlencode({'access': access})}"
    print(url, flush=True)
    print("Dashboard is running. Keep this terminal open; press Ctrl+C to stop. "
          "If no browser opens, copy the URL above into your browser.", file=sys.stderr, flush=True)
    if open_browser:
        def launch_browser() -> None:
            # Desktop browser launchers can block or fail without affecting the local server.
            try:
                opened = webbrowser.open(url)
            except (webbrowser.Error, OSError):
                opened = False
            if not opened:
                print("Could not open the browser automatically. Open the URL above manually.",
                      file=sys.stderr, flush=True)

        threading.Thread(target=launch_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

"""Local, on-demand dashboard. SQLite remains the only source of memory truth."""
from __future__ import annotations

import html
import json
import re
import secrets
import sqlite3
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import dev_memory_store as store

STATUS_LABELS = {"active": "生效", "candidate": "候选（未生效）", "conflicted": "冲突待核对",
                 "stale": "待复核", "archived": "已归档", "superseded": "已替代", "all": "全部状态"}
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
            return store.get_store_status(kind, project_root=root, global_root=self.global_root)
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
        nav = ['<a href="/?scope=global">全局记忆</a>']
        for row in projects(self.global_root):
            key = row["namespace_id"]
            nav.append(f'<a href="/?scope={_h(key)}" title="{_h(row["path"])}">{_h(Path(row["path"]).name)}</a>')
        return ("<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>{_h(title)} · Dev Memory</title><style>"
                "body{font:15px/1.6 system-ui,-apple-system,sans-serif;color:#20242c;background:#f5f7fa;margin:0}"
                "header{background:#14223b;color:#fff;padding:18px 24px}header a{color:#fff}"
                "main{max-width:1180px;margin:24px auto;padding:0 18px;display:grid;grid-template-columns:210px minmax(0,1fr);gap:22px}"
                "nav,.panel{background:white;border:1px solid #dce1e8;border-radius:10px;padding:18px;margin-bottom:16px}"
                "nav{align-self:start;position:sticky;top:18px}nav a{display:block;padding:6px 0;overflow-wrap:anywhere}"
                "a{color:#2355a5;text-decoration:none}a:hover{text-decoration:underline}"
                "h1{font-size:1.55rem;margin:0 0 14px}h2{font-size:1.15rem;margin:0 0 10px}h3{margin-bottom:6px}"
                ".muted{color:#5c6878}.warn{color:#a14c00}.bad{color:#a52222}.pill{background:#eaf0fb;padding:2px 8px;border-radius:12px}"
                ".scope-row{display:flex;justify-content:space-between;gap:16px;border-top:1px solid #e9edf2;padding:10px 0}"
                "table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e6e9ee;padding:8px}"
                "input,select,textarea,button{font:inherit;padding:7px;margin:4px 5px 4px 0;max-width:100%;box-sizing:border-box}"
                "form.filters{display:flex;flex-wrap:wrap;align-items:center;gap:8px}form.filters>*{margin:0}"
                "form.filters input[name=q]{flex:1;min-width:170px}"
                "textarea{width:100%;min-height:90px}button{background:#2456a6;color:white;border:0;border-radius:5px;cursor:pointer}"
                "button.danger{background:#ad2d2d}form.inline{display:inline}.record{white-space:pre-wrap;overflow-wrap:anywhere}"
                "details{margin:8px 0}code{overflow-wrap:anywhere}@media(max-width:750px){main{display:block}nav{position:static}.scope-row{display:block}}"
                "</style><header><strong>Dev Memory</strong>　<span>本机记忆看板</span></header><main><nav><strong>记忆范围</strong>"
                + "".join(nav) + '<hr><a href="/?scope=all">跨范围搜索</a><a href="/projects">项目管理</a></nav>'
                f'<div><h1>{_h(title)}</h1>{body}</div></main></html>')

    def _form_token(self) -> str:
        return f'<input type=hidden name=csrf value="{_h(self.csrf)}">'

    def _stats(self, key: str, month: str) -> tuple[str, dict]:
        status = self._status(key)
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
        result = store.recall_stats(kind, month, project_root=root, global_root=self.global_root)
        return f'{result["total_recalls"]} 次详情返回（不代表 AI 采用）', {
            item["id"]: item["recall_count"] for item in result["memories"]}

    def _list(self, key: str, query: str, status_filter: str, page: int) -> tuple[list[dict], bool, int]:
        kind, root = self._target(key)
        state = self._status(key)
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
            rows = conn.execute(f"SELECT id,title,kind,claim_type,status,strength,updated_at,revision "
                                f"FROM memories WHERE {predicate} ORDER BY updated_at DESC,id DESC LIMIT 50 OFFSET ?",
                                (*params, (page - 1) * 50)).fetchall()
            return [dict(row) for row in rows], count > page * 50, count
        finally:
            conn.close()

    def index(self, params: dict[str, str]) -> str:
        key = params.get("scope", "global")
        query = params.get("q", "")[:120].strip()
        status_filter = params.get("status", "all")
        if status_filter != "all" and status_filter not in store.STATUSES:
            status_filter = "all"
        page = max(1, int(params.get("page", "1")) if params.get("page", "1").isdigit() else 1)
        month = params.get("month", datetime.now(timezone.utc).strftime("%Y-%m"))
        if not re.fullmatch(r"[1-9]\d{3}-(0[1-9]|1[0-2])", month):
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        keys = ["global", *(row["namespace_id"] for row in projects(self.global_root))]
        if key not in keys and key != "all":
            raise store.MemoryError("project_not_registered", "Unknown dashboard scope.")
        cards = []
        for item in keys:
            state = self._status(item)
            counts = state.get("record_counts", {})
            badge = (f'有效 {counts.get("active", 0)} · 候选 {counts.get("candidate", 0)} · 冲突 {counts.get("conflicted", 0)}'
                     if state.get("status") == "available" else f'不可用：{state.get("reason", state.get("status"))}')
            cards.append(f'<div class=scope-row><a href="/?scope={_h(item)}">{_h(self._scope_name(item))}</a><span class=muted>{_h(badge)}</span></div>')
        body = '<section class=panel><h2>记忆范围</h2>' + "".join(cards) + '<p class=muted>只列出已登记项目；各项目仍保存在自己的库中。</p></section>'
        body += (f'<section class=panel><h2>查找记录</h2><form class=filters method=get><select name=scope>'
                 + ''.join(f'<option value="{_h(item)}" {"selected" if key == item else ""}>{_h(self._scope_name(item))}</option>' for item in keys)
                 + f'<option value=all {"selected" if key == "all" else ""}>全部范围</option></select>'
                 + f'<input name=q placeholder="标题或正文" value="{_h(query)}">'
                 + '<select name=status>' + ''.join(f'<option value={_h(item)} {"selected" if item == status_filter else ""}>{_h(STATUS_LABELS[item])}</option>'
                      for item in ("active", "candidate", "conflicted", "stale", "archived", "superseded", "all"))
                 + f'</select><input type=month name=month value="{_h(month)}"><button>查看</button></form></section>')
        rows: list[tuple[str, dict]] = []
        has_more = False
        total = 0
        if key == "all":
            if query:
                for item in keys:
                    subset, more, count = self._list(item, query, status_filter, 1)
                    rows.extend((item, row) for row in subset)
                    has_more |= more
                    total += count
                rows.sort(key=lambda pair: (pair[1]["updated_at"], pair[1]["id"]), reverse=True)
                has_more |= len(rows) > 50
                rows = rows[:50]
            else:
                body += '<section class=panel>输入关键词后可跨所有已登记范围搜索；逐个范围可完整翻页。</section>'
        else:
            subset, has_more, total = self._list(key, query, status_filter, page)
            rows = [(key, row) for row in subset]
            state = self._status(key)
            if state.get("status") == "available" and state.get("recall_enabled"):
                label, counts = self._stats(key, month)
                body += (f'<section class=panel><h2>{_h(self._scope_name(key))}</h2><p>捕获：'
                         f'{"开启" if state.get("capture_enabled") else "暂停"}；召回：开启；{_h(month)}：{_h(label)}</p>'
                         f'<form method=post action=/preview>{self._form_token()}<input type=hidden name=scope value="{_h(key)}">'
                         '<input name=q placeholder="输入任务词，预览当前召回" required><select name=intent>'
                         '<option value="">无意图</option>' + ''.join(f'<option>{_h(i)}</option>' for i in store.INTENTS)
                         + '</select><button>只读召回预览</button></form></section>')
            else:
                counts = {}
                body += f'<section class=panel>该范围当前不可读取：{_h(state.get("reason", "召回已禁用"))}。</section>'
        if rows:
            body += '<section class=panel><h2>记忆记录</h2><table><tr><th>范围 / 标题</th><th>状态</th><th>类型</th><th>更新时间</th><th>月度返回</th></tr>'
            for scope_key, row in rows:
                link = '/record?' + urlencode({"scope": scope_key, "id": row["id"]})
                amount = str(counts.get(row["id"], 0)) if key != "all" else "—"
                body += (f'<tr><td><small>{_h(self._scope_name(scope_key))}</small><br><a href="{_h(link)}">{_h(row["title"])}</a></td>'
                         f'<td>{_h(STATUS_LABELS.get(row["status"], row["status"]))}</td>'
                         f'<td>{_h(KIND_LABELS.get(row["kind"], row["kind"]))} / {_h(CLAIM_LABELS.get(row["claim_type"], row["claim_type"]))}</td>'
                         f'<td>{_h(_local_time(row["updated_at"]))}</td><td>{_h(amount)}</td></tr>')
            body += '</table>'
            if key != "all":
                body += f'<p class=muted>共 {_h(total)} 条；第 {_h(page)} 页。'
                if page > 1:
                    body += f' <a href="{_h("/?" + urlencode({"scope":key,"q":query,"status":status_filter,"month":month,"page":page-1}))}">上一页</a>'
                if has_more:
                    body += f' <a href="{_h("/?" + urlencode({"scope":key,"q":query,"status":status_filter,"month":month,"page":page+1}))}">下一页</a>'
                body += '</p>'
            elif has_more:
                body += '<p class=warn>跨范围搜索仅显示前 50 条；请缩小关键词或进入单个项目完整翻页。</p>'
            body += '</section>'
        elif key != "all" or query:
            body += '<section class=panel>没有符合条件的可读取记录。</section>'
        return self._shell("记忆总览", body)

    def detail(self, key: str, memory_id: str) -> str:
        kind, root = self._target(key)
        data = store.show_record(kind, memory_id, project_root=root, global_root=self.global_root)
        if data.get("status") == "disabled":
            return self._shell("已禁用", '<section class=panel>该范围的记忆读取已禁用。</section>')
        record = data["record"]
        body = f'<section class=panel><p><a href="/?scope={_h(key)}">← {_h(self._scope_name(key))}</a></p>'
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
            body += f'<section class=panel><h2>管理这条记忆</h2><p class=muted>操作使用当前修订号；归档保留审计历史，遗忘将删除受影响记录。</p>'
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
            return "/projects?notice=backup_created"
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
                    updated[field] = form.get(field, "")
                updated["source"] = {"type": "user_statement", "excerpt": reason}
            operation = {"op": "REVISE", "scope": kind, "id": memory_id,
                         "expected_revision": expected, "record": updated}
        turn = uuid.uuid4().hex
        payload = {"schema_version": 1, "scope": kind, "session_id": "local-dashboard",
                   "turn_id": turn, "idempotency_key": "dashboard:" + turn, "operations": [operation]}
        result = store.apply_payload(payload, project_root=root, global_root=self.global_root)
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
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
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
                    body = app.detail(params.get("scope", ""), params.get("id", ""))
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
            if (not self._host_ok() or not self._authorized() or
                    self.headers.get("Origin") not in (None, f"http://127.0.0.1:{self.server.server_port}")):
                self._respond("Forbidden", 403); return
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
                    self._respond("Forbidden", 403); return
                if route == "/preview":
                    self._respond(app.preview(form.get("scope", ""), form.get("q", ""), form.get("intent")))
                    return
                location = app.action(form)
                self._respond("", 303, location)
            except (store.MemoryError, OSError, sqlite3.Error, UnicodeError, ValueError) as exc:
                self._respond(app._shell("操作未完成", f'<section class=panel>{_h(exc)}<p><a href="/">返回看板</a></p></section>'), 400)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/?{urlencode({'access': access})}"
    print(url, flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

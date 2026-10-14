"""Private, per-namespace SQLite storage for dev-memory."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

SCHEMA_VERSION = 1
MAINTENANCE_REVIEW_VERSION = 3
MAINTENANCE_OPS = {'COMPACT', 'MERGE_DUPLICATES', 'MAINTENANCE_REVIEW'}
KINDS = {"preference", "convention", "project_fact", "business_rule", "decision", "lesson", "procedure", "checkpoint", "summary"}
GLOBAL_KINDS = {"preference", "convention", "decision", "lesson", "procedure", "summary"}
CLAIM_TYPES = {"desired", "observed", "preference", "hypothesis"}
STATUSES = {"candidate", "active", "superseded", "archived", "conflicted", "stale"}
STRENGTHS = {"informational", "soft", "hard"}
SOURCES = {"user_statement", "user_confirmation", "user_feedback", "code_observation", "tool_result", "external_reference", "model_inference"}
MAX_EVIDENCE_CHARS = 500
PROJECT_DIR_NAME = ".dev-memory"
MANAGED_EXCLUDE_BEGIN = "# dev-memory managed begin"
MANAGED_EXCLUDE_END = "# dev-memory managed end"

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|client_secret)\s*[:=]\s*[\"']?[A-Za-z0-9._~+/=-]{10,}", re.I),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis)://[^/\s:@]+:[^@\s]+@", re.I),
    re.compile(r"\bCookie\s*:\s*[^\r\n]{8,}", re.I),
    re.compile(r"[?&](?:X-Amz-Signature|Signature|sig)=([^&\s]{12,})", re.I),
]
PROJECT_MARKERS = [
    re.compile(r"(?:^|[\s\"'])(?:/Users/|/home/|[A-Za-z]:[\\/])[^\s\"']+", re.I),
    re.compile(r"(?:^|[\s\"'])\\{2,}[^\\/\s\"']+[\\/]+[^\\/\s\"']+", re.I),
    re.compile(r"(?:^|[\s\"'])\.dev-memory(?:/|\\|$)", re.I),
    re.compile(r"\b(?:project_id|workspace_id|task_id|customer_id|tenant_id)\s*[:=]", re.I),
    re.compile(r"\b(?:ORD|ORDER|CUS|TENANT|PROJ|WS)-[A-Z0-9]{4,}\b", re.I),
]

class MemoryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def new_id() -> str:
    return str(uuid.uuid4())

def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

def write_bytes_atomic(path: Path, data: bytes, mode: int = 0o600, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp_name = tempfile.mkstemp(prefix=".dev-memory-", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        else:
            os.chmod(temp_name, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp_name, path)
        else:
            # Atomic first creation: a concurrent initializer cannot replace the winner's identity.
            os.link(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass

def write_json_atomic(path: Path, value: Any) -> None:
    write_bytes_atomic(path, json_bytes(value))

def _create_config_once(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    try:
        write_bytes_atomic(path, json_bytes(config), replace=False)
    except FileExistsError:
        pass
    return read_json(path)

def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise MemoryError("path_escape", "Configuration files cannot be symlinks.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MemoryError("not_initialized", "Storage is not initialized.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryError("storage_unavailable", "Configuration cannot be read.") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise MemoryError("schema_error", "Unsupported or invalid dev-memory configuration.")
    return value

def default_global_root() -> Path:
    raw = os.environ.get("DEV_MEMORY_HOME")
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".dev-memory").resolve()

def _ensure_not_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for item in (*value.keys(), *value.values()):
            _ensure_not_sensitive(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _ensure_not_sensitive(item)
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS):
        raise MemoryError("sensitive_data_rejected", "Sensitive credential-like data was rejected before storage.")

def _project_marker(text: str) -> bool:
    return any(pattern.search(text) for pattern in PROJECT_MARKERS)

def _run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None

def _workspace_signature(root: Path, module: str | None = None) -> str | None:
    """Hash Git's changed-path list and cheap file metadata; never persist paths or file contents."""
    result = _run_git(root, ["-c", "core.quotepath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if result and result.returncode == 0:
        rows = [row for row in result.stdout.split("\0") if row]
        if len(rows) > 1000:
            return None  # Unknown workspace; never cache a truncated fingerprint as complete.
        bits = ["\n".join(rows[:1000])]
        for row in rows[:1000]:
            path_text = row[3:].split(" -> ")[-1]
            candidate = (root / path_text).resolve()
            if not candidate.is_relative_to(root.resolve()):
                continue
            try:
                stat = candidate.stat()
                bits.append(f"{path_text}:{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:
                bits.append(f"{path_text}:missing")
        return hashlib.sha256("\n".join(bits).encode("utf-8", errors="replace")).hexdigest()
    root_resolved = root.resolve()
    candidate = (root_resolved / module).resolve() if module else root_resolved
    scan_root = candidate if candidate.is_relative_to(root_resolved) and candidate.is_dir() else root_resolved
    bits = []
    visited_dirs = 0
    visited_files = 0
    truncated = False
    for current, dirs, files in os.walk(scan_root, followlinks=False):
        rel_current = Path(current).relative_to(scan_root)
        depth = len(rel_current.parts)
        dirs[:] = [name for name in dirs if name not in {".git", ".dev-memory", "node_modules", ".venv", "venv", "vendor"}]
        if depth >= 2:
            truncated |= bool(dirs)
            dirs[:] = []
        visited_dirs += 1
        for name in dirs:
            rel = (Path(current) / name).relative_to(root_resolved).as_posix()
            bits.append(f"dir:{rel}")
        for name in files:
            if visited_files >= 500:
                break
            file_path = Path(current) / name
            rel = file_path.relative_to(root_resolved).as_posix()
            try:
                stat = file_path.stat(follow_symlinks=False)
                bits.append(f"file:{rel}:{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:
                bits.append(f"file:{rel}:missing")
            visited_files += 1
        if visited_dirs >= 64 or visited_files >= 500:
            truncated = True
            break
    if truncated:
        return None
    return hashlib.sha256("\n".join(sorted(bits)).encode("utf-8", errors="replace")).hexdigest()

def _reject_unsafe_project_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        raise MemoryError("project_root_invalid", "Project root must be an existing directory.")
    forbidden = {Path(resolved.anchor), Path.home().resolve(), Path(tempfile.gettempdir()).resolve()}
    if resolved in forbidden:
        raise MemoryError("project_root_unsafe", "Refusing a filesystem, home, or temporary directory as project root.")
    target = resolved / PROJECT_DIR_NAME
    if target.is_symlink() or (target.exists() and not target.resolve().is_relative_to(resolved)):
        raise MemoryError("path_escape", "Project .dev-memory cannot resolve outside its project root.")
    return resolved

def _git_info(root: Path) -> tuple[Path, Path] | None:
    top = _run_git(root, ["rev-parse", "--show-toplevel"])
    exclude = _run_git(root, ["rev-parse", "--git-path", "info/exclude"])
    if not top or top.returncode or not exclude or exclude.returncode:
        return None
    repo_root = Path(top.stdout.strip()).resolve()
    exclude_path = Path(exclude.stdout.strip())
    if not exclude_path.is_absolute():
        exclude_path = (root / exclude_path).resolve()
    return repo_root, exclude_path

def _ensure_local_git_exclude(root: Path) -> None:
    root = root.resolve()
    info = _git_info(root)
    if not info:
        return
    repo_root, exclude = info
    rel = root.relative_to(repo_root).as_posix()
    memory_path = f"{rel + '/' if rel != '.' else ''}{PROJECT_DIR_NAME}"
    tracked = _run_git(repo_root, ["ls-files", "--", memory_path])
    if tracked and tracked.returncode == 0 and tracked.stdout.strip():
        raise MemoryError("tracked_memory_path", "Project memory path is already tracked; refusing to add private data.")
    ignored = _run_git(repo_root, ["check-ignore", "-q", "--", memory_path + "/"])
    if ignored and ignored.returncode == 0:
        return
    original = exclude.read_bytes() if exclude.exists() else b""
    original_text = original.decode("utf-8", errors="replace")
    # Gitignore patterns need escaping for literal project-directory characters.
    escaped_path = re.sub(r"([\\*?\[\]#! ])", r"\\\1", memory_path)
    rule = f"/{escaped_path}/\n"
    block = f"{MANAGED_EXCLUDE_BEGIN}\n{rule}{MANAGED_EXCLUDE_END}\n".encode("utf-8")
    updated = original + (b"" if not original or original.endswith(b"\n") else b"\n") + block
    mode = (exclude.stat().st_mode & 0o777) if exclude.exists() else 0o644
    try:
        write_bytes_atomic(exclude, updated, mode)
        checked = _run_git(repo_root, ["check-ignore", "-q", "--", memory_path + "/"])
        if not checked or checked.returncode != 0:
            write_bytes_atomic(exclude, original, mode) if original else exclude.unlink(missing_ok=True)
            raise MemoryError("git_exclude_failed", "Could not verify the local Git exclude rule.")
    except OSError as exc:
        raise MemoryError("git_exclude_failed", "Could not protect project memory from Git.") from exc

def locate_project_root(cwd: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        return _reject_unsafe_project_root(Path(explicit))
    current = Path(cwd).expanduser().resolve()
    for parent in (current, *current.parents):
        if (parent / PROJECT_DIR_NAME / "config.json").is_file():
            return _reject_unsafe_project_root(parent)
    info = _git_info(current)
    return _reject_unsafe_project_root(info[0]) if info else None

def global_paths(root: Path | None = None) -> tuple[Path, Path]:
    data_root = (root or default_global_root()).expanduser().resolve()
    candidate = data_root / "global"
    if candidate.is_symlink() or (candidate.exists() and not candidate.resolve().is_relative_to(data_root)):
        raise MemoryError("path_escape", "Global storage cannot resolve outside its configured data root.")
    base = candidate
    return base, base / "memory.sqlite3"

def project_paths(root: Path) -> tuple[Path, Path]:
    project = _reject_unsafe_project_root(root)
    base = project / PROJECT_DIR_NAME
    if base.is_symlink() or (base.exists() and not base.resolve().is_relative_to(project)):
        raise MemoryError("path_escape", "Project storage resolves outside its project root.")
    return base, base / "memory.sqlite3"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY, namespace_id TEXT NOT NULL,
 scope TEXT NOT NULL CHECK(scope IN ('global','project','task')),
 kind TEXT NOT NULL, claim_type TEXT NOT NULL, status TEXT NOT NULL,
 strength TEXT NOT NULL DEFAULT 'informational',
 title TEXT NOT NULL, content TEXT NOT NULL,
 rationale TEXT NOT NULL DEFAULT '', conditions TEXT NOT NULL DEFAULT '',
 exceptions TEXT NOT NULL DEFAULT '', do_text TEXT NOT NULL DEFAULT '',
 dont_text TEXT NOT NULL DEFAULT '', verification_steps TEXT NOT NULL DEFAULT '', verification TEXT NOT NULL DEFAULT '{}',
 tags TEXT NOT NULL DEFAULT '[]', source_refs TEXT NOT NULL DEFAULT '[]',
 task_id TEXT, workspace_id TEXT, branch TEXT, commit_id TEXT,
 code_refs TEXT NOT NULL DEFAULT '[]', source_fingerprint TEXT,
 derived_from TEXT NOT NULL DEFAULT '[]', promoted_global_ids TEXT NOT NULL DEFAULT '[]',
 cross_project_confirmed INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_verified_at TEXT,
 revision INTEGER NOT NULL DEFAULT 1, semantic_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_scope_status ON memories(scope,status,kind);
CREATE INDEX IF NOT EXISTS memory_task ON memories(task_id,status);
CREATE INDEX IF NOT EXISTS memory_task_recent ON memories(task_id,kind,status,updated_at,id);
CREATE INDEX IF NOT EXISTS memory_summary_source ON memories(kind,status);
CREATE TABLE IF NOT EXISTS derived_edges(
 source_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 summary_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 PRIMARY KEY(source_id,summary_id)
);
CREATE INDEX IF NOT EXISTS derived_summary_id ON derived_edges(summary_id);
CREATE INDEX IF NOT EXISTS memory_hash ON memories(semantic_hash,status);
CREATE TABLE IF NOT EXISTS search_terms(
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 term TEXT NOT NULL, PRIMARY KEY(memory_id,term)
);
CREATE INDEX IF NOT EXISTS search_term_term ON search_terms(term,memory_id);
CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY, memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 source_type TEXT NOT NULL, message_id TEXT, ingestion_id TEXT, ingestion_origin TEXT NOT NULL,
 excerpt TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, evidence_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS revisions(
 memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, snapshot TEXT NOT NULL, changed_at TEXT NOT NULL,
 PRIMARY KEY(memory_id,revision)
);
CREATE TABLE IF NOT EXISTS receipts(
 idempotency_key TEXT PRIMARY KEY, session_id TEXT, turn_id TEXT,
 status TEXT NOT NULL, checked_at TEXT NOT NULL, result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS receipt_turn ON receipts(session_id,turn_id);
CREATE TABLE IF NOT EXISTS session_bindings(
 session_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, workspace_id TEXT,
 branch TEXT, commit_id TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_context(
 session_id TEXT NOT NULL, context_key TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(session_id,context_key)
);
CREATE TABLE IF NOT EXISTS merged_aliases(
 source_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
 canonical_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS merged_alias_canonical ON merged_aliases(canonical_id);
CREATE TABLE IF NOT EXISTS forgotten(
 memory_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, forgotten_at TEXT NOT NULL
);
"""

def _check_project_git_write(db_path: Path) -> None:
    if db_path.parent.name != PROJECT_DIR_NAME:
        return  # Global and project data retain independent boundaries.
    root = db_path.parent.parent
    tracked = _run_git(root, ["--literal-pathspecs", "ls-files", "--", PROJECT_DIR_NAME])
    if not tracked or tracked.returncode:
        if any((parent / ".git").exists() for parent in (root, *root.parents)):
            raise MemoryError("git_protection_unavailable", "Project Git protection could not be checked; no private write was attempted.")
        return  # Non-Git projects need no Git exclude.
    if tracked.stdout.strip():
        raise MemoryError("tracked_memory_path", "Project memory is tracked by Git; refusing further private writes.")
    ignored = _run_git(root, ["check-ignore", "-q", "--", PROJECT_DIR_NAME + "/"])
    if not ignored or ignored.returncode:
        raise MemoryError("git_exclude_failed", "Project memory exclusion is missing or unavailable; initialize this project again before writing.")


def _connect(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    if db_path.is_symlink():
        raise MemoryError("path_escape", "Database files cannot be symlinks.")
    if readonly:
        if not db_path.is_file():
            raise MemoryError("not_initialized", "Storage is not initialized.")
        conn = sqlite3.connect(f"file:{quote(str(db_path.resolve()), safe='/')}?mode=ro", uri=True, timeout=2)
    else:
        _check_project_git_write(db_path)
        conn = sqlite3.connect(db_path, timeout=3)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=3000")
    return conn

def _init_database(db_path: Path, namespace_id: str, storage_kind: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(db_path.parent, 0o700)
    except OSError:
        pass
    conn = _connect(db_path)
    try:
        has_meta = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        existing = conn.execute("SELECT value FROM meta WHERE key='namespace_id'").fetchone() if has_meta else None
        if existing and existing[0] != namespace_id:
            raise MemoryError("namespace_mismatch", "Database namespace does not match its configuration.")
        existing_kind = conn.execute("SELECT value FROM meta WHERE key='storage_kind'").fetchone() if has_meta else None
        if existing_kind and existing_kind[0] != storage_kind:
            raise MemoryError("scope_error", "Existing database has another storage scope.")
        conn.executescript(SCHEMA)
        receipt_columns = {row[1] for row in conn.execute("PRAGMA table_info(receipts)")}
        if "payload_hash" not in receipt_columns:
            conn.execute("ALTER TABLE receipts ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
        memory_columns = {row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        if "verification" not in memory_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN verification TEXT NOT NULL DEFAULT '{}'")
        context_columns = conn.execute("PRAGMA table_info(session_context)").fetchall()
        context_pk = [row[1] for row in sorted((row for row in context_columns if row[5]), key=lambda row: row[5])]
        if context_pk == ["session_id"]:
            conn.execute("ALTER TABLE session_context RENAME TO session_context_v1")
            conn.execute("CREATE TABLE session_context(session_id TEXT NOT NULL,context_key TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(session_id,context_key))")
            conn.execute("INSERT INTO session_context(session_id,context_key,updated_at) SELECT session_id,context_key,updated_at FROM session_context_v1")
            conn.execute("DROP TABLE session_context_v1")
        if not conn.execute("SELECT 1 FROM derived_edges LIMIT 1").fetchone():
            for memory_id, sources_json in conn.execute("SELECT id,derived_from FROM memories WHERE kind='summary' AND derived_from!='[]'").fetchall():
                try:
                    source_ids = json.loads(sources_json)
                except (TypeError, json.JSONDecodeError):
                    continue
                conn.executemany("INSERT OR IGNORE INTO derived_edges(source_id,summary_id) VALUES(?,?)",
                                 ((source_id, memory_id) for source_id in source_ids if isinstance(source_id, str)))
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('namespace_id',?)", (namespace_id,))
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('storage_kind',?)", (storage_kind,))
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('data_revision','0')")
        hash_format = conn.execute("SELECT value FROM meta WHERE key='semantic_hash_format'").fetchone()
        if not hash_format or hash_format[0] != '3':
            for (memory_id,) in conn.execute("SELECT id FROM memories").fetchall():
                record = _select_record(conn, memory_id)
                conn.execute("UPDATE memories SET semantic_hash=? WHERE id=?", (_semantic_hash(record), memory_id))
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('semantic_hash_format','3')")
            conn.execute("DELETE FROM session_context")
        _ensure_maintenance(conn)
        conn.commit()
    finally:
        conn.close()
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass

def init_global(root: Path | None = None) -> dict[str, Any]:
    base, db_path = global_paths(root)
    if base.exists() and not (base / "config.json").exists() and any(base.iterdir()):
        raise MemoryError("unmanaged_existing_data", "Existing global data has no configuration; refusing to create a new identity.")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = base / "config.json"
    if config_path.exists():
        config = read_json(config_path)
        ns = config.get("namespace_id")
        if not isinstance(ns, str):
            raise MemoryError("schema_error", "Global namespace ID is missing.")
    else:
        ns = new_id()
        config = {
            "schema_version": SCHEMA_VERSION, "namespace_id": ns, "storage_kind": "global",
            "capture_enabled": True, "recall_enabled": True, "created_at": utc_now(),
            "limits": {"max_candidates": 20, "max_details": 5, "max_context_chars": 4000},
        }
        config = _create_config_once(config_path, config)
        ns = config["namespace_id"]
    if config.get("storage_kind") != "global":
        raise MemoryError("scope_error", "Existing configuration is not a global store.")
    _init_database(db_path, ns, "global")
    return {"status": "initialized", "scope": "global", "namespace_id": ns, "database": str(db_path)}

def init_project(root: Path, capture_mode: str = "full-project") -> dict[str, Any]:
    if capture_mode not in {"developer-first", "full-project"}:
        raise MemoryError("validation_error", "Project capture mode must be developer-first or full-project.")
    project = _reject_unsafe_project_root(root)
    base, db_path = project_paths(project)
    if base.exists() and not (base / "config.json").exists() and any(base.iterdir()):
        raise MemoryError("unmanaged_existing_data", "Existing .dev-memory data has no valid configuration; refusing to overwrite.")
    _ensure_local_git_exclude(project)
    config_path = base / "config.json"
    if config_path.exists():
        config = read_json(config_path)
        if Path(config.get("project_root", "")).resolve() != project:
            raise MemoryError("namespace_mismatch", "This memory store is bound to another project root.")
        ns, workspace_id = config["namespace_id"], config["workspace_id"]
    else:
        ns, workspace_id = new_id(), new_id()
        config = {
            "schema_version": SCHEMA_VERSION, "namespace_id": ns, "workspace_id": workspace_id,
            "storage_kind": "project", "project_root": str(project),
            "capture_enabled": True, "recall_enabled": True, "created_at": utc_now(),
            "capture_mode": capture_mode,
            "limits": {"max_candidates": 20, "max_details": 5, "max_context_chars": 4000},
            "excluded": False,
        }
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        config = _create_config_once(config_path, config)
        ns, workspace_id = config["namespace_id"], config["workspace_id"]
    if config.get("storage_kind") != "project" or Path(config.get("project_root", "")).resolve() != project:
        raise MemoryError("scope_error", "Existing configuration belongs to another scope or project.")
    _init_database(db_path, ns, "project")
    return {"status": "initialized", "scope": "project", "namespace_id": ns, "workspace_id": workspace_id,
            "capture_mode": config.get("capture_mode", "full-project"), "database": str(db_path)}

def _config_for(kind: str, root: Path | None, global_root: Path | None) -> tuple[Path, Path, dict[str, Any]]:
    if kind == "global":
        base, db = global_paths(global_root)
    else:
        if root is None:
            raise MemoryError("project_root_required", "Project scope requires an explicit or detected project root.")
        base, db = project_paths(root)
    config = read_json(base / "config.json")
    if db.is_symlink() or not db.is_file():
        raise MemoryError("not_initialized", "Storage database is not initialized.")
    if kind == "project":
        stored_root = Path(config.get("project_root", "")).resolve()
        if stored_root != _reject_unsafe_project_root(root):
            raise MemoryError("namespace_mismatch", "Project memory is bound to another root.")
    if config.get("storage_kind") != kind:
        raise MemoryError("scope_error", "Storage type does not match requested scope.")
    conn = _connect(db, readonly=True)
    try:
        metadata = dict(conn.execute("SELECT key,value FROM meta WHERE key IN ('namespace_id','storage_kind')"))
        if metadata.get("namespace_id") != config.get("namespace_id") or metadata.get("storage_kind") != kind:
            raise MemoryError("namespace_mismatch", "Database identity does not match its configuration.")
    finally:
        conn.close()
    return base, db, config

def _field_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key, "")
    if isinstance(value, list):
        value = "；".join(str(x) for x in value)
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "")

def _duplicate_partition(record: dict[str, Any]) -> dict[str, Any]:
    # Similar words are not equivalent conditions. Keep truth, scope and version boundaries exact.
    keys = ("kind", "scope", "task_id", "claim_type", "status", "strength", "conditions", "exceptions",
            "do", "dont", "rationale", "verification_steps", "verification", "source_refs", "code_refs",
            "derived_from", "promoted_global_ids", "cross_project_confirmed")
    value = {key: record.get(key) for key in keys}
    if record.get("scope") != "task":
        value["task_id"] = None  # Project rule task IDs are provenance, not narrower applicability.
    if record.get("claim_type") == "observed" or record.get("scope") == "task":
        value.update({key: record.get(key) for key in ("workspace_id", "branch", "commit_id", "source_fingerprint")})
    return value


def _semantic_hash(record: dict[str, Any]) -> str:
    # A content fingerprint, not model semantic similarity. Titles never establish a new rule.
    value = _duplicate_partition(record)
    value["content"] = re.sub(r"\s+", " ", record.get("content", "")).strip()
    return hashlib.sha256(json_bytes(value)).hexdigest()

def _token_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in re.finditer(r"[A-Za-z0-9_.$:/-]+", text.casefold()):
        token = match.group(0).strip("._:/-")
        if len(token) >= 2:
            terms.add(token)
            terms.update(piece for piece in re.split(r"[_.$:/-]+", token) if len(piece) >= 2)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return terms

def _record_search_text(record: dict[str, Any]) -> str:
    return "\n".join(_field_text(record, key) for key in (
        "title", "content", "rationale", "conditions", "exceptions", "do", "dont",
        "verification_steps", "verification", "tags", "code_refs", "source_refs",
    ))

def _update_search_terms(conn: sqlite3.Connection, memory_id: str, record: dict[str, Any]) -> None:
    conn.execute("DELETE FROM search_terms WHERE memory_id=?", (memory_id,))
    conn.executemany("INSERT OR IGNORE INTO search_terms(memory_id,term) VALUES(?,?)",
                     ((memory_id, term) for term in _token_terms(_record_search_text(record))))

def _record_row(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    names = (
        "id", "namespace_id", "scope", "kind", "claim_type", "status", "strength", "title", "content",
        "rationale", "conditions", "exceptions", "do_text", "dont_text", "verification_steps", "verification",
        "tags", "source_refs", "task_id", "workspace_id", "branch", "commit_id", "code_refs",
        "source_fingerprint", "derived_from", "promoted_global_ids", "cross_project_confirmed",
        "created_at", "updated_at", "last_verified_at", "revision", "semantic_hash",
    )
    data = dict(zip(names, row))
    for field in ("tags", "source_refs", "code_refs", "derived_from", "promoted_global_ids", "verification"):
        try:
            fallback = "{}" if field == "verification" else "[]"
            data[field] = json.loads(data[field] or fallback)
        except (TypeError, json.JSONDecodeError):
            data[field] = {} if field == "verification" else []
    data["do"] = data.pop("do_text")
    data["dont"] = data.pop("dont_text")
    data["cross_project_confirmed"] = bool(data["cross_project_confirmed"])
    return data

def _select_record(conn: sqlite3.Connection, memory_id: str) -> dict[str, Any] | None:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id,namespace_id,scope,kind,claim_type,status,strength,title,content,rationale,conditions,exceptions,do_text,dont_text,verification_steps,verification,tags,source_refs,task_id,workspace_id,branch,commit_id,code_refs,source_fingerprint,derived_from,promoted_global_ids,cross_project_confirmed,created_at,updated_at,last_verified_at,revision,semantic_hash FROM memories WHERE id=?",
        (memory_id,),
    ).fetchone()
    return _record_row(row) if row else None

def _validate_global(record: dict[str, Any], source: dict[str, Any], *, inferred_active: bool = False) -> None:
    if record["kind"] not in GLOBAL_KINDS:
        raise MemoryError("scope_error", "This record type cannot be stored globally.")
    if any(record.get(key) for key in ("task_id", "workspace_id", "project_id")):
        raise MemoryError("scope_error", "Global records cannot carry project, workspace, or task identifiers.")
    explicit = record.get("cross_project_confirmed") is True
    inferred_candidate = (record.get("status") == "candidate" and record.get("claim_type") == "preference"
                          and record.get("strength") == "soft" and record.get("cross_project_confirmed") is False)
    inferred_active_rule = (inferred_active and record.get("status") == "active" and record.get("claim_type") == "preference"
                            and record.get("strength") == "soft" and record.get("cross_project_confirmed") is False)
    if not (explicit or inferred_candidate or inferred_active_rule):
        raise MemoryError("scope_error", "Global rules need explicit cross-project scope or a de-identified soft-preference candidate.")
    if source.get("type") not in {"user_statement", "user_confirmation", "user_feedback"}:
        raise MemoryError("provenance_error", "A global rule needs explicit user evidence.")
    if (inferred_candidate or inferred_active_rule) and source.get("type") != "user_feedback":
        raise MemoryError("provenance_error", "Inferred global habits require direct user feedback, not an AI summary.")
    text = json.dumps({"record": record, "source": source}, ensure_ascii=False)
    if _project_marker(text):
        raise MemoryError("scope_error", "Global body or evidence contains a project-specific marker.")

def _valid_local_id(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value))

def _validate_record(record: Any, scope: str, task_id: str | None, namespace_id: str,
                     *, inferred_active: bool = False) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise MemoryError("validation_error", "Record must be a nested JSON object under the operation's record key.")
    _ensure_not_sensitive(record)
    if any(not isinstance(record.get(key), str) or not record[key].strip() for key in ("kind", "title", "content")):
        raise MemoryError("validation_error", "Record requires non-empty kind, title, and content.")
    if record["kind"] not in KINDS:
        raise MemoryError("validation_error", 'Unsupported memory kind; choose: ' + ', '.join(sorted(KINDS)) + '.')
    claim_type = record.get("claim_type", "hypothesis")
    status = record.get("status", "active")
    strength = record.get("strength", "informational")
    revision = record.get("revision", 1)
    if not all(isinstance(v, str) for v in (claim_type, status, strength)) or claim_type not in CLAIM_TYPES or status not in STATUSES or strength not in STRENGTHS:
        raise MemoryError("validation_error", "Unsupported claim type, status, or strength.")
    if not isinstance(revision, int) or revision < 1:
        raise MemoryError("validation_error", "Record revision must be a positive integer.")
    source = record.get("source", {})
    if not isinstance(source, dict) or (source.get("type") is not None and (not isinstance(source["type"], str) or source["type"] not in SOURCES)):
        raise MemoryError("provenance_error", "Invalid record source.")
    if status == "active" and not source.get("type"):
        raise MemoryError("provenance_error", "Active records require an explicit source type.")
    if source.get("excerpt") and (not isinstance(source["excerpt"], str) or len(source["excerpt"]) > MAX_EVIDENCE_CHARS):
        raise MemoryError("validation_error", "Evidence excerpt exceeds 500 characters.")
    if source.get("type") == "model_inference" and status == "active":
        raise MemoryError("provenance_error", "Model inference alone cannot create an active memory.")
    if scope == "global":
        _validate_global(record, source, inferred_active=inferred_active)
    verify = record.get("verification", {})
    if not isinstance(verify, dict):
        raise MemoryError("validation_error", "verification must be an object.")
    last_verified = None
    if verify:
        if source.get("type") != "tool_result":
            raise MemoryError("provenance_error", "Verification requires an actual tool_result source.")
        if not all(isinstance(verify.get(key), str) and verify[key].strip() for key in ("command", "finished_at", "code_version")) or type(verify.get("exit_code")) is not int or verify.get("exit_code") != 0:
            raise MemoryError("provenance_error", "Verified results require command, time, code version, and exit code 0.")
        last_verified = str(verify["finished_at"])
    stable_id = record.get("id") or new_id()
    if not _valid_local_id(stable_id):
        raise MemoryError("validation_error", "Record IDs may contain only letters, digits, underscore, or hyphen.")
    task = record.get("task_id") or task_id
    if task is not None and not _valid_local_id(task):
        raise MemoryError("validation_error", "task_id may contain only letters, digits, underscore, or hyphen.")
    canonical = {
        "id": stable_id, "namespace_id": namespace_id, "scope": scope, "kind": record["kind"],
        "claim_type": claim_type, "status": status, "strength": strength,
        "title": record["title"].strip(), "content": record["content"].strip(),
        "rationale": _field_text(record, "rationale"), "conditions": _field_text(record, "conditions"),
        "exceptions": _field_text(record, "exceptions"), "do": _field_text(record, "do"),
        "dont": _field_text(record, "dont"), "verification_steps": _field_text(record, "verification_steps"),
        "verification": verify,
        "tags": record.get("tags", []), "source_refs": record.get("source_refs", []), "task_id": task,
        "workspace_id": record.get("workspace_id"), "branch": record.get("branch"),
        "commit_id": record.get("commit_id"), "code_refs": record.get("code_refs", []),
        "source_fingerprint": record.get("source_fingerprint"), "derived_from": record.get("derived_from", []),
        "promoted_global_ids": record.get("promoted_global_ids", []),
        "cross_project_confirmed": bool(record.get("cross_project_confirmed")),
        "last_verified_at": last_verified, "source": source, "revision": revision,
        "created_at": record.get("created_at"),
        "expected_source_revisions": record.get("expected_source_revisions", {}),
    }
    for key in ("tags", "source_refs", "code_refs", "derived_from", "promoted_global_ids"):
        if not isinstance(canonical[key], list) or any(not isinstance(item, str) for item in canonical[key]):
            raise MemoryError("validation_error", f"{key} must be a list of strings.")
    if scope == "task" and not task:
        raise MemoryError("scope_error", "Task-scoped records require task_id.")
    if scope == "global" and (canonical["task_id"] or canonical["workspace_id"]):
        raise MemoryError("scope_error", "Global records cannot carry task or workspace identifiers.")
    canonical["semantic_hash"] = _semantic_hash(canonical)
    return canonical

def _add_evidence(conn: sqlite3.Connection, memory_id: str, source: dict[str, Any]) -> bool:
    source_type = source.get("type")
    if not isinstance(source_type, str) or source_type not in SOURCES:
        raise MemoryError("provenance_error", "Unsupported evidence source.")
    excerpt = str(source.get("excerpt", ""))
    if len(excerpt) > MAX_EVIDENCE_CHARS:
        raise MemoryError("validation_error", "Evidence excerpt exceeds 500 characters.")
    _ensure_not_sensitive(excerpt)
    message_id = source.get("message_id")
    provided_ingestion = source.get("ingestion_id")
    ingestion_id = provided_ingestion or new_id()
    origin = "provided" if provided_ingestion and not source.get("_dev_memory_generated_ingestion") else "generated_by_dev_memory"
    basis = message_id if message_id else ingestion_id
    digest = hashlib.sha256(f"{memory_id}\0{source_type}\0{basis}\0{excerpt}".encode("utf-8")).hexdigest()
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='merged_aliases'").fetchone():
        duplicate = conn.execute("""WITH RECURSIVE sources(id) AS (SELECT ? UNION SELECT a.source_id FROM merged_aliases a JOIN sources s ON a.canonical_id=s.id)
            SELECT 1 FROM evidence e JOIN sources s ON e.memory_id=s.id WHERE e.source_type=? AND COALESCE(e.message_id,e.ingestion_id)=? LIMIT 1""", (memory_id, source_type, basis)).fetchone()
        if duplicate:
            return False
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO evidence(id,memory_id,source_type,message_id,ingestion_id,ingestion_origin,excerpt,created_at,evidence_hash) VALUES(?,?,?,?,?,?,?,?,?)",
        (new_id(), memory_id, source_type, message_id, ingestion_id, origin, excerpt, utc_now(), digest),
    )
    return conn.total_changes > before

def _snapshot(record: dict[str, Any]) -> str:
    scrubbed = {key: value for key, value in record.items() if key not in {"source", "semantic_hash"}}
    return json.dumps(scrubbed, ensure_ascii=False, sort_keys=True)

def _invalidate_derived(conn: sqlite3.Connection, source_id: str) -> None:
    aliases_exist = conn.execute("SELECT 1 FROM sqlite_master WHERE name='merged_aliases'").fetchone()
    queue_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='maintenance_pending'").fetchone()
    pending, visited = [source_id], set()
    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        if aliases_exist:
            for (canonical_id,) in conn.execute('SELECT canonical_id FROM merged_aliases WHERE source_id=?', (source,)).fetchall():
                conn.execute("UPDATE memories SET status='conflicted',revision=revision+1,updated_at=? WHERE id=? AND status='active'", (utc_now(), canonical_id))
                if queue_exists:
                    conn.execute('DELETE FROM maintenance_pending WHERE memory_id=?', (canonical_id,))
                pending.append(canonical_id)
        rows = conn.execute("SELECT summary_id FROM derived_edges WHERE source_id=?", (source,)).fetchall()
        for (summary_id,) in rows:
            conn.execute(
                "UPDATE memories SET status='stale',revision=revision+1,updated_at=? WHERE id=? AND kind='summary' AND status IN ('active','candidate','conflicted')",
                (utc_now(), summary_id),
            )
            if queue_exists:
                conn.execute('DELETE FROM maintenance_pending WHERE memory_id=?', (summary_id,))
            pending.append(summary_id)

def _update_derived_edges(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    conn.execute("DELETE FROM derived_edges WHERE summary_id=?", (record["id"],))
    if record["kind"] == "summary":
        conn.executemany("INSERT INTO derived_edges(source_id,summary_id) VALUES(?,?)",
                         ((source_id, record["id"]) for source_id in record["derived_from"]))

def _validate_derived_sources(conn: sqlite3.Connection, record: dict[str, Any], namespace_id: str) -> None:
    source_ids = record["derived_from"]
    if not source_ids:
        return
    if len(set(source_ids)) != len(source_ids):
        raise MemoryError("validation_error", "Summary source IDs must be unique.")
    marks = ",".join("?" for _ in source_ids)
    count = conn.execute(f"SELECT COUNT(*) FROM memories WHERE id IN ({marks}) AND namespace_id=?", (*source_ids, namespace_id)).fetchone()[0]
    if count != len(source_ids):
        raise MemoryError("scope_error", "Summary sources must exist in this same storage namespace.")
    expected = record.get("expected_source_revisions")
    if not isinstance(expected, dict) or set(expected) != set(source_ids):
        raise MemoryError("revision_conflict", "Derived summaries require expected_source_revisions for every source.")
    for source_id in source_ids:
        source = _select_record(conn, source_id)
        if type(expected[source_id]) is not int or expected[source_id] != source["revision"]:
            raise MemoryError("revision_conflict", "Summary source changed; reload before summarizing.")
        if source["scope"] != record["scope"] or record["scope"] == "task" and source.get("task_id") != record.get("task_id"):
            raise MemoryError("scope_error", "Derived summaries must retain their sources' scope and task.")
        ancestors = conn.execute("WITH RECURSIVE deps(id) AS (SELECT ? UNION SELECT e.source_id FROM derived_edges e JOIN deps d ON e.summary_id=d.id) SELECT id FROM deps", (source_id,)).fetchall()
        if record["id"] in {row[0] for row in ancestors}:
            raise MemoryError("validation_error", "Summary dependencies cannot contain cycles.")
        reference = f"dev-memory-source:{source_id}@{source['revision']}"
        if reference not in record["source_refs"]:
            record["source_refs"].append(reference)

def _stamp_record(record: dict[str, Any], top: dict[str, Any]) -> dict[str, Any]:
    stamped = dict(record)
    for key in ("branch", "commit_id"):
        if top.get(key):
            stamped[key] = top[key]
    verification = stamped.get("verification")
    if isinstance(verification, dict) and verification:
        verification = dict(verification)
        if top.get("commit_id"):
            verification.setdefault("commit_id", top["commit_id"])
        if top.get("_workspace_signature"):
            verification.setdefault("workspace_fingerprint", top["_workspace_signature"])
        stamped["verification"] = verification
    return stamped

def _store_record(conn: sqlite3.Connection, record: dict[str, Any], evidence: bool = True, dedupe: bool = True) -> tuple[str, bool]:
    if dedupe:
        existing = conn.execute(
            "SELECT id FROM memories WHERE semantic_hash=? AND scope=? AND status IN ('active','candidate') ORDER BY updated_at DESC LIMIT 1",
            (record["semantic_hash"], record["scope"]),
        ).fetchone()
        if existing and existing[0] != record["id"]:
            evidence_added = evidence and _add_evidence(conn, existing[0], record["source"])
            if evidence_added:
                conn.execute("UPDATE memories SET revision=revision+1,updated_at=? WHERE id=?", (utc_now(), existing[0]))
                _invalidate_derived(conn, existing[0])
            return existing[0], bool(evidence_added)
    conn.execute(
        """INSERT INTO memories(id,namespace_id,scope,kind,claim_type,status,strength,title,content,rationale,conditions,exceptions,do_text,dont_text,verification_steps,verification,tags,source_refs,task_id,workspace_id,branch,commit_id,code_refs,source_fingerprint,derived_from,promoted_global_ids,cross_project_confirmed,created_at,updated_at,last_verified_at,revision,semantic_hash)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET namespace_id=excluded.namespace_id,scope=excluded.scope,kind=excluded.kind,claim_type=excluded.claim_type,status=excluded.status,strength=excluded.strength,title=excluded.title,content=excluded.content,rationale=excluded.rationale,conditions=excluded.conditions,exceptions=excluded.exceptions,do_text=excluded.do_text,dont_text=excluded.dont_text,verification_steps=excluded.verification_steps,verification=excluded.verification,tags=excluded.tags,source_refs=excluded.source_refs,task_id=excluded.task_id,workspace_id=excluded.workspace_id,branch=excluded.branch,commit_id=excluded.commit_id,code_refs=excluded.code_refs,source_fingerprint=excluded.source_fingerprint,derived_from=excluded.derived_from,promoted_global_ids=excluded.promoted_global_ids,cross_project_confirmed=excluded.cross_project_confirmed,updated_at=excluded.updated_at,last_verified_at=excluded.last_verified_at,revision=excluded.revision,semantic_hash=excluded.semantic_hash""",
        (
            record["id"], record["namespace_id"], record["scope"], record["kind"], record["claim_type"], record["status"],
            record["strength"], record["title"], record["content"], record["rationale"], record["conditions"],
            record["exceptions"], record["do"], record["dont"], record["verification_steps"],
            json.dumps(record["verification"], ensure_ascii=False, sort_keys=True),
            json.dumps(record["tags"], ensure_ascii=False), json.dumps(record["source_refs"], ensure_ascii=False),
            record["task_id"], record["workspace_id"], record["branch"], record["commit_id"],
            json.dumps(record["code_refs"], ensure_ascii=False), record["source_fingerprint"],
            json.dumps(record["derived_from"], ensure_ascii=False), json.dumps(record["promoted_global_ids"], ensure_ascii=False),
            int(record["cross_project_confirmed"]), record.get("created_at") or utc_now(), utc_now(),
            record["last_verified_at"], int(record.get("revision", 1)), record["semantic_hash"],
        ),
    )
    if evidence and record["source"].get("type"):
        _add_evidence(conn, record["id"], record["source"])
    _update_derived_edges(conn, record)
    _update_search_terms(conn, record["id"], record)
    return record["id"], True

def _ensure_maintenance(conn: sqlite3.Connection) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS merged_aliases(source_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,canonical_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS merged_alias_canonical ON merged_aliases(canonical_id)")
    conn.execute("CREATE TABLE IF NOT EXISTS maintenance_pending(memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,revision INTEGER NOT NULL,updated_at TEXT NOT NULL,long_content INTEGER NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS maintenance_pending_time ON maintenance_pending(updated_at,memory_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS maintenance_pending_long ON maintenance_pending(long_content,updated_at,memory_id)")
    if not conn.execute("SELECT 1 FROM meta WHERE key='maintenance_seeded'").fetchone():
        conn.execute("INSERT OR IGNORE INTO maintenance_pending SELECT id,revision,updated_at,length(content)>=1200 FROM memories WHERE status='active'")
        conn.execute("INSERT INTO meta(key,value) VALUES('maintenance_seeded','1')")
    review_version = conn.execute("SELECT value FROM meta WHERE key='maintenance_review_version'").fetchone()
    review_existing = not review_version or review_version[0] != str(MAINTENANCE_REVIEW_VERSION)
    if review_existing:
        # One-time bounded cleanup trigger after a maintenance protocol upgrade.
        # Requeue current active records only; historical and other-project data stay untouched.
        conn.execute("INSERT OR IGNORE INTO maintenance_pending SELECT id,revision,updated_at,length(content)>=1200 FROM memories WHERE status='active'")
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('maintenance_review_version',?)", (str(MAINTENANCE_REVIEW_VERSION),))
        if conn.execute("SELECT 1 FROM memories WHERE status='active' LIMIT 1").fetchone():
            conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('maintenance_review_notice','1')")
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('maintenance_cycle_active','1')")
    notice = conn.execute("SELECT 1 FROM meta WHERE key='maintenance_review_notice' AND value='1'").fetchone()
    return bool(notice)


def _queue_maintenance(conn: sqlite3.Connection, memory_id: str) -> None:
    conn.execute("INSERT INTO maintenance_pending SELECT id,revision,updated_at,length(content)>=1200 FROM memories WHERE id=? AND status='active' ON CONFLICT(memory_id) DO UPDATE SET revision=excluded.revision,updated_at=excluded.updated_at,long_content=excluded.long_content", (memory_id,))
    conn.execute("DELETE FROM maintenance_pending WHERE memory_id=? AND NOT EXISTS(SELECT 1 FROM memories WHERE id=? AND status='active')", (memory_id, memory_id))


def _refresh_maintenance_cycle(conn: sqlite3.Connection) -> bool:
    pending = conn.execute("SELECT q.long_content FROM maintenance_pending q JOIN memories m ON m.id=q.memory_id WHERE m.status='active' LIMIT 5").fetchall()
    if not pending:
        conn.execute("DELETE FROM meta WHERE key='maintenance_cycle_active'")
        return False
    if len(pending) == 5 or conn.execute("SELECT 1 FROM maintenance_pending q JOIN memories m ON m.id=q.memory_id WHERE q.long_content=1 AND m.status='active' LIMIT 1").fetchone():
        conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('maintenance_cycle_active','1')")
    return bool(conn.execute("SELECT 1 FROM meta WHERE key='maintenance_cycle_active' AND value='1'").fetchone())


def _maintained_this_turn(conn: sqlite3.Connection, top: dict[str, Any]) -> bool:
    if not top.get('session_id') or not top.get('turn_id'):
        return False
    rows = conn.execute("SELECT result_json FROM receipts WHERE session_id=? AND turn_id=? LIMIT 33",
                        (top['session_id'], top['turn_id'])).fetchall()
    if len(rows) > 32:
        return True  # Defer automatic work rather than inspect an unbounded turn history.
    for (result_json,) in rows:
        try:
            operations = json.loads(result_json)
        except ValueError:
            return True
        if isinstance(operations, list) and any(isinstance(op, dict) and
                (op.get('reviewed_ids') or op.get('merged_ids') or op.get('compacted') is True) for op in operations):
            return True
    return False


def _related_records(conn: sqlite3.Connection, record: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    terms = _token_terms(_record_search_text(record))
    ids = []
    if terms:
        # Prefer discriminating terms. Alphabetically truncating a token set can
        # discard the only topic-specific term in long Chinese/English records.
        all_terms = sorted(terms)
        frequencies = {}
        for offset in range(0, len(all_terms), 400):
            batch = all_terms[offset:offset + 400]
            marks = ','.join('?' for _ in batch)
            frequencies.update({row[0]: row[1] for row in conn.execute(
                f"SELECT term,COUNT(*) FROM search_terms WHERE term IN ({marks}) GROUP BY term",
                batch,
            )})
        # Terms absent from the store cannot retrieve a candidate and should not
        # consume the bounded query budget.
        terms = sorted((term for term in terms if frequencies.get(term, 0)),
                       key=lambda term: (frequencies[term], term))[:64]
        if not terms:
            return []
        marks = ','.join('?' for _ in terms)
        weighted_case = ' '.join('WHEN ? THEN ?' for _ in terms)
        weight_params = [value for term in terms for value in (term, 1.0 / frequencies[term])]
        score = f"(SUM(CASE t.term {weighted_case} ELSE 0 END)+MAX(CASE t.term {weighted_case} ELSE 0 END))*1.0/COUNT(*)"
        ids = [row[0] for row in conn.execute(
            f"SELECT m.id FROM search_terms t JOIN memories m ON m.id=t.memory_id WHERE t.term IN ({marks}) AND m.scope=? AND m.kind=? AND m.claim_type=? AND (?!='task' OR m.task_id IS ?) AND m.status=? GROUP BY m.id ORDER BY {score} DESC,m.updated_at DESC,m.id LIMIT ?",
            (*terms, record['scope'], record['kind'], record['claim_type'], record['scope'], record.get('task_id'), record['status'], *weight_params, *weight_params, limit),
        )]
    return [_select_record(conn, memory_id) for memory_id in ids]


def _maintenance_plan(conn: sqlite3.Connection, config: dict[str, Any], force: bool = False) -> dict[str, Any]:
    if config.get('maintenance_enabled', True) is False:
        return {'status': 'disabled'}
    seeds = conn.execute("SELECT q.memory_id FROM maintenance_pending q JOIN memories m ON m.id=q.memory_id WHERE m.status='active' ORDER BY q.updated_at,q.memory_id LIMIT 5").fetchall()
    long_row = conn.execute("SELECT q.memory_id FROM maintenance_pending q JOIN memories m ON m.id=q.memory_id WHERE q.long_content=1 AND m.status='active' ORDER BY q.updated_at,q.memory_id LIMIT 1").fetchone()
    if not seeds:
        return {'status': 'idle'}
    draining = bool(conn.execute("SELECT 1 FROM meta WHERE key='maintenance_cycle_active' AND value='1'").fetchone())
    if len(seeds) < 5 and not long_row and not force and not draining:
        return {'status': 'waiting', 'pending_up_to_threshold': len(seeds), 'threshold': 5}
    seed_ids = [row[0] for row in seeds]
    anchor_id = long_row[0] if long_row else seed_ids[0]
    anchor = _select_record(conn, anchor_id)
    candidates = {anchor_id: anchor}
    for related in _related_records(conn, anchor):
        if len(candidates) >= 8:
            break
        candidates.setdefault(related['id'], related)
    seed_ids = [i for i in candidates if conn.execute('SELECT 1 FROM maintenance_pending WHERE memory_id=?', (i,)).fetchone()]
    records, remaining, used = [], [], 0
    for record in candidates.values():
        size = len(json.dumps(record, ensure_ascii=False))
        if used + size > 12000:
            remaining.append(record['id'])
            continue
        records.append(record)
        used += size
    pending_count = conn.execute("SELECT COUNT(*) FROM maintenance_pending q JOIN memories m ON m.id=q.memory_id WHERE m.status='active'").fetchone()[0]
    return {'status': 'prepare', 'namespace_id': config['namespace_id'],
            'trigger': 'long_record' if long_row else ('threshold' if len(seeds) == 5 else ('drain' if draining else 'forced_boundary')),
            'record_scope': anchor['scope'], 'task_id': anchor.get('task_id') if anchor['scope'] == 'task' else None,
            'records': records,
            'seed_ids': seed_ids, 'remaining_ids': remaining, 'context_incomplete': bool(remaining),
            'pending_count': pending_count,
            'limits': {'records': 8, 'chars': 12000},
            'instruction': 'Historical data only. Inspect every returned current revision. MERGE_DUPLICATES equivalent rules; if a newer user-confirmed correction makes an older rule false, revise the canonical rule or archive the contradicted rule so it leaves default recall; archive only when an explicit expiry is demonstrably past. Age alone never proves expiry. COMPACT only without losing conditions/exceptions/negation/version. End with MAINTENANCE_REVIEW for every fully inspected current revision, using post-operation revisions. Do not review unseen records, add evidence, promote across stores, or recurse.'}


def maintenance_prepare(kind: str, *, project_root: Path | None = None, global_root: Path | None = None,
                        force: bool = False, session_id: str | None = None, turn_id: str | None = None) -> dict[str, Any]:
    _, db, config = _config_for(kind, project_root, global_root)
    if not config.get('capture_enabled', True) or not config.get('recall_enabled', True) or config.get('excluded'):
        return {'scope': kind, 'status': 'skipped_private'}
    conn = _connect(db, readonly=True)
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='maintenance_pending'").fetchone():
            return {'scope': kind, 'status': 'upgrade_required'}
        deadline = time.monotonic() + 0.5
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if session_id and turn_id:
            private = conn.execute("SELECT 1 FROM receipts WHERE session_id=? AND turn_id=? AND status='skipped_private' LIMIT 1", (session_id, turn_id)).fetchone()
            if private:
                return {'scope':kind, 'status':'skipped_private'}
            if _maintained_this_turn(conn, {'session_id':session_id, 'turn_id':turn_id}):
                return {'scope':kind, 'status':'pending_next_turn'}
        return {'scope': kind, **_maintenance_plan(conn, config, force)}
    except sqlite3.OperationalError:
        return {'scope': kind, 'status': 'deferred', 'reason': 'query_budget_or_storage_failure'}
    finally:
        conn.close()


def match_payload(payload: dict[str, Any], *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    _ensure_not_sensitive(payload)
    scope = payload.get('scope')
    if scope not in {'global', 'project', 'task'} or not isinstance(payload.get('record'), dict):
        raise MemoryError('validation_error', 'match requires one scope and proposed record.')
    kind = 'global' if scope == 'global' else 'project'
    _, db, config = _config_for(kind, project_root, global_root)
    if not config.get('recall_enabled', True) or config.get('excluded'):
        return {'scope': scope, 'status': 'skipped_private'}
    record = _validate_record(payload['record'], scope, payload.get('task_id'), config['namespace_id'])
    conn = _connect(db, readonly=True)
    try:
        deadline = time.monotonic() + 0.5
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        exact = conn.execute("SELECT id FROM memories WHERE semantic_hash=? AND status=? LIMIT 1", (record['semantic_hash'], record['status'])).fetchone()
        candidates = _related_records(conn, record)
        if exact and not any(r['id'] == exact[0] for r in candidates):
            candidates = [_select_record(conn, exact[0]), *candidates[:7]]
        records, remaining, used = [], [], 0
        for candidate in candidates:
            size = len(json.dumps(candidate, ensure_ascii=False))
            if used + size > 12000:
                remaining.append(candidate['id'])
            else:
                records.append(candidate); used += size
        return {'scope': scope, 'status': 'matched' if exact else 'compare', 'exact_id': exact[0] if exact else None,
                'records': records, 'remaining_ids': remaining, 'context_incomplete': bool(remaining),
                'instruction': 'Similarity is not equivalence. Reuse an equivalent record with ADD duplicate_of/expected_revision/equivalent=true; preserve protected fields. Different conditions or versions require separate records or a correction.'}
    except sqlite3.OperationalError:
        return {'scope': scope, 'status': 'deferred', 'context_incomplete': True, 'reason': 'query_budget_or_storage_failure'}
    finally:
        conn.close()


def _maintenance_apply(conn: sqlite3.Connection, config: dict[str, Any], scope: str, op: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    action = op['op']
    if scope == 'global' and _project_marker(json.dumps(op, ensure_ascii=False)):
        raise MemoryError('scope_error', 'Global maintenance cannot carry project-specific markers.')
    reason = op.get('reason')
    if not config.get('recall_enabled', True):
        raise MemoryError('capture_disabled', 'Maintenance requires enabled recall.')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise MemoryError('validation_error', 'Maintenance requires a short semantic review reason.')
    expected = op.get('expected_revisions')
    if not isinstance(expected, dict) or not 1 <= len(expected) <= 8:
        raise MemoryError('validation_error', 'Maintenance requires 1..8 expected_revisions.')
    records = {}
    for memory_id, revision in expected.items():
        record = _select_record(conn, memory_id) if _valid_local_id(memory_id) else None
        if not record or record['scope'] != scope:
            raise MemoryError('scope_error', 'Maintenance cannot escape a record scope.')
        if type(revision) is not int or revision != record['revision']:
            raise MemoryError('revision_conflict', 'Maintenance source changed; reload before retrying.')
        if action != 'MAINTENANCE_REVIEW' and record['status'] != 'active':
            raise MemoryError('validation_error', 'Only active records may be maintained.')
        records[memory_id] = record
    if action == 'MAINTENANCE_REVIEW':
        for memory_id, revision in expected.items():
            conn.execute('DELETE FROM maintenance_pending WHERE memory_id=? AND revision<=?', (memory_id, revision))
        return {'status': 'checked_noop', 'reviewed_ids': list(records), 'reviewed_revisions': expected}, False
    if op.get('meaning_preserved') is not True:
        raise MemoryError('validation_error', 'AI must review meaning preservation before maintenance.')
    target = records.get(op.get('id'))
    if not target:
        raise MemoryError('validation_error', 'Maintenance id must be one of the expected revisions.')
    if action == 'COMPACT':
        content = op.get('content')
        if len(records) != 1 or not isinstance(content, str) or not content.strip() or len(content.strip()) >= len(target['content']):
            raise MemoryError('validation_error', 'COMPACT needs one record and a shorter nonempty content.')
        if target['kind'] == 'summary':
            raise MemoryError('validation_error', 'Rebuild summaries from their atomic sources instead.')
        conn.execute('INSERT INTO revisions VALUES(?,?,?,?)', (target['id'], target['revision'], _snapshot(target), utc_now()))
        revised = {**target, 'content': content.strip(), 'revision': target['revision'] + 1, 'source': {}}
        revised['semantic_hash'] = _semantic_hash(revised)
        other = conn.execute("SELECT id FROM memories WHERE semantic_hash=? AND id!=? AND status='active'", (revised['semantic_hash'], target['id'])).fetchone()
        if other:
            raise MemoryError('duplicate_conflict', 'Compact result duplicates another rule; merge first.')
        _store_record(conn, revised, evidence=False, dedupe=False)
        _invalidate_derived(conn, target['id'])
        conn.execute('DELETE FROM maintenance_pending WHERE memory_id=?', (target['id'],))
        return {'status': 'saved', 'id': target['id'], 'revision': revised['revision'], 'compacted': True,
                'semantic_review': 'ai_claim_not_program_verified', 'evidence_added': False}, True
    if len(records) < 2 or target['kind'] in {'summary', 'checkpoint'}:
        raise MemoryError('validation_error', 'Merge requires 2..8 atomic rules; not summaries/checkpoints.')
    marks = ','.join('?' for _ in records)
    if conn.execute(f'SELECT 1 FROM merged_aliases WHERE source_id IN ({marks}) LIMIT 1', tuple(records)).fetchone():
        raise MemoryError('duplicate_conflict', 'A previously merged source was reactivated; resolve its merge conflict before merging again.')
    if any(_duplicate_partition(r) != _duplicate_partition(target) for r in records.values()):
        raise MemoryError('duplicate_conflict', 'Merge cannot change conditions, exceptions, truth, scope or version fields.')
    conn.execute('INSERT INTO revisions VALUES(?,?,?,?)', (target['id'], target['revision'], _snapshot(target), utc_now()))
    tags = set(target['tags'])
    for memory_id, record in records.items():
        if memory_id == target['id']:
            continue
        # Keep source identities and bodies as superseded audit history, never as fresh evidence.
        conn.execute('INSERT INTO revisions VALUES(?,?,?,?)', (memory_id, record['revision'], _snapshot(record), utc_now()))
        conn.execute("UPDATE memories SET status='superseded',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), memory_id))
        _invalidate_derived(conn, memory_id)
        conn.execute('INSERT OR IGNORE INTO merged_aliases(source_id,canonical_id) VALUES(?,?)', (memory_id, target['id']))
        tags.update(record['tags'])
    revised = {**target, 'revision': target['revision'] + 1, 'tags': sorted(tags), 'source': {}}
    _store_record(conn, revised, evidence=False, dedupe=False)
    _invalidate_derived(conn, target['id'])
    for memory_id in records:
        conn.execute('DELETE FROM maintenance_pending WHERE memory_id=?', (memory_id,))
    return {'status': 'saved', 'id': target['id'], 'revision': revised['revision'], 'merged_ids': [i for i in records if i != target['id']],
            'semantic_review': 'ai_claim_not_program_verified', 'evidence_added': False}, True


def _resolve_maintenance_revisions(conn: sqlite3.Connection, op: dict[str, Any], base: dict[str, int]) -> tuple[dict[str, Any], bool]:
    """Translate a validated batch snapshot, never an externally stale revision."""
    if op.get('op') not in MAINTENANCE_OPS:
        return op, False
    if op['op'] == 'COMPACT' and 'expected_revision' in op:
        revision = op['expected_revision']
        if not _valid_local_id(op.get('id')):
            raise MemoryError('validation_error', 'COMPACT requires a valid local record ID.')
        if type(revision) is not int:
            raise MemoryError('validation_error', 'COMPACT expected_revision must be an integer.')
        supplied = op.get('expected_revisions')
        if supplied is not None and (not isinstance(supplied, dict) or supplied != {op.get('id'):revision}):
            raise MemoryError('validation_error', 'COMPACT revision forms conflict; supply one consistent record revision.')
        op = {**op, 'expected_revisions':{op.get('id'):revision}}
    expected = op.get('expected_revisions')
    if not isinstance(expected, dict) or not 1 <= len(expected) <= 8:
        return op, False
    resolved = dict(expected)
    for memory_id, revision in expected.items():
        current = _select_record(conn, memory_id) if _valid_local_id(memory_id) else None
        if current:
            base.setdefault(memory_id, current['revision'])
            if type(revision) is int and revision == base[memory_id]:
                resolved[memory_id] = current['revision']
    return {**op, 'expected_revisions':resolved}, resolved != expected


def _apply_one(conn: sqlite3.Connection, config: dict[str, Any], scope: str, op: dict[str, Any], top: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    action = op.get("op")
    if action in MAINTENANCE_OPS:
        if config.get('maintenance_enabled', True) is False:
            raise MemoryError('capture_disabled', 'Automatic maintenance is disabled for this store.')
        return _maintenance_apply(conn, config, scope, op)
    if action == "NOOP":
        if not isinstance(op.get("reason"), str) or not op["reason"].strip():
            raise MemoryError("validation_error", "A checked NOOP requires a short reason.")
        return {"status": "checked_noop"}, False
    if action == 'USE':
        allowed = {'op', 'scope', 'id', 'expected_revision', 'reason', 'action_ref'}
        if set(op) - allowed:
            raise MemoryError('validation_error', 'USE reports an action only; it cannot supply content, evidence or verification.')
        current = _select_record(conn, op.get('id')) if _valid_local_id(op.get('id')) else None
        if not current or current['scope'] != scope or current['status'] != 'active':
            raise MemoryError('scope_error', 'USE needs an active rule in this scope.')
        if scope == 'task' and current['task_id'] != top.get('task_id'):
            raise MemoryError('scope_error', 'USE cannot report another task rule.')
        if type(op.get('expected_revision')) is not int or op['expected_revision'] != current['revision']:
            raise MemoryError('revision_conflict', 'The used rule changed; inspect the current revision.')
        if any(not isinstance(op.get(key), str) or not op[key].strip() or len(op[key]) > 500 for key in ('reason', 'action_ref')):
            raise MemoryError('validation_error', 'USE needs a short concrete reason and action_ref.')
        if scope == 'global' and _project_marker(json.dumps(op, ensure_ascii=False)):
            raise MemoryError('scope_error', 'Global USE receipts cannot contain project markers.')
        return {'status':'checked_noop', 'used_id':current['id'], 'revision':current['revision'],
                'reason':op['reason'], 'action_ref':op['action_ref'],
                'usage':'ai_reported_not_behavior_verified', 'evidence_added':False}, False
    if action in {"ADD", "CHECKPOINT"}:
        if not isinstance(op.get("record"), dict):
            raise MemoryError("validation_error", f'{action} requires a nested record JSON object; do not flatten its fields onto the operation.')
        record = dict(op["record"])
        if action == "CHECKPOINT":
            record["kind"] = "checkpoint"
        record = _stamp_record(record, top)
        source = record.get("source")
        if isinstance(source, dict) and not source.get("message_id") and not source.get("ingestion_id"):
            source = dict(source)
            source["ingestion_id"] = _turn_ingestion(top)
            source["_dev_memory_generated_ingestion"] = True
            record["source"] = source
        data = _validate_record(record, scope, top.get("task_id"), config["namespace_id"])
        if conn.execute("SELECT 1 FROM memories WHERE id=?", (data["id"],)).fetchone():
            raise MemoryError("revision_conflict", "ADD cannot overwrite a record; use REVISE with expected_revision.")
        if conn.execute("SELECT 1 FROM forgotten WHERE memory_id=?", (data["id"],)).fetchone():
            raise MemoryError("forgotten_record", "A forgotten record ID cannot be ingested again.")
        _validate_derived_sources(conn, data, config["namespace_id"])
        duplicate_of = op.get('duplicate_of')
        if duplicate_of is not None:
            canonical = _select_record(conn, duplicate_of) if _valid_local_id(duplicate_of) else None
            if not canonical or canonical['scope'] != scope or canonical['status'] != data['status']:
                raise MemoryError('scope_error', 'Duplicate target must be active in this same scope.')
            if type(op.get('expected_revision')) is not int or op['expected_revision'] != canonical['revision']:
                raise MemoryError('revision_conflict', 'Duplicate target changed; reload it.')
            if op.get('equivalent') is not True or _duplicate_partition(canonical) != _duplicate_partition(data):
                raise MemoryError('duplicate_conflict', 'Duplicate reuse requires equivalent meaning and unchanged protected fields.')
            if data['kind'] in {'summary', 'checkpoint'}:
                raise MemoryError('validation_error', 'Semantic duplicate reuse supports atomic rules only.')
            changed = _add_evidence(conn, duplicate_of, data['source'])
            if changed:
                conn.execute('UPDATE memories SET revision=revision+1,updated_at=? WHERE id=?', (utc_now(), duplicate_of))
                _invalidate_derived(conn, duplicate_of)
            return {'status': 'saved' if changed else 'duplicate_evidence', 'id': duplicate_of,
                    'revision': canonical['revision'] + int(changed), 'duplicate_merged': True,
                    'body_written': False, 'semantic_review': 'ai_claim_not_program_verified'}, bool(changed)
        memory_id, changed = _store_record(conn, data)
        promoted = False
        if scope == "global" and data["status"] == "candidate" and data["claim_type"] == "preference" and data["strength"] == "soft":
            independent = conn.execute("SELECT COUNT(DISTINCT ingestion_id) FROM evidence WHERE memory_id=? AND source_type='user_feedback' AND ingestion_id LIKE 'habit:%'", (memory_id,)).fetchone()[0]
            if independent >= 2 and _select_record(conn, memory_id)["status"] == "candidate":
                current_candidate = _select_record(conn, memory_id)
                conn.execute("INSERT INTO revisions(memory_id,revision,snapshot,changed_at) VALUES(?,?,?,?)",
                             (memory_id, current_candidate["revision"], _snapshot(current_candidate), utc_now()))
                conn.execute("UPDATE memories SET status='active',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), memory_id))
                changed = promoted = True
                _queue_maintenance(conn, memory_id)
        retired = []
        if data['kind'] == 'checkpoint' and scope == 'task' and data['status'] == 'active':
            previous = conn.execute("SELECT id FROM memories WHERE scope='task' AND task_id=? AND kind='checkpoint' AND status='active' AND id!=?", (data['task_id'], memory_id)).fetchall()
            for (old_id,) in previous:
                old = _select_record(conn, old_id)
                conn.execute('INSERT INTO revisions VALUES(?,?,?,?)', (old_id, old['revision'], _snapshot(old), utc_now()))
                conn.execute("UPDATE memories SET status='superseded',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), old_id))
                _invalidate_derived(conn, old_id)
                _queue_maintenance(conn, old_id)
                retired.append(old_id)
            changed = changed or bool(retired)
        current = _select_record(conn, memory_id)
        return {"status": "saved" if changed else "duplicate_evidence", "id": memory_id,
                "revision": current["revision"] if current else 1, "duplicate_merged": memory_id != data["id"],
                "habit_promoted": promoted, "independent_task_signals": independent if scope == "global" and data["status"] == "candidate" and data["claim_type"] == "preference" and data["strength"] == "soft" else None,
                "superseded_checkpoint_ids": retired}, changed
    memory_id = op.get("id")
    if not _valid_local_id(memory_id):
        raise MemoryError("validation_error", "This operation requires a valid record ID.")
    current = _select_record(conn, memory_id)
    if current is None:
        raise MemoryError("not_found", "Memory record was not found in the selected store.")
    if scope != current["scope"]:
        raise MemoryError("scope_error", "Operation scope must match the existing record.")
    expected = op.get("expected_revision")
    if action in {"REVISE", "SUPERSEDE", "ARCHIVE", "MARK_CONFLICT", "ADD_EVIDENCE"} and (type(expected) is not int or expected != current["revision"]):
        raise MemoryError("revision_conflict", "Record revision changed; reload it before retrying.")
    if action == "ADD_EVIDENCE":
        source = op.get("source")
        if not isinstance(source, dict):
            raise MemoryError("provenance_error", "ADD_EVIDENCE requires a source object.")
        source = dict(source)
        if not source.get("message_id") and not source.get("ingestion_id"):
            source["ingestion_id"] = _turn_ingestion(top)
            source["_dev_memory_generated_ingestion"] = True
        _ensure_not_sensitive(source)
        if scope == "global":
            inferred = current["cross_project_confirmed"] is False and current["status"] == "active" and current["strength"] == "soft"
            _validate_global(current, source, inferred_active=inferred)
        inserted = _add_evidence(conn, memory_id, source)
        if inserted:
            conn.execute("UPDATE memories SET revision=revision+1,updated_at=? WHERE id=?", (utc_now(), memory_id))
            _invalidate_derived(conn, memory_id)
        return {"status": "saved" if inserted else "duplicate_evidence", "id": memory_id,
                "revision": current["revision"] + (1 if inserted else 0)}, inserted
    if action in {"ARCHIVE", "MARK_CONFLICT"}:
        status = "archived" if action == "ARCHIVE" else "conflicted"
        conn.execute("INSERT INTO revisions(memory_id,revision,snapshot,changed_at) VALUES(?,?,?,?)",
                     (memory_id, current["revision"], _snapshot(current), utc_now()))
        conn.execute("UPDATE memories SET status=?,revision=revision+1,updated_at=? WHERE id=?", (status, utc_now(), memory_id))
        _invalidate_derived(conn, memory_id)
        return {"status": "saved", "id": memory_id, "revision": current["revision"] + 1}, True
    if action == "REVISE":
        if not isinstance(op.get("record"), dict):
            raise MemoryError("validation_error", "REVISE record must be a JSON object.")
        data = dict(op["record"])
        data.update({"id": memory_id, "revision": current["revision"] + 1, "created_at": current["created_at"]})
        data.setdefault("source", {})
        if isinstance(data["source"], dict) and not data["source"].get("message_id") and not data["source"].get("ingestion_id"):
            data["source"] = {**data["source"], "ingestion_id": _turn_ingestion(top), "_dev_memory_generated_ingestion": True}
        keeps_old_verification = data.get("verification", {}) == current["verification"] and bool(current["verification"])
        data = _stamp_record(data, top)
        if keeps_old_verification:
            data["verification"] = current["verification"]
        inferred = (current["scope"] == "global" and current["cross_project_confirmed"] is False
                    and current["status"] == "active" and current["strength"] == "soft")
        revised = _validate_record(data, current["scope"], top.get("task_id"), config["namespace_id"], inferred_active=inferred)
        if revised["semantic_hash"] != current["semantic_hash"] and revised["verification"] == current["verification"]:
            revised["verification"] = {}
            revised["last_verified_at"] = None
        _validate_derived_sources(conn, revised, config["namespace_id"])
        conn.execute("INSERT INTO revisions(memory_id,revision,snapshot,changed_at) VALUES(?,?,?,?)",
                     (memory_id, current["revision"], _snapshot(current), utc_now()))
        other = conn.execute("SELECT id FROM memories WHERE semantic_hash=? AND id!=? AND status IN ('active','candidate')",
                             (revised["semantic_hash"], memory_id)).fetchone()
        if other:
            raise MemoryError("duplicate_conflict", "The revised rule duplicates another record; inspect and merge explicitly.")
        _store_record(conn, revised, dedupe=False)
        _invalidate_derived(conn, memory_id)
        return {"status": "saved", "id": memory_id, "revision": current["revision"] + 1}, True
    if action == "SUPERSEDE":
        data = op.get("record")
        if not isinstance(data, dict):
            raise MemoryError("validation_error", "SUPERSEDE requires a replacement record.")
        conn.execute("INSERT INTO revisions(memory_id,revision,snapshot,changed_at) VALUES(?,?,?,?)",
                     (memory_id, current["revision"], _snapshot(current), utc_now()))
        conn.execute("UPDATE memories SET status='superseded',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), memory_id))
        _invalidate_derived(conn, memory_id)
        replacement_data = dict(data)
        keeps_old_verification = replacement_data.get("verification", {}) == current["verification"] and bool(current["verification"])
        replacement_data = _stamp_record(replacement_data, top)
        if keeps_old_verification:
            replacement_data["verification"] = current["verification"]
        replacement = _validate_record(replacement_data, current["scope"], top.get("task_id"), config["namespace_id"])
        if replacement["id"] == memory_id or conn.execute("SELECT 1 FROM memories WHERE id=?", (replacement["id"],)).fetchone():
            raise MemoryError("revision_conflict", "SUPERSEDE requires a new replacement ID.")
        if conn.execute("SELECT 1 FROM forgotten WHERE memory_id=?", (replacement["id"],)).fetchone():
            raise MemoryError("forgotten_record", "A forgotten replacement ID cannot be reused.")
        if replacement["semantic_hash"] != current["semantic_hash"] and replacement["verification"] == current["verification"]:
            replacement["verification"], replacement["last_verified_at"] = {}, None
        _validate_derived_sources(conn, replacement, config["namespace_id"])
        new_memory_id, changed = _store_record(conn, replacement)
        return {"status": "saved", "id": new_memory_id, "supersedes": memory_id, "duplicate_merged": new_memory_id != replacement["id"]}, True
    if action == "FORGET":
        raise MemoryError("confirmation_required", "Use forget preview and forget apply for deletion.")
    raise MemoryError("validation_error", "Unsupported operation.")

def _turn_ingestion(top: dict[str, Any]) -> str:
    basis = json.dumps([top.get("session_id"), top.get("turn_id"), top.get("idempotency_key") if not top.get("turn_id") else None])
    return hashlib.sha256(basis.encode()).hexdigest()

def _apply_store(kind: str, root: Path | None, global_root: Path | None, operations: list[dict[str, Any]], top: dict[str, Any]) -> dict[str, Any]:
    target_scope = kind
    try:
        base, db_path, config = _config_for(kind, root, global_root)
    except MemoryError as exc:
        return {"scope": target_scope, "status": "failed", "error": exc.code, "message": exc.message}
    except (sqlite3.Error, OSError):
        return {"scope": target_scope, "status": "failed", "error": "storage_unavailable", "message": "Storage identity could not be checked."}
    if not config.get("capture_enabled", True) or config.get("excluded") is True:
        return {"scope": target_scope, "status": "skipped_private", "checked": False}
    top = dict(top)
    if kind == "project" and config.get("capture_mode", "full-project") == "developer-first":
        if any(op.get("op") in {"ADD", "CHECKPOINT", "SUPERSEDE"} for op in operations):
            return {"scope": target_scope, "status": "skipped_developer_first",
                    "message": "New project/task memories are disabled in developer-first mode; enable full-project mode to capture them."}
    if kind == "global":
        task_id = top.get("task_id")
        prepared = []
        for op in operations:
            op = dict(op)
            record = op.get("record")
            if (op.get("op") == "ADD" and isinstance(record, dict) and record.get("status") == "candidate"
                    and record.get("scope", "global") == "global" and record.get("kind") == "preference"
                    and record.get("claim_type") == "preference" and record.get("strength") == "soft"
                    and record.get("cross_project_confirmed") is False):
                if not isinstance(task_id, str) or not task_id:
                    return {"scope": target_scope, "status": "failed", "error": "provenance_error",
                            "message": "A habit candidate needs an opaque task ID to count independent user evidence."}
                record = dict(record)
                source = dict(record.get("source") or {})
                if source.get("type") != "user_feedback":
                    return {"scope": target_scope, "status": "failed", "error": "provenance_error",
                            "message": "Habit candidates require direct user feedback."}
                source.pop("message_id", None)
                digest = hashlib.sha256(f"{config['namespace_id']}\0{task_id}".encode()).hexdigest()
                source["ingestion_id"] = "habit:" + digest
                source["_dev_memory_generated_ingestion"] = True
                record["source"] = source
                op["record"] = record
            prepared.append(op)
        operations = prepared
        # Request context belongs to the project side of a mixed-scope batch.
        # Explicit project identifiers in a global record still fail validation.
        for key in ("task_id", "workspace_id", "project_id", "branch", "commit_id", "module", "_workspace_signature"):
            top.pop(key, None)
    if kind == "project" and root is not None and any(isinstance(op.get("record"), dict) and op["record"].get("verification") for op in operations):
        top["_workspace_signature"] = _workspace_signature(root, top.get("module"))
    idem = str(top.get("idempotency_key") or "")
    if not idem:
        return {"scope": target_scope, "status": "failed", "error": "validation_error", "message": "idempotency_key is required."}
    changed_ids: set[str] = set()
    results: list[dict[str, Any]] = []
    conn = None
    try:
        conn = _connect(db_path)
        conn.execute("BEGIN IMMEDIATE")
        review_existing = _ensure_maintenance(conn)
        _refresh_maintenance_cycle(conn)
        maintained_this_turn = _maintained_this_turn(conn, top)
        if review_existing:
            conn.execute("DELETE FROM meta WHERE key='maintenance_review_notice'")
        private = conn.execute("SELECT 1 FROM receipts WHERE session_id=? AND turn_id=? AND status='skipped_private'",
                               (top.get("session_id"), top.get("turn_id"))).fetchone()
        if private:
            conn.rollback()
            conn.close()
            return {"scope": target_scope, "status": "skipped_private", "checked": False}
        digest = hashlib.sha256(json_bytes({"operations": operations, "session_id": top.get("session_id"),
                                           "turn_id": top.get("turn_id"), "task_id": top.get("task_id")})).hexdigest()
        replay = conn.execute("SELECT status,result_json,payload_hash FROM receipts WHERE idempotency_key=?", (idem,)).fetchone()
        if replay:
            if not replay[2] or replay[2] != digest:
                raise MemoryError("idempotency_conflict", "This key belongs to a different or legacy request; inspect it before using a new key.")
            conn.rollback()
            conn.close()
            return {"scope": target_scope, "status": replay[0], "idempotent_replay": True, "operations": json.loads(replay[1])}
        content_changed = False
        has_noop = False
        batch_revisions: dict[str, int] = {}
        for op in operations:
            op, revisions_resolved = _resolve_maintenance_revisions(conn, op, batch_revisions)
            op_scope = op.get("scope", target_scope)
            if op.get("op") == "CHECKPOINT":
                op_scope = "task"
            if target_scope == "global" and op_scope != "global":
                raise MemoryError("scope_error", "A project or task operation reached the global store.")
            result, changed = _apply_one(conn, config, op_scope, op, top)
            if revisions_resolved:
                result['revision_resolution'] = 'within_batch'
            results.append(result)
            content_changed |= changed
            has_noop |= result["status"] == "checked_noop"
            if changed and result.get("id"):
                changed_ids.add(result["id"])
                if op.get('op') not in MAINTENANCE_OPS:
                    _queue_maintenance(conn, result['id'])
        if kind == "project" and top.get("session_id") and top.get("task_id"):
            conn.execute(
                "INSERT INTO session_bindings(session_id,task_id,workspace_id,branch,commit_id,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET task_id=excluded.task_id,workspace_id=excluded.workspace_id,branch=excluded.branch,commit_id=excluded.commit_id,updated_at=excluded.updated_at",
                (top["session_id"], top["task_id"], config.get("workspace_id"), top.get("branch"), top.get("commit_id"), utc_now()),
            )
        status = "saved" if content_changed else ("checked_noop" if has_noop else "saved")
        draining = _refresh_maintenance_cycle(conn)
        if content_changed:
            conn.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='data_revision'")
        # Keep usage identity/revision, not another copy of project prose in receipts.
        receipt_results = [{k:v for k,v in result.items() if k not in {'reason','action_ref'}}
                           if result.get('usage') == 'ai_reported_not_behavior_verified' else result for result in results]
        result_blob = json.dumps(receipt_results, ensure_ascii=False, sort_keys=True)
        conn.execute(
            "INSERT INTO receipts(idempotency_key,session_id,turn_id,status,checked_at,result_json,payload_hash) VALUES(?,?,?,?,?,?,?)",
            (idem, top.get("session_id"), top.get("turn_id"), status, utc_now(), result_blob, digest),
        )
        committed_revision = int(conn.execute("SELECT value FROM meta WHERE key='data_revision'").fetchone()[0])
        conn.commit()
        conn.close()
        maintenance = {'status': 'not_due'}
        maintained_this_turn |= any(op['op'] in MAINTENANCE_OPS for op in operations)
        if maintained_this_turn and draining:
            maintenance = {'status':'pending_next_turn'}
        elif (content_changed or review_existing or draining) and not maintained_this_turn:
            try:
                maintenance = maintenance_prepare(kind, project_root=root, global_root=global_root)
            except (MemoryError, sqlite3.Error, OSError):
                maintenance = {'status': 'deferred', 'reason': 'storage_unavailable'}
        output = {"scope": target_scope, "status": status, "operations": results, "data_revision": committed_revision, "maintenance": maintenance}
        if changed_ids:
            output["view_status"] = "stale_until_export"
        return output
    except MemoryError as exc:
        if conn is not None:
            conn.rollback()
            conn.close()
        return {"scope": target_scope, "status": "failed", "error": exc.code, "message": exc.message, "transaction":"rolled_back"}
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return {"scope": target_scope, "status": "failed", "error": "revision_conflict", "message": "A concurrent update conflicted; reload before retrying."}
    except (sqlite3.Error, OSError):
        try:
            if conn is not None:
                conn.rollback()
                conn.close()
        except sqlite3.Error:
            pass
        return {"scope": target_scope, "status": "failed", "error": "storage_unavailable", "message": "Storage write failed."}

def apply_payload(payload: dict[str, Any], *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise MemoryError("validation_error", "Unsupported or invalid apply payload.")
    _ensure_not_sensitive(payload)
    scope = payload.get("scope")
    if not isinstance(scope, str) or scope not in {"global", "project", "task", "both"}:
        raise MemoryError("scope_error", "Apply scope must be global, project, task, or both.")
    if scope in {"project", "task", "both"} and project_root is None:
        raise MemoryError("project_root_required", "Project and task operations require an explicit project root.")
    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        raise MemoryError("validation_error", "At least one operation is required.")
    groups: dict[str, list[dict[str, Any]]] = {"global": [], "project": []}
    for op in operations:
        if not isinstance(op, dict):
            raise MemoryError("validation_error", "Each operation must be a JSON object.")
        if not isinstance(op.get("op"), str) or not isinstance(op.get("scope", scope), str):
            raise MemoryError("validation_error", "Operation and scope must be strings.")
        target = op.get("scope", scope)
        if op.get("op") == "CHECKPOINT":
            target = op.get("scope", "task")
        if target == "both":
            if op.get("op") != "NOOP":
                raise MemoryError("scope_error", "Only a checked NOOP may target both stores.")
            groups["global"].append({**op, "scope": "global"})
            groups["project"].append({**op, "scope": "project"})
        elif target == "global":
            groups["global"].append({**op, "scope": "global"})
        elif target in {"project", "task"}:
            groups["project"].append({**op, "scope": target})
        else:
            raise MemoryError("scope_error", "Unsupported operation scope.")
    if scope == "global" and groups["project"] or scope in {"project", "task"} and groups["global"]:
        raise MemoryError("scope_error", 'An operation cannot escape the selected storage scope; mixed global/project/task writes need envelope scope both and explicit scope on each operation.')
    results = []
    for kind, group in groups.items():
        if group:
            root = project_root if kind == "project" else None
            results.append(_apply_store(kind, root, global_root, group, payload))
    statuses = [item["status"] for item in results]
    successes = {"saved", "checked_noop", "duplicate_evidence"}
    skipped = {"skipped_private", "skipped_developer_first"}
    failures = [status for status in statuses if status not in successes and status not in skipped]
    if failures and any(status in successes for status in statuses):
        overall = "partial_success"
    elif failures:
        overall = "failed"
    elif "saved" in statuses:
        overall = "saved"
    elif "checked_noop" in statuses:
        overall = "checked_noop"
    elif "skipped_developer_first" in statuses:
        overall = "skipped_developer_first"
    else:
        overall = "skipped_private"
    return {"status": overall, "stores": results}

def receipt_for_turn(kind: str, *, session_id: str, turn_id: str, project_root: Path | None = None,
                     global_root: Path | None = None) -> dict[str, Any]:
    try:
        _, db, _ = _config_for(kind, project_root, global_root)
        conn = _connect(db, readonly=True)
        row = conn.execute(
            "SELECT status,checked_at FROM receipts WHERE session_id=? AND turn_id=? ORDER BY CASE status WHEN 'skipped_private' THEN 0 ELSE 1 END,checked_at DESC LIMIT 1",
            (session_id, turn_id),
        ).fetchone()
        conn.close()
        return {"scope": kind, "status": row[0], "checked_at": row[1]} if row else {"scope": kind, "status": "missing"}
    except (MemoryError, sqlite3.Error):
        return {"scope": kind, "status": "unavailable"}

def record_private_skip(scope: str, *, session_id: str, turn_id: str,
                        project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    """Persist only opaque turn identifiers so bounded recovery cannot reprocess an opted-out turn."""
    if not session_id or not turn_id or scope not in {"global", "project", "both"}:
        raise MemoryError("validation_error", "Private skip requires session and turn IDs, and a valid store scope.")
    if scope in {"project", "both"} and project_root is None:
        raise MemoryError("project_root_required", "Project private skip requires the current project root.")
    targets = ["project", "global"] if scope == "both" else [scope]
    results = []
    for kind in targets:
        try:
            _, db_path, config = _config_for(kind, project_root if kind == "project" else None, global_root)
            if not config.get("capture_enabled", True):
                results.append({"scope": kind, "status": "capture_disabled"})
                continue
            conn = _connect(db_path)
            idem = hashlib.sha256(f"skip:{kind}:{session_id}:{turn_id}".encode()).hexdigest()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR IGNORE INTO receipts(idempotency_key,session_id,turn_id,status,checked_at,result_json) VALUES(?,?,?,?,?,?)",
                    (idem, session_id, turn_id, "skipped_private", utc_now(), "[]"),
                )
                conn.commit()
                results.append({"scope": kind, "status": "skipped_private"})
            finally:
                conn.close()
        except (MemoryError, sqlite3.Error, OSError) as exc:
            results.append({"scope": kind, "status": "failed", "error": getattr(exc, "code", "storage_unavailable")})
    if any(item["status"] == "failed" for item in results) and any(item["status"] != "failed" for item in results):
        status = "partial_success"
    elif any(item["status"] == "failed" for item in results):
        status = "failed"
    else:
        status = "skipped_private"
    return {"status": status, "stores": results}

def _claim_context(kind: str, db_path: Path, config: dict[str, Any], session_id: str | None, key: str, force: bool) -> bool:
    if not session_id:
        return True
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT 1 FROM session_context WHERE session_id=? AND context_key=?", (session_id, key)).fetchone()
        if row and not force:
            conn.rollback()
            return False
        conn.execute(
            "INSERT INTO session_context(session_id,context_key,updated_at) VALUES(?,?,?) ON CONFLICT(session_id,context_key) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, key, utc_now()),
        )
        conn.execute("DELETE FROM session_context WHERE session_id=? AND context_key NOT IN (SELECT context_key FROM session_context WHERE session_id=? ORDER BY updated_at DESC LIMIT 32)",
                     (session_id, session_id))
        conn.commit()
        return True
    finally:
        conn.close()

def _context_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record.get(key) for key in (
        "id", "scope", "kind", "claim_type", "status", "strength", "title", "content",
        "conditions", "exceptions", "do", "dont", "verification_steps", "tags", "task_id",
        "branch", "commit_id", "verification", "verification_status", "last_verified_at", "revision", "derived_from",
        "source_refs", "code_refs",
    )}

def _verification_status(record: dict[str, Any], root: Path | None, current_head: str | None,
                         current_signature: str | None) -> str | None:
    verification = record.get("verification") or {}
    if not verification:
        return None
    if root is None:
        return "version_unknown"
    if current_signature is None:
        return "workspace_unknown"
    verified_signature = verification.get("workspace_fingerprint")
    verified_commit = verification.get("commit_id") or record.get("commit_id")
    if verified_signature and current_signature and verified_signature != current_signature:
        return "stale_workspace_changed"
    if verified_commit and current_head and verified_commit != current_head:
        return "stale_commit_changed"
    if not verified_signature and not verified_commit:
        return "version_unpinned"
    return "current_workspace"

def _recall_store(kind: str, root: Path | None, global_root: Path | None, query: str, *, task_id: str | None,
                  session_id: str | None, module: str | None, max_candidates: int, max_details: int,
                  max_chars: int, force: bool, readonly: bool, resume: bool = False) -> dict[str, Any]:
    try:
        base, db_path, config = _config_for(kind, root, global_root)
    except MemoryError as exc:
        return {"scope": kind, "status": "unavailable", "reason": exc.code, "records": []}
    except (sqlite3.Error, OSError):
        return {"scope": kind, "status": "unavailable", "reason": "storage_unavailable", "records": []}
    if not config.get("recall_enabled", True) or config.get("excluded") is True:
        return {"scope": kind, "status": "disabled", "records": []}
    readonly = readonly or not config.get("capture_enabled", True)
    limits = config.get("limits", {})
    if not isinstance(limits, dict) or any(type(limits.get(k, v)) is not int for k, v in (("max_candidates", 20), ("max_details", 5), ("max_context_chars", 4000))):
        return {"scope": kind, "status": "unavailable", "reason": "config_invalid", "records": []}
    max_candidates = min(max_candidates, limits.get("max_candidates", 20))
    max_details = min(max_details, limits.get("max_details", 5))
    max_chars = min(max_chars, limits.get("max_context_chars", 4000))
    max_candidates = max(1, min(int(max_candidates), 100))
    max_details = max(0, min(int(max_details), 20))
    max_chars = max(0, min(int(max_chars), 20000))
    try:
        current_revision = data_revision(db_path)
    except (sqlite3.Error, OSError, MemoryError):
        return {"scope": kind, "status": "unavailable", "reason": "storage_unavailable", "records": []}
    active_task = task_id
    if kind == "project" and not active_task and session_id:
        try:
            binding_conn = _connect(db_path, readonly=True)
            binding = binding_conn.execute("SELECT task_id FROM session_bindings WHERE session_id=?", (session_id,)).fetchone()
            active_task = binding[0] if binding else None
            binding_conn.close()
        except sqlite3.Error:
            active_task = task_id
    cache_value = {
        "retrieval_format": 2,
        "namespace": config["namespace_id"], "workspace": config.get("workspace_id"),
        "revision": current_revision, "task": active_task, "module": module, "resume": resume,
        "query_terms": sorted(_token_terms(query[:10000]))[:128],
        "limits": [max_candidates, max_details, max_chars],
    }
    current_head = None
    current_signature = None
    if root:
        branch = _run_git(root, ["branch", "--show-current"])
        head = _run_git(root, ["rev-parse", "--short=12", "HEAD"])
        current_head = head.stdout.strip() if head and head.returncode == 0 else None
        current_signature = _workspace_signature(root, module)
        cache_value["branch"] = branch.stdout.strip() if branch and branch.returncode == 0 else None
        cache_value["head"] = current_head
        cache_value["workspace_signature"] = current_signature
    cache_key = hashlib.sha256(json.dumps(cache_value, sort_keys=True).encode("utf-8")).hexdigest()
    can_cache = root is None or current_signature is not None
    conn = None
    try:
        if session_id and not force and not readonly and can_cache:
            cache_conn = _connect(db_path, readonly=True)
            previous = cache_conn.execute("SELECT 1 FROM session_context WHERE session_id=? AND context_key=?", (session_id, cache_key)).fetchone()
            cache_conn.close()
            if previous:
                return {"scope": kind, "status": "cached", "records": [], "context_incomplete": False, "data_revision": current_revision}
        conn = _connect(db_path, readonly=True)
        deadline = time.monotonic() + 0.5
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        conn.row_factory = sqlite3.Row
        ns_row = conn.execute("SELECT value FROM meta WHERE key='namespace_id'").fetchone()
        if not ns_row or ns_row[0] != config["namespace_id"]:
            conn.close()
            return {"scope": kind, "status": "namespace_mismatch", "records": []}
        terms = set(sorted(_token_terms(query[:10000]))[:128])
        scores: dict[str, int] = {}
        candidate_limit_reached = False
        if terms:
            placeholders = ",".join("?" for _ in terms)
            scopes = ["global"] if kind == "global" else ["project", "task"]
            scope_marks = ",".join("?" for _ in scopes)
            found = conn.execute(
                f"""SELECT m.id,COUNT(DISTINCT st.term) score FROM search_terms st INDEXED BY search_term_term
                CROSS JOIN memories m ON m.id=st.memory_id
                WHERE st.term IN ({placeholders}) AND m.status IN ('active','conflicted')
                AND m.scope IN ({scope_marks})
                AND (m.scope!='task' OR (? IS NOT NULL AND m.task_id=?))
                GROUP BY m.id ORDER BY score DESC,m.updated_at DESC LIMIT ?""",
                (*sorted(terms), *scopes, active_task, active_task, max_candidates + 1),
            ).fetchall()
            candidate_limit_reached = len(found) > max_candidates
            scores = {row["id"]: row["score"] for row in found}
        selected_ids = set(scores)
        if kind == "global":
            selected_ids.update(row[0] for row in conn.execute(
                "SELECT id FROM memories WHERE kind IN ('preference','convention') AND status='active' ORDER BY CASE strength WHEN 'hard' THEN 0 ELSE 1 END,updated_at DESC LIMIT ?",
                (max_candidates + 1,),
            ).fetchall())
        if resume and kind == "project" and not active_task:
            # Offer recent task candidates without silently binding an ambiguous
            # "continue" request to one task. Detail budgets still apply.
            selected_ids.update(row[0] for row in conn.execute(
                """SELECT m.id FROM memories m
                WHERE m.scope='task' AND m.kind='checkpoint' AND m.status IN ('active','conflicted')
                AND NOT EXISTS (SELECT 1 FROM memories n WHERE n.task_id=m.task_id AND n.kind='checkpoint'
                    AND n.status IN ('active','conflicted') AND
                    (n.updated_at>m.updated_at OR (n.updated_at=m.updated_at AND n.id>m.id)))
                ORDER BY m.updated_at DESC,m.id DESC LIMIT ?""", (min(3, max_candidates) + 1,),
            ).fetchall())
        if active_task and kind == "project":
            selected_ids.update(row[0] for row in conn.execute(
                "SELECT id FROM memories WHERE scope='task' AND task_id=? AND kind='checkpoint' AND status IN ('active','conflicted') ORDER BY updated_at DESC LIMIT 2",
                (active_task,),
            ).fetchall())
        if kind == "project":
            selected_ids.update(row[0] for row in conn.execute(
                "SELECT id FROM memories WHERE scope='project' AND strength='hard' AND status IN ('active','conflicted') ORDER BY updated_at DESC LIMIT ?",
                (max_candidates + 1,),
            ).fetchall())
        if not selected_ids:
            empty_store = conn.execute("SELECT 1 FROM memories WHERE status IN ('active','candidate','conflicted') LIMIT 1").fetchone() is None
            conn.close()
            if session_id and not readonly and can_cache:
                _claim_context(kind, db_path, config, session_id, cache_key, True)
            return {"scope": kind, "status": "ok", "records": [], "context_incomplete": False,
                    "candidate_count": 0, "data_revision": current_revision, "empty_store": empty_store}
        records = []
        for memory_id in selected_ids:
            record = _select_record(conn, memory_id)
            if record:
                record["_score"] = scores.get(memory_id, 0)
                record["verification_status"] = _verification_status(record, root, current_head, current_signature)
                records.append(record)
        conn.close()
        records.sort(key=lambda record: (record["updated_at"], record["id"]), reverse=True)
        records.sort(key=lambda record: (
            0 if record["kind"] == "checkpoint" and (record.get("task_id") == active_task or resume) else 1,
            0 if record['_score'] > 0 else 1,
            0 if record["strength"] == "hard" else 1,
            -record["_score"],
        ))
        overflow_ids = [r["id"] for r in records[max_candidates:]]
        candidate_count = len(records)
        all_candidates = records
        records = records[:max_candidates]
        details: list[dict[str, Any]] = []
        remaining: list[str] = overflow_ids
        used = 0
        for record in records:
            shaped = _context_record(record)
            size = len(json.dumps(shaped, ensure_ascii=False))
            if len(details) >= max_details or used + size > max_chars:
                remaining.append(record["id"])
            else:
                details.append(shaped)
                used += size
        unloaded = []
        index_chars = 0
        for record in all_candidates:
            if record['id'] not in remaining:
                continue
            descriptor = {key:record.get(key) for key in ('id','kind','claim_type','status','strength','task_id','revision')}
            descriptor.update(title=record['title'][:120], tags=record['tags'][:8],
                              query_match=record['_score'] > 0, content_loaded=False)
            size = len(json.dumps(descriptor, ensure_ascii=False))
            if len(unloaded) == 8 or index_chars + size > 2000:
                break
            unloaded.append(descriptor)
            index_chars += size
        if session_id and not readonly and not remaining and can_cache:
            _claim_context(kind, db_path, config, session_id, cache_key, True)
        return {
            "scope": kind, "status": "ok", "records": details, "candidate_count": candidate_count,
            "context_incomplete": bool(remaining), "remaining_ids": remaining,
            "unloaded_candidates": unloaded,
            "candidate_limit_reached": candidate_limit_reached or bool(overflow_ids),
            "task_id": active_task, "namespace_id": config["namespace_id"], "data_revision": current_revision,
        }
    except sqlite3.OperationalError:
        return {"scope": kind, "status": "deferred", "reason": "query_budget_or_storage_failure", "context_incomplete": True, "records": []}
    except (sqlite3.Error, OSError, MemoryError):
        return {"scope": kind, "status": "unavailable", "reason": "storage_unavailable", "records": []}
    finally:
        if conn is not None:
            conn.close()

def recall(query: str, *, project_root: Path | None = None, global_root: Path | None = None,
           task_id: str | None = None, session_id: str | None = None, module: str | None = None,
           max_candidates: int = 20, max_details: int = 5, max_chars: int = 4000,
           force: bool = False, readonly: bool = False, resume: bool = False) -> dict[str, Any]:
    if project_root is None:
        limits = (max_candidates, max_details, max_chars)
        stores = [_recall_store("global", None, global_root, query, task_id=None, session_id=session_id,
                                module=None, max_candidates=limits[0], max_details=limits[1], max_chars=limits[2],
                                force=force, readonly=readonly)]
    else:
        half_candidates = max(1, max_candidates // 2)
        # Fixed per-store budgets remain stable when one side returns cached.
        # Reserve project capacity even when many global preferences apply.
        global_details = min(2, max(0, max_details // 3))
        global_budget = max(0, max_chars // 3)
        global_result = _recall_store(
            "global", None, global_root, query, task_id=None, session_id=session_id, module=None,
            max_candidates=half_candidates, max_details=global_details, max_chars=global_budget,
            force=force, readonly=readonly,
        )
        remaining_details = max(0, max_details - global_details)
        remaining_chars = max(0, max_chars - global_budget)
        project_result = _recall_store(
            "project", project_root, global_root, query, task_id=task_id, session_id=session_id, module=module,
            max_candidates=max_candidates - half_candidates, max_details=remaining_details,
            max_chars=remaining_chars, force=force, readonly=readonly, resume=resume,
        )
        stores = [global_result, project_result]
    return {
        "status": "partial" if any(s["status"] in {"unavailable", "deferred"} for s in stores) else "ok",
        "context_incomplete": any(s.get("context_incomplete", False) for s in stores),
        "stores": stores,
    }

def data_revision(db_path: Path) -> int:
    try:
        conn = _connect(db_path, readonly=True)
        row = conn.execute("SELECT value FROM meta WHERE key='data_revision'").fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except (sqlite3.Error, MemoryError, OSError):
        return 0

def show_current(kind: str, memory_ids: list[str], *, project_root: Path | None = None,
                 global_root: Path | None = None) -> dict[str, Any]:
    if not 1 <= len(memory_ids) <= 8 or len(set(memory_ids)) != len(memory_ids) or any(not _valid_local_id(i) for i in memory_ids):
        raise MemoryError('validation_error', 'Current lookup requires 1..8 distinct valid IDs.')
    _, db, config = _config_for(kind, project_root, global_root)
    if not config.get('recall_enabled', True) or config.get('excluded'):
        return {'scope': kind, 'status': 'disabled', 'records': []}
    conn = _connect(db, readonly=True)
    try:
        records, remaining, missing, used = [], [], [], 0
        for memory_id in memory_ids:
            record = _select_record(conn, memory_id)
            if record is None:
                missing.append(memory_id)
                continue
            size = len(json.dumps(record, ensure_ascii=False))
            if used + size > 12000:
                remaining.append(memory_id)
            else:
                records.append(record); used += size
        return {'scope': kind, 'status': 'ok', 'records': records, 'remaining_ids': remaining,
                'missing_ids': missing, 'context_incomplete': bool(remaining or missing), 'audit_not_loaded': True}
    finally:
        conn.close()


def show_record(kind: str, memory_id: str, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    _, db, _ = _config_for(kind, project_root, global_root)
    conn = _connect(db, readonly=True)
    conn.row_factory = sqlite3.Row
    record = _select_record(conn, memory_id)
    evidence = []
    revisions = []
    if record:
        evidence = [dict(row) for row in conn.execute(
            "SELECT source_type,message_id,ingestion_id,ingestion_origin,excerpt,created_at FROM evidence WHERE memory_id=? ORDER BY created_at",
            (memory_id,),
        )]
        revisions = [dict(row) for row in conn.execute(
            "SELECT revision,snapshot,changed_at FROM revisions WHERE memory_id=? ORDER BY revision", (memory_id,)
        )]
    merged_sources = []
    if record and conn.execute("SELECT 1 FROM sqlite_master WHERE name='merged_aliases'").fetchone():
        merged_sources = [row[0] for row in conn.execute("WITH RECURSIVE sources(id) AS (SELECT source_id FROM merged_aliases WHERE canonical_id=? UNION SELECT a.source_id FROM merged_aliases a JOIN sources s ON a.canonical_id=s.id) SELECT id FROM sources", (memory_id,))]
    conn.close()
    if not record:
        raise MemoryError("not_found", "Memory record was not found.")
    if kind == "project":
        head = _run_git(project_root, ["rev-parse", "--short=12", "HEAD"]) if project_root else None
        signature = _workspace_signature(project_root) if project_root else None
        record["verification_status"] = _verification_status(
            record, project_root, head.stdout.strip() if head and head.returncode == 0 else None, signature
        )
    return {"record": record, "evidence": evidence, "revisions": revisions, "merged_source_ids": merged_sources}

def list_records(kind: str, *, project_root: Path | None = None, global_root: Path | None = None,
                 status: str = "active", limit: int = 50) -> dict[str, Any]:
    if status not in {"active", "candidate", "conflicted", "archived", "superseded", "stale", "all"}:
        raise MemoryError("validation_error", "Unsupported list status.")
    base, db, config = _config_for(kind, project_root, global_root)
    conn = _connect(db, readonly=True)
    conn.row_factory = sqlite3.Row
    if status == "all":
        rows = conn.execute(
            "SELECT id,scope,kind,status,strength,title,conditions,updated_at,revision FROM memories ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(limit, 200)),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,scope,kind,status,strength,title,conditions,updated_at,revision FROM memories WHERE status=? ORDER BY updated_at DESC LIMIT ?",
            (status, max(1, min(limit, 200))),
        ).fetchall()
    conn.close()
    return {"scope": kind, "status": "ok", "records": [dict(row) for row in rows],
            "namespace_id": config["namespace_id"], "limit": max(1, min(limit, 200))}

def _view_bucket(kind: str) -> str:
    return {
        "business_rule": "business", "project_fact": "project", "decision": "decisions",
        "lesson": "lessons", "preference": "preferences", "convention": "conventions",
        "procedure": "procedures", "summary": "summaries", "checkpoint": "tasks",
    }.get(kind, "project")

def _write_text_atomic(path: Path, content: str) -> None:
    write_bytes_atomic(path, content.encode("utf-8"), 0o600)

def _clear_generated_views(base: Path) -> list[str]:
    """Remove managed Markdown only, without following symlinks or unknown files."""
    views = base / "views"
    if not views.exists() and not views.is_symlink():
        return []
    if views.is_symlink():
        return ["views"]
    errors = []
    targets = [views / "INDEX.md", *(views / f"{bucket}.md" for bucket in {_view_bucket(k) for k in KINDS} if bucket != "tasks")]
    tasks = views / "tasks"
    if tasks.is_symlink():
        errors.append("views/tasks")
    elif tasks.is_dir():
        targets.extend(tasks.glob("*.md"))
    for target in targets:
        try:
            if target.is_symlink():
                errors.append(target.relative_to(base).as_posix())
            else:
                target.unlink(missing_ok=True)
        except OSError:
            errors.append(target.relative_to(base).as_posix())
    return errors

def _render_view(records: list[dict[str, Any]], config: dict[str, Any]) -> str:
    lines = ["# dev-memory view", "", f"Namespace: {config['namespace_id']}", f"Generated: {utc_now()}", ""]
    if not records:
        lines.append("_No records._")
    for record in records:
        lines += [
            f"## {record['title']}", "",
            f"- ID: {record['id']}",
            f"- Scope/status: {record['scope']} / {record['status']}",
            f"- Kind/claim: {record['kind']} / {record['claim_type']}",
            f"- Revision: {record['revision']}",
            f"- Content: {record['content']}",
        ]
        for key, label in (("conditions", "Conditions"), ("exceptions", "Exceptions"), ("do", "Do"),
                           ("dont", "Do not"), ("rationale", "Rationale"), ("verification_steps", "Verification")):
            if record.get(key):
                lines.append(f"- {label}: {record[key]}")
        if record.get("verification"):
            lines.append(f"- Verified run metadata: {json.dumps(record['verification'], ensure_ascii=False, sort_keys=True)}")
        lines.append("")
    return "\n".join(lines)

def refresh_views(base: Path, db_path: Path, config: dict[str, Any], changed_ids: set[str] | None = None) -> None:
    views = base / "views"
    if views.is_symlink():
        raise MemoryError("path_escape", "Generated views cannot be symlinks.")
    conn = _connect(db_path, readonly=True)
    conn.row_factory = sqlite3.Row
    all_ids = conn.execute("SELECT id FROM memories WHERE status IN ('active','conflicted','candidate','stale')").fetchall()
    all_records = [record for row in all_ids if (record := _select_record(conn, row["id"]))]
    conn.close()
    for record in all_records:
        _ensure_not_sensitive(record)
    if changed_ids is None:
        if _clear_generated_views(base):
            raise MemoryError("view_cleanup_failed", "Existing generated views could not be safely replaced.")
    if changed_ids:
        changed_records = [record for record in all_records if record["id"] in changed_ids]
        buckets = {_view_bucket(record["kind"]) for record in changed_records}
    else:
        buckets = {_view_bucket(record["kind"]) for record in all_records}
        buckets.add("tasks")
    for bucket in buckets:
        records = [record for record in all_records if _view_bucket(record["kind"]) == bucket]
        if bucket == "tasks":
            task_dir = views / "tasks"
            if task_dir.is_symlink():
                raise MemoryError("path_escape", "Generated task-view directory cannot be a symlink.")
            for task in {record.get("task_id") for record in records if record.get("task_id")}:
                if not _valid_local_id(task):
                    continue
                target = views / "tasks" / f"{task}.md"
                if target.is_symlink():
                    raise MemoryError("path_escape", "Generated task views cannot be symlinks.")
                _write_text_atomic(target, _render_view([r for r in records if r.get("task_id") == task], config))
        else:
            target = views / f"{bucket}.md"
            if target.is_symlink():
                raise MemoryError("path_escape", "Generated views cannot be symlinks.")
            _write_text_atomic(target, _render_view(records, config))
    # The index is refreshed only on an actual content change or explicit export.
    index = ["# dev-memory index", "", f"Namespace: {config['namespace_id']}", f"Generated: {utc_now()}", ""]
    for record in sorted(all_records, key=lambda r: (r["scope"], r["kind"], r["title"])):
        if record["status"] in {"active", "conflicted", "candidate"}:
            index.append(f"- {record['id']} [{record['scope']}/{record['kind']}/{record['status']}] {record['title']}")
    target = views / "INDEX.md"
    if target.is_symlink():
        raise MemoryError("path_escape", "Generated index cannot be a symlink.")
    _write_text_atomic(target, "\n".join(index) + "\n")
    writable = _connect(db_path)
    try:
        current = writable.execute("SELECT value FROM meta WHERE key='data_revision'").fetchone()
        writable.execute("INSERT INTO meta(key,value) VALUES('view_revision',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                          (str(current[0] if current else 0),))
        writable.commit()
    finally:
        writable.close()

def export_views(kind: str, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    base, db, config = _config_for(kind, project_root, global_root)
    _check_project_git_write(db)
    refresh_views(base, db, config, None)
    return {"status": "exported", "scope": kind, "views": str(base / "views")}

def backup_store(kind: str, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    base, db_path, _ = _config_for(kind, project_root, global_root)
    _check_project_git_write(db_path)
    directory = base / "backups"
    if directory.is_symlink():
        raise MemoryError("path_escape", "Backup directory cannot be a symlink.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + new_id()[:8] + ".sqlite3"
    target = directory / filename
    source = _connect(db_path, readonly=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
        check = destination.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            target.unlink(missing_ok=True)
            raise MemoryError("backup_failed", "Consistent SQLite backup failed integrity check.")
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise MemoryError("backup_failed", "Consistent SQLite backup failed.") from exc
    finally:
        destination.close()
        source.close()
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return {"status": "saved", "scope": kind, "backup": str(target)}

def _forget_targets(conn: sqlite3.Connection, memory_id: str) -> list[tuple[str, int, str]]:
    exists = conn.execute("SELECT 1 FROM memories WHERE id=?", (memory_id,)).fetchone()
    if not exists:
        raise MemoryError("not_found", "Memory record was not found.")
    alias_sql = ""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='merged_aliases'").fetchone():
        alias_sql = "UNION SELECT e.canonical_id FROM merged_aliases e JOIN affected a ON e.source_id=a.id UNION SELECT e.source_id FROM merged_aliases e JOIN affected a ON e.canonical_id=a.id"
    rows = conn.execute(
        f"""WITH RECURSIVE affected(id) AS (
             SELECT ?
             UNION
             SELECT e.summary_id FROM derived_edges e JOIN affected a ON e.source_id=a.id
             {alias_sql}
           )
           SELECT m.id,m.revision,m.title FROM memories m JOIN affected a ON a.id=m.id""",
        (memory_id,),
    ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]

def _forget_token(namespace_id: str, kind: str, targets: list[tuple[str, int, str]]) -> str:
    basis = json.dumps([namespace_id, kind, sorted((memory_id, revision) for memory_id, revision, _ in targets)], separators=(",", ":"))
    return hashlib.sha256(("dev-memory-forget-v1:" + basis).encode("utf-8")).hexdigest()

def forget_preview(kind: str, memory_id: str, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    _, db, config = _config_for(kind, project_root, global_root)
    conn = _connect(db, readonly=True)
    targets = _forget_targets(conn, memory_id)
    record = conn.execute("SELECT promoted_global_ids FROM memories WHERE id=?", (memory_id,)).fetchone()
    try:
        promoted = json.loads(record[0] or "[]")
    except (TypeError, json.JSONDecodeError):
        promoted = []
    conn.close()
    return {
        "status": "preview", "scope": kind, "target_id": memory_id,
        "records": [{"id": i, "revision": rev, "title": title} for i, rev, title in targets],
        "promoted_global_ids": promoted,
        "confirmation_token": _forget_token(config["namespace_id"], kind, targets),
        "note": "Host transcripts, user-managed copies, Git history, and system snapshots are outside this tool.",
    }

def _delete_ids(conn: sqlite3.Connection, ids: Iterable[str]) -> None:
    for memory_id in ids:
        row = conn.execute("SELECT revision FROM memories WHERE id=?", (memory_id,)).fetchone()
        if not row:
            continue
        _invalidate_derived(conn, memory_id)
        conn.execute("INSERT OR REPLACE INTO forgotten(memory_id,revision,forgotten_at) VALUES(?,?,?)",
                     (memory_id, row[0], utc_now()))
        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))

def forget_apply(kind: str, memory_id: str, confirmation_token: str, *, project_root: Path | None = None,
                 global_root: Path | None = None) -> dict[str, Any]:
    base, db, config = _config_for(kind, project_root, global_root)
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        targets = _forget_targets(conn, memory_id)
        actual_token = _forget_token(config["namespace_id"], kind, targets)
        if not hmac.compare_digest(actual_token, confirmation_token):
            conn.rollback()
            raise MemoryError("revision_conflict", "Deletion preview is stale; preview again.")
        ids = [item[0] for item in targets]
        _delete_ids(conn, ids)
        conn.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='data_revision'")
        conn.commit()
    finally:
        conn.close()
    backup_errors = []
    backup_dir = base / "backups"
    if backup_dir.is_dir() and not backup_dir.is_symlink():
        for backup in backup_dir.glob("*.sqlite3"):
            bconn = None
            try:
                if backup.is_symlink():
                    backup_errors.append(backup.name)
                    continue
                bconn = sqlite3.connect(backup, timeout=2)
                bconn.execute("PRAGMA foreign_keys=ON")
                metadata = dict(bconn.execute("SELECT key,value FROM meta WHERE key IN ('namespace_id','storage_kind')"))
                if metadata.get("namespace_id") != config["namespace_id"] or metadata.get("storage_kind") != kind:
                    backup_errors.append(backup.name)
                    continue
                _delete_ids(bconn, ids)
                bconn.commit()
            except sqlite3.Error:
                backup_errors.append(backup.name)
            finally:
                if bconn is not None:
                    bconn.close()
    result = {"status": "forgotten", "scope": kind, "deleted_ids": ids}
    view_errors = _clear_generated_views(base)
    result["view_status"] = "cleanup_incomplete" if view_errors else "removed_until_export"
    if view_errors:
        result["view_cleanup_incomplete"] = view_errors
    if backup_errors:
        result["backup_cleanup_incomplete"] = backup_errors
    return result

def restore_store(kind: str, backup_path: Path, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    base, db_path, config = _config_for(kind, project_root, global_root)
    backup_dir = (base / "backups").resolve()
    if backup_path.is_symlink():
        raise MemoryError("path_escape", "Restore backup cannot be a symlink.")
    source_path = backup_path.expanduser().resolve()
    if source_path.parent != backup_dir or not source_path.is_file():
        raise MemoryError("path_escape", "Restore only accepts a backup inside this scope's managed backups directory.")
    conn = _connect(db_path)
    try:
        conn.execute("ATTACH DATABASE ? AS restore_source", (str(source_path),))
        current_ns = conn.execute("SELECT value FROM meta WHERE key='namespace_id'").fetchone()
        backup_ns = conn.execute("SELECT value FROM restore_source.meta WHERE key='namespace_id'").fetchone()
        integrity = conn.execute("PRAGMA restore_source.integrity_check").fetchone()
        if not current_ns or not backup_ns or current_ns[0] != backup_ns[0] or current_ns[0] != config["namespace_id"]:
            raise MemoryError("namespace_mismatch", "Backup namespace does not match this store.")
        if not integrity or integrity[0] != "ok":
            raise MemoryError("backup_corrupt", "Backup integrity check failed.")
        forgotten = conn.execute("SELECT memory_id,revision,forgotten_at FROM forgotten").fetchall()
        private_receipts = conn.execute("SELECT idempotency_key,session_id,turn_id,status,checked_at,result_json,payload_hash FROM receipts WHERE status='skipped_private'").fetchall()
        previous_revision = data_revision(db_path)
        conn.execute("BEGIN IMMEDIATE")
        for table in ("maintenance_pending", "merged_aliases", "session_context", "session_bindings", "receipts", "revisions", "evidence", "search_terms", "derived_edges", "memories", "meta", "forgotten"):
            conn.execute(f"DELETE FROM main.{table}")
        for table in ("meta", "memories", "evidence", "revisions", "search_terms", "derived_edges", "receipts", "session_bindings", "session_context", "forgotten", "merged_aliases", "maintenance_pending"):
            current_cols = [row[1] for row in conn.execute(f"PRAGMA main.table_info({table})")]
            source_cols = {row[1] for row in conn.execute(f"PRAGMA restore_source.table_info({table})")}
            if not source_cols:
                continue
            columns = ",".join(f'"{col}"' for col in current_cols if col in source_cols)
            conn.execute(f"INSERT INTO main.{table} ({columns}) SELECT {columns} FROM restore_source.{table}")
        conn.executemany("INSERT OR REPLACE INTO receipts(idempotency_key,session_id,turn_id,status,checked_at,result_json,payload_hash) VALUES(?,?,?,?,?,?,?)", private_receipts)
        conn.execute("DELETE FROM session_context")
        for (memory_id,) in conn.execute("SELECT id FROM memories").fetchall():
            record = _select_record(conn, memory_id)
            conn.execute("UPDATE memories SET semantic_hash=? WHERE id=?", (_semantic_hash(record), memory_id))
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('semantic_hash_format','3')")
        for memory_id, revision, forgotten_at in forgotten:
            _delete_ids(conn, [memory_id])
            conn.execute("INSERT OR REPLACE INTO forgotten(memory_id,revision,forgotten_at) VALUES(?,?,?)",
                         (memory_id, revision, forgotten_at))
        _ensure_maintenance(conn)
        conn.execute("UPDATE meta SET value=MAX(CAST(value AS INTEGER),?)+1 WHERE key='data_revision'", (previous_revision,))
        conn.commit()
    except MemoryError:
        conn.rollback()
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise MemoryError("restore_failed", "Could not restore the selected same-scope backup safely.") from exc
    finally:
        try:
            conn.execute("DETACH DATABASE restore_source")
        except sqlite3.Error:
            pass
        conn.close()
    cleanup = _clear_generated_views(base)
    return {"status": "restored", "scope": kind, "forgotten_ids_suppressed": [row[0] for row in forgotten],
            "view_status": "cleanup_incomplete" if cleanup else "removed_until_export", "view_cleanup_incomplete": cleanup}

def set_capture(kind: str, enabled: bool, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    if kind == "project":
        base, _, _ = _config_for(kind, project_root, global_root)
    else:
        base, _, _ = _config_for("global", None, global_root)
    path = base / "config.json"
    config = read_json(path)
    config["capture_enabled"] = bool(enabled)
    config["updated_at"] = utc_now()
    write_json_atomic(path, config)
    return {"status": "updated", "scope": kind, "capture_enabled": bool(enabled)}

def get_store_status(kind: str, *, project_root: Path | None = None, global_root: Path | None = None) -> dict[str, Any]:
    try:
        base, db, config = _config_for(kind, project_root, global_root)
        conn = _connect(db, readonly=True)
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE status IN ('active','conflicted','candidate')").fetchone()[0]
        revisions = {row[0]: row[1] for row in conn.execute("SELECT key,value FROM meta WHERE key IN ('data_revision','view_revision')")}
        conn.close()
        current_revision = int(revisions.get("data_revision", 0))
        view_revision = int(revisions["view_revision"]) if "view_revision" in revisions else None
        return {
            "scope": kind, "status": "available" if integrity == "ok" else "corrupt",
            "database_exists": True, "readable": True, "writable": os.access(base, os.W_OK),
            "capture_enabled": config.get("capture_enabled", True) and config.get("excluded") is not True,
            "recall_enabled": config.get("recall_enabled", True) and config.get("excluded") is not True,
            "excluded": config.get("excluded") is True,
            "namespace_id": config["namespace_id"], "data_revision": current_revision, "active_count": count,
            "view_revision": view_revision,
            "view_status": "current" if view_revision == current_revision else ("not_exported" if view_revision is None else "stale"),
            "integrity": integrity,
        }
    except MemoryError as exc:
        return {"scope": kind, "status": "unavailable", "reason": exc.code}
    except (sqlite3.Error, OSError, ValueError):
        return {"scope": kind, "status": "unavailable", "reason": "storage_unavailable"}

def config_path_for(kind: str, root: Path | None = None, global_root: Path | None = None) -> Path:
    base = project_paths(root)[0] if kind == "project" and root else global_paths(global_root)[0]
    return base / "config.json"

def consolidate_sources(kind: str, source_ids: list[str], *, project_root: Path | None = None,
                        global_root: Path | None = None) -> dict[str, Any]:
    if not source_ids or len(set(source_ids)) != len(source_ids):
        raise MemoryError("validation_error", "Provide unique source record IDs.")
    _, db, config = _config_for(kind, project_root, global_root)
    conn = _connect(db, readonly=True)
    records = []
    for memory_id in source_ids:
        record = _select_record(conn, memory_id)
        if not record or record["namespace_id"] != config["namespace_id"] or record["scope"] == "task":
            conn.close()
            raise MemoryError("scope_error", "Consolidation sources must be existing records from this same namespace.")
        records.append(_context_record(record))
    conn.close()
    return {"status": "prepare", "scope": kind, "namespace_id": config["namespace_id"], "sources": records,
            "instruction": "Return a proposed summary preserving conditions, exceptions, negative constraints, and source revisions; do not write until reviewed."}

#!/usr/bin/env python3
"""CLI entry point for dev-memory. Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import dev_memory_store as store
import dev_memory_setup as activation

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
MARKER = ".dev-memory-skill-install"
SKILL_FILES = [
    "SKILL.md", "LICENSE", MARKER,
    "agents/openai.yaml", "assets/config.example.json",
    "references/protocol.md", "references/codex-hooks.md", "references/verification.md",
    "references/setup.md",
    "scripts/dev_memory.py", "scripts/dev_memory_store.py", "scripts/dev_memory_setup.py", "scripts/codex_hook.py", "scripts/dev-memory",
]
RELEASE_FILES = [*("skills/dev-memory/" + name for name in SKILL_FILES),
    "README.md", "LICENSE", ".gitignore", "install.py", "package.json", "bin/install.cjs", "CONTRIBUTING.md", "SECURITY.md",
    "docs/installation.md", "docs/ecosystem.md", "docs/architecture.md",
    "docs/readme/README.zh-CN.md", "docs/readme/README.ja.md", "docs/readme/README.ko.md",
    "tests/test_dev_memory.py", "tests/test_maintenance.py", "tests/test_lifecycle.py", "tests/test_adversarial.py", "tests/test_installer.py", "tests/test_setup.py", "tests/test_online_installer.py", "tests/test_npx_installer.py", "tests/install_smoke.py", "evals/scenarios.json", "evals/bench_compare.py", "evals/check_automatic.py", "evals/check_maintenance.py", "evals/check_lifecycle.py",
    "reports/verification.md", "reports/adversarial-review.md", "reports/maintenance-host.json", "reports/maintenance-benchmark.json", "reports/maintenance-installation.json", "reports/lifecycle-review.md", "reports/lifecycle-host.json", "reports/lifecycle-benchmark.json", "build_release.py",
    "reports/online-installation.json", "reports/npx-installation.json", "reports/npx-upgrade.json", "reports/automatic-onboarding.json", "reports/install-smoke.json", "reports/benchmark-2026-10-11.json", "reports/benchmark-0.7.0.md", "reports/project-isolation-demo.json",
    ".github/workflows/check.yml", "plugin.json", "evals/check_deepseek.py", "reports/deepseek.json", "reports/windows-access.json", "reports/multi-project-review.md", "reports/memory-cycle-review.md",
]
AGENT_DIRS = {"codex": ".agents/skills", "claude-code": ".claude/skills", "cursor": ".cursor/skills",
              "gemini-cli": ".gemini/skills", "github-copilot": ".copilot/skills", "opencode": ".config/opencode/skills",
              "deepseek-harness": ".dsh/skills"}
CODEX_EVENTS = ("SessionStart", "UserPromptSubmit", "Stop")

def _json_out(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))

def _die(code: str, message: str, status: int = 2) -> None:
    _json_out({"status": "failed", "error": code, "message": message})
    raise SystemExit(status)

def _scope_root(args: argparse.Namespace) -> tuple[str, Path | None]:
    scope = getattr(args, "scope", None)
    root_arg = getattr(args, "project_root", None)
    root = store.locate_project_root(Path.cwd(), root_arg) if root_arg else store.locate_project_root(Path.cwd())
    if scope in {"project", "task"} and root is None:
        raise store.MemoryError("project_root_required", "Use --project-root or run inside a Git worktree.")
    return scope, root

def _git_info(root: Path) -> dict[str, Any]:
    def run(args: list[str]) -> str | None:
        try:
            p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=2)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return {"branch": run(["branch", "--show-current"]), "commit_id": run(["rev-parse", "--short=12", "HEAD"])}

def _module_label(root: Path | None) -> str | None:
    if root is None:
        return None
    try:
        label = Path.cwd().resolve().relative_to(root.resolve()).as_posix()
        return "" if label == "." else label
    except ValueError:
        return None

def _hook_installed(hooks_file: Path) -> bool:
    try:
        config = json.loads(hooks_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(config, dict) or not isinstance(config.get("hooks"), dict):
        return False
    return any(
        isinstance(handler, dict) and handler.get("command") == _hook_command(PACKAGE_ROOT)
        for event in config["hooks"].values() if isinstance(event, list)
        for group in event if isinstance(group, dict)
        for handler in group.get("hooks", []) if isinstance(group.get("hooks", []), list)
    )

def _codex_version() -> dict[str, Any]:
    executable = shutil.which("codex")
    if not executable:
        return {"available": False}
    try:
        result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=3)
        version = (result.stdout or result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        version = None
    return {"available": bool(version), "version": version}

def _skill_locations() -> dict[str, bool]:
    return {
        "user": (Path.home() / ".agents" / "skills" / "dev-memory").is_dir(),
        "admin": (Path("/etc/codex/skills/dev-memory")).is_dir(),
        "legacy_codex_skills_directory": (Path.home() / ".codex" / "skills" / "dev-memory").is_dir(),
    }

def doctor(project_root: Path | None, global_root: Path | None) -> dict[str, Any]:
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    hooks_file = home / "hooks.json"
    config_file = home / "config.toml"
    version = _codex_version()
    config_text = ""
    try:
        config_text = config_file.read_text(encoding="utf-8")
    except OSError:
        pass
    features_hooks = bool(re.search(r"(?ms)^\[features\][^\[]*?^\s*hooks\s*=\s*true\s*$", config_text))
    configured = _hook_installed(hooks_file)
    stores = {
        "global": store.get_store_status("global", global_root=global_root),
        "project": store.get_store_status("project", project_root=project_root, global_root=global_root) if project_root else {"status": "not_bound"},
    }
    usable = [value for value in stores.values() if value.get("status") == "available" and value.get("recall_enabled", True)]
    writable_capture = [value for value in usable if value.get("capture_enabled", True)]
    automatic_candidate = configured and features_hooks
    if not usable:
        mode = "unavailable"
    elif not writable_capture:
        mode = "read_only"
    elif automatic_candidate:
        mode = "automatic_unverified"
    else:
        mode = "base"
    project_git = None
    if project_root:
        info = _git_info(project_root)
        gitdir = subprocess.run(["git", "-C", str(project_root), "rev-parse", "--git-path", "info/exclude"],
                                capture_output=True, text=True) if shutil.which("git") else None
        ignored = subprocess.run(["git", "-C", str(project_root), "check-ignore", "-q", "--", ".dev-memory/"],
                                 capture_output=True) if shutil.which("git") else None
        project_git = {
            "branch": info["branch"], "commit_id": info["commit_id"],
            "tracked_memory_path": bool(subprocess.run(["git", "-C", str(project_root), "ls-files", "--", ".dev-memory"],
                capture_output=True, text=True).stdout.strip()) if shutil.which("git") else False,
            "local_exclude_check": "ignored" if ignored and ignored.returncode == 0 else "not_ignored_or_not_git",
            "exclude_path_available": bool(gitdir and gitdir.returncode == 0),
        }
    project_activation = activation.status(project_root)
    if mode == "base" and project_activation["status"] == "configured":
        mode = "project_guided"
    return {
        "status": "ok", "python": sys.version.split()[0], "python_minimum": "3.10",
        "sqlite": sqlite3.sqlite_version, "git_version": _command_version("git", ["--version"]),
        "codex_cli": version, "codex_hooks_feature_enabled": features_hooks,
        "hook_configured": configured, "hook_trust": "unknown; Codex requires review via /hooks",
        "mode": mode, "automatic_mode": "configured_but_unverified" if automatic_candidate else "not_configured",
        "base_mode": "available",
        "skill_discovery": _skill_locations(),
        "global_data_default": str(store.global_paths(global_root)[0]),
        "project_data_default": str(project_root / ".dev-memory") if project_root else "unbound",
        "stores": stores, "git": project_git,
        "read_only": True, "project_activation": project_activation,
        "real_host_e2e_verified": False,
    }

def context(query: str = '', *, project_root: Path | None = None, global_root: Path | None = None,
            task_id: str | None = None, session_id: str | None = None, module: str | None = None,
            turn_id: str | None = None,
            max_candidates: int = 20, max_details: int = 5, max_chars: int = 4000,
            force: bool = False, readonly: bool = False, resume: bool = False,
            include_task: bool = True) -> dict[str, Any]:
    """One normal startup call: bounded recall and pending check, no host probes/init."""
    result = store.recall(query, project_root=project_root, global_root=global_root, task_id=task_id,
                          session_id=session_id, module=module, max_candidates=max_candidates,
                          max_details=max_details, max_chars=max_chars, force=force, readonly=readonly, resume=resume,
                          include_task=include_task)
    for bucket in result['stores']:
        if readonly:
            bucket['maintenance'] = {'status': 'not_requested_readonly'}
        elif bucket['status'] in {'unavailable', 'disabled', 'deferred'}:
            bucket['maintenance'] = {'status': 'not_requested_unavailable'}
        else:
            try:
                bucket['maintenance'] = store.maintenance_prepare(bucket['scope'], project_root=project_root, global_root=global_root,
                                                                  session_id=session_id, turn_id=turn_id,
                                                                  include_task=include_task)
            except (store.MemoryError, sqlite3.Error, OSError):
                bucket['maintenance'] = {'status': 'deferred', 'reason': 'storage_unavailable'}
    project_activation = activation.status(project_root)
    result['activation'] = project_activation
    result['mode'] = 'read_only' if readonly else ('project_guided' if project_activation['status'] == 'configured' else 'base')
    if all(b['status'] in {'unavailable', 'disabled'} for b in result['stores']):
        result['mode'] = 'unavailable'
    return result


def _command_version(binary: str, args: list[str]) -> str | None:
    if not shutil.which(binary):
        return None
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=2)
        return (result.stdout or result.stderr).strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()

def _inline_hooks_present(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return bool(re.search(r"(?m)^\s*\[hooks\.(?:SessionStart|UserPromptSubmit|Stop|PreCompact|PostCompact|Interrupt|SessionEnd)\]\s*$", text))

def _hook_command(target: Path) -> str:
    script = (target / "scripts" / "codex_hook.py").resolve()
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"

def _hook_config(target: Path) -> dict[str, Any]:
    command = _hook_command(target)
    def handler(limit: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "command", "command": command, "timeout": 2}
        if limit is not None:
            result["additionalContextLimit"] = limit
        return result
    return {
        "SessionStart": [{"matcher": "startup|resume|compact", "hooks": [handler(1200)]}],
        "UserPromptSubmit": [{"hooks": [handler(1200)]}],
        "Stop": [{"hooks": [handler()]}],
    }

def _merge_hook_config(target: Path) -> dict[str, Any]:
    home = _codex_home()
    hook_file = home / "hooks.json"
    config_file = home / "config.toml"
    if _inline_hooks_present(config_file):
        raise store.MemoryError("config_conflict", "Inline Codex hooks exist; merge this adapter there manually to avoid duplicate hook sources.")
    if hook_file.is_symlink():
        raise store.MemoryError("path_escape", "Codex hooks.json cannot be a symlink.")
    if hook_file.exists():
        try:
            data = json.loads(hook_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise store.MemoryError("config_invalid", "Codex hooks.json is unreadable or invalid; no changes were made.") from exc
    else:
        data = {}
    if not isinstance(data, dict):
        raise store.MemoryError("config_invalid", "Codex hooks.json must contain an object.")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise store.MemoryError("config_invalid", "Codex hooks must be an object.")
    command = _hook_command(target)
    for event, groups in _hook_config(target).items():
        old = hooks.setdefault(event, [])
        if not isinstance(old, list):
            raise store.MemoryError("config_invalid", "A Codex hook event must contain a list.")
        if any(isinstance(g, dict) and any(isinstance(h, dict) and h.get("command") == command for h in g.get("hooks", [])) for g in old):
            continue
        old.extend(groups)
    store.write_json_atomic(hook_file, data)
    return {"path": str(hook_file), "status": "configured_requires_review"}

def _remove_hook_config(target: Path) -> dict[str, Any]:
    hook_file = _codex_home() / "hooks.json"
    if not hook_file.exists():
        return {"status": "absent"}
    if hook_file.is_symlink():
        raise store.MemoryError("path_escape", "Codex hooks.json cannot be a symlink.")
    try:
        data = json.loads(hook_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise store.MemoryError("config_invalid", "Codex hooks.json is invalid; refusing to rewrite it.") from exc
    script = str((target / "scripts" / "codex_hook.py").resolve())
    if not isinstance(data, dict):
        raise store.MemoryError("config_invalid", "Codex hooks.json must contain an object.")
    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        raise store.MemoryError("config_invalid", "Codex hooks must be an object; refusing to rewrite it.")
    removed = 0
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue  # Unknown schemas belong to the host or another integration.
        kept_groups = []
        for group in groups if isinstance(groups, list) else []:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = []
            for handler in group["hooks"]:
                command = handler.get("command", "") if isinstance(handler, dict) else ""
                try:
                    tokens = shlex.split(command)
                    owns_handler = (handler.get("type") == "command" and len(tokens) == 2 and tokens[1] == script
                                    and Path(tokens[0]).name.startswith("python"))
                except (ValueError, TypeError, AttributeError):
                    owns_handler = False
                if owns_handler:
                    removed += 1
                else:
                    kept.append(handler)
            if kept:
                group = {**group, "hooks": kept}
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            hooks.pop(event, None)
    if not hooks:
        data.pop("hooks", None)
    if removed:
        store.write_json_atomic(hook_file, data)
    return {"status": "removed", "handlers_removed": removed, "path": str(hook_file)}

def _copy_release(target: Path) -> None:
    missing = [name for name in SKILL_FILES if not (PACKAGE_ROOT / name).is_file()]
    if missing:
        raise store.MemoryError("package_incomplete", "Cannot install: release files are missing.")
    # Windows treats 0700 as an owner/admin-only ACL, hiding public Skill code
    # from legitimate sandbox identities. Inherit the program parent's ACL;
    # private memory storage keeps its separate restrictive policy.
    program_mode = 0o755 if sys.platform == "win32" else 0o700
    target.mkdir(parents=True, exist_ok=False, mode=program_mode)
    for name in SKILL_FILES:
        src, dst = PACKAGE_ROOT / name, target / name
        if not src.resolve().is_relative_to(PACKAGE_ROOT.resolve()):
            raise store.MemoryError("path_escape", "Release file path escaped package root.")
        dst.parent.mkdir(parents=True, exist_ok=True, mode=program_mode)
        shutil.copyfile(src, dst)
        if sys.platform != "win32":
            try:
                os.chmod(dst, 0o700 if name.endswith(".py") or name.endswith("/dev-memory") else 0o600)
            except OSError:
                pass

def _install_path(target: Path | None, agent: str = "codex") -> Path:
    default = (Path(os.environ.get("DSH_HOME") or str(Path.home() / ".dsh")) / "skills" / "dev-memory"
               if agent == "deepseek-harness" else Path.home() / AGENT_DIRS[agent] / "dev-memory")
    path = (target or default).expanduser().absolute()
    if path.is_symlink() or any(p.name == ".dev-memory" for p in (path, *path.parents)):
        raise store.MemoryError("path_escape", "Install target cannot be a symlink or a memory-data path.")
    path = path.resolve()
    if any(p.name == ".dev-memory" for p in (path, *path.parents)):
        raise store.MemoryError("path_escape", "Resolved installation cannot be in a memory-data path.")
    if path in {Path(path.anchor), Path.home().resolve()}:
        raise store.MemoryError("path_escape", "Install target cannot be the home or filesystem root.")
    return path

def _check_managed_install(path: Path) -> None:
    marker = path / MARKER
    if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != "dev-memory-managed-install-v1":
        raise store.MemoryError("unmanaged_install", "Target is not a dev-memory-managed installation.")
    allowed = set(SKILL_FILES)
    # Preserve compatibility with the former all-in-one managed release layout.
    allowed.update({"README.md", "LICENSE.pending", "build_release.py", "templates/config.example.json",
                    "tests/test_dev_memory.py", "evals/scenarios.json", "evals/bench_compare.py", "evals/check_automatic.py", "reports/verification.md"})
    allowed_dirs = {parent.as_posix() for name in allowed for parent in Path(name).parents if str(parent) != "."}
    for entry in path.rglob("*"):
        rel = entry.relative_to(path).as_posix()
        if entry.is_symlink() or not entry.resolve().is_relative_to(path.resolve()):
            raise store.MemoryError("path_escape", "Managed installation contains a link or escaped path; inspect it before removal.")
        bytecode = "__pycache__" in entry.parts and (entry.is_dir() or entry.suffix == ".pyc")
        if not bytecode and rel not in (allowed_dirs if entry.is_dir() else allowed):
            raise store.MemoryError("unmanaged_files", "Installation contains extra files; move or review them before upgrade/removal.")

@contextmanager
def _installation_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name("." + path.name + ".dev-memory-install.lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise store.MemoryError("installation_busy", "Another install/removal is running, or a stale installation lock needs inspection.") from exc
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _release_version(path: Path) -> tuple[int, ...] | None:
    skill = path / "SKILL.md"
    if not skill.is_file():
        return None
    match = re.search(r'(?m)^\s+version:\s*"(\d+\.\d+\.\d+)"\s*$', skill.read_text(encoding="utf-8"))
    return tuple(map(int, match[1].split("."))) if match else None


def install(target: Path | None, with_hooks: bool, upgrade: bool, agent: str = "codex") -> dict[str, Any]:
    install_path = _install_path(target, agent)
    if with_hooks and agent != "codex":
        raise store.MemoryError("host_mismatch", "Codex hooks can only be requested for a Codex installation.")
    with _installation_lock(install_path):
        return _install_locked(install_path, with_hooks, upgrade)


def _install_locked(install_path: Path, with_hooks: bool, upgrade: bool) -> dict[str, Any]:
    version = _release_version(PACKAGE_ROOT)
    action = "installed"
    if install_path.exists():
        _check_managed_install(install_path)
        installed_version = _release_version(install_path)
        if version and installed_version and installed_version > version:
            raise store.MemoryError("source_older", "Installer source is older than the installed Skill; fetch the current source instead of downgrading.")
        same = all((install_path / name).is_file() and (PACKAGE_ROOT / name).is_file()
                   and (install_path / name).read_bytes() == (PACKAGE_ROOT / name).read_bytes()
                   for name in SKILL_FILES)
        action = "reused" if same and not upgrade else "updated"
    cleanup = "not_needed"
    if action != "reused":
        temp_target = Path(tempfile.mkdtemp(prefix=".dev-memory-install-", dir=install_path.parent))
        temp_target.rmdir()
        try:
            _copy_release(temp_target)
            if install_path.exists():
                old = install_path.with_name(install_path.name + ".old-" + store.new_id()[:8])
                install_path.rename(old)
                try:
                    temp_target.rename(install_path)
                except OSError:
                    old.rename(install_path)
                    raise
                try:
                    shutil.rmtree(old)
                    cleanup = "removed"
                except OSError:
                    cleanup = "pending:" + old.name
            else:
                temp_target.rename(install_path)
        except Exception:
            shutil.rmtree(temp_target, ignore_errors=True)
            raise
    if with_hooks:
        try:
            hook_status = _merge_hook_config(install_path)
        except store.MemoryError as exc:
            hook_status = {"status": "failed", "error": exc.code, "message": exc.message,
                           "skill_installed": True}
    else:
        hook_status = {"status": "not_requested"}
    return {"status": "installed", "path": str(install_path), "data_preserved": True, "hooks": hook_status,
            "program_action": action, "program_version": ".".join(map(str, version)) if version else None,
            "old_program_cleanup": cleanup,
            "program_permissions": "unchanged" if action == "reused" else ("inherited_windows_acl" if sys.platform == "win32" else "private_posix_modes"),
            "sandbox_access_verified": False}

def uninstall(target: Path | None, agent: str = "codex") -> dict[str, Any]:
    install_path = _install_path(target, agent)
    with _installation_lock(install_path):
        _check_managed_install(install_path)
        user_activation = activation.remove_user(agent, install_path)
        hooks = _remove_hook_config(install_path)
        shutil.rmtree(install_path)
    return {"status": "uninstalled", "path": str(install_path), "memory_data_preserved": True,
            "user_activation": user_activation, "hooks": hooks}

def _scope_arg(args: argparse.Namespace) -> tuple[str, Path | None]:
    scope = args.scope
    if scope not in {"global", "project", "task"}:
        raise store.MemoryError("scope_error", "Use global, project, or task for this command.")
    root = store.locate_project_root(Path.cwd(), args.project_root) if getattr(args, "project_root", None) else store.locate_project_root(Path.cwd())
    if scope in {"project", "task"} and root is None:
        raise store.MemoryError("project_root_required", "Use --project-root or run inside a Git worktree.")
    return scope, root

def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read(1_000_001)
    if len(raw) > 1_000_000:
        raise store.MemoryError("validation_error", "Structured apply input exceeds the 1 MB limit.")
    if not raw.strip():
        raise store.MemoryError('validation_error', 'Supply structured JSON on stdin using a quoted heredoc, or use --input with a scope-local JSON file; no input was submitted.')
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise store.MemoryError("validation_error", "Apply input is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise store.MemoryError("validation_error", "Apply input must be an object.")
    return payload

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev-memory", description="Private local R&D memory for development work.")
    parser.add_argument("--global-root", type=Path, help="Override global data root (or set DEV_MEMORY_HOME).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("doctor")
    p.add_argument("--project-root", type=Path)
    p = sub.add_parser("setup", help="Initialize this project and configure automatic host instructions")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--agent", choices=tuple(AGENT_DIRS), default="codex")
    p.add_argument("--user", action="store_true", help="Enable Codex user-level global habit recall across projects")
    p = sub.add_parser("mode", help="Set project memory capture mode")
    p.add_argument("capture_mode", choices=("developer-first", "full-project"))
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p = sub.add_parser("init")
    p.add_argument("--global", dest="init_global", action="store_true")
    p.add_argument("--project-root", type=Path)
    for name in ("recall", "context"):
        p = sub.add_parser(name)
        p.add_argument("--query", default="")
        p.add_argument("--resume", action="store_true", help="Include recent checkpoint candidates when continuing without a task ID")
        p.add_argument("--exclude-task", action="store_true", help="Exclude legacy task records from recall and context maintenance")
        p.add_argument("--project-root", type=Path)
        p.add_argument("--global-only", action="store_true", help="Use only the user global store, even inside a project")
        p.add_argument("--task-id")
        p.add_argument("--session-id")
        if name == 'context':
            p.add_argument("--turn-id", help="Suppress repeated maintenance packs and honor a turn opt-out")
        p.add_argument("--module")
        p.add_argument("--max-candidates", type=int, default=20)
        p.add_argument("--max-details", type=int, default=5)
        p.add_argument("--max-chars", type=int, default=4000)
        p.add_argument("--force", action="store_true")
        p.add_argument("--readonly", action="store_true")
    p = sub.add_parser("show")
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--id")
    group.add_argument("--ids", nargs="+")
    p.add_argument("--current", action="store_true", help="Current records only; omit evidence/revision audit history")
    p = sub.add_parser("list")
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p.add_argument("--status", default="active")
    p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("apply")
    p.add_argument("--project-root", type=Path)
    p.add_argument("--module")
    p.add_argument("--input", type=Path, help="Read structured JSON from file; stdin by default.")
    p = sub.add_parser("match", help="Read-only duplicate candidates before adding a record")
    p.add_argument("--project-root", type=Path)
    p.add_argument("--input", type=Path)
    p = sub.add_parser("maintain", help="Bounded changed-record maintenance preparation")
    p.add_argument("--scope", choices=("global", "project", "both"), default="both")
    p.add_argument("--project-root", type=Path)
    p.add_argument("--force", action="store_true", help="Review pending records below the threshold at a task boundary")
    p.add_argument("--session-id")
    p.add_argument("--turn-id")
    p = sub.add_parser("skip")
    p.add_argument("--scope", choices=("global", "project", "both"), default="project")
    p.add_argument("--project-root", type=Path)
    p.add_argument("--session-id", required=True)
    p.add_argument("--turn-id", required=True)
    p = sub.add_parser("consolidate")
    p.add_argument("action", choices=("prepare",))
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p.add_argument("--ids", nargs="+", required=True)
    p = sub.add_parser("export")
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p = sub.add_parser("forget")
    p.add_argument("action", choices=("preview", "apply"))
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p.add_argument("--id", required=True)
    p.add_argument("--confirm")
    p = sub.add_parser("backup")
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p = sub.add_parser("restore")
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p.add_argument("--backup", type=Path, required=True)
    p = sub.add_parser("capture")
    p.add_argument("action", choices=("on", "off", "readonly", "disable"))
    p.add_argument("--scope", required=True)
    p.add_argument("--project-root", type=Path)
    p = sub.add_parser("install")
    p.add_argument("--target", type=Path)
    p.add_argument("--agent", choices=tuple(AGENT_DIRS), default="codex")
    p.add_argument("--with-codex-hooks", action="store_true")
    p.add_argument("--upgrade", action="store_true")
    p = sub.add_parser("uninstall")
    p.add_argument("--target", type=Path)
    p.add_argument("--agent", choices=tuple(AGENT_DIRS), default="codex")
    p = sub.add_parser("hooks")
    p.add_argument("action", choices=("configure", "remove"))
    p.add_argument("--target", type=Path, default=PACKAGE_ROOT)
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        command = args.command
        global_root = args.global_root
        if command == "doctor":
            root = store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            _json_out(doctor(root, global_root))
        elif command == "setup":
            result = (activation.setup_user(args.agent, PACKAGE_ROOT, sys.executable, global_root) if args.user
                      else activation.setup(args.project_root, args.agent, PACKAGE_ROOT, sys.executable, global_root))
            _json_out(result)
            return 0 if result["status"] == "initialized" else 1
        elif command == "mode":
            root = store._reject_unsafe_project_root(args.project_root)
            base, _, config = store._config_for("project", root, global_root)
            config["capture_mode"] = args.capture_mode
            config["updated_at"] = store.utc_now()
            store.write_json_atomic(base / "config.json", config)
            _json_out({"status": "updated", "project_root": str(root), "capture_mode": args.capture_mode})
        elif command == "init":
            results = []
            if args.init_global:
                results.append(store.init_global(global_root))
            if args.project_root:
                results.append(store.init_project(args.project_root, capture_mode="developer-first"))
            if not results:
                _die("validation_error", "Use --global and/or --project-root PATH.")
            _json_out({"status": "initialized", "stores": results})
        elif command in {"recall", "context"}:
            root = None if args.global_only else store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            recall_func = context if command == "context" else store.recall
            _json_out(recall_func(
                args.query, project_root=root, global_root=global_root, task_id=args.task_id,
                session_id=args.session_id, module=args.module if args.module is not None else _module_label(root), max_candidates=args.max_candidates,
                max_details=args.max_details, max_chars=args.max_chars, force=args.force, readonly=args.readonly, resume=args.resume,
                include_task=not args.exclude_task,
                **({'turn_id':args.turn_id} if command == 'context' else {}),
            ))
        elif command == "show":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            result = store.show_current(scope, args.ids or [args.id], project_root=root, global_root=global_root) if args.current or args.ids else store.show_record(scope, args.id, project_root=root, global_root=global_root)
            store._ensure_not_sensitive(result)
            _json_out(result)
        elif command == "list":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            _json_out(store.list_records(scope, project_root=root, global_root=global_root,
                                         status=args.status, limit=args.limit))
        elif command == "apply":
            payload = json.loads(args.input.read_text(encoding="utf-8")) if args.input else _read_payload()
            root = store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            branch = _git_info(root) if root else {}
            payload.setdefault("branch", branch.get("branch"))
            payload.setdefault("commit_id", branch.get("commit_id"))
            if args.module:
                payload.setdefault("module", args.module)
            elif root:
                payload.setdefault("module", _module_label(root))
            result = store.apply_payload(payload, project_root=root, global_root=global_root)
            _json_out(result)
            return 2 if result["status"] == "failed" else (3 if result["status"] == "partial_success" else 0)
        elif command == "match":
            payload = json.loads(args.input.read_text(encoding="utf-8")) if args.input else _read_payload()
            root = store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            _json_out(store.match_payload(payload, project_root=root, global_root=global_root))
        elif command == "maintain":
            root = store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            kinds = ["global", "project"] if args.scope == "both" else [args.scope]
            results = []
            for kind in kinds:
                try:
                    results.append(store.maintenance_prepare(kind, project_root=root if kind == "project" else None,
                                                            global_root=global_root, force=args.force,
                                                            session_id=args.session_id, turn_id=args.turn_id))
                except (store.MemoryError, sqlite3.Error, OSError) as exc:
                    results.append({"scope": kind, "status": "failed", "error": getattr(exc, "code", "storage_unavailable")})
            failures = sum(r["status"] == "failed" for r in results)
            _json_out({"status": "failed" if failures == len(results) else ("partial_success" if failures else "ok"), "stores": results})
            return 2 if failures == len(results) else (3 if failures else 0)
        elif command == "skip":
            root = store.locate_project_root(Path.cwd(), str(args.project_root) if args.project_root else None)
            if root is None:
                raise store.MemoryError("project_root_required", "A project store is required to record a private skip.")
            _json_out(store.record_private_skip(args.scope, session_id=args.session_id, turn_id=args.turn_id,
                                                project_root=root, global_root=global_root))
        elif command == "consolidate":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            _json_out(store.consolidate_sources(scope, args.ids, project_root=root, global_root=global_root))
        elif command == "export":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            _json_out(store.export_views(scope, project_root=root, global_root=global_root))
        elif command == "forget":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            if args.action == "preview":
                _json_out(store.forget_preview(scope, args.id, project_root=root, global_root=global_root))
            elif not args.confirm:
                _die("confirmation_required", "Use forget preview, then pass its --confirm token to forget apply.")
            else:
                _json_out(store.forget_apply(scope, args.id, args.confirm, project_root=root, global_root=global_root))
        elif command == "backup":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            _json_out(store.backup_store(scope, project_root=root, global_root=global_root))
        elif command == "restore":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            _json_out(store.restore_store(scope, args.backup, project_root=root, global_root=global_root))
        elif command == "capture":
            scope, root = _scope_arg(args)
            if scope == "task":
                scope = "project"
            capture_enabled = args.action == "on"
            recall_enabled = args.action != "disable"
            if scope == "project":
                base, _, _ = store._config_for("project", root, global_root)
            else:
                base, _, _ = store._config_for("global", None, global_root)
            cfg_path = base / "config.json"
            cfg = store.read_json(cfg_path)
            cfg.update({"capture_enabled": capture_enabled, "recall_enabled": recall_enabled, "updated_at": store.utc_now()})
            store.write_json_atomic(cfg_path, cfg)
            _json_out({"status": "updated", "scope": scope, "capture_enabled": capture_enabled, "recall_enabled": recall_enabled})
        elif command == "install":
            _json_out(install(args.target, args.with_codex_hooks, args.upgrade, args.agent))
        elif command == "uninstall":
            _json_out(uninstall(args.target, args.agent))
        elif command == "hooks":
            _json_out(_merge_hook_config(args.target) if args.action == "configure" else _remove_hook_config(args.target))
        return 0
    except store.MemoryError as exc:
        _die(exc.code, exc.message)
    except (OSError, sqlite3.Error):
        _die("storage_unavailable", "The requested operation failed; no success was recorded.")
    except json.JSONDecodeError:
        _die("validation_error", "Invalid JSON input.")
    return 2

if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

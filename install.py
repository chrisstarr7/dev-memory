#!/usr/bin/env python3
"""Install dev-memory locally or online, with an explicit AI and runtime check."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ALIASES = {"claude": "claude-code", "gemini": "gemini-cli", "copilot": "github-copilot",
           "deepseek": "deepseek-harness", "dsh": "deepseek-harness"}


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", nargs="?", help="codex, claude, cursor, gemini, copilot, opencode, deepseek (DSH)")
    parser.add_argument("update_agent", nargs="?", help="AI to update: update codex")
    parser.add_argument("--agent", dest="agent_option", help="Compatible explicit AI selector")
    parser.add_argument("--project", type=Path, help="Initialize this project; Codex also enables user-level global habits")
    parser.add_argument("--target", type=Path, help="Custom Skill directory")
    parser.add_argument("--upgrade", action="store_true", help="Force rebuilding a managed installation; normal runs reuse/update automatically")
    parser.add_argument("--with-codex-hooks", action="store_true", help="Explicitly configure optional Codex hooks")
    parser.add_argument("--json", action="store_true", help="Structured result for automation")
    return parser


def parse_arguments(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    args.operation = "update" if args.agent == "update" else "install"
    if args.operation == "update":
        args.agent = args.update_agent
    elif args.update_agent:
        parser.error("额外的 AI 参数；更新请使用 update codex。")
    return args


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("需要 Python 3.10+。请使用 python3 或 Windows 的 py -3。", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent / "skills/dev-memory/scripts"))
    try:
        import sqlite3
        import dev_memory
        import dev_memory_store as store
    except ImportError:
        print("运行环境不完整：需要包含 sqlite3 的 Python，以及完整的仓库文件。", file=sys.stderr)
        return 2
    try:
        sqlite3.connect(":memory:").close()
    except sqlite3.Error:
        print("sqlite3 不可用，请修复 Python 运行环境后重试。", file=sys.stderr)
        return 2

    parser = argument_parser()
    args = parse_arguments(parser, argv)
    agent = ALIASES.get(args.agent or "", args.agent)
    option = ALIASES.get(args.agent_option or "", args.agent_option)
    if agent and option and agent != option:
        parser.error("两个 AI 参数不一致。")
    agent = agent or option
    if not agent:
        if args.operation == "update":
            parser.error("请指定更新的 AI，例如 update codex。")
        if args.json or not sys.stdin.isatty():
            parser.error("请指定 AI，例如 python3 install.py codex；非交互环境不会猜测安装目录。")
        choices = list(dev_memory.AGENT_DIRS)
        print("选择要安装的 AI：")
        for number, value in enumerate(choices, 1):
            print(f"  {number}. {value}")
        try:
            selected = input("输入编号或 AI 名称：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消安装。", file=sys.stderr)
            return 130
        if selected in map(str, range(1, len(choices) + 1)):
            agent = choices[int(selected) - 1]
        else:
            agent = ALIASES.get(selected, selected)
    if agent not in dev_memory.AGENT_DIRS:
        parser.error("未知 AI；可选：" + ", ".join(dev_memory.AGENT_DIRS))
    enable_user = agent == "codex" and args.project is not None

    result: dict = {"operation": args.operation}
    phase = "preflight"
    global_root = store.default_global_root()
    refresh_project = args.project is not None
    try:
        # Codex project installation configures project and user-level guidance together.
        install_path = dev_memory._install_path(args.target, agent)
        if args.operation == "update":
            import dev_memory_setup
            if not install_path.is_dir():
                raise store.MemoryError("installation_missing", "未找到已安装的 Skill；首次安装请使用 AI 名称命令。")
            dev_memory._check_managed_install(install_path)
            refresh_project = False
            result["project_setup"] = {"status": "skipped", "reason": "not_bound"}
            if args.project:
                project = store._reject_unsafe_project_root(args.project)
                binding = dev_memory_setup._activation(project)["bindings"].get(agent)
                if binding is not None:
                    if (not isinstance(binding, dict)
                            or not isinstance(binding.get("skill_file"), str)
                            or Path(binding["skill_file"]).expanduser().resolve() != install_path / "SKILL.md"
                            or not isinstance(binding.get("cli"), str)
                            or Path(binding["cli"]).expanduser().resolve() != install_path / "scripts/dev_memory.py"
                            or not isinstance(binding.get("global_root"), str)):
                        raise store.MemoryError("binding_mismatch", "项目绑定不属于当前安装目录；未修改绑定。")
                    global_root = Path(binding["global_root"]).expanduser().resolve()
                    refresh_project = True
            enable_user = False
            if agent == "codex":
                user = dev_memory_setup.user_status(install_path)
                if user["status"] not in {"configured", "unavailable", "not_configured"}:
                    raise store.MemoryError("user_binding_unavailable", "已有用户绑定不可用；请检查绑定后重试。")
                enable_user = user["status"] in {"configured", "unavailable"}
                if enable_user:
                    user_root = Path(user["global_root"])
                    if refresh_project and user_root != global_root:
                        raise store.MemoryError("binding_mismatch", "项目和用户绑定使用不同全局库；未修改绑定。")
                    global_root = user_root
                else:
                    result["user_activation"] = {"status": "skipped", "reason": "not_bound"}
            # Updating guidance must never turn a missing store into a fresh one.
            bases = ([project / ".dev-memory"] if refresh_project else [])
            if refresh_project or enable_user:
                bases.append(global_root / "global")
            for base in bases:
                if not all((base / name).is_file() for name in ("config.json", "memory.sqlite3")):
                    raise store.MemoryError("store_unavailable", "绑定的记忆库不完整；更新不会创建新库，请先修复。")
            kinds = (["project"] if refresh_project else []) + (["global"] if refresh_project or enable_user else [])
            for kind in kinds:
                _, database, config = store._config_for(kind, project if refresh_project else None, global_root)
                connection = store._connect(database, readonly=True)
                try:
                    if not store._restorable_backup(connection, config, kind):
                        raise store.MemoryError("store_validation_failed", "已有记忆库结构或完整性校验失败；更新不会重建缺失表，请先恢复存储。")
                finally:
                    connection.close()
        if refresh_project:
            import dev_memory_setup
            project = store._reject_unsafe_project_root(args.project)
            guide = dev_memory_setup.guide_path(project, agent)
            dev_memory_setup._merged(guide.read_bytes() if guide.exists() else b"", agent)
            dev_memory_setup._activation(project)
        if enable_user:
            import dev_memory_setup
            _, guide = dev_memory_setup.user_guide_path(agent)
            dev_memory_setup._merge_user_guide(guide.read_bytes() if guide.exists() else b"",
                                               dev_memory_setup._user_block(install_path, sys.executable, global_root))
        phase = "program_install"
        result.update(dev_memory.install(args.target, args.with_codex_hooks,
                                         args.upgrade, agent))
        phase = "runtime_check"
        installed_cli = Path(result["path"]) / "scripts/dev_memory.py"
        check = subprocess.run([sys.executable, "-B", str(installed_cli), "runtime-check"],
                               capture_output=True, text=True, encoding="utf-8", timeout=10)
        diagnostic = json.loads(check.stdout) if check.returncode == 0 else {}
        if (not isinstance(diagnostic, dict) or diagnostic.get("status") != "ok"
                or diagnostic.get("base_mode") != "available"
                or not all(isinstance(diagnostic.get(key), str) for key in ("python", "sqlite"))):
            raise store.MemoryError("runtime_check_failed", "程序已安装，但轻量运行检查失败；请使用 --json 查看失败阶段。")
        result["runtime_check"] = {"status": "passed", "python": diagnostic["python"], "sqlite": diagnostic["sqlite"]}
        if refresh_project:
            phase = "project_setup"
            import dev_memory_setup
            setup = dev_memory_setup.setup(args.project, agent, Path(result["path"]), sys.executable, global_root)
            result["project_setup"] = setup
            if setup["status"] != "initialized":
                result.update(status="failed", error="project_setup_failed",
                              message="程序已安装，但项目初始化未完成；请检查各存储结果。")
        if enable_user and result["status"] == "installed":
            import dev_memory_setup
            phase = "user_activation"
            result["user_activation"] = dev_memory_setup.setup_user(agent, Path(result["path"]), sys.executable, global_root)
            if (result["user_activation"].get("status") != "initialized"
                    or result["user_activation"].get("activation") != "configured"):
                result.update(status="failed", error="user_activation_failed",
                              message="程序已安装，但 Codex 用户级指令未配置完成。")
        if result["hooks"]["status"] == "failed":
            result.update(status="failed", error="hook_configuration_failed",
                          message="Skill 文件已安装且基础检查通过，但可选 hooks 配置失败；请检查 hooks 结果。")
    except store.MemoryError as exc:
        result.update(status="failed", error=exc.code, message=exc.message)
    except subprocess.TimeoutExpired:
        result.update(status="failed", error="installation_phase_timeout",
                      message=f"{phase} 阶段超时；已返回的程序路径可能完成更新，记忆不会重置。")
    except sqlite3.Error:
        result.update(status="failed", error="store_validation_failed",
                      message="已有记忆库校验失败；未创建替代记忆库，请先检查存储完整性。")
    except PermissionError:
        result.update(status="failed", error="permission_denied",
                      message="程序或项目路径访问被拒绝；请检查普通用户与宿主权限。已有记忆不会转存到其他范围。")
    except (OSError, ValueError, subprocess.SubprocessError):
        result.update(status="failed", error="installation_check_failed",
                      message="安装或检查失败。若已返回 path，文件可能已安装；请从该目录运行 doctor 检查。")
    if result.get("status") == "failed":
        result["phase"] = phase
    report(result, args, agent)
    return 0 if result["status"] == "installed" else 1


def report(result: dict, args: argparse.Namespace, agent: str) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=True))
    elif result["status"] == "failed":
        print(("更新未完成：" if args.operation == "update" else "安装未完成：") + str(result.get("message", result.get("error", "安装检查失败。"))), file=sys.stderr)
        if result.get("phase"):
            print("失败阶段：" + result["phase"] + " (" + str(result.get("error", "unknown")) + ")", file=sys.stderr)
        if result.get("path"):
            print("程序目录：" + result["path"], file=sys.stderr)
        setup = result.get("project_setup")
        if isinstance(setup, dict):
            items = setup.get("stores", [])
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                print(f"{item.get('scope', 'store')}：{item.get('status', 'unknown')}"
                      + (f" ({item['error']})" if item.get('error') else ""), file=sys.stderr)
            print("项目引导：" + str(setup.get("activation", "unknown")), file=sys.stderr)
        user_setup = result.get("user_activation")
        if isinstance(user_setup, dict):
            print("Codex 用户级引导：" + str(user_setup.get("activation", "unknown")), file=sys.stderr)
        if result.get("error") == "source_older":
            operation = "update " if args.operation == "update" else ""
            print(f"获取最新版本：npx -y --prefer-online chrisstarr7/dev-memory#main {operation}{agent}", file=sys.stderr)
    else:
        print("更新成功；轻量运行检查通过。" if args.operation == "update" else "安装成功；轻量运行检查通过。")
        print("程序目录：" + result["path"])
        print("程序处理：" + str(result.get("program_action", "installed")))
        cleanup = result.get("old_program_cleanup", "")
        if isinstance(cleanup, str) and cleanup.startswith("pending:"):
            print("旧程序目录清理待完成：" + cleanup.split(":", 1)[1] + "；请在文件不再占用后清理该目录。")
        if args.operation == "update":
            for label, key in (("当前项目引导", "project_setup"), ("用户级引导", "user_activation")):
                if key in result:
                    print(label + "：" + ("已更新" if result[key].get("status") == "initialized" else "未绑定，已跳过"))
            print("已有记忆和控制开关保留；其他项目无需重新初始化。新会话加载更新后的规则。")
        elif args.project:
            print("项目已初始化：" + result["project_setup"]["project_root"])
            print("自动引导：" + result["project_setup"]["guide"])
            print("在该项目新建 AI 会话，直接提出开发任务即可；无需启用口令。")
        if args.operation != "update" and agent == "codex" and args.project is not None:
            print("Codex 用户级全局开发习惯已配置；在各项目新会话中生效。")
        elif args.operation != "update" and not args.project:
            print("仅安装了程序。为业务项目初始化：python3 install.py " + agent + " --project /项目路径")
        if args.with_codex_hooks:
            print("可选 hooks 已配置；仍需宿主信任和真实事件验证。")


# The online entry has no __file__ and binds the caller's project. Local source
# installation requires --project when project activation is wanted.
ONLINE_URL = "https://codeload.github.com/chrisstarr7/dev-memory/zip/refs/heads/main"
MAX_DOWNLOAD = 8 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024


def download_snapshot() -> bytes:
    import os
    import ssl
    import time
    import urllib.request

    context = ssl.create_default_context()
    # python.org macOS builds can lack their optional certificate bundle. Use
    # the system CA file without weakening verification or overriding custom CAs.
    system_ca = Path("/etc/ssl/cert.pem")
    if (sys.platform == "darwin" and system_ca.is_file()
            and not os.environ.get("SSL_CERT_FILE") and not os.environ.get("SSL_CERT_DIR")):
        context.load_verify_locations(cafile=str(system_ca))
    started = time.monotonic()
    chunks = []
    size = 0
    with urllib.request.urlopen(ONLINE_URL, timeout=15, context=context) as response:
        while True:
            chunk = response.read(min(65536, MAX_DOWNLOAD + 1 - size))
            size += len(chunk)
            if size > MAX_DOWNLOAD:
                raise ValueError("在线安装包超过大小上限。")
            if time.monotonic() - started > 45:
                raise TimeoutError("在线安装包读取超时。")
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def unpack_snapshot(data: bytes, destination: Path) -> dict:
    """Validate a bounded ZIP and its entire public manifest before any execution."""
    import hashlib
    import io
    import re
    import stat
    import zipfile
    from pathlib import PurePosixPath

    def safe_path(name: str) -> tuple[str, ...]:
        parts = PurePosixPath(name).parts
        if (not name or "\\" in name or name.startswith("/") or ":" in name
                or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))):
            raise ValueError("在线安装包包含不安全路径。")
        return parts

    if len(data) > MAX_DOWNLOAD:
        raise ValueError("在线安装包超过大小上限。")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > 1024 or sum(info.file_size for info in infos) > MAX_EXPANDED:
            raise ValueError("在线安装包展开超过上限。")
        entries = {}
        roots = set()
        for info in infos:
            # zipfile normalizes Windows separators and strips NULs. Validate
            # the original name before using the normalized lookup name.
            if info.orig_filename != info.filename:
                raise ValueError("在线安装包包含被规范化的不安全路径。")
            parts = safe_path(info.filename)
            roots.add(parts[0])
            if info.filename in entries or info.file_size > 1024 * 1024:
                raise ValueError("在线安装包包含重复条目或过大的文件。")
            kind = stat.S_IFMT(info.external_attr >> 16)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
                raise ValueError("在线安装包包含链接、特殊文件或加密条目。")
            entries[info.filename] = info
        if len(roots) != 1:
            raise ValueError("在线安装包根目录不唯一。")
        prefix = roots.pop() + "/"
        manifest = json.loads(archive.read(prefix + "manifest.json"))
        if (not isinstance(manifest, dict) or manifest.get("package") != "dev-memory"
                or not isinstance(manifest.get("version"), str) or not manifest["version"]
                or not isinstance(manifest.get("files"), list)
                or not 1 <= len(manifest["files"]) <= 256):
            raise ValueError("在线安装清单无效。")
        verified = {}
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValueError("在线安装清单文件条目无效。")
            name = entry["path"]
            safe_path(name)
            if (name.endswith("/") or name == "manifest.json" or name in verified
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
                raise ValueError("在线安装清单包含重复或无效条目。")
            info = entries.get(prefix + name)
            if info is None or info.is_dir():
                raise ValueError("在线安装清单中的文件缺失。")
            content = archive.read(info)
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("在线安装包校验失败，请稍后重试。")
            verified[name] = content
        required = {"install.py", "skills/dev-memory/SKILL.md", "skills/dev-memory/scripts/dev_memory.py"}
        if not required.issubset(verified):
            raise ValueError("在线安装包缺少必要程序。")
        # Only checked public source files are staged. No memory data lives here.
        for name, content in verified.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return {"version": manifest["version"], "verified_files": len(verified)}


def online_main(argv: list[str] | None = None) -> int:
    import tempfile
    import zipfile

    parser = argument_parser()
    args = parse_arguments(parser, argv)
    agent = ALIASES.get(args.agent or "", args.agent)
    option = ALIASES.get(args.agent_option or "", args.agent_option)
    if agent and option and agent != option:
        parser.error("两个 AI 参数不一致。")
    agent = agent or option
    if agent not in {"codex", "claude-code", "cursor", "gemini-cli", "github-copilot", "opencode", "deepseek-harness"}:
        parser.error("请指定 AI：codex、claude、cursor、gemini、copilot、opencode 或 deepseek。")
    if args.project is not None:
        args.project = args.project.expanduser().resolve()
    else:
        args.project = Path.cwd().resolve()
    enable_user = agent == "codex"
    result = {}
    try:
        if sys.version_info < (3, 10):
            raise ValueError("需要 Python 3.10+。")
        import sqlite3
        try:
            sqlite3.connect(":memory:").close()
        except sqlite3.Error as exc:
            raise ValueError("sqlite3 不可用。") from exc
        with tempfile.TemporaryDirectory(prefix="dev-memory-source-") as staging:
            source = Path(staging)
            snapshot = unpack_snapshot(download_snapshot(), source)
            command = [sys.executable, "-B", str(source / "install.py"), agent,
                       "--json", "--project", str(args.project)]
            if args.operation == "update":
                command.insert(3, "update")
            if args.target:
                command += ["--target", str(args.target.expanduser().resolve())]
            if args.upgrade:
                command.append("--upgrade")
            if args.with_codex_hooks:
                command.append("--with-codex-hooks")
            child = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
            result = json.loads(child.stdout)
            if not isinstance(result, dict):
                raise ValueError("安装程序返回了无效回执。")
            if child.returncode == 0:
                runtime = result.get("runtime_check")
                setup = result.get("project_setup")
                user_setup = result.get("user_activation")
                valid_setup = (isinstance(setup, dict) and setup.get("status") == "initialized"
                               and setup.get("activation") == "configured" and setup.get("project_root") == str(args.project)
                               and isinstance(setup.get("stores"), list) and len(setup["stores"]) == 2
                               and {item.get("scope") for item in setup["stores"] if isinstance(item, dict)} == {"global", "project"})
                valid_user = (not enable_user or (isinstance(user_setup, dict)
                              and user_setup.get("status") == "initialized" and user_setup.get("activation") == "configured"))
                if args.operation == "update":
                    valid_setup = isinstance(setup, dict) and (valid_setup or (setup.get("status") == "skipped" and setup.get("reason") == "not_bound"))
                    valid_user = not enable_user or (isinstance(user_setup, dict) and (valid_user or (user_setup.get("status") == "skipped" and user_setup.get("reason") == "not_bound")))
                if (result.get("status") != "installed" or not isinstance(result.get("path"), str) or not result["path"]
                        or not isinstance(runtime, dict) or runtime.get("status") != "passed" or not valid_setup or not valid_user):
                    raise ValueError("安装程序没有返回完整成功回执。")
            elif result.get("status") != "failed":
                raise ValueError("安装程序退出失败，但回执未报告失败。")
            result["online"] = {"source": ONLINE_URL, **snapshot}
    except subprocess.TimeoutExpired:
        result = {"status": "failed", "error": "online_install_timeout",
                  "message": "安装检查超时；部分程序或空库可能已创建，请检查后重试同一命令。"}
    except (OSError, ImportError, ValueError, KeyError, TypeError, AttributeError,
            zipfile.BadZipFile, RuntimeError, subprocess.SubprocessError) as exc:
        if not isinstance(result, dict):
            result = {}
        result.update(status="failed", error="online_install_failed",
                      message="在线安装未完成：" + str(exc) + "。若安装程序已运行，请检查实际安装状态。")
    report(result, args, agent)
    return 0 if result.get("status") == "installed" else 1


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(online_main() if globals().get("__file__", "<stdin>") == "<stdin>" else main())

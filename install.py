#!/usr/bin/env python3
"""Install dev-memory with an explicit AI selection and a runtime check."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ALIASES = {"claude": "claude-code", "gemini": "gemini-cli", "copilot": "github-copilot"}


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

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", nargs="?", help="codex, claude, cursor, gemini, copilot, opencode")
    parser.add_argument("--agent", dest="agent_option", help="Compatible explicit AI selector")
    parser.add_argument("--target", type=Path, help="Custom Skill directory")
    parser.add_argument("--upgrade", action="store_true", help="Replace a managed installation; preserve memory")
    parser.add_argument("--with-codex-hooks", action="store_true", help="Explicitly configure optional Codex hooks")
    parser.add_argument("--json", action="store_true", help="Structured result for automation")
    args = parser.parse_args(argv)
    agent = ALIASES.get(args.agent or "", args.agent)
    option = ALIASES.get(args.agent_option or "", args.agent_option)
    if agent and option and agent != option:
        parser.error("两个 AI 参数不一致。")
    agent = agent or option
    if not agent:
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

    result: dict = {}
    try:
        result = dev_memory.install(args.target, args.with_codex_hooks, args.upgrade, agent)
        installed_cli = Path(result["path"]) / "scripts/dev_memory.py"
        check = subprocess.run([sys.executable, "-B", str(installed_cli), "doctor"],
                               capture_output=True, text=True, timeout=10)
        diagnostic = json.loads(check.stdout) if check.returncode == 0 else {}
        if (not isinstance(diagnostic, dict) or diagnostic.get("status") != "ok"
                or diagnostic.get("base_mode") != "available"
                or not all(isinstance(diagnostic.get(key), str) for key in ("python", "sqlite"))):
            raise ValueError("runtime check failed")
        result["runtime_check"] = {"status": "passed", "python": diagnostic["python"], "sqlite": diagnostic["sqlite"]}
        if result["hooks"]["status"] == "failed":
            result.update(status="failed", error="hook_configuration_failed",
                          message="Skill 文件已安装且基础检查通过，但可选 hooks 配置失败；请检查 hooks 结果。")
    except store.MemoryError as exc:
        result.update(status="failed", error=exc.code, message=exc.message)
    except (OSError, ValueError, subprocess.SubprocessError):
        result.update(status="failed", error="installation_check_failed",
                      message="安装或检查失败。若已返回 path，文件可能已安装；请从该目录运行 doctor 检查。")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result["status"] == "failed":
        print("安装未完成：" + result["message"], file=sys.stderr)
        if result.get("path"):
            print("程序目录：" + result["path"], file=sys.stderr)
        if result.get("error") == "already_installed":
            print(f"升级已有安装：python3 install.py {agent} --upgrade", file=sys.stderr)
    else:
        print("安装成功；基础命令检查通过。")
        print("程序目录：" + result["path"])
        print("下一步：重开 AI 或新建会话，打开你的项目，发送：")
        print("使用 dev-memory，为当前项目启用研发记忆，先检查环境并召回相关要求。")
        if args.with_codex_hooks:
            print("可选 hooks 已配置；仍需宿主信任和真实事件验证。")
    return 0 if result["status"] == "installed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

# 安装与首次使用

## 安装前

- 准备 Python 3.10+，包含标准库 sqlite3。Mac/Linux 使用 `python3`，Windows 通常使用 `py -3`。
- 使用能访问本机文件并运行命令的 AI 开发助手。远程容器安装只影响容器，不能据此声称已安装到你的电脑。
- 首次安装不创建记忆库、不加载演示数据、不修改 hooks。为项目启用记忆是后续独立操作。

## 给 AI 的安装流程

用户说“安装 dev-memory”时，按下面流程完成基础模式安装：

1. 确认当前 AI 宿主和本机文件/命令权限。检查 Python 版本和 sqlite3；缺少运行条件时报告具体缺口，不能只复制文件后声称可用。无法确定宿主时询问用户，不按目录猜测。
2. 将仓库下载或克隆到独立的临时目录，阅读 `install.py` 和运行程序。保存用户原工作区/项目路径，避免把下载目录当成用户的业务项目。
3. 从仓库根目录执行 `python3 install.py <AI参数> --json`；Windows 使用 `py -3`。参数从下表选择。不要使用 `--with-codex-hooks`，不要顺便初始化库或修改宿主引导文件。
4. 检查进程退出码、JSON 的 `status: installed` 与 `runtime_check.status: passed`，报告 `path`。返回失败、只有下载完成或只有宿主安装器的“成功”都不足以证明运行可用。
5. 已有安装时，核对原安装方式及冲突。用户要求升级后，Python 管理的安装可使用 `--upgrade`；拒绝覆盖未管理文件、额外文件或符号链接。使用 Skill 管理器安装的副本继续由原管理器维护。
6. 告诉用户重开 AI/会话，并在原项目发送 README 的启用指令。新会话应能发现 Skill；若不能，按下方常见问题检查。没有真实宿主发现/调用结果时只报告程序安装和运行检查已完成。

安装过程中不要要求用户提供密钥或添加另一套模型/服务。安装失败后最多一次针对明确原因的重试；持续失败时报告实际结果。

## 手动安装

下载 ZIP、解压，在含 `install.py` 的仓库根目录打开终端：

```sh
python3 install.py
```

选择菜单中的 AI；输入编号或名称即可。取消或选错时不会创建安装目录。Windows：

```powershell
py -3 install.py
```

已知宿主时，可直接指定短名称：

| AI | 命令 | Python 安装目录 |
| --- | --- | --- |
| Codex | `python3 install.py codex` | `~/.agents/skills/dev-memory/` |
| Claude Code | `python3 install.py claude` | `~/.claude/skills/dev-memory/` |
| Cursor | `python3 install.py cursor` | `~/.cursor/skills/dev-memory/` |
| Gemini CLI | `python3 install.py gemini` | `~/.gemini/skills/dev-memory/` |
| GitHub Copilot | `python3 install.py copilot` | `~/.copilot/skills/dev-memory/` |
| OpenCode | `python3 install.py opencode` | `~/.config/opencode/skills/dev-memory/` |

原来的 `--agent codex`、`--agent claude-code` 等参数仍可使用。`--target` 可指定自定义 Skill 目录；需要同时选择 AI，安装器不会自动猜测。脚本调用必须显式选择 AI，不能依赖交互菜单。

成功输出包含：

```text
安装成功；基础命令检查通过。
程序目录：实际安装路径
下一步：重开 AI 或新建会话，打开你的项目，发送：
使用 dev-memory，为当前项目启用研发记忆，先检查环境并召回相关要求。
```

该检查证明安装后的 CLI 可以运行。AI 是否发现并调用 Skill，需要在该宿主的新会话中确认。初次 `doctor` 显示记忆库 `unavailable` 是尚未初始化的状态，不等于程序安装失败。

## 使用 skills 管理器

已有 Node.js/npm 的用户可从 GitHub 安装：

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 add chrisstarr7/dev-memory -g
```

仓库只有一个 Skill，无需再指定 `--skill dev-memory`。按安装器提示选择目标 AI。`-g` 表示安装程序到用户目录，**不表示业务记忆进入全局库**。需要非交互安装时加 `-a codex --copy -y`，并选择自己的 AI 参数。

`skills@1.7.2` 需要 Node >=22.20.0。`DISABLE_TELEMETRY=1` 关闭外部安装器的遥测；dev-memory 核心不收集遥测。Windows PowerShell：

```powershell
$env:DISABLE_TELEMETRY = '1'
npx skills@1.7.2 add chrisstarr7/dev-memory -g
```

该管理器只复制 Skill，不检查 Python 运行时。安装后请让 AI 从实际安装目录运行 `scripts/dev_memory.py doctor`，检查 `base_mode: available`，再重开会话并启用记忆。实际测试中，Codex/Cursor/Gemini/Copilot/OpenCode 使用 `~/.agents/skills/dev-memory`，Claude Code 使用 `~/.claude/skills/dev-memory`。以安装器报告的路径为准，勿混用管理器。

## 启用、使用与检查

打开业务项目，在新 AI 会话中发送：

> 使用 dev-memory，为当前项目启用研发记忆，先检查环境并召回相关要求。

AI 应检查环境和项目归属，然后初始化全局空库与所属项目空库。Git 项目初始化会验证本地忽略规则；已跟踪的记忆路径会阻止写入，不删除 Git 历史。非 Git 项目需要明确项目根。只读请求不会初始化。启用已有暂停的项目时，AI 应按你的明确恢复要求重新开启该项目写入。

正常开发中，纠错及时保存，普通增量轮末批量保存；新会话重新调用 Skill 并核对断点。检查保存结果时让 AI 执行只读 `list`/`show`，查看来源、条件和版本。不能用 AI 的复述代替实际记录。

CLI 排查示例（Codex 默认路径，其他安装器请使用报告的实际路径）：

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py doctor
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py list --scope project --project-root "/path/to/project"
```

记忆属于数据：全局 `~/.dev-memory/global/`，项目与任务 `<项目根>/.dev-memory/`。程序升级或卸载不会自动删除这些目录。

## 常见问题

| 情况 | 怎么处理 |
| --- | --- |
| `python3` 找不到或版本低于 3.10 | 安装/更新 Python 后重新运行；Windows 尝试 `py -3`。安装器不自动改系统 Python |
| `sqlite3` 缺失 | 使用包含 sqlite3 的 Python；不要安装同名第三方包代替标准库 |
| `install.py` 找不到 | 进入解压后含 `install.py` 的仓库根目录，确认解压完成 |
| 没出现 AI 选择菜单 | 非交互终端需要显式指定，如 `python3 install.py claude` |
| 提示已经安装 | 核对原管理器；Python 管理的副本按下节升级，不直接删除目录 |
| 运行检查失败，但目录已创建 | 文件可能已安装，按返回路径运行 `doctor`；失败不等于完整成功 |
| 重开会话仍找不到 Skill | 确认 AI 参数和实际目录；Codex 尝试 `$dev-memory`，其他宿主检查自己的 Skill 入口/版本 |
| AI 说“记住了”但查不到记录 | 要求查看 CLI 回执，检查是否未启用、暂停、只读或写入失败 |
| 项目路径不明确/不可写 | 指定业务项目根或授权可写目录；项目内容不能改存全局 |
| 安装成功但不是每轮自动记忆 | 当前基础模式依赖实际调用；可选 hooks 的真实自动事件链路仍未验证 |

## 升级与卸载

使用最初的安装方式。Python 安装：下载新版，在新版仓库根目录运行，例如 Codex：

```sh
python3 install.py codex --upgrade
python3 skills/dev-memory/scripts/dev_memory.py uninstall --agent codex
```

第一条升级，第二条卸载程序。其他 AI 指定对应的完整 `--agent` 名称；自定义目录沿用 `--target`。升级/卸载保留记忆，额外文件或符号链接会阻止覆盖/删除。旧数据库的授权迁移由 AI 执行 `init`，不遍历其他项目。彻底删除某些记忆需使用 `forget` 的预览和确认流程。

skills 管理器安装：

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 update dev-memory -g
DISABLE_TELEMETRY=1 npx skills@1.7.2 remove dev-memory -g -a codex -y
```

这些命令修改程序和管理器元数据，保留记忆。不会替你处理手动配置的 hooks。

## 可选 Codex hooks

仅在明确需要时，从实际安装的副本运行 `scripts/dev_memory.py hooks configure`。它合并 `$CODEX_HOME/hooks.json`，保留无关配置，不开启特性、不授予脚本信任。必须按当前宿主版本核验事件与 `/hooks` 信任后才能使用；配置成功不能当作自动端到端验证。

曾配置 hooks 的安装，在改变路径或由外部管理器卸载前，先从原副本运行 `scripts/dev_memory.py hooks remove`。Python 受管理卸载清理属于该副本的适配命令。详见 [适配器说明](../skills/dev-memory/references/codex-hooks.md)。

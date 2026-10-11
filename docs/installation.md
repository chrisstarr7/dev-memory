# 安装与项目初始化

## 推荐入口

下载并解压本仓库，在包含 `install.py` 的目录运行：

```sh
python3 install.py codex --project /实际项目路径
```

Windows 使用 `py -3`。需要 Python 3.10+ 和标准库 sqlite3。一条命令安装 Skill、检查运行时、初始化全局和项目空库、合并宿主项目引导。首次创建没有演示记录；已有数据及暂停状态不会被重置。

| AI 参数 | 自动加载的项目引导 | Python 安装目录 |
| --- | --- | --- |
| `codex` | `AGENTS.md`；已有非空 `AGENTS.override.md` 时合并其中 | `~/.agents/skills/dev-memory/` |
| `claude` | `CLAUDE.local.md` | `~/.claude/skills/dev-memory/` |
| `cursor` | `.cursor/rules/dev-memory.mdc`，`alwaysApply: true` | `~/.cursor/skills/dev-memory/` |
| `gemini` | `GEMINI.md` | `~/.gemini/skills/dev-memory/` |
| `copilot` | `.github/copilot-instructions.md` | `~/.copilot/skills/dev-memory/` |
| `opencode` | `AGENTS.md` | `~/.config/opencode/skills/dev-memory/` |

项目路径必须明确指向你的开发项目，不能误指下载目录。非 Git 项目同样可初始化。项目目录不可写时返回失败，不会将项目数据转存全局。初始化只配置这个项目，其他项目需各自初始化。

新建该项目的 AI 会话后直接开发。宿主启动时加载引导，AI 读取安装的 Skill 并默认管理记忆；不需要聊天启用口令。已有会话可能缓存启动指令，需要新会话才能生效。宿主自己的信任和进程权限要求仍由宿主管理。

## 给 AI 的安装流程

用户要求安装并初始化时：

1. 确认当前宿主、本地命令权限，以及用户原项目的根目录。保留原项目路径，再下载或克隆仓库到独立临时目录；不要把下载目录当成业务项目。无法确认宿主或项目时，仅询问缺失的信息。
2. 检查 Python 3.10+、sqlite3，阅读安装程序。从仓库运行 `python3 install.py <AI参数> --project <用户项目绝对路径> --json`。可用 `--target` 指定真实宿主支持的自定义 Skill 目录。
3. 检查退出码为 0，`status: installed`、`runtime_check.status: passed`，以及 `project_setup.status: initialized`、`activation: configured`。检查两个 `stores` 的真实结果。仅复制了文件不算初始化成功。
4. 报告项目、程序路径和引导文件。告诉用户在该项目新建会话后正常开发即可；不要要求发送启用、保存、召回或继续的 Skill 口令。
5. 已有受管理的安装在带 `--project` 的调用中可重复更新；额外文件、非受管理目录、符号链接和损坏的标记会拒绝覆盖。保留用户无关配置。外部管理器安装应继续使用其更新流程，并从实际安装副本调用 `setup`。

不修改个人全局指令，不开启后台进程，不配置默认 hooks，也不授予宿主信任。初始化是用户授权的项目配置变化，合并的管理块外内容保持原样。失败最多一次针对明确原因的重试，如实说明已安装/已初始化的部分。

## 已安装 Skill：初始化另一个项目

从实际安装副本执行（Codex 默认路径示例）：

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py setup --project-root /另一个项目路径
```

这个显式命令的项目参数省略时使用当前目录；默认宿主为 Codex。其他宿主加 `--agent claude-code`、`cursor`、`gemini-cli`、`github-copilot` 或 `opencode`。自定义安装使用实际副本路径。无需重复聊天授权。

`setup` 保存私有项目绑定 `.dev-memory/activation.json`，主机程序路径留在本项目范围内。项目记忆和绑定通过 Git 本地 exclude 排除。宿主指令文件只有通用协议，已有受版本管理的指令会出现一个管理块 diff，可正常审查；不会插入业务内容或个人绝对路径。

## 仅安装程序 / 使用 skills 管理器

高级用法：`python3 install.py codex` 只安装程序，不初始化项目；`python3 install.py` 可交互选择宿主。非交互环境必须指定宿主。原 `--agent` 参数仍支持。

已有 Node.js/npm 的用户也可安装标准 Skill：

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 add chrisstarr7/dev-memory -g -a codex --copy -y
```

这个外部管理器只复制程序；要得到默认项目记忆，应从它报告的实际安装副本运行上面的 `setup` 一次。`-g` 是程序安装位置，业务记忆仍留在所属项目。外部安装器需要 Node >=22.20.0；核心不依赖 Node，也不收集遥测。

## 检查与故障

AI 可从安装副本运行 `doctor --project-root <路径>`，检查 `project_activation` 和各存储状态。检查不会初始化或写入。`configured` 证明引导与运行文件存在，不证明每一轮都执行了。每次实际保存须检查回执；未检查、失败和 NOOP 必须区分。

- **原会话未生效**：新建该项目会话，使宿主重新加载启动指令。
- **只读或暂停**：初始化不会取消该设置；只有用户要求恢复时才执行 `capture on`。
- **找不到程序**：安装可能被移动或卸载。重新执行安装并初始化命令更新绑定。
- **项目指令冲突**：管理标记损坏、Cursor 同名未管理规则或文件符号链接会报错。检查实际冲突，保留用户内容后再重试。
- **宿主没有加载指令**：检查宿主是否禁用项目指令、路径范围、工作区信任及上下文容量。不会用一条手动 Skill 口令冒充默认启用成功。
- **部分失败**：按 `project_setup.stores` 与 `activation` 判断实际结果，不能声称整体已启用。已完成的空库初始化可保留并安全重试。

其他宿主的引导格式依据官方文档，真实运行结果见 [验证报告](../reports/verification.md)。没有实际事件回执时不宣称事件自动模式。

## 升级与卸载

从新下载的版本重新执行安装并初始化命令即可更新这个项目的绑定；已有数据和暂停状态保留。仅更新程序：

```sh
python3 install.py codex --upgrade
```

从实际副本卸载程序：

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py uninstall --agent codex
```

程序卸载保留所有记忆，不遍历其他项目。项目引导的管理块和私有绑定也保留，下一次安装初始化可复用；若不再使用，可删除该项目指令中的 `dev-memory:managed:start/end` 管理块。不要删除无关指令。要删除记忆内容，使用 `forget` 的预览与确认流程。

外部管理器安装的副本通过同一管理器 update/remove。不要混用升级方式。

## 可选 Codex hooks

项目引导无需 hooks。额外需要事件回执检查时，从安装副本运行 `scripts/dev_memory.py hooks configure`。它只合并 `$CODEX_HOME/hooks.json` 的自有处理器，保留无关配置，不开启特性、不授予脚本信任。真实事件、宿主权限和 `/hooks` 信任须单独验证；配置成功不是自动端到端成功。

改变路径或通过外部管理器卸载前，从原副本运行 `hooks remove`。Python 受管理卸载会清理属于自己的 hook 命令。详见 [适配器说明](../skills/dev-memory/references/codex-hooks.md)。

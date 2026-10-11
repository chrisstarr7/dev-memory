# 安装与项目初始化

## 推荐：短命令在线安装

在**业务项目根目录**执行，macOS、Linux、Windows 使用同一条命令：

```sh
npx -y chrisstarr7/dev-memory codex
```

只替换末尾的 AI 名称，见下表。需要 Node.js 22+、npm/npx、Git 和 Python 3.10+（含 sqlite3）。`npx` 直接获取这个公开 GitHub 仓库的程序，不需要 npm 账号。安装器无第三方 Node 依赖、无安装生命周期脚本，记忆运行时仍是 Python 标准库和 SQLite；安装完成后的记忆管理不调用 npx 或网络下载。

成功时显示程序、项目和引导文件。一条命令完成下载、运行检查、独立空库初始化和项目引导。重复执行更新受管理安装；已有记忆、暂停状态和原有指令保留。默认使用当前目录；其他目录执行时可加 `--project /项目绝对路径`。加 `--json` 获取机器回执。

| AI 参数 | 自动加载的项目引导 | Python 安装目录 |
| --- | --- | --- |
| `codex` | `AGENTS.md`；已有非空 `AGENTS.override.md` 时合并其中 | `~/.agents/skills/dev-memory/` |
| `claude` | `CLAUDE.local.md` | `~/.claude/skills/dev-memory/` |
| `cursor` | `.cursor/rules/dev-memory.mdc`，`alwaysApply: true` | `~/.cursor/skills/dev-memory/` |
| `gemini` | `GEMINI.md` | `~/.gemini/skills/dev-memory/` |
| `copilot` | `.github/copilot-instructions.md` | `~/.copilot/skills/dev-memory/` |
| `opencode` | `AGENTS.md` | `~/.config/opencode/skills/dev-memory/` |
| `deepseek`（DSH） | `AGENTS.md` | `~/.dsh/skills/dev-memory/`；遵循 `DSH_HOME` |

请在开发项目的根目录执行；不要在用户主目录或无关目录初始化。非 Git 项目同样可初始化。项目目录不可写时返回失败，不会将项目数据转存全局。初始化只配置这个项目，其他项目需各自初始化。

新建该项目的 AI 会话后直接开发。宿主启动时加载引导，AI 读取安装的 Skill 并默认管理记忆；不需要聊天启用口令。已有会话可能缓存启动指令，需要新会话才能生效。宿主自己的信任和进程权限要求仍由宿主管理。

## DeepSeek Harness（DSH）

在业务项目根目录执行：

```sh
npx -y chrisstarr7/dev-memory deepseek
```

`deepseek`、`dsh`、`deepseek-harness` 指向同一个 DSH 安装目标。默认安装到 `~/.dsh/skills/dev-memory/`；设置 `DSH_HOME` 时使用 `$DSH_HOME/skills/dev-memory/`，显式 `--target` 优先。若 DSH 配置文件另行覆盖了 Skill 的 `dshHome`，用 `--target` 指定该目录下的 `skills/dev-memory/`。

安装器合并项目 `AGENTS.md`，保留原指令，写入私有绑定并初始化空库。新建 DSH 项目会话后，按相同流程召回、纠错、去重、整理和保存断点。已有记忆和暂停状态在重复安装时保留。不会修改 DSH 模型配置、API 密钥、权限或 profiles。

这是给**已安装的 DeepSeek Harness**配置 dev-memory；本命令不安装 DSH 本身。通过 OpenCode 等工具调用 DeepSeek 模型时，应使用实际宿主的安装参数，例如 `opencode`。DeepSeek 网页和手机 App 无法直接执行本机 CLI。

本工具依赖 DSH 的文件系统 Skill provider、项目指令加载和命令执行权限。默认 base profile 有相应指令机制；自定义 profile 禁用这些功能或截断 `AGENTS.md` 时，不能声称自动加载成功。依据：[官方 Skill 文档](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/skills.md)、[官方项目指令文档](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/context/agent-instructions/README.md)。程序安装验证与真实模型端到端验证分别列在 [验证报告](../reports/verification.md)。

## 给 AI 的安装流程

用户要求安装并初始化时：

1. 确认当前宿主、本地命令权限及原业务项目根目录。无法确认时，只询问缺失的信息。
2. 检查 Python 3.10+ 和 sqlite3。在原项目根目录运行本页在线命令，选择实际宿主，并在末尾加 `--json`。其他目录使用显式 `--project <原项目绝对路径>`；自定义宿主目录用 `--target`。
3. 检查退出码为 0、`status: installed`、`runtime_check.status: passed`、`project_setup.status: initialized`、`activation: configured`，以及两个 `stores` 的实际结果。只复制文件不算初始化成功。
4. 报告项目、程序路径和引导文件。用户新建该项目会话后正常开发即可，不需要启用、保存、召回或继续的 Skill 口令。
5. 重复执行在线命令更新受管理安装和项目绑定。未知文件、非受管理目录、符号链接或损坏的标记会拒绝覆盖；保留无关配置。外部管理器安装应继续使用原管理器更新，从实际副本运行 `setup`。

不修改个人全局指令，不开启后台进程，不配置默认 hooks，也不授予宿主信任。初始化是用户授权的项目配置变化，合并的管理块外内容保持原样。失败最多一次针对明确原因的重试，如实说明已安装/已初始化的部分。

## 初始化另一个项目

在另一个项目根目录重复执行在线命令即可。每个项目有独立记忆，明确确认的全局研发偏好可以共用。

已有安装且不方便联网时，可直接使用本地副本（Codex 默认路径）：

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py setup --project-root /项目路径
```

其他宿主加 `--agent claude-code`、`cursor`、`gemini-cli`、`github-copilot` 、`opencode` 或 `deepseek-harness`；自定义安装使用实际副本路径。无需重复聊天授权。

`setup` 保存私有项目绑定 `.dev-memory/activation.json`，主机程序路径留在本项目范围内。项目记忆和绑定通过 Git 本地 exclude 排除。宿主指令文件只有通用协议，已有受版本管理的指令会出现一个管理块 diff，可正常审查；不会插入业务内容或个人绝对路径。

## 没有 Node.js：Python 在线入口

macOS / Linux（使用系统 Bash、curl 和 Python）：

```sh
bash -o pipefail -c 'curl -fsSL --max-time 30 https://raw.githubusercontent.com/chrisstarr7/dev-memory/main/install.py | python3 - "$@"' -- codex
```

Windows PowerShell：

```powershell
py -3 -c "import urllib.request as u; exec(u.urlopen('https://raw.githubusercontent.com/chrisstarr7/dev-memory/main/install.py', timeout=30).read())" codex
```

这个替代入口核对单份公开源码快照的完整性清单，并清理临时源码。下载、校验失败返回非零状态；HTTPS 保持证书验证。没有后台服务，不上传项目或记忆。

## 离线源码 / 仅安装程序

已有完整源码时，在仓库目录执行 `python3 install.py codex --project /业务项目绝对路径`。这与在线安装调用同一套运行检查和初始化逻辑；Windows 使用 `py -3`。

高级用法：`python3 install.py codex` 只安装程序，不初始化项目；`python3 install.py` 可交互选择宿主。非交互环境必须指定宿主。原 `--agent` 参数仍支持。

## 外部 skills 管理器

已有 Node.js/npm 的用户也可安装标准 Skill：

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 add chrisstarr7/dev-memory -g -a codex --copy -y
```

这个外部管理器只复制程序；要得到默认项目记忆，应从它报告的实际安装副本运行上面的 `setup` 一次。`-g` 是程序安装位置，业务记忆仍留在所属项目。外部安装器需要 Node >=22.20.0；核心不依赖 Node，也不收集遥测。

## 检查与故障

AI 可从安装副本运行 `doctor --project-root <路径>`，检查 `project_activation` 和各存储状态。检查不会初始化或写入。`configured` 证明引导与运行文件存在，不证明每一轮都执行了。每次实际保存须检查回执；未检查、失败和 NOOP 必须区分。

- **网络失败**：先确认能访问 GitHub，再重试同一在线命令；没有“安装成功”和项目初始化回执时，不算完成。下载、校验失败不会安装，安装阶段超时可能留下部分结果，应检查后重试。
- **HTTPS 证书错误**：保持证书验证，不使用 `-k` 或关闭 SSL 检查。macOS 安装包读取会加载系统 CA；自定义 `SSL_CERT_FILE` / `SSL_CERT_DIR` 会被保留。Windows/Python 首次下载失败时检查系统或管理员的 CA 配置。
- **找不到 npx**：使用含 npm 的 Node.js 22+，或使用上面的 Python 在线入口。
- **Windows PowerShell 限制 npx.ps1**：用 `npx.cmd -y chrisstarr7/dev-memory codex`，无需修改执行策略。
- **原会话未生效**：新建该项目会话，使宿主重新加载启动指令。
- **只读或暂停**：初始化不会取消该设置；只有用户要求恢复时才执行 `capture on`。
- **找不到程序**：安装可能被移动或卸载。重新执行安装并初始化命令更新绑定。
- **项目指令冲突**：管理标记损坏、Cursor 同名未管理规则或文件符号链接会报错。检查实际冲突，保留用户内容后再重试。
- **全局库无写权限**：Codex 的 `workspace-write` 等沙箱可能限制项目外写入；全局记忆目录需要宿主允许（例如 Codex 的 writable roots / `--add-dir`）。初始化不扩大宿主权限或绕过信任。按宿主提示一次性授权必要目录；拒绝或只读时报告该范围不可写，不能把项目内容转存其他位置。
- **宿主没有加载指令**：检查宿主是否禁用项目指令、路径范围、工作区信任及上下文容量。不会用一条手动 Skill 口令冒充默认启用成功。
- **部分失败**：按 `project_setup.stores` 与 `activation` 判断实际结果，不能声称整体已启用。已完成的空库初始化可保留并安全重试。

其他宿主的引导格式依据官方文档，真实运行结果见 [验证报告](../reports/verification.md)。没有实际事件回执时不宣称事件自动模式。

## 升级与卸载

**升级：在项目根目录重新执行同一在线命令。** 会更新程序与该项目的绑定，已有记忆和暂停状态保留。其他项目的绑定不被扫描或修改。

使用离线源码且仅更新程序时：

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

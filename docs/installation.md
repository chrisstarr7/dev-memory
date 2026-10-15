# 安装与宿主配置

## 推荐：短命令在线安装

在**项目根目录**执行，先将 `<agent>` 替换为下方宿主表中的参数。macOS、Linux、Windows 使用同一条命令：

```sh
npx -y --prefer-online chrisstarr7/dev-memory <agent>
```

支持 Codex、Claude Code、Cursor、Gemini CLI、GitHub Copilot、OpenCode 和 DeepSeek Harness，参数与路径见下表。需要 Node.js 22+、npm/npx、Git 和 Python 3.10+（含 sqlite3）。`npx` 直接获取这个公开 GitHub 仓库的程序，不需要 npm 账号。安装器无第三方 Node 依赖、无安装生命周期脚本，记忆运行时仍是 Python 标准库和 SQLite；安装完成后的记忆管理不调用 npx 或网络下载。

成功时显示程序、项目和引导文件。一条命令完成下载、运行检查、独立空库初始化和项目引导。新项目默认为 `developer-first`：优先学习全局习惯，读取已有项目规则，但不新增项目或任务记录。需要完整项目捕获时，让 AI 使用 `.dev-memory/activation.json` 中当前宿主的 `python` 和 `cli` 路径，调用 `mode full-project --project-root /项目路径`；同一命令接受 `developer-first` 以切回。重复执行复用相同的受管理程序，有变化时自动更新；已有记忆与配置不会清空。默认使用当前目录；其他目录执行时可加 `--project /项目绝对路径`。加 `--json` 获取机器回执。

## Codex 一次安装同时配置全局与项目

上面的安装命令选择 `codex` 后，同时配置用户级全局记忆和当前项目引导，不需要额外参数或第二条安装命令。安装器初始化各自独立的全局库与项目库；已有记忆、暂停/只读设置和项目捕获模式保持原样。新项目仍默认采用 `developer-first`，不会因合并入口而扩大业务记忆捕获范围。

用户级引导写入 `$CODEX_HOME/AGENTS.override.md`（若存在且非空），否则写入 `$CODEX_HOME/AGENTS.md`，仅更新管理标记之间的内容。当前项目使用自己的引导与私有 activation 绑定。已有非空 override 会被优先使用，避免遮蔽实际引导。

已初始化项目只进行一次有界全局＋项目召回，不重复执行用户级全局召回。其他项目通过用户级引导使用 `context --global-only --exclude-task`，初始化前不自动记录其业务信息。其他 AI 宿主暂无用户级适配器，继续使用项目适配器。

安装成功必须同时具备项目与用户级配置回执；部分成功会报告失败及已完成部分。卸载受管理 Skill 会删除属于该安装路径的用户级管理块，保留无关指令及记忆数据；重新打开 Codex 会话后生效。

用户级激活可在隔离环境中检查文件、回执和全局库；程序回执不代表真实 Codex 对话已正确遵循。官方检查方法是在任意两个项目新会话中询问当前加载的指令，并确认全局文件在项目文件之前。见 [Codex AGENTS.md 指南](https://developers.openai.com/codex/guides/agents-md)。

| AI 参数 | 自动加载的项目引导 | Python 安装目录 |
| --- | --- | --- |
| `codex` | `AGENTS.md`；已有非空 `AGENTS.override.md` 时合并其中 | `~/.agents/skills/dev-memory/` |
| `claude` | `CLAUDE.local.md` | `~/.claude/skills/dev-memory/` |
| `cursor` | `.cursor/rules/dev-memory.mdc`，`alwaysApply: true` | `~/.cursor/skills/dev-memory/` |
| `gemini` | `GEMINI.md` | `~/.gemini/skills/dev-memory/` |
| `copilot` | `.github/copilot-instructions.md` | `~/.copilot/skills/dev-memory/` |
| `opencode` | `AGENTS.md` | `~/.config/opencode/skills/dev-memory/` |
| `deepseek`（DSH） | `AGENTS.md` | `~/.dsh/skills/dev-memory/`；遵循 `DSH_HOME` |

请在开发项目的根目录执行；不要在用户主目录或无关目录初始化。非 Git 项目同样可初始化。项目目录不可写时返回失败，不会将项目数据转存全局。项目业务记忆只绑定当前项目，其他项目需各自初始化；Codex 用户级全局习惯可跨项目使用。

新建该项目的 AI 会话后直接开发。宿主启动时加载引导，AI 读取安装的 Skill 并默认管理记忆；不需要聊天启用口令。已有会话可能缓存启动指令，需要新会话才能生效。宿主自己的信任和进程权限要求仍由宿主管理。

## DeepSeek Harness（DSH）

在业务项目根目录执行：

```sh
npx -y chrisstarr7/dev-memory deepseek
```

`deepseek`、`dsh`、`deepseek-harness` 指向同一个 DSH 安装目标。默认安装到 `~/.dsh/skills/dev-memory/`；设置 `DSH_HOME` 时使用 `$DSH_HOME/skills/dev-memory/`，显式 `--target` 优先。若 DSH 配置文件另行覆盖了 Skill 的 `dshHome`，用 `--target` 指定该目录下的 `skills/dev-memory/`。

安装器合并项目 `AGENTS.md`，保留原指令，写入私有绑定并初始化空库。新建 DSH 项目会话后，按相同流程召回、纠错、去重、整理和保存开发习惯。已有记忆和暂停状态在重复安装时保留。不会修改 DSH 模型配置、API 密钥、权限或 profiles。

这是给**已安装的 DeepSeek Harness**配置 dev-memory；本命令不安装 DSH 本身。通过 OpenCode 等工具调用 DeepSeek 模型时，应使用实际宿主的安装参数，例如 `opencode`。DeepSeek 网页和手机 App 无法直接执行本机 CLI。

本工具依赖 DSH 的文件系统 Skill provider、项目指令加载和命令执行权限。默认 base profile 有相应指令机制；自定义 profile 禁用这些功能或截断 `AGENTS.md` 时，不能声称自动加载成功。依据：[官方 Skill 文档](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/skills.md)、[官方项目指令文档](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/context/agent-instructions/README.md)。程序安装验证与真实模型端到端验证分别列在 [验证报告](../reports/verification.md)。

## Windows Codex 访问权限

0.5.2 修复了程序目录的 Windows ACL 创建方式：以前将 `0700` 同时用于公开 Skill 程序和私有数据，而 Windows Python 会把这种目录限制为当前用户和管理员可访问。Codex 沙箱身份可能因此读不到 Skill。现在公开程序目录继承安装父目录的 ACL，macOS/Linux 的模式和私有记忆库权限保持原策略。

已有安装在业务项目根目录的**普通终端**重复执行原命令即可升级：

```sh
npx -y chrisstarr7/dev-memory codex
```

从旧版升级时，安装器会重建受管理的程序目录和子目录；相同新版重复执行时复用文件。若需要修复同版本程序目录权限，追加 `--upgrade` 强制重建。已有记忆、暂停设置、项目指令及绑定保留。完成后新建 Codex App 会话。该修复不要求给 AI 管理员权限，不运行 `RunAs`、`takeown`、`icacls /reset`，不修改整个 `.agents`、Codex 沙箱或企业权限策略。

继承父目录 ACL 不能保证任意父目录或权限 profile 都允许访问。如果普通终端也不能读写原 `.agents` 目录，可显式选择普通用户可写、且 Codex 可读的项目内程序位置（程序不含记忆数据）：

```sh
npx -y chrisstarr7/dev-memory codex --target ./tools/dev-memory
```

自定义程序位置通过项目引导和绑定使用；它不保证作为原生 Skill 目录被发现，需通过 `AGENTS.md` 加载。请选不存在的目录或本工具受管理目录；此选项不会删除旧安装，也不会更改它的 ACL。自定义程序目录是否提交 Git 由项目决定，私有记忆仍默认排除。升级和卸载须继续指定同一 `--target`。

新建或更新回执 `program_permissions: inherited_windows_acl` 描述程序创建方式；复用回执为 `unchanged`，不声称重新应用 ACL。`sandbox_access_verified: false` 明确普通安装进程的运行检查不能代替当前 Codex 沙箱检查。真实会话需确认能读取绑定中的 `SKILL.md`、执行 CLI，并报告各库访问/写入结果。全局库不可访问时不能将它移到项目，项目内容也不能改存全局。

如果新会话仍拒绝访问，请在普通 PowerShell 中只读检查实际拒绝路径的 `Get-Acl`，再核对 Codex 的权限 profile、受管理限制和沙箱状态。目录 ACL、profile 的路径限制、旧 sandbox 初始化失败属于不同问题。企业禁止的路径或 Codex 旧沙箱本身需要管理员批准的初始化不能由 Skill 绕过；针对私有库的必要访问授权也不能冒充已完成。

依据：[Python 3.14 mkdir 权限](https://docs.python.org/3.14/library/os.html#os.mkdir)、[Python 3.10.15 的同类行为](https://docs.python.org/3.10/library/os.html#os.mkdir)、[OpenAI Windows 沙箱文档](https://learn.chatgpt.com/docs/windows/windows-sandbox)、[受保护目录规则](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots)。Windows 程序 ACL 测试与桌面 App 验证状态见 [报告](../reports/windows-access.json)。

## 给 AI 的安装流程

用户要求安装并初始化时：

1. 确认当前宿主、本地命令权限及原业务项目根目录。无法确认时，只询问缺失的信息。
2. 检查 Python 3.10+ 和 sqlite3。在原项目根目录运行本页在线命令，选择实际宿主，并在末尾加 `--json`。其他目录使用显式 `--project <原项目绝对路径>`；自定义宿主目录用 `--target`。
3. 检查退出码为 0、`status: installed`、`runtime_check.status: passed`、`project_setup.status: initialized`、`activation: configured`，以及两个 `stores` 的实际结果。只复制文件不算初始化成功。
4. 报告项目、程序路径和引导文件。用户新建该项目会话后正常开发即可，不需要启用、保存、召回或继续的 Skill 口令。
5. 重复执行在线命令更新受管理安装和项目绑定。未知文件、非受管理目录、符号链接或损坏的标记会拒绝覆盖；保留无关配置。外部管理器安装应继续使用原管理器更新，从实际副本运行 `setup`。

不修改个人全局指令，不开启后台进程，不配置默认 hooks，也不授予宿主信任。初始化是用户授权的项目配置变化，合并的管理块外内容保持原样。失败最多一次针对明确原因的重试，如实说明已安装/已初始化的部分。

## 初始化另一个项目

在另一个项目根目录重复执行在线命令即可。程序只需一份；A、B 各自初始化，不因公共程序已存在而跳过 B。每个项目有独立记忆，明确确认的全局研发偏好可以共用。

回执中的 `program_action` 为 `installed`（首次安装）、`updated`（更新/强制重建）或 `reused`（相同文件复用）。这三个结果都必须继续检查 `project_setup`；公共目录存在不是项目初始化成功。切回 A 重复执行也不会清空 A 或恢复已暂停的采集。

若旧安装入口仍报“已存在”，或回执版本落后，可获取明确的最新分支：

```sh
npx -y --prefer-online chrisstarr7/dev-memory#main codex
```

无需清空整个 npm 缓存、删除公共 Skill 或使用管理员终端。缓存相关选项见 [npm 官方说明](https://docs.npmjs.com/cli/v11/commands/npm-exec/#a-note-on-caching)。未知文件或非受管理目录仍会拒绝覆盖；它们需要检查，不能作为重复安装自动删除。多个安装/卸载同时操作同一目录时返回 `installation_busy`，结束后重试一次；进程中断留下的锁须确认没有活动进程再删除该锁文件。

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

**升级：在项目根目录重新执行同一在线命令。** 程序有变化时更新，相同版本复用，同时检查/更新该项目的绑定，已有记忆和暂停状态保留。其他项目的绑定不被扫描或修改。

使用离线源码且仅更新程序时：

```sh
python3 install.py codex
```

`--upgrade` 仅用于强制重建同版本受管理程序；普通安装和更新无需追加。安装器拒绝用旧源码覆盖较新版本。`old_program_cleanup` 如为 `pending:<目录名>`，新程序已经就位，但旧程序备份因文件占用尚未删除；确认文件不再占用后清理该具名旧程序目录。该备份不含记忆。

从实际副本卸载程序：

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py uninstall --agent codex
```

程序卸载保留所有记忆，不遍历其他项目。项目引导的管理块和私有绑定也保留，下一次安装初始化可复用；若不再使用，可删除该项目指令中的 `dev-memory:managed:start/end` 管理块。不要删除无关指令。要删除记忆内容，使用 `forget` 的预览与确认流程。

外部管理器安装的副本通过同一管理器 update/remove。不要混用升级方式。

## 可选 Codex hooks

项目引导无需 hooks。额外需要事件回执检查时，从安装副本运行 `scripts/dev_memory.py hooks configure`。它只合并 `$CODEX_HOME/hooks.json` 的自有处理器，保留无关配置，不开启特性、不授予脚本信任。真实事件、宿主权限和 `/hooks` 信任须单独验证；配置成功不是自动端到端成功。

改变路径或通过外部管理器卸载前，从原副本运行 `hooks remove`。Python 受管理卸载会清理属于自己的 hook 命令。详见 [适配器说明](../skills/dev-memory/references/codex-hooks.md)。


## 项目 Git 保护失效

数据库、Markdown 视图和备份写入前检查当前项目的 `.dev-memory` 路径；不扫描其他项目。若初始化后被 `git add -f` 强制跟踪，返回 `tracked_memory_path`，停止新增私有写入，不修改 Git 历史。检查后由用户处理已跟踪文件；仅重新执行初始化无法抹去已提交内容。

若本地排除规则被移除，返回 `git_exclude_failed`，重新执行本页初始化命令恢复该项目的排除。无法检查 Git 状态时返回 `git_protection_unavailable`，修复 Git 环境后重试。项目失败不会把内容转写全局，独立全局结果仍单独报告。只读召回不增加这些写入检查。

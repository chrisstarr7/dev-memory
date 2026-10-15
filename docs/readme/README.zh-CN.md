<h1 align="center">dev-memory</h1>

<p align="center"><strong>让 AI 在新会话中继续使用开发习惯和项目规则。</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <strong>简体中文</strong> · <a href="../../docs/readme/README.ja.md">日本語</a> · <a href="../../docs/readme/README.ko.md">한국어</a></p>

Dev Memory 帮助 AI 编程助手从用户明确表达的要求、纠错和选择中学习可复用的开发习惯。项目规则保留在各自项目中，记忆、证据和修订记录存储在本地 SQLite。

## 它能做什么

- 形成可追溯、可纠正，并能在后续会话和项目中复用的开发习惯。
- 按当前任务少量召回相关习惯和已授权的项目规则。
- 一次性要求只在当前对话生效；新项目默认不新增项目记忆。
- 通过宿主指令运行 Skill 和本地 Python CLI；没有常驻进程、遥测或外部记忆服务。

## 快速开始

在需要配置的项目根目录执行。将 `codex` 替换为下表中对应的宿主参数：

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex
```

| AI 宿主 | 参数 |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness（DSH） | `deepseek` |

需要 Node.js 22+（含 npm/npx）、Git 和 Python 3.10+（含 sqlite3）。配置完成后，在该项目中开启新的 AI 会话即可正常开发，不需要每轮重复调用 Skill 或要求保存记忆。

对 Codex，这条命令会同时配置用户级全局习惯和当前项目绑定。其他宿主需要逐项目配置才能自动使用；目前只有 Codex 支持在未初始化项目中使用用户级引导。这里的 DeepSeek 指本地 DSH 宿主。

## 记忆范围与默认设置

| 记忆 | 示例 | 作用范围与默认设置 |
| --- | --- | --- |
| 全局开发习惯 | 复用合适的已有实现、依据证据排查、交付表达偏好 | 去除项目细节后跨项目使用；宿主配置授权后可进行合规的全局学习。 |
| 项目规则 | 业务约束、架构决策、接口约定 | 只在所属项目使用；新增项目记录需要 `full-project`。 |
| 一次性要求 | “这次不要运行测试” | 只在当前对话生效。 |

新项目默认使用 **`developer-first`**：可以读取已有项目规则，但不会新增项目记忆。切换到 `full-project` 后，才会新增长期项目记录。升级会保留已有数据和设置。

Codex 用户级引导可以在尚未初始化的项目中使用全局习惯，但不会初始化或记录该项目的业务内容。若另一个项目也需要独立记忆库和项目规则，请在该项目根目录执行安装命令。已初始化项目会一次性召回全局与当前项目记忆。

## 学习与召回流程

1. **召回：**任务开始、恢复或主题实质变化时，AI 有界查询少量相关记忆，并在上下文有效期间复用。
2. **学习：**明确适用于多个项目的偏好可以成为已确认习惯。重复反馈先形成未生效候选；两个真正独立任务的证据可以将其提升为软偏好。AI 总结和重复检索不算用户证据。
3. **纠正与整理：**新增前先检查现有记录；用户纠正时修订原习惯；在合适的任务节点进行有界整理。当前用户要求始终优先。

宿主支持异步子智能体时，只读评估可以与开发并行。主 AI 复核作用域、隐私和控制设置，负责写入，并在报告成功前核对存储回执。不支持委派时，由主 AI 自行评估。这是由宿主指令驱动的流程，不会持续监听对话。

## 控制记忆

| 目的 | 可以对 AI 说 |
| --- | --- |
| 开启项目记录 | “把当前项目切换到 full-project。” |
| 切回默认模式 | “把当前项目切回 developer-first。” |
| 修正习惯 | “修订这条习惯：符合当前需求时优先复用已有实现。” |
| 暂停全局学习，保留读取 | “暂停全局习惯写入，但继续读取。” |
| 本轮不记录 | “这一轮不要保存记忆。” |
| 查看或删除记录 | “查看相关记忆。” / “先预览删除范围，等我确认后再删除。” |

## 存储与隐私

| 存储 | 默认位置 |
| --- | --- |
| 用户全局习惯 | `~/.dev-memory/global/` |
| 当前项目规则 | `<项目根目录>/.dev-memory/` |

SQLite 是权威数据源，导出的 Markdown 仅供阅读。工作流程要求全局记录排除项目名称、业务细节、代码、路径、凭据和原始对话。程序会拦截已知的敏感信息和项目标记，但语义脱敏仍由 AI 负责。核心程序不上传记忆库、不收集遥测；交给云端模型处理的摘录遵循宿主的数据政策。

## 验证与文档

安装成功只表示配置完成，不代表真实宿主会话一定遵循引导。跨项目 Codex 使用、异步记录收尾和当前版本的任务总耗时仍需真实宿主验证。

[安装与卸载](../../docs/installation.md) · [架构](../../docs/architecture.md) · [记录协议](../../skills/dev-memory/references/protocol.md) · [验证报告](../../reports/verification.md) · [安全说明](../../SECURITY.md) · [贡献指南](../../CONTRIBUTING.md)

通过 [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues) 提交脱敏问题。本项目采用 [MIT License](../../LICENSE)。

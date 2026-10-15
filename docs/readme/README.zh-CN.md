<h1 align="center">dev-memory</h1>

<p align="center"><strong>以开发者为中心的本地 AI 研发习惯记忆系统。</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <strong>简体中文</strong> · <a href="../../docs/readme/README.ja.md">日本語</a> · <a href="../../docs/readme/README.ko.md">한국어</a></p>
<p align="center"><a href="#如何形成记忆">如何形成记忆</a> · <a href="#安装">安装</a> · <a href="#日常使用">日常使用</a></p>

Dev Memory 从开发者日常编码中的明确要求、纠错、技术决策和工作方式中，逐渐积累可追溯、可纠正、跨项目复用的个人研发习惯与思维偏好。配置宿主引导后，AI 可在不同项目和新会话中主动召回相关习惯，并用于问题分析、编码策略与交付流程。

## 如何形成记忆

1. **从用户反馈学习。** 明确适用于多个项目的习惯可直接形成确认规则；反复出现的反馈先形成候选，两个不同任务 ID 的证据可使其晋升为软偏好。AI 仍需判断任务与反馈是否真实独立、可复用。
2. **按当前任务采用。** AI 召回少量相关的有效习惯，结合条件与例外使用，并在任务内复用有效上下文。当前用户要求优先于推断的软偏好。
3. **依据纠正修订。** 新反馈修订已有习惯，保留来源与版本。程序检测完全重复，当前 AI 判断同义表达；AI 自己的总结和检索命中不增加用户证据。

| 开发者表达 | 处理方式 |
| --- | --- |
| “以后各项目改代码都先检查已有实现，再考虑新增。” | 明确的全局开发习惯 |
| 在独立任务中反复选择“先查实际证据，再修复” | 先形成候选，证据充分后成为软偏好 |
| “本项目不允许修改支付模块。” | 开启项目捕获后保存为项目约束 |
| “这次不要运行测试。” | 仅在当前对话生效，不写入记忆 |

## 安装

在项目根目录执行，将 `<agent>` 替换为下表参数：

```sh
npx -y --prefer-online chrisstarr7/dev-memory <agent>
```

| AI 宿主 | `<agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness（DSH） | `deepseek` |

需要 Node.js 22+（含 npm/npx）、Git 和 Python 3.10+（含 sqlite3）。安装器复制运行程序并配置所选宿主的项目指令，完成后**新建宿主会话**。已激活的项目共用当前用户的全局习惯，各项目记忆保持隔离。这里的 DeepSeek 指本地 DSH 宿主，网页或手机聊天无法执行安装。

**Codex 另支持用户级激活：** 执行一次下面的命令，即可通过用户指令在不同项目使用全局习惯，无需逐个初始化项目：

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex --user
```

用户级激活目前仅支持 Codex；其他宿主使用项目适配器。重复执行安装命令可更新受管理程序，保留本地记忆和无关用户指令。离线安装、宿主路径与卸载见 [安装指南](../../docs/installation.md)。

## 日常使用

配置完成后正常开发即可。当前 AI 从可见的用户反馈中提炼习惯，提交给本地程序保存；系统没有后台对话监听，也不另调用学习模型。

| 想控制什么 | 对 AI 说 |
| --- | --- |
| 纠正习惯 | “修订这条偏好：现有实现适合当前需求时才复用。” |
| 暂停学习 | “暂停全局习惯写入，仍可召回。” |
| 排除本轮 | “这一轮不要保存记忆。” |
| 遗忘习惯 | “预览这条习惯的删除范围，我确认后再删除。” |

Skill 只召回全局习惯和当前项目的长期规则。新项目默认采用 **`developer-first`**：已有项目规则仍可召回，新项目记忆默认不新增，除非用户启用 `full-project`。任务进度和断点不属于常规 Skill 流程；旧任务记录会保留，但普通召回和维护会排除它们。

## 本地存储与控制

| 记忆 | 默认位置 |
| --- | --- |
| 全局开发者习惯 | `~/.dev-memory/global/` |
| 项目规则与决策 | `<project-root>/.dev-memory/` |

SQLite 保存原子习惯、证据与修订，当前有效习惯共同组成工作画像。运行程序支持幂等写入、作用域隔离、备份、只读访问和受控遗忘。全局习惯信号需去业务化，项目名称、业务数据、代码、路径及原始对话不应进入全局库。核心程序不上传记忆、不收集遥测；模型处理遵循宿主的数据政策。

## 文档与验证

运行时使用 Python 标准库和 SQLite。程序测试、对话语义评估与真实宿主检查分别记录；安装成功证明配置完成，实际自动使用依赖宿主加载指令和 AI 遵循。真实 Codex 用户级指令在两个独立项目中的自动加载，以及禁用／原版／新版同任务性能对照仍未验证。

[架构](../../docs/architecture.md) · [协议](../../skills/dev-memory/references/protocol.md) · [验证报告](../../reports/verification.md) · [0.7.0 任务对照](../../reports/benchmark-0.7.0.md) · [安全](../../SECURITY.md) · [贡献](../../CONTRIBUTING.md)

通过 [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues) 提交脱敏问题。本项目采用 [MIT License](../../LICENSE)。

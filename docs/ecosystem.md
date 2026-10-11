# Agent Skills 生态调查与设计取舍

日期：2026-10-11。只采用官方规范、官方宿主文档和作者维护的仓库。路径/能力随版本变化；可安装不等于已验证自动记忆。

[Agent Skills 规范](https://agentskills.io/specification) 定义含 YAML `name`/`description` 的 `SKILL.md`，按需配 `scripts/`、`references/`、`assets/`；目录名应与技能名一致。`license`、`compatibility` 和 `metadata` 可选。宿主先读元数据，匹配后加载流程和需要的资源，适合短流程与按需参考文件。[OpenAI skills](https://github.com/openai/skills) 与 [Anthropic skills](https://github.com/anthropics/skills) 都采用 Skill 目录组合，外层还可容纳目录分组、模板和插件元数据。

| 宿主/入口 | 官方架构与安装方式 | 本工具采用 |
| --- | --- | --- |
| [Codex](https://developers.openai.com/codex/skills) | `.agents/skills`；可由内置 Skill Installer 下载 GitHub Skill；`agents/openai.yaml` 可选 | 标准基础 Skill，UI 元数据独立 |
| [OpenAI Plugins](https://developers.openai.com/plugins/build/plugins) | 根 `plugin.json`、`skills/`；可选 MCP/资产/扩展 | 最小可选 manifest；没有 MCP/自动 hooks 扩展，插件 E2E 未验证 |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills`、`~/.claude/skills` 或插件包装；有宿主扩展字段 | 标准字段，避免专有子代理/工具授权 |
| [Cursor](https://cursor.com/docs/skills) | `.agents/skills`、`.cursor/skills` 及用户目录 | 本地安装；远程/云端不自动取得本机私有库 |
| [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) | 项目/个人 Skill 目录；GitHub CLI 还有 `gh skill` 入口 | 基础目录，不声称云端可操作本机记忆 |
| [Gemini CLI](https://geminicli.com/docs/cli/skills/) | 原生 `gemini skills install` 可从 Git/目录安装 | 基础标准目录，自动适配另行验证 |
| [OpenCode](https://opencode.ai/docs/skills/) | Skill 文件夹，按需原生加载 | 独立 CLI，无宿主 SDK 依赖 |
| [Vercel skills](https://github.com/vercel-labs/skills) | `npx skills add owner/repo`；选择 Skill/Agent、项目/用户安装、复制/链接、升级/卸载 | 通用简易 GitHub 入口，只安装运行目录 |

Vercel 安装器支持众多 Agent，不证明各宿主都能运行 Python或每轮捕获。安装器有可关闭的匿名遥测，见其[源码](https://github.com/vercel-labs/skills/blob/main/src/telemetry.ts)；提供关闭方式和本地 Python 替代。`skills@1.7.2` [包元数据](https://github.com/vercel-labs/skills/blob/main/package.json)要求 Node >=22.20.0。安装器是下载工具，不是运行依赖。

开发模式采用：失败样例/合同 → 程序与 Skill 流程 → 临时库回归 → 模型语义评测 → 真实宿主 E2E → 白名单发布。CLI 负责确定性事务和隔离，当前 AI 负责语义，参考文件按需读取，Hook 单独适配。纯指令无法完成事务/删除/准确回执；无需因此引入后台服务或专有平台。

测试、语义评分和宿主事件分别记录；CI 不调用模型。A/B 显式运行并固定模型/思考/起点，记录延迟及约束遗漏。可参考 [OpenAI Skill evals](https://developers.openai.com/blog/eval-skills)。源码与分发采用同一运行目录，不生成各宿主分叉副本。格式能保证发现方式，权限和执行正确性仍须实测。

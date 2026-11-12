# dev-memory

**Local memory for your development habits and project rules.**

Dev Memory is a Skill plus a local Python program for AI-assisted development. It recalls relevant developer habits and authorized project rules at task start, and saves durable knowledge from real user requirements, corrections and choices. The assistant judges meaning; the program validates, stores and protects records in local SQLite.

The canonical, always current documentation is the [Chinese README](../../README.md). This page summarizes the essentials.

## Requirements

- **Node.js 22+** (npm/npx) and **Git** for the recommended install path.
- Windows x64 and macOS (Apple Silicon / Intel) prepare a dedicated Python 3.12 automatically; no system Python changes. macOS vectors require 13+.
- Linux and direct Python entrypoints need Python 3.10+ with sqlite3. See [installation details](../installation.md).

## Install

Run this from the root of a development project:

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex
```

Replace `codex` with the actual host: `claude`, `cursor`, `gemini`, `copilot`, `opencode`, or `deepseek`. Start a new AI session in that project afterwards; no per-turn invocation or "remember" phrase is needed. A Codex install also enables user-level global habits; other projects reuse them, and run the install command again in a project to enable project memory there. The installer places its own runtime under `~/.dev-memory/` (override with `DEV_MEMORY_HOME`); nothing is added to system Python, PATH, registry or shell config. Existing memories and controls are preserved on upgrade.

## What it remembers

| Scope | What fits | Example |
| --- | --- | --- |
| Global | Reusable habits that survive the project | Check for suitable existing code before adding a new implementation |
| Project | Durable rules, contracts, decisions and evidenced facts | API requirements, security boundaries, code conventions |

One-off requests, task progress and unconfirmed guesses stay in the conversation. Credentials are never stored. Global records are de-identified: no project names, business details, code, paths or raw dialogue. An explicit cross-project instruction becomes a confirmed rule immediately; a reusable choice without that scope is first saved as an inactive candidate and is promoted only with evidence from two independent tasks.

## Everyday flow

At task start (and after resume, compaction or context loss) the AI makes one focused `context` call with task terms and an optional intent. Keyword search always works; local semantic vectors join in when ready. When exact keyword matches already fill a scope's detail budget, the semantic pass is skipped (`lexical_sufficient`) to avoid a wasted model cold start. Ordinary recall never schedules background indexing: new writes are indexed from the save path, and historical backlogs use `vectors sync`. Budgets return at most 5 records / 4000 characters per combined call.

You can correct a memory in plain language: “把项目记忆里的默认表名改成‘核验登记’，其他条件不变。” The AI locates the record, revises it and reads back the result; a failed lookup never masquerades as a correction.

## Automatic organization

Changed records queue for review. A due notice appears at five distinct pending records, one body over 1200 characters, or an unreviewed change after seven days; the AI then reviews one bounded pack at a quiet boundary (8 records / 12000 characters). Archival requires explicit user request, proven falsity, or a passed expiry with a linked current replacement — never age, similarity or disuse alone.

## Local dashboard

```sh
npx -y --prefer-online chrisstarr7/dev-memory dashboard
```

Runs on demand at a localhost address with a private access token; `Ctrl+C` stops it. It can view memory text, evidence and revision history, search and filter, preview recall, manage registered projects, create backups, and inspect the vector index without starting inference. It never uploads memory.

## Controls and privacy

Tell the AI things like “暂停全局记忆写入，但继续读取”, “这一轮不要保存记忆”, “查看相关记忆”, or “删除前先预览影响范围”. Current instructions always win over recalled memory. Storage is local SQLite only; there is no telemetry and no automatic upload. Forgetting is a preview-and-confirm `forget` flow. See [SECURITY.md](../../SECURITY.md).

## Update and uninstall

```sh
npx -y --prefer-online chrisstarr7/dev-memory update codex
npx -y --prefer-online chrisstarr7/dev-memory uninstall codex
```

Uninstall removes the managed program and Codex user guidance/hooks; project guidance, stores and the shared Python runtime are preserved. Delete memories with the CLI `forget` flow. Upgrades quarantine unrecognized extra files next to the install instead of failing or overwriting them.

## References

- [Chinese README (canonical)](../../README.md) · [installation and uninstall](../installation.md)
- [operation protocol](../../skills/dev-memory/references/protocol.md) · [vector runtime](../../skills/dev-memory/references/vectors.md)
- [architecture](../architecture.md) · [verification](../../reports/verification.md) · [security](../../SECURITY.md)

Report de-identified issues through [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues); never attach databases, credentials or raw conversations.

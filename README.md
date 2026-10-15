<h1 align="center">dev-memory</h1>

<p align="center"><strong>Local memory for development habits and project rules.</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><strong>English</strong> · <a href="docs/readme/README.zh-CN.md">简体中文</a> · <a href="docs/readme/README.ja.md">日本語</a> · <a href="docs/readme/README.ko.md">한국어</a></p>

Dev Memory helps an AI coding assistant learn reusable development habits from visible user requirements, corrections and choices. It keeps project rules in their owning projects and stores records, evidence and revisions locally in SQLite.

## What it does

- Learns traceable, correctable habits that can be reused in later sessions and projects.
- Recalls a small set of relevant habits and authorized project rules for the current task.
- Keeps one-time directions in the conversation; new project memory is off by default.
- Runs as a host-guided Skill with a local Python CLI. It has no daemon, telemetry or external memory service.

## Quick start

Run this from the root of the project you want to configure. Replace `codex` with the host parameter in the table below:

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex
```

| AI host | Parameter |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness (DSH) | `deepseek` |

Requirements: Node.js 22+ with npm/npx, Git, and Python 3.10+ with sqlite3. After setup, start a new AI session in that project and work normally; no repeated Skill invocation or save request is needed.

For Codex, the command configures both user-level global habits and the current project's binding. Other hosts need project setup for automatic use; only Codex currently supports user-level guidance across uninitialized projects. DeepSeek here means the local DSH host.

## Memory scope and defaults

| Memory | Examples | Scope and default |
| --- | --- | --- |
| Global habits | Reuse suitable existing code; diagnose from evidence; preferred response order | Reused across projects after removing project details. Eligible global capture requires an authorized setup. |
| Project rules | Business constraints, architecture decisions, interface agreements | Available only in the owning project. New project records require `full-project`. |
| One-time directions | “Skip tests this time” | Current conversation only. |

New project stores use **`developer-first`**: existing project rules can be recalled, but new project records are off. Use `full-project` to enable new durable project records. Existing settings and data are preserved during upgrades.

Codex user-level guidance can use global habits in an uninitialized project without initializing or capturing that project's business memory. To give another project its own store and project rules, run the setup command from that project's root. Initialized projects make one combined global/project recall.

## How learning and recall work

1. **Recall:** At task start, resume, or a meaningful topic change, the assistant makes one bounded, focused lookup and reuses valid results while working.
2. **Learn:** Explicit cross-project preferences can become confirmed habits. Repeated feedback starts as an inactive candidate; two genuinely independent tasks can promote it to a soft preference. AI summaries and repeated retrieval do not count as user evidence.
3. **Correct and organize:** The assistant checks existing records before adding, revises habits when corrected, and performs bounded cleanup at suitable task boundaries. Current user instructions take priority over remembered preferences.

When the host supports asynchronous subagents, a read-only reviewer can assess potential memory while development continues. The primary assistant checks scope, privacy and controls, performs all writes, and verifies the store receipt before reporting success. Without delegation, the primary assistant does the assessment. This is a host-guided workflow, not continuous conversation monitoring.

## Control memory

| Goal | Tell the assistant |
| --- | --- |
| Enable project records | “Switch this project to full-project memory capture.” |
| Return to the default mode | “Switch this project to developer-first.” |
| Correct a habit | “Revise that habit: reuse existing code when it fits the requirement.” |
| Pause global learning, keep recall | “Pause global habit writes, but keep recall.” |
| Exclude this turn | “Do not save memory from this turn.” |
| Inspect or forget a record | “Show relevant memories.” / “Preview deletion scope, then delete after I confirm.” |

## Storage and privacy

| Store | Default location |
| --- | --- |
| User's global habits | `~/.dev-memory/global/` |
| Current project's rules | `<project-root>/.dev-memory/` |

SQLite is authoritative; exported Markdown is a reading view. The workflow excludes project names, business details, code, paths, credentials and raw conversations from global records. The program rejects known sensitive and project-specific markers, but semantic de-identification remains the assistant's responsibility. The core does not upload stores or collect telemetry. Excerpts processed by a hosted model follow that host's data policy.

## Verification and documentation

Installation confirms configuration, not that a real host session follows it. Cross-project Codex behavior, asynchronous capture completion and current-version total task latency still need real-host verification.

[Installation and removal](docs/installation.md) · [Architecture](docs/architecture.md) · [Protocol](skills/dev-memory/references/protocol.md) · [Verification reports](reports/verification.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

Report sanitized issues at [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues). Released under the [MIT License](LICENSE).

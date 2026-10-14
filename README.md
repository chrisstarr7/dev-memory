<h1 align="center">dev-memory</h1>

<p align="center"><strong>A developer-centered local memory system for AI development habits.</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><strong>English</strong> · <a href="docs/readme/README.zh-CN.md">简体中文</a> · <a href="docs/readme/README.ja.md">日本語</a> · <a href="docs/readme/README.ko.md">한국어</a></p>
<p align="center"><a href="#how-it-works">How it works</a> · <a href="#installation">Installation</a> · <a href="#everyday-use">Everyday use</a></p>

Dev Memory learns from the requirements, corrections, technical decisions and working methods you express during everyday coding. It builds traceable, correctable habits and reasoning preferences that can be reused across projects. With host guidance configured, your AI assistant can recall them in a new project or session and apply them to analysis, implementation and delivery.

## How it works

1. **Learn from your feedback.** Explicit cross-project preferences can become confirmed rules. Repeated feedback first forms a candidate; evidence from two distinct task IDs can promote it to an active soft preference. The assistant must judge whether those tasks and feedback are genuinely independent and reusable.
2. **Recall for the task.** The assistant retrieves a small set of relevant active habits and applies their conditions and exceptions. It reuses valid context within the task; current user instructions take priority over soft preferences.
3. **Revise with evidence.** Corrections update existing habits, preserving their sources and revision history. Exact duplicates are detected locally; the current assistant judges equivalent wording. AI summaries and retrieval hits add no user evidence.

| What you express | How it is treated |
| --- | --- |
| “Across my projects, check existing code before adding another implementation.” | Confirmed global habit |
| Repeatedly choosing evidence-based diagnosis in separate tasks | Candidate, then a soft preference when supported |
| “Do not modify this project's payment module.” | Project constraint, when project capture is enabled |
| “Skip tests this time.” | Temporary task instruction |

## Installation

Run from the project root. Replace `<agent>` with a parameter from the table:

```sh
npx -y --prefer-online chrisstarr7/dev-memory <agent>
```

| AI host | `<agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness (DSH) | `deepseek` |

Requires Node.js 22+ with npm/npx, Git, and Python 3.10+ with sqlite3. The installer copies the runtime and configures the selected host's project instructions. **Start a new host session after setup.** Activated projects share the same user's global habits while keeping their project stores separate. DeepSeek here means the local DSH host; web and mobile chats cannot run the installer.

**Codex also supports user-level activation:** run the following once to use global habits across projects without initializing each project:

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex --user
```

User-level activation currently supports Codex only. Other hosts use their project adapters. Repeating the install command updates the managed runtime; local memories and unrelated user instructions are preserved. Offline installation, host paths and removal are in the [installation guide](docs/installation.md).

## Everyday use

Develop normally after setup. The assistant interprets visible user feedback in the current conversation and submits supported habits to the local program. There is no background conversation monitor or separate learning model.

| To control memory | Tell your assistant |
| --- | --- |
| Correct a habit | “Revise that preference: reuse existing code only when it fits the requirement.” |
| Pause learning | “Pause global habit writes, but keep recall.” |
| Exclude a turn | “Do not save memory from this turn.” |
| Forget a habit | “Preview the deletion scope for this habit; delete it after I confirm.” |

New project stores default to **`developer-first`**: global habits are the focus, existing project rules remain recallable, and new project business records and checkpoints are disabled. Ask the assistant to switch the installed CLI to `full-project` when you want those optional records; see the [mode instructions](docs/installation.md). Ordinary development uses bounded recall and batches new feedback rather than rebuilding the whole profile.

## Local storage and control

| Memory | Default location |
| --- | --- |
| Global developer habits | `~/.dev-memory/global/` |
| Optional project rules and task checkpoints | `<project-root>/.dev-memory/` |

SQLite stores atomic habits, evidence and revisions; the working profile consists of the current effective habits. The runtime supports idempotent writes, isolation, backup, read-only access and controlled forgetting. Global habit signals must be de-identified; project names, business data, code, paths and raw conversations do not belong there. The core uploads no memory and collects no telemetry; model processing follows the host's data policy.

## Documentation and verification

The runtime uses Python's standard library and SQLite. Program checks, semantic evaluation and real-host checks are reported separately. Successful installation confirms configuration; automatic use depends on the host loading instructions and the assistant following them. Real two-project Codex user-level activation and a matched disabled/old/new performance comparison remain unverified.

[Architecture](docs/architecture.md) · [Protocol](skills/dev-memory/references/protocol.md) · [Verification](reports/verification.md) · [0.7.0 task comparison](reports/benchmark-0.7.0.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md)

Report sanitized issues at [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues). Released under the [MIT License](LICENSE).

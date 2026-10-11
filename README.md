<h1 align="center">dev-memory</h1>

<p align="center">
  <strong>Private local memory for AI coding assistants.</strong><br />
  Recall constraints. Save corrections. Resume real progress.
</p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><strong>English</strong> · <a href="docs/readme/README.zh-CN.md">简体中文</a> · <a href="docs/readme/README.ja.md">日本語</a> · <a href="docs/readme/README.ko.md">한국어</a></p>

<p align="center"><a href="#quick-start">Quick start</a> · <a href="#features">Features</a> · <a href="#how-memory-works">How it works</a></p>

<p align="center"><kbd>Codex</kbd> · <kbd>Claude Code</kbd> · <kbd>Cursor</kbd> · <kbd>Gemini CLI</kbd> · <kbd>GitHub Copilot</kbd> · <kbd>OpenCode</kbd> · <kbd>DeepSeek Harness</kbd></p>

---

## Quick start

Run this in the **root of the project you want to develop**:

```sh
npx -y chrisstarr7/dev-memory codex
```

Use `claude`, `cursor`, `gemini`, `copilot`, `opencode`, or `deepseek` (DeepSeek Harness / DSH) instead of `codex` for another assistant. The same command works on macOS, Linux, and Windows.

**Requirements:** Node.js 22+ with npm/npx, Git, and Python 3.10+ with sqlite3. The installer downloads the program, checks the environment, initializes an empty project store, and configures the assistant's project instructions.

After installation succeeds, **start a new AI session in that project and develop normally**. No enable phrase, explicit Skill invocation, or repeated save/recall request is needed. Existing sessions must restart to load the new instructions.

Run the same command to upgrade or initialize another project. Upgrades preserve existing memories, unrelated project instructions, and paused settings. Each project needs its own initialization; explicitly confirmed global preferences can be shared.

<details>
<summary>Ask your local AI to install it</summary>

> Install dev-memory from https://github.com/chrisstarr7/dev-memory and initialize the current project for this AI host. Check the success receipt and preserve existing memories and settings.

The AI needs local file and command access. A web-only chat cannot install software on your computer. Offline installation, installation without Node.js, and uninstallation are covered in the [installation guide](docs/installation.md).

</details>

## Features

| Capability | What it does |
| --- | --- |
| Accurate constraints | Keeps conditions, exceptions, prohibitions, and verification steps; corrections revise the existing rule. |
| Real task checkpoints | Records completed work, unfinished work, blockers, and the next step. Each task has one current checkpoint. |
| Project isolation | Project A's business stays in A. Only explicitly confirmed cross-project preferences and methods belong globally. |
| Selective recall | Retrieves applicable global, current-project, and current-task records; reuses valid context and invalidates it after changes. |
| Deduplication and compaction | Intercepts exact duplicates; the current AI compares paraphrases and shortens related records while preserving constraints and evidence. |
| Local control | Supports inspection, correction, turn opt-out, pause, read-only recall, archive, and forget. |

An independent Agent Skill plus a small Python CLI: standard library and SQLite, with no daemon, vector service, or additional paid model. Program and protocol are public; each installer's memory is private and local. New stores contain no demo records.

## Everyday use

Describe your development work normally. The initialized assistant recalls relevant constraints, saves explicit corrections promptly, batches ordinary changes at turn end, and checks actual code before resuming a saved checkpoint.

| To control memory | Tell your AI |
| --- | --- |
| Correct a business condition | “Change the refund deadline to 14 days after delivery.” |
| Save a global preference | “This development convention applies to all my projects; save it globally.” |
| Skip this turn | “Do not save memory from this turn.” |
| Pause / resume writes | “Pause memory writes for this project, but keep recall.” / “Resume memory writes.” |
| Use read-only recall | “Recall memory only; do not write anything this turn.” |
| Forget a record | “Preview the forget scope for this rule; delete it after I confirm.” |

Examples are fictional and are never imported automatically. No hand-written JSON is needed; the AI uses the [local protocol](skills/dev-memory/references/protocol.md). A save claim requires a successful per-store receipt.

## How memory works

1. **Recall:** at task start/resume or project/module changes, one call returns relevant records and pending maintenance. Normal startup avoids repeated host probes.
2. **Capture:** the current AI extracts meaning; the CLI validates scope, source, revision, and transaction boundaries. No increment produces a short checked NOOP receipt.
3. **Organize:** compare related records, retire equivalent duplicates, and compact long bodies while retaining conditions, exceptions, negation, version boundaries, and sources.
4. **Continue:** preserve one current checkpoint per task and keep older checkpoints as history. Source edits/deletion invalidate dependent summaries.

### Maintenance defaults

| Trigger or limit | Default |
| --- | --- |
| Distinct changed records pending in one store | **5 records** |
| A pending record's body length | **1,200 characters** |
| A related batch in each store | Up to **8 records / 12,000 characters** |
| Each development turn | At most **one batch**, within the current AI turn |
| Recall and maintenance SQL budget | **500 ms**; report deferred work on timeout |

Thresholds are separate for global and project stores. NOOPs and repeated checks do not accumulate changes. Session/task boundaries can check unfinished topics once; startup work is not repeated. No pending change means no maintenance. Pause, read-only, and turn opt-out suppress it. There is no background timer, per-tool summary, or full-library sweep.

Reuse valid memory and the loaded protocol. Context compaction, memory revision, and workspace changes invalidate reuse. Recall reserves capacity for project constraints; overflow is reported as incomplete and critical missing constraints require follow-up. Stores commit separately and report success or failure independently.

Retired originals and old bodies remain traceable history. Compaction reduces active context, **not total disk usage**. Semantic uncertainty leaves the original record intact.

## Architecture and storage

```mermaid
flowchart TD
    I[One-time project initialization] --> A[AI coding assistant]
    A --> S[Agent Skill: workflow and boundaries]
    S --> C[Python CLI: routing and validation]
    H[Optional host adapter] --> C
    C --> G[Global SQLite store]
    C --> P[Current project SQLite store: project and task]
    G --> GV[On-demand Markdown view]
    P --> PV[On-demand Markdown view]
```

| Scope | Contents | Default location |
| --- | --- | --- |
| `global` | Explicitly confirmed cross-project development preferences, conventions, and methods | `~/.dev-memory/global/` |
| `project` | The owning project's business, architecture, interfaces, constraints, decisions, and defect lessons | `<project-root>/.dev-memory/` |
| `task` | Temporary requirements, progress, blockers, and next steps | Inside the owning project's store |

Each store has separate transactions, evidence, receipts, views, and backups. Project writes never fall back to global storage. Scope follows content and user intent, not just the working directory; business without an identified project never goes global.

Runtime files live in `skills/dev-memory/`; installation entry points are `bin/install.cjs` and `install.py`. `docs/`, `tests/`, `evals/`, and `reports/` contain documentation, isolated tests, evaluation tools, and evidence. See the [architecture guide](docs/architecture.md).

## Compatibility and verification

| Mode | Behavior / status |
| --- | --- |
| Base mode | The AI calls the Skill and CLI; installing the Skill alone does not guarantee execution each turn. |
| Default project guidance | Initialization configures host-native project instructions for ordinary development tasks. It depends on the host loading instructions and the model following them. |
| Optional event mode | Codex hooks require host trust and event verification; the real hook delivery chain remains unverified. |
| Read-only mode | Recall existing records without initialization or writes. |
| Unavailable | Missing permissions or inaccessible storage are reported honestly. |

Program tests and packaging CI passed on Ubuntu/macOS with Python 3.10/3.14. Six installation targets passed isolated GitHub installation and repeat-install checks; successful installation does not prove automatic behavior on every host. Real Codex CLI evidence, host versions, semantic checks, and outstanding S01–S48 scenarios are listed in the [verification report](reports/verification.md). DSH has program installation and published-provider checks; a full DeepSeek model session remains unverified. See [DSH results](reports/deepseek.json).

**Performance remains a measured limitation.** The latest full workflow comparison is a partial 0.4.0 sample: about 52–53 seconds with memory off versus 86–89 seconds on. Version 0.5.0 reduces startup/repeated reads, but its new matched comparison was blocked by host credits. No claim of negligible delay is made. See the [lifecycle review](reports/lifecycle-review.md).

## Privacy and safety

- Release packages contain no real memories, author data, or automatically seeded examples.
- The core program does not upload memory or collect telemetry. AI model calls follow the host's configuration and data policies.
- Program files and runtime data are separate. Upgrades and default uninstallation preserve memory; project memory is excluded from Git by default.
- Do not store credentials, passwords, full sensitive logs, or unnecessary customer data. Credential detection does not replace semantic minimization.
- Historical memory cannot override current instructions or safety rules. Local stores have no default application encryption.
- Forget removes tool-managed data; it cannot clean host chats, external copies, or system snapshots and does not promise secure erasure.

See [SECURITY.md](SECURITY.md) and the [adversarial review](reports/adversarial-review.md).

## Contributing and support

Use [Issues](https://github.com/chrisstarr7/dev-memory/issues) for bugs and ideas, and Pull Requests for improvements. Share sanitized minimal reproductions, never real memory stores. Development and evaluation guidance: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Copyright © 2026 dev-memory contributors. Released under the [MIT License](LICENSE).

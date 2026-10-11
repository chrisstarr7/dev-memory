# Installation

## Python installer

Requires Python 3.10+ with `sqlite3`. Download/extract or clone this repository, then run at its root:

```sh
python3 install.py --agent codex
```

On Windows, use `py -3 install.py --agent codex` when that launcher provides the required Python. Supported selectors are listed below. An explicit `--target /path/to/dev-memory` overrides the host destination.

The installer copies a fixed runtime whitelist, uses an atomic directory swap and refuses unmanaged/extra/symlinked files on replacement. It does not initialize memory or change hooks by default. Tests, evaluations and reports are not installed. This local installer has no network or telemetry.

## skills CLI

As an alternative, install directly from GitHub:

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 add chrisstarr7/dev-memory --skill dev-memory -g
```

Select your own agent. A noninteractive Codex copy on macOS/Linux:

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 add chrisstarr7/dev-memory --skill dev-memory -g -a codex --copy -y
```

Change `codex` to the matching agent selector below. From a downloaded repository root, use `.` as the source instead. The skills CLI also accepts GitHub tree URLs for reviewed tags or commits. Use one manager for each installation.

The tested `skills@1.7.2` requires Node >=22.20.0 and npm. Python remains required at runtime. `--copy` avoids symlink privileges. The external installer contacts npm and, for remote sources, GitHub; it supports telemetry opt-out through `DISABLE_TELEMETRY` or `DO_NOT_TRACK`. dev-memory itself does not upload memory or collect telemetry. On Windows PowerShell:

```powershell
$env:DISABLE_TELEMETRY = '1'
npx skills@1.7.2 add chrisstarr7/dev-memory --skill dev-memory -g -a codex --copy -y
```

## Installation directories and status

| Host selector | Python installer user destination | Runtime status |
| --- | --- | --- |
| codex | `~/.agents/skills/dev-memory/` | Base CLI tested on macOS; optional hook protocol tested; trusted host delivery unverified |
| claude-code | `~/.claude/skills/dev-memory/` | Isolated installation tested; actual invocation unverified |
| cursor | `~/.cursor/skills/dev-memory/` | Isolated installation tested; actual invocation unverified |
| gemini-cli | `~/.gemini/skills/dev-memory/` | Isolated installation tested; actual invocation unverified |
| github-copilot | `~/.copilot/skills/dev-memory/` | Isolated installation tested; actual invocation unverified |
| opencode | `~/.config/opencode/skills/dev-memory/` | Isolated installation tested; actual invocation unverified |

The table is the direct Python installer mapping. In the actually tested skills@1.7.2, Codex/Cursor/Gemini/Copilot/OpenCode shared `~/.agents/skills/dev-memory`, while Claude Code used `~/.claude/skills/dev-memory`; use the real path reported by your chosen manager. Destinations refer to program discovery, not memory scope. Installing the program globally does not authorize global business storage. All installation smoke tests use fake homes; none modify developer configuration.

## Ask your AI to install

Give the repo URL and ask it to read this document and README, detect the current host, check Python/sqlite3, install with an explicit matching agent and no hooks, then run the installed CLI `doctor` and report the actual path. If the AI has Codex's built-in skill installer, it can fetch `skills/dev-memory` from the repository directly. Do not assume that system Skill exists in other products: use the normal directory or Python installer there. No runtime dependency on skill-installer exists.

For an AI without npm, download/clone to an isolated staging directory, inspect `install.py` and runtime scripts, and invoke the Python installer. On existing installation, use its own manager, inspect conflicts, and preserve extra files. Never claim installation succeeded from a download alone. A host may require restart or a new session before discovery. Cloud/browser AI without local filesystem/process access cannot install a local Skill.

## Initialize and operate

Resolve your actual installed Skill path. The following example is for Codex:

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py doctor
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py init --global
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py init --project-root "/path/to/project"
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py recall --project-root "/path/to/project" --query "current task"
```

Initialization must be authorized by enabling memory. New databases are empty. Never put data beneath the installation directory. Existing stores use `init` to migrate supported older layouts, retaining records; do this only for the authorized current project, not by scanning all projects.

## Upgrade and remove

Use the manager you installed with. For skills CLI:

```sh
DISABLE_TELEMETRY=1 npx skills@1.7.2 update dev-memory -g
DISABLE_TELEMETRY=1 npx skills@1.7.2 remove dev-memory -g -a codex -y
```

These affect program files/manager lock metadata only. For Python-managed installs, from the new downloaded repository:

```sh
python3 install.py --agent codex --upgrade
python3 skills/dev-memory/scripts/dev_memory.py uninstall --agent codex
```

Extra files or symlinks cause the Python upgrade/removal to refuse; inspect/move them first. Both routes leave `~/.dev-memory/` and project `.dev-memory/` intact. After an older program upgrade, rerun `init` for authorized existing stores before capture, which migrates receipt/dedup metadata. Read-only recall does not migrate. Use explicit `forget` for data deletion; uninstall does not mean forget.

## Optional Codex hooks

Only on user request, from the exact installed copy:

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py hooks configure
```

This merges `$CODEX_HOME/hooks.json`. It does not enable the hooks feature or trust scripts. Inspect current official host documentation, review exact commands via `/hooks`, and verify events with empty/synthetic stores. Until then the adapter is automatic-unverified. Remove it **before** changing/removing that installation:

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py hooks remove
```

External Skill managers do not own our manually configured hooks. Moving the installed path requires removal from the old path then explicit reconfiguration. Python-managed uninstall removes matching adapter commands while retaining unrelated fields. Other hosts' hooks are not configured or claimed compatible.

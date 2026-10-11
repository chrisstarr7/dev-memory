# Codex adapter behavior

The adapter targets the documented command-hook protocol and does not install itself unless explicitly requested.

| Event | Work |
| --- | --- |
| `SessionStart` (`startup`) | Returns only the short protocol; avoids a pre-prompt recall that would consume the new session's cache. |
| `SessionStart` (`resume`, `compact`) | Forces a bounded recall of global preferences, hard project constraints, and task checkpoints. |
| `UserPromptSubmit` | Checks current module/worktree/data revision and retrieves from global plus only the bound current project when the signature changed. Unchanged contexts return a cached receipt without re-reading memory rows. The query is an empty, stable baseline; the AI explicitly queries a new task/topic. Prompt text is inspected only for conservative private-turn suppression and is not persisted. |
| `Stop` | Checks receipts only for initialized, writable stores. Missing receipt yields at most one block/continuation; `stop_hook_active` prevents recursion. No recovery occurs in capture-disabled stores. |

An explicit opt-out phrase can create a receipt containing only opaque session/turn IDs; this blocks recovery without saving prompt text. The phrase match is conservative and may mark quoted examples as private for that turn; this only suppresses memory capture.

## Configure

`python3 <installed-skill>/scripts/dev_memory.py hooks configure` adds only this adapter's `SessionStart`, `UserPromptSubmit`, and `Stop` handlers to `$CODEX_HOME/hooks.json` (default `~/.codex/hooks.json`). It preserves other JSON fields/handlers, refuses malformed configuration and refuses to merge when inline TOML hooks are present. It does not enable the Codex hooks feature or trust the scripts. Review exact commands and approve trust through the host's `/hooks` flow. Only then can this be described as configured automatic mode; a successful end-to-end session is still separately required before claiming verified automation.

The handler timeout is 2 seconds. On storage/query errors, the adapter emits no successful receipt and does not block normal work. Stop recovery is one retry per hook cycle, not a background worker. If the host omits required session/turn IDs or does not support these events, use basic/manual mode and don't report automatic coverage.

No hook integration was installed during this build. The CLI version inspected was Codex `0.155.1`; real hook delivery, trust UI, event ordering and token/context latency remain unverified on this machine.

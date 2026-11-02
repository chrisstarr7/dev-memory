# Optional Codex adapter

Hooks are not installed by default. Normal automatic use comes from host-native project/user instructions and the primary AI following the Skill.

| Event | Work |
| --- | --- |
| `SessionStart` startup | Returns concise workflow guidance; no store read. |
| `SessionStart` resume/compact | Tells the primary AI to force one focused global/project recall after context loss; it does not save conversation progress. |
| `UserPromptSubmit` ordinary prompt | No lookup, Git probe, cache write or receipt. |
| `UserPromptSubmit` direct correction, durable requirement or verified claim | With stable host session/turn IDs, returns a content-free capture-review hint. The primary AI still checks eligibility, scope, evidence, duplicates, revisions and all controls; the hook does not save memory or assert tool verification. |
| `UserPromptSubmit` recognized private-turn request | Saves only opaque suppression IDs in applicable initialized stores. Unknown IDs/storage are reported honestly; no prompt is retained. |
| Old `Stop` registrations | Harmless no-op. Reconfiguration removes only this adapter's old Stop handler. No compulsory NOOP or recovery turn. |

`hooks configure` merges owned SessionStart/UserPromptSubmit handlers into `$CODEX_HOME/hooks.json` and preserves unrelated configuration. It refuses malformed JSON or conflicting inline TOML hooks. The host must support these events, enable the feature and trust the command; configuration alone proves none of those. `hooks remove` removes only owned handlers.

Handlers have a two-second host timeout. The conservative phrase recognizer may suppress a quoted opt-out example; semantic opt-outs are also handled by the primary AI. High-value routing deliberately skips examples, quoted/code blocks, temporary requests, oversized prompts and events without stable IDs. Misses fall back to the normal Skill assessment. Capture completion and successful per-store receipts remain the primary AI's responsibility. There is no transcript monitor, stored prompt, extra summary model or background worker. Configure only on a supported host, then review the exact commands through its normal trust interface; installation never writes hook trust or enables hooks by default. Historical 0.8.0 program tests did not establish real delivery; see the current source report for separately observed trusted events.

The separate `evals/check_host_delivery.py` acceptance tool exercises actual Codex startup, process restart/resume and context compaction without hooks. It checks new memory bodies and independently generated artifacts after each event. That establishes the instruction-driven path on the tested host/model, not trusted-hook delivery or every future turn. Run it only for explicit integration acceptance; see [verification](verification.md#startup-resume-and-compaction-acceptance).

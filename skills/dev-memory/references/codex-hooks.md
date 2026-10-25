# Optional Codex adapter

Hooks are not installed by default. Normal automatic use comes from host-native project/user instructions and the primary AI following the Skill.

| Event | Work |
| --- | --- |
| `SessionStart` startup | Returns concise workflow guidance; no store read. |
| `SessionStart` resume/compact | Tells the primary AI to force one focused global/project recall after context loss; it does not save conversation progress. |
| `UserPromptSubmit` ordinary prompt | No lookup, Git probe, cache write or receipt. |
| `UserPromptSubmit` recognized private-turn request | Saves only opaque suppression IDs in applicable initialized stores. Unknown IDs/storage are reported honestly; no prompt is retained. |
| Old `Stop` registrations | Harmless no-op. Reconfiguration removes only this adapter's old Stop handler. No compulsory NOOP or recovery turn. |

`hooks configure` merges owned SessionStart/UserPromptSubmit handlers into `$CODEX_HOME/hooks.json` and preserves unrelated configuration. It refuses malformed JSON or conflicting inline TOML hooks. The host must support these events, enable the feature and trust the command; configuration alone proves none of those. `hooks remove` removes only owned handlers.

Handlers have a two-second host timeout. The conservative phrase recognizer may suppress a quoted opt-out example; semantic opt-outs are also handled by the primary AI. Capture completion and successful per-store receipts remain the primary AI's responsibility. There is no transcript monitor or background worker. Real trusted hook delivery for 0.8.0 has not been verified by configuration/program tests.

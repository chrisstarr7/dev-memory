# Project initialization

Preferred online entrypoint: run `bash -o pipefail -c 'curl -fsSL --max-time 30 https://raw.githubusercontent.com/chrisstarr7/dev-memory/main/install.py | python3 - "$@"' -- codex` in the user's business project root, selecting the actual host. Add `--json` to inspect the receipt, or `--project /absolute/project/path` when invoking from another directory. No manual repository download is required. The bootstrap checks the public snapshot manifest before running the shared source installer, removes temporary source files, and preserves existing memory and user controls on repeated installation.

This explicit command authorizes default project memory and merges host-native startup instructions. No chat enable phrase or repeated Skill invocation is needed. Start a new host session to load new instructions; existing sessions may cache startup instructions. Offline source entrypoint remains `python3 install.py codex --project /absolute/project/path`.

From an installed Skill, use `python3 <skill>/scripts/dev_memory.py setup --agent codex --project-root /absolute/project/path`. The project argument defaults to the current working directory for this explicit command, including non-Git projects. Never run it in a downloaded package or unrelated project accidentally.

Host files: Codex uses existing nonempty root `AGENTS.override.md` when present, otherwise `AGENTS.md`; Claude Code uses `CLAUDE.local.md`; Cursor uses `.cursor/rules/dev-memory.mdc` with `alwaysApply: true`; Gemini uses `GEMINI.md`; Copilot uses `.github/copilot-instructions.md`; OpenCode uses `AGENTS.md`. Existing content outside the managed block is preserved. No override is created that would hide existing team instructions. The files contain only the generic protocol; private runtime paths stay in the project's Git-excluded activation manifest. Existing tracked instructions can show a managed block change in Git; review it normally.

Inspect `status`, each `stores` result, and `activation`. A failure may leave one initialized store or installed program; it does not certify enabled memory. Project write failures do not route project content globally. Setup is idempotent and preserves namespace, data, paused and read-only settings. Do not use setup to undo a user's pause.

`doctor --project-root ...` reports `project_activation` separately from event hooks. Configuration never certifies actual host loading, per-turn execution, or model compliance. Initializing another project is a separate explicit action. Enabling memory in A does not authorize capture in B or make A's business global.

The low-level `init --global --project-root ...` command only creates stores; it does not install host instructions. It remains available for programmatic tests and specialized integrations. Read-only recall creates neither store nor instruction files.

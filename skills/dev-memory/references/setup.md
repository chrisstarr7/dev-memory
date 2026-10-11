# Project initialization

Preferred entrypoint from the downloaded repository: `python3 install.py codex --project /absolute/project/path` (select the actual host). It installs/checks the runtime, initializes independent empty global and project stores, and merges a managed block into the host's automatically loaded project instructions. This explicit command authorizes default project memory. No chat enable phrase or repeated Skill invocation is needed. Starting a new host session loads the new instructions; existing sessions may have cached their startup instructions.

From an installed Skill, use `python3 <skill>/scripts/dev_memory.py setup --agent codex --project-root /absolute/project/path`. The project argument defaults to the current working directory for this explicit command, including non-Git projects. Never run it in a downloaded package or unrelated project accidentally.

Host files: Codex uses existing nonempty root `AGENTS.override.md` when present, otherwise `AGENTS.md`; Claude Code uses `CLAUDE.local.md`; Cursor uses `.cursor/rules/dev-memory.mdc` with `alwaysApply: true`; Gemini uses `GEMINI.md`; Copilot uses `.github/copilot-instructions.md`; OpenCode uses `AGENTS.md`. Existing content outside the managed block is preserved. No override is created that would hide existing team instructions. The files contain only the generic protocol; private runtime paths stay in the project's Git-excluded activation manifest. Existing tracked instructions can show a managed block change in Git; review it normally.

Inspect `status`, each `stores` result, and `activation`. A failure may leave one initialized store or installed program; it does not certify enabled memory. Project write failures do not route project content globally. Setup is idempotent and preserves namespace, data, paused and read-only settings. Do not use setup to undo a user's pause.

`doctor --project-root ...` reports `project_activation` separately from event hooks. Configuration never certifies actual host loading, per-turn execution, or model compliance. Initializing another project is a separate explicit action. Enabling memory in A does not authorize capture in B or make A's business global.

The low-level `init --global --project-root ...` command only creates stores; it does not install host instructions. It remains available for programmatic tests and specialized integrations. Read-only recall creates neither store nor instruction files.

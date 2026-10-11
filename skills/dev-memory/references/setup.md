# Setup and lifecycle

Resolve the Skill directory from the loaded `SKILL.md`. Use `python3 <skill-dir>/scripts/dev_memory.py`; on Windows use `py -3` if that is the available Python 3.10+ launcher. Python must include sqlite3. No API key, npm package or daemon is required by the runtime.

Run `doctor` read-only first. Installation never imports or creates memories. When the user has enabled development memory, initialize an empty global store with `init --global`, and the authorized owning project with `init --project-root <root>`. These are idempotent and also perform supported schema migrations. A project initialization adds a verified local Git exclude rule; tracked memory paths fail safely. A non-Git project needs an explicit root. Do not initialize or change configs for read-only use.

A missing store stays unavailable until initialized. Do not report an unavailable store as checked. A user enabling memory in a project authorizes ordinary scoped writes there; explicit global rules still need genuine cross-project user confirmation.

Programs and data are separated. Default global data: `~/.dev-memory/global/`; project and task data: `<root>/.dev-memory/`. Set `DEV_MEMORY_HOME` for a different global parent; it does not redirect project data. Never put memory inside the Skill installation.

The GitHub repo includes `docs/installation.md`; Skill managers install only this runtime folder. Use the same manager for updates/removal. A manager update/removal does not handle manually configured Codex hooks: run `hooks remove` from this exact installed Skill first. Pure Python managed installation may use `install --upgrade --target <skill-dir>` and `uninstall --target <skill-dir>`; extra or symlinked files block destructive replacement. After upgrading an older schema, rerun `init` for each authorized existing store before writing. Do not traverse other projects to migrate them.

Only configure the Codex adapter when asked: `hooks configure` modifies `$CODEX_HOME/hooks.json`. It preserves unrelated entries and does not enable features, trust scripts or extend permissions. Real event delivery and `/hooks` approval must still be confirmed. Other hosts remain base mode.

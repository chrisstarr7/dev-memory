# Architecture

The portable Skill, deterministic local program, optional host integration and private data have separate responsibilities. Python 3.10+ and SQLite are the runtime dependencies; the current AI supplies semantic judgment.

## Components

| Component | Location | Responsibility |
| --- | --- | --- |
| Skill | `skills/dev-memory/SKILL.md` | Recall triggers, scope, capture policy and user controls |
| CLI | `skills/dev-memory/scripts/dev_memory.py` | Commands, project binding, routing, installation and JSON results |
| Store | `skills/dev-memory/scripts/dev_memory_store.py` | Validation, transactions, provenance, revisions, retrieval, summaries, views and deletion |
| Project initializer | `skills/dev-memory/scripts/dev_memory_setup.py` | Merge automatically loaded host instructions and private project bindings; preserve existing user controls |
| Codex adapter | `skills/dev-memory/scripts/codex_hook.py` | Optional event processing and bounded receipt repair; actual event delivery requires host verification |
| References | `skills/dev-memory/references/` | Apply protocol, lifecycle, adapter contract and verification limits |
| Configuration | `skills/dev-memory/assets/config.example.json` | Empty template; contains no memories |
| npx entry | `bin/install.cjs`, `package.json` | GitHub package transport, interpreter check, original-project binding; delegate to the shared Python installer |
| Installer | `install.py` | Fetch and validate a bounded online snapshot when executed remotely; reuse the local runtime installer and project initializer |
| Release builder | `build_release.py` | Package the public whitelist with SHA-256 hashes, excluding runtime data |

`agents/openai.yaml` supplies optional Codex UI metadata. `plugin.json` is an optional plugin descriptor; marketplace installation has not been verified. Neither is required by the CLI. Tests, evaluations, reports and repository docs remain outside the installed runtime Skill.

The recommended `npx -y chrisstarr7/dev-memory codex` entry uses npm’s [GitHub package spec](https://docs.npmjs.com/cli/v11/using-npm/package-spec/) and [single-bin command selection](https://docs.npmjs.com/cli/v11/commands/npm-exec/). Its public npm pack whitelist contains the launcher, shared installer and runtime files; it has no dependencies or lifecycle scripts. Installation captures the caller’s business directory and delegates to the same Python implementation. npx caching/transport has npm’s own policies and is not used for memory processing. The Python online alternative uses HTTPS and a single GitHub source snapshot. Before executing its source installer, it checks every manifest file's SHA-256, ZIP paths and types, duplicate entries, size limits and required files. The manifest establishes snapshot consistency, not an independent signature. Only public source is staged in a temporary directory and cleaned up; private stores and bindings use their normal scope-specific paths. Network reads and installer execution are bounded; failures have nonzero exits and never certify completion. The current business directory is captured before staging and passed explicitly to setup.

## Storage boundaries

```text
User home
└── .dev-memory/global/
    ├── memory.sqlite3       # Confirmed cross-project development memory
    └── ...                  # Global-only configuration, views and backups

Project A
└── .dev-memory/
    ├── memory.sqlite3       # A's project and task memory
    └── ...                  # A-only configuration, views and backups

Project B
└── .dev-memory/
    ├── memory.sqlite3       # B's project and task memory
    └── ...                  # B-only configuration, views and backups
```

There is no global database containing all projects. Recall opens the applicable global store and explicitly bound/current project, selecting the applicable task. It does not scan other projects. Task records have a task ID inside their owning project's database.

The AI chooses scope from meaning and ownership; the CLI enforces declared scope, provenance and project identity. Global capture requires explicit cross-project confirmation. Business discussed outside its directory still belongs to its project. Unbound business remains in the conversation until ownership is known. A project write failure cannot redirect its data into the global store.

Each database contains its own records, evidence, revisions, retrieval terms, derivation edges and receipts. SQLite is authoritative; Markdown is a rebuildable view. `DEV_MEMORY_HOME` changes only the global data parent. Different clones/worktrees have independent project stores by default. AI hosts used by the same local user share that user's stores at these paths.

## Data flow

1. **Check**: `doctor` reports capabilities without initializing stores. Plain installation copies programs only; online installation (current project), source `install.py --project` or installed `setup` explicitly authorizes project memory and merges automatically loaded host instructions. Startup instructions load the Skill without a chat invocation.
2. **Recall**: a focused query, project/task identity and context state select applicable memory. The AI compares it with current instructions and authoritative project evidence.
3. **Judge**: within the current turn, the AI identifies new requirements, corrections, decisions or actual progress. Desired behavior, observed facts, preferences and hypotheses remain distinct.
4. **Apply**: the AI submits structured operations and sources. The CLI validates, checks revision conflicts and deduplicates. Global and project batches use separate transactions and results; one call can succeed in one store and fail in the other.
5. **Acknowledge**: saved content has a successful receipt. Checked turns with no increment have a short NOOP receipt. Missing checks and failed writes retain their actual status.
6. **Continue**: checkpoints describe completed work, unfinished work, blockers, next steps and workspace/code boundaries. New sessions recall the checkpoint.

An AI restatement or retrieval hit is not new user evidence. A passed test requires an actual tool result. The program validates source structure but cannot prove that an AI's semantic interpretation is true.

## Revisions and derived memory

Corrections revise an existing rule with its expected revision, preserving conditions, exceptions, negative requirements and verification steps. Repeated violations require checking recall, execution and expiry rather than appending duplicates.

Summaries refer to source IDs and expected revisions within one scope. Source revision or deletion invalidates related summaries. Cross-project reuse requires a de-identified proposal and explicit user confirmation before creating global memory.

## Lightweight operation

- Recall at task start/resume, project/module/topic changes and relevant rule changes. Reuse context while query, task, workspace and store state remain valid.
- Force recall after compaction/resume; inspect incomplete results before acting on key constraints. Cache metadata cannot prove that conversation content survived compaction.
- Save explicit corrections promptly; batch ordinary changes at turn end. Do not summarize after every tool call or start a default second AI turn.
- NOOP writes only the necessary receipt. Consolidation handles changed related sources. Markdown views are exported on demand.
- Optional receipt repair is bounded to one attempt with timeouts. There is no background worker.

Database speed alone does not establish AI workflow latency. Historical model A/B measurements and their version boundary are in [verification](../reports/verification.md); this version has no newly completed model A/B run.

## Trust and lifecycle

Opt-outs, pause state and deletion suppression constrain later processing. Credentials, full sensitive logs and unnecessary customer data must be removed before submission; deterministic filters are incomplete. Memory is historical data below current instructions and safety policy, never permission to execute commands or upload information.

Upgrade/removal preserves global and project data. Hosts control Skill discovery, process permissions and event trust. The Codex adapter has synthetic protocol checks; trusted automatic event delivery remains unverified. Host-native project instruction formats are configured for six hosts; actual no-invocation host behavior is reported separately from installation and hook event enforcement.

See [installation](installation.md), [protocol](../skills/dev-memory/references/protocol.md), [verification](../reports/verification.md) and [security](../SECURITY.md).

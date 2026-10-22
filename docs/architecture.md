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
    ├── memory.sqlite3       # Developer habits and preferences; explicit or evidence-backed soft rules
    └── ...                  # Global-only configuration, views and backups

Project A
└── .dev-memory/
    ├── memory.sqlite3       # A's durable project rules; older task records may remain
    └── ...                  # A-only configuration, views and backups

Project B
└── .dev-memory/
    ├── memory.sqlite3       # B's durable project rules; older task records may remain
    └── ...                  # B-only configuration, views and backups
```

There is no global database containing all projects. Normal Skill recall opens only the applicable global store and current project store; it passes `--exclude-task`, so session bindings and legacy task records do not enter context. It does not scan other projects. Existing task records and low-level task APIs are retained for backward compatibility, but the Skill neither reads nor writes them.

The AI chooses between global habits and durable project rules; the CLI enforces declared scope, provenance and project identity. The primary AI assesses potential increments in its existing task reasoning; no secondary reviewer/model call is required. A host-provided asynchronous reviewer is optional for an ambiguous set of signals or a substantive cleanup when useful work overlaps. It has no memory-store access and cannot write. If delegated, before the final response the primary AI joins that review, validates user controls, privacy, scope and source independence, applies eligible records and checks commit receipts. If delegation is unavailable or fails, the primary AI completes the assessment; finishing coding first does not discard pending capture. A reasoned finding of no eligible memory needs no write. Storage failure gets a bounded repair and an honest unsaved status, never a false completion claim. Explicit important corrections are captured before affected edits. Independent, de-identified feedback may be promoted to a soft preference after two task signals, using opaque task IDs only to deduplicate. Business rules and one-time directions never become global habits. New project stores use `full-project`: supported durable project knowledge is captured automatically. Upgrades preserve existing capture modes and privacy controls; `developer-first` still blocks new project writes until an explicitly authorized mode switch. A user-level Codex activation shares only global habits across projects. Temporary task progress stays in the conversation.

Each database contains its own records, evidence, revisions, retrieval terms, derivation edges and receipts. SQLite is authoritative; Markdown is a rebuildable view. `DEV_MEMORY_HOME` changes only the global data parent. Different clones/worktrees have independent project stores by default. AI hosts used by the same local user share that user's stores at these paths.

## Data flow

1. **Check**: `doctor` reports capabilities without initializing stores. The recommended Codex installation configures user-level global habits and the current project together; other hosts use project adapters. Codex success requires both activation receipts. Existing controls and data are preserved. In initialized projects, one combined recall replaces a separate user-level recall; elsewhere only global habits are recalled. Startup instructions load the Skill without a chat invocation.
2. **Recall**: one `context --exclude-task --intent INTENT --query TASK_TERMS` call combines focused global/project recall with a metadata-only maintenance check. Intent expands indexed topic/body wording in English and Chinese without category filtering. Normal startup does not probe host versions, initialize stores or create a receipt. `doctor` remains an environment/integration diagnostic. The AI compares memory with current instructions and authoritative project evidence.
3. **Judge**: the primary AI identifies new requirements, corrections and decisions. Assessment normally stays in the primary AI; an optional read-only host reviewer can assess complex signals in parallel; it cannot read or write memory, and project evidence never becomes global evidence. Desired behavior, observed facts, preferences and hypotheses remain distinct. If delegated, the primary AI joins that assessment before final delivery.
4. **Apply**: the AI submits structured operations and sources. The CLI validates, checks revision conflicts and deduplicates. A read-only `match` returns bounded related candidates when existing context is insufficient; identical text reuses a rule automatically, paraphrases require the current AI's semantic review. Global and project batches use separate transactions and results; one call can succeed in one store and fail in the other.
5. **Acknowledge**: final delivery follows capture review and confirmation of all required per-store commit receipts. A completed subagent or launched command is not a successful write. No extra write is required for a confirmed no-increment turn. Missing checks and failed writes retain their actual status; bounded repair does not imply success.
6. **Maintain**: changed global/project IDs queue within their owning store. Five pending IDs, a 1200-character body or an unreviewed change waiting seven days yield a metadata-only due notice. The assistant fetches a pack only at a quiet boundary, or an explicit caller requests maintenance bodies. The Skill's context maintenance excludes legacy task records. The primary AI reviews at most one batch at a natural task boundary; `MERGE_DUPLICATES`, `RETAG`, `COMPACT` and `MAINTENANCE_REVIEW` use current revision guards. No background maintenance model, full-library sweep or recursive maintenance.

The AI maps applicable recalled rules to a concrete design/code decision and regression check before edits. Optional `USE` operations in the ordinary apply batch report the rule revision and action reference. They add no memory/evidence and are explicitly AI reports, not independent behavioral proof. Evaluation checks task outcomes separately. Candidate directories help choose relevant missing records without reading every unrelated body; omitted constraints remain marked incomplete.

Thresholds start a store-local maintenance cycle that drains on later normal interactions until idle, including a final one-to-four-record tail. Existing session/turn receipts suppress additional packs after maintenance that turn. `context`/`maintain` accept the same session/turn IDs to honor this bound and opt-outs. Each pack remains capped at 8 records/12000 characters. Idle turns return no bodies; a turn during active cleanup may process one topic. Maintenance itself has no background worker or extra model round; optional read-only capture review is a separate host capability, not a default round.

An AI restatement or retrieval hit is not new user evidence. A passed test requires an actual tool result. The program validates source structure but cannot prove that an AI's semantic interpretation is true.

## Revisions and derived memory

Corrections revise an existing rule with its expected revision, preserving conditions, exceptions, negative requirements and verification steps. Repeated violations require checking recall, execution and expiry rather than appending duplicates.

Summaries refer to source IDs and expected revisions within one scope. Source revision or deletion invalidates related summaries. Duplicate aliases retain original sources; later alias revisions invalidate the canonical rule and its summaries. Compaction retains the old body and all structured constraints/evidence. Merged originals become superseded and leave default recall. Logical cleanup reduces active context, not audit disk size; there is no automatic history retention cap. An explicit `storage` command accounts for local bytes; `--reclaim` removes disposable cache/retired search terms and reclaims free pages. User-selected `--backup-keep N` retains validated same-store backups; it never prunes evidence, revisions, opt-outs or idempotency receipts. Confirmed forget includes connected alias sources and derived history, and restore retains suppression. Global habits require explicit cross-project user instructions or de-identified direct feedback stored as an inactive candidate and promoted after two independent task signals; the AI judges independence.

## Lightweight operation

- Recall at task start/resume, project/module/topic changes and relevant rule changes. Reuse context while query, task, workspace and store state remain valid.
- Reuse loaded Skill/protocol instructions within the current runtime/context. Default combined recall reserves 60% of body characters and three of five details for global habits, and 40%/two details for project constraints. Fixed budgets remain cache-stable; the one-detail special case reserves project safety.
- Candidate SQL reads a sentinel beyond the limit. Overflow remains incomplete and cannot be cached as complete. Batch `show --ids ... --current` retrieves up to eight current records/12000 characters without old audit bodies. Full single-record `show` remains available for explicit provenance inspection.
- Concrete lexical matches rank before intent-only matches and unrelated hard-rule fallback; indexed term rarity reduces generic-word noise. Up to eight unloaded candidate descriptors use a separate 2000-character store budget; they contain directory metadata, not complete business constraints. Current records retain code/source references for targeted checks.
- Force recall after compaction/resume; inspect incomplete results before acting on key constraints. Cache metadata cannot prove that conversation content survived compaction.
- Git dirty-path or bounded non-Git metadata traversal overflow makes the workspace fingerprint unknown. Unknown workspaces are not cached and are not labeled currently verified. The fingerprint is a bounded metadata check, not a cryptographic snapshot of every source file.
- Recall and maintenance SQL have a 500 ms progress budget; term-led recall uses the term index and interruption returns deferred/incomplete. This does not bound process startup, SQLite lock waiting, Git calls or model reasoning. Failures never become successful recall or write claims.
- Save explicit corrections promptly; batch ordinary changes at turn end. A host subagent can assess capture while coding continues; join it before final delivery and confirm required writes. Without delegation, the primary AI assesses the increment directly.
- No-op turns do not make a separate write. Consolidation handles changed related sources. Markdown views are exported on demand.
- Optional Codex hooks provide startup/invalidation guidance and private-turn suppression, with no ordinary prompt recall or compulsory Stop receipt/NOOP recovery. Storage save repair is bounded to one attempt. The local program has no background worker or capture evaluator; parallel assessment is supplied by the host and is read-only. When unavailable, the primary AI performs assessment.

Database speed alone does not establish AI workflow latency. Historical model A/B measurements and their version boundary are in [verification](../reports/verification.md); the 0.4.0 A/B attempted 12 tasks, with 8 completed and 4 host exits. Memory-on completed tasks took materially longer. It is a small prepublication sample, not a frozen final-source or latency-free claim. The 0.5.0 matched comparison was blocked by an actual workspace-credit rejection; its local scale probe and two project-A host cycles do not establish a total-task speed improvement. See the [lifecycle review](../reports/lifecycle-review.md).

## Trust and lifecycle

Opt-outs, pause state and deletion suppression constrain later processing. Credentials, full sensitive logs and unnecessary customer data must be removed before submission; deterministic filters are incomplete. Memory is historical data below current instructions and safety policy, never permission to execute commands or upload information.

Upgrade/removal preserves global and project data. Hosts control Skill discovery, process permissions and event trust. The Codex adapter has synthetic protocol checks; trusted automatic event delivery remains unverified. Host-native project instruction formats are configured for seven hosts; actual no-invocation host behavior is reported separately from installation and hook event enforcement.

See [installation](installation.md), [protocol](../skills/dev-memory/references/protocol.md), [verification](../reports/verification.md) and [security](../SECURITY.md).

The 0.8.0 review and validation evidence is in [workflow optimization](../reports/optimization-0.8.0.md).

The [0.8.2 capture review](../reports/capture-review-0.8.2.md) separates first-signal persistence from automatic adoption. Direct user requirements, confirmations and corrections can start a candidate; one controlled task reference counts once across source types. A read-only match never saves evidence. Runtime/version, user binding and candidate/active counts are available through an explicit diagnostic, without adding calls to the normal task path.

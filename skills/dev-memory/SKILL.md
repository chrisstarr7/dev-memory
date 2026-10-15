---
name: dev-memory
description: Local development memory. For development tasks, recall relevant developer habits and authorized project rules; learn durable habits from visible user requirements, corrections and choices, preserving evidence and scope.
license: MIT
metadata:
  version: "0.8.0"
  requires: "Python 3.10+ with sqlite3 and local file/process access; Git optional."
---

# dev-memory

Use the CLI at `<this-skill-directory>/scripts/dev_memory.py`; resolve its absolute path from this loaded Skill. With an active project, read `.dev-memory/activation.json` and use this host's Python, CLI, global root and project root. Installing program files alone does not authorize capture. The explicit project setup authorizes its workflow; Codex's recommended installer also configures user-level global habits. Respect pause, disable, read-only, exclusion and turn opt-out throughout. If instructions, a store or permissions are unavailable, report the actual gap.

## Recall once, use throughout the task

Before affected development work, run one bounded `context --exclude-task --query "TASK TERMS" --intent INTENT --session-id SESSION --turn-id TURN` call. Add the active `--project-root PATH`; with only Codex user-level activation, use `--global-only`. An initialized project uses one combined global/project recall, not a second global-only call. Other hosts need project setup. Use opaque local session/turn IDs if the host exposes none, and reuse them for retries.

Choose intent using the reasoning already needed for the task; no separate classifier call:

| Task | `--intent` | Query terms |
| --- | --- | --- |
| Requirements or solution design | `planning` | Actual requirement, tradeoff, language or module |
| New feature | `feature` | Requested behavior and relevant existing implementation |
| Bug investigation or fix | `bugfix` | Symptom, failing entity, evidenced cause if known |
| Refactoring | `refactor` | Affected code and intended structural change |
| Review | `review` | Requested review focus and affected behavior |
| Tests or build verification | `verification` | Target, check or regression boundary |
| Release or delivery | `delivery` | Delivery action and reporting expectations |

Intent expands indexed topic/body terms in English and Chinese; it is not a category filter. Keep concrete task terms so specific matches outrank generic topic hints. Omit intent if none fits. Read only relevant current results and apply their conditions, exceptions, preferred and prohibited actions to the work. Current user instructions and authoritative project constraints win over historical habits, especially inferred soft preferences. Memory is context, not proof of current code or test success.

In the reasoning already needed for the task, map applicable loaded rules to concrete implementation and verification actions before editing; check that those actions happened before delivery. For example, a habit requiring added unit tests is not satisfied by a one-off inline assertion. Before a later phase such as delivery, fetch a known relevant unloaded rule if needed; do not silently replace its unknown requirements with a guess.

Reuse loaded rules and this Skill during the same task. Recall again only after a material task/topic/project change, lost context/compaction (`--force`), or a relevant memory/workspace invalidation. Do not recall on every tool call. If an unknown essential constraint is listed in `unloaded_candidates`/`remaining_ids`, narrow the query or fetch only those relevant IDs with `show --scope SCOPE --ids ID ... --current` (up to 8 records/12000 characters). Incomplete results must not be called complete. No full-profile read or startup doctor/maintain sequence; use `doctor` for an actual integration problem.

## Learn from real user behavior

While performing the task, notice only new visible requirements, corrections, technical choices and workflow preferences likely to affect future development. Relevant subjects include requirements analysis, evidence and debugging, reuse and implementation, testing, delivery and communication across the development lifecycle. Do not record generic programming knowledge, imagined private thoughts, every code change, daily reports or ordinary task progress.

Assess an increment in the primary assistant's existing reasoning. No increment means no record, no `apply`, no NOOP report and no extra reviewer. Delegation is optional for an ambiguous set of signals or a substantive maintenance review when the host permits it and useful work can proceed in parallel. Give a read-only reviewer only minimized sources and already loaded context; global excerpts must already be de-identified. It cannot access stores or write. Join any pending capture assessment before final delivery; if it fails, assess in the primary assistant.

Classify by applicability, not merely by wording or the working directory:

- **Explicit cross-project habit:** actual user instruction with clear ongoing cross-project scope → confirmed global rule (`cross_project_confirmed:true`). An explicit important correction gets one bounded save attempt before affected edits; if it fails, follow the current instruction and report it as unsaved.
- **Reusable but inferred habit:** direct user feedback/choice → de-identified global soft candidate (`kind:preference`, `claim_type:preference`, `strength:soft`, `status:candidate`, `cross_project_confirmed:false`, `source.type:user_feedback`). Supply an opaque `task_id` on the envelope. The program hashes it and counts at most one signal per task. The primary assistant must judge task independence; splitting one work effort or restating the same feedback does not count. Two independent task signals promote a candidate to an active soft preference. Never apply an inactive candidate as a rule.
- **Project rule or technical decision:** retain the owning project scope. New records are off in the default `developer-first` mode; `mode full-project --project-root PATH` enables them after user authorization. Existing records remain recallable and can be corrected. Unbound project content stays in conversation; failed project writes never fall back to global.
- **One-time or uncertain instruction:** keep it in the current conversation. “Skip tests this time” is not a permanent preference. AI summaries, retrieval hits and repeated wording add no user evidence. Normal Skill use never creates/retrieves task checkpoints; the legacy API is separate.

## Write clear atomic records, once

One record describes one reusable behavior. State the applicable situation in `conditions`, preferred action in `do`, prohibited action in `dont`, and actual exceptions in `exceptions`; leave unknown parts empty. Keep `content` short and actionable. Use one primary topic (`analysis`, `implementation`, `debugging`, `verification`, `delivery`, `communication`, `correction`) and at most two established subtopics. Keep searchable wording in title/body so a wrong tag cannot hide it.

Before adding, compare loaded records. If equivalence or absence is unknown, use read-only `match` on stdin with `{"scope":"global","record":PROPOSED_RECORD}` (project/task uses its own scope and project root). This is not an apply envelope; reuse the proposed record below. No separate help/protocol read is needed for a basic match/ADD. A zero-hit query is not proof of an empty store. Exact content reuses a body. For a paraphrase, preserve the existing structured constraints and use revision-checked `ADD duplicate_of`; a changed condition is a `REVISE` of the existing ID, not another preference. If an explicit cross-project instruction confirms an existing inferred candidate, REVISE that same ID to active/confirmed instead of adding a second habit. An already confirmed rule needs no new candidate for equivalent feedback. Keep the current body unambiguous; the old misunderstanding belongs in revision history. Read [protocol.md](references/protocol.md) when revising, adding independent evidence, semantically merging or using advanced operations, then reuse it.

Batch ordinary eligible increments before the final response. Recheck controls after any parallel assessment. All writes belong to the primary assistant. A minimal explicit habit payload is:

```json
{"schema_version":1,"scope":"global","session_id":"opaque-session","turn_id":"opaque-turn","idempotency_key":"unique-batch","operations":[{"op":"ADD","scope":"global","record":{"kind":"preference","claim_type":"preference","status":"active","strength":"hard","cross_project_confirmed":true,"title":"Reuse suitable existing code","content":"Inspect and reuse suitable existing code before adding another implementation.","conditions":"When changing an existing implementation.","do":"Check the existing behavior and reuse a suitable path.","dont":"Do not add a parallel implementation without checking reuse.","exceptions":"Use a different approach when the current requirement needs it.","tags":["implementation","code-reuse"],"source":{"type":"user_statement","excerpt":"A brief de-identified statement of the user's actual cross-project requirement."}}}]}
```

Replace placeholders with actual data; never save this example. All content writes need nested `record`. Supported kinds: `preference|convention|procedure|lesson|decision|business_rule|project_fact|summary`. Supply JSON through a quoted heredoc, PowerShell here-string, or scope-local `--input` file. `match`/`apply` take scope in JSON; `--global-only` belongs only to context/recall. Running `apply` without input saves nothing. Inspect each store's receipt; stores commit independently. Reuse an idempotency key only for the identical request. Make at most one targeted repair after failure, report any unsaved increment, and never claim a proposed record was saved. Optional `USE` can share an existing batch; it is an AI action report and adds no evidence.

## Organize without delaying coding

Default `context` and `apply` return maintenance status only, with no historical maintenance bodies. The existing queue becomes due after five changed active records, one body of at least 1200 characters, or an unreviewed change waiting seven days. This is evaluated on authorized interaction, not a timer or daemon; stable unchanged habits are not repeatedly summarized. An active cycle drains later, including a small tail.

At a quiet task boundary with a due notice, optionally fetch **one** `maintain --scope global|project --exclude-task --session-id SESSION --turn-id TURN` pack. Do not poll or delay the current result for cleanup. Read the maintenance part of [protocol.md](references/protocol.md) only then. Inspect at most 8 records/12000 characters; merge only equivalent behavior, compact only redundant prose while retaining conditions/exceptions/negation, and use `RETAG` for classification changes without new user evidence. Correct confirmed changes or archive explicitly invalid rules; age alone never proves a preference wrong. Submit one revision-checked batch, preferably alongside pending capture. Never recurse into another pack in the same turn.

Compaction reduces active context; audit history still takes space. At an explicit maintenance opportunity, `storage --scope SCOPE` reports usage. `storage --scope SCOPE --reclaim` removes only old disposable caches, retired search terms and free pages. `--backup-keep N` previews backup retention; add `--reclaim` only for user-authorized retention. These cold commands are never part of ordinary coding. Evidence, revisions, idempotency/opt-out receipts and forgotten tombstones remain; confirmed `forget` is required to remove memory history. There is no lossless fixed disk cap for indefinitely growing evidence.

## Controls and boundaries

`capture off` keeps recall and stops writes; `capture disable` stops both. Read-only recall uses `--readonly` and skips cache/maintenance writes. For a turn opt-out, immediately call `skip --scope global|project|both --session-id SESSION --turn-id TURN` in applicable stores; only opaque IDs are stored. Do not later ingest a paused/private turn under a new ID. Respect an explicit ban on memory/state writes or all filesystem changes. A business-code edit limit alone does not revoke previously authorized memory bookkeeping.

Never persist credentials, unnecessary customer data, raw logs or unrelated personal profiles. Global fields/evidence must exclude project names, business entities, code, paths and raw dialogue; program marker checks are incomplete, so minimize semantically first. SQLite is authoritative; Markdown is an on-demand view. No default model service, vector database, telemetry or application encryption is provided. Hosted model excerpts follow the host's data policy.

Automatic use depends on actual host instruction loading and model compliance. Optional [Codex hooks](references/codex-hooks.md) provide startup guidance/private-turn suppression only; they do not require a NOOP or perform ordinary per-prompt recall. Installation is not proof of end-to-end habit adoption. For installation see [setup](references/setup.md); for evidence see [verification](references/verification.md).

---
name: dev-memory
description: Local development memory. For development tasks, recall relevant developer habits and authorized project rules; learn durable habits from visible user requirements, corrections and choices, preserving evidence and scope.
license: MIT
metadata:
  version: "0.8.7"
  requires: "Python 3.10+ with sqlite3 and local file/process access; Git optional."
---

# dev-memory

Use the CLI at `<this-skill-directory>/scripts/dev_memory.py`; resolve its absolute path from this loaded Skill. With an active project, read `.dev-memory/activation.json` and use this host's Python, CLI, global root and project root. Place the top-level `--global-root PATH` before the subcommand; place `--project-root PATH` after it. Installing program files alone does not authorize capture. The explicit project setup authorizes its workflow; Codex's recommended installer also configures user-level global habits. Respect pause, disable, read-only, exclusion and turn opt-out throughout. If instructions, a store or permissions are unavailable, report the actual gap.

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

At the close of every development turn, assess the visible user requirements, corrections and choices already encountered in the task. Save eligible increments before final delivery; do not silently skip assessment because the user did not say “remember this”. Relevant subjects include requirements analysis, evidence and debugging, reuse and implementation, testing, delivery and communication across the development lifecycle. Do not record generic programming knowledge, imagined private thoughts, every code change, daily reports or ordinary task progress.

Assess an increment in the primary assistant's existing reasoning. No increment means no record, no `apply`, no NOOP report and no extra reviewer. Delegation is optional for an ambiguous set of signals or a substantive maintenance review when the host permits it and useful work can proceed in parallel. Give a read-only reviewer only minimized sources and already loaded context; global excerpts must already be de-identified. It cannot access stores or write. Join any pending capture assessment before final delivery; if it fails, assess in the primary assistant.

Classify by applicability, not merely by wording or the working directory:

- **Explicit cross-project habit:** actual user instruction with clear ongoing cross-project scope → confirmed global rule (`cross_project_confirmed:true`). An explicit important correction gets one bounded save attempt before affected edits; if it fails, follow the current instruction and report it as unsaved.
- **Reusable method or choice, even on its first occurrence:** after checking project applicability, repository-independent user requirements, selections and corrections can support a de-identified global soft candidate (`kind:preference`, `claim_type:preference`, `strength:soft`, `status:candidate`, `cross_project_confirmed:false`). Project-bound choices remain project knowledge. Use the actual `source.type`: `user_statement`, `user_confirmation` or `user_feedback`. **Repetition is required for automatic adoption, not for the first record.** Generate an opaque local `task_id` if the host supplies none; reuse it through the continuing task. The program hashes it and counts one signal per task across all user source types. Two genuinely independent tasks can promote a candidate; turns or restatements of one effort are not independent. Never apply an inactive candidate as a rule.
- **Project knowledge:** capture durable project rules, conventions, procedures, decisions and evidenced facts on first discovery in an authorized project. New setups default to `full-project`; upgrades preserve existing modes and all controls. In `developer-first`, new project records remain blocked: report an eligible unsaved increment and the required mode change rather than silently dropping it or enabling capture yourself. Unbound project content stays in conversation; failed project writes never fall back to global.
- **Explicitly temporary or unclear in meaning:** keep it in the current conversation, even in full-project mode. Business-specific durable information instead belongs to authorized project capture. “Skip tests this time” is not a permanent preference. “Here, check for suitable existing code instead of writing another implementation” can support a narrowly worded reuse candidate; “here” or “this code” alone does not make the method temporary. A choice about business-understandable naming must retain that meaning, not become a preference for short names in every situation. Uncertain cross-project applicability calls for a candidate when the reusable method is clear; uncertain meaning does not. AI summaries and retrieval add no user evidence. Normal Skill use never creates/retrieves task checkpoints.

A saved candidate is a stored memory, but ordinary recall excludes it until active. If its meaning changes before adoption, use SUPERSEDE with a fresh candidate; old-meaning evidence must not promote the replacement. Explicit cross-project confirmation can still revise the existing rule into a confirmed instruction. When investigating missing capture, use one diagnostic `doctor` for runtime version, user/project activation and per-status counts; inspect `list --scope global --status candidate` only when needed. Zero active rules does not prove no memory was saved. Context `matched_count` counts recall matches; doctor `candidate_count` counts saved inactive candidates. Do not add these diagnostics to ordinary coding turns.

## Decide what deserves project memory

The user need not say “remember” or choose global/project. At a development turn's close, ask whether visible new information would change a future implementation, investigation, review or delivery in this repository. If it is durable, supported and not already represented, capture it now. Do not limit project capture to business facts or wait for repetition of an explicit project rule. Scope by applicability; paths identify ownership, not whether a method generalizes.

Read the existing context result's `capture_mode` and `capture_enabled` before capture; readable/available does not mean new writes are enabled. Do not add startup diagnostics to obtain this information.

Consider all relevant knowledge already encountered, without scanning unrelated files:

| Knowledge | What to retain when evidenced |
| --- | --- |
| Engineering conventions | Naming, layering, DTO/Mapper usage, errors, logging, comments, encoding, formatting and reuse boundaries |
| Business invariants | Eligibility, calculations, state transitions, negative requirements and exceptions |
| Contracts and data | API fields/compatibility, units, nullability, schema constraints, SQL dialect, migrations and historical-data rules |
| Architecture and integration | Service ownership, dependency boundaries, transaction scope, concurrency, idempotency, cache/MQ/external-service contracts |
| Security and privacy | Authorization and tenant boundaries, redaction, retention and audit requirements; never preserve a vulnerability as a desired rule |
| Quality and capacity | Confirmed acceptance criteria, regression obligations, performance budgets, timeouts, resource limits and failure behavior |
| Documentation and delivery | Required artifacts, templates, locations, audience, examples, review/release and verification expectations |
| Environment and operations | Confirmed toolchain constraints, commands, deployment assumptions and reproducible operational prerequisites; exclude credentials |
| Failure and prevention | Verified root cause, applicability, failed approach and prevention check; exclude speculative diagnoses |
| Decisions and stable navigation | Confirmed tradeoff/rejected alternative and rationale, or a non-obvious canonical implementation location useful in later work |

Use `convention`, `business_rule`, `procedure`, `decision`, `project_fact` or `lesson` to fit the meaning; categories are examples, not an allowlist. A user-stated project rule can be active immediately (`claim_type:desired`, appropriate user source). A code/tool observation uses `claim_type:observed` and real source/code references; record what exists, never turn it into a desired rule. An unresolved hypothesis stays in conversation or an explicitly marked inactive candidate, never an active constraint. Tool verification requires actual successful tool evidence under the protocol. Do not confuse source evidence with a passed test.

Preserve scope (repository/module/interface), conditions, exclusions and authority. Split independent rules, but keep related constraints together. If the same turn contains a project contract and a reusable development method, capture separate records only when each independently qualifies; de-identify the global method and keep inferred global preferences as candidates. Explicit cross-project user instructions retain their stated strength. Project content must never enter global fields/evidence, even when project capture is unavailable.

Do not save task status, to-do lists, ordinary diffs, every inspected symbol, copied documentation, speculative architecture or generic programming advice. Prefer a compact actionable rule with a canonical source reference over duplicating an entire spec. Revise an existing rule on correction, preserving history; do not manufacture supporting evidence from AI restatements. A blocked/skipped write is not a successful save; inspect each store receipt and report relevant unsaved rules before delivery.

## Write clear atomic records, once

One record describes one reusable behavior. State the applicable situation in `conditions`, preferred action in `do`, prohibited action in `dont`, and actual exceptions in `exceptions`; leave unknown parts empty. Keep `content` short and actionable. Use one primary topic (`analysis`, `implementation`, `debugging`, `verification`, `delivery`, `communication`, `correction`) and at most two established subtopics. Keep searchable wording in title/body so a wrong tag cannot hide it.

Before adding, compare loaded records. An unchanged scope with `empty_store:true` already proves absence: skip a redundant match until a write or invalidation changes that evidence. If equivalence or absence is unknown, use read-only `match` on stdin with `{"scope":"global","record":PROPOSED_RECORD}` (project/task uses its own scope and project root). This is not an apply envelope; reuse the proposed record below. No separate help/protocol read is needed for a basic match/ADD. A zero-hit query is not proof of an empty store. Exact content reuses a body. For a paraphrase, preserve the existing structured constraints and use revision-checked `ADD duplicate_of`; correct a confirmed rule with `REVISE`; a changed inactive inferred habit instead uses `SUPERSEDE` with a fresh candidate. If an explicit cross-project instruction confirms an existing inferred candidate, REVISE that same ID to active/confirmed instead of adding a second habit. An already confirmed rule needs no new candidate for equivalent feedback. Keep the current body unambiguous; the old misunderstanding belongs in revision history. Read [protocol.md](references/protocol.md) when revising, adding independent evidence, semantically merging or using advanced operations, then reuse it.

**A match is read-only, not a saved signal.** When new user evidence supports an equivalent candidate, finish with `apply`; finding it does not complete capture. Use an ADD operation with `duplicate_of: EXISTING_ID`, `expected_revision: EXISTING_REVISION`, `equivalent:true`, and nested `record` preserving that candidate's meaning, conditions and protected fields but carrying the new minimized user `source`. Include the current task's stable opaque `task_id` in the envelope. This adds evidence to the same body and lets the program decide promotion; never promote it yourself because it was found again. Repeated turns of the same task add no independent task signal.

Batch ordinary eligible increments before the final response. Recheck controls after any parallel assessment. All writes belong to the primary assistant. A minimal explicit habit payload is:

```json
{"schema_version":1,"scope":"global","session_id":"opaque-session","turn_id":"opaque-turn","idempotency_key":"unique-batch","operations":[{"op":"ADD","scope":"global","record":{"kind":"preference","claim_type":"preference","status":"active","strength":"hard","cross_project_confirmed":true,"title":"Reuse suitable existing code","content":"Inspect and reuse suitable existing code before adding another implementation.","conditions":"When changing an existing implementation.","do":"Check the existing behavior and reuse a suitable path.","dont":"Do not add a parallel implementation without checking reuse.","exceptions":"Use a different approach when the current requirement needs it.","tags":["implementation","code-reuse"],"source":{"type":"user_statement","excerpt":"A brief de-identified statement of the user's actual cross-project requirement."}}}]}
```

For a first reusable user choice without explicit cross-project scope, use the same `apply` command with this candidate shape instead (no second task or confirmation prompt is required to store the first signal):

```json
{"schema_version":1,"scope":"global","session_id":"opaque-session","turn_id":"opaque-turn","task_id":"opaque-task","idempotency_key":"unique-candidate-batch","operations":[{"op":"ADD","scope":"global","record":{"kind":"preference","claim_type":"preference","status":"candidate","strength":"soft","cross_project_confirmed":false,"title":"Reuse suitable existing code","content":"Inspect suitable existing code before adding another implementation.","conditions":"When an existing implementation may satisfy the requirement.","tags":["implementation"],"source":{"type":"user_statement","excerpt":"The user chose checking a suitable existing implementation before creating another one."}}}]}
```

Replace placeholders with actual data; never save these examples. All content writes need nested `record`. Supported kinds: `preference|convention|procedure|lesson|decision|business_rule|project_fact|summary`. Supply JSON through a quoted heredoc, PowerShell here-string, or scope-local `--input` file. `match`/`apply` take scope in JSON; `--global-only` belongs only to context/recall. Running `apply` without input saves nothing. Inspect each store's receipt, including `memory_status` (`candidate` or `active`); stores commit independently. Report an inactive save as a candidate, not as already adopted. Reuse an idempotency key only for the identical request. Make at most one targeted repair after failure, report any unsaved increment, and never claim a proposed record was saved. Optional `USE` can share an existing batch; it is an AI action report and adds no evidence.

## Organize without delaying coding

Default `context` and `apply` return maintenance status only, with no historical maintenance bodies. The existing queue becomes due after five changed active rules or inactive non-hypothesis candidates, one body of at least 1200 characters, or an unreviewed change waiting seven days. This is evaluated on authorized interaction, not a timer or daemon; stable unchanged habits are not repeatedly summarized. An active cycle drains later, including a small tail.

At the next natural task boundary with a due notice, fetch **one** `maintain --scope global|project --exclude-task --session-id SESSION --turn-id TURN` pack. Finish urgent substantive work first; leave pending work queued if no safe boundary is available. Do not poll or start a second pack in the same turn. Read the maintenance part of [protocol.md](references/protocol.md) only then. Inspect at most 8 records/12000 characters; the write transaction also limits the union of maintenance IDs to eight per store and rejects a second maintenance batch for the same session/turn (identical idempotent replay is safe); merge only equivalent behavior, compact only redundant prose while retaining conditions/exceptions/negation, and use `RETAG` for classification changes without new user evidence. Correct confirmed changes or archive explicitly invalid rules; age alone never proves a preference wrong. Submit one revision-checked batch, preferably alongside pending capture. Never recurse into another pack in the same turn. Candidate organization preserves inactive status and adds no evidence. Merge only records with the same status; later real user evidence may promote a global candidate using distinct task signals from the canonical record and its retained alias sources.

Compaction reduces active context; audit history still takes space. At an explicit maintenance opportunity, `storage --scope SCOPE` reports usage. `storage --scope SCOPE --reclaim` removes only old disposable caches, retired search terms and free pages. `--backup-keep N` previews backup retention; add `--reclaim` only for user-authorized retention. These cold commands are never part of ordinary coding. Evidence, revisions, idempotency/opt-out receipts and forgotten tombstones remain; confirmed `forget` is required to remove memory history. There is no lossless fixed disk cap for indefinitely growing evidence.

Summary preparation is read-only, bounded to eight revision-pinned sources/12000 characters, and respects disabled/excluded recall. A generated active summary requires compatible active sources and ancestors, cannot raise their strength or cross-project confirmation, and never serves as new user evidence. Keep uncertain derivations inactive; do not create recursive summaries to evade the source budget. Prefer atomic rules for ordinary recall and rebuild invalidated reading aids only when needed.

Oversized queue IDs remain explicit pending work; choose another fitting topic. Do not mark unseen revisions reviewed or force a lossy compact just to clear the queue. A separate targeted source review can handle them. Cross-kind semantic conflicts are not guaranteed to be discovered by the bounded related search.

## Controls and boundaries

`capture off` keeps recall and stops writes; `capture disable` stops both. Read-only recall uses `--readonly` and skips cache/maintenance writes. For a turn opt-out, immediately call `skip --scope global|project|both --session-id SESSION --turn-id TURN` in applicable stores; only opaque IDs are stored. Do not later ingest a paused/private turn under a new ID. Respect an explicit ban on memory/state writes or all filesystem changes. A business-code edit limit alone does not revoke previously authorized memory bookkeeping.

Never persist credentials, unnecessary customer data, raw logs or unrelated personal profiles. Global fields/evidence must exclude project names, business entities, code, paths and raw dialogue; program marker checks are incomplete, so minimize semantically first. SQLite is authoritative; Markdown is an on-demand view. No default model service, vector database, telemetry or application encryption is provided. Hosted model excerpts follow the host's data policy.

Automatic use depends on actual host instruction loading and model compliance. Optional [Codex hooks](references/codex-hooks.md) provide startup guidance/private-turn suppression only; they do not require a NOOP or perform ordinary per-prompt recall. Installation is not proof of end-to-end habit adoption. For installation see [setup](references/setup.md); for evidence see [verification](references/verification.md).

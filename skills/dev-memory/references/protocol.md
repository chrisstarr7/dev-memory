# Storage and CLI protocol

The normal Skill workflow stores and recalls only global and project memories. It calls `context --exclude-task`; task scope, checkpoints and task recall remain in the CLI only for backward compatibility with existing data and direct legacy callers. The Skill does not read, create or maintain task records. Existing task data is preserved.

## Paths

- Global data root defaults to `~/.dev-memory/`; the global store lives in `global/`.
- Each project store lives at `<project-root>/.dev-memory/`; project task checkpoints live inside the same SQLite database.
- `DEV_MEMORY_HOME=/private/path` or `--global-root /private/path` changes only the global data root. Do not use either option to route project content globally.
- A project is selected by an explicit root or nearest initialized `.dev-memory/config.json`; otherwise Git root is used. A working directory is not evidence that its business facts are global.

## Task recall and hot-path contract (0.8.0)

Use one `context --exclude-task --intent bugfix --query "ACTUAL TASK TERMS" --session-id SESSION --turn-id TURN` call. Intent is optional (`planning|feature|bugfix|refactor|review|verification|delivery`), expands bilingual topic/body terms and never filters a category. Specific lexical matches rank before intent-only hints; rarer indexed terms carry more weight. Default combined recall reserves 3 details/60% of body characters for global habits and 2/40% for the project, within the same 5-detail/4000-character budget. A one-detail combined request reserves that detail for project safety. Global-only recall uses the whole budget. Intent participates in the cache key.

Normal `context` and `apply` return maintenance metadata only. Request bodies at a quiet boundary with `maintain --exclude-task`; explicit `context --with-maintenance` or an apply envelope with `maintenance:"prepare"` also opts into packs. Ordinary capture uses the default `maintenance:"defer"`. Low-level task packs additionally require envelope `include_task:true`; the normal Skill excludes task records. No default secondary model/reviewer or NOOP write is required. If optional capture delegation is used, join it and check actual commits before final delivery.

## Apply envelope

Required fields: `schema_version: 1`, `scope` (`global`, `project`, `task`, `both`), non-empty `operations`, stable per-turn `idempotency_key`, host `session_id` and `turn_id` when available. Include current `task_id`, branch and commit when known. Operations:

- `ADD`: requires explicit operation `scope`, typed record, claim type, status, and source. Active records need a source. `model_inference` cannot create an active record.
- `CHECKPOINT`: stored as `task`; requires task ID and current project.
- `ADD_EVIDENCE`: needs current `expected_revision` and source. Repeated matching evidence is idempotent.
- `REVISE`, `SUPERSEDE`, `ARCHIVE`, `MARK_CONFLICT`: require current `expected_revision`.
- `NOOP`: a checked scope-specific result with a brief reason. Use operation scope `both` only for NOOP. Both stores commit independently; inspect each returned result.
- `USE`: optional, same existing apply call; `id`, current `expected_revision`, short `reason` and concrete `action_ref`. Only an active record in the same scope/task is accepted. It records `ai_reported_not_behavior_verified` in the ordinary receipt, changes no body/data revision and adds no evidence. Never supply content/source/verification, report mere recall as use, or make an extra tool call just for USE. Global references must not contain project details. A successful USE is a checked no-increment turn, not a successful test.

USE action notes appear in the current command result only. Persisted receipts keep the ID/revision and reporting marker, omitting `reason`/`action_ref` to avoid another copy of business prose after record deletion. An idempotent replay therefore returns the minimal stored usage result, not those action notes.

Global explicit habits require a global kind, `cross_project_confirmed: true`, explicit user statement/confirmation/feedback, and no project/task/workspace markers. The one inferred-habit path accepts only a de-identified `preference` candidate (`claim_type: preference`, `strength: soft`, `status: candidate`, `cross_project_confirmed: false`) from a direct `user_statement`, `user_confirmation` or `user_feedback`; project/task/workspace markers are rejected. It also requires the envelope task ID. Before writing global evidence, the program replaces that ID with a namespace-salted SHA-256 reference and drops any message ID. One distinct task reference counts once across all three user source types; changing source type or wording within one task does not create independence. A single eligible occurrence is stored immediately as a candidate; two references promote the candidate to an active soft preference. Exact reuse, `ADD duplicate_of`, revision-checked `REVISE` and `ADD_EVIDENCE` all evaluate promotion. All inferred content writes, including legacy SUPERSEDE, replace caller evidence IDs with the controlled task hash; the `habit:` prefix is reserved. For inferred `ADD_EVIDENCE`, the envelope task ID is mandatory and caller-provided message/ingestion identities are replaced by the controlled task hash. Reusing an active inferred habit never creates another body merely because it was promoted. Model inference, recall, and reuse of the same task cannot add independent support. ADD/REVISE/ADD_EVIDENCE receipts expose `memory_status`: `saved` can mean an inactive candidate was persisted, not that a rule became active. Project records allow business rules. Task is a project-local checkpoint. Machine marker checks are defense in depth; the AI must semantically remove project names, business entities, code, paths, customer data, and raw dialogue.

## Evidence and truth

Source types: `user_statement`, `user_confirmation`, `user_feedback`, `code_observation`, `tool_result`, `external_reference`, `model_inference`. Store short source excerpts only when necessary and safe. AI repetition and recall are not independent user evidence. `verification` requires an actual successful `tool_result` with command, timestamp, code version, and exit code 0. The store binds it to the current commit and workspace signature when available. `show`/recall report unknown or stale version state; workspace edits or commit changes expire the verification. A semantic record revision clears the old verification. After source change, tool-verified status must not silently transfer to the new revision. A model must never fill this object from its own summary or intended test plan.

Keep `desired` and `observed` separate. An unconfirmed `hypothesis` cannot be active; normal recall excludes legacy hypotheses without deleting their history. Preserve conditions, exceptions, negative constraints, prevention check, and verification method. Consolidation is a same-namespace proposal; never write a proposed summary until reviewed. Derived summaries carry source IDs and are invalidated by source change/deletion.

Developer-habit records are atomic: one reusable behavior per record, with a short actionable `content` and structured `conditions`, `do`, `dont`, and `exceptions` where applicable. Use one primary topic tag from `analysis`, `implementation`, `debugging`, `verification`, `delivery`, `communication`, or `correction`; add up to two concise subtopic tags only when they improve retrieval, reusing established tags where possible. Tags are advisory indexes, not access controls: keep the behavior understandable and searchable in title/body so a wrong category cannot hide it. Do not add empty categories or general programming knowledge as personal memory.

## Missing-capture diagnosis (0.8.2)

Do not confuse an absent write with an inactive candidate. A single diagnostic `doctor` reports the loaded `skill_version`/`skill_path`, `user_activation`, `project_activation`, capture controls and per-status store counts. `active_count` now counts only active records; `candidate_count` and `record_counts` expose other states. Inspect candidate bodies only when needed using `list --scope global --status candidate`, then `show`/`match`. These diagnostics are not a per-turn workflow.

`setup --user --agent codex` authorizes/configures only global user guidance using this runtime. It initializes no project and preserves global pause/disable settings. It is mutually exclusive with `--project-root`; other hosts reject user-only activation. Use a current installed runtime, and start a new host session afterward. A successful configuration or stored record is not proof that the host loaded or applied it.

## Sessions and latency

Session context cache key covers namespace, workspace ID, data revision, task/module, normalized query terms, output budgets, branch/head, and a one-way Git worktree signature. A changed context triggers another bounded lookup. This detects many working-tree changes but is not a cryptographic content snapshot and may miss files outside Git status coverage. Context compression/resume guidance requires the primary assistant to force focused recall. Optional hooks do not retrieve baseline memory on each prompt.

Reads are bounded by candidate/detail/character limits and restricted to the global database plus one current project database. Search uses SQLite indexes, ASCII code tokens, and Chinese bigrams. Hard project rules and the current task checkpoint have dedicated slots. When detail budget is exceeded, result sets `context_incomplete` and lists remaining IDs; do not claim all constraints were loaded.

An `apply` request can process global and project operation groups. Each store gets its own transaction, revision and receipt. One may succeed while the other fails: report partial success and retry only the failed scope with a new idempotency key after inspecting the successful scope. Markdown is rebuilt only by `export`.

## Deletion, backup, restore

Deletion is a two-step preview/token flow. Project deletion previews project-local derived entries and lists promoted global IDs but cannot delete cross-store data automatically. Backups are within the same store's `backups/`; restore validates namespace/integrity and reapplies forgotten tombstones. Host transcripts, external copies and OS snapshots remain outside this tool.

## Minimal valid write (synthetic example; never seed automatically)

```json
{
  "schema_version": 1,
  "scope": "project",
  "session_id": "local-session-1",
  "turn_id": "local-turn-1",
  "idempotency_key": "local-session-1:local-turn-1:batch-1",
  "operations": [
    {"op": "ADD", "scope": "project", "record": {
      "kind": "business_rule", "claim_type": "desired", "strength": "hard",
      "title": "Refund eligibility", "content": "Refunds require all stated conditions.",
      "conditions": "Delivered, unopened, within 14 days.",
      "exceptions": "Gift orders and final-sale items are excluded.",
      "dont": "Do not weaken any condition or exclusion.",
      "verification_steps": "Check boundaries and each excluded order type.",
      "source": {"type": "user_feedback", "excerpt": "Delivered, unopened, within 14 days; exclude gifts and final-sale items."}
    }}
  ]
}
```

This is a desired rule, with planned verification only. An observed, actually executed test result may instead supply `source.type: tool_result` and `verification` with the actual `command`, `finished_at`, `code_version`, `exit_code: 0`. Never copy example placeholders as actual verification.

Global preference lookup includes both active rules and inferred candidates for semantic comparison. When a new explicit cross-project statement confirms a candidate, revise that ID to active/confirmed with the current revision; differing status/strength is not duplicate equivalence. Equivalent feedback already covered by a confirmed rule does not require another candidate.

Basic read-only duplicate lookup takes `{"scope":"global","record":PROPOSED_RECORD}` on stdin. An outer opaque task ID is not copied into a global proposal; nested project/task identifiers are still rejected. Both `match` and `apply` accept omitted `--input` or `--input -` for stdin, with the same 1 MB/object validation as file input.

`ADD` cannot overwrite an existing or forgotten ID; use `REVISE` with a current revision for edits. Scope and task participate in deduplication; desired and observed claims remain separate. `cross_project_confirmed` must be JSON `true`, not a truthy string. Global evidence additions are checked against the same scope rules.

Use a stable idempotency key for the exact same request; reuse with changed contents fails. Legacy receipts without a request digest cannot certify an exact replay. Locally generated ingestion identity combines session and turn, so repeated turn IDs in separate conversations do not merge evidence.

An explicit `skip` blocks all later writes for that same session/turn in the selected store. Controlled restore preserves these private receipts. New IDs must never be used to bypass an opt-out; the CLI cannot identify rephrased private content by meaning.

A derived summary with `derived_from: ["source-id"]` must also provide `expected_source_revisions: {"source-id": 3}` for every source. The program checks current revisions, rejects cross-task/scope dependencies and cycles, and stamps revision references into `source_refs`. Use `consolidate` to retrieve the actual versions. Changed/deleted source records invalidate dependent summaries. `SUPERSEDE` requires a distinct replacement ID.

Query terms and output budgets also participate in cache identity; a topic change cannot inherit an unrelated cached query. Incomplete recall does not create a complete-context cache claim. Global preferences/conventions are included in bounded baseline recall even for a business query. The primary AI queries the actual task topic; optional hooks do not perform a baseline recall.

Forgetting removes managed Markdown views immediately rather than leaving private text waiting for an export. Check `view_cleanup_incomplete` and `backup_cleanup_incomplete` for failure to clean a managed artifact. A later export removes old empty buckets. This is logical deletion, not secure disk erasure.

The empty config example is not a ready runtime config: initialize with the CLI to generate namespace/workspace identity. New project `setup` stores use `capture_mode: full-project` for supported durable project knowledge. Existing modes and controls are preserved on upgrade. `developer-first` blocks new project/task records while retaining recall; an explicitly authorized `mode full-project` enables them. Context and doctor expose capture_mode, and context also reports capture_enabled; a readable store need not permit capture. Existing configs without this field keep their existing behavior. Authorized changes to limits narrow recall budgets; `excluded: true` disables project capture and recall. Do not alter identity/storage routing fields.

For an ordinary continuation request with no known task ID, use `recall --resume --force`. It includes bounded recent task checkpoint candidates from the current project without automatically binding a task. Select the relevant task from current user intent and visible progress; ask if candidates make that materially ambiguous. Explicit task IDs retain the normal focused path. Resume intent participates in cache identity; incomplete results still require inspection.

A mixed-scope envelope may carry a project task/branch/commit context. The global transaction excludes these inherited fields; explicit project markers inside a global record still fail validation. Project and task operations keep their own context, identity and independent receipt.


## Automatic duplicate prevention and maintenance

`match --project-root PATH` reads one proposed record from stdin:
`{"scope":"project","record":{...valid record...}}`. It reads only the selected store, returns at most eight complete candidates within 12000 characters, and writes no receipt/cache/state. Use remembered context instead when it already contains the applicable rule. `exact_id` is a deterministic content match; other candidates require current-AI semantic review. The fingerprint ignores titles and normalizes body whitespace, preserves case-sensitive business values, and separates conditions, exceptions, negative requirements, claim type, scope/task, verification and observed code versions. Project-rule task IDs describe provenance and do not create a new business rule per task; task-scoped constraints remain separate. No fuzzy threshold silently merges rules.

For equivalent paraphrases, `ADD` accepts `duplicate_of`, `expected_revision`, `equivalent: true`, and a valid proposed `record` with the **existing structured fields** and the actual independent source. The program validates both records' protected fields and never inserts the proposed body. Repeated source identity cannot increase evidence even if its excerpt is rephrased. With no new independent source or information, make no write; NOOP remains a legacy explicit API operation. Corrections and incompatible conditions are revisions or distinct rules, never duplicate reuse. `summary` and `checkpoint` are excluded from semantic duplicate reuse.

An actual changed write queues its record revision in the same SQLite transaction. After commit, the success receipt includes a metadata-only due notice when five records are pending, a queued body has at least 1200 characters, or an unreviewed change has waited seven days (`maintenance_interval_days`, 1..365). Fetch one read-only maintenance pack at a quiet task boundary; envelope `maintenance:"prepare"` explicitly requests the pack in the receipt. This is a threshold to review **one related topic**, not to summarize five unrelated rules. Candidate search prioritizes rarer terms so long multilingual records do not lose their discriminating terms through alphabetical truncation. Only one store's indexed records are read; no global project enumeration. The pack reports the total pending count, but the AI reviews only its bounded records and leaves the rest queued. A half-second SQLite query budget defers slow planning; SQLite busy waits remain bounded separately. Planning failure is reported separately from already committed capture. Routine NOOPs return no pack. A maintenance-protocol upgrade queues existing eligible active rules and inactive non-hypothesis candidates once; subsequent default calls still return only due metadata, and bodies require explicit preparation. No transcript is written during the one-time requeue.

`maintain --scope both --project-root PATH` checks pending history without modifying it. Each store has its own result and budget; `--force` reviews a pending related topic below the threshold at a task boundary. Disabled capture/recall, exclusion and `maintenance_enabled: false` suppress automatic maintenance. Idle returns no body. There is no daemon: pending work resumes on subsequent authorized interaction. It does not repeatedly scan the entire history. Oversized records are listed in `remaining_ids`/`oversized_ids`; bounded planning chooses another fitting pending topic instead of repeatedly blocking the queue. When all available records exceed the budget, perform a separate targeted source review. Unread oversized revisions remain queued; never truncate away a constraint or acknowledge a body not read.

Maintenance is submitted through ordinary `apply` with an idempotency key, session/turn IDs and scoped operations. The pack's `record_scope` is the operation scope: a project database also contains `task` records, so its outer store `scope` is not sufficient. Copy `record_scope` into each operation and use the supplied task ID for task context; never label a task review as project scope. No new evidence is supplied. Each operation requires a short `reason` (at most 500 characters) and `expected_revisions` for 1..8 fully read records. The union across all maintenance operations in that store batch is capped at eight IDs. With session/turn IDs, another maintenance mutation batch is rejected as `maintenance_deferred`; an identical idempotency replay still returns the original result. Submit any new capture separately instead of retrying maintenance. Example **synthetic** operations:

```json
{"op":"MERGE_DUPLICATES","scope":"project","id":"keep-id",
 "expected_revisions":{"keep-id":2,"duplicate-id":1},
 "meaning_preserved":true,"reason":"Both state exactly the same rule, with identical conditions and exclusions."}
```

- `MERGE_DUPLICATES`: keep the target's canonical body and status; only same-status active rules or inactive non-hypothesis candidates may merge, with identical structured constraints/truth/version/scope fields are required. Supersede the other atomic rules, retain original evidence/history with inspectable `merged_source_ids`, invalidate their dependent summaries, and clear reviewed queue entries. No summary/checkpoint merging. Different wording is accepted only after AI semantic review; the receipt labels that judgment `ai_claim_not_program_verified`. Inspect original IDs with `show` to trace their evidence. A later source edit marks an active canonical rule conflicted or an inactive candidate stale; do not silently continue using a now questionable merge.
- `COMPACT`: one current ID/revision; use either `expected_revision` or one-entry `expected_revisions` (conflicting forms fail). Provide shorter nonempty `content`, `meaning_preserved:true` and reason. Other fields remain untouched, the previous body stays in revisions, and dependent summaries invalidate. Preserve prose-only restrictions; uncertain shortening is skipped. Rebuild summaries from atomic sources.
- `RETAG`: one eligible ID with `expected_revisions`, `meaning_preserved:true`, reason and 1..3 unique short `tags`. Changes only tags/revision/search terms on an active rule or inactive non-hypothesis candidate, retains evidence, and invalidates derived summaries/cache. It is classification, not a new observation.
- `MAINTENANCE_REVIEW`: fully inspected IDs/revisions plus reason. Unseen oversized IDs are never part of this acknowledgement. A merge/compact/review chain in one atomic apply may reuse the original loaded snapshot map; the program translates revisions changed inside that batch. Explicit post-operation revisions are also accepted. External stale revisions and booleans still fail. Remove only checked pending revisions; change no body/data revision. Never include unseen or unrelated records.

Every store batch is atomic: if any operation fails, that store's whole batch rolls back, including earlier merge/compact changes. Do not advance source revisions on a failed batch. Another store in the same call can have committed independently. The failed result reports `transaction:rolled_back`; a successful translated operation reports `revision_resolution:within_batch` and review returns the checked revisions. The original snapshot applies only to its one transaction, never a later request after external changes.

Maintenance also handles supported obsolescence without treating age as evidence: `REVISE` a canonical record when a newer user-confirmed correction changes its content; `ARCHIVE` a record contradicted by a newer confirmed rule or whose explicit expiry is demonstrably past. Use the current revision and cite the basis in `reason`. Do not archive merely because a fact is old, a date is absent, or a candidate looks similar. Archived/superseded records leave default recall; their audit revisions and evidence remain until the user explicitly forgets them. Permanent deletion is not automatic because it would destroy provenance and may remove a still-applicable condition.

Thresholds **start** a store-local maintenance cycle. An age-triggered or explicit review also starts the cycle on its first successful apply. Once started, the pending queue keeps returning a metadata-only due notice until idle, even below five records; a quiet-boundary explicit preparation returns one bounded topic. This is queued work, not a requirement to interrupt coding: the AI may defer semantic review until a natural task boundary. Existing session/turn receipts suppress another automatic pack after a merge/compact/review in that turn; `pending_next_turn` has no record bodies. Pass `--session-id`/`--turn-id` on context/maintain for the same bound and turn opt-out protection. Idle NOOPs remain body-free. Legacy checked NOOPs can report due metadata, but ordinary no-increment turns make no call. No background execution, timer, recursive loop or other-project scan is added.

Merge/compact/review batches return `maintenance: not_due` and do not requeue themselves. Limit to one batch per original user turn, no retry loop or default second summarization phase. Ordinary capture can include a maintenance operation already justified by current context; newly returned packs can use one bounded follow-up apply. Deferred work waits for a later interaction.

Superseded bodies and old compressed bodies remain audit history; automatic maintenance removes duplicate **active** rules and shortens the current body, not secure-erases history or caps total disk use. It does not expire stable preferences, unfinished task constraints, private-skip receipts, forgotten tombstones or backups by age. User-confirmed forget handles physical managed-content deletion; its preview includes the canonical merge, all alias sources and derived history, even when invoked on an old duplicate ID. Restore supports older backups and preserves forgotten/opt-out suppression. Source evidence cannot be revived by a maintenance batch.


Candidate maintenance preserves inactive status. Merging candidate bodies does not invoke promotion or create evidence; a later ordinary user-evidence operation counts distinct controlled task references across canonical and retained alias evidence, with same-task references counted once. A changed inactive global habit must use `SUPERSEDE` with a fresh candidate, not `REVISE` carrying old-meaning evidence. Explicit cross-project confirmation can still revise the existing record into a confirmed rule. No age-based candidate deletion. Automatic related matching uses compatible kinds/claims and is not a complete cross-category contradiction detector.

Summary preparation accepts 1..8 local IDs and returns at most 12000 characters, with remaining_ids/context_incomplete for omitted sources, respecting disabled/excluded recall. Summary writes require source revision pins. An active summary requires active compatible source claims and ancestors and cannot increase strength or cross-project confirmation. Candidates and hypotheses cannot become active through summarization; retrieved sources are not proof of their truth. Ordinary recall revalidates legacy summary ancestry and skips incompatible derived rules without deleting audit history. No sourceless summary or recursively strengthened reading aid.

## Legacy task API and bounded startup

Use one `context --project-root PATH --query TOPIC --session-id SESSION` call at start or a topic/module transition. Normal Skill use adds `--exclude-task` and forces recall after context loss; `--resume` is only for direct legacy task callers. It reuses bounded recall and checks pending maintenance in both separate stores, without probing host versions, initializing stores, writing receipts or certifying automatic hooks. `--readonly` skips maintenance and cache writes. A normal startup does not need separate doctor/recall/maintain calls. Doctor remains available for diagnostics.

Recall reserves fixed project capacity even with many global preferences. Candidate-limit overflow is incomplete and cannot be cached as full. Unknown essential constraints must be obtained before changing behavior. `show --scope project --ids ID1 ID2 --current` batches up to 8 current records/12000 characters and omits audit history; oversized/missing IDs are explicit. Single `show --id ID` retains evidence/revision inspection. An `empty_store: true` recall proves no active/candidate/conflicted rule exists; zero lexical hits does not. Reuse a loaded protocol until context/runtime changes.

Focused query matches rank before unrelated hard-rule fallback; applicable checkpoints retain resume priority. Results preserve code/source references and provide up to eight unloaded candidate descriptors (2000 characters per store) to target selective follow-up. Descriptors do not contain complete constraints and never imply those constraints were checked. `remaining_ids` and `context_incomplete` still expose omitted records. Translate loaded applicable rules to design/code actions and regression checks before edits; test actual behavior independently of USE receipts.

Keep one task ID through a continuing development effort, and optional topic/stage/module tags for focused retrieval. A newly saved active task checkpoint atomically supersedes earlier active checkpoints of that task, retaining evidence/history and invalidating old derived summaries. Other tasks are untouched. A duplicate unchanged checkpoint need not produce another body. Existing legacy checkpoints are not destructively pruned; the next valid checkpoint retires prior active ones. Requirements, schema/API decisions, implementation observations, test plans and actual verification remain different claims. Do not copy entire source/spec/log artifacts into the store.

Maintenance defaults are **5 pending current records, a pending body of at least 1200 characters, or an unreviewed change waiting 7 days**, with at most 8 related records/12000 characters per store and one batch per turn. Retired checkpoints leave the pending queue. Do not force a below-threshold review on an ordinary coding turn; a quiet task boundary may fetch and review one topic after a due notice. Startup context already checked pending status, so do not poll during coding. This threshold manages active working context; it is not a disk-size cap or a guarantee about model latency.

## Storage accounting and reclamation (cold path)

`storage --scope global|project` is read-only accounting: database/WAL/free-page bytes, evidence/history/receipt/cache rows, backup bytes and disposable cache/index counts. It is not called at startup. `--reclaim` removes session cache keys older than 30 days and search terms for archived/superseded/stale records, checkpoints WAL and runs SQLite VACUUM. Evidence, memory bodies/revisions, idempotency receipts, private skips and forgotten tombstones are not pruned. Reactivating a record rebuilds its index. Paused/disabled/excluded stores reject reclamation.

`storage --scope SCOPE --backup-keep N` previews copies removable under an explicit retention choice; adding `--reclaim` deletes those copies. N must be 1..1000. Only managed backup filenames with this exact namespace/storage kind are eligible; symlinks, foreign/invalid databases and unknown files are preserved/reported. Retain the newest N validated backups. Never invoke backup retention, full export or VACUUM during a normal coding turn. Compaction and reclamation do not impose a fixed total disk cap: provenance grows with distinct evidence until the user explicitly forgets it.

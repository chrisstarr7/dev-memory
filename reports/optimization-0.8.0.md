# Developer habit workflow review — 0.8.0

## Contract and first principles

The requested outcome is relevant recall and evidence-backed habit learning with bounded foreground work and sustainable local storage. Keep the SQLite authority, separate scopes, revisions, evidence, opt-outs, backups and explicit forget. No new service or default additional model call.

Three constraints determine correctness:

1. A recalled record must be current, applicable and authorized: returning an obsolete or foreign constraint can change the code incorrectly.
2. A learned personal habit needs visible user evidence: generated wording or retrieval cannot establish what the user prefers.
3. Work and output on the coding path must be bounded: every unnecessary tool/model round and historical body consumes task time or context.

Success criteria: synthetic intent/cross-language retrieval finds the intended habit despite a wrong tag; exact and paraphrase candidate evidence promotes once; default context/apply contains no maintenance bodies; hooks add no normal-turn recall or NOOP recovery; stale queue items become reviewable without a timer; safe reclamation reduces disposable data without deleting evidence, revisions or suppression. CI must pass across the configured matrix.

## Assumptions challenged

| Assumption | Evidence / challenge | Constraint | Decision |
| --- | --- | --- | --- |
| Every increment needs a second AI reviewer | The primary AI already understands the request; joining a reviewer adds a round on short tasks. | 2, 3 | Primary assessment by default; delegation optional when it adds value. |
| One global detail is sufficient | Combined recall reserves only one of five details for developer habits even with an empty project. | 1, 3 | Reserve most detail capacity for global habits while keeping project capacity. |
| Ordinary word overlap captures intent | Chinese tasks and English topic tags can have no shared tokens; generic words can outrank specific entities. | 1 | Optional explicit intent expansion and indexed rarity weighting, no hard category filter. |
| Preparing cleanup is free | Startup and apply return up to 8 historical bodies per store, even if semantic review is deferred. | 3 | Metadata-only due notices by default; fetch a pack only at a quiet boundary. |
| Count thresholds guarantee periodic cleanup | One to four short pending records can wait forever before a cycle starts. | 1, 3 | A seven-day age trigger on the existing queue, evaluated on interaction. |
| Deduplication always preserves learning | The paraphrase reuse branch returns before candidate promotion. | 2 | Shared promotion after independent evidence on either deduplication path. |
| Compaction caps disk usage | Old bodies, caches and backups remain; provenance cannot be deleted just because it is old. | 1, 2 | Expose storage accounting and explicit safe reclamation/backup retention; retain audit data until forget. |
| Optional hooks follow the current Skill | Hooks still demand checked NOOPs and perform baseline reads on each prompt. | 3 | Startup/invalidation guidance and opt-out handling; no compulsory Stop recovery. |

## Grounded design

The repository already has indexed terms, atomic revision-checked writes, bounded related packs and distinct task signal hashes. Reuse these primitives. The instruction entrypoint can be shortened by routing only advanced maintenance/storage operations to the existing protocol.

The queue's timestamp supports periodic due checks without a daemon. A due notice need not select record bodies. Semantic cleanup merges only equivalent rules, retags without adding user evidence, and shortens prose while preserving conditions and exceptions. Current source edits must immediately invalidate derived context.

Reclamation is an explicit cold operation: remove disposable old session cache and retired-record search terms, checkpoint/VACUUM, and optionally retain a user-selected number of validated same-store backups. Do not prune idempotency receipts, opt-outs, forgotten tombstones, evidence, revisions or active memories automatically. Unique valid habits and their audit trail can still grow; there is no honest lossless fixed disk cap.

## Progress and validation

- [x] Frame: three correctness constraints and measurable acceptance criteria.
- [x] Essence: relevant, traceable memory with bounded foreground work.
- [x] Challenge: eight assumptions checked against repository behavior.
- [x] Ground truth and design: reuse existing local primitives.
- [x] Validate: 231 local tests (2 native Windows checks skipped on macOS), package build, scale probe and independent review. Skill format validation passed in an isolated test-only PyYAML environment; runtime dependencies remain standard-library only.
- Publication gate: push the reviewed revision, require the configured six-job Program checks matrix to pass, then publish the release. The release and its commit identify the authoritative CI result; remaining host limits are below.

Inversion stress case: a short Chinese bug request arrives in a large store containing many unrelated recent preferences, one old pending rule, a paraphrased candidate and private-turn receipts. It must recall relevant current guidance, avoid unrelated maintenance bodies, preserve opt-outs and neither fabricate evidence nor silently delete history.

## Implemented changes and compatibility

- Task intent is an optional hint, not a classifier service or category filter. Rarity weighting favors concrete code/task terms; normal combined budgets changed from 1 global + 4 project details to 3 + 2.
- Startup/apply maintenance is metadata-only. Direct callers opt into bodies with `--with-maintenance` / `maintenance:"prepare"`; low-level task packs use `include_task:true`. The queue also has a seven-day pending-change trigger.
- Exact, paraphrase, evidence-only and revision paths share inferred-habit evidence rules. Active/candidate lookup and content fingerprints treat promotion as the same behavior. A caller cannot forge the reserved task-evidence identity.
- Global preference matching also exposes candidates to explicit confirmation; revise the same ID instead of creating a parallel confirmed rule. User-level activation now states confirmed and inferred fields in separate bullets. Basic match input is documented in the Skill; stdin/file share validation and accept `--input -`.
- RETAG changes classification with revision/index invalidation and no new evidence. COMPACT/MERGE preserve protected conditions and provenance.
- Optional hooks perform no ordinary-prompt recall or Stop receipt recovery. Reconfiguration removes only the owned legacy Stop handler.
- Cold storage accounting/reclamation preserves evidence, revisions, all idempotency/privacy receipts and forgotten tombstones. Explicit backup retention validates scope, required recoverable schema and SQLite integrity before counting retained copies.

SQLite schema_version remains 1; no new authoritative database or service is introduced. Re-running setup/installation refreshes semantic content fingerprints to format 4 and invalidates old recall caches, while preserving bodies, evidence, namespace and controls. No historical project data moves to global. Existing low-level task data remains.

## Changed surfaces

| Files | Responsibility |
| --- | --- |
| `skills/dev-memory/SKILL.md`, `scripts/dev_memory_setup.py` | Focused task recall, explicit/inferred learning, action mapping, compact host activation and quiet maintenance |
| `scripts/dev_memory_store.py`, `scripts/dev_memory.py` | Indexed intent/rareness retrieval, promotion/dedup/provenance, metadata-only hot path, RETAG, storage/backup validation and CLI input |
| `scripts/codex_hook.py`, hook/protocol references | Remove ordinary-prompt probing and Stop recovery; document current contracts |
| `tests/test_efficiency.py` plus existing test adaptations | Twenty-one targeted regressions without dropping legacy maintenance coverage |
| `evals/check_efficiency.py`, measurement JSON | Reproducible isolated program and explicitly requested host probes |
| Root and translated READMEs, architecture/installation/contributing, package metadata/manifest | Actual behavior, limits, upgrade path and 0.8.0 packaging |

Script paths in the table are relative to `skills/dev-memory/`. No unrelated project, live memory store or user host configuration was changed.

## Program comparison

Baseline is Git commit `9ecc959` (0.7.2). Each cell uses fresh isolated stores with 1,000/10,000 synthetic indexed global habits, an empty project, a narrow concrete query and a due maintenance queue. Bulk index seeding omits evidence, so this measures lookup/context overhead, not evidence ingestion or real model behavior. Ten forced calls per cell, sequential baseline then current; not randomized.

| Indexed habits | Baseline median / max | Current median / max | Response characters, baseline → current | Maintenance bodies, baseline → current |
| --- | --- | --- | --- | --- |
| 1,000 | 32.465 / 34.269 ms | 23.871 / 25.679 ms | 11,906 → 4,789 | 8 → 0 |
| 10,000 | 128.211 / 139.179 ms | 32.920 / 33.423 ms | 11,946 → 4,823 | 8 → 0 |

Both actual lexical query plans use the covering `search_term_term` index and primary-key record lookups. The new response returns three global habit bodies within the existing total budget, versus one previously. Extra candidate-directory metadata has its own existing bound. The Skill entrypoint fell from 23,001 to 13,192 bytes. These results do not measure AI task latency and do not justify a zero-overhead claim.

Reproduce program measurements with `python3 evals/check_efficiency.py --output /outside/repository/program.json`. Source hashes are recorded with results. Real-host runs use explicit `--host --model MODEL --reasoning LEVEL`, synthetic projects and an isolated temporary home; they consume the existing host account. Raw logs and local authentication are not release artifacts.

## Independent adversarial review

An independent read-only reviewer reproduced three defects during development: promoted habits missing from candidate matching; caller-supplied revision evidence faking a second task; and schema-incomplete files counting as retained backups. All were fixed and regression-tested; the reviewer reproduced closure. A second malformed backup containing only sampled core columns revealed another retention hole; validation now derives the complete stable core-column set from the canonical schema, while preserving supported older optional fields and absent maintenance tables. The independent reviewer reproduced closure of the malformed-core case, passed 21/21 efficiency tests and verified the old-backup-without-maintenance-tables restoration test. The complete local suite passed 231 tests in 39.712 seconds, with two native Windows tests skipped on macOS.

## Host evidence and remaining limits

All nine exploratory cells used the same retry task, configured `gpt-6-luna` / high, Codex CLI 0.155.1, synthetic stores and isolated homes. Project B starts from the same code in a separate directory; an existing store is shared within a condition. Diagnostics led to targeted fixes, not discarded unsuccessful samples. [Program JSON](efficiency-program-0.8.0.json) and [host JSON](efficiency-host-0.8.0.json) retain source hashes, per-cell calls, token counts, correctness and manual semantic observations.

| Condition / project | Whole task | Observed tool events | Commands containing memory CLI | Durable unit tests / required report headings |
| --- | --- | --- | --- | --- |
| Off / A | 116.556 s | 6 | 0 | No / No |
| 0.7.2 / A | 166.835 s | 10 | 6 | No / No |
| 0.7.2 / B | 169.829 s | 28 | 16 | Yes / No |
| Final workflow / A | 81.762 s | 11 | 4 | No / Yes |
| Final workflow / B, user-level only | 68.877 s | 8 | 1 | Yes / No |

All nine implementations passed the independent positive-integer, retry-count, original-exception and immediate-failure checks. The initial two current cells took 100.360/54.287 s (14/7 tool events); the intermediate cells took 88.785/85.145 s (12/8 events). These are sequential development diagnostics with differing snapshots, one invocation per cell, not a randomized repeated latency benchmark. The off cell completed before a subsequent harness directory collision; the harness was repaired and baseline/current cells resumed. Catalog/plugin-fetch warnings occurred; raw stderr is excluded because it can contain signed URLs.

The final A session loaded three relevant habits and saved the explicit new preference as active/confirmed. Final B had no project setup, loaded the user-level guide, retrieved that same habit, wrote no duplicate and added/reran unit tests. It attempted a missing project activation lookup and used a combined context call instead of the advised global-only flag; global recall still succeeded without creating project memory.

Compliance is **partial**, not a universal success: final A used inline assertions despite the recalled persistent-unit-test habit; final B omitted the required headings while that rule was unloaded. The stronger action-mapping instruction reduced some earlier failures but does not enforce model behavior. No further runtime gate or compulsory reviewer was added to conceal this limitation. The final host snapshot predates only a further cold-backup validation hardening and a verification-document link; exact differences appear in the JSON. The complete semantic scenario inventory was not rerun on a model in this change, and no statistical speed/accuracy claim is made.

 Other-host installation adapters are covered by program tests, not by real model sessions. Trusted hook event delivery is not claimed. The primary AI must still judge semantic equivalence, project de-identification, applicability and genuine task independence; typed source fields and successful commands cannot prove those judgments.

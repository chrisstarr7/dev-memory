# Development lifecycle adversarial review — 0.5.0

## Result and scope

The full local suite passed **157 tests**. Implemented the recall, checkpoint and startup fixes below, using isolated synthetic stores. Final program checks, real-host observations and workflow timing are separate evidence. No developer's real memory or installed host configuration was changed.

**The “no material AI slowdown” requirement is not established.** New matched workflow trials were blocked by an actual host workspace-credit error. The previous 0.4.0 comparison measured substantial overhead. Fast local reads do not resolve that result.

## Findings and changes

| Priority | Failure / counterexample | Change and verifier |
| --- | --- | --- |
| P1 | Checkpoints written in the same second could resume an earlier development stage because UUID order selected the winner. | A new active checkpoint atomically supersedes earlier active checkpoints of the same task. Evidence/history stay available; dependent summaries invalidate. Seven-stage and identical-time regressions pass. |
| P1 | Five global preferences could consume the detail budget and leave the project's business contract unloaded. | Fixed per-store capacity reserves project details/characters. The default five-detail budget is one global plus four project/task details; overflow remains explicit. |
| P1 | A truncated lexical candidate query could report complete context and then cache it. | Query one sentinel beyond the limit, report incomplete/overflow and never cache it as complete. Saturation regression and 10,000-record probe pass. |
| P1 | More than 1,000 dirty paths or a truncated non-Git metadata walk could produce a stable incomplete fingerprint. | Overflow becomes unknown; unknown workspaces are neither cached nor labeled currently verified. Metadata fingerprints are not full content snapshots. |
| P2 | Startup repeatedly called diagnostic, recall and maintenance commands; current-record reads could load entire audit histories one ID at a time. | One `context` combines recall and pending checks without host probes/init/receipts. Bounded current batch lookup accepts up to eight IDs/12,000 characters and omits audit history. Actual CLI tests pass. |
| P2 | SQL recall lacked a progress budget. | A 500 ms SQL budget returns deferred/incomplete on interruption; no fake empty/checked result. This is not a wall-clock bound on Git, locks, process startup or models. |
| P2 | The evaluator interpreted a superseded 30-day annotation as active permission and required optional machine-verification fields to recognize saved test observations. | Preserve the failed evaluation attempts, review actual events, distinguish operative conditions from history and plain observations from machine verification. The corrected evaluator was subsequently blocked by host credits. |
| Open | Model bookkeeping adds calls/tokens, and similarity does not prove semantic equivalence. | Reuse loaded protocol/context, batch writes/reads and skip unnecessary duplicate matching for proven empty stores. AI semantic judgment remains necessary; a fresh workflow comparison is still required. |

No new runtime module, dependency, daemon, extra summarizer or vector service was introduced.

## Lifecycle simulation

[Host evidence](lifecycle-host.json) records **eight actual invocations: seven completed, one rejected for workspace credits**. All used Codex CLI 0.155.1, `gpt-6-astra`, medium reasoning, ordinary prompts without naming/invoking the Skill, and the same fourteen runtime-file hashes. Two project-A cycles completed the following development work before evaluator predicates stopped their final assessment:

| Phase | Actual project-A evidence |
| --- | --- |
| Requirements | Desired refund policy and one explicitly cross-project reporting preference captured; application implementation remained unfinished. |
| Database design | SQLite schema created; independent checks rejected fractional/negative cents. Tenant/order identities and integer cents were retained. |
| Interface design | HTTP status, tenant boundary, uppercase result and idempotent replay contract defined. |
| Code development | A new conversation saved the inclusive 30-to-14-day correction and implemented the backend/client. Old permission did not remain operative. |
| Frontend/backend integration | Independent Node client made actual loopback HTTP requests to the Python backend; replay, conflicts, tenants, cents and exclusions passed. |
| Testing | Generated suites ran; separate evaluator checks exercised the defined behavior. Plain saved tool-result observations were not promoted to currently machine-verified workspace status. |
| Bug fixing | Evaluator changed the backend's 14 constant to 15, reproduced approval of day 15, then a fresh ordinary conversation repaired the defect. Independent checks passed again. Current same-task checkpoints superseded earlier ones. |

The final corrected four-session run reached requirements/design and then received `Your workspace is out of credits. Add credits to continue.` Further model calls stopped. **The new project-B host session and the final complete evaluator pass were not obtained.** The deterministic seven-stage test checks the 30-to-14 revision, one current checkpoint, preserved exclusions/history, global preference reuse and no A business in B. It is program evidence, not a substitute for the missing host session. Earlier cross-project real-host evidence remains scoped to its earlier release.

Historical annotations may remain in current prose when explicitly superseded. A source excerpt and successful test output establish a historical observation; optional structured verification adds time/code/workspace guards. Neither a model's restatement nor an observation without those guards certifies current code.

## Maintenance policy

- Separate global/project thresholds: **five distinct pending current records**, or **one pending body of at least 1,200 characters**.
- One related-topic pack: **up to eight records/12,000 characters per store**, at most one maintenance batch per user turn.
- Startup already checks pending work; do not prepare it again in the same turn. Task boundaries may force one unchecked pending topic below threshold.
- NOOP/repeated checks do not accumulate body changes. Retired checkpoints leave the pending queue. Pause/read-only/opt-out suppress maintenance.
- No idle/background timer, full-library sweep, default second summarization turn or per-tool summary.
- Exact duplicates are intercepted deterministically; paraphrases require semantic comparison and current revisions. Uncertain equivalence/compaction is skipped. Conditions, exceptions, negation, versions and sources remain protected.
- Superseded originals and compacted old bodies remain audit history. Active working context is reduced; **total disk size, backups and audit history have no automatic retention cap**. User-confirmed forget remains necessary for managed physical deletion.

## Program scale probe

Ten repetitions per operation, local Python 3.14.2/SQLite 3.50.4, isolated synthetic fixture. Seeding excluded from measured operations. [JSON](lifecycle-host.json), reproducible with `evals/check_lifecycle.py --program-only`.

| Active records | Narrow recall median / max | Saturated recall median / max | Maintenance prepare median / max |
| --- | ---: | ---: | ---: |
| 1,000 | 19.196 / 23.997 ms | 19.573 / 20.626 ms | 6.197 / 6.518 ms |
| 10,000 | 21.991 / 26.427 ms | 41.364 / 42.966 ms | 74.667 / 77.238 ms |

Narrow queries returned one record; saturated queries returned four and explicitly reported incomplete candidate coverage; maintenance returned eight. This measures local program operations, **not AI task latency**.

## Performance verification still required

[New comparison status](lifecycle-benchmark.json): not run because host credits were exhausted. The revised harness seeds identical history for on/off, fixes model/reasoning/task/business code, shuffles repeated trials, guards runtime hashes, records the first business edit separately from the first-tool proxy, and keeps failures/unknown metrics separate. These are harness changes, not new results.

Latest actual workflow comparison: [0.4.0 report](maintenance-benchmark.json), eight completed of twelve attempts, approximately 52–53 seconds off versus 86–89 seconds on. It was a partial prepublication sample, not a measured 0.5.0 result or proof that these fixes reduce total AI time.

## Remaining boundaries

Model adherence, semantic extraction, arbitrary paraphrase deduplication and lossless prose compaction cannot be guaranteed by SQLite. Other hosts' automatic behavior, trusted hook events and Windows installation remain unverified. Relevant unknown constraints must be obtained before business changes; overflow/deferred work cannot be called NOOP. The historical S01–S48 acceptance gaps remain open unless separately verified.

### Public installation and CI — 0.5.0

Tested feature commit: `070bdda6821d48f103a9c05de5372aa91b594a9c`. Sanitized results are in [lifecycle-host.json](lifecycle-host.json), under `public_distribution`.

- Actual public `npx -y chrisstarr7/dev-memory <host>` passed fresh and repeat installation for all six selectors on macOS in temporary HOME/cache/projects. Fourteen installed runtime files matched source. New global/project stores were empty; repeated installation retained synthetic records, store identities, capture/recall controls and unrelated project instructions. No hooks or npm files were added to the business project. This verifies distribution/configuration, not automatic model behavior on every host.
- Pinned 0.4.0 to public 0.5.0 upgrade passed using the same temporary cache. Bodies, conditions, exceptions, evidence, revisions, namespace, paused capture and unrelated instructions survived; pending work remained queued once and paused maintenance stayed suppressed.
- Downloaded public source ZIP passed all 57 manifest hashes using TLS-verified curl. The first Python download failed because its local certificate issuer was unavailable; no insecure TLS bypass was used.
- [GitHub Actions 38139487751](https://github.com/chrisstarr7/dev-memory/actions/runs/38139487751) passed all four Ubuntu/macOS × Python 3.10/3.14 jobs with Node.js 22: each ran 157 tests and built a 58-entry release archive.
- These isolated checks changed no real user memories or installed AI configuration. Windows transport and new model timing remain unverified.

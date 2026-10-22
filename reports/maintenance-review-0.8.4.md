# Maintenance and summary review — 0.8.4

## Scope and method

Adversarial source review of the global and current-project maintenance queue, compaction, duplicate aliases, candidate evidence, derived summaries, privacy controls and recall. All regression fixtures use temporary synthetic stores. No real memory content is copied into this report. An independent read-only review challenged candidate/alias interactions after implementation.

The goal is less repeated context and safe organization during ordinary authorized interactions. This release adds no background service, compulsory extra model call, whole-library semantic scan or cross-project enumeration.

## Reproduced findings and repairs

| Finding | Repair and evidence |
| --- | --- |
| Summary preparation returned bodies despite disabled recall and accepted unbounded source sets/bodies | Honor recall/exclusion controls, accept 1–8 same-scope IDs, cap returned source bodies at 12000 characters, report omissions explicitly. Regression: `test_consolidation_honors_recall_controls_and_bounds`. |
| Active summaries could turn inactive/uncertain sources into effective stronger rules | Require revision-pinned active compatible sources and ancestors; prevent strength or cross-project-confirmation escalation. Revalidate legacy summary provenance during ordinary recall, preserving audit data. Regressions: `test_summary_cannot_activate_candidates_or_strengthen_sources`, `test_legacy_active_summary_with_uncertain_sources_is_not_recalled`. |
| Oversized oldest/long records repeatedly blocked smaller pending topics | Select another fitting pending anchor with a bounded fallback. Report oversized IDs, keep them queued, and never mark unread sources reviewed. Regression includes six oversized sources before a smaller distinct topic. |
| A second same-turn maintenance apply with a new idempotency key could mutate again | Reject a second store maintenance mutation batch for matching session/turn IDs; preserve identical idempotency replay. Limit the union of touched maintenance IDs to eight per transaction. |
| Age-triggered review left a recent below-threshold tail idle | Start the drain cycle when the first maintenance apply succeeds, then continue one topic on later interactions until idle. Age is only a review trigger, never proof that a rule expired. |
| Inactive candidates could accumulate without organization | Queue and maintain non-hypothesis candidates in same-status batches. Merge/compact/retag preserve inactive status and create no evidence. Later genuine evidence counts distinct controlled task IDs across canonical and retained aliases, once per task. |
| Candidate alias edits could expose unadopted rules or mix evidence for different meanings | Invalidate an inactive canonical candidate to stale, keeping it out of ordinary recall. Changed inactive inferred habits require a fresh candidate through SUPERSEDE; explicit cross-project confirmation may still revise the existing rule. Old evidence/history remains inspectable. |

The first six focused regressions were run against the previous implementation and failed before repair. Follow-up review produced the candidate/alias regressions rather than accepting the initial patch on inspection alone.

## Runtime contract

- Recall stays in the main workflow, through one focused combined context lookup; normal calls return maintenance metadata without record bodies.
- Five pending IDs, a body of at least 1200 characters, or an unreviewed change waiting seven days starts review. A started store-local cycle may drain its final smaller tail on later interactions.
- At a quiet task boundary, read one related pack per store, at most eight records/12000 characters. Pass stable session/turn IDs. Keep global and project scopes physically separate.
- The AI decides semantic equivalence and lossless wording; SQLite enforces structural fields, status, revision, provenance, budgets and transaction safety. Uncertain rules remain distinct.
- Optional host review is read-only. The primary assistant joins delegated assessment before final delivery and checks each required write receipt. A failed reviewer or write is not completion.
- Pause/disable, read-only, exclusion, turn opt-out, forgotten suppression, historical evidence and revisions remain protected. Automatic maintenance never permanently deletes evidence or expires stable rules by age.
- README translations now share installation order, eligibility, three architecture/workflow diagrams, maintenance limits, controls, privacy, diagnostics and update instructions.

## Verification

- The frozen-runtime full suite ran **259 cases**: 257 passed, one platform-specific case skipped, and one existing candidate-revision fixture failed because it changed the candidate meaning while expecting historical evidence reuse. That behavior is now deliberately rejected. The fixture was changed to revise only title/source, preserving its task-ID forgery/deduplication assertions; the complete **22-case efficiency module then passed**. Runtime code did not change after the full run. The 50-case maintenance module, including all ten new regressions, passed in that full run. This is full coverage plus a focused fixture rerun, not a claim that a subsequent single full invocation was green.
- An earlier in-progress full run had a transient installed-doctor failure in the repeated DeepSeek npx scenario. Its standalone rerun passed, and the frozen-runtime full run also passed it. The original transient cause was not established; it is not attributed to a specific performance or permission defect.
- The Skill validator, Python syntax parsing and Git diff checks passed. Nine changed documents had balanced fences and 79 resolvable local links; the four READMEs contain 12 Mermaid diagrams in total.
- The release builder packaged 78 public files plus its manifest; every archive file hash was checked. Private store files are excluded. Public file bytes are LF-normalized to match the GitHub snapshot.
- Local Codex installation upgraded to 0.8.4 with runtime verification. All 14 installed Skill files matched source. Global/project configuration files were byte-for-byte unchanged; the current project remained full-project and both store namespace identities were preserved. Installation requires a new host session to reload guidance.

## Limits

Program tests prove deterministic transitions on synthetic data; they do not prove an AI preserves every prose condition or always classifies natural language correctly. Related matching is bounded and compatible-kind/claim oriented, not a complete cross-category contradiction detector. All-oversized queues still need a separate targeted source review. Same-turn enforcement depends on supplied stable session/turn IDs. Historical evidence remains on disk; logical compaction is not secure deletion or a fixed disk cap.

No new paid host-model benchmark or end-to-end capture session was run for this release. No claim is made that total coding latency improved by a measured amount. Mermaid fences/links are checked statically; no renderer screenshot is claimed.

# Memory use and maintenance — 0.6.0

## Axioms and outcome

1. A recalled record only improves a task if its applicable constraints change a decision or check (A1). Retrieval alone cannot establish execution.
2. Dropping an exception, using a superseded rule, or importing another project's business changes the contract (A2). Speed cannot justify those losses.
3. Memory processing consumes model context, tool calls and elapsed time (A3). SQLite timing alone cannot establish whole-task efficiency.
4. Routine maintenance cannot obtain evidence that the user never supplied (A4). Similar wording and age do not establish equivalence or expiry.

The outcome is bounded, applicable recall followed by concrete use and accurate incremental maintenance. Success requires focused-rule coverage under noisy history, no cross-project leakage, no evidence inflation, correction/source invalidation, a threshold-triggered backlog that reaches idle, and at most one maintenance pack per original turn. Real model behavior and matched on/off timing must be reported separately from program tests.

## Assumptions challenged

| Assumption | Why challenge it | Basis | Decision |
| --- | --- | --- | --- |
| More recalled hard rules help every task | Unrelated hard rules occupy the detail budget before relevant soft rules | A1, A3 | Rank query-related rules first; retain bounded unloaded candidate metadata and incompleteness |
| A returned ID proves the AI used it | Loading is neither application nor verification | A1 | Add optional revision-guarded USE receipts for concrete actions; label them AI reports, not behavioral proof |
| A fixed pending threshold completes maintenance | A threshold of five leaves a tail of one to four after review | A1, A2 | Latch a maintenance cycle after the threshold; drain one bounded topic on subsequent interactions |
| Every new write may return another pack | Checkpoint/correction writes can produce repeated maintenance in one turn | A3 | Use existing turn receipts to suppress further packs after that turn's maintenance |
| Old records should be deleted by age | Stable preferences and unfinished tasks may remain applicable | A2, A4 | Archive only evidence-supported obsolescence; keep audit sources until explicit forget |
| A shorter prompt necessarily speeds the whole workflow | Model decisions, process startup and useful work dominate different tasks | A3 | Reuse lifecycle/maintenance evaluations and matched timing harness; report actual failures and limits |
| The AI should calculate intermediate database revisions | A correct semantic merge can still roll back on a mechanical revision error | A2, A3 | Resolve loaded snapshots within one atomic maintenance batch; reject externally stale snapshots |
| A checkpoint captures the requirement | Progress prose can omit the operative business contract | A1, A2 | Save a canonical desired requirement separately from the observed checkpoint |

## Ground truths and implementation trace

- GT1: 0.5.5 recall sorts hard strength before lexical relevance and returns overflow IDs without descriptive metadata (`_recall_store`). Relevant rules can be displaced by unrelated hard history.
- GT2: 0.5.5 maintenance returns waiting when fewer than five short records remain (`_maintenance_plan`). No persistent cycle drains that tail.
- GT3: Receipts already carry session/turn identity and structured operation results (`_apply_store`). They can report concrete AI use and bound returned maintenance without a new database or extra command.
- GT4: Current stores and tests already preserve scope, revision guards, evidence, summaries, opt-outs and disabled capture. Those boundaries remain required.
- GT5: A real ordinary-task maintenance run made the correct semantic distinction but failed twice: single-record COMPACT revision shape, then post-merge revision arithmetic. Both batches rolled back. The final API accepts a scalar COMPACT revision and safely resolves initial snapshots across merge/compact/review in the same transaction.
- GT6: Real requirement-stage runs exposed flat operation JSON and progress-only capture. The entrypoint now supplies one valid nested ADD + CHECKPOINT example, allowed enums and source types. A simple save no longer requires loading the entire advanced protocol. Corrections get a bounded save attempt before affected edits.

GT1 + A1/A3 → prioritize applicable query matches and provide bounded candidate descriptors for selective follow-up. GT2 + A2/A3 → maintain a local cycle flag until idle, one topic per later turn. GT3 + A1/A4 → USE is a self-reported action receipt with current revision validation, no new memory/evidence. GT3/GT4 → turn limits and private controls use the existing store transaction.

## Lifecycle use contract

Requirements preserve eligibility, exclusions and negative requirements; schema/API design maps them to fields, constraints and interfaces; implementation applies them before edits; integration checks cross-layer boundaries; testing uses stored regression conditions; bug fixing revises the violated rule and investigates missed recall/execution/expiry; handoff records the actual remaining work. A phase change alone creates neither a new business rule nor evidence. Reuse the same canonical rule and task while their applicability remains valid.

## Validation — 2026-10-14

All evaluations use synthetic temporary homes/projects. No installed personal Skill, real memory store or business repository was modified. Host sessions use **codex-cli 0.155.1, gpt-5.5, medium**, with fresh session context and no explicit user Skill/maintenance invocation. Installed project guidance provides automatic routing; hooks are not enabled. Other model aliases were not assumed compatible.

### Program and adversarial checks

The final local suite passed **195 tests in 32.531 seconds**, with two native Windows checks skipped on macOS. It includes the benchmark-inspection regression and malformed-ID guard; the earlier 194-test iteration also passed. See [verification.md](verification.md). New behavior checks cover:

| Counterexample | Result |
| --- | --- |
| Twelve unrelated hard rules compete with one relevant informational business rule | Relevant rule receives the body budget; bounded candidate metadata and incompleteness remain available |
| Five pending records drop to two after review | The cycle continues below threshold and reaches idle when reviewed |
| Correction/checkpoint/NOOP follow maintenance in one turn | No second automatic pack; the next turn may drain the remaining topic |
| Old store has only one active short record | One-time protocol upgrade requeues it and enables bounded draining |
| Rule changes externally between read and use/review | Stale USE and maintenance snapshots are rejected |
| Merge, compact and review use the initial snapshot in one batch | In-batch revisions resolve; failed batches still roll back entirely |
| USE attempts content/evidence injection, wrong-task or project-specific global notes | Rejected; successful USE changes neither memory data revision nor evidence |
| Usage prose would duplicate business in receipts | Current response returns the action note; persisted receipts retain only ID/revision/report metadata |
| Paused/read-only/opt-out, source revision and forget boundaries | Existing protections remain covered; derived summaries invalidate on source changes |

USE remains optional and is bundled with an existing apply, never an extra required call. A reported ID is not proof of correct code; independent behavior checks provide the latter evidence.

### Real project-cycle evaluation

The real lifecycle run passed requirement capture → schema/API artifacts → corrected implementation → frontend/backend HTTP integration → injected boundary bug → regression fix → project B. Each phase starts a fresh CLI session.

| Phase | Task time (s) | First tool (s) | Tool calls | Input tokens | Cached input subset | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Requirements / schema / API | 142.988 | 30.486 | 15 | 176,994 | 155,648 | 5,296 |
| Correction / code / frontend integration | 213.537 | 27.527 | 16 | 256,361 | 228,096 | 9,312 |
| Testing / injected bug / fix | 136.498 | 14.769 | 20 | 328,928 | 301,568 | 5,478 |
| Switch to project B | 97.216 | 14.474 | 18 | 227,916 | 182,400 | 3,523 |

Independent checks passed integer cents/status, idempotent replay, tenant-isolated keys, conflicting-key rejection, every eligibility/exclusion and the 14-day boundary, no cross-tenant order leak, and actual frontend/backend loopback HTTP. An injected 15-day eligibility bug failed independently before the AI fixed it; the same checks passed afterward. A retained only one active business rule and one current checkpoint; B recalled the confirmed global preference without A's business rule. Two phases reported concrete rule use; code checks, not those reports, established the tested behavior. Actual tool-result observations were recorded; structured verification metadata count was **zero** and is not claimed as implemented model output.

**Source boundary:** this successful lifecycle used an earlier 0.6.0 candidate. Later changes minimized USE receipts, improved error messages, added the maintenance revision resolver, invalidated old recall-cache formats, and refined instructions. The maintenance evaluation below and final program suite cover those changes; the entire lifecycle was not repeated on the final bytes. Runtime hashes for both snapshots are included in the local evaluation artifact; this distinction must not be collapsed into a claim of exhaustive final-source end-to-end verification.

### Real automatic maintenance

| Fresh session | Task time (s) | Tool calls | Input tokens | Cached input subset | Output tokens | Observed successful operations |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Ordinary policy inspection | 92.035 | 9 | 142,808 | 120,064 | 3,568 | MERGE_DUPLICATES, COMPACT, MAINTENANCE_REVIEW |
| Equivalent requirement in new words | 68.857 | 9 | 148,292 | 130,688 | 2,443 | MAINTENANCE_REVIEW; no new rule |

The first session merged three equivalent normal policies, compacted a separate damaged-item policy and preserved its 7-day window, ReturnPolicyV2 limit and prose-only `manual_review` / `supervisor_override` exception. Structured protected fields and original evidence survived unchanged. The second session reused the canonical rule without duplicate insertion. Scope isolation and no business-code edits passed. The maintenance runner does **not** sample first effective action, so no value is inferred here. These are total task times, not incremental memory overhead.

Maintenance-evaluated runtime SHA-256 checkpoints:

| File under `skills/dev-memory/` | SHA-256 |
| --- | --- |
| `SKILL.md` | `97aa6b806342b61cb9bf135ba5feee3bf6a89ece41a3cc19aa12831a295d9f88` |
| `references/protocol.md` | `4926edbd2aad11170192775263f11b5b1e2b320c27680efc3a89fc47f0695ca8` |
| `scripts/dev_memory.py` | `04a7a11ec3c93ac958ce45dd2f831f0336d8dcafbc885bce4e486f8a9acba85e` |
| `scripts/dev_memory_store.py` | `3c4b4acc4e1c8155ec13452fb4c3a1868274b923b5ca3d5d9458f325ab1336f9` |
| `scripts/dev_memory_setup.py` | `e7640dc8bc430c37af7080932d81f528e957f5cb0af743ed4c46822df1f00661` |

### Matched on/off workflow timing — incomplete

Attempted eight shuffled trials: two repetitions of memory on/off × empty/history stores, identical current policy, starting code, gpt-5.5 and medium reasoning. History is seeded identically in both modes. The harness captures first observable tool action, first business edit, full task time, tool/token use and six independent business cases. Cached input is a subset and is not added again to input+output totals.

**There are no completed valid comparison samples.** Four empty-store trials explicitly failed with host `Your workspace is out of credits`; one emitted four tool starts before failing. The four history trials were lost to a runner `KeyError: claim_type`: post-run inspection incorrectly treated list-summary rows as full records. The runner now fetches full records; a program regression checks this contract. No further paid/model retry was made after the quota failure. Runner-failure rows cannot establish whether a model task completed and are not latency or accuracy samples.

| Cell | Scheduled | Valid completed | Completed-task / first-action / tools / tokens / accuracy |
| --- | ---: | ---: | --- |
| Off / empty | 2 | 0 | Unavailable |
| On / empty | 2 | 0 | Unavailable |
| Off / history | 2 | 0 | Unavailable |
| On / history | 2 | 0 | Unavailable |

No valid key-constraint omission rate or improvement claim follows from this run. Historical 0.4.0 timing remains in [lifecycle-review.md](lifecycle-review.md), and cannot be extrapolated to 0.6.0. A future matched run needs available host quota; the corrected harness is supplied. CLI process startup and ephemeral-host initialization also differ from a warm desktop conversation. Faster SQL and fewer mandatory protocol reads do not establish negligible whole-task delay.

### Program-only scale probe

Ten repetitions per cell; synthetic data only, no AI invocation. Medians:

| Active records | Narrow recall | Saturated recall | Maintenance preparation |
| ---: | ---: | ---: | ---: |
| 1,000 | 22.679 ms | 25.355 ms | 11.455 ms |
| 10,000 | 25.327 ms | 54.487 ms | 127.303 ms |

Saturated retrieval reports incomplete/candidate overflow and preserves its bounded output. Preparation returns at most eight related records. These measurements include the local program path, and exclude AI inference, semantic review and host tool latency.

A final adversarial extension reproduced an unhashable-ID exception for scalar COMPACT input (`id:[]`). A two-line ID guard now returns a transactional validation error; the final suite covers it. This guard was added after the successful real maintenance sessions; they were not repeated for the malformed-input-only change. Source hashes distinguish the snapshots.

The final program-only probe includes that guard; its store-script SHA-256 is `8a6db928ac2d2ebfe2f5b066ddc6f195484f00994043e6c545ac86d984de69ca`.

### Public update command

A real public npx check at feature commit `4defe59f0065208bc9fa493eee29467f92eaaa15` passed a pinned 0.5.5 A install → unqualified 0.6.0 B update/init → A reuse using one temporary npm cache. A retained body, conditions, exceptions, evidence, revisions, namespace and paused capture; B started empty with a separate namespace; unrelated team guidance survived; all fourteen installed runtime files matched that commit. The final malformed-ID guard does not change installation. This is transport/upgrade evidence, not another AI session.

## Remaining limits and review conclusion

The implementation improves applicability, actionable use, capture reliability and maintenance completion while reusing the existing stores and receipts. It adds no daemon, external model, vector service, dependency or extra framework. It does **not** prove perfect AI compliance or net project-time savings. Automatic routing depends on actual host instruction loading and model behavior. Real Windows Codex desktop, trusted hooks and other hosts' full model sessions were not newly verified. Semantic merging remains fallible; uncertain records stay intact, age alone does not expire a rule, audit history has no automatic disk-size cap, and explicit forget remains necessary for permanent deletion.

Earlier failed real runs are retained as findings: unsupported model alias; flat operation JSON; requirement saved only as progress; a timeout; the two transactional maintenance failures; evaluator source/kind assumptions; and the blocked/broken comparison above. Requirements are not downgraded to progress-only capture, a valid desired `decision` is not failed merely because it is not named `business_rule`, and user source evidence is checked in actual evidence rows. Evaluation errors are reported separately from model errors.


## Final publication evidence

[Native CI 38489141510](https://github.com/chrisstarr7/dev-memory/actions/runs/38489141510) at `8b52f645fcd064973912d81489d548db075bbaa9` passed all six Ubuntu/macOS/Windows × Python 3.10/3.14 jobs: 195 tests and 66-entry release build per job. The final malformed-ID guard is included. Public source transport verified all 65 manifest entries at that commit; a fresh public npx install matched all fourteen runtime files. CI does not run AI models or the Windows Codex desktop App. The final publication follow-up changes only evidence documentation and its manifest.

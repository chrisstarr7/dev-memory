# Development lifecycle review — 0.8.5

## First-principles contract

Memory is durable decision support, not a transcript, task tracker or proof that current code passed tests. A useful record must change a later decision, retain evidence and applicability, and remain below current instructions and authoritative project facts. A useful recall must reach the relevant development phase without opening unrelated projects or forcing extra model work. A useful summary must preserve meaning and source confidence. Storage success, semantic correctness, application behavior and host automation are separate claims.

## Lifecycle exercise

An independent assistant used installed 0.8.4 in an isolated synthetic project, following ordinary requirements through design, implementation, correction, delivery and a subsequent refund feature. It created real small Python artifacts and executed their tests. A second fresh assistant continued the same project with a new feature and no inherited discussion. Raw synthetic artifacts remain outside this repository; no real private memories are included here.

The first exercise saved four active project rules (integer cents; no charging cancelled orders; synchronize API docs; accept zero and reject negative amounts), and three inactive global candidates. Every phase reused the same opaque task reference: no manufactured independent tasks, active global habits or task checkpoints. A temporary three-item reply limit was not saved. The important amount correction was captured before implementation. Actual app checks: three tests passed initially; a zero-amount regression failed before the fix; five passed afterward; the next feature passed ten tests. There were 20 memory CLI calls: setup 1, context 5, match 7, apply 4, list 3. Some empty-store match calls were unnecessary, and fixed global reservations caused repeated incomplete project context despite no active global rules.

The fresh assistant received only a new batch-payment requirement, the Skill and the project path. It loaded two project bodies, fetched the two missing relevant rules before editing, reused the payment/ledger capabilities and passed all 14 app tests. The reusable-code preference acquired a second independent task signal and was promoted by the program; the narrower existing test preference was not merged with a broader new test candidate because its conditions differed. The new batch failure-isolation contract stayed project-local. At the quiet boundary, one maintenance pack of four distinct rules was reviewed without unnecessary merging; the unread documentation rule remained pending_next_turn. There were 11 memory CLI invocations, including one argument-position repair and one redundant delivery lookup. Their reported command wall times totaled about 21.45 seconds; this is neither total task latency nor a matched benchmark.

Both native-assistant exercises used the baseline installed 0.8.4. Patched 0.8.5 behavior is verified by deterministic regressions and the program-only scale probe below; this distinction avoids attributing baseline model behavior to an unrun updated host session.

## Findings and changes

| Finding | Change |
| --- | --- |
| Existing code could be saved as a desired convention, including a permissive authorization bug | Reject desired/preference claims sourced only as code_observation; observed facts remain valid. Current user/spec authority must establish required behavior. |
| Single show/list bypassed disabled/excluded recall | Apply the same read controls already used by context/current-show/summary preparation, without returning body/evidence/history/title data. |
| Current-only lookups and summary preparation omitted stale verification labeling | Use the shared verification classifier, computing current metadata at most once per batch; unverified single inspection skips unnecessary Git/fingerprint work. |
| Empty/inactive global scope still reserved three of five details and most characters | Lend its unused capacity to current project only when no eligible global rule exists or global recall is disabled. Preserve cache-stable allocation; restore reservations when global rules activate. Never raise total limits or enable candidates. |
| Context candidate_count looked like a saved-candidate count | Context now reports matched_count; doctor candidate_count retains its saved inactive-record meaning. |
| The workflow could redundantly match against a proven empty store or misplace a root option | Explicitly reuse unchanged empty_store:true evidence and skip that match. Document global-root before the subcommand. A zero-hit query alone remains insufficient. |
| Evaluators required forbidden checkpoints and transient test-result writes, and reported obsolete versions | Align lifecycle capture checks with durable project/global rules, read actual runtime version, and delegate the obsolete activation evaluator to this one maintained implementation. |
| Lifecycle host runner used Unix-only subprocess pipe/kill handling | Use bounded standard subprocess completion and file logs on all platforms. Do not invent first-tool timestamps from buffered events. |
| Independent API probe missed an already-refunded order under a new key, and client non-2xx rejection | Add the two promised behavioral checks. Policy numeric checks inspect actual rule text, not generated IDs/timestamps. |

## Participation by phase

| Phase | Recall/use | Eligible capture | Excluded |
| --- | --- | --- | --- |
| Requirements | Current business rules, exclusions and acceptance constraints | Confirmed durable requirements and corrections | Ambiguous decisions and provisional assumptions |
| Design | Contracts, ownership, compatibility and prior decisions | Confirmed tradeoffs and applicable boundaries | Speculative architecture treated as policy |
| Implementation | Current conventions, canonical capabilities and verified facts | New durable conventions/facts with their actual sources | Every diff, symbol or legacy bug as a required pattern |
| Verification | Acceptance/regression obligations and historical lessons | Durable evidenced causes and prevention checks; version-pinned results when useful | Automatic test-progress snapshots or claiming an old pass is current |
| Correction | Current request overrides old memory | Revise confirmed rules before affected edits; invalidate derived readers | Old meaning silently accumulating evidence for a new candidate |
| Delivery | Applicable artifact/reporting/release requirements | Durable feedback; inspect required store commit receipts before final response | Temporary reply limits, TODOs and checkpoints |
| Later task/project | One focused global/current-project lookup, targeted follow-up if incomplete | Genuine new independent evidence, within its own scope | Other-project scans or promoting repeated turns of one task |

## Verification

The full Windows/Python 3.14 suite completed **271 tests: 270 passed and one platform-specific Bash case skipped**. The eight offline evaluator checks use actual fake processes, synthetic stores and no external model calls. All four new lifecycle runtime regressions were independently rerun by a read-only reviewer and passed. Skill validation, Python syntax and Markdown checks passed (nine documents, 83 local links, 12 Mermaid fences; diagrams were not visually rendered).

After this full run, remote 0.8.4 CI was inspected: Linux and Windows passed, while both macOS jobs failed the oversized-queue test's assumption that first insertion sorts first. Actual queue priority uses second-resolution timestamp then UUID; fast insertion on macOS tied those timestamps. The test fixture now explicitly orders the six oversized records ahead of the small rule. No runtime change was needed. The final maintenance module was rerun after this fixture repair: **all 50 tests passed**. Runtime code did not change after the full suite.

Program-only scale probe (ten repetitions, synthetic stores, no model calls): at 1000 records, narrow recall median 315.783 ms, saturated recall 315.740 ms, maintenance 79.175 ms with 8 returned records. At 10000 records, narrow recall 326.286 ms, saturated recall 596.117 ms with 5 returned records and explicit incompleteness; maintenance median 562.825 ms and its last result was deferred by the query budget. These are local program timings during other test activity, not a matched end-to-end performance claim.

A proposed planner hint was independently tested and rejected: forcing the term index/CROSS JOIN preserved the same eight ranked IDs but worsened the related-query median from 615.841 ms to 1472.519 ms. Both maintenance variants still deferred. The SQL was retained; no unsupported speed fix or enlarged query budget was shipped. Large highly overlapping topic sets remain a known maintenance-progress limitation.

Release packaging verifies all 80 public file hashes against both staged Git blobs and archive entries, excluding private SQLite stores. Local installation upgraded to 0.8.5 with its runtime check passed; all 14 installed Skill files match source and both existing configuration files are byte-for-byte unchanged. Project capture remains full-project and existing namespace identities are preserved. A new host session is required to reload updated guidance.

## Limits

Native-assistant exercises are actual tool-driven behavioral observations, not proof of automatic Codex CLI/Desktop instruction discovery or every-turn enforcement. Fake-emitter tests prove evaluator process/log handling, not model compliance. No matched latency improvement is claimed. Git fingerprints exclude ignored inputs, environment changes and external services; they are bounded metadata checks, not complete test-environment snapshots. Host timeout reaps the direct process but does not recursively terminate independently spawned descendants. Semantic equivalence and requirement interpretation still need AI review.

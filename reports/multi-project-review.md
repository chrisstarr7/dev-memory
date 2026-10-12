# First-principles contract — multi-project initialization

## Axioms
- A1: Public program files and private memory are different resources; replacing a program must never replace project data.
- A2: A project's successful initialization requires its own stores and valid host binding; existence of another project's program is insufficient evidence.
- A3: A success receipt must describe committed observable state; a skipped check or failed write is not success.

## Outcome
A → B → A using the same installer must share one managed runtime, initialize independent project namespaces, preserve A's data/controls/team instructions, and report program and project results separately. Unknown files, malformed bindings and concurrent replacements must fail safely.

## Challenged assumptions
| Assumption | Evidence / concern | Decision |
| --- | --- | --- |
| Existing Skill means initialization is done | B can lack activation and data (A2) | Always initialize/check the named project |
| Every repeat must replace the program | Same bytes need no rename; Windows may hold files open (A1) | Reuse identical managed files; replace changed files or explicit repair |
| Wrapper logic makes all entry points idempotent | Shared install still raises already_installed (A2) | Put ensure/update behavior in shared install |
| Two projects can replace shared files concurrently | Validate/rename operations are not one atomic action (A1) | Scope one nonblocking filesystem lock to the target |
| Checking data_revision after commit is harmless | A read failure can falsely report a committed write as failed (A3) | Return revision obtained in the committing transaction |
| Windows paths always use backslashes | C:/ paths can enter metadata (A1) | Reject both separators in global project markers |
| A returned installed status proves desktop access | CLI/ACL tests do not invoke the user's App (A3) | Keep sandbox/E2E verification explicitly separate |

## Ground truths / delivery mapping
- GT1: Current shared installer raises already_installed without upgrade; source --project has a different policy. Unify at the shared entry (A2).
- GT2: Current managed runtime whitelist is 14 files and excludes all stores. Compare those files, retain strict unknown-file rejection (A1).
- GT3: Stores already use independent namespaces and configuration preservation. Verify A/B using native-platform CI and the real public npx transport (A1/A2).
- GT4: SQLite revision can be read in the write transaction. Remove the extra postcommit read; inject a failing postcommit reader in regression (A3).

## Stress test / completion gate
Test an unknown existing directory, extra files, concurrent setup, stale cached source, interrupted rename rollback, malformed B activation, paused A, mixed host bindings, UTF-8 paths, Windows forward-slash global contamination, duplicate/correction/forget lifecycle. Rebuild only whitelisted public sources. Traceability, ground-truth coverage and phase completeness were checked against the changes and regression cases below. Actual Codex App / semantic / latency evaluations are not inferred from program CI.

## Repository-wide adversarial coverage — 0.5.4

| Boundary | Confirmed correction or regression coverage | Evidence boundary |
| --- | --- | --- |
| Install / update / uninstall | Shared entry now ensures one managed runtime; byte-identical reuse, changed-file update, explicit repair, target lock, rollback, pending cleanup, downgrade refusal | Deterministic tests; user-specific Windows error path/version unavailable |
| Project binding | A → B → A, separate namespaces, original guide/paused settings retained; invalid B manifest rejected before shared program mutation | CLI/Node entry plus native-platform CI; not model instruction adherence |
| Windows path isolation | Forward/backslash drive paths and UNC markers rejected globally; program and host-guide junction escapes rejected | Synthetic paths; native junction test must run on Windows |
| Transaction receipts | Revision returned from the committing transaction; no fallible postcommit database reopen | Injected reader failure, committed row and receipt inspection |
| Independent reads | Global revision-read failure now returns unavailable while current project recall continues | Failure injection plus actual project record returned |
| Provenance / truth | Desired/observed/hypothesis, source identity, independent evidence, revision guards and idempotency tested | Caller authenticity and paraphrase meaning remain semantic judgments |
| Recall / continuation | Bounded global/current-project/task reads, budgets reserved, overflow/deferred visible, fresh/resume/compaction forced, workspace and data revision invalidation | Lifecycle regressions; metadata fingerprint is not a complete content snapshot |
| Duplicate / maintenance | Exact dedupe, case/condition/task/version boundaries, merge alias invalidation, 5 changed records or 1200-character long body, <=8/12000 pack, NOOP and opt-out suppression | Program tests; prose preservation still reviewed by current AI |
| Delete / backup / restore | Same-store backup identity, connected derived/alias delete preview, forgotten suppression on restore, partial cleanup reported | No secure erasure or cleanup of external/host copies |
| Privacy / distribution | Secret patterns, global scope guards, Git tracking/exclude checks before database/view/backup writes, isolated synthetic data, npm/release allowlists | No claim to detect all sensitive prose; no data encrypted by default |
| Host / speed | Project guidance and optional hooks retain honest capability flags; no extra model/daemon/runtime dependency | No new desktop session, hook chain, semantic model evaluation or matched AI latency run |

### Strong counterexamples checked

Existing public Skill + empty B; paused A revisited; two installs/uninstall targeting one directory; changed public file; older cached source; unknown extra user file; failed staged rename; Windows open old file during cleanup; malformed B manifest; junction into another directory; denied ordinary-user access; global database fails during recall; successful write followed by unavailable revision reader. No automatic blanket ACL grants, cache deletion, or project-data fallback is introduced.

### Remaining limitations

- The current pre-change Node `--project` entry already attempted automatic upgrade. Its exact reported A/B Windows failure cannot be attributed conclusively without the original error/entry version. A shared-entry inconsistency is independently reproducible; cached old entry, unmanaged copy, and permission denial remain distinguishable possibilities.
- An old cached installer cannot acquire new code by itself. Updated receipts include `program_version`/`program_action`; documentation gives an explicit current-branch fetch if necessary. Normal command remains short. New source refuses to downgrade a newer installed version.
- Locks are nonblocking and bounded. A terminated process can leave a lock; inspect activity before deleting that named lock. No unsafe automatic stale-lock eviction.
- A real Windows Codex App session has not been run. Program/ACL/junction CI does not prove the App's permission profile or model follows instructions.
- AI semantic equivalence, correct scope extraction, and preservation of prose constraints are not fully deterministic. Similarity alone cannot authorize merging.
- Active-context compaction does not cap receipts, revisions, evidence or backup disk usage. Destructive automatic history pruning is not introduced.
- The earlier matched AI workflow comparison showed material overhead. No new model timing or semantic model run is performed in this review; faster reuse/local SQL is not an end-to-end latency claim.

## Verification

Initial 0.5.3 local suite: 177 tests passed in 27.499 seconds (two native Windows skips). Native CI [38271569317](https://github.com/chrisstarr7/dev-memory/actions/runs/38271569317) passed five jobs; Windows Python 3.14 failed only temporary cleanup in the new A/B test because its SQLite fixture did not close connections explicitly. Changed the fixture to `contextlib.closing`; installation assertions, native ACL and junction tests passed. The failed run is retained as failure, not counted as full success.

The initial public unqualified npx command, using one temporary cache across 0.5.2 → 0.5.3, passed B → A → B. A's corrected rule/conditions/evidence/revision, pause and team instruction survived; B had an independent empty store and recalled the confirmed global preference without A's business. Tested commit: `45e46f4fb69ffacd8d1e2008a2a640d811deb072`. This was macOS program/transport evidence, zero model calls.

Further privacy regression: force-tracking memory after initialization or removing its Git exclusion could bypass the initial check. 0.5.4 checks only the current project's memory path before writable database connections, views and backups. It refuses unknown Git protection or tracked data, preserves independent global results, and does not edit Git history. Read-only operations do not add these write checks. Git projects require two bounded Git metadata commands on a write; no full code/history scan, new AI tool call or external model is added. No end-to-end latency claim follows from this.

Final 0.5.4 local suite, native CI and repeated public transport checks pending at this hardening commit. One initial local installer run exposed a missing closing parenthesis in new human output; corrected before publication and rerun. Historical evaluation reports retain their own version/hash identities.

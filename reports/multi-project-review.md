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

Final 0.5.4 local suite: **180 tests**, passed in **32.454 seconds**, two native Windows checks skipped on macOS. Native [six-job CI](https://github.com/chrisstarr7/dev-memory/actions/runs/38272839308) at `0db4021bab2dd7ce744c9f1c025744b85ef6931c` passed Ubuntu/macOS/Windows × Python 3.10/3.14, Node 22, test suite and 65-entry release build. Windows runs the native ACL and junction checks and skips only the POSIX Bash test; Ubuntu/macOS skip only the two native Windows checks. A → B → A assertions passed on both Windows jobs. Format and whitespace checks passed.

A second public unqualified npx test retained one temporary cache across 0.5.3 → 0.5.4. B updated the shared runtime and initialized independently; A and B subsequently reused identical program files. A's saved rule, conditions, evidence, revision, pause and team guide survived; B's empty store excluded A business while read-only recall returned the confirmed global preference. The 14 installed runtime hashes matched the tested source. Installation timings below include transport; they are **not AI workflow timing**.

The final program-only scale evaluation used 1,000 and 10,000 synthetic active records with ten repetitions. At 10,000 records, narrow read median was 22.181 ms, saturated read 41.362 ms with incomplete/candidate-overflow flags, pending maintenance 72.987 ms with eight records. These numbers exclude AI/model orchestration and cannot establish negligible workflow overhead.

### Reproduce deterministic checks

```sh
python -m unittest discover -s tests -v
python evals/check_lifecycle.py --program-only --output /outside/source/program-check.json
python build_release.py /outside/source/dev-memory.zip
```

The public transport experiment ran the short command in temporary A/B projects with a temporary HOME/cache: prepare A on the old published source; save synthetic project/global rules; pause A; publish the named new source; run the same unqualified command in B, A, B; compare rows, evidence, configuration and installed file hashes; use read-only `context` in B. No real user store, installed Skill, administrator privilege or model call was used.

### Recorded public transport and source-package evidence
 One initial local installer run exposed a missing closing parenthesis in new human output; corrected before publication and rerun. Historical evaluation reports retain their own version/hash identities.

```json
{
  "public_transport": {
    "status": "passed",
    "runtime_version": "0.5.4",
    "host_platform": "darwin",
    "tested_commit": "0db4021bab2dd7ce744c9f1c025744b85ef6931c",
    "command": "npx -y chrisstarr7/dev-memory codex",
    "same_unqualified_spec_cache_across_upgrade": true,
    "source_version": "0.5.3",
    "observations": [
      {
        "project": "B",
        "program_action": "updated",
        "program_version": "0.5.4",
        "elapsed_seconds": 28.509
      },
      {
        "project": "A",
        "program_action": "reused",
        "program_version": "0.5.4",
        "elapsed_seconds": 9.223
      },
      {
        "project": "B",
        "program_action": "reused",
        "program_version": "0.5.4",
        "elapsed_seconds": 8.491
      }
    ],
    "a_saved_rule_conditions_evidence_revision_preserved": true,
    "a_pause_and_team_guide_preserved": true,
    "b_independent_empty_store": true,
    "b_recall_excludes_a_business_and_includes_global_preference": true,
    "runtime_sha256": {
      "SKILL.md": "3cec7d447fe54a11de8ee46b3ff9b71d62ba6401de07a7f3d65ffb28d821696e",
      "LICENSE": "601e5c25c2e9faaafe4f05554d5f46e7c13d56eb1a016e79363a56780dbdf71c",
      ".dev-memory-skill-install": "746f3fa0fe42a57384b3f394acccd08bf3c2d07421184fb6a8980b23e7a7282f",
      "agents/openai.yaml": "9a8922dacaac48fd36dc0b77fd30b4cb5444ad402c5ef2f73cc5567b4264287e",
      "assets/config.example.json": "7ebca4f7b77e0b818f83c188b55c9c5f145650727d73885220c3a67b6786adfe",
      "references/protocol.md": "88cfa26d2135eb12657c5ee02038f20f69f339ba3da374c073e54d9a89a1d47c",
      "references/codex-hooks.md": "fccbc5c0ad2f6eb45296c2b6719f72e9bb5f9c65b86d9e739e4bd66f34fd74ff",
      "references/verification.md": "98558415eb8aa60db84b85497b38fcb3ab7b58659fc2e5ab8028af0e6d77f8c1",
      "references/setup.md": "702c598c51bcbaebb18da5c1dbd173bb981956ce7c28050fc4baceec1af098b8",
      "scripts/dev_memory.py": "e7c33d43c0a8f24c62901a25460020b38623197993d7a7fae844305d16e34fee",
      "scripts/dev_memory_store.py": "3935858f327ef4ea66f08a3ae322b0544b873ed3c2b16557b858c8ebcce803ad",
      "scripts/dev_memory_setup.py": "31f5b8f027f961f3eaa649040caf2288a10a028ad4ff5597b84958692730a549",
      "scripts/codex_hook.py": "bab255c139a1bbc0707868ede09dc7349c975d8d9f27eeded00889c04b95d807",
      "scripts/dev-memory": "603b86ad31de614321f3092b54e29bacd50bba9421c4fc1710e9e50fb07cdc24"
    },
    "models_called": 0,
    "windows_codex_app_e2e": "not_run",
    "real_user_stores_modified": false,
    "timing_kind": "installation_transport_only_not_AI_workflow"
  },
  "source_package": {
    "status": "passed",
    "commit": "0db4021bab2dd7ce744c9f1c025744b85ef6931c",
    "version": "0.5.4",
    "manifest_files_verified": 64,
    "transport": "TLS verified public source ZIP",
    "sha256": "506abfc7a70470bcc0029c7db84a20fb74143c5777dbef5b56259453b018af10"
  }
}
```

## Completion gate

- [x] Traceable contract: shared program and independent project initialization, physical/privacy boundaries, truthful receipts.
- [x] Each ground truth has a regression or explicit verification boundary.
- [x] Inversion/partial-failure stress cases checked; failed attempts preserved.
- [x] Shared root fixes and standard-library primitives; no additional runtime dependencies, model calls, daemon or full-library scans.
- [x] Nontrivial diff reviewed for unnecessary abstraction; the installer wrapper delegates reuse/update to the existing shared module, and the Git guard is reused at writable boundaries.

Actual Windows Codex App sessions, new semantic model evaluations and matched AI on/off latency remain not run. Other historical reports remain attached to their recorded versions.

## 0.5.5 maintenance candidate and obsolescence review

Long-record related search used alphabetical term truncation and raw hit counts. That could spend the bounded candidate window on generic/common terms and omit a rare topic marker. It now queries only indexed terms, favors rarer terms and ranks with inverse-frequency weighting. A synthetic long-topic regression fails under the previous selection behavior and passes with the weighted ranking.

Maintenance instructions now explicitly use `REVISE` for a user-confirmed correction and `ARCHIVE` for a contradiction or an explicitly elapsed expiry. Age alone never proves expiry. These records leave default recall while audit history remains; only explicit forget deletes the managed record/history. No new AI call, daemon or unbounded library scan was introduced.

The 0.5.5 maintenance protocol version triggers a one-time requeue of active records in the store being used. The next apply can expose one bounded review pack, including when the current turn is an ordinary checked NOOP. This avoids relying on fresh writes to rediscover an older unrevised backlog; other project stores remain unopened.

Program tests confirm search ranking and correction/archive transitions. They do not establish semantic equivalence quality or automatic maintenance execution across host AI products; no real model evaluation, host E2E or matched latency run was performed for 0.5.5.

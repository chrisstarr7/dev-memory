# Verification report

This report records actual executions. Synthetic data and temporary homes were used throughout. Historical model demos/A-B below predate the 0.2.0 review; no new model runs are claimed for 0.2.0 or the 0.2.1 onboarding update. Results are scoped by the sections below.

## Environment checked

- Python 3.14.2, SQLite 3.50.4, Git 2.47.0.
- Codex CLI 0.155.1 detected; Codex Desktop app bundle was not present at `/Applications/Codex.app`.
- User configuration and project stores were inspected read-only. Real user Skill directories, hooks configuration and memory stores were not changed. This review installed and removed synthetic Skill copies in temporary HOME directories only.

## Results

| Category | Status | Evidence |
| --- | --- | --- |
| Program tests | Passed: 64 tests | `python3 -m unittest discover -s tests -v`; `py_compile` passed. Synthetic temporary stores. |
| S01–S48 | Partially executed; see below | Scenario classifications and concrete unit-test mappings are in `evals/scenarios.json`. |
| Semantic evaluation | Focused synthetic CLI sequence passed; broad semantic set not run | One correction/resume/project-isolation sequence plus the A/B task. These do not establish general language-routing accuracy. |
| Codex hook protocol unit tests | Passed | Synthetic JSON event inputs; does not prove host delivery/trust. |
| Manual Codex CLI multi-session sequence | Passed on the second bounded run | A correction to 14 days, a new CLI session implemented from recalled state and passed 6 tests, then B asked for its own policy while using a confirmed global preference. First run's later stages exited 1; evaluator stderr was not retained then. The successful report records its metrics and exact results. |
| Automatic real-host hook end-to-end | Not run | No hook was installed or trusted; the desktop app version is unavailable. User configuration was not modified. |
| `memory on/off × empty/history` A/B | Completed, 3 trials per cell | Same synthetic task/source, `gpt-6-astra` medium, Codex CLI 0.155.1. Whole-task latency, first visible action, JSONL tool events, token totals, criteria, and generated tests were captured. Historical full results in `reports/benchmark-2026-10-11.json`. |
| License/package | MIT selected by user authorization | Full license included at repository and runtime roots; GitHub publication had not occurred at the original review. |
| Actual skills installer | Passed on local source, six requested Agents | skills@1.7.2; isolated install/reinstall/remove; 78 per-Agent file checks; databases retained; hooks unchanged. reports/install-smoke.json. Remote GitHub URL and actual host invocation were not tested in that review. |
| Skill schema validation | Passed | System skill-creator quick_validate.py, temporary author-only PyYAML 6.0.3 environment; no runtime dependency added. |

## S01–S48 execution status

- The 28 `program` scenarios map to passed tests in `evals/scenarios.json`. S46 is partial: an abrupt subprocess exit rolls back an uncommitted SQLite transaction; disk-full and physical power-loss injection were not run.
- The 10 `mixed` scenarios have their program-checkable portions mapped to tests. Their language judgment portions are marked `semantic_review_not_run` where applicable. S22's actual hook-driven resume was not run.
- The 8 `semantic` scenarios are not a complete scored suite. The A/B and three-stage project demo exercise safe question behavior, correction evidence, resume, and project isolation, but do not cover every S03–S39 semantic variation.
- S40 and S48 require real host trust/event or cross-host E2E. They remain unverified. Hook protocol tests alone do not satisfy them.

## Whole-workflow latency

The same task and code stub were run 3 times for each condition, in seeded shuffled order, with `gpt-6-astra`, reasoning `medium`, Codex CLI `0.155.1`:

| Condition | First visible action median | Full task median (range) | Tool events median | Input + output tokens median | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Off / empty | 12.759 s | 27.483 s (25.103–33.121) | 2 | 56,037 | Asked for missing policy: 3/3 |
| On / empty | 18.400 s | 37.441 s (31.219–58.631) | 4 | 82,159 | Asked for missing policy: 3/3 |
| Off / history | 17.347 s | 31.839 s (29.985–36.737) | 2 | 55,790 | Asked for policy because memory was unavailable: 3/3 |
| On / history | 14.101 s | 69.886 s (63.322–87.832) | 11 | 235,900 | Five code-string constraints matched and independent generated unit tests passed: 3/3 |

Token totals are input plus output; cached input is a subset and is not added twice. Tool events count observable CLI JSONL `item.started` events of selected types, not every hidden model/tool operation. The first-action metric is the first such event, not time to first text. In this task the with-history model implemented code and tests while the no-memory model correctly asked for unspecified policy; their full task durations measure different outcomes. On an empty store, enabling memory increased median end-to-end time by 9.958 seconds (36.2%). These results are a small synthetic sample, not a general latency guarantee.

The project isolation report also includes per-stage time/tool/token measurements and six independently run tests. The first demo run had two CLI-stage failures; a second full run succeeded. An initial checker also missed a task checkpoint because the ordinary list output omits `task_id`; this was corrected to inspect scoped recall.

## Known verification gaps

- Hook trust and event ordering cannot be determined from local config alone.
- Customer-data minimization, scope inference, correction quality, and malicious external instructions require semantic review.
- Disk-full/physical power-loss injection and automatic real-host hook E2E have not been run.
- The worktree signature uses Git status names and file metadata, not a full content hash; it is a cache invalidation aid, not a cryptographic snapshot.
- Benchmark token/tool event data is best-effort; string/code checks need human scoring. The first-action value is a tool-event proxy rather than time to first response text.

## Review execution details

- Program suite: 64 synthetic tests (38 original plus 26 new adversarial regressions). Final run: `python3 -m unittest discover -s work/dev-memory/tests -q`, 64 tests passed in 4.303 seconds. The equivalent repository-root command uses `-s tests`. Python compilation succeeded. The first review run caught a macOS /var symlink-normalization assertion and missing in-progress release documents; fixed before the final green run.
- Actual installation: local repository source with skills@1.7.2, Node v26.0.0. Initial run exposed a mismatch between assumed host-specific paths and this installer's canonical .agents directory; fixed the path expectations. One subsequent npm fetch failed with ERR_SSL_CIPHER_OPERATION_FAILED. Later bounded runs succeeded. No failed run is counted as successful.
- The legacy local Skill validator rejected the optional standard compatibility field; environment requirements were moved to portable string metadata. Validation then passed using temporary author-only PyYAML. Runtime remains standard-library only.
- Prepared GitHub CI for Ubuntu/macOS, Python 3.10/3.14; it had not run at the original review. No Windows or additional real AI host execution is claimed. The optional plugin manifest has no tested marketplace installation.
- Review fixes include application of exclusion/configured limits, lightweight NOOP without a worktree scan, source-type validation, atomic first config creation, same-scope backup purge and restore of old receipt schemas. Check the adversarial report for limits.
- Historical results have explicit version boundaries and the prior release manifest digest; the new benchmark harness copies the full runtime, including required references. It has not been run with a model in this review.

## README and repository presentation update

The project homepage now presents features, installation, usage, architecture, privacy, contribution and licensing. Publisher-only instructions and repository-owner placeholders were removed from the README and installation guide. The public release replaces the publication checklist with `docs/architecture.md`; the installed Skill's file set stays at 13 files.

Checks performed for this documentation/package update:

- 19 local documentation links and README navigation anchors checked successfully.
- Installation `--help` executed successfully. Read-only `doctor` reported available base CLI capabilities, an uninitialized global store and an unbound project; no initialization or hook configuration was performed.
- Release whitelist regression passed in 0.061 seconds. The first invocation used the wrong test module path and did not execute the regression; the corrected repository-root invocation passed.
- Installer preservation regression passed using temporary stores and directories.
- No new full program suite, model benchmark, semantic suite or automatic host E2E run is claimed for this presentation update. Earlier results retain their stated scope and version boundaries.

## GitHub publication verification — 2026-10-11

Published public repository: https://github.com/chrisstarr7/dev-memory. The initial published commit tested below is `c6e7b4df883c093f81cee8bbba096ca6cecae22d`.

- Real GitHub source installation with skills@1.7.2 and Node v24.13.0 passed for Codex, Claude Code, Cursor, Gemini CLI, GitHub Copilot and OpenCode in an isolated temporary HOME/cache. Installation, six read-only doctor calls, reinstallation and removal all succeeded. 78 per-Agent runtime file hashes matched. No memories were initialized by installation; synthetic databases survived reinstallation/removal, and hooks were unchanged. Evidence is `reports/install-smoke.json` under `github_publication_check`.
- [GitHub Actions run 38105343903](https://github.com/chrisstarr7/dev-memory/actions/runs/38105343903) completed successfully. All four Ubuntu/macOS × Python 3.10/3.14 jobs ran 64 tests successfully and built the whitelist archive. Exact commit and matrix are retained in the installation report.
- README and installation guide now use the real repository source. Program files are unchanged by this publication evidence update. Historical review and benchmark statements above retain their original boundaries.
- These checks establish public download/install and program CI. They do not establish automatic host event delivery, additional model A/B measurements or a complete semantic suite. Windows E2E remains unverified.

## Installation UX update — 0.2.1

- README now documents install → new session/project enablement → inspect actual saved records. The primary entry is a copyable AI request; the manual entry is `python3 install.py` with explicit interactive host selection. Optional skills-manager installation is documented separately.
- The installer validates Python/sqlite3 before copying and runs the installed CLI doctor with a 10-second timeout. Human output gives the actual path and next step; --json supports AI/automation. Original --agent options remain supported, with shorter positional aliases added. Noninteractive calls no longer silently select Codex.
- Final local command: `python3 -m unittest discover -s tests -q`, 74 tests passed in the final local run in 7.381 seconds. Python compilation and 23 local links/anchors passed. One intermediate test run failed because the fixture used the wrong global config parent; fixed to use the store path function before the final green run.
- A real PTY menu install was executed on macOS/Python 3.14.2, selecting Codex. The temporary installation passed its actual doctor check, printed the enablement instruction, created no memory or hooks, and was cleaned up. Six direct Python host destinations were also exercised by synthetic subprocess tests. No real user's installation/configuration was changed.
- No new full semantic, real AI onboarding, automatic host-event or model performance run was performed. This version's local installation tests are distinct from the earlier 0.2.0 public GitHub installation and CI evidence. New GitHub CI/download evidence must be tied to its actual commit rather than inferred from the earlier run.

### Public installation and CI for 0.2.1

Tested commit: `60344057ae916fc5128b5080b8af285c1fe6735d`. Evidence: `reports/install-smoke.json` → `onboarding_0_2_1`.

- Simplified skills-manager installation omitted --skill and selected the six agents explicitly in an isolated temporary HOME/cache. Actual GitHub install, six doctor calls, reinstall and remove passed; 78 runtime hashes matched, synthetic memory was preserved, hooks were unchanged. Installer: skills@1.7.2, Node v24.13.0.
- Actual GitHub source ZIP was downloaded and its 36 manifest hashes verified. `python3 install.py claude --json` succeeded from the extracted archive, checking the installed CLI with Python 3.14.2 / SQLite 3.50.4. It initialized no memory and changed no hooks.
- [CI run 38106077305](https://github.com/chrisstarr7/dev-memory/actions/runs/38106077305) passed all four Ubuntu/macOS × Python 3.10/3.14 jobs, each with 74 tests and a successful release build. The download checks and CI apply to the named commit. Later evidence/documentation-only updates do not change runtime or installer code.
- Real AI onboarding/model behavior, automatic hook delivery and Windows E2E remain unverified. No new latency or semantic accuracy claims are made.

## Default project activation — 0.3.0

### Program and package verification

- Final local suite: `python3 -B -m unittest discover -s tests -q`, 91 tests passed. Added project-activation, mixed-scope context and no-task-ID continuation regressions. All data/configuration writes use synthetic temporary homes/projects.
- Python syntax parsing passed. Skill creator validation passed using an isolated author-only PyYAML 6.0.3 environment; no runtime dependency was added. Whitelist release build passed with 41 ZIP entries including the generated manifest.
- `install.py <host> --project <project>` installs, checks the actual installed runtime, initializes independent empty stores and merges host-native instructions. Repeating it preserves data, identities, existing instructions and pause/read-only settings. A guide write failure is reported with actual initialized store results, never as complete activation.
- Six host instruction formats have program coverage. This does not verify actual instruction loading or model behavior in six hosts.

### Real Codex CLI sessions without Skill invocation

Actual host: **Codex CLI 0.155.1**, macOS, Python 3.14.2, SQLite 3.50.4. Model configuration: `gpt-6-astra`, medium reasoning. The host used an isolated temporary HOME/CODEX_HOME, synthetic Git projects and actual login. Existing user instructions/configurations, Skill installations and memories were not changed. The test used `workspace-write` plus `--add-dir` for the synthetic temporary HOME to permit writes to both isolated stores. This does not establish global-store write permission in a user's default sandbox. No hooks were configured or trusted. JSON evidence: [automatic-onboarding.json](automatic-onboarding.json). Reproducible explicit evaluator: `evals/check_automatic.py`.

| Ordinary user request | Observed result | Full invocation | Tool calls |
| --- | --- | ---: | ---: |
| A: correct return eligibility and stop at preparation; separately confirm a cross-project reply preference | Automatically read Skill, recalled empty stores, saved A-only business rule, global preference and task checkpoint | 73.250 s | 12 |
| A, fresh session: continue and implement the function, modifying only its code file | Automatically read Skill, `recall --resume --force` returned checkpoint and rule; six independent eligibility assertions passed; new progress was saved | 61.334 s | 9 |
| B, fresh session: implement its own cancellation rule | Automatically read Skill and recalled the confirmed global preference; project recall was empty, A's return rule stayed absent, B's code and capture checks passed | 41.060 s | 7 |

None of the user prompts named dev-memory, invoked a Skill, or requested saving/recall. Each host ran recall and apply; persisted records and per-scope results were inspected. The resumed host's actual recall output included both `checkpoint` and `business_rule`; B's actual host recall included only the global preference and no project records.

Two earlier attempts are retained as failures/gaps in the evidence summary: first, the evaluator missed writes performed via Python subprocess (the AI actually saved and retried one failed global write); second, the AI recovered the business conditions and implemented code but treated a normal code-file scope as a memory opt-out. The guidance and evaluator were corrected before the final successful sequence. These are not hidden as NOOP or counted as successful runs.

### Actual limits

This establishes observed **project-guided default behavior** in three fresh Codex CLI sessions. It does not establish enforced hook events, every-turn compliance, automatic compaction delivery, Codex Desktop or the five other host integrations. S40/S48's event/trust and cross-host requirements remain unverified. Existing S01–S48 semantic gaps above remain partial; no blanket pass is claimed.

Times and token fields are whole real model invocations, not database microbenchmarks. These three different tasks are **not** a controlled on/off latency comparison. The historical A/B table remains scoped to its earlier runtime; no latency-free claim or new 0.3.0 A/B result is made.

### Public download and CI — 0.3.0

- Commit `08813ed633f3f8463414a0ee0ef8c440299aaef7` was pushed to the public `chrisstarr7/dev-memory` repository. Its actual GitHub source ZIP passed all 40 manifest hashes; `install.py claude --project <synthetic-project> --json` completed runtime checking, independent store initialization and project guide configuration in a temporary HOME, leaving hooks unchanged.
- Actual `skills@1.7.2` installation from this GitHub repository passed for six hosts: 84 runtime file checks, installed doctor calls, reinstall and removal. Databases remained unchanged and hooks were not configured.
- [GitHub Actions 38107607438](https://github.com/chrisstarr7/dev-memory/actions/runs/38107607438) passed all four Ubuntu/macOS × Python 3.10/3.14 jobs, including 91 tests and release building. Exact public-install evidence is in `reports/install-smoke.json` under `onboarding_0_3_0`. Subsequent report-only changes do not imply additional model runs.


## Online installation — 0.3.1

The default README entry now installs directly from GitHub and initializes the current business project in one command. Manual source download and an extra enable prompt are not required. Local source installation and the installed `setup` command remain available for offline use.

- Local program suite: **107 tests passed**, including **16 online bootstrap regressions**, with synthetic snapshots, temporary homes and projects.
- Covered: six host selectors, current-project binding, explicit project/custom target, repeat installation preserving a saved business rule and paused/disabled controls, stable memory identity, unrelated instructions, source cleanup, unavailable Python/sqlite3, offline/timeout failures, invalid arguments, ZIP/manifest/hash attacks, malformed child results, complete and partial receipts, and download/expanded size bounds.
- Skill schema validation passed using author-only PyYAML; no dependency was added to the runtime.
- Public GitHub online execution passed on macOS for all six host selectors, including repeated installation, saved-rule/control/identity/instruction preservation, stable installed bindings, runtime file comparisons and Git exclusion. See `reports/online-installation.json` (tested commit `4380cbdcd6c85922872f33ef8be90896d65c5105`). One initial TLS-handshake transport failure was returned as failure; a bounded rerun completed.
- [CI run 38108587855](https://github.com/chrisstarr7/dev-memory/actions/runs/38108587855) passed Ubuntu/macOS × Python 3.10/3.14, 107 tests and a 42-file release build in each job.

These are installation/program checks. No new model session or full latency A/B was run for 0.3.1; the observed 0.3.0 Codex CLI session results are historical evidence. Windows and actual automatic behavior on other hosts remain unverified.


## Short GitHub npx entry — 0.3.2

- Local program suite: **114 tests passed**, including seven Node-launcher/packaging tests and the existing Python online checks. Node.js 26.0.0 / npm 11.12.1 were used locally; the CI config now selects Node.js 22.
- Checked: all six host selectors, current/original project binding, explicit project/custom directory, idempotent setup preserving paused controls, unavailable Python, invalid/conflicting/omitted noninteractive host, source failures and unchanged exit codes, no Node dependencies/lifecycle scripts, and an exact npm pack whitelist excluding injected synthetic SQLite/private files.
- The default command is `npx -y chrisstarr7/dev-memory codex`; the Python-only online command remains in the installation guide. The memory runtime does not require Node or run npm.
- Actual public GitHub shorthand execution passed on macOS for all six host selectors, with fresh/repeated install, runtime whitelist byte comparisons, saved-rule/control/identity/instruction preservation, stable bindings and no npm files in business projects. See `reports/npx-installation.json`, tested commit `f59509bd78e31c5c2a4a990a50de55597443c919`. Temporary HOME/npm cache were used; system/global Git configuration was disabled and no login prompt was permitted.
- [CI run 38121192754](https://github.com/chrisstarr7/dev-memory/actions/runs/38121192754) passed Ubuntu/macOS × Python 3.10/3.14 with Node.js 22, 114 tests and release builds in each job.
- Same-cache upgrade passed: the same short command and npm cache refreshed a changed runtime from a new public commit even with package version 0.3.2 unchanged, preserving paused controls and project namespace. See `reports/npx-upgrade.json`, tested commit `2ee09212327094942491ec33a37bdefc8c275a3b`. Installation elapsed times in the npx report include transport and do not measure AI workflow latency.

Windows CLI selection is implemented (`py -3`, then Python fallbacks), but no Windows installation or host session was executed. This packaging change adds no new model-session or workflow-latency evidence.


## Automatic duplicate prevention and maintenance — 0.4.0

### Program checks

Local final suite: **145 tests passed** on macOS, Python 3.14.2 / SQLite 3.50.4, using isolated synthetic stores. This adds 28 store/maintenance regressions and three evaluator regressions to the prior 114 tests. Covered exact/title/whitespace deduplication, case-sensitive business values, semantic reuse without body writes, source replay, task separation, bounded match/queue, long-record trigger, optimistic revision guards, compact/merge provenance, derived invalidation, late source conflicts, alias cycles, global leak guards, pause/read-only/opt-out, forgetting connected sources, old-backup restore and suppressed resurrection. Evaluator tests reject source-keyword false positives and separate failed-host timing from completed tasks.

The program does not prove natural-language equivalence or lossless AI compaction. It enforces same-scope structured conditions, exceptions, prohibitions, truth and version fields; AI must also preserve restrictions embedded only in prose. Revisions/original evidence remain inspectable. No automatic total disk limit or history expiration was implemented.

### Actual host and semantic evidence

[maintenance-host.json](maintenance-host.json), generated by `evals/check_maintenance.py`: **Codex CLI 0.155.1**, `gpt-6-astra`, medium reasoning, macOS. Two isolated ordinary-prompt sessions; no Skill invocation, maintenance request or hooks. Three equivalent historical rules and one distinct long rule were seeded only in synthetic project A; B/global stayed empty.

| Session | Observed successful behavior | Whole invocation | Tool events |
| --- | --- | ---: | ---: |
| Ordinary preparation task | Merged historical duplicates, compacted a distinct long rule, preserved original evidence and all structured fields | 92.459 s | 16 |
| Fresh-session paraphrase | Reused the saved conditions; no additional business rule was created | 62.230 s | 9 |

The distinct rule's prose-only `ReturnPolicyV2`, `manual_review`, `supervisor_override=true` and “unless” exception survived compaction and were correctly explained in the model answer. Actual receipts and persisted records were checked; merely reading source keywords is not counted as maintenance. The business code remained unchanged as requested. This sampled semantic review passed; it is not exhaustive equivalence proof or every-turn enforcement. These sessions predate final `record_scope` guidance; that guidance has program coverage, not a fresh model run. Desktop, Windows, other hosts and trusted hook delivery remain unverified.

### Whole-workflow on/off comparison

[maintenance-benchmark.json](maintenance-benchmark.json), `evals/bench_compare.py --scenario automatic-maintenance`: same complete policy/task and starting business code, `gpt-6-astra`, medium reasoning, Codex CLI 0.155.1; shuffled three attempts per condition. Input/output tokens are summed once; cached input is a subset. Off/history has no installed Skill or accessible seeded memory and is the same no-access baseline as off/empty; on/history seeds three related synthetic rules. This evaluates bookkeeping overhead when current user instructions already contain all business constraints.

**12 attempts, 8 completed, 4 nonzero host exits.** Two exits explicitly reported account usage limits; two causes were not captured. They remain in the JSON, have unavailable tokens/unknown correctness, and are not fast successful tasks. Further model calls stopped at the quota boundary. Three *completed* trials per cell were not achieved, so this is a partial comparison. Negative program guards were added during the run and record-scope guidance afterward; it is a prepublication feature sample, not a frozen final-source benchmark.

The following medians/ranges use completed invocations only:

| Condition | Completed / attempted | First tool action proxy, median (range) | Whole task, median (range) | Tool events, median | Input + output tokens, median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Off / empty | 1 / 3 | 19.915 s (single) | 52.415 s (single) | 5 | 74,932 |
| Off / history inaccessible | 3 / 3 | 17.699 s (15.678–21.817) | 53.236 s (48.722–57.835) | 5 | 74,890 |
| On / empty | 2 / 3 | 17.401 s (17.170–17.631) | 85.929 s (83.262–88.595) | 13 | 183,414 |
| On / history | 2 / 3 | 19.579 s (19.543–19.615) | 88.830 s (87.480–90.180) | 13.5 | 178,347 |

All **8 completed** tasks implemented the policy, passed six independent behavior cases and their generated test suites. No tested condition was missing in those completed tasks; the four incomplete calls remain unknown. A first-tool timestamp is **not measured time to first business code edit**. Token observations are best effort. One on/empty host saved its checkpoint but reported a scope-mismatched maintenance review; the review remained pending. The final pack now explicitly supplies `record_scope`/task ID to reduce this mistake, with regression coverage; its model behavior was not rerun.

**Memory adds material overhead in this sample.** Completed on tasks took about 86–89 seconds versus 52–53 seconds off, with more calls and tokens. No claim of invisible overhead, zero latency or improved accuracy is made. The partial comparison and unchanged historical S01–S48 gaps must not be presented as full acceptance.

### Public release evidence

Tested commit: `bfe40cd9f516a0f52e33eec5df9f4c3cbb735f52`. Evidence: [maintenance-installation.json](maintenance-installation.json).

- Actual `npx -y chrisstarr7/dev-memory <host>` passed fresh and repeated installation for all six host selectors on macOS, with isolated HOME/cache and no real user-store changes. Fourteen installed runtime files matched public source; new stores were empty, repeated installation preserved synthetic records, identities, controls and unrelated instructions. No hooks or npm project files were added.
- Actual public upgrade from pinned 0.3.2 to current 0.4.0 via the short command passed. Body/conditions/evidence/revision and namespace were retained; paused capture remained paused, old active history was queued once and paused maintenance was suppressed. The same temporary cache was reused; the initial old installation used a pinned commit rather than an unmodified main shorthand.
- Downloaded public GitHub source ZIP passed all 51 manifest hashes. [GitHub Actions 38127667281](https://github.com/chrisstarr7/dev-memory/actions/runs/38127667281) passed all four Ubuntu/macOS × Python 3.10/3.14 jobs, each with 145 tests and a 52-entry release build using Node.js 22.
- Later additions of this evidence/report to the release whitelist do not add model or installation runs. Windows installation, other-host automatic behavior and the final scope-guidance model rerun remain unverified. Earlier release results remain scoped to their named commits.

## Lifecycle review and lightweight startup — 0.5.0

Full findings: [lifecycle-review.md](lifecycle-review.md). Machine-readable observations: [lifecycle-host.json](lifecycle-host.json); unmatched new workflow comparison status: [lifecycle-benchmark.json](lifecycle-benchmark.json).

### Program evidence

The full local suite passed **157 tests** in 22.838 seconds. The lifecycle regressions cover same-second checkpoint replacement and summary invalidation, global/project recall capacity, candidate overflow, unknown workspace invalidation, SQL interruption, bounded current batch lookup, normal startup without host probes, read-only cache behavior, actual CLI parsing and a seven-phase synthetic memory sequence with an A-to-B scope check. The scale probe ran ten repetitions at 1,000 and 10,000 active synthetic records. At 10,000, narrow recall median was 21.991 ms, saturated recall 41.364 ms and maintenance preparation 74.667 ms; saturated recall stayed incomplete and maintenance stayed bounded. These are local program measurements.

### Real-host and semantic evidence

Codex CLI 0.155.1, `gpt-6-astra`, medium reasoning; eight invocations with seven completed and one explicit workspace-credit rejection. The same fourteen runtime hashes were retained in all attempts. Two project-A cycles completed requirements, SQLite/API design, the 30-to-14-day correction, backend/frontend implementation, actual HTTP integration, testing and injected-boundary bug fixing. Independent behavior checks passed before injection and after repair. Record revisions preserved the correction and same-task checkpoint retirement was observed.

The first evaluator incorrectly treated an explicitly superseded 30-day annotation as current permission; the second required an optional verification object even though successful tool-result observations were saved. Those failed assessments remain in the JSON. They do not constitute a complete evaluator pass. A third run with corrected predicates stopped on `Your workspace is out of credits. Add credits to continue.` No further model calls or credit purchase was attempted. **New project-B host behavior and the corrected complete four-session pass remain unverified.**

Plain observations record historical test outcomes; absent structured time/version fields are not inferred as currently verified workspace status. Actual tool outputs were reviewed independently of the AI's final message. Finite synthetic checks do not prove complete semantic correctness or enforced execution on every turn.

### Whole-workflow timing boundary

The new matched on/off comparison was **not run** after the host credit rejection. Its harness now freezes runtime hashes, seeds identical history in both modes and separately observes first business edit, but these changes are not timing results. The latest actual comparison remains the 0.4.0 partial sample above: on tasks took about 86–89 seconds versus 52–53 seconds off. No claim of no material slowdown or measured whole-task improvement is made for 0.5.0. Earlier Windows, cross-host, hook-event and S01–S48 gaps are unchanged.

### Public installation and CI — 0.5.0

Tested feature commit: `070bdda6821d48f103a9c05de5372aa91b594a9c`. Sanitized results are in [lifecycle-host.json](lifecycle-host.json), under `public_distribution`.

- Actual public `npx -y chrisstarr7/dev-memory <host>` passed fresh and repeat installation for all six selectors on macOS in temporary HOME/cache/projects. Fourteen installed runtime files matched source. New global/project stores were empty; repeated installation retained synthetic records, store identities, capture/recall controls and unrelated project instructions. No hooks or npm files were added to the business project. This verifies distribution/configuration, not automatic model behavior on every host.
- Pinned 0.4.0 to public 0.5.0 upgrade passed using the same temporary cache. Bodies, conditions, exceptions, evidence, revisions, namespace, paused capture and unrelated instructions survived; pending work remained queued once and paused maintenance stayed suppressed.
- Downloaded public source ZIP passed all 57 manifest hashes using TLS-verified curl. The first Python download failed because its local certificate issuer was unavailable; no insecure TLS bypass was used.
- [GitHub Actions 38139487751](https://github.com/chrisstarr7/dev-memory/actions/runs/38139487751) passed all four Ubuntu/macOS × Python 3.10/3.14 jobs with Node.js 22: each ran 157 tests and built a 58-entry release archive.
- These isolated checks changed no real user memories or installed AI configuration. Windows transport and new model timing remain unverified.

## DeepSeek Harness target — 0.5.1

`npx -y chrisstarr7/dev-memory deepseek` now installs and initializes a native DSH target. `dsh` and `deepseek-harness` are aliases. Program location follows `DSH_HOME` (default `~/.dsh/skills/dev-memory/`); explicit `--target` wins. Project `AGENTS.md` and the private `deepseek-harness` activation binding connect the existing engine to DSH. Model/API settings, permissions and profiles are not modified.

The complete local suite passed **160 tests**. Added coverage checks DSH aliases, custom home, explicit target, repeat-install pause preservation and unsafe data-path rejection. Existing all-target install, setup, npx and synthetic online tests include DSH; the pinned external-manager smoke remains limited to its original six targets.

The published **`@deepseek-ai/dsh-skill-filesystem@0.2.0-rc.2`** provider was directly exercised in an isolated temporary home: it discovered `dev-memory` from `user-dsh`, parsed the actual YAML, marked it model-invocable and loaded its full 0.5.1 body. Watchers were disabled; no model call occurred. This was a component probe with a minimal context and native Node filesystem fallback, not a full DSH profile or model session. The first probe's evaluation context omitted `ctx.get`; after correcting the evaluation harness, the probe passed. Source inspection separately covered the published instruction component and pinned upstream sources.

Optional reproducible probe (downloads test-only npm dependencies in a temporary directory, no runtime dependency added): `python3 evals/check_deepseek.py --output /temporary-directory/deepseek-probe.json`. Results must be outside the source package. Machine-readable status: [deepseek.json](deepseek.json).

Actual DSH model end-to-end behavior and workflow latency remain **not run**. Custom profiles can disable providers, omit/truncate project instructions or deny commands; installation cannot override these controls. Earlier model/benchmark evidence remains scoped to its named release and host.

### Public distribution checks — 0.5.1

Feature commit `fb4740f5dd81f0a8212aaa7f0f54d9b3a5a73ee4`: actual public short-command installation and repeat installation passed for **all seven selectors**, including `deepseek`, in temporary homes/projects on macOS. Installed runtime bytes matched all fourteen public files. DSH's empty initial store, synthetic record retention, namespace, capture/recall controls, unrelated `AGENTS.md` instructions and stable runtime binding survived repeated installation. No npm project files or default hooks were added. This is distribution/program evidence, not a DeepSeek model session.

An actual pinned 0.5.0 → 0.5.1 Codex upgrade retained body, conditions, exceptions, evidence, revisions, namespace, paused capture and unrelated project instructions using the same temporary npm cache. All 62 manifest hashes in the public source ZIP passed. [GitHub Actions 38144087727](https://github.com/chrisstarr7/dev-memory/actions/runs/38144087727) passed four Ubuntu/macOS × Python 3.10/3.14 jobs, each with 160 tests and a 63-entry release build using Node.js 22. Machine-readable outcomes are in [deepseek.json](deepseek.json). No real user store/configuration or API credential was changed.

## Windows public-program ACL repair — 0.5.2

The public Skill directory and nested program directories formerly used `0700`. Python maps this mode on Windows to a current-user/admin-only ACL, which can block another authorized sandbox identity. This is a confirmed installer defect and a plausible explanation of the reported Codex desktop App denial; the specific user's denied path, error and version were not supplied.

The fix inherits the program parent's ACL on Windows, recreating managed directories on upgrade. Private memory ACL policy and POSIX modes remain unchanged; no administrator elevation, blanket ACL grant/reset, sandbox bypass or memory relocation is performed. An installation receipt explicitly distinguishes the program policy from unverified sandbox access. A custom ordinary program directory remains supported when the default parent cannot be accessed.

The local suite passed 162 tests with one native Windows test skipped. The native regression gives a synthetic read principal access on one temporary parent, reproduces the old private program ACL, upgrades the actual runtime, checks inherited read/execute on program directories/files and checks that private memory remains restricted. Windows CI and actual Codex desktop App status are recorded separately in [windows-access.json](windows-access.json). Windows CI was added to both Python 3.10 and 3.14 jobs; CI does not invoke models or alter real user configuration.

### First native Windows run and portability fixes

[First Windows CI attempt](https://github.com/chrisstarr7/dev-memory/actions/runs/38263958384): four Ubuntu/macOS jobs passed; both Windows jobs failed. Failures exposed Unicode pipe encoding and fixture decoding assumptions, plus a native ACL post-upgrade assertion. The installer/CLI now configure UTF-8 streams at executable entry points, installer JSON is codec-safe, and child receipts are decoded explicitly as UTF-8. Text fixtures use UTF-8; native command-lookup, malformed ZIP-name and POSIX-only Bash fixtures were corrected for Windows without removing equivalent native online-install coverage. A cp1252 pipe regression now checks the actual Unicode project binding.

The updated local suite passed 163 tests, with the native Windows ACL check skipped on macOS. The ACL test now reports numeric SID/rule diagnostics and checks effective allowed read/execute bits rather than assuming inheritance flags survive directory renames. This is a diagnostic refinement, not a passing native result; the Windows retry is pending. No actual Windows desktop App session is claimed.

### Second native run

[Second run](https://github.com/chrisstarr7/dev-memory/actions/runs/38265555280) cleared the Unicode installation/runtime failures; both Windows jobs retained two failures (163 tests, one POSIX-only skip). The ACL reader returned null/empty data even for its parent, so it did not establish an ACL result. It now calls native .NET ACL APIs with fail-fast error handling. Windows zipfile normalization exposed a real validation gap: normalized names are now rejected when they differ from `orig_filename`, preserving the malformed-path check on every OS. The updated local run passed 163 tests with the native ACL check skipped. A new native run is required; the desktop App remains unverified.

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
- Final local command: `python3 -m unittest discover -s tests -q`, 74 tests passed in 7.322 seconds; the final presentation-only adjustment was checked again before publication. Python compilation and 23 local links/anchors passed. One intermediate test run failed because the fixture used the wrong global config parent; fixed to use the store path function before the final green run.
- A real PTY menu install was executed on macOS/Python 3.14.2, selecting Codex. The temporary installation passed its actual doctor check, printed the enablement instruction, created no memory or hooks, and was cleaned up. Six direct Python host destinations were also exercised by synthetic subprocess tests. No real user's installation/configuration was changed.
- No new full semantic, real AI onboarding, automatic host-event or model performance run was performed. This version's local installation tests are distinct from the earlier 0.2.0 public GitHub installation and CI evidence. New GitHub CI/download evidence must be tied to its actual commit rather than inferred from the earlier run.

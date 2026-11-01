# Host delivery acceptance

This report covers the instruction-driven Dev Memory integration, recall budget reuse, Dashboard preview diagnostics and natural-language correction acceptance. Program tests, real model behavior and optional hook execution are separate claims.

## Tested environment

- macOS 15.1.1, Apple Silicon; managed Python 3.12.16 / SQLite 3.53.1.
- Codex CLI 0.163.0, model `gpt-6.1-sol`, reasoning `high`.
- Hooks unconfigured, source-only temporary stores, no vector/model installation.
- Chrome 156.0.8078.79 for native Dashboard form interaction.

## Real lifecycle acceptance

The evaluator uses actual app-server `thread/start`, a new app-server process with `thread/resume`, and `thread/compact/start`. It does not simulate lifecycle messages or feed a memory body through the test prompt.

Before each phase the controller puts a fresh unpredictable marker into the same project rule and resets the generated module. The new marker was never part of the preceding conversation. Successful `context --force` output must contain both the global memory and the current project revision. The controller then executes the generated `write_receipt(text)` itself and checks exact UTF-8 bytes, including the marker, separator and final newline.

| Phase | Required evidence | Result |
| --- | --- | --- |
| Startup | Global body, project revision 1, exact independently generated artifact | Passed |
| Restart and resume | Actual same-thread resume, project revision 2, new marker in artifact | Passed |
| Compaction | Actual completed `contextCompaction`, project revision 3, new marker in artifact | Passed |

An early complete run passed, but the next independent run exposed a real resume failure: the model said it would reuse loaded memory, did not call `context`, and generated the old marker. The acceptance rejected both missing body delivery and the wrong artifact. This was a behavior failure, not a SQLite/vector outage or a reason to retry unchanged code until green.

The trigger list previously named task/topic changes while a later sentence only specified which flag to use after resume. That left a conflict with same-task reuse. Project guidance, user guidance and the Skill now make resume/compaction explicit fresh-recall boundaries, even when the task and visible old bodies are unchanged. Reuse is limited to uninterrupted context; unexpected workspace differences require one relevant refresh before edits.

The first complete run after this correction passed in 34.725 / 30.504 / 25.896 seconds for startup/resume/post-compaction model turns. A separately initialized full lifecycle run checks the same final runtime again before release; hashes and all failure logs are retained outside the repository. These are correctness samples, not a performance benchmark or statistical reliability rate.

The project guide was then shortened to 1797 characters to retain its existing size limit without relaxing a test. The exact final runtime passed again in 41.769 / 25.884 / 21.432 seconds. The acceptance checks delivery before final output, not that the first tool must be recall: in one resume phase the model first discovered the reset module, then refreshed memory before implementing the new rule.

The fix stays in the existing instruction-driven path. No extra runtime adapter, background process, per-prompt lookup or model call is introduced. Optional hooks still require their own explicit configuration and trust; these runs do not establish trusted-hook execution. Other AI hosts are not covered by these real model checks.

## Recall, Dashboard and correction checks

- Default combined recall keeps 5 details / 4000 body characters. Unused global capacity reaches the project while per-store limits and stable cache allocation remain effective. A 1-global / 6-project fixture returns 1 + 4 bodies.
- Dashboard default preview uses the same fresh-call budget. Explicit expansion is labelled and still respects store limits. Native Chrome forms exercised required validation, Chinese query submission, default and expanded modes, and retained query values. Read-only database snapshots remained unchanged.
- Candidate overflow is distinguished from detail/character omissions; a shared-list alias that incorrectly raised the candidate-limit flag was fixed with a regression assertion.
- Three independent correction conversations covered a synonym lookup miss followed by one query reformulation, materially ambiguous targets, and a one-turn exception. The correction retained the same project candidate, evidence/history, unaffected exceptions and correctness requirements. Ambiguity and temporary exceptions did not change stored rules. Primary-assistant source-by-source review passed.
- Real local multilingual vector integration reused the existing runtime. Model/index failure remains a bounded fallback to raw/keyword memory; it does not turn a missing vector into a missing original record.

## Installer follow-up

An isolated execution of the real GitHub `npx` entry exposed a delivery gap: `update codex` updated the installed program and user guide but omitted the current project argument, leaving its managed guide stale. The launcher now supplies the current directory for update as well as installation; the Python updater still refreshes only an existing matching binding and does not initialize unbound directories. A regression checks refreshed managed guidance, preserved team text and unchanged control switches.

Windows CI also caught a platform-dependent fixture in the new artifact acceptance test: text output translated LF to CRLF. The synthetic implementation now writes explicit UTF-8 bytes, and an explicit CRLF case must fail. The acceptance still requires exact LF bytes; no production check or platform is skipped.

## Reproduce

From the source repository, with an existing authorized Codex login:

```text
python3 evals/check_host_delivery.py --model EXACT_MODEL --reasoning high --output /absolute/path/outside-repository/host.json
python3 evals/check_one_sentence.py --model EXACT_MODEL --reasoning high --output /absolute/path/outside-repository/correction.json
python3 -m unittest discover -s tests -v
```

The real-host commands are explicit opt-in checks and spend model quota. They create temporary homes/projects, keep reports outside the repository and remove temporary credentials, sessions and stores on exit. Do not publish raw reports without reviewing their contents. The unit suite does not launch these model calls.

## Limits

- Results cover the named local Codex/model sample; they do not enforce correct behavior in every future turn or establish a semantic accuracy percentage.
- Claude Code, OpenCode and other hosts have instruction/configuration coverage, not real model lifecycle acceptance in this report. Installation is not proof of body delivery or adoption.
- Existing global/project privacy switches, candidate status, revision checks and vector eligibility remain authoritative. The acceptance tooling does not bypass hook trust or weaken production sandbox/CSP controls.
- The controller initially used the newer documentation's sandbox spelling; the installed 0.163.0 schema required `workspace-write`. This was corrected before the first complete model lifecycle run. The later real resume failure was retained and addressed in guidance before additional acceptance; no production timeout was increased.

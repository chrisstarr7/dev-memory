# Memory quality baseline and selective event review

## Contract

The development order is evaluation baseline, selective capture review, then optional progressive retrieval. Ordinary Skill work remains bounded and local. No transcript collector, extra summarization model, service or automatic hook trust is added.

`evals/check_memory_quality.py` runs the same synthetic coding tasks with and without memory. Three default scenarios cover durable project knowledge, a current instruction overriding an old global preference, and a conditional rule with an exception. Each runs twice with reversed pair order on the second repetition. The off condition installs neither Skill nor stores; deleting only project guidance was found insufficient because the real host auto-discovers user Skills. That invalid fixture was stopped and its evidence retained outside the repository.

## Metrics and interpretation

| Metric | Observable evidence | Missing/failure treatment |
| --- | --- | --- |
| Correct recall | Required current IDs actually returned as successful context/show bodies | Indexes, claims and failed commands do not count; failed host attempts remain in the denominator |
| Rule execution | Independently call the generated function on Chinese input, with both condition values | Missing implementation, wrong output and errors fail the task |
| Wrong adoption | Generated output contains the forbidden obsolete/cross-project prefix | Missing artifacts are reported separately, never as a correct rejection |
| Token delta | Paired actual input plus output usage, with cached input reported separately | Unavailable usage is unknown; no character-to-token estimate or double-counted cache |
| Task time | Full invocation time and paired delta; repeated sample median/p95 | Host failures/timeouts retained; a failed task is not a fast successful task |

This is a small synthetic regression baseline, not a population accuracy, causal attribution or broad latency claim. Hidden project conventions are deliberately unavailable to the off condition. Cold/warm caches, provider capacity and host instructions can influence whole-task tokens and latency. General performance claims still require the larger randomized benchmark described in the installed verification reference.

## Selective events

Only optional, normally trusted `UserPromptSubmit` hooks with stable session/turn IDs produce high-value capture-review hints. Direct corrections, durable requirements and user verification claims are routed conservatively. Examples, code/quotes, temporary requests, oversized messages and missing IDs fall back to normal Skill assessment. Privacy suppression takes precedence.

The event carries a short routing hint, not the user's prompt, a saved record or proof of a tool result. The primary AI checks scope, source, duplicates, revisions and privacy/capture controls before writing through the existing protocol. No event is allowed to promote a user's verification claim to tool evidence.

Actual local Codex CLI 0.163.0 TUI testing used a temporary HOME/project and the normal `/hooks` review interface to inspect and trust exactly the two owned definitions. No bypass flag or direct trust-file write was used. Native host messages were marked `hooks.additional_context`. A durable requirement produced one project record; a correction revised that same record to revision 2 and retained history. A private-turn marker was absent from both databases and had suppression receipts. Pausing project capture prevented another revision and did not create a global fallback. Temporary trust/auth/session files are removed after the test; production user hooks are not enabled or trusted by this work. This named-host sample does not establish every future capture or other hosts.

## Progressive retrieval

Default `full` remains compatible. Optional `auto` removes only empty fields from short bodies; it does not summarize away any substantive constraint. Bodies over 1000 serialized characters are returned as navigation previews, with current identity/revision and explicit full-read requirements. `index` returns navigation only. Before applying a preview, fetch required IDs with the existing scoped batch `show --current` path. Its existing privacy/status/currentness checks remain in force. No fixed three-call sequence is required.

Preview-only reads do not increment full-body recall counts, and cache keys include disclosure mode. Full-body/detail budgets and global/project isolation still apply. Tests cover long exceptions, unchanged complete bodies, disabled stores, cache isolation and unchanged counters. The 1000-character split is an explicit optional heuristic, not a token measurement or an automatically chosen performance optimum.

## Reproduction

From the source repository with an existing authorized Codex login:

```sh
python3 evals/check_memory_quality.py --model EXACT_MODEL --reasoning high --output /absolute/outside-repo/current.json
python3 evals/check_memory_quality.py --model EXACT_MODEL --reasoning high --runtime-ref BASELINE_COMMIT --output /absolute/outside-repo/baseline.json
python3 evals/check_memory_quality.py --model EXACT_MODEL --reasoning high --disclosure auto --cases long --output /absolute/outside-repo/long.json
python3 -m unittest discover -s tests -v
```

Real-model commands are explicit opt-in and consume quota. They use frozen runtime copies and synthetic temporary homes/stores, preserve unavailable usage and provider errors, and remove temporary credentials/projects. Raw logs stay outside the repository. Source hashes, full failure evidence, semantic review and measured results are retained with local release artifacts. Validation results are recorded after final verification; no stable speedup is claimed by this change.

## Measured local evidence

Environment: macOS 15.1.1 arm64; managed Python 3.12.16 / SQLite 3.53.1; Codex CLI 0.163.0, gpt-6.1-sol, high reasoning. Baseline runtime is main commit 9acb821ac2d611c782b35f4c4c2a5ba5437056e3. Each phase freezes its own 18 Skill-file hashes.

| Paired cohort | Current bodies / expected | Rule artifacts | Forbidden output | Host errors / missing usage | Off artifacts |
| --- | --- | --- | --- | --- | --- |
| Prior runtime, 12 attempts | 5/6 | 5/6 | 0/5 readable | 1 / 1 | 2/6 |
| Optional auto path, 12 attempts | 6/6 | 6/6 | 0/6 readable | 0 / 0 | 2/6 |

The one prior-runtime failure was an explicit provider response, “Selected model is at capacity”; all five completed on-tasks passed. It was retained and not retried or attributed to a storage defect. The table therefore does not establish an improvement from 83% to 100% model reliability. Strict CLI-invocation rechecking of all successful body receipts also passed; echo/text claims do not count.

For the optional-auto cohort, median paired input-plus-output increment was **26,163.5 tokens**, including cache-accounted input; median whole-task increment was **10.719 seconds**. These are actual task usage, not extra tool-output tokens alone. The control group lacked required project knowledge and often asked for clarification instead of producing the artifact, so cost comparisons are not equal-success throughput comparisons. These samples support keeping progressive disclosure optional and full bodies as the default; they do not support a speedup claim.

After the full cohort, only redundant preview guidance on short/no-preview responses was removed, along with malformed-argument validation. The final frozen runtime is separately accepted on short bodies and a long rule with its exception beyond the preview. Source hashes distinguish these runs; do not relabel the earlier cohort as byte-identical final-source evidence. All final unit/vector/release checks use the final source.

Final-source targeted acceptance: 4 additional paired attempts (short and long), with 2/2 on-tasks delivering the required body and passing both independent condition checks; 0/2 readable artifacts adopted forbidden output, no host failures or missing usage. The long case first returned zero bodies plus a navigation preview, then a successful explicit `show --current` returned the full body; the late exception was correctly implemented. All 18 frozen runtime digests match the final source. The named-host event test also checks the exact final hook digest. Real vector integration reused the existing environment and passed all 3 tests under production index/query budgets.

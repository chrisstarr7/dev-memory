# Inspection-only capture review — 0.8.8

## Observed omission versus supported cause

A user reported an explicit project convention missing after an assistant inspected already-compliant request/response models. The matching local host trace contains one code-reading tool invocation after that instruction and no memory write attempt. This supports an omitted capture action, rather than a failed SQLite write in that turn. It does not reveal the model's internal decision, establish which instructions it used, or prove that the absence of code edits caused the omission. Private transcripts, real model names and business code are not included here.

The 0.8.7 Skill already permits first-discovery project conventions, and the store has no edit/diff prerequisite. Its opening capture reminder emphasized requirements/corrections/choices; the generated project guide did not explicitly name inspection/no-change outcomes; the optional startup hook narrowed the reminder to user feedback. These are evidenced guidance weaknesses, not a claim that the previous rule prohibited saving.

## Isolated native-assistant exercises

All cases use separate synthetic SQLite stores and already-annotated `AssetQueryDTO.java`/`AssetItemVO.java` files. No Java build, server or test is required. Original bytes were checked against the fixture's initial contents, including Windows line endings. No real project rule is backfilled by these exercises.

| Case | Observed result |
| --- | --- |
| Frozen 0.8.7 guidance, explicit project convention | Saved one active, desired project convention from user evidence, without changing Java. Also created an unnecessary global style candidate by generalizing the same scoped requirement. The original missing write did not reproduce. |
| Patched guidance, same user instruction | Saved one active, desired project convention from user evidence; no global record; Java unchanged. |
| Patched guidance, one-time annotation inspection | No project/global record; Java unchanged. |
| Patched guidance, explicit turn memory opt-out | Both scopes returned private-skip receipts; no memory body saved; Java unchanged. |
| Patched guidance, quoted prompt for explanation only | No project/global record or source edit; the quotation was not adopted as a rule. |
| Fresh independent assistant, new DTO/VO task without naming Swagger | Retrieved the actual saved rule ID and applied its annotation/style requirements, inspecting the two local examples as needed. No duplicate record or apply call; the project still contains exactly one rule. |

The baseline used one independent assistant; the four patched cases used one other assistant with distinct project/global stores; fresh recall used a third assistant without earlier discussion. These are exploratory behavioral checks, not a repeated randomized A/B or a statistical reliability claim. They use host-native subagents, not an updated external Codex CLI lifecycle run. Frozen patched guidance differs from the final release only in subsequent version metadata. Raw synthetic outcomes remain outside the source checkout.

## Narrow changes

- Assess capture on inspection, explanation, review and already-compliant/no-code-change turns, independently of edits, tests and diff outcomes.
- Retain a newly stated durable convention even when current code already complies. Attribute desired behavior to the user; inspected implementation is observed evidence, not authority for a desired rule.
- Resolve an eligible increment before delivery with a checked save, an already represented equivalent, or a truthful blocked/failure report. No eligible increment still means no write, NOOP, extra classifier or receipt gate.
- Preserve project/module scope. Do not strip that scope to manufacture another global preference from the same convention; distinct supported reusable choices and explicit cross-project instructions remain eligible under existing rules.
- Preserve temporary-request exclusions, quoted/example boundaries, capture modes, pause/disable/read-only/opt-out and all-state-write bans. A business-code edit limit alone does not revoke previously configured memory bookkeeping.
- Align generated project guidance and the optional startup reminder. Do not add hooks, per-prompt processes, automatic database writes, task checkpoints, repeated recall or background classifiers.

## Verification and limits

Local affected suites: 7 evaluator tests, 22 setup tests, 13 capture tests and 25 efficiency tests passed. Controls distinguish observed facts from desired user conventions, inactive/global-only records from project success, Java edits/checkpoints, paused/private writes, actual recall IDs, read-only inspection, and failed CLI exit status. These program tests submit synthetic records explicitly; they do not prove that a model autonomously captures them. The native-assistant results above provide separate behavioral evidence.

`evals/check_noedit_capture.py` creates a separate compliant fixture or reads existing fixture results; it never invokes `apply`. Its topic/provenance matcher is a heuristic: semantic scope/meaning must also be reviewed. The inspector exits nonzero when its positive acceptance checks fail. Negative scenarios intentionally require no saved rule and are evaluated against that expectation rather than falsely counted as positive capture success.

```text
python -B evals/check_noedit_capture.py /outside/source/fixture --create
# Have a host follow fixture/project/AGENTS.md and perform the returned prompt.
python -B evals/check_noedit_capture.py /outside/source/fixture --output /outside/source/outcome.json
python -B -m unittest discover -s tests -p test_noedit_capture_eval.py -v
```

Host loading and model compliance remain necessary. This change strengthens the decision guidance and covers the missing scenario; it does not guarantee a write on every future eligible turn or override privacy controls.

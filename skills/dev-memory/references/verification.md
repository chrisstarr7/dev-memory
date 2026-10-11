# Verification and evaluation limits

## Test categories

- **Program tests** can verify routing, transactions, scope isolation, validation, exact receipt states, bounded SQL results, data deletion and filesystem behavior using synthetic temporary stores.
- **Semantic evaluation** asks whether an AI correctly inferred scope, retained conditions/negative constraints, avoided forbidden data, and resumed the right task. Program unit tests cannot prove these natural-language judgments. The source repository contains `evals/scenarios.json` for S01–S48; the installed runtime does not bundle evals.
- **Host end-to-end** requires a trusted, configured hook and actual Codex sessions on a named version. Hook protocol unit tests are not host E2E.
- **Latency comparison** must measure whole model tasks. SQLite timings alone are not workflow latency. Compare the same code snapshot, task, model and reasoning setting over repeated randomized trials for `off/on × empty/history`.

## A/B runner

In the source repository, `python3 evals/bench_compare.py --help` documents the explicit model-runner. It creates isolated scratch copies and stores, invokes `codex exec --json` with a fixed model and reasoning setting, and writes a JSON report to a caller-chosen output. The harness records whole invocation wall time, first observable tool action as a proxy, tool event count, and available token fields. It sums input and output tokens once; cached input is already included in input tokens. It checks key code strings and runs generated unit tests when present. These measures do not establish semantic correctness; retain final messages and test output for review. It does not claim tool-action events equal every hidden model/tool operation.

Compare each condition separately (`memory off/on × empty/history`) with identical task text and starting code, at least three shuffled repetitions per condition, one named model and reasoning setting. Report medians and ranges for first action and full task, observed calls, available token counts, correctness, and missing constraints. Empty-store and seeded-history cases answer different questions. A seeded store in the off condition remains inaccessible by construction; this measures behavior without memory access, not a model's latent knowledge.

Do not benchmark with personal repository data or a production memory store. Inspect prompts and scratch cleanup policy first. Use at least three trials per cell, randomize cell order, record the model/reasoning/version, report medians and range, and include token unavailability. A benchmark of zero-delay NOOP tasks is not evidence about coding-task latency.

## Known limits

Codex events can run concurrently; hook trust is host-controlled. This package cannot ensure that implicit skill selection occurs every turn, cannot query host trust state through the CLI, and cannot enforce semantic correctness. Git status plus metadata is an invalidation aid rather than a content snapshot. Standard library credential patterns are incomplete. Deleted text may remain in filesystem snapshots or other databases. The package uses MIT. Historical model runs predate the 0.2.0 review and do not establish this version's workflow latency.

# Contributing

Python 3.10+ standard library only. Runtime lives under `skills/dev-memory`; tests/evals/docs belong at the repository root. Never add real stores, personal workflows, unrelated Skills, a background service or default paid model calls.

Ground behavior in README, SKILL.md and protocol.md. Installer changes must preserve noninteractive explicit host selection, installed-runtime checks, cancellation and data/configuration safety. Add synthetic regressions and run `python3 -m unittest discover -s tests -v`. Tests use temporary stores/fake homes. Optional real installer smoke: `python3 tests/install_smoke.py --output ../install-smoke.json`; downloads npm code into a temporary cache and does not alter real Skill directories.

Keep semantic judgments with the current AI and deterministic state transitions in CLI/SQLite. Preserve physical isolation, provenance, source revisions, opt-outs and truthful receipts. Skill examples must actually execute.

S01–S48 mapping is `evals/scenarios.json`. Semantic/host claims need actual runs. Optional model A/B: `python3 evals/bench_compare.py --model MODEL --reasoning medium --repetitions 3 --output ../benchmark.json`; consumes model usage and is excluded from CI.

Update public files and release whitelist together. Version fields in SKILL.md, plugin.json and build_release.py must agree. Migrations preserve deletion/privacy suppression; use build_release.py for public archives and SHA-256 manifests.

## Default activation end-to-end check

`python3 evals/check_automatic.py --output /outside/repository/automatic.json` executes three real Codex CLI sessions using the existing login, `gpt-6-astra` and medium reasoning. It uses synthetic projects, an isolated temporary home and empty stores; no user's instructions, Skill configuration or memory are modified. Temporary login material is copied locally for this explicit test and removed with the scratch directory. Ordinary user prompts never invoke the Skill. Model calls use the host account and take time; this is not a default CI step or an additional runtime service.

The output directory receives synthetic JSONL transcripts and the report. Verify saved records, resumed conditions and B's scope isolation separately from configuration checks. Failure is a failure; do not mark event enforcement, other hosts or latency verified from this sequence.

## Automatic maintenance evaluation

`python3 evals/check_maintenance.py --model MODEL --reasoning medium --output /outside/repository/maintenance.json` checks two real ordinary-prompt Codex sessions with synthetic duplicates, a long distinct rule and prose-only version/exception constraints. It verifies successful receipts and actual records, including no fresh-session paraphrase duplicate and scope isolation. It uses the same isolated login/scratch policy as the activation check and consumes host account usage.

For a matched coding comparison, add `--scenario automatic-maintenance` to the A/B command. Keep failed calls, unavailable tokens and unknown correctness in the report; present completed-task timing separately. Freeze runtime source while comparing. Do not call a first-tool-action timestamp a measured first business edit. Published JSON reports must omit raw transcripts, login material and local user paths.

## Lifecycle and matched performance checks

Use synthetic projects and an output path outside this repository. The program-only scale probe has no model calls:

```sh
python3 -B evals/check_lifecycle.py --program-only --output /tmp/dev-memory-scale.json
```

The explicit host evaluator creates a fresh requirements/schema/API session, an implementation/correction session, an injected-defect repair session and a separate-project session:

```sh
python3 -B evals/check_lifecycle.py --model gpt-6-astra --reasoning medium --timeout-seconds 600 --output /tmp/dev-memory-cycle.json
```

After host usage is available, run matched empty/history comparisons separately from other model evaluations:

```sh
python3 -B evals/bench_compare.py --scenario automatic-maintenance --model gpt-6-astra --reasoning medium --repetitions 3 --timeout-seconds 240 --output /tmp/dev-memory-performance.json
```

Freeze runtime sources throughout a model evaluation. Identical history is seeded in both modes; off has no installed/activated Skill. Business task/code/model/reasoning stay equal. First business edit is sampled separately from the first-tool proxy and does not prove a correct edit. Retain failed invocations and unavailable metrics; do not treat quota failures as successful fast tasks. These tools consume the existing host account's model usage; they are optional contributor evaluations, not runtime dependencies or background work. Never publish their raw authentication files or synthetic transcripts by default.

Review semantic predicates as well as outputs: an explicitly superseded historical condition is not an active permission. Plain successful tool-result observations may be stored without optional machine-verification fields; they do not certify the present workspace. The 0.5.0 final host pass and matched workflow timings remain blocked as documented in `reports/lifecycle-review.md`.

## Optional DeepSeek provider check

`python3 evals/check_deepseek.py --output /temporary-directory/deepseek-probe.json` uses synthetic HOME/project directories and the pinned published DSH filesystem provider. It downloads test-only npm dependencies with lifecycle scripts disabled, checks real Skill discovery/frontmatter/full-body loading, and removes temporary files. It does not call a model, run a complete DSH profile, change credentials or install dependencies into the product. Keep output outside the repository; this optional network check is not part of routine CI.

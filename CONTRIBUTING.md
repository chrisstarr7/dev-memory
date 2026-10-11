# Contributing

Python 3.10+ standard library only. Runtime lives under `skills/dev-memory`; tests/evals/docs belong at the repository root. Never add real stores, personal workflows, unrelated Skills, a background service or default paid model calls.

Ground behavior in README, SKILL.md and protocol.md. Installer changes must preserve noninteractive explicit host selection, installed-runtime checks, cancellation and data/configuration safety. Add synthetic regressions and run `python3 -m unittest discover -s tests -v`. Tests use temporary stores/fake homes. Optional real installer smoke: `python3 tests/install_smoke.py --output ../install-smoke.json`; downloads npm code into a temporary cache and does not alter real Skill directories.

Keep semantic judgments with the current AI and deterministic state transitions in CLI/SQLite. Preserve physical isolation, provenance, source revisions, opt-outs and truthful receipts. Skill examples must actually execute.

S01–S48 mapping is `evals/scenarios.json`. Semantic/host claims need actual runs. Optional model A/B: `python3 evals/bench_compare.py --model MODEL --reasoning medium --repetitions 3 --output ../benchmark.json`; consumes model usage and is excluded from CI.

Update public files and release whitelist together. Version fields in SKILL.md, plugin.json and build_release.py must agree. Migrations preserve deletion/privacy suppression; use build_release.py for public archives and SHA-256 manifests.

## Default activation end-to-end check

`python3 evals/check_automatic.py --output /outside/repository/automatic.json` executes three real Codex CLI sessions using the existing login, `gpt-6-astra` and medium reasoning. It uses synthetic projects, an isolated temporary home and empty stores; no user's instructions, Skill configuration or memory are modified. Temporary login material is copied locally for this explicit test and removed with the scratch directory. Ordinary user prompts never invoke the Skill. Model calls use the host account and take time; this is not a default CI step or an additional runtime service.

The output directory receives synthetic JSONL transcripts and the report. Verify saved records, resumed conditions and B's scope isolation separately from configuration checks. Failure is a failure; do not mark event enforcement, other hosts or latency verified from this sequence.

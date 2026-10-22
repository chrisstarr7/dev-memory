# Recall performance review — 0.8.6

## Scope and evidence

Baseline: main commit `4655b4920a82565b7797b0911c09eb78e06d543e` (0.8.5). The comparison freezes its Python scripts outside the checkout and uses the same isolated synthetic stores for both versions. No private global/project memories are exported or modified by the benchmark; no hosted model is invoked.

The fixture has an empty global store and 1,000 or 10,000 active, unverified project rules. It covers Git and non-Git directories, narrow and saturated read-only recall, ordinary combined context without a session, first/cached session context, related-record matching, actual CLI invocation, and a 500-dirty-file fingerprint. Each operation has five wall-clock samples. Versions execute sequentially under possible concurrent regression-test load: these are local observations, not an interleaved experiment or a total AI conversation speed claim. Small differences on unchanged paths are inconclusive.

## Changes

1. Previously every project recall started three Git processes before querying, even without a session cache or historical verification. Now only writable session-cache calls need this early snapshot. Other calls compute HEAD and a fingerprint once, after SQL completes, only if matched records have historical verification. Read-only/uncached unverified recall needs no Git probe.
2. Git fingerprints repeatedly resolved the same root for every changed path. Resolve the root once per fingerprint while retaining per-path resolution, containment checks, metadata, overflow handling and the original persisted hash format.

No retrieval terms, ordering, detail/character limits, scope reservations, global candidate eligibility, source validation or completeness cues were loosened. Historical verification still reports changed/unknown workspaces. Session-cache calls still check branch, HEAD and workspace every time, including forced calls that can populate the cache. Project cache writes still require Git tracking/exclusion protection.

## Measurements

Medians in milliseconds (baseline → working):

| Operation | Non-Git 1k | Non-Git 10k | Git 1k | Git 10k |
| --- | ---: | ---: | ---: | ---: |
| Read-only narrow recall | 307.9 → 32.7 | 346.6 → 56.9 | 442.7 → 35.1 | 270.8 → 43.8 |
| Read-only saturated recall | 410.3 → 44.4 | 615.3 → 374.6 | 360.7 → 46.2 | 508.0 → 274.2 |
| Context, no session | 408.8 → 67.2 | 344.6 → 95.3 | 342.8 → 56.2 | 296.6 → 64.0 |
| Context, first session | 459.7 → 451.4 | 463.9 → 471.3 | 534.3 → 510.4 | 507.0 → 646.5 |
| Context, cache hit | 325.6 → 307.2 | 323.6 → 472.1 | 359.9 → 305.6 | 370.2 → 392.1 |
| Related-record match | 64.9 → 58.7 | 518.3 → 527.8 (deferred) | 66.9 → 61.2 | 522.7 → 518.1 (deferred) |
| Actual CLI context, no session | 1065.0 → 662.2 | 1135.2 → 764.6 | 1210.6 → 683.6 | 1042.5 → 805.1 |

The no-session/unverified program paths dropped from three Git processes to zero in all four cells. The two 500-dirty-file checks measured 633.5 → 393.7 ms and 632.4 → 362.3 ms; both produced exactly the original fingerprint.

All 30 operation summaries matched. Twenty-eight completed comparisons are equivalent; the two 10k related-match comparisons hit the original deadline on both versions and remain inconclusive. The raw benchmark therefore honestly reports `needs_review`, not an all-path performance pass. Session-cache calls retained the same Git counts (first: four non-Git/five Git; hit: three); their timing varies in both directions, so no session-cache speed improvement is claimed.

Core store SHA-256: baseline `1cb541431e3ffe397db9b8caa020c4d0aaa5de25df22ba51ebadee7980074c16`; working `f0a54ff697fac43ed3bedf542d6ae01737c9892c3bfd7c5772e5fab6160e7b17`. Release metadata changes after measurement do not change this store implementation.

## Adversarial review

- Rejected time-based Git/cache reuse: it can hide changed code, branch changes or newly tracked private memory.
- Kept the current branch/HEAD/status protocol on cache-capable calls. Combining branch output into status requires a new parser for unborn/detached/upstream states; this release uses the smaller demonstrated changes.
- Kept the existing indexed term-led recall SQL and its 500 ms progress budget. The previous related-record forced-index experiment was slower; no speculative index or approximate candidate pruning was introduced.
- Large common-term matching may still defer at its SQL deadline; deferral is incomplete evidence, never successful empty recall. The benchmark reports such comparisons as inconclusive.
- Python startup, filesystem/antivirus effects, SQLite locks, Git startup and model reasoning remain outside the SQL progress budget. Their contribution to whole-conversation latency is not established here.

## Verification and reproduction

New regressions cover zero Git probes without cache/verification, a shared verified snapshot, current/stale/unknown verification labels and unchanged returned records. Existing coverage checks workspace/cache invalidation, incomplete results, paused/disabled/excluded stores, private Git write protection and source provenance. An independent read-only review found no actionable issue in the runtime diff.

Freeze the baseline scripts from the commit above outside the source tree, then run with Python 3.10+:

```text
python -B evals/check_recall_performance.py --baseline-scripts /absolute/baseline/scripts --output /absolute/outside-source/comparison.json
python -B -m unittest discover -s tests -v
```

The benchmark checks runtime hashes before/after, compares full retrieved records, omitted IDs/descriptors, maintenance cues and completeness, and keeps raw synthetic results outside the repository. Performance numbers are observations, not timing gates in CI.

Local complete regression: 273 tests, 272 passed and one documented Bash-on-Windows skip. Skill validation passed. No updated hosted-model lifecycle or whole-conversation timing A/B was run.

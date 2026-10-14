# 0.7.0 Codex CLI task comparison

This is an exploratory, real-host comparison using synthetic project files and refund-policy fixtures. Host: Codex CLI 0.155.1; model: `gpt-6-luna`, high reasoning; one run per cell. The task supplied the same explicit policy in every condition and generated/executed unit tests. “History” additionally seeded equivalent and long project-memory records so the existing bounded maintenance path was exercised.

| Memory | Seeded history | Elapsed | Tool events | Memory CLI events | Maintenance protocol reads | Behavior criteria | Generated tests |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Off | Empty | 70.151 s | 8 | 0 | 0 | 0/1 | Pass |
| Off | Seeded | 68.856 s | 5 | 0 | 0 | 1/1 | Pass |
| On (0.7.0) | Empty | 106.008 s | 9 | 1 | 0 | 0/1 | Pass |
| On (0.7.0) | Seeded | 115.392 s | 16 | 7 | 2 | 1/1 | Pass |

All four host processes completed. Generated test suites passed in all four runs. The independent six-case behavior probe passed in two of four runs; tests passing did not guarantee correct behavior. This is material: the observed memory-enabled paths did not outperform the disabled paths in this small sample, and the seeded maintenance scenario used extra memory tools and protocol reads.

Limits: one sample per cell is not enough to estimate typical latency; model and startup variation are large. Seeded history deliberately triggers maintenance, so it does not represent an ordinary task. This comparison used the 0.7.0 runtime with memory enabled or disabled; it did **not** rerun 0.6.0 on the same task, and it does not test whether Codex automatically loads user-level instructions across two projects. Historical 0.6.0 benchmark data is not a matched baseline. No claim of negligible overhead or verified user-level host activation follows from these results.

A separate local SQLite scale probe seeded 300 synthetic global habits. Ten forced recalls for a narrow term took 19.353 ms total (1.935 ms/query) on this machine. `EXPLAIN QUERY PLAN` started with `search_term_term (term=?)`, then looked up matching memories by primary key. The probe requested at most 2 full details and saw `candidate_limit_reached=true`; the union held 22 candidate IDs before the configured candidate/detail shaping. This is a small local dataset and not a guarantee for larger stores or slower disks.

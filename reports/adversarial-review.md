# Adversarial review — 0.2.0

Scope: Skill instructions, deterministic privacy/provenance/storage boundaries, installer/hooks and publication. Synthetic stores only; not a claim against every semantic injection or same-user process attack.

| Priority | Reproduced issue | Correction |
| --- | --- | --- |
| High | A private-turn receipt stopped repair but late apply still wrote it | Transactional skip guard; retain skips on restore |
| High | ADD upsert bypassed expected revision and reused forgotten IDs | Fresh/nonforgotten IDs; explicit revisioned edits |
| High | Forget left Markdown containing original text; empty buckets remained | Remove generated views on forget/restore; export clears old managed buckets; report cleanup failures |
| High | Global evidence and metadata bypassed scope checks | Apply global checks to metadata/evidence; require literal JSON true |
| High | Dedup merged tasks and desired/observed claims | Scope/task/claim/strength/constraint identity; explicit init migrates old hashes |
| Medium | Same idempotency key with changed content claimed old success | Request digest; exact replay; reject ambiguous legacy request |
| Medium | Raw turn IDs collided between conversations | Session + turn ingestion identity |
| Medium | New query inherited unrelated cache; incomplete context cached | Query terms/budgets in cache; incomplete lookup never certified complete |
| Medium | Nonmatching business queries omitted global preferences | Bounded baseline preferences/conventions always considered |
| Medium | Paused recall mutated session cache | Nonmutating recall for paused stores |
| Medium | Nested Git pathspec cwd and ignore metacharacters were wrong | Repository-root checks, escaped literal paths, multiple project blocks |
| Medium | Some paths missed database/config identity; initializer could replace an identity in a race | Namespace/storage-type checks and atomic first configuration creation |
| Medium | Template exclusion/limit fields were ignored | Apply configured limits and project exclusion; doctor reports effective state |
| Medium | Missing evidence type defaulted to user statement | Require source type; label generated ingestion IDs honestly |
| Medium | Backup cleanup could touch a foreign namespace | Validate controlled backup identity; report skipped mismatches |
| Medium | Stale summary sources and self supersession could succeed | Source revisions/scope/task/cycle guard; distinct replacement ID |
| Medium | Managed marker allowed deletion of extra user files | Check marker content, whitelist, symlinks and data paths before removal |
| Medium | Hook removal could alter unrelated commands/unknown event shapes | Match standalone Python adapter; preserve unrelated/unknown fields |
| Medium | Main example combined feedback with tool verification and failed | Tested desired-rule example, tool-result verification documented separately |
| Low | Runtime included tests/evals/reports; install assumed one host | Standard runtime directory plus ecosystem and local host installers |

Regressions: 26 tests in tests/test_adversarial.py, plus 38 original program tests; final 64-test run passed. Exact final results are in verification.md and install-smoke.json. Format validation, code copying, actual model invocation and trusted host events remain distinct evidence.

Remaining: caller provenance/semantic scope cannot be independently proved; rephrased opt-outs under new IDs cannot be detected; credential patterns are incomplete; no secure disk erasure; metadata/Git signature is not a full code snapshot; bounded recall can require follow-up; corrupt/unwritable/symlinked cleanup artifacts need explicit attention. External copies, unknown host versions, same-user path races and third-party manager contracts remain outside deterministic guarantees.

At the original 0.2.0 review, Codex event trust/delivery, other hosts' model invocation, plugin marketplace installation and remote GitHub URL installation were unverified. Later public GitHub installation checks are recorded in verification.md; automatic host delivery remains unverified. Historical model A/B results belong to the pre-review source, with no new model run in this review.

Complexity review after checks: removed two unused cache helpers and reused existing CLI/SQLite boundaries. No custom network bootstrap, npm runtime, host SDK, daemon or multi-agent framework was introduced. Installation is a six-entry host mapping with identical runtime files.

## Installation and onboarding review — 0.2.1

| Priority | Adversarial first-use scenario | Change / evidence |
| --- | --- | --- |
| High | A Claude user runs the short Python command and silently installs to Codex | Interactive AI selection; noninteractive calls without an explicit AI fail without creating a directory |
| High | Installer reports success after copying, but Python/sqlite3 or the installed CLI cannot run | Preflight and installed CLI doctor; failure returns a nonzero exit and does not claim successful verification |
| High | Doctor returns malformed/unsupported JSON, or missing stores are confused with failed program installation | Validate response shape and base CLI capability; docs distinguish empty, uninitialized memory from unusable runtime |
| Medium | A user sees several installation methods but cannot choose or tell what to do next | One recommended AI prompt; one manual command with AI menu; installed path and next-session instruction |
| Medium | Installing is mistaken for enabling automatic memory | Three explicit onboarding steps; only project enablement authorizes initialization; automatic event delivery remains unverified |
| Medium | AI clones the repository, then mistakes that staging directory for the user's business project | AI guide retains the original workspace and returns there for enablement |
| Medium | A repeated install overwrites existing notes or resets data/configuration | Explicit managed upgrade; extra files block replacement; database/config/hooks preservation checked |
| Low | Expert command carries redundant Skill selector and is mixed with beginner steps | Optional skills-manager route in the guide; one Skill in the repo, omit --skill |

74 program tests passed, including 10 installer regressions. A real terminal menu selected Codex in a temporary HOME, verified the CLI, displayed next steps, and left memory/hooks uninitialized. All tests are synthetic; no developer memory or installation was modified. A test-fixture assumption placed global config at the wrong parent path; the corrected fixture follows global_paths and the final suite passed. Program checks do not prove that a novice AI session follows the guide or that hosts discover the Skill. No new model onboarding evaluation, automatic host E2E or latency A/B was run.

Complexity review: reuse the existing managed copy/upgrade implementation, add one small human-facing entry point, keep machine JSON behind --json. No network bootstrap, shell-pipe installer, package registry dependency or host-directory guessing was added.

## Default project activation review — 0.3.0

### Findings corrected

- Installation only placed the Skill and left invocation to the user. Added explicit `install.py --project` and installed CLI `setup` to initialize independent stores and merge host-native project instructions. Normal tasks no longer require an enable/save/continue phrase.
- Codex can prefer `AGENTS.override.md` over `AGENTS.md`. Setup uses an existing nonempty override; it does not create an override that hides team instructions. An empty override is left empty and the existing `AGENTS.md` is updated.
- A new session had no task ID, so ordinary focused recall could exclude its checkpoint. Explicit continuation now uses bounded `--resume` candidates without choosing an ambiguous task automatically. The intent participates in cache identity.
- A mixed-scope batch inherited the envelope's project task/branch into its global operation. Global processing now drops inherited project metadata; explicit project markers inside a global record remain rejected. Separate commits and receipts are retained.
- Model evaluation exposed a code-edit scope being treated as a memory opt-out. The Skill now scopes normal code-file limits to business edits while respecting explicit memory/state/all-file write prohibitions.
- Cursor's managed rule could have `alwaysApply: false` yet be reported configured. Setup rejects that conflict and doctor reports it inactive.

### Checked invariants

Synthetic tests cover all six host guide paths, idempotent one-command setup, preserving existing instructions/bindings/paused settings, empty stores, unknown/symlinked paths, malformed markers, oversized instruction files, existing setup locks, tracked memory paths, project/global partial failures, unavailable bindings and truthful diagnostics. A changed guide under the activation lock is rejected instead of overwriting concurrent user edits.

### Limits retained

Project instructions guide the current model; they are not an enforced per-turn event system. Host trust, instruction settings, nested overrides and context limits can affect loading. Only named real-host sessions in the verification report establish observed AI behavior. Cross-host and desktop behavior are not inferred from six-host configuration tests. A same-user adversarial file replacement race remains outside the filesystem threat boundary. Setup's bounded lock can remain after an interrupted process and requires inspection before removal. Uninstall does not enumerate other projects or erase private memories.


## Online installation review — 0.3.1

- Manual ZIP download, unpacking and specifying a business path made the default workflow needlessly long. The recommended macOS/Linux command now fetches the online bootstrap using system curl and initializes the original current project. AI selection is still explicit. Source invocation keeps its documented offline/program-only behavior.
- A shell pipe can report success when an upstream download fails and feeds an empty script to Python. The recommended macOS/Linux entry runs the pipe under Bash with `pipefail`, propagating download failures; Windows uses Python fetch/execute. No extra package manager is required. Real online execution exposed missing certificates in this macOS Python build; snapshot reads now also load macOS system CAs, retaining verification and explicit custom CA settings.
- ZIP traversal, absolute/Windows paths, duplicate entries, symlinks, special/encrypted files, missing manifest files and checksum mismatches are rejected before executing downloaded code. Compressed/expanded bytes, entry count, per-file bytes and manifest size are bounded. Only manifest-checked public files are staged.
- Staging could be mistaken for the business directory. The bootstrap captures the original project and explicitly passes it to the shared source installer; private activation paths refer to the installed runtime and stable interpreter. Temporary source is cleaned on success and failure.
- Copy success or a malformed child receipt could be mistaken for complete activation. The wrapper checks the child exit, runtime result, project identity, activation and both independent store receipts. Actual partial failures are retained; human output includes per-store status.
- Network download and child installation are bounded, with no automatic retry loop. A child timeout may leave installed programs or initialized empty stores; it reports this possibility. Repeating the same command safely updates a managed installation while preserving existing records, identities, controls and unrelated instructions.

Complexity review: reuse the existing installer/setup/storage functions and argument parser; the standalone online bootstrap uses only Python standard-library HTTP, temporary files and ZIP support. No npm package, service, daemon or per-turn network operation was introduced. Integrity checks establish consistency of trusted GitHub source, not independent code authenticity.

Windows command syntax is provided, but no real Windows installation or Windows host session was run. The online transport change does not establish new cross-host model behavior, hook enforcement or whole-workflow latency; existing limitations remain.

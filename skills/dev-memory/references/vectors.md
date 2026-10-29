# Local vectors: operation and recovery

The source of truth remains the existing `memory.sqlite3` in each scope. Original Chinese/English text, evidence, revisions and counts remain readable through the ordinary CLI and dashboard. sqlite-vec is a retrieval index in that same file, not a replacement for original text. Global and project databases remain separate.

## Runtime and installation

Prepare the user-managed prerequisites before Skill installation; see [environment preparation](../../../docs/installation.md#environment-prerequisites). On Windows, the pinned vector packages support standard x64 CPython 3.10–3.14; recommend the latest 3.14 patch and the current x64 Microsoft Visual C++ Redistributable. Native Windows ARM64, 32-bit, Python 3.15 and free-threaded builds have no complete matching wheel set for these pins. The base SQLite runtime retains its separate Python 3.10+ requirement. macOS continues to use the managed native Python 3.12 runtime.

Setup checks the actual vector interpreter and selects dependencies for that version, including when the existing virtual environment was created by a different host Python. Errors identify the stage, a sanitized cause and a preparation/remediation step. A missing wheel can mean incompatible Python/architecture or an incomplete package mirror; a failed native-library import does not by itself prove a missing VC++ runtime. Raw dependency logs, proxy credentials and download URLs are not copied into memory receipts.

Install/update attempts vector setup automatically. Use `--without-vectors` for basic installation without dependency/model downloads. A vector setup failure is reported separately from successful base installation. It must not enable paused capture, recreate missing stores, or discard existing records. Ordinary recall never installs packages or downloads models.

The shared runtime is `<global-root>/vector-runtime/`:

- `venv/`: isolated Python environment, with `fastembed==0.9.1` and `sqlite-vec==0.1.9`. ONNX Runtime is pinned for the effective Python version.
- On macOS, `bootstrap/`, `python/` and `venv-py312/` hold pinned `uv==0.13.6` and an isolated native Python 3.12 runtime. This avoids both missing Intel wheels and host Python builds that omit SQLite extensions. It does not replace the user's Python. macOS ONNX Runtime is pinned to 1.23.2 and requires macOS 13 or newer.
- `models/`: local model assets shared by projects, not project memory data.
- `config.json`: runtime paths, model identity and artifact fingerprints; `enabled:false` is preserved by updates.

The initial CPU model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, a 384-dimensional multilingual model downloaded through FastEmbed. Ordinary inference uses ONNX Runtime directly and never imports the downloader. It is not an E5 model and does not use E5 query/passage prefixes. The tokenizer's default truncation is disabled before splitting into 96-token chunks with 16-token overlap; pooled normalized vectors include the full rule. The embedding-format version participates in index and cache identity. The initial cosine-distance gate is 0.60, checked against bilingual positive and unrelated fixtures, not a universal relevance guarantee. A matching vector is a retrieval candidate, never proof that two rules are equivalent.

Setup is allowed network access to install dependencies and download the fixed model. Subsequent inference uses local assets. Model loading and indexing may consume CPU and memory while the assistant works; asynchronous execution is not zero cost.

Windows x64 and macOS Apple Silicon/Intel are separate compatibility targets. Python, native packages and SQLite extension architecture must match. When host Python lacks `enable_load_extension`, the CLI automatically uses its validated managed runtime after setup, including for transactional cleanup. See [sqlite-vec's Python guidance](https://alexgarcia.xyz/sqlite-vec/python.html). Platform support is established by successful real model/extension checks on that platform, not by installation alone.

## Commands

Use the installed Skill's Python entry point; the package's `dev-memory` bin is an installer. Put a custom `--global-root PATH` before `vectors`.

Windows PowerShell, default Codex installation:

```powershell
py -3 "$env:USERPROFILE\.agents\skills\dev-memory\scripts\dev_memory.py" vectors setup
py -3 "$env:USERPROFILE\.agents\skills\dev-memory\scripts\dev_memory.py" vectors status --scope both --project-root .
py -3 "$env:USERPROFILE\.agents\skills\dev-memory\scripts\dev_memory.py" vectors sync --scope both --project-root .
py -3 "$env:USERPROFILE\.agents\skills\dev-memory\scripts\dev_memory.py" vectors finish --scope both --project-root . --wait-seconds 3
```

macOS/Linux, default Codex installation:

```sh
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py vectors setup
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py vectors status --scope both --project-root .
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py vectors sync --scope both --project-root .
python3 ~/.agents/skills/dev-memory/scripts/dev_memory.py vectors finish --scope both --project-root . --wait-seconds 3
```

Replace the interpreter and Skill paths for another host. `status` inspects state; `sync` requests a bounded batch; `finish` checks the result and waits within its limit. None of them initializes a missing memory store or changes capture mode. Scope `both` means the global store and specified current project, never every registered project.

## Save, query and display

1. The assistant judges durability, scope, evidence, privacy and existing equivalents under the normal Skill rules.
2. The raw transaction saves the record and invalidates any old vector. The original-save receipt is authoritative even if inference fails.
3. A local process calculates vectors outside a write transaction. One batch has a 10-second execution budget, including model loading.
4. Before vector commit, recheck record identity/revision, model fingerprint, eligibility and capture controls. A changed or deleted record rejects a late result.
5. Once the requested work and its authorized checks are complete, send one visible progress message before the finish check, for example: “修复和本轮检查已完成，可以先查看或自行提交代码；我正在确认记忆向量化结果。” Use the actual task and known indexing state, not an assumption that a previously running job is still running. Then perform one finish check before the final reply. Additional waiting is at most 3 seconds within the remaining batch budget, not 3 seconds per record. Report pending vectors accurately; on timeout say the original was saved and vectors await completion. This notice does not authorize an automatic commit.
6. Recall generates a query vector within a 5-second combined-call budget, fuses candidates with keyword results and rechecks authoritative records. Timeout/unavailability returns lexical results with a degradation reason. The existing context limits and global/project isolation still apply.
7. Only full details actually delivered increment ordinary recall counts. Candidate indexes, cached results and read-only previews do not. Vector and keyword duplicates count once.

The dashboard reads original text and vector state from the same store. Ordinary browsing starts no indexing or model download. A ready vector matches the current source revision; pending records remain searchable by keywords. An unavailable runtime must show a reason. A crashed process cannot leave a permanent unexpired processing state.

Time budgets are execution limits, not measured latency or accuracy guarantees. Cold inference may exceed a budget on a supported machine and correctly fall back to lexical retrieval.

## Failure and lifecycle

| Condition | Required behavior |
| --- | --- |
| Dependency/model unavailable | Keep raw records and keyword recall; report vector degradation. |
| Calculation exceeds the batch budget | Terminate computation, reject late results, keep pending source state. |
| Record revised while encoding | Discard the old revision's result; never use its vector for the new source. |
| Record archived, superseded or deleted | Exclude it from ordinary semantic recall; indexing cannot resurrect it. |
| Capture paused, read-only request or turn opt-out | Do not schedule new writes; recheck controls before a pending commit. |
| Recall disabled or scope excluded | Do not expose original text or vector search results. |
| Model/template fingerprint changes | Invalidate old vectors and rebuild through bounded maintenance; never mix spaces. |
| Permanent forget | Clean vectors as well as source/history under the confirmed scope, including managed backups; incomplete cleanup is not complete forgetting. |
| Restore | Invalidate restored/stale derived indexes and rebuild from restored authoritative records. Preserve deletion suppression and controls. |

An interrupted host may not execute its final hook. Raw-first persistence and durable pending state allow later recovery without a permanently running service. The embedding model does not decide promotion, semantic merging, scope or permission to save.

A query with no matches is not a reason to save the current task. Capture still requires supported durable information, correct scope and permitted controls. The visible progress message keeps the user informed while finalization runs; it does not weaken the capture or completion gates.

The dashboard's record detail contains an expandable **查看实际存储的向量数据** section. It reads the actual float32 vector from `memory_vectors` and displays all 384 components, stored model fingerprint, indexed/current revisions and update time. Existing stale vectors remain inspectable with an explicit warning; inspection never makes them eligible for recall. Missing runtime/extension data is reported without hiding original text. Disabled/excluded stores expose neither text nor vector data. This read-only view does not load the embedding model, enqueue indexing or increment recall counters.

## Verification boundary

`vectors.yml` defines real integration checks on Windows, macOS ARM and macOS Intel with Python 3.10/3.14. The integration test must fail when setup degrades; a keyword fallback is not evidence that vectors worked. It verifies actual local embedding and sqlite-vec retrieval after setup, with ordinary runtime offline. Unit tests separately cover timeout, revision races, controls and lifecycle behavior. A configured matrix is not a passing CI result; report the result for the exact tested commit.

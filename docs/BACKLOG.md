# Backlog — anime-subtitle-pipeline

Generated: 2026-04-25. Based on full code review + security scan.

---

## Already Fixed (this session)

- **[SECURITY]** `anime-subtitle-pipeline/.gitignore` was missing `.env`, `*.backup`, artifact JSON files.  Added all of these.
- **[SECURITY]** Revoked GitHub token string was still sitting in `Anime_subtiltes/japanese-subtitle-generator/.env`. Replaced with placeholder.
- **[SECURITY]** `subtitle_corrector.py` had `OLLAMA_BASE_URL` hardcoded as `"http://localhost:11434"` with no escape hatch. Fixed to read `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")`, matching how `MODEL` is already handled in the same file.
- **[CODE]** `asr.py` used a `setattr` hack to attach `_build_candidate_from_segments` to the class from outside the class body. Moved it to a proper instance method.
- **[NOISE]** `llm_polish.py` emitted a `WARNING: Non-localhost LLM endpoint` on every API call when running against Unraid Ollama (`192.168.x.x`). Removed — non-localhost is valid for production.
- **[PERSISTENCE]** Artifact registry migrations now run automatically through `core.artifacts.schema.init_db()` and migration files are documented in `docs/migrations/README.md`.
- **[PERSISTENCE]** `process_video()` now writes media assets, pipeline runs, subtitle candidates, output SRTs, muxed MKVs, and failure status to `ArtifactRegistry`.
- **[PERSISTENCE]** `ArtifactRegistry` and `ProcessingLedger` now expose read APIs for pipeline run history, latest artifacts, and candidate lineage.
- **[CONFIG]** `LLM_BASE_URL` now overrides `llm.base_url`, so Docker/Unraid deployments can point at a LAN Ollama endpoint without editing `config.yaml`.
- **[CLI]** `subtitle_corrector.py` now exposes `--timeout` and validates it as a positive integer.
- **[QC]** `subtitle_corrector.py` drift detection now handles all-caps names and case-only output changes.

---

## P0 — Fix Before Next Run

### ~~P0-1: Remove tracked build artifacts from git history~~ ✅ RESOLVED

None of the listed artifacts (`error_log.txt`, `benchmark.py.backup`, `comparison*.json`,
`benchmark_results.json`, `debug_test.py`, `__pycache__`) are tracked in git. Already cleaned up.

### ~~P0-2: `ConcurrentPolisher` is missing CJK guard and drift check~~ ✅ RESOLVED (commit 675bd7b)

`ConcurrentPolisher` and its `polish_segments_concurrent` method were deleted from `llm_polish.py`.
The class had zero callers, skipped the drift check and stock-phrase collapse guard, and its concurrent
design conflicted with the inherently sequential per-batch collapse check.

---

## P1 — Fix Soon (before Unraid deploy)

### ~~P1-1: Root-level test files are orphaned — pytest never runs them~~ ✅ RESOLVED (commit 1818d787)

All 9 root-level test files migrated: 8 moved to `tests/`, `test_pipeline.py` moved to `attic/`
(it was a CLI smoke script, not a real pytest module). `norecursedirs = attic` added to `pytest.ini`
to prevent `attic/debug_test.py` from being collected. No regressions introduced.

### ~~P1-2: `subtitle_corrector.py` timeout is hardcoded~~ ✅ RESOLVED (commit b6f1a62)

`subtitle_corrector.py` now exposes `--timeout` and rejects zero, negative, and
non-integer values before runtime. Tests cover parser defaults, custom values,
invalid values, and timeout forwarding to the Ollama call.

### ~~P1-3: `llm_polish.py` legacy import of `asr.Segment`~~ ✅ RESOLVED

Removed `from asr import Segment`, `LLMPolisher.polish_segments()`, `polish_english_subtitles_with_llm()`,
`enforce_subtitle_constraints_on_segments()`, and `BatchPolisher` (entire class, no callers).
`example_usage.py` rewritten to use the candidate-based API throughout. Dead legacy imports
(`polish_english_subtitles_with_llm`, `enforce_subtitle_constraints_on_segments`) also removed from `main.py`.
`__all__` in `llm_polish.py` updated to only export modern symbols.

### ~~P1-4: `subtitle_pipeline.py` — status unclear~~ ✅ RESOLVED (keep)

`subtitle_pipeline.py` has unique functionality distinct from `main.py`: it batch-processes existing SRT
files through `subtitle_corrector` with skip-if-newer logic, SHA-256 change detection, and a per-file
JSON pipeline log. `main.py` handles video → SRT generation from scratch. Both tools are valid.

### ~~P1-5: `llm.base_url` in `config.yaml` is `http://localhost:11434`~~ ✅ RESOLVED (commit b6f1a62)

`Config.llm_base_url` now checks `LLM_BASE_URL` before the YAML value, with tests
for YAML fallback and environment override behavior. README documents the
Docker/Unraid usage pattern.

### ~~P1-6: 17 orchestrator tests fail in sandbox due to `temp/` unlink permission~~ ✅ RESOLVED

All `audio_path.unlink(missing_ok=True)` and `probe_path.unlink(missing_ok=True)` calls in
`orchestrator.py` are now wrapped with `except PermissionError` (option 1). 533 tests pass.

### ~~P1-7: 3 benchmark tests fail due to missing `jiwer`/`sacrebleu` in CI~~ ✅ RESOLVED (commit 802a975)

`pytest.importorskip("jiwer")` and `pytest.importorskip("sacrebleu")` added at the top of both
`tests/test_benchmark.py` and `tests/test_benchmark_generalized.py`. Files are skipped gracefully
when optional metric libraries are absent.

---

## P2 — Improvements

### ~~P2-1: `config.py` `_apply_profile` leaves dev/prod sub-dicts in place~~ ✅ RESOLVED (commit 3a46a86)

`_apply_profile()` now pops both `"dev"` and `"prod"` keys from `asr` and `llm` sections after merging.
`_PROFILE_KEYS = ("dev", "prod")` constant added to document the known keys.

### ~~P2-2: Protect against silent regression in `generate` config key placement~~ ✅ RESOLVED

Three regression-guard tests added to `tests/test_config.py`: assert `prefer_subtitles`,
`prefer_audio_language`, and `use_llm_polish` are not `None` when loaded from the default config.

### ~~P2-3: `asr.py` — `transcribe_audio_to_candidate` reads instance attribute as return value~~ ✅ RESOLVED

`transcribe_audio_to_segments()` now returns `(List[Segment], SubtitleCandidate)` as a tuple.
All call sites updated to unpack the tuple; no more side-effect `last_candidate` attribute reads.
Module-level `transcribe_audio_to_candidate()` uses `_, cand = asr.transcribe_audio_to_segments(...)`.

### ~~P2-4: `subtitle_corrector.py` `check_drift` noun detection is case-sensitive~~ ✅ RESOLVED (commit b6f1a62)

`_extract_nouns()` now includes all-caps proper nouns, excludes common
single-letter words (`A`, `I`), and checks noun preservation case-insensitively.
Tests cover all-caps extraction, missing and preserved all-caps names, case-only
changes, and lowercased output.

### ~~P2-5: Doc sprawl in `anime-subtitle-pipeline` root~~ ✅ RESOLVED

Root Markdown is now limited to `README.md`, `CHANGELOG.md`, `SECURITY.md`,
and `CONTRIBUTING.md`. Extended guides now live under `docs/`.

---

## P3 — Nice to Have

### ~~P3-1: `Anime_subtiltes/japanese-subtitle-generator` repo is superseded~~ ✅ N/A

Directory does not exist in this repository; already removed or never committed.

### ~~P3-2: `attic/` directory has no README~~ ✅ RESOLVED

`attic/README.md` created, explaining the graveyard purpose and listing retired files with reasons.

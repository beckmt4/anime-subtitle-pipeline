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

### P0-1: Remove tracked build artifacts from git history

These files are now covered by `.gitignore` but are still **tracked** in git — `git rm --cached` won't delete the local copies but stops git from tracking future changes. The files themselves should also be deleted.

```bash
cd anime-subtitle-pipeline
git rm --cached error_log.txt benchmark.py.backup comparison.json comparison_results.json benchmark_results.json debug_test.py
git rm -r --cached __pycache__
```

Then manually delete the files from disk (Windows Explorer or PowerShell `Remove-Item`).

**Why:** `error_log.txt` contains local paths and internal run output. `comparison*.json` and `benchmark_results.json` are run artifacts that churn on every run. `.backup` files in git are an anti-pattern.

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

### P1-3: `llm_polish.py` legacy import of `asr.Segment` 

Line 23: `from asr import Segment  # legacy`

This imports the ASR-specific `Segment` dataclass (with `text_ja`, `text_en_raw`, `text_en_final` fields) rather than the generic `models.Segment`. It exists because `polish_segments()` and `BatchPolisher.polish()` still operate on legacy ASR segments. These paths are superseded by the `polish_candidate()` / `polish_candidate_with_llm()` API. The legacy path should be formally deprecated and eventually removed.

### P1-4: `subtitle_pipeline.py` — status unclear

`subtitle_pipeline.py` exists at root. It was likely an earlier version of `main.py`. Check whether it has unique functionality or is fully superseded. If superseded, move to `attic/`.

### ~~P1-5: `llm.base_url` in `config.yaml` is `http://localhost:11434`~~ ✅ RESOLVED (commit b6f1a62)

`Config.llm_base_url` now checks `LLM_BASE_URL` before the YAML value, with tests
for YAML fallback and environment override behavior. README documents the
Docker/Unraid usage pattern.

### P1-6: 17 orchestrator tests fail in sandbox due to `temp/` unlink permission

`tests/test_orchestrator.py` contains 17 tests that fail in the Linux sandbox with
`PermissionError: [Errno 1] Operation not permitted` when `orchestrator.py` calls
`audio_path.unlink(missing_ok=True)` to clean up temp WAV files. This is a Windows-
filesystem-mount restriction (the sandbox cannot delete files on the Windows mount).

The tests pass on the user's real dev machine. Fix options:
1. Suppress unlink errors in orchestrator: `try: audio_path.unlink(missing_ok=True) except PermissionError: pass`
2. Let the orchestrator accept a `cleanup=True` flag that tests can set to `False`
3. Mock `Path.unlink` in the test fixtures

Option 1 is lowest risk — a missing temp cleanup is not a correctness problem.

**Affected tests:** `test_strategy_en_audio_*`, `test_strategy_ja_audio_asr_mt`,
`test_skip_embedded_en_forces_generation`, all probe tests, `test_polish_status_fallback_*`,
and most `test_selection_report_*` tests.

### P1-7: 3 benchmark tests fail due to missing `jiwer`/`sacrebleu` in CI

`tests/test_benchmark.py::test_compute_metrics_*` and `test_compare_candidates_basic`
fail with `ModuleNotFoundError: No module named 'jiwer'`. The library is in
`requirements.txt` but not installed in CI or the sandbox environment.

Two of these tests (`test_compute_metrics_perfect`, `test_compute_metrics_different`)
call `compute_metrics()` directly. Add `pytest.importorskip("jiwer")` at the top of
`test_benchmark.py` to skip the whole file when the library is absent, rather than
failing with an ImportError.

`test_benchmark_generalized.py` has 2 additional failures that need investigation —
they may be a downstream effect of the missing `jiwer` import.

---

## P2 — Improvements

### P2-1: `config.py` `_apply_profile` leaves dev/prod sub-dicts in place

After calling `_apply_profile()`, the `_config["asr"]` dict still contains nested `"dev": {...}` and `"prod": {...}` keys alongside the merged values. This is harmless but `cfg.get("asr", "dev")` would return a dict rather than raising. Add cleanup to remove the profile sub-dicts after merging.

### P2-2: Protect against silent regression in `generate` config key placement

The comment in `config.yaml` notes that the `generate:` section was previously nested under `benchmark:` which caused a silent fallback to defaults. There is no test guarding against this regression. Add a test in `tests/test_config.py` that asserts `cfg.get("generate", "prefer_subtitles")` is not `None` when loaded from the default config.

### P2-3: `asr.py` — `transcribe_audio_to_candidate` reads instance attribute as return value

`transcribe_audio_to_candidate()` calls `transcribe_audio_to_segments()` and then reads `asr.last_candidate` — an attribute that is set as a side-effect inside `transcribe_audio_to_segments`. This is fragile: the attribute is only set after a successful run, and `getattr(asr, "last_candidate", None)` silently returns `None` on failure, triggering a fallback that rebuilds the candidate without the language info from the Whisper info object. Refactor to return the candidate directly from `transcribe_audio_to_segments`.

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

### P3-1: `Anime_subtiltes/japanese-subtitle-generator` repo is superseded

This was the original prototype that used GitHub Models API. It's superseded by `anime-subtitle-pipeline` which uses local Ollama. Add a `README.md` deprecation notice pointing to `anime-subtitle-pipeline`, or archive the directory.

### P3-2: `attic/` directory has no README

Add `attic/README.md` explaining that this is a graveyard for retired code and scripts. Anyone reading the repo shouldn't wonder what `attic/` is for.

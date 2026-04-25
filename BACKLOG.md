# Backlog — anime-subtitle-pipeline

Generated: 2026-04-25. Based on full code review + security scan.

---

## Already Fixed (this session)

- **[SECURITY]** `anime-subtitle-pipeline/.gitignore` was missing `.env`, `*.backup`, artifact JSON files.  Added all of these.
- **[SECURITY]** Revoked GitHub token string was still sitting in `Anime_subtiltes/japanese-subtitle-generator/.env`. Replaced with placeholder.
- **[SECURITY]** `subtitle_corrector.py` had `OLLAMA_BASE_URL` hardcoded as `"http://localhost:11434"` with no escape hatch. Fixed to read `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")`, matching how `MODEL` is already handled in the same file.
- **[CODE]** `asr.py` used a `setattr` hack to attach `_build_candidate_from_segments` to the class from outside the class body. Moved it to a proper instance method.
- **[NOISE]** `llm_polish.py` emitted a `WARNING: Non-localhost LLM endpoint` on every API call when running against Unraid Ollama (`192.168.x.x`). Removed — non-localhost is valid for production.

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

### P0-2: `ConcurrentPolisher` is missing CJK guard and drift check

`llm_polish.py` lines 696–752: `ConcurrentPolisher.polish_segments_concurrent` calls `polish_text()` but does **not** run the drift check (`check_drift`) or stock-phrase collapse guard that `LLMPolisher.polish_segments()` runs. If this class is ever used, it will pass through hallucinated or drifted translations without any safety net.

Fix: Either delete `ConcurrentPolisher` (it's marked "optional enhancement" and has no callers) or move the guard logic into `polish_text()` so all callers benefit.

Recommended: **Delete it.** It's dead code, and its concurrent nature would violate the per-batch stock-phrase collapse check which is inherently sequential.

---

## P1 — Fix Soon (before Unraid deploy)

### P1-1: Root-level test files are orphaned — pytest never runs them

`pytest.ini` sets `testpaths = tests`. The 9 root-level `test_*.py` files are never run by CI or local `pytest`:

```
test_asr_candidate.py
test_audio_selection.py
test_benchmark.py
test_benchmark_generalized.py
test_candidate_pipeline.py
test_models_and_inspect.py
test_orchestrator.py
test_pipeline.py
test_subtitle_utils.py
```

Some of these have real `def test_*` functions that cover scenarios not in `tests/`. They should be:
1. Reviewed against `tests/` for overlap
2. Unique tests moved into `tests/` with proper conftest fixtures
3. Script-style files (no real `def test_`) moved to `attic/` or deleted

**Priority order to integrate:** `test_orchestrator.py`, `test_audio_selection.py`, `test_asr_candidate.py`.

### P1-2: `subtitle_corrector.py` timeout is hardcoded

`_call_ollama(... timeout: int = 120)` — 120s is the fallback default but the CLI exposes no `--timeout` flag. The corrector is a standalone CLI tool; heavy models on slow hardware can exceed this. Add `--timeout` to `_build_parser()`.

### P1-3: `llm_polish.py` legacy import of `asr.Segment` 

Line 23: `from asr import Segment  # legacy`

This imports the ASR-specific `Segment` dataclass (with `text_ja`, `text_en_raw`, `text_en_final` fields) rather than the generic `models.Segment`. It exists because `polish_segments()` and `BatchPolisher.polish()` still operate on legacy ASR segments. These paths are superseded by the `polish_candidate()` / `polish_candidate_with_llm()` API. The legacy path should be formally deprecated and eventually removed.

### P1-4: `subtitle_pipeline.py` — status unclear

`subtitle_pipeline.py` exists at root. It was likely an earlier version of `main.py`. Check whether it has unique functionality or is fully superseded. If superseded, move to `attic/`.

### P1-5: `llm.base_url` in `config.yaml` is `http://localhost:11434`

This works on dev but will fail on Unraid where Ollama listens on the LAN IP. The config is the right place to change this, but there's no env var override for `llm.base_url` in `config.py`. Add a fallback: `llm_base_url` should check `LLM_BASE_URL` env var before returning the YAML value. This makes Docker/Unraid deployment easier without editing config.yaml.

```python
@property
def llm_base_url(self) -> str:
    return os.environ.get("LLM_BASE_URL") or self.get("llm", "base_url", default="http://localhost:11434")
```

---

## P2 — Improvements

### P2-1: `config.py` `_apply_profile` leaves dev/prod sub-dicts in place

After calling `_apply_profile()`, the `_config["asr"]` dict still contains nested `"dev": {...}` and `"prod": {...}` keys alongside the merged values. This is harmless but `cfg.get("asr", "dev")` would return a dict rather than raising. Add cleanup to remove the profile sub-dicts after merging.

### P2-2: Protect against silent regression in `generate` config key placement

The comment in `config.yaml` notes that the `generate:` section was previously nested under `benchmark:` which caused a silent fallback to defaults. There is no test guarding against this regression. Add a test in `tests/test_config.py` that asserts `cfg.get("generate", "prefer_subtitles")` is not `None` when loaded from the default config.

### P2-3: `asr.py` — `transcribe_audio_to_candidate` reads instance attribute as return value

`transcribe_audio_to_candidate()` calls `transcribe_audio_to_segments()` and then reads `asr.last_candidate` — an attribute that is set as a side-effect inside `transcribe_audio_to_segments`. This is fragile: the attribute is only set after a successful run, and `getattr(asr, "last_candidate", None)` silently returns `None` on failure, triggering a fallback that rebuilds the candidate without the language info from the Whisper info object. Refactor to return the candidate directly from `transcribe_audio_to_segments`.

### P2-4: `subtitle_corrector.py` `check_drift` noun detection is case-sensitive

`_extract_nouns()` matches `\b[A-Z][a-zA-Z]+\b` — capitalized words only. If the raw subtitle has an all-caps proper noun (e.g. `TOYO`) or a name that appears lowercase in the LLM output, drift is missed. Low-frequency edge case but worth noting.

### P2-5: Doc sprawl in `anime-subtitle-pipeline` root

16 Markdown files in root: `API_DOCUMENTATION.md`, `BENCHMARK_IMPLEMENTATION.md`, `BENCHMARK_QUICKSTART.md`, `CHANGELOG.md`, `CODE_REVIEW_SUMMARY.md`, `EVALUATION.md`, `FILE_OVERVIEW.md`, `HOW_TO_RUN.md`, `PROJECT_SUMMARY.md`, `QUICKSTART.md`, `QUICK_REFERENCE.md`, `README.md`, `SECURITY.md`, `USAGE.md`, `CONTRIBUTING.md`.

Consolidate into: `README.md` (overview + quickstart), `CHANGELOG.md`, `SECURITY.md`. Move the rest to `docs/`.

---

## P3 — Nice to Have

### P3-1: `Anime_subtiltes/japanese-subtitle-generator` repo is superseded

This was the original prototype that used GitHub Models API. It's superseded by `anime-subtitle-pipeline` which uses local Ollama. Add a `README.md` deprecation notice pointing to `anime-subtitle-pipeline`, or archive the directory.

### P3-2: `attic/` directory has no README

Add `attic/README.md` explaining that this is a graveyard for retired code and scripts. Anyone reading the repo shouldn't wonder what `attic/` is for.

### P3-3: `compare_srt.py` vs `compare_core.py` vs `compare_subtitles.py`

Three comparison utilities at root with overlapping names. Clarify ownership and purpose, or consolidate.

### P3-4: `tracing.py` — OpenTelemetry setup not documented for Unraid

`tracing.py` emits OTLP traces if `TRACING_ENABLED=true`. On Unraid there's no collector configured. Document the env vars and show a minimal docker-compose fragment for running a Jaeger or OTEL collector alongside the pipeline container.

---

## Manual Steps Required (can't be done automatically)

```bash
# 1. Remove tracked build artifacts from git
cd anime-subtitle-pipeline
git rm --cached error_log.txt benchmark.py.backup comparison.json comparison_results.json benchmark_results.json debug_test.py
git rm -r --cached __pycache__

# 2. Delete the files from disk (Windows PowerShell)
Remove-Item error_log.txt, benchmark.py.backup, comparison.json, comparison_results.json, benchmark_results.json, debug_test.py

# 3. Commit everything
git add .gitignore asr.py llm_polish.py subtitle_corrector.py
git commit -m "security: gitignore .env + artifacts; fix OLLAMA_BASE_URL env var; fix asr setattr hack"

# 4. Unraid production: set env vars in docker-compose
# OLLAMA_BASE_URL=http://192.168.1.147:11434
# LLM_BASE_URL=http://192.168.1.147:11434  (after P1-5 is implemented)
```

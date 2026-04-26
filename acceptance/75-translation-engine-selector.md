# Acceptance Mapping - Issue #75: Translation Engine Selector

## Implemented

- Added top-level `translation` config support:
  - `engine`: `marian`, `llm_direct`, or `hybrid`
  - `fallback_engine`
  - `context_window_segments`
  - `mode`
  - `timeout`
- Added translation selector API in `mt.py`:
  - `translate_candidate(...)`
  - compatibility wrapper `translate_candidate_jp_to_en(...)`
  - clear `InvalidTranslationEngineError` for unsupported values
- `marian` keeps the existing MarianMT route.
- `llm_direct` translates each source cue through the local Ollama-compatible
  LLM endpoint with nearby source context.
- `hybrid` runs MarianMT first, then passes the source cue and Marian baseline
  into the LLM direct translator.
- LLM-based engines explicitly fall back to Marian when configured and record
  fallback metadata.
- Generate mode automatically uses the configured selector through existing
  Japanese subtitle and Japanese ASR translation call sites.
- Generate metadata includes translation engine/model/mode/fallback fields.
- Benchmark mode supports `benchmark.translation_engines` and emits separate
  candidates for each configured engine.
- Candidate metadata records engine, model, mode, fallback status, and hybrid
  baseline details.

## Tests

- `tests/test_translation_engine_selector.py`
  - Marian selector metadata
  - LLM direct selector metadata
  - LLM direct fallback to Marian
  - Hybrid baseline plus LLM output
  - invalid engine configuration
- `tests/test_benchmark_generalized.py`
  - benchmark fan-out for multiple translation engines
- `tests/test_config.py`
  - default translation config placement/accessors
- `tests/test_orchestrator.py`
  - generate-mode regression coverage remains green through selector wrapper

## Deferred

- Final model recommendation.
- Translation quality tuning.
- Removing MarianMT.

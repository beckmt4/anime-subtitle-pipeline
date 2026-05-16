# Acceptance Mapping - Issue #74: Direct Context-Aware LLM Translation Engine

## Implemented

- Added `LLMDirectTranslator` class in `mt.py`:
  - Calls a local Ollama-compatible endpoint (`llm.base_url` + `/api/generate`).
  - Translates each Japanese source cue directly to English without going through
    MarianMT.
  - Accepts a configurable context window (`translation.context_window_segments`)
    of surrounding source segments; the prompt marks the cue being translated with
    `>>` so the model outputs only the current segment.
  - Supports prompt modes `literal`, `natural_subtitle`, and `accuracy_first`
    (controlled by `translation.mode`).
  - Accepts an optional `baseline_candidate` (used by the `hybrid` engine path)
    and includes the baseline MarianMT translation in the prompt for reference.
  - Retries failed LLM requests up to two times before raising.
  - Returns a structured `SubtitleCandidate` whose segment timing is preserved
    exactly from the source candidate.
- Translation metadata recorded in candidate `meta`:
  - `translation_engine` (`llm_direct`)
  - `translation_model` (LLM model name)
  - `translation_mode`
  - `translation_dialogue_profile`
  - `context_window_segments`
  - `llm_base_url`
  - `translation_fallback` / `fallback_engine` / `fallback_reason` if fallback
    to MarianMT was triggered.
- Per-segment `meta.source_text_ja` records the original Japanese source for
  downstream QC judge checks.
- `translate_candidate_jp_to_en()` wrapper selects `llm_direct` or `hybrid`
  routes when configured; fails safely by falling back to Marian with explicit
  fallback metadata.

## Tests

- `tests/test_translation_engine_selector.py`
  - LLM direct selector metadata
  - LLM direct fallback to Marian with explicit metadata
  - Hybrid baseline plus LLM output
  - Context window sent in prompt (live-action profile test captures prompt)
  - Invalid engine configuration raises `InvalidTranslationEngineError`

## Deferred

- Cloud translation endpoints.
- Hardware-specific quantization tuning for LLM direct throughput.
- Full human review UI for flagged lines.
